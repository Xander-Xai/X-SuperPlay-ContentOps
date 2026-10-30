#!/usr/bin/env python3
"""One command that says which production pipeline this project uses, and why.

Why this exists
---------------
Two accounts share this repository and share the receipt/approval substrate, but
they do not make the same film:

- ``x-superplay-1024`` is ``EVIDENCE_LED``: captures are the evidence, and the
  account's composition is 70 % screen recording / 25 % vector / 5 % card.
- ``x-superplay-future-intelligence`` is ``EXPLANATORY``: manual recording is
  ``FORBIDDEN``, the picture budget is 70 % vector / 25 % code / 5 % metric, and
  an episode runs 90--120 s.

The DNA already declares all of that, including a ``skill_route`` table. What was
missing was a way to ask "so which scripts do I run for *this* project?" without
reading the runbook and remembering which of the two chains applies.
``skill_route.py`` routes a deliverable to a *skill*; this routes a *project* to
the ordered producer sequence its account's evidence mode implies.

It is read-only. It resolves the DNA, prints the sequence, and refuses when the
account cannot be resolved or its evidence mode has no declared pipeline. It does
not run anything, does not spend, and never records approval.

Usage
-----
    python scripts/account_route.py projects/easel-fi-audio-first
    python scripts/account_route.py projects/easel-1024-proof --json

Exit codes: 0 route resolved, 1 route refused, 2 usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

SCHEMA = "contentops.account-route/v1"

#: Which producers an evidence mode implies.
#:
#: The mode is the account's own word for how a film is made, so it -- not a
#: project-level flag -- decides the chain. ``{project}`` expands to the project
#: path as it was given on the command line.
PIPELINES: Dict[str, Tuple[Dict[str, str], ...]] = {
    "EVIDENCE_LED": (
        {
            "step": "cut-plan",
            "command": "python scripts/audio_first_plan.py {project}",
            "produces": "script/cut-plan.json + receipts/audio-first-plan.json",
            "why": "sizes the windows from measured narration and records whether the "
                   "cut lands inside the account's duration window; a plan authored by "
                   "hand is allowed, but it still has to pass cut_qc",
        },
        {
            "step": "capture-plan",
            "command": "python scripts/recording_plan.py {project}",
            "produces": "script/capture-plan.json",
            "why": "turns each beat into a capture contract, and refuses a beat the "
                   "account's recording policy forbids",
        },
        {
            "step": "capture",
            "command": "python scripts/capture_terminal_evidence.py "
                       "{project}/script/capture-plan.json --dry-run",
            "produces": "captured evidence",
            "why": "only through an approved plan; the plan is the allowlist, and a "
                   "capture is not proof until a person looks at it",
        },
        {
            "step": "build",
            "command": "python scripts/build_evidence_package.py {project}",
            "produces": "final/easel.mp4 + receipts/qc-report.json + review bundle",
            "why": "build -> cover -> cut_qc -> review bundle in one pass; exits "
                   "non-zero when QC fails",
        },
        {
            "step": "qc",
            "command": "python scripts/qc_video.py {project}",
            "produces": "receipts/qc-report-easel.json",
            "why": "technical QC; WARN is not a pass and never a human decision",
        },
    ),
    "EXPLANATORY": (
        {
            "step": "plan",
            "command": "python scripts/audio_first_plan.py {project}",
            "produces": "script/cut-plan.json + receipts/audio-first-plan.json",
            "why": "synthesise, measure, then size the windows; records whether the "
                   "measured narration lands inside the account's duration window",
        },
        {
            "step": "build",
            "command": "python scripts/build_evidence_package.py {project}",
            "produces": "final/easel.mp4 + receipts/qc-report.json + review bundle",
            "why": "same packager as the evidence path: cover, cut_qc, review bundle",
        },
        {
            "step": "qc",
            "command": "python scripts/qc_video.py {project}",
            "produces": "receipts/qc-report-easel.json",
            "why": "technical QC; WARN is not a pass and never a human decision",
        },
    ),
}

#: Legitimate variants of a pipeline, never the default.
ALTERNATIVES: Dict[str, Tuple[Dict[str, str], ...]] = {
    "EXPLANATORY": (
        {
            "step": "motion",
            "command": "python scripts/build_motion_film.py {project}",
            "why": "when the picture is one continuous motion film instead of "
                   "per-beat cards; it re-renders every clip and needs the external "
                   "engine, whose runtime must verify before it is trusted",
        },
    ),
}


class RouteBlocked(Exception):
    """A route that cannot be resolved. The code is the contract, not the prose."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def declared_account_slug(project: Path) -> Optional[str]:
    """Read ``account_slug`` from project.yaml.

    Mirrors ``cut_qc.account_dna_for`` on purpose: one rule for how a project
    names its account, so a project cannot resolve differently in two places.
    """
    path = Path(project) / "project.yaml"
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("account_slug:"):
            value = line.split(":", 1)[1].strip().strip("'\"")
            return value or None
    return None


