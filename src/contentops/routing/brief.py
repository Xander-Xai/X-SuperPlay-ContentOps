"""Turn a chosen topic into the brief package the pipeline reads.

Why this exists
---------------
Two routes produce a topic, and the pipeline downstream must not care which.
So the convergence happens here, once, and everything after this point reads
one shape.

The package has three documents, and two of them are the repository's
existing contracts rather than new dialects:

``intent``
    The unified input contract, ``contentops.content-intent/v1``. This is the
    object the pipeline consumes. It carries the account, the profile version
    it was built against, the topic, the evidence and approval status, and a
    ``route_context`` block whose keys are identical in both routes.

``candidate``
    The topic candidate, in the repository's own
    ``contentops.content-candidate/v1`` shape. Its scores are derived from
    the account-weighted components, so the document that a person reviews is
    the document the ranker produced. It is validated with the existing
    validator, so a brief that would not survive that contract is refused
    before it is written.

``forecast``
    The evidence feasibility forecast, in the existing
    ``contentops.evidence-feasibility/v1`` shape: which captures the topic
    needs, who produces them, whether they are available, and what to do if
    they are not.

What a brief does not say
-------------------------
It does not say the topic is true, that the evidence exists, or that the
video is good. The forecast says the evidence *path* is declared; the copy
review, downstream and unchanged, still decides whether the copy may be
rendered.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..routing.models import ContentIntent, digest
from .account_profile import AccountProfile
from ..hotspots.adapters import RawItem
from ..hotspots.ranking import score_item

#: The brief package's own schema.
BRIEF_SCHEMA = "contentops.content-brief/v1"

#: The directory the package occupies inside a project or a run.
BRIEF_DIR = "00_brief"

#: The filename the package occupies.
BRIEF_FILE = "brief.json"

#: Which of the seven ranking components feeds which topic-contract score.
#: The mapping is one-to-one where it can be and stated where it cannot be, so
#: a reviewer comparing the two documents can follow it.
NEED_SCORE_SOURCES: Dict[str, str] = {
    "problem_frequency": "audience_value",
    "problem_severity": "originality_potential",
    "decision_value": "evidence_availability",
    "information_gap": "profile_relevance",
    "existing_solution_quality": "cross_source_signal",
    "audience_relevance": "audience_value",
}

VALUE_SCORE_SOURCES: Dict[str, str] = {
    "demand": "audience_value",
    "audience_relevance": "audience_value",
    "problem_severity": "profile_relevance",
    "trust_evidence_strength": "evidence_availability",
    "business_fit": "originality_potential",
    "production_cost": "freshness",
}

CATEGORY_LABELS: Dict[str, str] = {
    "open_source_project": "开源项目",
    "ai_tool": "AI 工具",
    "ai_model": "AI 模型",
    "engineering_technique": "工程技巧",
    "industry_news": "行业动态",
    "business_opportunity": "商业机会",
    "hardware": "AI 硬件",
    "community_discussion": "社区讨论",
    "unclassified": "未分类",
}


def _to_band(value: float) -> int:
    """A 0-10 component as the topic contract's 1-5 band."""
    try:
        scaled = float(value)
    except (TypeError, ValueError):
        return 1
    band = 1 + round(max(0.0, min(10.0, scaled)) / 10.0 * 4)
    return max(1, min(5, band))


