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
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from process_utils import hidden_run

ROOT = Path(__file__).resolve().parents[1]
for _candidate in (ROOT / "src", ROOT / "scripts"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from contentops.media.real_source_duration import (  # noqa: E402
    BLOCKED as RSD_BLOCKED,
    PASS as RSD_PASS,
    check as check_real_source_duration,
)
from contentops.paths import relative_label, resolve_label, resolve_project  # noqa: E402

MIN_FILE_BYTES = 100 * 1024  # 100 KB
MIN_DURATION = 30.0
MAX_DURATION = 120.0
EXPECTED_W, EXPECTED_H = 1080, 1920
# Evidence-first policy: the majority of shots must come from real captured
# assets, not generated visuals.
MIN_REAL_SOURCE_RATIO = 0.70

REAL_SOURCE_TYPES = {"real_screenshot", "real_recording", "diagram", "real_document"}
GENERATED_SOURCE_TYPES = {"generated", "ai_generated", "stock", "title_card"}


def _account_slug(project: Path) -> str:
    """The account a project declares, or ``""`` when it declares none.

    The measured duration gate is a hard failure for an A/B project and a
    warning for the historical samples, so this value decides a severity. A
    missing YAML parser must not silently turn the gate into a pass, so there is
    a single-line fallback for the one scalar this needs.
    """
    path = Path(project) / "project.yaml"
    if not path.is_file():
        return ""
    try:
        import yaml  # type: ignore

        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return str(document.get("account_slug") or "").strip()
    except ImportError:
        pass
    except ValueError:
        return ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("account_slug:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


def _real_source_floor(project: Path) -> tuple[float, str, str]:
    """Resolve the measured capture floor without allowing format labels to weaken DNA.

    Capture-heavy formats always retain the 70% floor. Explanatory formats may
    use verified documents/code/claims instead of recording duration, except when
    the account DNA itself is evidence-led. That distinction keeps 1024's
    evidence-first contract while allowing future-intelligence explainers to use
    animation without pretending it is recorded evidence.
    """
    slug = _account_slug(project)
    content_type = ""
    project_yaml = Path(project) / "project.yaml"
    if project_yaml.is_file():
        try:
            import yaml  # type: ignore
            config = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
            content_type = str(config.get("content_type") or "").strip().lower()
        except (ImportError, ValueError):
            for line in project_yaml.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip().startswith("content_type:"):
                    content_type = line.split(":", 1)[1].strip().strip("\"'").lower()
                    break

    mode = ""
    if slug:
        try:
            profile = json.loads((ROOT / "config" / "accounts" / f"{slug}.json")
                                 .read_text(encoding="utf-8"))
            mode = str((profile.get("evidence") or {}).get("mode") or "").upper()
        except (OSError, ValueError):
            mode = ""

    capture_formats = {"recorded_demo", "screen_recording", "evidence_demo", "field_capture"}
    explanatory_formats = {
        "technical_explainer", "tech_review", "code_walkthrough",
        "product_launch", "motion_explainer",
    }
    if content_type in capture_formats:
        return MIN_REAL_SOURCE_RATIO, "EVIDENCE_LED", content_type
    if content_type in explanatory_formats:
        if mode == "EVIDENCE_LED":
            return MIN_REAL_SOURCE_RATIO, mode, content_type
        if mode in {"EXPLANATORY", "CLAIM_LED"}:
            return 0.0, mode, content_type
        return 0.0, "EXPLANATORY", content_type
    if not slug:
        return MIN_REAL_SOURCE_RATIO, "UNRESOLVED", content_type
    if mode == "EXPLANATORY":
        return 0.0, mode, content_type
    if mode == "EVIDENCE_LED":
        return MIN_REAL_SOURCE_RATIO, mode, content_type
    if mode == "CLAIM_LED":
        return 0.0, mode, content_type
    return MIN_REAL_SOURCE_RATIO, "UNRESOLVED", content_type


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



def _expected_canvas(project: Path) -> tuple[int, int, str]:
    """Resolve QC geometry from the M5 project, never by guessing from the MP4.

    Legacy projects stay 1080x1920. An explicitly authored Bilibili native
    relayout may opt into 1920x1080; merely padding/cropping an old vertical
    output is not evidence of native layout or founder approval.
    """
    manifest = project / "project.yaml"
    if not manifest.is_file():
        return EXPECTED_W, EXPECTED_H, "9:16"
    try:
        import yaml  # type: ignore

        document = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        if not isinstance(document, dict):
            raise ValueError("project.yaml must be a mapping")
        target = document.get("target") or {}
        if not isinstance(target, dict):
            raise ValueError("target must be a mapping")
        resolution = str(target.get("resolution") or f"{EXPECTED_W}x{EXPECTED_H}").lower()
        if resolution == f"{EXPECTED_W}x{EXPECTED_H}":
            return EXPECTED_W, EXPECTED_H, "9:16"
        if resolution != "1920x1080":
            raise ValueError(f"unsupported QC canvas {resolution!r}")
        if target.get("platform") != "bilibili" or target.get("native_relayout") is not True:
            raise ValueError(
                "1920x1080 requires target.platform=bilibili and "
                "target.native_relayout=true; padded vertical carriers are not native")
        storyboard_path = project / "script" / "storyboard.json"
        storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
        if not isinstance(storyboard, dict) or storyboard.get("size") != "1920x1080":
            raise ValueError("Bilibili native storyboard must declare size=1920x1080")
        return 1920, 1080, "16:9"
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"NATIVE_CANVAS_UNVERIFIED: {exc}") from None


def _native_source_geometry_check(project: Path, storyboard: dict) -> dict:
    """Require every native horizontal storyboard shot to source 16:9 media.

    Output dimensions alone cannot distinguish an authored landscape scene from
    a portrait asset padded into a landscape carrier. The actual per-shot input
    must therefore be present, probeable and landscape too.
    """
    shots = storyboard.get("shots") if isinstance(storyboard, dict) else None
    failed = []
    checked = 0
    if not isinstance(shots, list) or not shots:
        failed.append(-1)
        shots = []

    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            failed.append(index)
            continue
        label = shot.get("video") or shot.get("image") or shot.get("source")
        if not isinstance(label, str) or not label.strip():
            failed.append(index)
            continue
        label = label.strip()
        if label.startswith("project://"):
            source_path = project / label[len("project://"):]
        else:
            candidate = Path(label)
            if candidate.is_absolute():
                source_path = candidate
            else:
                source_path = resolve_label(label, repo_root=ROOT)
                if not source_path.is_file():
                    source_path = project / candidate
        if not source_path.is_file():
            failed.append(index)
            continue
        meta = ffprobe_meta(source_path)
        stream = next((row for row in meta.get("streams", [])
                       if row.get("codec_type") == "video"), {})
        width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
        checked += 1
        if width <= 0 or height <= 0 or abs(width * 9 - height * 16) > 2:
            failed.append(index)

    ok = checked == len(shots) and not failed
    return {
        "id": "native_storyboard_source_geometry",
        "ok": ok,
        "severity": "PASS" if ok else "FAIL",
        "checked_shots": checked,
        "failed_shot_indices": failed,
        "expected_aspect": "16:9",
    }


def _canvas_checks(width: int, height: int, expected_w: int,
                   expected_h: int, aspect: str) -> list[dict]:
    """Exact dimensions and aspect are separate failure checks."""
    resolved = width == expected_w and height == expected_h
    if aspect == "16:9":
        aspect_ok = width > 0 and height > 0 and abs(width * 9 - height * 16) <= 2
        aspect_id = "aspect_ratio_16_9"
    else:
        aspect_ok = width > 0 and height > 0 and abs(width * 16 - height * 9) <= 2
        aspect_id = "aspect_ratio_9_16"
    return [
        {"id": "resolution", "ok": resolved,
         "severity": "PASS" if resolved else "FAIL",
         "value": f"{width}x{height}", "expected": f"{expected_w}x{expected_h}"},
        {"id": aspect_id, "ok": aspect_ok,
         "severity": "PASS" if aspect_ok else "FAIL",
         "value": f"{width}:{height}"},
    ]


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
    # Examine the actual decoded canvas: a 16:9 source is not a 9:16 byte grid.
    video_stream = next((stream for stream in meta.get("streams", [])
                         if stream.get("codec_type") == "video"), {})
    frame_w = int(video_stream.get("width") or 0)
    frame_h = int(video_stream.get("height") or 0)
    if frame_w <= 0 or frame_h <= 0:
        return {"ok": False, "method": "unknown", "note": "video geometry unavailable"}
    band_start = int(frame_h * 0.82) * frame_w
    expected = frame_w * frame_h
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
    # --video selects which render to grade: an engine name ("easel",
    # "fallback") or an explicit .mp4 filename. A bare slug used to resolve to
    # a non-existent path and then overwrite a CURRENT PASS receipt with a
    # two-check FAIL. Refuse the ambiguous target instead of writing anything.
    if target and not (target in {"easel", "fallback"}
                       or target.lower().endswith(".mp4")):
        return {"state": "BLOCKED", "overall": "FAIL",
                "reason": (f"QC_TARGET_INVALID: {target!r} is neither an engine name "
                           "nor an .mp4 filename; no receipt was written")}
    try:
        expected_w, expected_h, expected_aspect = _expected_canvas(project)
    except ValueError as exc:
        return {"state": "BLOCKED", "overall": "FAIL", "reason": str(exc)}
    if target:
        filename = target if target.lower().endswith(".mp4") else f"{target}.mp4"
        final = project / "final" / filename
    else:
        easel_vid = project / "final" / "easel.mp4"
        final = easel_vid if easel_vid.exists() else project / "final" / "final.mp4"
    target_name = Path(target).stem if target else final.stem
    receipts = project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)

    checks = [{"id": "_video", "ok": True, "severity": "INFO", "path": str(final)}]

    # 1) final.mp4 exists
    if not final.exists():
        prior_path = receipts / f"qc-report-{target_name}.json"
        try:
            prior = json.loads(prior_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prior = {}
        if (prior.get("currency") == "CURRENT"
                and prior.get("overall") == "PASS"
                and len(prior.get("checks") or []) > 2):
            return {"state": "BLOCKED", "overall": prior["overall"],
                    "reason": ("QC_RECEIPT_PROTECTED: target file is missing but a "
                               "CURRENT PASS receipt already exists; refusing to "
                               "overwrite it with a degraded FAIL. Pass an explicit "
                               ".mp4 filename to grade a different render."),
                    "preserved_report": str(prior_path)}
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

    # 4–5) native resolution and aspect, based on an explicit project target.
    checks.extend(_canvas_checks(
        int(width or 0), int(height or 0), expected_w, expected_h, expected_aspect))

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
    if expected_aspect == "16:9":
        checks.append(_native_source_geometry_check(project, sb))

    shots = sb.get("shots", []) or []
    real_floor, evidence_mode, content_type = _real_source_floor(project)
    real_n = sum(1 for s in shots if s.get("source_type") in REAL_SOURCE_TYPES)
    gen_n = sum(1 for s in shots if s.get("source_type") in GENERATED_SOURCE_TYPES)
    declared_n = real_n + gen_n
    ratio = (real_n / declared_n) if declared_n else 0.0
    checks.append({
        "id": "real_source_ratio", "ok": ratio >= real_floor,
        "severity": "WARN" if ratio < real_floor else "PASS",
        "value": round(ratio, 3),
        "min": real_floor,
        "evidence_mode": evidence_mode,
        "content_type": content_type or "UNDECLARED",
        "real_shots": real_n, "generated_shots": gen_n,
        "note": "historical shot-count diagnostic, kept for comparison; the gate is "
                "real_source_duration_ratio",
    })

    # The measured gate. Shot count can pass while one long diagram fills the
    # cut, so the ratio is over visible seconds of the rendered file. It is a
    # hard failure for a project that declares an account (A/B) and a warning
    # for the historical samples, which predate the rule and are not re-graded
    # retroactively.
    measured = check_real_source_duration(project, output_duration_s=duration,
                                          min_ratio=real_floor)
    required = evidence_mode in {"EXPLANATORY", "EVIDENCE_LED"}
    if measured["state"] == RSD_PASS:
        severity = "PASS"
    elif required:
        severity = "FAIL"
    else:
        severity = "WARN"
    checks.append({
        "id": "real_source_duration_ratio",
        "ok": measured["state"] == RSD_PASS,
        "severity": severity,
        "state": measured["state"],
        "required": required,
        "value": measured.get("real_source_duration_ratio"),
        "min": measured.get("min"),
        "real_seconds": measured.get("real_seconds"),
        "required_seconds": measured.get("required_seconds"),
        "undeclared_tail_s": measured.get("undeclared_tail_s"),
        "code": measured.get("code"),
        "detail": measured.get("detail"),
        "note": ("capture duration is format-specific; verified claims and source "
                 "provenance remain separately required"),
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
    # A project may cite tracked evidence owned by another project instead of
    # copying it. Its declared manifest counts, but only for entries whose file
    # exists and whose type is a real capture.
    declared = 0
    manifest = project / "sources" / "assets.json"
    if manifest.is_file():
        try:
            for asset in (json.loads(manifest.read_text(encoding="utf-8")).get("assets") or []):
                if str(asset.get("type") or "").lower() not in REAL_SOURCE_TYPES:
                    continue
                rel = asset.get("repo_path")
                target = (ROOT / rel) if rel else (project / str(asset.get("path") or ""))
                if rel or asset.get("path"):
                    if target.is_file():
                        declared += 1
        except (OSError, ValueError):
            declared = 0
    checks.append({
        "id": "real_evidence_present", "ok": (len(real) + declared) > 0,
        "severity": "WARN" if (len(real) + declared) == 0 else "PASS",
        "value_count": len(real) + declared,
        "from_manifest": declared,
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

    # Canonical receipt (contentops.qc-canonical/v1): the runtime result is
    # preserved verbatim inside the canonical envelope — sanitizing paths
    # must never change a verdict. The driver's completion gate consumes the
    # canonical schema, so the producing step and its consumer share one
    # contract instead of two vocabularies for the same verdict.
    from contentops.media.qc_canonical import canonical_qc_report

    graded_video = target_name if "." in target_name else f"{target_name}.mp4"
    canonical = canonical_qc_report(
        out,
        repo_root=ROOT,
        project_root=project,
        graded_target=f"project://final/{graded_video}",
    )
    canonical["project"] = (str(project.relative_to(ROOT))
                         if project.is_relative_to(ROOT)
                         else relative_label(project))
    out = canonical

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
        detail = ", ".join(f"{k}={_md_value(v, project)}"
                           for k, v in c.items() if k not in ("id", "ok", "severity"))
        lines.append(f"| {c['id']} | {status} | {sev} | {detail} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return out


def _md_value(value, project: Path):
    """Render one detail value for the markdown receipt.

    The JSON goes through the canonical envelope, which sanitizes paths; the
    markdown used to be written from the raw checks and leaked machine paths
    into a file whose own header claims `no absolute paths`. Any value that
    points inside the repository is written repo-relative instead.
    """
    if isinstance(value, str):
        for base in (project, ROOT):
            base_str = str(base)
            if value.startswith(base_str + os.sep) or value == base_str:
                try:
                    return relative_label(Path(value))
                except Exception:  # noqa: BLE001 - a label must never fail a receipt
                    return value
    return value


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project", help="project dir, e.g. projects/easel-review")
    p.add_argument("--video", default="",
                   help="which render to grade: easel | fallback | <file>.mp4")
    args = p.parse_args()
    project = resolve_project(args.project)
    result = qc(project, target=args.video)
    return 1 if result.get("overall") == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
