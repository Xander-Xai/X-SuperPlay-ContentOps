"""Hot-list collection: sources, plans, adapters, ranking and storage.

The pieces, in the order a run uses them:

- :mod:`source_registry` — what sources exist and what each can actually do.
- :mod:`query_planner` — the account's profile turned into a written plan.
- :mod:`adapters` — how to read each source, and how to fail by name.
- :mod:`dedup` — collapsing one story seen in two places.
- :mod:`ranking` — the account-weighted score and the reasons behind it.
- :mod:`storage` — the per-account candidate pool and the run record.

Nothing here chooses a topic. It collects, filters and ranks; the choice is
a person's, and it is made in :mod:`contentops.routing.router`.
"""

from .adapters import FetchError, FetchResult, RawItem
from .dedup import dedupe, distinct_sources, same_story
from .query_planner import build_search_plan, plan_is_current
from .ranking import build_candidate, rank_candidates, relevance_verdict, score_item
from .source_registry import (
    LIST_ONLY,
    NATIVE_SEARCH,
    SOURCES,
    Source,
    get_source,
    resolve_sources,
    supports_native_query,
)
from .storage import RouterStore, StorageError

__all__ = [
    "FetchError",
    "FetchResult",
    "LIST_ONLY",
    "NATIVE_SEARCH",
    "RawItem",
    "RouterStore",
    "SOURCES",
    "Source",
    "StorageError",
    "build_candidate",
    "build_search_plan",
    "dedupe",
    "distinct_sources",
    "get_source",
    "plan_is_current",
    "rank_candidates",
    "relevance_verdict",
    "resolve_sources",
    "same_story",
    "score_item",
    "supports_native_query",
]
