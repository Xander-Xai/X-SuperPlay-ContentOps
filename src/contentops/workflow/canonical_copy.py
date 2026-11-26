"""Canonical topic copy and format-derivative lineage contracts.

The authoring skill writes one claim/evidence-bound source after pre-copy
research. VIDEO and GRAPHIC_TEXT derivatives keep a reference to that source;
this module validates structure and lineage, not semantic equivalence of prose.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence

SCHEMA = "contentops.canonical-topic-copy/v1"
DERIVATIVE_SCHEMA = "contentops.topic-copy-derivative/v1"
FORMATS = ("VIDEO", "GRAPHIC_TEXT")
CANONICAL_FILE = Path("00_brief") / "canonical-copy.json"
DERIVATIVE_FILE = Path("00_brief") / "copy-derivative.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(document: Dict[str, Any]) -> str:
    """Return the stable SHA-256 of a JSON-compatible copy record."""
    return hashlib.sha256(_canonical(document)).hexdigest()


def validate(document: Any) -> List[str]:
    """Return structural failures for a canonical copy; never infer approval."""
    failures: List[str] = []
    if not isinstance(document, dict):
        return ["canonical copy must be a JSON object"]
    if document.get("schema") != SCHEMA:
        failures.append(f"schema must be {SCHEMA}")
    for key in ("copy_id", "account", "topic"):
        if not isinstance(document.get(key), str) or not document[key].strip():
            failures.append(f"{key} must be a non-empty string")
    for key in ("intent_sha256", "research_sha256"):
        if not isinstance(document.get(key), str) or not _SHA256.fullmatch(document[key]):
            failures.append(f"{key} must be a lowercase SHA-256 digest")

    segments = document.get("segments")
    claims = document.get("claims")
    if not isinstance(segments, list) or not segments:
        failures.append("segments must be a non-empty list")
        segments = []
    if not isinstance(claims, dict) or not claims:
        failures.append("claims must be a non-empty mapping")
        claims = {}

    seen_segments = set()
    used_claims = set()
    for index, segment in enumerate(segments):
        where = f"segments[{index}]"
        if not isinstance(segment, dict):
            failures.append(f"{where} must be an object")
            continue
        segment_id = segment.get("id")
        if not isinstance(segment_id, str) or not segment_id.strip():
            failures.append(f"{where}.id must be a non-empty string")
        elif segment_id in seen_segments:
            failures.append(f"{where}.id {segment_id!r} is duplicated")
        else:
            seen_segments.add(segment_id)
        if not isinstance(segment.get("text"), str) or not segment["text"].strip():
            failures.append(f"{where}.text must be a non-empty string")
        refs = segment.get("claim_refs")
        if not isinstance(refs, list) or not refs:
            failures.append(f"{where}.claim_refs must be a non-empty list")
            continue
        for claim_ref in refs:
            if not isinstance(claim_ref, str) or not claim_ref:
                failures.append(f"{where}.claim_refs entries must be non-empty strings")
            elif claim_ref not in claims:
                failures.append(f"{where} references unknown claim {claim_ref!r}")
            else:
                used_claims.add(claim_ref)

    for claim_id, claim in claims.items():
        where = f"claims.{claim_id}"
        if not isinstance(claim_id, str) or not claim_id.strip():
            failures.append("claim ids must be non-empty strings")
        if not isinstance(claim, dict):
            failures.append(f"{where} must be an object")
            continue
        if not isinstance(claim.get("statement"), str) or not claim["statement"].strip():
            failures.append(f"{where}.statement must be a non-empty string")
        refs = claim.get("evidence_refs")
        if not isinstance(refs, list) or not refs or any(
                not isinstance(ref, str) or not ref.strip() for ref in refs):
            failures.append(f"{where}.evidence_refs must contain at least one evidence id")
    unused = set(claims) - used_claims
    if unused:
        failures.append(f"claims are not used by any segment: {', '.join(sorted(unused))}")
    return failures


def status(project: Path, content_format: str) -> Dict[str, Any]:
    """Check project binding, derivative lineage, and rendered copy presence.

    Legacy projects without a canonical-copy artifact remain on their existing
    path. Once a project opts in by carrying the artifact, every failure blocks.
    """
    project = Path(project)
    source_path = project / CANONICAL_FILE
    if not source_path.is_file():
        return {"ok": True, "applicable": False, "state": "LEGACY",
                "detail": "project has no canonical topic-copy artifact"}
    if content_format not in FORMATS:
        return {"ok": False, "applicable": True, "state": "FORMAT_UNKNOWN",
                "detail": f"format must be one of {FORMATS}"}
    try:
        document = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "applicable": True, "state": "CANONICAL_COPY_INVALID",
                "detail": "canonical-copy.json is unreadable"}
    failures = validate(document)
    if failures:
        return {"ok": False, "applicable": True, "state": "CANONICAL_COPY_INVALID",
                "detail": "; ".join(failures)}

    from . import preresearch

    research = preresearch.check(project)
    if not research.get("ok"):
        return {"ok": False, "applicable": True, "state": "RESEARCH_NOT_CURRENT",
                "detail": str(research.get("detail") or research.get("state"))}
    intent_path = project / preresearch.INTENT_FILE
    try:
        intent_raw = intent_path.read_bytes()
        intent = json.loads(intent_raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return {"ok": False, "applicable": True, "state": "INTENT_UNREADABLE",
                "detail": "the signed research intent cannot be read"}
    if hashlib.sha256(intent_raw).hexdigest() != document.get("intent_sha256"):
        return {"ok": False, "applicable": True, "state": "INTENT_MISMATCH",
                "detail": "canonical copy is not bound to the current routed intent"}
    if research.get("artifacts_sha256") != document.get("research_sha256"):
        return {"ok": False, "applicable": True, "state": "RESEARCH_MISMATCH",
                "detail": "canonical copy is not bound to the current signed research"}
    if intent.get("account_id") != document.get("account") or intent.get("topic") != document.get("topic"):
        return {"ok": False, "applicable": True, "state": "INTENT_MISMATCH",
                "detail": "canonical copy account/topic differs from the routed intent"}
    try:
        evidence_list = json.loads(
            (project / preresearch.EVIDENCE_FILE).read_text(encoding="utf-8"))
        evidence_ids = {item.get("id") for item in evidence_list.get("items", [])
                        if isinstance(item, dict)}
    except (OSError, ValueError, AttributeError):
        evidence_ids = set()
    unknown_evidence = sorted({evidence_ref
                               for claim in document["claims"].values()
                               for evidence_ref in claim["evidence_refs"]
                               if evidence_ref not in evidence_ids})
    if unknown_evidence:
        return {"ok": False, "applicable": True, "state": "EVIDENCE_MISMATCH",
                "detail": "claim evidence refs are absent from signed research: "
                          + ", ".join(unknown_evidence)}

    derivative_path = project / DERIVATIVE_FILE
    try:
        derivative = json.loads(derivative_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "applicable": True, "state": "DERIVATIVE_MISSING",
                "detail": f"{DERIVATIVE_FILE.as_posix()} is missing or unreadable"}
    failures = validate_derivative(document, derivative)
    if derivative.get("format") != content_format:
        failures.append(f"derivative format is {derivative.get('format')!r}, expected {content_format}")
    if failures:
        return {"ok": False, "applicable": True, "state": "DERIVATIVE_INVALID",
                "detail": "; ".join(failures)}

    output = project / Path("draft.md" if content_format == "GRAPHIC_TEXT"
                            else "script/master.md")
    try:
        output_text = output.read_text(encoding="utf-8")
    except OSError:
        return {"ok": False, "applicable": True, "state": "FORMAT_COPY_MISSING",
                "detail": f"{output.relative_to(project).as_posix()} is missing"}
    missing = [segment["text"] for segment in derivative["segments"]
               if segment["text"] not in output_text]
    if missing:
        return {"ok": False, "applicable": True, "state": "FORMAT_COPY_DIVERGED",
                "detail": "format copy does not contain all reviewed derivative segments"}
    return {"ok": True, "applicable": True, "state": "LINEAGE_CURRENT",
            "copy_id": document["copy_id"], "copy_sha256": digest(document),
            "format": content_format,
            "detail": "format copy is bound to the current researched canonical source"}


def derive(document: Dict[str, Any], content_format: str,
           segment_ids: Sequence[str]) -> Dict[str, Any]:
    """Build a format-specific, exact-text derivative from selected source segments."""
    failures = validate(document)
    if failures:
        raise ValueError("canonical copy invalid: " + "; ".join(failures))
    if content_format not in FORMATS:
        raise ValueError(f"format must be one of {FORMATS}")
    by_id = {segment["id"]: segment for segment in document["segments"]}
    if not segment_ids:
        raise ValueError("at least one canonical segment must be selected")
    if len(set(segment_ids)) != len(segment_ids):
        raise ValueError("segment_ids must not contain duplicates")
    missing = [segment_id for segment_id in segment_ids if segment_id not in by_id]
    if missing:
        raise ValueError("unknown canonical segment(s): " + ", ".join(missing))
    return {
        "schema": DERIVATIVE_SCHEMA,
        "copy_id": document["copy_id"],
        "copy_sha256": digest(document),
        "format": content_format,
        "segments": [
            {"source_segment_id": segment_id,
             "text": by_id[segment_id]["text"],
             "claim_refs": list(by_id[segment_id]["claim_refs"])}
            for segment_id in segment_ids
        ],
    }


def validate_derivative(document: Dict[str, Any], derivative: Any) -> List[str]:
    """Validate the derivative's source binding and claim subset.

    This is a deterministic lineage check. It cannot prove that an edited
    paraphrase preserves a claim's meaning, so production callers must not treat
    this check as semantic or editorial approval.
    """
    failures = validate(document)
    if failures:
        return ["canonical copy invalid: " + "; ".join(failures)]
    if not isinstance(derivative, dict):
        return ["derivative must be a JSON object"]
    if derivative.get("schema") != DERIVATIVE_SCHEMA:
        failures.append(f"derivative schema must be {DERIVATIVE_SCHEMA}")
    if derivative.get("copy_id") != document.get("copy_id"):
        failures.append("derivative copy_id does not match canonical copy")
    expected_digest = digest(document)
    if derivative.get("copy_sha256") != expected_digest:
        failures.append("derivative copy_sha256 does not match canonical copy")
    if derivative.get("format") not in FORMATS:
        failures.append(f"derivative format must be one of {FORMATS}")

    canonical_segments = {item["id"]: item for item in document["segments"]}
    derivative_segments = derivative.get("segments")
    if not isinstance(derivative_segments, list) or not derivative_segments:
        failures.append("derivative segments must be a non-empty list")
        return failures
    seen = set()
    claims = document["claims"]
    for index, segment in enumerate(derivative_segments):
        where = f"derivative.segments[{index}]"
        if not isinstance(segment, dict):
            failures.append(f"{where} must be an object")
            continue
        source_id = segment.get("source_segment_id")
        source = canonical_segments.get(source_id)
        if source is None:
            failures.append(f"{where} references unknown source segment {source_id!r}")
            continue
        if source_id in seen:
            failures.append(f"{where} duplicates source segment {source_id!r}")
        seen.add(source_id)
        if not isinstance(segment.get("text"), str) or not segment["text"].strip():
            failures.append(f"{where}.text must be a non-empty string")
        refs = segment.get("claim_refs")
        if not isinstance(refs, list):
            failures.append(f"{where}.claim_refs must be a list")
            continue
        allowed = set(source.get("claim_refs") or [])
        actual = set(refs)
        if len(actual) != len(refs):
            failures.append(f"{where}.claim_refs contains duplicates")
        if actual != allowed:
            failures.append(
                f"{where}.claim_refs must preserve the source segment's claim set "
                f"{sorted(allowed)}; got {sorted(actual)}")
    return failures