def load_dna(slug: str) -> Dict[str, Any]:
    path = ROOT / "config" / "accounts" / f"{slug}.json"
    if not path.is_file():
        raise RouteBlocked("ACCOUNT_DNA_MISSING", str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def route_for(dna: Dict[str, Any]) -> Dict[str, Any]:
    """The pipeline a parsed DNA implies. Pure: no filesystem, no project path."""
    evidence = dna.get("evidence") or {}
    mode = str(evidence.get("mode") or "")
    if not mode:
        raise RouteBlocked("EVIDENCE_MODE_MISSING",
                           f"{dna.get('slug')!r} declares no evidence.mode")
    pipeline = PIPELINES.get(mode)
    if pipeline is None:
        raise RouteBlocked(
            "EVIDENCE_MODE_UNMAPPED",
            f"{dna.get('slug')!r} is {mode!r}, which has no declared pipeline; "
            f"declared modes: {sorted(PIPELINES)}")
    narrative = dna.get("narrative") or {}
    visual = dna.get("visual") or {}
    return {
        "account_slug": dna.get("slug"),
        "evidence_mode": mode,
        "required_evidence_class": evidence.get("required_evidence_class"),
        "manual_recording": evidence.get("manual_recording"),
        "duration_s": narrative.get("target_duration_s"),
        "composition": (visual.get("composition") or {}).get("segments"),
        "pipeline": [dict(step) for step in pipeline],
        "alternatives": [dict(step) for step in ALTERNATIVES.get(mode, ())],
        "skills": [
            {"step": entry.get("step"), "skill": entry.get("skill"),
             "script": entry.get("script")}
            for entry in dna.get("skill_route") or []
        ],
    }


def resolve(project: Path) -> Dict[str, Any]:
    slug = declared_account_slug(project)
    if not slug:
        raise RouteBlocked(
            "ACCOUNT_SLUG_MISSING",
            f"{Path(project) / 'project.yaml'} declares no account_slug, so no "
            "pipeline can be chosen; guessing one would be inventing the account")
    route = route_for(load_dna(slug))
    project_text = str(Path(project).as_posix())
    for group in ("pipeline", "alternatives"):
        for step in route[group]:
            step["command"] = step["command"].replace("{project}", project_text)
    route = {"schema": SCHEMA, "project": project_text, **route}
    route["warnings"] = _warnings(route, Path(project))
    return route


def _warnings(route: Dict[str, Any], project: Path) -> List[str]:
    """Facts a caller would otherwise discover after spending money."""
    warnings: List[str] = []
    span = route.get("duration_s")
    if span:
        warnings.append(
            f"the account owns a {float(span[0]):.0f}-{float(span[1]):.0f}s window; "
            "a cut outside it fails account_duration at cut_qc")
    if route.get("manual_recording") == "FORBIDDEN":
        warnings.append(
            "manual recording is FORBIDDEN for this account; a capture step is not "
            "part of its pipeline")
    for step in route["pipeline"]:
        executable = step["command"].split()
        if len(executable) > 1 and executable[0].startswith("python"):
            script = ROOT / executable[1]
            if not script.is_file():
                warnings.append(f"route names a missing script: {executable[1]}")
    # The producers need inputs this router does not create. Naming them here keeps
    # "the route is right" from being mistaken for "this project is ready".
    script_dir = project / "script"
    for step in route["pipeline"]:
        if "audio_first_plan.py" in step["command"] and not (script_dir / "lines.json").is_file():
            warnings.append(
                "the cut-plan step reads script/lines.json, which this project does "
                "not have; either add it or author script/cut-plan.json by hand (it "
                "still has to pass cut_qc)")
        if "recording_plan.py" in step["command"] and not (script_dir / "storyboard.json").is_file():
            warnings.append(
                "the capture-plan step reads script/storyboard.json, which this "
                "project does not have; a capture contract needs beats to attach to")
    return warnings


def _print_route(route: Dict[str, Any]) -> None:
    print(f"account      {route['account_slug']}")
    print(f"evidence     {route['evidence_mode']} "
          f"(required class {route['required_evidence_class']})")
    print(f"recording    {route['manual_recording']}")
    span = route.get("duration_s") or []
    if span:
        print(f"duration     {span[0]}-{span[1]} s")
    segments = route.get("composition") or []
    if segments:
        print("composition  " + ", ".join(
            f"{segment.get('role')} {segment.get('pct')}%" for segment in segments))
    print()
    print("pipeline (in order):")
    for index, step in enumerate(route["pipeline"], start=1):
        print(f"  {index}. {step['step']:<13} {step['command']}")
        print(f"     {step['why']}")
    if route["alternatives"]:
        print()
        print("alternatives (not the default):")
        for step in route["alternatives"]:
            print(f"  - {step['step']:<13} {step['command']}")
            print(f"     {step['why']}")
    if route["skills"]:
        print()
        print("creative owners (from the account DNA's skill_route):")
        for entry in route["skills"]:
            print(f"  {str(entry['step']):<22} {entry['skill']}")
    if route["warnings"]:
        print()
        print("warnings:")
        for warning in route["warnings"]:
            print(f"  - {warning}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a project's account DNA into its production pipeline.")
    parser.add_argument("project", help="project directory, e.g. projects/easel-fi-audio-first")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    try:
        route = resolve(Path(args.project))
    except RouteBlocked as blocked:
        if args.json:
            print(json.dumps({"status": "BLOCKED", "code": blocked.code,
                              "reason": blocked.detail}, ensure_ascii=False, indent=2))
        else:
            print(f"BLOCKED {blocked.code}: {blocked.detail}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(route, ensure_ascii=False, indent=2))
    else:
        _print_route(route)
    return 0


if __name__ == "__main__":
    sys.exit(main())
