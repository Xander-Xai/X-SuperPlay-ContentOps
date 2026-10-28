#!/usr/bin/env python3
"""Compose a code-animation sample from external-skill clips.

The animation is rendered by an external skill (huashu-art-motion's engine);
this driver owns the parts that belong to ContentOps:

1. **Timeline** — `motion/timeline.json` lists beat segments and optional
   claim-free inserts. Each beat binds one synthesised line; an insert plays
   silently, so no factual assertion rides on generated media.
2. **Narration placement** — each line sits at its segment start, so voice and
   picture share one timeline (audio-first).
3. **Captions** — an SRT from the measured line durations, burned with the
   account DNA style through ``assemble_easel``.
4. **Receipts** — spec/clip/output hashes, engine provenance, the generated
   duration share, ffprobe facts and a technical QC summary. It refuses a
   generated share of 10 % or more and never claims production readiness.

Usage::

    python scripts/build_code_animation_sample.py projects/easel-fi-what-is-agent
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from contentops.media.transport import ffprobe_json  # noqa: E402
from contentops.media.video_qc import measure_video  # noqa: E402

BEAT_SECONDS = 4.0
MAX_GENERATED_RATIO = 0.10
SAMPLE_SCHEMA = "contentops.code-animation-sample/v1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _yaml(path: Path) -> Dict[str, str]:
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip().strip('"')
    return data


def _caption_style(slug: str) -> Dict[str, Any]:
    dna = json.loads((ROOT / "config" / "accounts" / f"{slug}.json").read_text(
        encoding="utf-8"))
    caption = dna["visual"]["caption_style"]
    style: Dict[str, str] = {}
    for part in caption["burn_style"].split(","):
        key, _, value = part.partition("=")
        key = key.strip()
        if key and key not in ("Fontsize", "MarginV", "Alignment"):
            style[key] = value.strip()
    return {"style": style, "font_size": int(caption["size_px"]),
            "margin_v": int(caption["safe_zone"]["margin_v_px"])}


def _timeline(project: Path, line_count: int) -> List[Dict[str, Any]]:
    path = project / "motion" / "timeline.json"
    if path.is_file():
        doc = json.loads(path.read_text(encoding="utf-8"))
        segments = doc["segments"]
    else:
        segments = [{"type": "beat", "clip": f"p{i:02d}", "line": i}
                    for i in range(1, line_count + 1)]
    for segment in segments:
        segment.setdefault("duration", BEAT_SECONDS if segment["type"] == "beat" else None)
        if segment["type"] == "beat":
            if not 1 <= int(segment["line"]) <= line_count:
                raise SystemExit(f"timeline line out of range: {segment}")
        elif segment["type"] != "insert":
            raise SystemExit(f"unknown segment type: {segment['type']}")
    return segments


def _place_narration(project: Path, lines: Dict[int, Dict[str, Any]],
                     segments: List[Dict[str, Any]]) -> Tuple[Path, List[Dict[str, Any]]]:
    """Write one PCM track; each beat line starts at its segment start."""
    first_line = next(line for line in lines.values())
    first_path = project / first_line["path"].replace("project://", "")
    with wave.open(str(first_path), "rb") as first:
        rate, channels, width = first.getframerate(), first.getnchannels(), first.getsampwidth()
    total_s = sum(float(segment["duration"]) for segment in segments)
    buffer = bytearray(int(round(total_s * rate)) * channels * width)
    cursor = 0.0
    placed = []
    for segment in segments:
        if segment["type"] == "beat":
            row = lines[int(segment["line"])]
            source = project / row["path"].replace("project://", "")
            with wave.open(str(source), "rb") as handle:
                if (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()) != (rate, channels, width):
                    raise SystemExit(f"sample format differs: {source}")
                frames = handle.readframes(handle.getnframes())
            offset = int(round(cursor * rate)) * channels * width
            buffer[offset:offset + len(frames)] = frames
            placed.append({"line": int(segment["line"]), "start_s": round(cursor, 3),
                           "duration_s": row["duration_s"]})
        cursor += float(segment["duration"])
    target = project / "work" / "narration.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(bytes(buffer))
    return target, placed


def _write_srt(project: Path, lines: Dict[int, Dict[str, Any]],
               placed: List[Dict[str, Any]]) -> Path:
    target = project / "assets" / "captions" / "cut.srt"
    target.parent.mkdir(parents=True, exist_ok=True)

    def ts(ms: int) -> str:
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    rows = []
    for index, item in enumerate(placed, 1):
        row = lines[item["line"]]
        start = int(round(item["start_s"] * 1000))
        end = min(start + int(round(row["duration_s"] * 1000)), start + 3900)
        rows.append(f"{index}\n{ts(start)} --> {ts(end)}\n{row['text']}\n")
    target.write_text("\n".join(rows), encoding="utf-8")
    return target


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--out-name", default="easel")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()
    config = _yaml(project / "project.yaml")
    voice = json.loads((project / "receipts" / "voice-lines.json").read_text(encoding="utf-8"))
    lines = {int(row["line"]): row for row in voice["lines"]}
    segments = _timeline(project, len(lines))

    clips = []
    for segment in segments:
        clip = project / "work" / "clips" / f"{segment['clip']}.mp4"
        if not clip.is_file():
            print(json.dumps({"status": "BLOCKED", "reason": f"missing clip {clip}"},
                             ensure_ascii=False))
            return 4
        segment["path"] = clip
        clips.append(clip)

    narration, placed = _place_narration(project, lines, segments)
    srt = _write_srt(project, lines, placed)

    storyboard = {
        "size": config.get("format", "1080x1920"),
        "engine": "easel",
        "pad_mode": "trim",
        "narration": str(narration),
        "subtitle": str(srt),
        "voice_provider": "minimax-mplan",
        "shots": [{"video": str(segment["path"]), "duration": float(segment["duration"])}
                  for segment in segments],
    }
    storyboard_path = project / "work" / "storyboard.json"
    storyboard_path.write_text(json.dumps(storyboard, indent=2, ensure_ascii=False),
                               encoding="utf-8")

    total_s = sum(float(segment["duration"]) for segment in segments)
    generated_s = sum(float(segment["duration"]) for segment in segments
                      if segment["type"] == "insert" and segment.get("generated"))
    ratio = generated_s / total_s if total_s else 0.0
    if ratio >= MAX_GENERATED_RATIO:
        print(json.dumps({"status": "BLOCKED",
                          "reason": f"generated share {ratio:.1%} is not below "
                                    f"{MAX_GENERATED_RATIO:.0%}"}, ensure_ascii=False))
        return 6
    silent_claims = [segment for segment in segments
                     if segment["type"] == "insert" and segment.get("claim_bearing")]
    if silent_claims:
        print(json.dumps({"status": "BLOCKED",
                          "reason": "an insert may not be claim-bearing"}, ensure_ascii=False))
        return 6

    style = _caption_style(config["account_slug"])
    from assemble_easel import run as assemble
    result = assemble(project, out_name=args.out_name, strict_captions=True,
                      storyboard_path=storyboard_path,
                      caption_style=style["style"],
                      caption_font_size=style["font_size"],
                      caption_margin_v=style["margin_v"])
    if result.get("status") != "OK":
        print(json.dumps(result, ensure_ascii=False))
        return 5

    output = Path(result["video"])
    measured = measure_video(output)
    meta = ffprobe_json(output)
    audio = next((s for s in meta.get("streams", []) if s.get("codec_type") == "audio"), {})
    visual = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), {})

    segment_rows = []
    grammars = set()
    for segment in segments:
        row = {"type": segment["type"], "clip": f"project://work/clips/{segment['path'].name}",
               "duration_s": float(segment["duration"]),
               "clip_sha256": _sha(segment["path"])}
        if segment["type"] == "beat":
            spec = project / "motion" / "specs" / f"{segment['clip']}.json"
            spec_doc = json.loads(spec.read_text(encoding="utf-8"))
            grammars.add(spec_doc.get("grammar", ""))
            row.update({"line": int(segment["line"]),
                        "spec": f"project://motion/specs/{spec.name}",
                        "spec_sha256": _sha(spec),
                        "grammar": spec_doc.get("grammar")})
        else:
            row.update({"generated": segment.get("generated"),
                        "claim_bearing": bool(segment.get("claim_bearing", False)),
                        "role": "claim-free insert"})
        segment_rows.append(row)

    receipt = {
        "schema": SAMPLE_SCHEMA,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "package_id": project.name,
        "content_type": "DEFINITIONAL_EXPLAINER",
        "claim_bearing": False,
        "external_skill": {
            "name": "huashu-art-motion",
            "version": "1.2.0",
            "license": "MIT",
            "engine": "scripts/engine/render.py",
            "grammar": sorted(g for g in grammars if g),
            "windows_adapter": "Playwright channel fallback (chrome/msedge) and PYTHONUTF8=1 for spec JSON",
        },
        "timeline": {"total_s": round(total_s, 3), "segments": len(segments),
                     "beats": sum(1 for s in segments if s["type"] == "beat"),
                     "inserts": sum(1 for s in segments if s["type"] == "insert")},
        "generated_media": {"seconds": round(generated_s, 3),
                            "ratio": round(ratio, 4),
                            "cap": MAX_GENERATED_RATIO,
                            "policy": "claim-free inserts only; deletes if it does not improve"},
        "segments": segment_rows,
        "voice": {"provider": voice.get("voice", "speech-2.8-hd"),
                  "lines": voice["lines"], "receipts": "project://receipts/voice-lines.json"},
        "captions": {"path": "project://assets/captions/cut.srt", "sha256": _sha(srt),
                     "style_source": f"config/accounts/{config['account_slug']}.json",
                     "cues": len(placed)},
        "output": {"path": f"project://{output.relative_to(project).as_posix()}",
                   "sha256": _sha(output),
                   "duration_s": float(meta["format"]["duration"]),
                   "width": visual.get("width"), "height": visual.get("height"),
                   "video_codec": visual.get("codec_name"),
                   "audio_codec": audio.get("codec_name") or None},
        "technical_qc": {
            "decodable": measured.decodable,
            "longest_black_run_s": measured.longest_black_run_s,
            "longest_freeze_run_s": measured.longest_freeze_run_s,
            "analysed_frames": measured.analysed_frames,
            "notes": list(measured.notes),
            "reasons": list(measured.reasons),
        },
        "red_lines": {
            "manual_recording": "none — pure code animation",
            "mouse_or_desktop": "none",
            "ai_generated_footage": "generated inserts are claim-free and below the 10% cap",
            "platform_url_claimed": False,
        },
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }
    (project / "receipts" / "sample.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "OK", "output": receipt["output"],
                      "generated_ratio": ratio,
                      "qc": {"decodable": measured.decodable,
                             "freeze_s": measured.longest_freeze_run_s,
                             "black_s": measured.longest_black_run_s},
                      "receipt": "receipts/sample.json"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
