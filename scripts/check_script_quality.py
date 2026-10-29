#!/usr/bin/env python3
"""Pre-render quality gate for a video project's script artefacts.

Why this exists
---------------
A batch of throwaway cuts were reviewed after the fact. Six defect classes
showed up that no gate could have caught, because every gate in this repo runs
*after* the render: ``qc_video.py`` inspects an MP4 that already exists. The
cheapest place to catch them is the script, before a single frame is rendered.

Every rule below is derived from a defect actually observed in a throwaway cut.
The rule is written so that the same authoring mistake fails here instead of
reaching a render.

SQ01 silent_visual_gap
    A shot ran 2.85 s with no narration under it: a stock 3-D render had been
    dropped in to fill the hole. A visual that exists only to cover silence is
    filler, and it reads as filler. Any shot longer than ``max_silent_s`` must
    be covered by a caption cue, or declare ``justification``.

SQ02 source_type_vocabulary
    Five shots declared ``source_type: vector_animation``, a value that is in
    neither ``REAL_SOURCE_TYPES`` nor ``GENERATED_SOURCE_TYPES`` in
    ``qc_video.py``. The ratio therefore computed to 0.0 and the film scored a
    false "no real evidence" warning. An unrecognised type is not neutral: it
    silently removes the shot from every downstream ratio.

SQ03 layout_undeclared
    Seven of twelve beats were the same "title + two empty cards" frame. Nothing
    recorded what layout a beat used, so repetition was invisible until someone
    watched the finished cut. Gated projects must name a layout per beat.

SQ04 layout_concentration
    Once layouts are named, one layout may not carry more than
    ``max_layout_share`` of the beats. Repetition is a ratio, not a rule of
    taste: a third of the film in one layout is allowed, two thirds is not.

SQ05 presenter_continuity
    The film opened on a presenter for 2.6 s and never returned to them. A
    presenter shown once and then dropped reads as two different films stitched
    together. Either the presenter carries ``min_presenter_share`` of the beats,
    or the project declares ``presenter_scope`` and says why.

SQ06 doc_drift
    The script table listed 5 beats, ``lines.json`` held 12, the storyboard
    summed to 20 s against a 38.9 s cut, and its ``subtitle`` pointer named a
    file that did not exist. Every one of those made the project look authored
    while the documents described a film nobody had made.

SQ07 cta_missing
    The cut ended on its last explanatory beat with no call to action.

Usage::

    python scripts/check_script_quality.py --project projects/<slug>
    python scripts/check_script_quality.py --all-gated
    python scripts/check_script_quality.py --project projects/<slug> --json

Exit 0 = pass, 1 = fail, 2 = project not gated (skipped).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]

# Mirrors qc_video.py's vocabulary. An unrecognised value drops a shot out of
# every ratio, so it is rejected here rather than neutral.
REAL_SOURCE_TYPES = {"real_screenshot", "real_recording", "diagram", "real_document"}
GENERATED_SOURCE_TYPES = {"generated", "ai_generated", "stock", "title_card"}
KNOWN_SOURCE_TYPES = REAL_SOURCE_TYPES | GENERATED_SOURCE_TYPES

MAX_SILENT_S = 1.0
MAX_LAYOUT_SHARE = 0.40
MIN_BEATS_FOR_CONCENTRATION = 4
MIN_PRESENTER_SHARE = 0.25
MIN_PRESENTER_BEATS = 2
DURATION_TOLERANCE_S = 2.0

SRT_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")
TABLE_ROW = re.compile(r"^\|\s*(?:\d+|\|)")


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _srt_span(path: Path) -> Optional[Tuple[float, float]]:
    """First cue start and last cue end, or None."""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    spans = []
    for match in SRT_TIME.finditer(text):
        groups = [int(g) for g in match.groups()]
        start = groups[0] * 3600 + groups[1] * 60 + groups[2] + groups[3] / 1000
        end = groups[4] * 3600 + groups[5] * 60 + groups[6] + groups[7] / 1000
        spans.append((start, end))
    if not spans:
        return None
    return min(s[0] for s in spans), max(e for _, e in spans)


def _script_rows(path: Path) -> Optional[int]:
    if not path.is_file():
        return None
    rows = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        if set(cells[0]) <= set("-: "):
            continue
        if cells[0] in ("#", "No.", "No"):
            continue
        rows += 1
    return rows


def _fail(rule: str, detail: str) -> Dict[str, str]:
    return {"rule": rule, "detail": detail}


def check_project(project: Path) -> Dict[str, Any]:
    """Every finding for one project. Empty ``failures`` means it may render."""
    project = project.resolve()
    failures: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    stats: Dict[str, Any] = {"project": project.name}

    lines = _load_json(project / "script" / "lines.json")
    storyboard = _load_json(project / "script" / "storyboard.json")
    master = project / "script" / "master.md"

    if storyboard is None and lines is None:
        return {
            "project": project.name, "gated": True, "evaluable": False,
            "failures": [], "warnings": [], "stats": stats,
        }

    beats = (lines or {}).get("beats") or []
    shots = (storyboard or {}).get("shots") or []

    # ---- SQ02 source_type vocabulary -------------------------------------
    unknown = [
        f"{index}:{shot.get('source_type')!r}"
        for index, shot in enumerate(shots)
        if shot.get("source_type") not in KNOWN_SOURCE_TYPES
    ]
    if unknown:
        failures.append(_fail(
            "SQ02 source_type_vocabulary",
            "shots declare a source_type qc_video cannot classify "
            f"({', '.join(unknown[:6])}); they are dropped from every ratio",
        ))

    provenance = [
        str(index) for index, shot in enumerate(shots)
        if not shot.get("source")
    ]
    if provenance:
        failures.append(_fail(
            "SQ06 doc_drift",
            f"shots declare no source (indices {', '.join(provenance[:6])})",
        ))

    # ---- SQ01 silent visual gap ------------------------------------------
    subtitle_rel = (storyboard or {}).get("subtitle")
    span: Optional[Tuple[float, float]] = None
    if beats and shots and len(beats) != len(shots):
        failures.append(_fail(
            "SQ06 doc_drift",
            f"lines.json has {len(beats)} beats but storyboard has {len(shots)} shots",
        ))

    if subtitle_rel:
        subtitle_path = (project / subtitle_rel)
        span = _srt_span(subtitle_path)
        if span is None:
            failures.append(_fail(
                "SQ06 doc_drift",
                f"storyboard.subtitle points at {subtitle_rel!r}, which is missing or empty",
            ))
        else:
            shot_total = sum(float(s.get("duration") or 0) for s in shots)
            stats["shot_total_s"] = round(shot_total, 2)
            stats["caption_end_s"] = round(span[1], 2)
            if abs(shot_total - span[1]) > DURATION_TOLERANCE_S:
                failures.append(_fail(
                    "SQ06 doc_drift",
                    f"storyboard sums to {shot_total:.1f}s but captions end at "
                    f"{span[1]:.1f}s (tolerance {DURATION_TOLERANCE_S}s)",
                ))
    elif shots:
        warnings.append(_fail(
            "SQ01 silent_visual_gap",
            "not evaluated: the storyboard names no subtitle file",
        ))

    rows = _script_rows(master)
    if rows is not None:
        stats["script_rows"] = rows
        if beats and rows != len(beats):
            failures.append(_fail(
                "SQ06 doc_drift",
                f"script/master.md lists {rows} beats but lines.json holds {len(beats)}",
            ))

    # A shot is "silent" when the part of it no caption cue covers exceeds the
    # budget. Measuring the uncovered remainder, not "has no coverage at all",
    # is what catches a shot whose narration stops two seconds early.
    if subtitle_rel and span is not None and shots:
        cursor = 0.0
        uncovered = []
        for index, shot in enumerate(shots):
            duration = float(shot.get("duration") or 0)
            claimed = _spoken_overlap(cursor, cursor + duration, project / subtitle_rel)
            if duration - claimed > MAX_SILENT_S and not shot.get("justification"):
                uncovered.append(f"{index}({duration - claimed:.1f}s)")
            cursor += duration
        if uncovered:
            failures.append(_fail(
                "SQ01 silent_visual_gap",
                f"shots {', '.join(uncovered[:6])} run over {MAX_SILENT_S}s with "
                "no narration and no justification",
            ))

    # ---- SQ03/SQ04 layout ------------------------------------------------
    if beats:
        missing_layout = [b.get("placement_id") or i for i, b in enumerate(beats) if not b.get("layout")]
        if missing_layout:
            failures.append(_fail(
                "SQ03 layout_undeclared",
                f"beats {', '.join(map(str, missing_layout[:6]))} name no layout; "
                "repetition cannot be measured without it",
            ))
        else:
            counts: Dict[str, int] = {}
            for beat in beats:
                counts[str(beat["layout"])] = counts.get(str(beat["layout"]), 0) + 1
            worst = max(counts.items(), key=lambda kv: kv[1])
            share = worst[1] / len(beats)
            stats["max_layout_share"] = round(share, 3)
            # With fewer than four beats one layout always owns most of them,
            # so the ratio says nothing. Only judge repetition on a cut long
            # enough to have varied.
            if len(beats) >= MIN_BEATS_FOR_CONCENTRATION and share > MAX_LAYOUT_SHARE:
                failures.append(_fail(
                    "SQ04 layout_concentration",
                    f"layout {worst[0]!r} carries {worst[1]}/{len(beats)} beats "
                    f"({share:.0%} > {MAX_LAYOUT_SHARE:.0%})",
                ))

    # ---- SQ05 presenter continuity ---------------------------------------
    presenter_beats = [i for i, b in enumerate(beats) if (b.get("role") == "presenter")]
    if presenter_beats:
        share = len(presenter_beats) / len(beats)
        stats["presenter_share"] = round(share, 3)
        short = len(presenter_beats) < MIN_PRESENTER_BEATS or share < MIN_PRESENTER_SHARE
        if short and not (lines or {}).get("presenter_scope"):
            failures.append(_fail(
                "SQ05 presenter_continuity",
                f"presenter appears in {len(presenter_beats)}/{len(beats)} beats "
                f"({share:.0%}); a presenter shown once reads as two films stitched "
                "together — declare presenter_scope or drop the opening",
            ))

    # ---- SQ07 CTA --------------------------------------------------------
    cta = (lines or {}).get("cta") or (lines or {}).get("call_to_action")
    if not cta and beats:
        last_text = str(beats[-1].get("text") or "")
        if not re.search(r"评论区|复现|CLI|跑一遍|交付", last_text):
            failures.append(_fail(
                "SQ07 cta_missing",
                "no CTA declared and the last beat carries no call to action",
            ))

    stats["beats"] = len(beats)
    stats["shots"] = len(shots)
    return {
        "project": project.name, "gated": True, "evaluable": True,
        "failures": failures, "warnings": warnings, "stats": stats,
    }


def _spoken_overlap(start: float, end: float, srt: Path) -> float:
    """Seconds of [start, end) covered by any caption cue."""
    text = srt.read_text(encoding="utf-8", errors="replace")
    covered = 0.0
    for match in SRT_TIME.finditer(text):
        g = [int(x) for x in match.groups()]
        cue_start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        cue_end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        covered += max(0.0, min(end, cue_end) - max(start, cue_start))
    return covered


def is_gated(project: Path) -> bool:
    path = project / "project.yaml"
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return re.search(r"^quality_gate:\s*enforced\s*$", text, re.M) is not None


def _gated_projects() -> List[Path]:
    return sorted(p for p in (ROOT / "projects").iterdir() if p.is_dir() and is_gated(p))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", help="project directory or slug")
    parser.add_argument("--all-gated", action="store_true",
                        help="every project that declares quality_gate: enforced")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.all_gated:
        targets = _gated_projects()
        if not targets:
            print("[script_quality] no project declares quality_gate: enforced; nothing to gate")
            return 0
    elif args.project:
        target = Path(args.project)
        if not target.is_dir():
            target = ROOT / "projects" / args.project
        if not target.is_dir():
            print(f"[script_quality] no such project: {args.project}", file=sys.stderr)
            return 2
        targets = [target]
    else:
        parser.error("pass --project or --all-gated")
        return 2

    reports = [check_project(t) for t in targets]
    failures = [(r["project"], f) for r in reports for f in r["failures"]]

    if args.json:
        print(json.dumps({
            "schema": "contentops.script-quality/v1",
            "overall": "FAIL" if failures else "PASS",
            "reports": reports,
        }, indent=2, ensure_ascii=False))
        return 1 if failures else 0

    for report in reports:
        status = "PASS" if not report["failures"] else "FAIL"
        note = "" if report["evaluable"] else " (no script artefacts yet)"
        print(f"[{report['project']}] {status}{note}")
        for finding in report["failures"]:
            print(f"  [FAIL] {finding['rule']}: {finding['detail']}")
        for finding in report["warnings"]:
            print(f"  [WARN] {finding['rule']}: {finding['detail']}")
        stats = report.get("stats") or {}
        if stats.get("beats"):
            print(f"  beats={stats['beats']} shots={stats['shots']} "
                  f"captions_end={stats.get('caption_end_s', '-')}s")

    if failures:
        print(f"\n{len(failures)} pre-render quality failure(s)")
        return 1
    print("\n[script_quality] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
