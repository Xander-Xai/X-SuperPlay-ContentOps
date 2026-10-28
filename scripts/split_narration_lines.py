#!/usr/bin/env python3
"""Split one recorded narration into per-line wavs and write voice-lines.json.

Why this exists
---------------
``build_code_animation_sample.py`` places one audio file per timeline line, so a
project whose narration is a single continuous recording cannot use the motion
pipeline without this step. The split is deterministic: the caption file already
records where each spoken line starts and ends, and the recording is exactly the
span of those cues.

A cue's timestamps are film time; the recording starts at the first cue, so the
in-file offset is the first cue's start. That is derived, never hardcoded — a
project whose narration begins at 0 s works unchanged.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from process_utils import hidden_run  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CUE = re.compile(r"\d+\n(\d\d:\d\d:\d\d,\d+) --> (\d\d:\d\d:\d\d,\d+)\n(.+?)(?=\n\n|\Z)", re.S)


def _seconds(stamp: str) -> float:
    h, m, s = stamp.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def split(project: Path, narration: Path, caption: Path) -> dict:
    offset = None
    rows = []
    outdir = project / "assets" / "voice" / "lines"
    outdir.mkdir(parents=True, exist_ok=True)

    for index, match in enumerate(CUE.finditer(caption.read_text(encoding="utf-8")), 1):
        start, end, text = _seconds(match.group(1)), _seconds(match.group(2)), match.group(3)
        if offset is None:
            offset = start
        out = outdir / f"line{index:02d}.wav"
        proc = hidden_run(
            ["ffmpeg", "-y", "-ss", f"{start - offset:.3f}", "-to", f"{end - offset:.3f}",
             "-i", str(narration), "-c:a", "pcm_s16le", str(out)],
            timeout=120,
        )
        if proc.returncode != 0 or not out.is_file():
            raise SystemExit(f"split failed at line {index}: {(proc.stderr or '')[-300:]}")
        rows.append({
            "line": index,
            "text": text.strip().replace("\n", ""),
            "path": f"project://{out.relative_to(project).as_posix()}",
            "duration_s": round(end - start, 3),
        })

    document = {
        "voice": f"split from {narration.name} at caption cue boundaries",
        "clone_alias": None,
        "clone_id_hash": None,
        "speed": 1.0,
        "lines": rows,
        "total_s": round(sum(row["duration_s"] for row in rows), 3),
    }
    (project / "receipts" / "voice-lines.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return document


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    parser.add_argument("--narration", help="default: storyboard.narration")
    parser.add_argument("--caption", help="default: the single script/*.srt")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()

    if args.narration:
        narration = Path(args.narration)
    else:
        storyboard = json.loads((project / "script" / "storyboard.json").read_text(encoding="utf-8"))
        narration = ROOT / str(storyboard.get("narration") or "")
    if not narration.is_file():
        raise SystemExit(f"narration not found: {narration}")

    if args.caption:
        caption = Path(args.caption)
    else:
        captions = sorted((project / "script").glob("*.srt"))
        if len(captions) != 1:
            raise SystemExit(f"expected one caption in script/, found {len(captions)}")
        caption = captions[0]

    doc = split(project, narration, caption)
    print(json.dumps({"lines": len(doc["lines"]), "total_s": doc["total_s"],
                      "receipt": "receipts/voice-lines.json"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
