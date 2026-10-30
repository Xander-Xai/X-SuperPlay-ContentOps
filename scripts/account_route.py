#!/usr/bin/env python3
"""One command that says which production pipeline this project uses, and why.

Why this exists
---------------
Three accounts share this repository and share the receipt/approval substrate, but
they do not make the same deliverable:

- ``x-superplay-1024`` is ``EVIDENCE_LED``: captures are the evidence, and the
  account's composition is 70 % screen recording / 25 % vector / 5 % card.
- ``x-superplay-future-intelligence`` is ``EXPLANATORY``: manual recording is
  ``FORBIDDEN``, the picture budget is 70 % vector / 25 % code / 5 % metric, and
  an episode runs 90--120 s.
- ``x-superplay-english`` is a **text** account. It has no film and therefore no
  evidence mode, so its DNA declares ``pipeline: X_EDITORIAL`` and that wins.

The DNA already declares all of that, including a ``skill_route`` table. What was
missing was a way to ask "so which scripts do I run for *this* project?" without
reading the runbook and remembering which of the chains applies.
``skill_route.py`` routes a deliverable to a *skill*; this routes a *project* to
the ordered producer sequence its account implies.

It is read-only. It resolves the DNA, prints the sequence, and refuses when the
account cannot be resolved or its pipeline has no declared chain. It does not run
anything, does not spend, and never records approval.

Usage
-----
    python scripts/account_route.py projects/easel-fi-audio-first
    python scripts/account_route.py projects/easel-1024-proof --json
    python scripts/account_route.py projects/x-growth-en

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

#: Which producers a DNA implies.
#:
#: A key is either an evidence mode (the video account's own word for how a film
#: is made) or a declared ``pipeline`` name (what a text account has instead, since
#: it has no film to describe). A declared ``pipeline`` always wins, because it is
#: the more specific statement. ``{project}`` expands to the project path as it was
#: given on the command line.
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
    # The X track. Nothing here renders a film, and the last two steps are a
    # person's: no command below can publish anything.
    "X_EDITORIAL": (
        {
            "step": "research",
            "command": "python scripts/x_post.py --new {project} --id <content-id> "
                       "--topic \"<topic>\"",
            "produces": "posts/<content-id>.json (status draft, image_status missing) "
                        "+ one seeded row in templates/posts.csv",
            "why": "the draft record comes before the copy: it is what carries the "
                   "audience job, the proof grade, the artifact ref and the one "
                   "experiment variable that the editorial gate reads",
        },
        {
            "step": "editorial",
            "command": "python scripts/x_post.py --check {project} --id <content-id>",
            "produces": "a named refusal or a PASS receipt",
            "why": "three theses, the red-team pass, six scored dimensions and the "
                   "280-weighted-character budget; a post with no image is refused "
                   "at IMAGE_MISSING, not waved through",
        },
        {
            "step": "visual",
            "command": "python scripts/skill_route.py --match \"X post 1600x900 editorial card\"",
            "produces": "the owning skill and its renderer",
            "why": "routes the card to card-quote; the image is rendered from HTML so "
                   "labels and numbers are exact, and an SVG alone is not uploadable",
        },
        {
            "step": "package",
            "command": "python scripts/x_post.py --package {project} --id <content-id>",
            "produces": "receipts/x-package-<content-id>.json with "
                        "status=AWAITING_MANUAL_PUBLISH",
            "why": "assembles the copy, the image path, the ALT text and the review "
                   "record so a person can paste and attach them; it cannot publish",
        },
        {
            "step": "publish",
            "command": "python scripts/x_post.py --mark-published {project} "
                       "--id <content-id> --url <status-url>",
            "produces": "status=published in the post record and the CSV row",
            "why": "manual by contract: this step only records a URL a person "
                   "actually has, and refuses anything that is not a real status link",
        },
        {
            "step": "measure",
            "command": "python vendor/x-growth-os/scripts/x_growth_report.py "
                       "--root {project}",
            "produces": "the read-only metric report",
            "why": "the vendored analytics script runs unmodified against this "
                   "project; blank stays blank because it is not zero",
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


#: The vendored WeChat workflow. It has no ContentOps account DNA, so its chain is
#: read from the workflow itself rather than derived from `evidence.mode`.
WECHAT_HOME = ROOT / "vendor" / "gzh-thinktank" / "gzh_未来智能"

WECHAT_STEPS: Tuple[Dict[str, str], ...] = (
    {
        "step": "workspace",
        "command": "python {home}/scripts/route_content.py --interactive",
        "why": "writes a confirmed route; the workflow refuses a hand-made article "
               "directory and allocates the workspace itself",
    },
    {
        "step": "init",
        "command": "python {home}/scripts/matrix_init.py --route <route> --title \"<title>\"",
        "why": "allocates THK-YYYYMMDD-NNN-<slug> under the artifact root and seeds "
               "the stage artifacts, all of them deliberately failing",
    },
    {
        "step": "gate",
        "command": "python {home}/scripts/workflow_gate.py --article <dir> --stage <stage> --advance",
        "why": "ten ordered stages; each refuses until its own artifacts and evidence "
               "exist, and publishing stops at a WeChat draft",
    },
    {
        "step": "audit",
        "command": "python {home}/scripts/workspace_audit.py --check",
        "why": "proves the artifact root fits the workspace contract before the "
               "next article is started",
    },
)


def is_wechat_workspace(project: Path) -> bool:
    """A 公众号 artifact root is recognised by its registry, not by its name."""
    return (Path(project) / "registry" / "workspace-index.json").is_file()


def wechat_route(project: Path) -> Dict[str, Any]:
    project_text = Path(project).as_posix()
    steps = []
    home = WECHAT_HOME.relative_to(ROOT).as_posix() if WECHAT_HOME.is_dir() \
        else WECHAT_HOME.as_posix()
    for step in WECHAT_STEPS:
        steps.append({**step, "command": step["command"].replace("{home}", home)})
    warnings = [
        "this is the 公众号 track: its workspace is the artifact root, not a "
        "ContentOps project",
        "set GZH_ARTIFACT_ROOT to the artifact root before running anything",
        "the environment stage needs a local .aws-article/config.yaml; it was never "
        "versioned, and credentials must stay outside the repository",
    ]
    if not WECHAT_HOME.is_dir():
        warnings.append(f"the vendored workflow is missing: {WECHAT_HOME}")
    return {
        "schema": SCHEMA,
        "project": project_text,
        "platform": "wechat_article",
        "account_slug": "x-superplay-future-intelligence",
        "evidence_mode": "WECHAT_ARTICLE",
        "required_evidence_class": "DOCUMENTED",
        "manual_recording": "n/a",
        "duration_s": None,
        "composition": None,
        "pipeline": steps,
        "alternatives": [],
        "skills": [],
        "warnings": warnings,
    }


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
    """The pipeline a parsed DNA implies. Pure: no filesystem, no project path.

    A declared ``pipeline`` wins over an evidence mode. A text account has no
    film, so it has no evidence mode to declare, and borrowing a video mode to
    name its chain would make the vocabulary mean two things at once.
    """
    evidence = dna.get("evidence") or {}
    mode = str(evidence.get("mode") or "")
    declared = str(dna.get("pipeline") or "")
    name, source = (declared, "pipeline") if declared else (mode, "evidence_mode")
    if not name:
        raise RouteBlocked(
            "EVIDENCE_MODE_MISSING",
            f"{dna.get('slug')!r} declares neither a pipeline nor an evidence.mode")
    pipeline = PIPELINES.get(name)
    if pipeline is None:
        code = "PIPELINE_UNMAPPED" if source == "pipeline" else "EVIDENCE_MODE_UNMAPPED"
        raise RouteBlocked(
            code,
            f"{dna.get('slug')!r} is {name!r}, which has no declared pipeline; "
            f"declared pipelines: {sorted(PIPELINES)}")
    narrative = dna.get("narrative") or {}
    visual = dna.get("visual") or {}
    return {
        "account_slug": dna.get("slug"),
        "pipeline_name": name,
        "pipeline_source": source,
        "evidence_mode": mode or None,
        "required_evidence_class": evidence.get("required_evidence_class"),
        "manual_recording": evidence.get("manual_recording"),
        "publication_mode": (dna.get("publication") or {}).get("mode"),
        "duration_s": narrative.get("target_duration_s"),
        "composition": (visual.get("composition") or {}).get("segments"),
        "pipeline": [dict(step) for step in pipeline],
        "alternatives": [dict(step) for step in ALTERNATIVES.get(name, ())],
        "skills": [
            {"step": entry.get("step"), "skill": entry.get("skill"),
             "script": entry.get("script")}
            for entry in dna.get("skill_route") or []
        ],
    }


def resolve(project: Path) -> Dict[str, Any]:
    if is_wechat_workspace(project):
        return wechat_route(project)
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
    if route.get("publication_mode") == "MANUAL_ONLY":
        warnings.append(
            "publication is MANUAL_ONLY: the package stops at "
            "AWAITING_MANUAL_PUBLISH, and no step here can publish it — a person "
            "posts the copy with the image, then records the real status URL")
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
    if route.get("pipeline_source") == "pipeline":
        print(f"pipeline     {route['pipeline_name']} (declared by the DNA; "
              f"evidence class {route['required_evidence_class']})")
    else:
        print(f"evidence     {route['evidence_mode']} "
              f"(required class {route['required_evidence_class']})")
    if route.get("manual_recording"):
        print(f"recording    {route['manual_recording']}")
    if route.get("publication_mode"):
        print(f"publication  {route['publication_mode']}")
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
