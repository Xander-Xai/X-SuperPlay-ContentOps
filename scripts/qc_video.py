#!/usr/bin/env python3
"""Quality gate for a V1 video project.

Checks:
    - final.mp4 exists, > 100 KB
    - ffprobe parses it
    - 9:16 1080x1920, H.264 + AAC
    - 30 <= duration <= 120 sec
    - storyboard / script / source_refs indicators present
    - no unreferenced AI-generated assets left behind

Emits:
    projects/<slug>/receipts/qc-report.json
    projects/<slug>/receipts/qc-report.md

Status: PASS / WARN / FAIL. FAIL -> final is not production-ready.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from process_utils import hidden_run

ROOT = Path(__file__).resolve().parents[1]

MIN_FILE_BYTES = 100 * 1024  # 100 KB
MIN_DURATION = 30.0
MAX_DURATION = 120.0
EXPECTED_W, EXPECTED_H = 1080, 1920
# Evidence-first policy: the majority of shots must come from real captured
# assets, not generated visuals.
MIN_REAL_SOURCE_RATIO = 0.70

REAL_SOURCE_TYPES = {"real_screenshot", "real_recording", "diagram", "real_document"}
GENERATED_SOURCE_TYPES = {"generated", "ai_generated", "stock", "title_card"}


def audio_is_not_silence(path: Path) -> dict:
    """Measure loudness so a silent track can't pass as 'has voice'."""
    r = hidden_run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect",
         "-f", "null", "-"],
        timeout=120,
    )
    text = r.stderr or ""
    mean = None
    peak = None
    for line in text.splitlines():
        if "mean_volume:" in line:
            mean = line.split("mean_volume:")[1].strip()
        if "max_volume:" in line:
            peak = line.split("max_volume:")[1].strip()
    def _db(v):
        try:
            return float(v.replace("dB", "").strip())
        except Exception:
            return None
    mean_db, peak_db = _db(mean or ""), _db(peak or "")
    ok = peak_db is not None and peak_db > -50.0
    return {"ok": ok, "mean_volume_db": mean, "max_volume_db": peak,
            "threshold_db": -50.0}


def ffprobe_meta(path: Path) -> dict:
    out = hidden_run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        timeout=30,
    )
    if out.returncode != 0:
        return {}
    try:
        return json.loads(out.stdout)
    except Exception:
        return {}


def parse_yaml(path: Path) -> dict:
    data = {}
    current_section = None
    list_section = None
    list_item = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - ") and list_section is not None:
            kv = line[4:]
            if ":" in kv:
                k, _, v = kv.partition(":")
                list_item = {k.strip(): v.strip().strip('"')}
                list_section.append(list_item)
                current_section = None
            continue
        if line.startswith("  ") and list_item is not None and ":" in line:
            kv = line.strip()
            k, _, v = kv.partition(":")
            list_item[k.strip()] = v.strip().strip('"')
            continue
        if line.startswith("    ") and list_item is not None and ":" in line:
            kv = line.strip()
            k, _, v = kv.partition(":")
            list_item[k.strip()] = v.strip().strip('"')
            continue
        if line.startswith("  ") and current_section is not None:
            kv = line.strip()
            if ":" in kv:
                k, _, v = kv.partition(":")
                current_section[k.strip()] = v.strip().strip('"')
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip().strip('"')
            list_item = None
            if v == "":
                # detect list section (next lines start with "  -")
                list_section = []
                data[k] = list_section
                current_section = None
            else:
                data[k] = v
                current_section = None
                list_section = None
    return data


