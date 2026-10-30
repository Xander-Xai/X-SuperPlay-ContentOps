"""Rank candidates for an account, and say why each one ranked where it did.

Why this exists
---------------
The obvious ranking is the hot list's own order. It is wrong for this system
for one reason: a list's rank is a statement about *popularity among that
list's readers*, and the account's question is a statement about *fit for one
account's readers*. Those are different questions and they routinely disagree.

So the rank is computed from seven components, each scored 0-10 and each
weighted by a percentage the account owns. The weights live in the account's
DNA, they sum to 100, and the candidate record carries the score *and* the
sentence explaining it. A person choosing a topic can see that it won because
it matched two pillars and had a primary source, not because it was third on
a list.

The rule about numbers
----------------------
A view count on one platform and a heat index on another are not the same
quantity and are not added together. Platform-native counters are recorded on
the candidate and marked ``comparable: false``; they never enter the score.
The one cross-source signal the rank does use is a *count of distinct sources*
mentioning the same thing, which is a fact about coverage rather than a
comparison of incompatible scales.

What the rank is not
--------------------
It is not a fact check. A candidate can score well on every component and
still be wrong; that is why the candidate carries an explicit
``verification_status`` and why a person still chooses it.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .adapters import RawItem, freshness_hours_since

#: Content categories a candidate can be put in. The set is closed so a
#: category means the same thing on every run.
CATEGORIES: Tuple[str, ...] = (
    "open_source_project",
    "ai_tool",
    "ai_model",
    "engineering_technique",
    "industry_news",
    "business_opportunity",
    "hardware",
    "community_discussion",
    "unclassified",
)

#: Evidence a candidate can offer. ``PRIMARY_ARTIFACT`` is the strongest: it
#: is something the account can itself go and test.
VERIFICATION_STATUSES: Tuple[str, ...] = (
    "primary_artifact",
    "reported_not_verified",
    "unverified",
)

#: Substrings that mark a URL as pointing at something the account can open
#: and use. These are checked against the URL, never guessed from the title.
_PRIMARY_HOSTS = ("github.com", "arxiv.org", "huggingface.co", "pypi.org",
                  "npmjs.com", "docs.", "developer.")

#: Words that mark a title as offering a business or opportunity angle.
_BUSINESS_MARKERS = ("商业", "生意", "变现", "机会", "定价", "收费", "客户", "付费",
                     "收入", "成本", "岗位", "求职", "freelance", "pricing",
                     "revenue", "monetiz", "business", "market")

#: Words that mark a title as offering a technical angle.
_TECHNICAL_MARKERS = ("架构", "实现", "源码", "调试", "部署", "评测", "复现", "踩坑",
                      "重构", "性能", "架构", "agent", "rag", "llm", "mcp",
                      "architecture", "implementation", "benchmark", "debug")


def normalise(text: str) -> str:
    """A comparable form of a title: case-folded, punctuation-free, tight."""
    lowered = (text or "").casefold()
    stripped = re.sub(r"[^\w一-鿿]+", " ", lowered)
    return re.sub(r"\s+", " ", stripped).strip()


def token_set(text: str) -> frozenset:
    """The tokens of a title, for overlap comparison between sources."""
    return frozenset(token for token in normalise(text).split() if token)


def classify(title: str, snippet: str = "", extra: Optional[Dict[str, Any]] = None
             ) -> str:
    """Put a candidate in one closed category."""
    extra = extra or {}
    blob = f"{title} {snippet}".casefold()
    if "github" in blob or "开源" in blob or "open source" in blob or "repo" in blob:
        return "open_source_project"
    if any(word in blob for word in ("模型", "model", "llm", "多模态", "multimodal")):
        return "ai_model"
    if any(word in blob for word in ("工具", "tool", "插件", "plugin", "agent", "平台")):
        return "ai_tool"
    if any(word in blob for word in ("硬件", "hardware", "芯片", "chip", "gpu")):
        return "hardware"
    if any(word in blob for word in _BUSINESS_MARKERS):
        return "business_opportunity"
    if any(word in blob for word in _TECHNICAL_MARKERS):
        return "engineering_technique"
    if any(word in blob for word in ("融资", "发布", "上线", "announce", "release",
                                     "acquire", "收购")):
        return "industry_news"
    if any(word in blob for word in ("讨论", "请问", "大家", "how do i", "求助")):
        return "community_discussion"
    return "unclassified"


def verification_status(item: RawItem, category: str) -> str:
    """How well evidenced a candidate is, from what it actually points at."""
    url = (item.url or "").casefold()
    if any(marker in url for marker in _PRIMARY_HOSTS):
        return "primary_artifact"
    if category in ("open_source_project", "engineering_technique"):
        return "reported_not_verified"
    return "unverified"


def _hits(text: str, terms: Iterable[str]) -> List[str]:
    haystack = text.casefold()
    return [term for term in terms if term and term.casefold() in haystack]


# ---------------------------------------------------------------------------
# components
# ---------------------------------------------------------------------------


def _profile_relevance(item: RawItem, profile: Any, pillar: Optional[str]) -> Tuple[float, str]:
    text = f"{item.title} {item.snippet}"
    positive = _hits(text, profile.positive_terms)
    negative = _hits(text, profile.negative_terms)
    names_pillar = bool(pillar) and pillar.casefold() in text.casefold()
    score = min(10.0, len(positive) * 2.5)
    if names_pillar:
        score = min(10.0, score + 2.0)
    why = (f"matches {len(positive)} account term(s)"
           + (f" ({', '.join(positive[:4])})" if positive else ""))
    if names_pillar:
        why += f"; names the account's pillar {pillar!r}"
    if negative:
        why += f"; also matches {len(negative)} excluded term(s) ({', '.join(negative[:3])})"
        score -= min(4.0, len(negative) * 2.0)
    return max(0.0, score), why


def _audience_value(item: RawItem, profile: Any) -> Tuple[float, str]:
    text = f"{item.title} {item.snippet}"
    audience = _hits(text, profile.target_audience)
    score = min(10.0, len(audience) * 3.0)
    if audience:
        why = f"names {len(audience)} of the account's core audiences ({', '.join(audience[:3])})"
    else:
        why = "names none of the account's core audiences"
    return score, why


def _evidence_availability(item: RawItem, profile: Any, category: str) -> Tuple[float, str]:
    status = verification_status(item, category)
    if status == "primary_artifact":
        return 10.0, "links to a primary artifact the account can open and test"
    if status == "reported_not_verified":
        return 6.0, "is a technical subject that can be verified, but links only to a report"
    return 3.0, "is a report with no primary artifact behind it"


def _freshness(item: RawItem, window_hours: float,
               now: Optional[datetime] = None) -> Tuple[float, str]:
    age = freshness_hours_since(item.published_at, now=now)
    if age is None:
        return 0.0, "carries no publication time, so its freshness cannot be established"
    if window_hours and window_hours > 0:
        if age > window_hours:
            return 0.0, f"is {age:.0f} h old, outside the {window_hours:.0f} h window"
        score = 10.0 * (1.0 - (age / window_hours)) ** 0.5
        return round(score, 2), f"is {age:.0f} h old, inside the {window_hours:.0f} h window"
    return 5.0, "carries no usable freshness window, so recency is not scored"


def _cross_source_signal(distinct_sources: int) -> Tuple[float, str]:
    """How many *different* sources carry it. Never a sum of platform counters."""
    if distinct_sources <= 1:
        return 2.0, "carried by one source only"
    score = min(10.0, 2.0 + (distinct_sources - 1) * 2.5)
    return score, f"carried by {distinct_sources} distinct sources"


def _originality_potential(item: RawItem, profile: Any) -> Tuple[float, str]:
    text = f"{item.title} {item.snippet}"
    markers = [marker for marker in _BUSINESS_MARKERS + _TECHNICAL_MARKERS
               if marker.casefold() in text.casefold()]
    score = min(10.0, len(markers) * 3.0)
    if markers:
        return score, f"names {len(markers)} testable or commercial angle(s) ({', '.join(markers[:3])})"
    return 2.0, "names no angle the account can test, price or reproduce"


def _non_repetition(prior_appearances: int) -> Tuple[float, str]:
    if prior_appearances <= 0:
        return 10.0, "has not appeared in this account's earlier candidate pools"
    score = max(0.0, 10.0 - prior_appearances * 3.0)
    return score, f"appeared {prior_appearances} time(s) in this account's earlier pools"


def score_item(item: RawItem, profile: Any, *,
               pillar: Optional[str] = None,
               distinct_sources: int = 1,
               prior_appearances: int = 0,
               window_hours: float = 72.0,
               now: Optional[datetime] = None) -> Dict[str, Any]:
    """Score one candidate. Returns the total, every component and its reason."""
    category = classify(item.title, item.snippet, item.extra)
    components: Dict[str, Dict[str, Any]] = {}

    def add(name: str, value: float, why: str) -> None:
        components[name] = {"value": round(max(0.0, min(10.0, value)), 2), "why": why}

    add("profile_relevance", *_profile_relevance(item, profile, pillar))
    add("audience_value", *_audience_value(item, profile))
    add("evidence_availability", *_evidence_availability(item, profile, category))
    add("freshness", *_freshness(item, window_hours, now))
    add("cross_source_signal", *_cross_source_signal(distinct_sources))
    add("originality_potential", *_originality_potential(item, profile))
    add("non_repetition", *_non_repetition(prior_appearances))

    weights = profile.match_weights
    total = sum(components[name]["value"] * weights.get(name, 0) for name in components)
    total = total / 100.0
    return {
        "score": round(total, 2),
        "components": components,
        "weights": dict(weights),
        "category": category,
        "verification_status": verification_status(item, category),
    }


# ---------------------------------------------------------------------------
# relevance gate
# ---------------------------------------------------------------------------


def relevance_verdict(item: RawItem, profile: Any) -> Dict[str, Any]:
    """Whether an item belongs to this account at all.

    The gate is deliberately strict. An item that matches none of the
    account's terms is not "a weaker candidate"; it is not this account's
    content, and putting it in front of a person would be asking them to do
    the router's filtering.

    An item that matches an *excluded* term is rejected too, and the reason
    names the excluded term, so the rejection is auditable.
    """
    text = f"{item.title} {item.snippet}"
    positive = _hits(text, profile.positive_terms)
    negative = _hits(text, profile.negative_terms)
    if negative:
        return {
            "accepted": False,
            "reason": "EXCLUDED_TERM",
            "detail": f"matches the account's excluded term(s): {', '.join(negative)}",
            "matched_terms": positive,
        }
    if not positive:
        return {
            "accepted": False,
            "reason": "NO_ACCOUNT_TERM",
            "detail": "matches none of the account's declared terms",
            "matched_terms": [],
        }
    return {
        "accepted": True,
        "reason": "MATCHED",
        "detail": f"matches {len(positive)} of the account's declared terms",
        "matched_terms": positive,
    }


def _angles_for(profile: Any, pillar: Optional[str]) -> List[str]:
    """The shapes an episode on this pillar could take.

    They are the account's own declared beat structure for that pillar — the
    steps the account says a piece of this kind goes through. Listing them is
    not inventing an angle; it is quoting the account's content formula.
    """
    for entry in getattr(profile, "content_pillars", ()) or ():
        if isinstance(entry, dict) and entry.get("name") == pillar:
            return [str(step) for step in (entry.get("structure") or [])]
    return []


def build_candidate(item: RawItem, profile: Any, *, collected_at: str,
                    pillar: Optional[str] = None,
                    distinct_sources: int = 1,
                    prior_appearances: int = 0,
                    window_hours: float = 72.0,
                    now: Optional[datetime] = None,
                    also_seen_in: Optional[List[str]] = None) -> Dict[str, Any]:
    """The full candidate record, as the task requires it.

    It carries the source, the original title and link, the original
    publication time and the collection time, the rank and how the rank
    changed, the platform's own counters (marked incomparable), the category,
    the pillar, the relevance, the freshness, the verification status, and the
    reasons for and against making it.
    """
    scored = score_item(item, profile, pillar=pillar,
                        distinct_sources=distinct_sources,
                        prior_appearances=prior_appearances,
                        window_hours=window_hours, now=now)
    relevance = relevance_verdict(item, profile)
    resolved_pillar = pillar or profile.pillar_for(f"{item.title} {item.snippet}")
    age = freshness_hours_since(item.published_at, now=now)
    reasons_for: List[str] = []
    reasons_against: List[str] = []
    for name, component in scored["components"].items():
        if component["value"] >= 6.0:
            reasons_for.append(f"{name}: {component['why']}")
        elif component["value"] <= 3.0:
            reasons_against.append(f"{name}: {component['why']}")
    if not reasons_for:
        reasons_for.append("no component scored above the review threshold")
    if not reasons_against:
        reasons_against.append("no component scored below the threshold")

    return {
        "source_id": item.source_id,
        "title": item.title,
        "url": item.url,
        "published_at": item.published_at,
        "collected_at": collected_at,
        "source_rank": item.rank,
        "rank_change": None,
        "snippet": item.snippet,
        "rank_change_note": "the source publishes one rank, not a history; a "
                            "change is recorded only when a source actually "
                            "carries one, and never inferred",
        "metrics": dict(item.metrics),
        "metrics_comparable": False,
        "metrics_note": "platform-native counters; they are recorded, never added "
                        "to another platform's counters and never scored",
        "category": scored["category"],
        "pillar": resolved_pillar,
        "angles": _angles_for(profile, resolved_pillar),
        "angles_note": "the account's own declared beat structure for this "
                       "pillar; these are the shapes the episode could take, "
                       "not angles invented here",
        "relevance": {
            "score": scored["score"],
            "components": scored["components"],
            "weights": scored["weights"],
            "accepted": relevance["accepted"],
            "reason": relevance["reason"],
            "detail": relevance["detail"],
            "matched_terms": relevance["matched_terms"],
        },
        "freshness": {
            "hours_old": round(age, 2) if age is not None else None,
            "window_hours": window_hours,
            "within_window": age is not None and (not window_hours or age <= window_hours),
        },
        "verification_status": scored["verification_status"],
        "also_seen_in": list(also_seen_in or []),
        "reasons_for": reasons_for,
        "reasons_against": reasons_against,
    }


def rank_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort by score, then by the account's own ordering rules.

    Ties break on the original publication time and then the title, so the
    order is stable across runs. A hot list's own rank is never a tie-breaker:
    it belongs to a different question. A candidate with no publication time
    sorts after one that has it, because an undated item cannot be shown to
    be the newer one.
    """
    def key(candidate: Dict[str, Any]):
        score = candidate.get("relevance", {}).get("score", 0.0)
        published = str(candidate.get("published_at") or "")
        undated = 0 if published else 1
        return (-float(score), undated, _invert_time(published),
                str(candidate.get("title") or ""))

    return sorted(candidates, key=key)


def _invert_time(timestamp: str) -> str:
    """Sort helper that puts newer timestamps first inside an ascending sort."""
    if not timestamp:
        return ""
    return "".join(chr(255 - ord(ch)) if ord(ch) < 255 else ch for ch in timestamp)
