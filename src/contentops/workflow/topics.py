"""Topic backlog and candidate scoring: decide what is worth making.

Two documents, two questions:

- the **backlog** answers "what is queued, and in which shelf?" so four videos a
  week cannot quietly become four unrelated experiments;
- the **candidate** answers "should this one move?" with a weighted score and an
  explicit decision, so a topic is not accepted because it feels timely.

The weights are data, not constants: they come from the account's positioning
document and can be changed without touching this module. The score is reported
with its components, so a reviewer can see *why* a topic ranked where it did.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

BACKLOG_SCHEMA = "contentops.topic-backlog/v1"
CANDIDATE_SCHEMA = "contentops.content-candidate/v1"

TOPIC_STATUSES = (
    "backlog", "shaped", "ready", "queued", "produced", "archived", "stopped",
)
DECISIONS = ("ACCEPT", "EXPERIMENT", "DEFER", "REJECT")
ALIGNMENT = ("ALIGNED", "ADJACENT", "EXPERIMENTAL", "OFF_POSITIONING")
TRUST = ("HIGH", "MEDIUM", "LOW", "UNKNOWN")

#: Shelves mirror the account's content pillars. A topic outside them is not
#: forbidden, but it must be declared EXPERIMENTAL by the candidate document.
DEFAULT_SHELVES = (
    "ai_tool_validation",
    "ai_real_business",
    "ai_native_one_person_company",
    "failure_boundary",
    "experimental",
)

DEFAULT_CONTENT_TYPES = (
    "newsjacking", "tool_test", "technical_explainer", "comparison",
    "github_project", "monetization_case", "career_experiment",
    "business_experiment", "tutorial", "failure_review", "opinion",
)

#: Weights are percentages and must sum to 100. They mirror the positioning
#: document; a project may override them, but the sum is still enforced.
DEFAULT_NEED_WEIGHTS = {
    "problem_frequency": 20,
    "problem_severity": 20,
    "decision_value": 20,
    "information_gap": 15,
    "existing_solution_quality": 10,
    "audience_relevance": 15,
}
DEFAULT_VALUE_WEIGHTS = {
    "demand": 20,
    "audience_relevance": 20,
    "problem_severity": 15,
    "trust_evidence_strength": 20,
    "business_fit": 15,
    "production_cost": 10,
}

BROAD_TERMS = ("所有人", "互联网用户", "对AI感兴趣的人", "everyone", "internet users")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate_backlog(document: Any,
                     shelves: Tuple[str, ...] = DEFAULT_SHELVES,
                     content_types: Tuple[str, ...] = DEFAULT_CONTENT_TYPES) -> List[str]:
    if not isinstance(document, dict):
        return ["topic backlog must be a JSON object"]
    if document.get("schema") != BACKLOG_SCHEMA:
        return [f"backlog schema must be {BACKLOG_SCHEMA!r}"]
    topics = document.get("topics")
    if not isinstance(topics, list) or not topics:
        return ["backlog.topics must be a non-empty array"]
    errors: List[str] = []
    seen = set()
    for index, topic in enumerate(topics):
        where = f"topics[{index}]"
        if not isinstance(topic, dict):
            errors.append(f"{where} must be an object")
            continue
        topic_id = topic.get("topic_id")
        if not isinstance(topic_id, str) or not topic_id.strip():
            errors.append(f"{where}.topic_id must be a non-empty string")
        elif topic_id in seen:
            errors.append(f"{where}.topic_id duplicates {topic_id!r}")
        else:
            seen.add(topic_id)
        if not _text(topic.get("title")):
            errors.append(f"{where}.title must be a non-empty string")
        if topic.get("shelf") not in shelves:
            errors.append(f"{where}.shelf must be one of {shelves}")
        if topic.get("content_type") not in content_types:
            errors.append(f"{where}.content_type must be one of {content_types}")
        if topic.get("status") not in TOPIC_STATUSES:
            errors.append(f"{where}.status must be one of {TOPIC_STATUSES}")
    return errors


def _weighted(scores: Dict[str, Any], weights: Dict[str, int], field: str,
              errors: List[str]) -> float:
    total = 0.0
    for key, weight in weights.items():
        value = scores.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 1 <= value <= 5:
            errors.append(f"{field}.{key} must be a number from 1 to 5")
            continue
        total += value * weight
    return total


def score_candidate(document: Dict[str, Any],
                    need_weights: Optional[Dict[str, int]] = None,
                    value_weights: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Return a 0-100 score with its components. Never invents a missing score."""
    need_weights = need_weights or DEFAULT_NEED_WEIGHTS
    value_weights = value_weights or DEFAULT_VALUE_WEIGHTS
    errors: List[str] = []
    for name, weights in (("need_weights", need_weights), ("value_weights", value_weights)):
        if sum(weights.values()) != 100:
            raise ValueError(f"{name} must sum to 100, got {sum(weights.values())}")
    need = document.get("need_scores") or {}
    value = document.get("value_scores") or {}
    need_total = _weighted(need, need_weights, "need_scores", errors)
    value_total = _weighted(value, value_weights, "value_scores", errors)
    return {
        "need_score": round(need_total / 100.0, 2),
        "value_score": round(value_total / 100.0, 2),
        "combined": round((need_total + value_total) / 200.0, 2),
        "errors": errors,
    }


def validate_candidate(document: Any,
                       need_weights: Optional[Dict[str, int]] = None,
                       value_weights: Optional[Dict[str, int]] = None) -> List[str]:
    if not isinstance(document, dict):
        return ["content candidate must be a JSON object"]
    if document.get("schema") != CANDIDATE_SCHEMA:
        return [f"candidate schema must be {CANDIDATE_SCHEMA!r}"]
    errors: List[str] = []
    for key in ("candidate_id", "title", "thesis", "audience_segment"):
        if not _text(document.get(key)):
            errors.append(f"{key} must be a non-empty string")
    if document.get("decision") not in DECISIONS:
        errors.append(f"decision must be one of {DECISIONS}")
    if document.get("positioning_alignment") not in ALIGNMENT:
        errors.append(f"positioning_alignment must be one of {ALIGNMENT}")
    if document.get("trust_level") not in TRUST:
        errors.append(f"trust_level must be one of {TRUST}")
    text = " ".join(str(document.get(key) or "") for key in ("title", "thesis", "audience_segment"))
    for term in BROAD_TERMS:
        if term.lower() in text.lower():
            errors.append(f"broad audience term {term!r} does not name a decision group")
    if document.get("positioning_alignment") == "OFF_POSITIONING" and document.get("decision") == "ACCEPT":
        errors.append("an OFF_POSITIONING candidate cannot be ACCEPTed")
    errors.extend(score_candidate(document, need_weights, value_weights)["errors"])
    return errors


def rank_candidates(documents: List[Dict[str, Any]],
                    need_weights: Optional[Dict[str, int]] = None,
                    value_weights: Optional[Dict[str, int]] = None) -> List[Dict[str, Any]]:
    """Sort accepted/experiment candidates by combined score, highest first."""
    ranked = []
    for document in documents:
        errors = validate_candidate(document, need_weights, value_weights)
        score = score_candidate(document, need_weights, value_weights)
        ranked.append({
            "candidate_id": document.get("candidate_id"),
            "decision": document.get("decision"),
            "combined": score["combined"],
            "errors": errors,
        })
    ranked.sort(key=lambda item: (-item["combined"], str(item["candidate_id"])))
    return ranked