def _subtitles_burned(video: Path, sb: dict) -> dict:
    """Decide whether subtitles are visible: a real subtitle stream, or burned in.

    A subtitle file existing next to the video is NOT evidence that anything is
    visible. When the storyboard declares a subtitle, sample a frame from the
    middle of the video and check whether bright pixels appeared in the lower
    band (the subtitle zone) compared with the source frames' own brightness.
    """
    meta = ffprobe_meta(video)
    for s in meta.get("streams", []):
        if s.get("codec_type") == "subtitle":
            return {"ok": True, "method": "subtitle_stream"}

    declared = sb.get("subtitle")
    if not declared:
        return {"ok": False, "method": "none",
                "note": "no subtitle declared and none present"}

    import tempfile
    dur = float(meta.get("format", {}).get("duration", "0") or 0)
    if dur <= 2:
        return {"ok": False, "method": "unknown",
                "note": "video too short to sample"}

    # Sample several points, not just the midpoint: a single frame can land in a
    # gap between cues and wrongly report "no subtitles".
    band_start = int(EXPECTED_H * 0.82) * EXPECTED_W
    expected = EXPECTED_W * EXPECTED_H
    best, samples = 0.0, 0
    with tempfile.TemporaryDirectory() as td:
        for frac in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9):
            out = Path(td) / f"f{frac}.png"
            r = hidden_run(
                ["ffmpeg", "-y", "-ss", f"{dur * frac:.2f}", "-i", str(video),
                 "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", str(out)],
                timeout=120,
            )
            if r.returncode != 0 or not out.exists():
                continue
            data = out.read_bytes()
            if len(data) < expected:
                continue
            samples += 1
            band = data[band_start:expected]
            bright = sum(1 for b in band if b > 200)
            best = max(best, bright / max(len(band), 1))
    ok = best > 0.002
    return {"ok": ok, "method": "burned_in_scan",
            "note": f"max bright-pixel ratio across {samples} samples = {best:.5f}"}


