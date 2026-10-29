#!/usr/bin/env python3
"""Deterministic subtitle checks for vertical-video delivery.

The checker is intentionally offline and does not rewrite the subtitle file.
It catches timing, overlap, empty-cue, line-length and optional script-drift
problems before a platform package is approved.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import Any


TIMING = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})\s+-->\s+"
    r"(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{3})"
)


def timestamp(value: str) -> float:
    hours, minutes, rest = value.replace(",", ".").split(":")
    seconds = float(rest)
    return int(hours) * 3600 + int(minutes) * 60 + seconds


def parse_srt(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()) if text.strip() else []
    cues: list[dict[str, Any]] = []
    for block_number, block in enumerate(blocks, 1):
        lines = block.splitlines()
        if len(lines) < 3:
            cues.append({"block": block_number, "error": "cue must contain an index, timing line and text"})
            continue
        timing_line = next((line for line in lines if "-->" in line), "")
        match = TIMING.match(timing_line.strip())
        if not match:
            cues.append({"block": block_number, "error": "invalid timing line"})
            continue
        cues.append(
            {
                "block": block_number,
                "start": timestamp(match.group("start")),
                "end": timestamp(match.group("end")),
                "text": " ".join(line.strip() for line in lines[lines.index(timing_line) + 1 :] if line.strip()),
            }
        )
    return cues


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def run(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().resolve()
    cues = parse_srt(input_path)
    errors: list[str] = []
    warnings: list[str] = []
    previous_end = -1.0
    for index, cue in enumerate(cues, 1):
        if cue.get("error"):
            errors.append(f"cue {index}: {cue['error']}")
            continue
        start = float(cue["start"])
        end = float(cue["end"])
        text = str(cue.get("text", ""))
        if start >= end:
            errors.append(f"cue {index}: start must be before end")
        if start < previous_end:
            errors.append(f"cue {index}: overlaps the previous cue")
        if not text:
            errors.append(f"cue {index}: text is empty")
        if len(text) > args.max_chars:
            warnings.append(f"cue {index}: {len(text)} characters exceeds {args.max_chars}")
        if end - start < args.min_duration - 1e-6:
            warnings.append(f"cue {index}: duration {end - start:.3f}s is below {args.min_duration:.3f}s")
        previous_end = max(previous_end, end)

    script_match: float | None = None
    script_arg = args.script
    if not script_arg:
        candidate_1 = input_path.parent / "01_script" / "final.txt"
        candidate_2 = input_path.parent.parent / "01_script" / "final.txt"
        if candidate_1.is_file():
            script_arg = str(candidate_1)
        elif candidate_2.is_file():
            script_arg = str(candidate_2)

    script_source: str | None = None
    script_text: str | None = None
    if getattr(args, "script_text", ""):
        script_source = "inline:approved-script"
        script_text = args.script_text
    elif script_arg:
        script_path = Path(script_arg).expanduser().resolve()
        if not script_path.is_file():
            errors.append(f"approved script does not exist: {script_path}")
        else:
            script_source = str(script_path)
            script_text = script_path.read_text(encoding="utf-8")
    if script_text is not None:
        subtitle_text = "".join(str(cue.get("text", "")) for cue in cues if not cue.get("error"))
        script_match = difflib.SequenceMatcher(None, normalize(script_text), normalize(subtitle_text)).ratio()
        if script_match < args.min_script_match:
            warnings.append(f"subtitle/script similarity {script_match:.3f} is below {args.min_script_match:.3f}")
    elif args.require_script or args.strict:
        errors.append("approved script is required for strict subtitle QC; pass --script or place 01_script/final.txt beside the SRT")

    valid_cues = [cue for cue in cues if not cue.get("error")]
    if getattr(args, "require_segmentation", False) and len(valid_cues) <= 1 and len(normalize("".join(str(cue.get("text", "")) for cue in valid_cues))) > args.max_chars:
        errors.append("long narration must be split into multiple readable subtitle cues")

    report = {
        "schema_version": 1,
        "content_id": args.content_id,
        "input": str(input_path),
        "cue_count": len(cues),
        "status": "passed" if not errors and (not args.strict or not warnings) else "blocked",
        "passed": not errors and (not args.strict or not warnings),
        "errors": errors,
        "warnings": warnings,
        "script_match": script_match,
        "script_source": script_source,
        "limits": {
            "max_chars": args.max_chars,
            "min_duration": args.min_duration,
            "min_script_match": args.min_script_match,
            "require_segmentation": getattr(args, "require_segmentation", False),
        },
    }
    output = Path(args.output).expanduser().resolve() if args.output else input_path.with_suffix(".qc.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check SRT timing and readability without rewriting it.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--content-id", default="", help="当前内容包 ID；严格门禁会校验血缘一致性")
    parser.add_argument("--output")
    parser.add_argument("--script")
    parser.add_argument("--script-text", help="直接提供已批准口播原文，避免为 QC 临时写文件")
    parser.add_argument("--max-chars", type=int, default=24)
    parser.add_argument("--min-duration", type=float, default=0.6)
    parser.add_argument("--min-script-match", type=float, default=0.65)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--require-script", action="store_true", help="Fail when no approved script is available for comparison")
    parser.add_argument("--require-segmentation", action="store_true", help="Fail when a long narration is emitted as one cue")
    parser.set_defaults(handler=run)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
