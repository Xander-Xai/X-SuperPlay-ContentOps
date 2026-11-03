#!/usr/bin/env python3
"""Write the capture contract a recording-heavy cut needs before anyone records.

    python scripts/recording_plan.py projects/x-superplay-1024
    python scripts/recording_plan.py projects/x-superplay-1024 --check
    python scripts/recording_plan.py --beats beats.json --account x-superplay-1024

Reads the project's storyboard, reads the account DNA's `visual.manual_recording`
policy, and writes `script/capture-plan.json` beside the storyboard. That
location matters: the `storyboard` stage runs `capture-plan.json` as a sibling
validator, so a plan that contradicts the account policy stops the gate.

The plan is a brief, not a capture. It never runs a recorder and never claims
one happened. Exit 0 = plan written and valid, 1 = plan invalid, 2 = usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.workflow.capture_plan import (  # noqa: E402
    plan as build_plan,
    validate_capture_plan,
)

#: Storyboard source types that already represent a real observation.
OBSERVATION_SOURCES = ("real_screenshot", "recording", "real_source",
                       "real_document", "terminal_capture")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _policy(slug: str) -> str:
    dna_path = ROOT / "config" / "accounts" / f"{slug}.json"
    if not dna_path.is_file():
        raise SystemExit(f"account DNA not found: {dna_path}")
    dna = _read_json(dna_path)
    policy = ""
    for section in ("evidence", "visual"):
        block = dna.get(section)
        if isinstance(block, dict) and str(block.get("manual_recording", "")).strip():
            policy = str(block["manual_recording"]).strip()
            break
    if not policy:
        raise SystemExit(f"{dna_path.name} declares no manual_recording policy")
    return policy


def _account_slug(project: Path) -> str:
    project_yaml = project / "project.yaml"
    if not project_yaml.is_file():
        raise SystemExit(f"project manifest not found: {project_yaml}")
    for line in project_yaml.read_text(encoding="utf-8").splitlines():
        if line.startswith("account_slug:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"cannot determine account: {project_yaml} has no account_slug")


def beats_from_storyboard(storyboard: Dict[str, Any]) -> List[Dict[str, Any]]:
    shots = storyboard.get("shots")
    if not isinstance(shots, list) or not shots:
        raise SystemExit("storyboard has no shots")
    beats: List[Dict[str, Any]] = []
    cursor_ms = 0
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            raise SystemExit(f"storyboard shots[{index}] is not an object")
        try:
            duration_ms = int(round(float(shot.get("duration", 0) or 0) * 1000))
        except (TypeError, ValueError):
            raise SystemExit(f"storyboard shots[{index}] has a non-numeric duration")
        if duration_ms <= 0:
            raise SystemExit(f"storyboard shots[{index}] has no duration")
        source_type = str(shot.get("source_type", "")).strip()
        placement = str(shot.get("placement", "")).strip()
        beat = {
            # A placement may hold several views; the beat id must stay unique.
            "beat_id": f"{placement or 'shot'}#{index + 1:02d}",
            "placement": placement,
            "unit_id": str(shot.get("unit", "")).strip(),
            "claim_ids": list(shot.get("claim_ids") or []),
            "spoken_text": str(shot.get("narration", "")).strip(),
            "route": str(shot.get("route", "")).strip(),
            "evidence_need": ("direct_observation"
                              if source_type in OBSERVATION_SOURCES
                              else "explanation"),
            "start_ms": cursor_ms,
            "end_ms": cursor_ms + duration_ms,
            # A desktop capture may show an account name or a key in a terminal.
            # This is the fail-closed default; an operator may clear it on a
            # beat that provably shows nothing personal.
            "redaction_required": True,
        }
        cursor_ms += duration_ms
        beats.append(beat)
    return beats


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", help="project directory with script/storyboard.json")
    parser.add_argument("--beats", help="a beats.json instead of a storyboard")
    parser.add_argument("--account", default="", help="account slug override")
    parser.add_argument("--recording-policy", default="", help="ALLOWED_CROPPED or FORBIDDEN")
    parser.add_argument("--out", default="", help="output path; defaults beside the storyboard")
    parser.add_argument("--check", action="store_true", help="validate an existing plan only")
    args = parser.parse_args(argv)

    if not args.project and not args.beats:
        parser.error("give a project directory or --beats")

    project = Path(args.project).resolve() if args.project else None
    out = Path(args.out) if args.out else None

    if args.check:
        if out is None:
            if project is None:
                parser.error("--check needs a project directory or --out")
            out = project / "script" / "capture-plan.json"
        document = _read_json(out)
        errors = validate_capture_plan(document)
        for message in errors:
            print(f"  - {message}")
        print(f"[{'FAIL' if errors else 'PASS'}] {out}")
        return 1 if errors else 0

    if args.beats:
        source = _read_json(Path(args.beats).resolve())
        raw_beats = source.get("beats") if isinstance(source, dict) else source
        if not isinstance(raw_beats, list):
            raise SystemExit("beats input must be a list or an object with 'beats'")
        account = args.account or (str(source.get("account", "")) if isinstance(source, dict) else "")
        policy = args.recording_policy or (str(source.get("recording_policy", ""))
                                          if isinstance(source, dict) else "")
        if not account or not policy:
            raise SystemExit("--beats input needs account and recording_policy, or the flags")
        out = out or Path("capture-plan.json")
    else:
        assert project is not None
        storyboard_path = project / "script" / "storyboard.json"
        if not storyboard_path.is_file():
            raise SystemExit(f"storyboard not found: {storyboard_path}")
        storyboard = _read_json(storyboard_path)
        account = args.account or _account_slug(project)
        policy = args.recording_policy or _policy(account)
        raw_beats = beats_from_storyboard(storyboard)
        out = out or project / "script" / "capture-plan.json"

    document = build_plan(raw_beats, account=account, recording_policy=policy)
    errors = validate_capture_plan(document)
    if errors:
        for message in errors:
            print(f"  - {message}")
        print("[FAIL] capture plan")
        return 1
    assert out is not None
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    modes: Dict[str, int] = {}
    for beat in document["beats"]:
        mode = beat["capture"]["mode"]
        modes[mode] = modes.get(mode, 0) + 1
    print(f"[PASS] wrote {out}")
    print(f"       {len(document['beats'])} beats, policy {policy}: "
          + ", ".join(f"{key}={value}" for key, value in sorted(modes.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