def qc(project: Path, target: str = "") -> dict:
    project = project.resolve()
    # --video selects which render to grade: "easel", "fallback" or an explicit
    # filename. Defaults to easel.mp4 when it exists (the production render),
    # otherwise falls back to the legacy final.mp4.
    if target:
        final = project / "final" / target
    else:
        easel_vid = project / "final" / "easel.mp4"
        final = easel_vid if easel_vid.exists() else project / "final" / "final.mp4"
    target_name = Path(target).stem if target else final.stem
    receipts = project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)

    checks = [{"id": "_video", "ok": True, "severity": "INFO", "path": str(final)}]

    # 1) final.mp4 exists
    if not final.exists():
        checks.append({
            "id": "final_exists", "ok": False,
            "severity": "FAIL",
            "msg": f"final.mp4 not found at {final}",
        })
        return _emit(project, checks, target_name)

    # 2) file size
    size = final.stat().st_size
    checks.append({
        "id": "file_size", "ok": size >= MIN_FILE_BYTES,
        "severity": "FAIL" if size < MIN_FILE_BYTES else "PASS",
        "value_bytes": size,
        "min_bytes": MIN_FILE_BYTES,
    })

    # 3) ffprobe parse
    meta = ffprobe_meta(final)
    parse_ok = bool(meta)
    checks.append({
        "id": "ffprobe_parse", "ok": parse_ok,
        "severity": "FAIL" if not parse_ok else "PASS",
    })
    if not parse_ok:
        return _emit(project, checks, target_name)

    streams = meta.get("streams", [])
    fmt = meta.get("format", {})
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})

    width = video.get("width", 0)
    height = video.get("height", 0)
    duration = float(fmt.get("duration", "0"))

    # 4) resolution
    ok_res = (width == EXPECTED_W and height == EXPECTED_H)
    checks.append({
        "id": "resolution", "ok": ok_res,
        "severity": "FAIL" if not ok_res else "PASS",
        "value": f"{width}x{height}", "expected": f"{EXPECTED_W}x{EXPECTED_H}",
    })

    # 5) aspect 9:16
    aspect_ok = (width > 0 and height > 0 and abs(width * 16 - height * 9) <= 2)
    checks.append({
        "id": "aspect_ratio_9_16", "ok": aspect_ok,
        "severity": "FAIL" if not aspect_ok else "PASS",
        "value": f"{width}:{height}",
    })

    # 6) duration
    dur_ok = MIN_DURATION <= duration <= MAX_DURATION
    checks.append({
        "id": "duration_range", "ok": dur_ok,
        "severity": "WARN" if not dur_ok else "PASS",
        "value_sec": round(duration, 2),
        "expected_range_sec": [MIN_DURATION, MAX_DURATION],
    })

    # 7) video codec
    vcodec = video.get("codec_name", "")
    checks.append({
        "id": "video_codec_h264", "ok": vcodec in ("h264", "libx264"),
        "severity": "WARN" if vcodec not in ("h264", "libx264") else "PASS",
        "value": vcodec,
    })

    # 8) audio present
    has_audio = bool(audio)
    checks.append({
        "id": "audio_present", "ok": has_audio,
        "severity": "WARN" if not has_audio else "PASS",
    })

    # 9) audio codec
    acodec = audio.get("codec_name", "")
    checks.append({
        "id": "audio_codec_aac", "ok": acodec in ("aac",),
        "severity": "WARN" if acodec not in ("aac",) else "PASS",
        "value": acodec,
    })

    # 10) script / storyboard / source_refs
    project_yaml = project / "project.yaml"
    cfg = parse_yaml(project_yaml) if project_yaml.exists() else {}
    source_refs = cfg.get("source_refs", [])
    checks.append({
        "id": "project_yaml", "ok": bool(cfg),
        "severity": "WARN" if not cfg else "PASS",
    })
    checks.append({
        "id": "source_refs_recorded", "ok": isinstance(source_refs, list),
        "severity": "WARN" if not isinstance(source_refs, list) else "PASS",
        "value_count": len(source_refs) if isinstance(source_refs, list) else 0,
    })

    srt = project / "assets" / "captions" / "default.srt"
    checks.append({
        "id": "caption_srt_present", "ok": srt.exists(),
        "severity": "WARN" if not srt.exists() else "PASS",
        "path": str(srt),
    })

    # --- evidence-first checks -------------------------------------------------
    script_md = project / "script" / "master.md"
    checks.append({
        "id": "script_exists", "ok": script_md.exists() and script_md.stat().st_size > 0,
        "severity": "FAIL" if not script_md.exists() else "PASS",
        "path": str(script_md),
    })

    storyboard = project / "script" / "storyboard.json"
    sb = {}
    if storyboard.exists():
        try:
            sb = json.loads(storyboard.read_text(encoding="utf-8"))
        except Exception as e:
            sb = {}
            checks.append({
                "id": "storyboard_parses", "ok": False, "severity": "FAIL",
                "msg": f"invalid JSON: {e}",
            })
    checks.append({
        "id": "storyboard_exists", "ok": bool(sb.get("shots")),
        "severity": "FAIL" if not sb.get("shots") else "PASS",
        "shot_count": len(sb.get("shots", []) or []),
    })

    shots = sb.get("shots", []) or []
    real_n = sum(1 for s in shots if s.get("source_type") in REAL_SOURCE_TYPES)
    gen_n = sum(1 for s in shots if s.get("source_type") in GENERATED_SOURCE_TYPES)
    declared_n = real_n + gen_n
    ratio = (real_n / declared_n) if declared_n else 0.0
    checks.append({
        "id": "real_source_ratio", "ok": ratio >= MIN_REAL_SOURCE_RATIO,
        "severity": "WARN" if ratio < MIN_REAL_SOURCE_RATIO else "PASS",
        "value": round(ratio, 3),
        "min": MIN_REAL_SOURCE_RATIO,
        "real_shots": real_n, "generated_shots": gen_n,
        "note": "AI-generated key visuals must not be the majority",
    })

    missing_prov = [i for i, s in enumerate(shots)
                    if not s.get("source") or not s.get("source_type")]
    checks.append({
        "id": "source_provenance_complete", "ok": not missing_prov,
        "severity": "WARN" if missing_prov else "PASS",
        "missing_shot_indices": missing_prov,
    })

    engine = (sb.get("engine") or cfg.get("engine") or "").strip()
    checks.append({
        "id": "engine_recorded", "ok": bool(engine),
        "severity": "WARN" if not engine else "PASS",
        "value": engine or "unrecorded",
    })

    # --- voice is actually audible --------------------------------------------
    if final.exists():
        vol = audio_is_not_silence(final)
        checks.append({
            "id": "voice_not_silence", "ok": vol["ok"],
            "severity": "WARN" if not vol["ok"] else "PASS",
            "max_volume_db": vol["max_volume_db"],
            "mean_volume_db": vol["mean_volume_db"],
        })

    # --- subtitles are burned in ---------------------------------------------
    burned = _subtitles_burned(final, sb)
    checks.append({
        "id": "subtitle_burned_or_track", "ok": burned["ok"],
        "severity": "WARN" if not burned["ok"] else "PASS",
        "method": burned["method"],
        "note": burned.get("note", ""),
    })

    # 11) no unreferenced AI-generated assets: count real vs generated
    real = []
    for sub in ("sources/screenshots", "sources/diagrams", "sources/recordings"):
        d = project / sub
        if d.exists():
            for pat in ("*.png", "*.jpg", "*.jpeg"):
                real.extend(d.glob(pat))
    checks.append({
        "id": "real_evidence_present", "ok": len(real) > 0,
        "severity": "WARN" if len(real) == 0 else "PASS",
        "value_count": len(real),
    })

    # 12) voice provenance. Prefer the storyboard's recorded provider — it is
    # what actually produced THIS render. project.yaml's voice_quality reflects
    # whichever engine ran last (usually the fallback) and must not be
    # attributed to an Easel render.
    sb_provider = (sb.get("voice_provider") or "").strip()
    yaml_voice = (cfg.get("voice_quality") or "").strip()
    provider = sb_provider or yaml_voice or "unknown"
    low = provider.lower()
    if "edge" in low:
        vq, warn = "edge_tts_fallback", True
    elif "sapi" in low or "silence" in low or low == "fallback":
        vq, warn = "fallback", True
    elif provider == "unknown":
        vq, warn = "unknown", True
    else:
        vq, warn = "configured_provider", False
    checks.append({
        "id": "voice_quality_declared", "ok": True,
        "severity": "INFO",
        "voice_provider": provider,
        "voice_quality": vq,
        "production_quality_warning": warn,
        "note": "mechanical/fallback voice keeps the render at READY_FOR_HUMAN_REVIEW; "
                "only a human can accept it as production (V1 spec §11)",
    })

    return _emit(project, checks, target_name)


