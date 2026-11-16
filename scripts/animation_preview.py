#!/usr/bin/env python3
"""One-shot local preview for a rendered animation clip (P1.2).

Given a short clip and its shot spec, produce first/middle/last frames, a
contact sheet, and a single JSON preview card carrying template parameters,
the render log, the technical QC result, and the input source/rights state.
This reuses ``qc_visual.build_contact_sheet`` and does not add an editor.
Nothing here approves publication or changes a receipt's governance flags.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from process_utils import hidden_run  # noqa: E402
import qc_visual  # noqa: E402
import huashu_motion_adapter as huashu  # noqa: E402
from contentops.media.motion_sample import check_motion_sample  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _extract(clip: Path, at: float, out: Path) -> bool:
    proc = hidden_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{at:.3f}", "-i", str(clip), "-frames:v", "1", str(out),
    ], timeout=120)
    return proc.returncode == 0 and out.is_file()


def build_preview(clip: Path, spec: Path | None, out_dir: Path) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    probe = huashu._ffprobe(clip)
    duration = float(probe.get("duration_s") or 0.0)
    sample = check_motion_sample(clip, probe=probe)
    times = [0.0, round(duration / 2, 3), max(0.0, round(duration - 0.1, 3))]
    frames = []
    for index, at in enumerate(times):
        frame = out_dir / f"frame-{index}.png"
        if _extract(clip, at, frame):
            frames.append(frame)
    sheet = out_dir / "contact-sheet.png"
    sheet_ok = qc_visual.build_contact_sheet(frames, sheet)

    spec_doc = _read_json(spec) if spec else {}
    scene = spec_doc.get("contentops_scene") or {}
    source = spec_doc.get("contentops_source") or {}
    render_log = clip.with_suffix(clip.suffix + ".log")

    card = {
        "schema": "contentops.animation-preview/v1",
        "clip": clip.name,
        "clip_sha256": _sha(clip) if clip.is_file() else None,
        "spec": spec.name if spec else None,
        "spec_sha256": _sha(spec) if spec and spec.is_file() else None,
        "template_parameters": {
            "animation_type": scene.get("animation_type"),
            "grammar": spec_doc.get("grammar"),
            "duration_s": spec_doc.get("duration"),
            "cue_count": len(spec_doc.get("cues") or []),
            "cues": spec_doc.get("cues") or [],
            "data": spec_doc.get("data") or None,
            "params": scene.get("animation_params") or spec_doc.get("animation") or None,
        },
        "frames": [{"timestamp_s": ts, "path": f.name}
                   for ts, f in zip(times, frames)],
        "contact_sheet": {"state": "READY" if sheet_ok else "UNAVAILABLE",
                          "path": sheet.name if sheet_ok else None},
        "render_log": {"state": "READY" if render_log.is_file() else "NOT_RECORDED",
                       "path": render_log.name if render_log.is_file() else None},
        "technical_qc": {"state": sample.get("state"), "reason": sample.get("reason"),
                         "probe": probe},
        "input_source": {
            "asset_id": source.get("asset_id"),
            "sha256": source.get("sha256"),
            "source_document_sha256": source.get("source_document_sha256"),
            "rights": "GENERATED_LOCAL_NO_COMMERCIAL_CLEARANCE",
        },
        "generated": True,
        "evidence_capable": False,
        "production_ready": False,
        "publish_authorized": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }
    (out_dir / "preview-card.json").write_text(
        json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return card


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clip", type=Path, help="rendered short MP4")
    parser.add_argument("--spec", type=Path, default=None, help="shot spec JSON")
    parser.add_argument("--out", type=Path, default=None, help="output directory")
    args = parser.parse_args(argv)
    out = args.out or args.clip.parent.parent / "receipts" / "preview" / args.clip.stem
    card = build_preview(args.clip.resolve(), args.spec.resolve() if args.spec else None, out)
    print(json.dumps(card, ensure_ascii=False, indent=2))
    return 0 if card["technical_qc"]["state"] == "TECHNICALLY_CHECKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
