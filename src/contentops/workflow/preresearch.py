#!/usr/bin/env python3
"""Pre-copy research gate: the mandatory step before any copy is authored.

A content project may not reach ``make_content.py`` preflight or a copy review
approval until five things exist and a named human has signed them:

    00_preresearch/content-intent.json  which ContentIntent this research serves
    00_preresearch/project-reading.md   what was read in this repository
    00_preresearch/outline.md           the outline / handbook for the piece
    00_preresearch/evidence-list.json   authoritative, traceable sources
    00_preresearch/boundary.md          honest scope and non-production claims
    receipts/precopy-research.json      fingerprint-bound human approval

``content-intent.json`` is what ties the two entrances together. The router
(``contentops.routing``) decides *how* a topic arrived -- ``USER_TOPIC`` for a
topic the user named, ``HOTSPOT_DISCOVERY`` for one selected out of candidates
-- and both modes emit the same ``contentops.content-intent/v1`` document. The
gate consumes that document rather than a free-text topic, so an approval can
never be reused across two different intents: the intent file is one of the
fingerprinted artifacts.

The gate is fail-closed and has no force switch. Changing any of the five
artifacts after approval makes the approval STALE. This module reads local
files only; it never calls a provider, starts a host or publishes anything.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "contentops.precopy-research/v1"
CHECK_SCHEMA = "contentops.precopy-research-check/v1"
INTENT_SCHEMA = "contentops.content-intent/v1"

RESEARCH_DIR = Path("00_preresearch")
RECEIPT = Path("receipts") / "precopy-research.json"

INTENT_FILE = RESEARCH_DIR / "content-intent.json"
READING_FILE = RESEARCH_DIR / "project-reading.md"
OUTLINE_FILE = RESEARCH_DIR / "outline.md"
EVIDENCE_FILE = RESEARCH_DIR / "evidence-list.json"
BOUNDARY_FILE = RESEARCH_DIR / "boundary.md"

#: Where the router leaves the brief package. Mirrored from
#: ``contentops.routing.brief`` so this gate stays import-light.
BRIEF_FILE = Path("00_brief") / "brief.json"

#: The router brief dialect. ``00_brief/brief.json`` is also used by
#: ``contentops.graphic-brief/v1``, which carries no intent -- only compare when
#: the file actually is a router package.
BRIEF_SCHEMA = "contentops.content-brief/v1"

ARTIFACTS: Tuple[Tuple[str, Path], ...] = (
    ("intent_source", INTENT_FILE),
    ("project_reading", READING_FILE),
    ("outline", OUTLINE_FILE),
    ("evidence", EVIDENCE_FILE),
    ("boundary", BOUNDARY_FILE),
)

#: The two entrances the router supports. Mirrored here so this gate does not
#: import the router's dependency tree; ``contentops.routing.models`` is the
#: authority for the values.
ROUTE_MODES = ("HOTSPOT_DISCOVERY", "USER_TOPIC")
TOPIC_ORIGINS = ("USER_INPUT", "HOTSPOT_SELECTION")

#: ``HOTSPOT_DISCOVERY`` must prove a candidate was actually chosen; a directly
#: named topic has no candidate to point at.
REQUIRED_INTENT_CONTEXT = {
    "USER_TOPIC": ("topic_origin",),
    "HOTSPOT_DISCOVERY": ("topic_origin", "candidate_id", "search_plan_id"),
}
TOPIC_ORIGIN_FOR_MODE = {
    "USER_TOPIC": "USER_INPUT",
    "HOTSPOT_DISCOVERY": "HOTSPOT_SELECTION",
}

EVIDENCE_KINDS = ("primary", "official", "interpretation")
URL_RE = re.compile(r"^(?:https?://|repo://)\S+$", re.IGNORECASE)
REPO_PATH_RE = re.compile(r"\b(?:scripts|src|docs|config|runtime|tests|projects)/[\w./-]+")

MIN_LENGTH = {
    "project_reading": 200,
    "outline": 100,
    "boundary": 80,
}
MIN_EVIDENCE_ITEMS = 3
MIN_REPO_PATHS = 3


class PreresearchError(RuntimeError):
    """A blocked pre-copy research gate; nothing downstream may proceed."""

    def __init__(self, code: str, detail: str, report: Optional[Dict[str, Any]] = None):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.report = report


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_bytes(project: Path, relative: Path) -> Optional[bytes]:
    path = project / relative
    return path.read_bytes() if path.is_file() else None


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def fingerprint(project: Path) -> Optional[str]:
    """SHA-256 over the five labeled artifacts; None until all five exist."""
    digest = hashlib.sha256()
    for label, relative in ARTIFACTS:
        raw = _read_bytes(project, relative)
        if raw is None:
            return None
        digest.update(label.encode("utf-8") + b"\0")
        digest.update(raw)
        digest.update(b"\0")
    return digest.hexdigest()


def _validate_intent(project: Path) -> List[str]:
    """The intent file is the only artifact that says *whose* research this is."""
    problems: List[str] = []
    intent = _read_json(project / INTENT_FILE)
    if intent is None:
        return ["content-intent.json is missing or is not a JSON object"]

    if intent.get("schema") != INTENT_SCHEMA:
        problems.append(f"content-intent.json schema must be {INTENT_SCHEMA}")

    route_mode = str(intent.get("route_mode") or "")
    if route_mode not in ROUTE_MODES:
        problems.append(f"content-intent.json route_mode must be one of {ROUTE_MODES}")
        return problems

    if not str(intent.get("topic") or "").strip():
        problems.append("content-intent.json needs a non-empty topic")
    for key in ("account_id", "account_profile_version"):
        if not str(intent.get(key) or "").strip():
            problems.append(f"content-intent.json needs a non-empty {key}")

    context = intent.get("route_context")
    context = context if isinstance(context, dict) else {}
    for key in REQUIRED_INTENT_CONTEXT[route_mode]:
        if not str(context.get(key) or "").strip():
            problems.append(f"{route_mode} content-intent.json needs route_context.{key}")

    mounted = str(context.get("mode") or "")
    if mounted and mounted != route_mode:
        problems.append(
            f"route_context.mode {mounted} contradicts route_mode {route_mode}")

    origin = str(context.get("topic_origin") or "")
    if origin and origin not in TOPIC_ORIGINS:
        problems.append(f"route_context.topic_origin must be one of {TOPIC_ORIGINS}")
    elif origin and origin != TOPIC_ORIGIN_FOR_MODE[route_mode]:
        problems.append(
            f"{route_mode} must use topic_origin {TOPIC_ORIGIN_FOR_MODE[route_mode]}, "
            f"not {origin}"
        )

    problems.extend(_validate_intent_against_brief(project, intent))
    return problems


def _validate_intent_against_brief(project: Path, intent: Dict[str, Any]) -> List[str]:
    """When the router has already written a brief, the two must agree.

    This is what stops a research approval from being carried over to a
    different topic: re-routing rewrites ``00_brief/brief.json``, the copy in
    ``00_preresearch`` no longer matches, and the gate turns red on its own.

    ``00_brief/brief.json`` is shared with the graphic line's
    ``contentops.graphic-brief/v1``, which has no intent to compare against, so
    the check applies only to a real router package.
    """
    brief = _read_json(project / BRIEF_FILE)
    if brief is None or brief.get("schema") != BRIEF_SCHEMA:
        return []
    recorded = brief.get("intent")
    if not isinstance(recorded, dict):
        return [f"{BRIEF_FILE.as_posix()} is a router brief but carries no intent"]
    if _canonical(recorded) == _canonical(intent):
        return []
    return [
        "content-intent.json differs from the router's intent in "
        f"{BRIEF_FILE.as_posix()}; this research was done for a different topic -- "
        "re-route the research or copy the intent again"
    ]


def _canonical(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _validate(project: Path) -> List[str]:
    """Content checks. These run before and after approval (drift -> STALE)."""
    problems: List[str] = []
    problems.extend(_validate_intent(project))

    reading = _read_bytes(project, READING_FILE)
    if reading is None or len(reading.decode("utf-8", "replace")) < MIN_LENGTH["project_reading"]:
        problems.append("project-reading.md is missing or too short to be a real read-through")
    else:
        text = reading.decode("utf-8", "replace")
        paths = set(REPO_PATH_RE.findall(text))
        if not text.lstrip().startswith("#") and "##" not in text:
            problems.append("project-reading.md needs section headings")
        if len(paths) < MIN_REPO_PATHS:
            problems.append(
                f"project-reading.md cites {len(paths)} repository path(s); need at least "
                f"{MIN_REPO_PATHS} distinct paths under scripts/ src/ docs/ ..."
            )

    outline = _read_bytes(project, OUTLINE_FILE)
    if outline is None or len(outline.decode("utf-8", "replace")) < MIN_LENGTH["outline"]:
        problems.append("outline.md is missing or too short to be an outline")
    else:
        text = outline.decode("utf-8", "replace")
        bullets = sum(1 for line in text.splitlines()
                      if line.lstrip().startswith(("- ", "* ", "## ")))
        if bullets < 3:
            problems.append("outline.md needs at least 3 outline items or headings")

    evidence = _read_json(project / EVIDENCE_FILE)
    if evidence is None:
        problems.append("evidence-list.json is missing or is not a JSON object")
    else:
        items = evidence.get("items")
        if not isinstance(items, list) or len(items) < MIN_EVIDENCE_ITEMS:
            problems.append(
                f"evidence-list.json needs at least {MIN_EVIDENCE_ITEMS} items"
            )
        else:
            for index, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    problems.append(f"evidence item {index} is not an object")
                    continue
                url = str(item.get("url") or "")
                if not URL_RE.match(url):
                    problems.append(f"evidence item {index} has no followable url")
                if item.get("kind") not in EVIDENCE_KINDS:
                    problems.append(f"evidence item {index} needs a kind in {EVIDENCE_KINDS}")
                if not str(item.get("title") or "").strip():
                    problems.append(f"evidence item {index} needs a title")
            kinds = {item.get("kind") for item in items if isinstance(item, dict)}
            if not kinds.intersection({"primary", "official"}):
                problems.append("at least one source must be primary or official")

    boundary = _read_bytes(project, BOUNDARY_FILE)
    if boundary is None:
        problems.append("boundary.md is missing")
    else:
        text = boundary.decode("utf-8", "replace")
        if len(text) < MIN_LENGTH["boundary"]:
            problems.append("boundary.md is too short to be a boundary statement")
        for required in ("production_ready: false", "publish_authorized: false"):
            if required not in text:
                problems.append(f"boundary.md must state `{required}`")

    return problems


def check(project: Path) -> Dict[str, Any]:
    """Return a fail-closed report. Never raises for an ordinary missing artifact."""
    project = Path(project).resolve()
    missing = [relative.as_posix() for _, relative in ARTIFACTS
               if not (project / relative).is_file()]
    problems = _validate(project)
    sha = fingerprint(project)
    receipt = _read_json(project / RECEIPT)

    if len(missing) == len(ARTIFACTS):
        state = "NOT_STARTED"
        detail = "missing: " + ", ".join(missing)
    elif problems:
        state = "INCOMPLETE"
        detail = "; ".join(problems[:5])
    elif receipt is None:
        state = "AWAITING_APPROVAL"
        detail = "artifacts complete; a named human approval is required"
    elif receipt.get("status") != "APPROVED":
        state = "INVALID_RECEIPT"
        detail = "approval receipt is not APPROVED"
    elif not receipt.get("reviewer") or not receipt.get("opinion"):
        state = "INVALID_RECEIPT"
        detail = "approval receipt needs a named reviewer and a written opinion"
    elif receipt.get("artifacts_sha256") != sha:
        state = "STALE"
        detail = "research artifacts changed after approval; re-check and re-approve"
    else:
        state = "APPROVED"
        detail = "pre-copy research approved and fingerprint current"

    ok = state == "APPROVED"
    intent_problem = any("content-intent.json" in problem for problem in problems)
    remedy = ""
    if not ok:
        if state == "NOT_STARTED":
            remedy = "python scripts/preresearch.py init --project <slug>"
        elif state == "INCOMPLETE":
            remedy = ("python scripts/preresearch.py intent --project <slug>   # copy the "
                      "router's intent, then fill the rest"
                      if intent_problem else
                      "python scripts/preresearch.py init --project <slug>")
        else:
            remedy = ("python scripts/preresearch.py check --project <slug> && "
                      "python scripts/preresearch.py approve --project <slug> "
                      "--reviewer <name> --opinion <text> --confirm")

    intent = _read_json(project / INTENT_FILE) or {}
    route_context = intent.get("route_context")
    route_context = route_context if isinstance(route_context, dict) else {}
    brief_intent = (_read_json(project / BRIEF_FILE) or {}).get("intent")
    return {
        "schema": CHECK_SCHEMA,
        "ok": ok,
        "state": state,
        "detail": detail,
        "remedy": remedy,
        "project": project.name,
        "checked_at": _now(),
        "missing": missing,
        "problems": problems,
        "artifacts_sha256": sha,
        "route_mode": intent.get("route_mode"),
        "topic": intent.get("topic"),
        "topic_origin": route_context.get("topic_origin"),
        "candidate_id": route_context.get("candidate_id"),
        "intent_bound_to_brief": (
            _canonical(brief_intent) == _canonical(intent)
            if isinstance(brief_intent, dict) else None),
        "approved_by": receipt.get("reviewer") if isinstance(receipt, dict) else None,
        "approved_at": receipt.get("approved_at") if isinstance(receipt, dict) else None,
        "production_ready": False,
        "publish_authorized": False,
        "note": "Approved research is not copy approval, production approval or publication.",
    }


# ``status`` is a readable alias for callers that expect a gate-like API.
status = check


def approve(project: Path, *, reviewer: str, opinion: str,
            reviewed_at: Optional[str] = None) -> Dict[str, Any]:
    """Write a fingerprint-bound approval. Requires a green artifact check."""
    project = Path(project).resolve()
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise PreresearchError("REVIEWER_REQUIRED", "a named reviewer is required")
    if not isinstance(opinion, str) or not opinion.strip():
        raise PreresearchError("OPINION_REQUIRED", "a written rationale is required")

    report = check(project)
    if report["missing"]:
        raise PreresearchError("ARTIFACTS_MISSING", report["detail"], report)
    if report["problems"]:
        raise PreresearchError("CHECK_REQUIRED", report["detail"], report)

    record = {
        "schema": SCHEMA,
        "status": "APPROVED",
        "reviewer": reviewer.strip(),
        "opinion": opinion.strip(),
        "approved_at": reviewed_at or _now(),
        "artifacts_sha256": fingerprint(project),
        "production_ready": False,
        "publish_authorized": False,
        "note": "Human sign-off on the research phase only; copy review is separate.",
    }
    path = project / RECEIPT
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return record


def bind_intent(project: Path) -> Dict[str, Any]:
    """Copy the router's intent into the research package, verbatim.

    The gate does not accept a hand-written topic: it consumes the
    ``ContentIntent`` the router already produced, so both entrances
    (``USER_TOPIC`` and ``HOTSPOT_DISCOVERY``) arrive here in the same shape.
    Refuses to invent an intent, and refuses to re-point an approved package.
    """
    project = Path(project).resolve()
    brief = _read_json(project / BRIEF_FILE)
    intent = brief.get("intent") if isinstance(brief, dict) else None
    if not isinstance(intent, dict):
        raise PreresearchError(
            "NO_ROUTED_INTENT",
            f"no intent in {BRIEF_FILE}; route a topic first "
            f"(python scripts/content_route.py start --account <slug> --mode topic|hotspot)")

    receipt = _read_json(project / RECEIPT)
    if isinstance(receipt, dict) and receipt.get("status") == "APPROVED":
        raise PreresearchError(
            "ALREADY_APPROVED",
            "an approved research package cannot be re-pointed at another intent; "
            f"delete {RECEIPT} and research the new topic")

    path = project / INTENT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(intent, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    context = intent.get("route_context")
    context = context if isinstance(context, dict) else {}
    return {
        "state": "INTENT_BOUND",
        "project": project.name,
        "path": str(INTENT_FILE),
        "route_mode": intent.get("route_mode"),
        "topic": intent.get("topic"),
        "topic_origin": context.get("topic_origin"),
        "candidate_id": context.get("candidate_id"),
        "next": "fill the remaining four artifacts, then check, then approve",
        "production_ready": False,
        "publish_authorized": False,
    }


def require(project: Path) -> Dict[str, Any]:
    """Fail-closed wrapper for the stable production entry point."""
    report = check(project)
    if not report["ok"]:
        raise PreresearchError("PRECOPY_RESEARCH_REQUIRED", report["detail"], report)
    return report