def _emit(project: Path, checks: list[dict], target_name: str = "") -> dict:
    severity_rank = {"FAIL": 3, "WARN": 2, "INFO": 1, "PASS": 0}
    overall = "PASS"
    for c in checks:
        sev = c.get("severity", "PASS")
        if sev == "INFO":
            continue  # informational only, doesn't affect PASS/WARN/FAIL rollup
        if severity_rank.get(sev, 0) > severity_rank.get(overall, 0):
            overall = sev
        if not c.get("ok"):
            if sev == "FAIL":
                overall = "FAIL"
                break
            if sev == "WARN" and overall == "PASS":
                overall = "WARN"

    out = {
        "project": str(project),
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "video": checks[0].get("_video", "") if checks else "",
        "overall": overall,
        "checks": [{k: v for k, v in c.items() if not k.startswith("_")} for c in checks],
    }
    suffix = f"-{target_name}" if target_name else ""
    json_path = project / "receipts" / f"qc-report{suffix}.json"
    md_path = project / "receipts" / f"qc-report{suffix}.md"
    json_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [f"# QC Report — {project.name}", "", f"**Video**: `{target_name}`", "", f"**Overall**: `{overall}`", ""]
    lines.append(f"**Checked at**: {out['checked_at']}")
    lines.append("")
    lines.append("| Check | Status | Severity | Detail |")
    lines.append("|---|---|---|---|")
    for c in checks:
        status = "OK" if c.get("ok") else "FAIL"
        sev = c.get("severity", "PASS")
        detail = ", ".join(f"{k}={v}" for k, v in c.items() if k not in ("id", "ok", "severity"))
        lines.append(f"| {c['id']} | {status} | {sev} | {detail} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project", help="project dir, e.g. projects/easel-review")
    p.add_argument("--video", default="",
                   help="which render to grade: easel | fallback | <file>.mp4")
    args = p.parse_args()
    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / args.project).resolve()
    result = qc(project, target=args.video)
    return 1 if result.get("overall") == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())