"""Route A: find the topics for an account, then wait for a person to choose.

Why this exists
---------------
This is the entrance that used to be a hot list with no owner. It is now a
three-step sequence, and the order is the design:

1. **Plan.** The account's profile decides which sources are contacted, what
   query each native-search source receives, how many items each may
   contribute, and how fresh an item must be. The plan is written down
   before anything is fetched.
2. **Collect.** Only the planned sources are contacted, each within its own
   limit. A source that fails is recorded by name and the others continue.
3. **Filter and rank.** Items that match no account term are dropped before
   they can reach the shortlist; the survivors are de-duplicated and ranked by
   the account's own weights.

What this route never does
--------------------------
It never chooses a topic. A candidate list is a proposal, and the state
machine has no edge that lets ``CANDIDATES_READY`` become a brief without a
person passing through ``TOPIC_SELECTED``. The cost of that rule is that the
CLI has one more step; the benefit is that no episode is made about something
nobody picked.

It also never calls a paid service, and never asks a model to pick. The
ranking is arithmetic over the account's declared weights.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from ..routing.models import digest, utcnow
from .account_profile import AccountProfile
from ..hotspots.adapters import FetchResult, RawItem, adapter_for, within_window
from ..hotspots.dedup import dedupe, distinct_sources, same_story
from ..hotspots.query_planner import build_search_plan
from ..hotspots.ranking import build_candidate, rank_candidates, relevance_verdict
from ..hotspots.source_registry import NATIVE_SEARCH


class CollectionResult:
    """What a collection run produced, and what it could not."""

    def __init__(self, *, plan: Dict[str, Any], items: List[RawItem],
                 candidates: List[Dict[str, Any]], fetch_results: List[FetchResult],
                 rejected: List[Dict[str, Any]], collected_at: str) -> None:
        self.plan = plan
        self.items = items
        self.candidates = candidates
        self.fetch_results = fetch_results
        self.rejected = rejected
        self.collected_at = collected_at

    @property
    def failures(self) -> List[Dict[str, Any]]:
        return [result.to_dict() for result in self.fetch_results if not result.ok]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan.get("plan_id"),
            "collected_at": self.collected_at,
            "fetched": len(self.items),
            "candidates": len(self.candidates),
            "rejected": len(self.rejected),
            "sources": [result.to_dict() for result in self.fetch_results],
            "failures": self.failures,
        }


def make_plan(profile: AccountProfile, *, pillar: Optional[str] = None,
              freshness_hours: int = 72,
              per_source_limit: int = 30) -> Dict[str, Any]:
    """The search plan for an account. Pure: it touches no network."""
    return build_search_plan(profile, pillar=pillar,
                             freshness_hours=freshness_hours,
                             per_source_limit=per_source_limit)


def collect(profile: AccountProfile, plan: Dict[str, Any], *,
            adapters: Optional[Dict[str, Callable[..., FetchResult]]] = None,
            trendradar_db: Optional[str] = None,
            timeout: float = 12.0,
            prior_appearances: Optional[Callable[[str], int]] = None,
            now: Optional[str] = None) -> CollectionResult:
    """Fetch, filter and rank, according to the plan.

    ``adapters`` overrides the adapter for a source id, which is how the
    offline tests run the whole route without a network. ``prior_appearances``
    answers "has this account seen this title before", which is what makes the
    non-repetition component real rather than decorative.
    """
    collected_at = now or utcnow()
    sources = plan.get("sources") or []
    fetch_results: List[FetchResult] = []
    items: List[RawItem] = []

    for entry in sources:
        source_id = str(entry.get("source_id") or "")
        source = _source_from_registry(source_id)
        if source is None:
            fetch_results.append(FetchResult(
                source_id, False, error_code="UNKNOWN_SOURCE",
                error_detail="the plan names a source that is not in the registry"))
            continue
        limit = int(entry.get("max_items") or 30)
        query = entry.get("query")
        adapter = None
        if adapters is not None:
            adapter = adapters.get(source_id)
        if adapter is None:
            adapter = adapter_for(source, trendradar_db=trendradar_db)
        result = adapter.fetch(source, limit=limit, timeout=timeout, query=query)
        fetch_results.append(result)
        items.extend(result.items)

    window_hours = float((plan.get("time_window") or {}).get("freshness_hours") or 0)
    accepted_raw: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for item in items:
        verdict = relevance_verdict(item, profile)
        if not verdict["accepted"]:
            rejected.append({
                "source_id": item.source_id,
                "title": item.title,
                "url": item.url,
                "reason": verdict["reason"],
                "detail": verdict["detail"],
            })
            continue
        if window_hours and item.published_at and not within_window(
                item.published_at, window_hours):
            from ..hotspots.adapters import freshness_hours_since
            age = freshness_hours_since(item.published_at)
            rejected.append({
                "source_id": item.source_id,
                "title": item.title,
                "url": item.url,
                "reason": "OUTSIDE_FRESHNESS_WINDOW",
                "detail": f"published {age:.0f} h ago, outside the "
                          f"{window_hours:.0f} h window",
            })
            continue
        accepted_raw.append({
            "source_id": item.source_id,
            "title": item.title,
            "url": item.url,
            "published_at": item.published_at,
            "snippet": item.snippet,
            "metrics": dict(item.metrics),
            "extra": dict(item.extra),
            "source_rank": item.rank,
        })

    # De-duplication happens before scoring, so each candidate is scored once
    # with the cross-source count it actually earned. Scoring first and
    # correcting afterwards would leave the reasons out of step with the
    # score they explain.
    merged = dedupe(accepted_raw)

    accepted: List[Dict[str, Any]] = []
    for record in merged:
        item = RawItem(source_id=str(record.get("source_id") or ""),
                       title=str(record.get("title") or ""),
                       url=str(record.get("url") or ""),
                       published_at=record.get("published_at"),
                       rank=record.get("source_rank"),
                       snippet=str(record.get("snippet") or ""),
                       metrics=dict(record.get("metrics") or {}),
                       extra=dict(record.get("extra") or {}))
        count = distinct_sources(record)
        pillar = profile.pillar_for(f"{item.title} {item.snippet}")
        prior = prior_appearances(item.title) if prior_appearances else 0
        full = build_candidate(item, profile, collected_at=collected_at,
                               pillar=pillar, prior_appearances=prior,
                               window_hours=window_hours,
                               distinct_sources=count,
                               also_seen_in=list(record.get("also_seen_in") or []))
        full["candidate_id"] = candidate_id_for(profile, full)
        full["plan_id"] = plan.get("plan_id")
        full["status"] = "candidate"
        full["sources"] = _sources_for(record, merged)
        accepted.append(full)

    ranked = rank_candidates(accepted)
    return CollectionResult(plan=plan, items=items, candidates=ranked,
                            fetch_results=fetch_results, rejected=rejected,
                            collected_at=collected_at)


def candidate_id_for(profile: AccountProfile, record: Dict[str, Any]) -> str:
    """A stable id for a candidate, derived from the account and the title.

    The account is part of the key, so two accounts that surface the same
    story get different ids and neither can select the other's candidate. The
    profile version is deliberately *not* part of it: a candidate keeps its
    identity when the account's profile is revised, so a run started before
    the edit and one started after it can be compared.
    """
    from ..hotspots.dedup import title_key
    payload = {
        "account": profile.account_id,
        "title": title_key(str(record.get("title") or "")),
        "url": str(record.get("url") or ""),
    }
    return f"CAND-{digest(payload)[:16].upper()}"


def _source_from_registry(source_id: str):
    from ..hotspots.source_registry import SOURCES
    return SOURCES.get(source_id)


def _sources_for(record: Dict[str, Any], pool: List[Dict[str, Any]]
                 ) -> List[Dict[str, Any]]:
    """Every source that carried this story, for the cross-source signal."""
    sources: List[Dict[str, Any]] = []
    for item in pool:
        if same_story(item, record):
            sources.append({
                "source_id": item.get("source_id"),
                "url": item.get("url"),
                "published_at": item.get("published_at"),
                "rank": item.get("source_rank"),
            })
    if not sources:
        sources.append({
            "source_id": record.get("source_id"),
            "url": record.get("url"),
            "published_at": record.get("published_at"),
            "rank": record.get("source_rank"),
        })
    unique: List[Dict[str, Any]] = []
    seen: set = set()
    for entry in sources:
        key = str(entry.get("source_id"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
    return unique


def native_query_sources(plan: Dict[str, Any]) -> List[str]:
    """The sources in a plan that were asked a real question."""
    return [str(entry.get("source_id")) for entry in (plan.get("sources") or [])
            if entry.get("query_mode") == NATIVE_SEARCH]


def list_only_sources(plan: Dict[str, Any]) -> List[str]:
    """The sources in a plan that were read as a list and filtered locally."""
    return [str(entry.get("source_id")) for entry in (plan.get("sources") or [])
            if entry.get("query_mode") != NATIVE_SEARCH]
