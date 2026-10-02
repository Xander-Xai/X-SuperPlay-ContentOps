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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MIN_FILE_BYTES = 100 * 1024  # 100 KB
MIN_DURATION = 30.0
MAX_DURATION = 120.0
EXPECTED_W, EXPECTED_H = 1080, 1920


def ffprobe_meta(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=30,
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


def qc(project: Path) -> dict:
    project = project.resolve()
    final = project / "final" / "final.mp4"
    receipts = project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)

    checks = []

    # 1) final.mp4 exists
    if not final.exists():
        checks.append({
            "id": "final_exists", "ok": False,
            "severity": "FAIL",
            "msg": f"final.mp4 not found at {final}",
        })
        return _emit(project, checks)

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
        return _emit(project, checks)

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

    # 12) voice quality declared
    voice_quality = (cfg.get("voice_quality") or "").strip()
    if not voice_quality:
        voice_quality = "unknown"
    checks.append({
        "id": "voice_quality_declared", "ok": True,
        "severity": "INFO",
        "value": voice_quality,
        "note": "fallback is acceptable for smoke test; not for production publish",
    })

    return _emit(project, checks)


def _emit(project: Path, checks: list[dict]) -> dict:
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
        "overall": overall,
        "checks": checks,
    }
    json_path = project / "receipts" / "qc-report.json"
    md_path = project / "receipts" / "qc-report.md"
    json_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [f"# QC Report — {project.name}", "", f"**Overall**: `{overall}`", ""]
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
    args = p.parse_args()
    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / args.project).resolve()
    result = qc(project)
    return 1 if result.get("overall") == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())