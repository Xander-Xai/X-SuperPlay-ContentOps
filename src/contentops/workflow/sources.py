"""Source candidates: the reviewed list a rights ledger must descend from.

A ledger says an asset is cleared. It cannot say the asset was ever *chosen*
from a reviewed list, so a clip can enter a delivery with a licence field
filled in by whoever fetched it. The failure that allows is quiet: the licence
looks complete, nobody can show where it came from, and there is no earlier
record to check it against.

This module owns that earlier record. A candidate keeps the canonical page, the
creator, the licence text and URL, the capture date and a score, and it stays
``candidate``: clearance is the ledger's job, in a separate document, by a named
person. Promotion is a check, not a flag — :func:`promotable` lists what still
blocks a candidate from becoming a ledger row.

The candidate fields and the "never cleared or used here" rule are absorbed
from the retired ``dy_x1024`` ``material-source-research`` contract.
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

SCHEMA = "contentops.source-candidates/v1"

LICENCES = ("owned", "licensed", "public_domain", "permission", "unknown")

#: Candidate statuses. There is exactly one, on purpose: a research list that
#: can say "cleared" is a research list that can clear itself.
STATUSES = ("candidate",)

#: Score weights, applied to 0-10 components. Evidence and relevance decide
#: whether the beat is worth showing; rights decide whether it may be used, and
#: are weighted lower only because an unlicensed candidate is already blocked
#: by :func:`promotable` rather than merely scored down.
SCORE_WEIGHTS = {"relevance": 0.4, "evidence": 0.4, "rights": 0.2}
SCORE_MAX = 10

#: A candidate below this aggregate is not worth a human's review time.
PROMOTION_FLOOR = 6.0

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_http(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        # urlparse raises on a malformed bracketed host ("https://[::1"). A URL
        # that cannot be parsed is not an http URL; it must not crash a gate.
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _valid_date(value: str) -> bool:
    if not _DATE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def score_of(candidate: Dict[str, Any]) -> Optional[float]:
    """The weighted 0-10 score, or ``None`` when a component is missing."""
    score = candidate.get("score")
    if not isinstance(score, dict):
        return None
    total = 0.0
    for key, weight in SCORE_WEIGHTS.items():
        value = score.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        if not math.isfinite(value):
            # NaN compares false against every bound, so a bare range check
            # would let it through and every later comparison would be wrong.
            return None
        if value < 0 or value > SCORE_MAX:
            return None
        total += float(value) * weight
    return round(total, 2)


def validate_candidates(document: Any) -> List[str]:
    """Structural and rights-field checks. Returns human-readable failures."""
    if not isinstance(document, dict):
        return ["source candidates must be a JSON object"]
    if document.get("schema") != SCHEMA:
        return [f"source candidates schema must be {SCHEMA!r}"]

    items = document.get("candidates")
    if not isinstance(items, list) or not items:
        return ["source candidates must be a non-empty array"]

    errors: List[str] = []
    seen = set()
    today = date.today()
    for index, item in enumerate(items):
        where = f"candidates[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} must be an object")
            continue

        candidate_id = _text(item.get("candidate_id"))
        if not candidate_id:
            errors.append(f"{where}.candidate_id must be a non-empty string")
        elif candidate_id in seen:
            errors.append(f"{where}.candidate_id duplicates {candidate_id!r}")
        else:
            seen.add(candidate_id)

        if item.get("status") not in STATUSES:
            errors.append(
                f"{where}.status must be 'candidate'; clearance belongs to the "
                "rights ledger, not to a research list")

        source_url = _text(item.get("source_url"))
        if not source_url:
            errors.append(f"{where}.source_url must name the canonical page")
        elif not _is_http(source_url):
            errors.append(f"{where}.source_url must be an http(s) URL")

        direct_url = _text(item.get("direct_url"))
        if direct_url and not _is_http(direct_url):
            errors.append(f"{where}.direct_url must be an http(s) URL when given")

        if not _text(item.get("creator")):
            errors.append(f"{where}.creator must name the creator or rights holder")

        licence = item.get("license")
        if licence not in LICENCES:
            errors.append(f"{where}.license must be one of {LICENCES}")
        elif licence != "owned":
            # A non-owned candidate without its licence text and URL cannot be
            # checked later, and a summary word ("CC") is not a licence.
            if not _text(item.get("license_text")):
                errors.append(f"{where}.license_text is required when license is {licence!r}")
            if not _is_http(_text(item.get("license_url"))):
                errors.append(f"{where}.license_url must be an http(s) URL "
                              f"when license is {licence!r}")

        captured = _text(item.get("capture_date"))
        if not captured:
            errors.append(f"{where}.capture_date must record when the source was seen")
        elif not _valid_date(captured):
            errors.append(f"{where}.capture_date must be YYYY-MM-DD")
        else:
            try:
                if date.fromisoformat(captured) > today:
                    errors.append(f"{where}.capture_date is in the future")
            except ValueError:  # pragma: no cover - _valid_date already refused
                pass

        score = item.get("score")
        if not isinstance(score, dict):
            errors.append(f"{where}.score must be an object with "
                          f"{sorted(SCORE_WEIGHTS)}")
        elif score_of(item) is None:
            errors.append(f"{where}.score components must be numbers 0-{SCORE_MAX}: "
                          f"{sorted(SCORE_WEIGHTS)}")

        claim_ids = item.get("claim_ids", [])
        if not isinstance(claim_ids, list) or any(not _text(cid) for cid in claim_ids):
            errors.append(f"{where}.claim_ids must be an array of non-empty strings")
    return errors


def promotable(document: Dict[str, Any], candidate_id: str) -> List[str]:
    """What still blocks ``candidate_id`` from becoming a rights-ledger row.

    An empty list means the candidate carries everything the ledger will need;
    it does **not** mean it is cleared. A named human still approves the ledger.
    """
    items = document.get("candidates") if isinstance(document, dict) else None
    if not isinstance(items, list):
        return ["source candidates must be an object with a candidates array"]
    match = next((item for item in items
                  if isinstance(item, dict)
                  and _text(item.get("candidate_id")) == candidate_id), None)
    if match is None:
        return [f"unknown candidate {candidate_id!r}"]

    blockers: List[str] = []
    if match.get("status") not in STATUSES:
        blockers.append(f"status {match.get('status')!r} is not 'candidate'; this "
                        "list may not promote a record that claims another state")
    licence = match.get("license")
    if licence not in LICENCES:
        # A missing or misspelt licence is not "probably fine": it is a record
        # nobody can act on, and the ledger row would inherit the uncertainty.
        blockers.append(f"license {licence!r} is not one of {LICENCES}")
    elif licence == "unknown":
        blockers.append("license is unknown; a candidate cannot be promoted "
                        "without an identified licence")
    elif licence != "owned" and not _is_http(_text(match.get("license_url"))):
        blockers.append("license_url is missing; the ledger row would be unverifiable")
    score = score_of(match)
    if score is None:
        blockers.append("score is incomplete")
    elif score < PROMOTION_FLOOR:
        blockers.append(f"score {score} is below the promotion floor {PROMOTION_FLOOR}")
    return blockers


def validate_ledger_provenance(ledger: Any, candidates: Any) -> List[str]:
    """Every ledger asset that cites a candidate must agree with that candidate.

    An asset with no ``source_candidate_id`` is not failed here: user-owned
    captures legitimately have no research candidate. But once an asset claims
    a candidate, the two documents must describe the same licence, or one of
    them is wrong and neither can be trusted.
    """
    if not isinstance(ledger, dict):
        return ["rights ledger must be a JSON object"]
    items = ledger.get("assets")
    if not isinstance(items, list):
        return ["rights ledger assets must be an array"]
    pool = candidates.get("candidates") if isinstance(candidates, dict) else None
    if not isinstance(pool, list):
        return ["source candidates must be an object with a candidates array"]

    by_id = {_text(item.get("candidate_id")): item for item in pool
             if isinstance(item, dict)}
    errors: List[str] = []
    for index, asset in enumerate(items):
        if not isinstance(asset, dict):
            continue
        where = f"assets[{index}]"
        raw_reference = asset.get("source_candidate_id")
        if raw_reference is None:
            continue
        reference = _text(raw_reference)
        if not reference:
            # A malformed reference is worse than none: it looks like a link
            # that was checked, so skipping it would hide the broken link.
            errors.append(f"{where}.source_candidate_id must be a non-empty "
                          f"string, got {raw_reference!r}")
            continue
        candidate = by_id.get(reference)
        if candidate is None:
            errors.append(f"{where}.source_candidate_id {reference!r} is not in "
                          "the candidate list")
            continue
        if asset.get("license") != candidate.get("license"):
            errors.append(
                f"{where}.license {asset.get('license')!r} disagrees with "
                f"candidate {reference!r} ({candidate.get('license')!r})")
    return errors