def candidate_document(candidate_id: str, *, title: str, thesis: str,
                       audience_segment: str, decision: str,
                       positioning_alignment: str, trust_level: str,
                       components: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """A topic candidate in the repository's existing contract shape."""
    def band(source: str) -> int:
        return _to_band((components.get(source) or {}).get("value", 0.0))

    return {
        "schema": "contentops.content-candidate/v1",
        "candidate_id": candidate_id,
        "title": title,
        "thesis": thesis,
        "audience_segment": audience_segment,
        "decision": decision,
        "positioning_alignment": positioning_alignment,
        "trust_level": trust_level,
        "need_scores": {key: band(source) for key, source in NEED_SCORE_SOURCES.items()},
        "value_scores": {key: band(source) for key, source in VALUE_SCORE_SOURCES.items()},
    }


def forecast_document(*, topic_id: str, profile: AccountProfile,
                      verification_status: str, has_primary_source: bool,
                      assessment_basis: str) -> Dict[str, Any]:
    """The evidence feasibility forecast for a topic.

    The forecast is written before production, which is its whole purpose: it
    says what evidence the topic will need and what happens when it cannot be
    got. A required capture that has not happened yet is recorded as not
    available, with a declared failure plan — that is what makes the verdict
    ``DEGRADED`` rather than ``FEASIBLE``, and it is the honest answer at this
    point in the pipeline.
    """
    evidence: List[Dict[str, Any]] = []
    evidence_led = profile.evidence_mode == "EVIDENCE_LED"
    recording_allowed = profile.manual_recording == "ALLOWED_CROPPED"

    if verification_status == "primary_artifact" and has_primary_source:
        evidence.append({
            "kind": "authoritative_source",
            "required": True,
            "owner": "automated",
            "available": True,
        })
    else:
        evidence.append({
            "kind": "authoritative_source",
            "required": True,
            "owner": "human",
            "available": False,
        })

    if evidence_led and recording_allowed:
        evidence.append({
            "kind": "screen_recording",
            "required": True,
            "owner": "human",
            "available": False,
        })
        evidence.append({
            "kind": "terminal_capture",
            "required": False,
            "owner": "human",
            "available": False,
        })
    elif not evidence_led:
        evidence.append({
            "kind": "real_document",
            "required": False,
            "owner": "human",
            "available": False,
        })

    failure_plan = "degrade_and_declare" if recording_allowed else "change_claim"
    document: Dict[str, Any] = {
        "schema": "contentops.evidence-feasibility/v1",
        "topic_id": topic_id,
        "assessment_basis": assessment_basis,
        "evidence": evidence,
        "failure_plan": failure_plan,
    }
    if failure_plan == "degrade_and_declare":
        document["degrade_note"] = (
            "The account's evidence mode needs a recording this topic has not "
            "produced yet. The cut may proceed only with the recording actually "
            "captured, or with the affected claims narrowed and declared in the "
            "script. A generated illustration may not stand in for the capture.")
    return document


def alignment_for(profile: AccountProfile, text: str) -> Dict[str, Any]:
    """How a piece of text sits against the account's declared positioning.

    ``ALIGNED`` — the text names the account's own terms.
    ``ADJACENT`` — it names a related term but not a declared one.
    ``OFF_POSITIONING`` — it names an excluded term, or nothing the account
    covers. This is a *review* state, never an automatic rejection: the
    account owner may know a reason the declaration does not.
    """
    lowered = text.casefold()
    positive = [keyword.term for keyword in profile.keywords_positive
                if keyword.term.casefold() in lowered]
    negative = [keyword.term for keyword in profile.keywords_negative
                if keyword.term.casefold() in lowered]
    pillars = [name for name in profile.pillar_names() if name.casefold() in lowered]
    include_text = " ".join(profile.topics_include).casefold()

    if negative:
        return {
            "alignment": "OFF_POSITIONING",
            "reason": "EXCLUDED_TERM",
            "detail": f"the topic names the account's excluded term(s): "
                      f"{', '.join(negative)}",
            "matched_terms": positive,
            "matched_excluded": negative,
            "matched_pillars": pillars,
        }
    if positive:
        return {
            "alignment": "ALIGNED",
            "reason": "MATCHED_ACCOUNT_TERM",
            "detail": f"the topic names {len(positive)} of the account's declared "
                      f"terms: {', '.join(positive[:4])}",
            "matched_terms": positive,
            "matched_excluded": [],
            "matched_pillars": pillars,
        }
    if include_text and any(token and token in lowered for token in _scope_tokens(profile)):
        return {
            "alignment": "ADJACENT",
            "reason": "PILLAR_SCOPE_TERM",
            "detail": "the topic names a term from the account's pillar scopes "
                      "without naming a declared keyword",
            "matched_terms": [],
            "matched_excluded": [],
            "matched_pillars": pillars,
        }
    return {
        "alignment": "OFF_POSITIONING",
        "reason": "NO_ACCOUNT_TERM",
        "detail": "the topic names none of the account's declared terms or pillar "
                  "scopes; it may still be on-strategy, but the account's own "
                  "declaration does not say so",
        "matched_terms": [],
        "matched_excluded": [],
        "matched_pillars": pillars,
    }


def _scope_tokens(profile: AccountProfile) -> List[str]:
    """Meaningful tokens from the account's pillar scopes."""
    tokens: List[str] = []
    for pillar in profile.content_pillars:
        scope = str(pillar.get("scope") or "")
        for part in scope.replace("/", " ").replace("，", " ").split():
            cleaned = part.strip()
            if len(cleaned) >= 2:
                tokens.append(cleaned)
    return tokens


def topic_components(profile: AccountProfile, *, topic: str, snippet: str = "",
                      url: str = "", published_at: Optional[str] = None,
                      distinct_sources: int = 1, prior_appearances: int = 0
                      ) -> Dict[str, Any]:
    """The seven components for a topic, whichever route produced it.

    A user-specified topic is scored the same way a hot-list candidate is, so
    the two briefs are comparable and the same downstream validators accept
    both. The only difference is freshness: a topic the user chose has no
    publication time, so recency is not scored against it rather than being
    scored as zero.
    """
    item = RawItem(source_id="user-topic", title=topic, url=url,
                   published_at=published_at, snippet=snippet)
    scored = score_item(item, profile, distinct_sources=distinct_sources,
                        prior_appearances=prior_appearances, window_hours=0.0)
    components = scored["components"]
    components["freshness"] = {
        "value": 5.0,
        "why": "a user-specified topic carries no publication time, so recency is "
               "not scored against it",
    }
    return scored


def build_brief_package(*, intent: ContentIntent, profile: AccountProfile,
                        candidate: Dict[str, Any],
                        forecast: Dict[str, Any],
                        extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The package written to disk and handed to the pipeline."""
    from ..workflow.human_forecast import forecast_verdict
    document = {
        "schema": BRIEF_SCHEMA,
        "intent": intent.to_dict(),
        "candidate": candidate,
        "forecast": forecast,
        "forecast_verdict": forecast_verdict(forecast),
        "profile": profile.summary(),
        "route": intent.route_context.to_dict(),
        "created_at": intent.created_at,
    }
    if extra:
        document.update(extra)
    document["brief_id"] = "BRIEF-" + digest(document)[:16].upper()
    return document


def write_brief_package(directory: Path, package: Dict[str, Any]) -> Path:
    """Write the package, creating its directory. Returns the file written."""
    directory = Path(directory)
    target = directory / BRIEF_DIR
    target.mkdir(parents=True, exist_ok=True)
    path = target / BRIEF_FILE
    path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


def read_brief_package(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_brief_package(package: Any) -> List[str]:
    """The failures that would make this brief unusable downstream."""
    from ..routing.models import validate_intent
    from ..workflow.human_forecast import validate_forecast
    from ..workflow.topics import validate_candidate

    if not isinstance(package, dict):
        return ["a brief package must be a JSON object"]
    if package.get("schema") != BRIEF_SCHEMA:
        return [f"brief package schema must be {BRIEF_SCHEMA!r}"]
    failures: List[str] = []
    failures.extend(f"intent: {message}" for message in validate_intent(package.get("intent")))
    failures.extend(f"candidate: {message}" for message in validate_candidate(package.get("candidate")))
    failures.extend(f"forecast: {message}" for message in validate_forecast(package.get("forecast")))
    return failures
