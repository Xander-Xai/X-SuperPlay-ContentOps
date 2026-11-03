"""The catalog of sources the router may read, and what each of them can do.

Why this exists
---------------
Hot-list services look uniform from the outside — every one of them returns a
ranked list of titles — and that uniformity is what makes it easy to claim a
capability that does not exist. NewsNow and TrendRadar publish *pre-curated
lists*. They do not accept a keyword query and they do not return a relevance
score. Asking them for "my account's topics" is not a search; it is a
subscription to somebody else's editorial judgement, followed by a local
filter that happens to look like one.

So every source declares its own capability, and the registry says which
capability it has:

``NATIVE_SEARCH``
    The service accepts a query and returns ranked matches for *that* query.
    GitHub's search API is the one real example here. The account's keywords
    go into the request.

``LIST_ONLY``
    The service publishes a fixed list. The account's keywords cannot narrow
    it; they can only filter it afterwards. This is stated in the source's
    ``note`` and carried into the search plan, so a reader of the plan can
    see that the narrowing happened locally.

The difference is the difference between "we searched for this account's
topics" and "we read a popular list and kept what fit". Both are legitimate.
Only the first one may be called a search.

The allowlist is the account's, not the router's
-------------------------------------------------
An account that names no source collects nothing. A source that is not on the
allowlist is never contacted — not fetched and filtered afterwards, but not
contacted. That is the difference between a scoped collector and a broad one
that discards most of what it fetched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

#: The two capabilities a source may have. There is no third.
NATIVE_SEARCH = "NATIVE_SEARCH"
LIST_ONLY = "LIST_ONLY"

QUERY_MODES: Tuple[str, ...] = (NATIVE_SEARCH, LIST_ONLY)

#: The adapter that knows how to talk to a source.
NEWSNOW = "newsnow"
GITHUB_SEARCH = "github_search"
TRENDRADAR_SQLITE = "trendradar_sqlite"


@dataclass(frozen=True)
class Source:
    """One source the router may read, and the limits it carries."""

    source_id: str
    name: str
    adapter: str
    query_mode: str
    upstream_id: str
    endpoint: str
    platform: str
    language: Tuple[str, ...]
    max_items: int
    note: str
    #: What the source's items look like, so an adapter knows how to normalise.
    item_shape: str = "newsnow_items"
    #: How many alternatives a query may carry, when the service caps them.
    #: Zero means the router's own cap applies. GitHub rejects a repository
    #: query with more than five operators, so six OR'd terms is the ceiling
    #: there — learned from a real 422, and stated here so the planner cannot
    #: build a query the service will refuse.
    max_query_terms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "adapter": self.adapter,
            "query_mode": self.query_mode,
            "upstream_id": self.upstream_id,
            "endpoint": self.endpoint,
            "platform": self.platform,
            "language": list(self.language),
            "max_items": self.max_items,
            "max_query_terms": self.max_query_terms,
            "note": self.note,
        }


def _newsnow(source_id: str, name: str, upstream_id: str, platform: str,
             language: Tuple[str, ...], note: str, max_items: int = 60) -> Source:
    return Source(
        source_id=source_id,
        name=name,
        adapter=NEWSNOW,
        query_mode=LIST_ONLY,
        upstream_id=upstream_id,
        endpoint=f"https://newsnow.busiyi.world/api/s?id={upstream_id}",
        platform=platform,
        language=language,
        max_items=max_items,
        note=note,
    )


#: The catalog. A source that is not here cannot be contacted, however an
#: account's allowlist is written.
SOURCES: Dict[str, Source] = {
    source.source_id: source
    for source in (
        Source(
            source_id="github-search",
            name="GitHub repository search",
            adapter=GITHUB_SEARCH,
            query_mode=NATIVE_SEARCH,
            upstream_id="repositories",
            endpoint="https://api.github.com/search/repositories",
            platform="github",
            language=("en",),
            max_items=30,
            note="Accepts a server-side query, so the account's keywords narrow the "
                 "result at the source rather than after the fetch.",
            item_shape="github_repos",
            max_query_terms=6,
        ),
        _newsnow("github-trending", "GitHub Trending", "github-trending-today",
                 "github", ("en",),
                 "A curated trending list. GitHub offers no keyword query over it, "
                 "so account terms are applied locally after the fetch."),
        _newsnow("zhihu-hot", "知乎热榜", "zhihu-hot", "zhihu", ("zh",),
                 "A curated hot list with no server-side query; account terms are "
                 "applied locally after the fetch."),
        _newsnow("weibo-hot", "微博热搜", "weibo", "weibo", ("zh",),
                 "A curated hot list with no server-side query; account terms are "
                 "applied locally after the fetch."),
        _newsnow("baidu-hot", "百度热搜", "baidu", "baidu", ("zh",),
                 "A general-interest hot list with no server-side query; account "
                 "terms are applied locally after the fetch."),
        _newsnow("bilibili-hot", "哔哩哔哩热门", "bilibili", "bilibili", ("zh",),
                 "A curated hot list with no server-side query; account terms are "
                 "applied locally after the fetch."),
        _newsnow("douyin-hot", "抖音热点榜", "douyin-hot", "douyin", ("zh",),
                 "A curated hot list with no server-side query; account terms are "
                 "applied locally after the fetch."),
        _newsnow("juejin-hot", "掘金热榜", "juejin", "juejin", ("zh",),
                 "A curated hot list with no server-side query; account terms are "
                 "applied locally after the fetch."),
        _newsnow("v2ex-hot", "V2EX 热榜", "v2ex", "v2ex", ("zh",),
                 "A curated hot list with no server-side query; account terms are "
                 "applied locally after the fetch."),
        _newsnow("36kr-hot", "36氪热榜", "36kr", "36kr", ("zh",),
                 "A curated hot list with no server-side query; account terms are "
                 "applied locally after the fetch."),
        _newsnow("ithome", "IT之家", "ithome", "ithome", ("zh",),
                 "A curated hot list with no server-side query; account terms are "
                 "applied locally after the fetch."),
        _newsnow("hacker-news", "Hacker News", "hacker-news", "hackernews", ("en",),
                 "A curated hot list with no server-side query; account terms are "
                 "applied locally after the fetch."),
        _newsnow("producthunt", "Product Hunt", "producthunt", "producthunt", ("en",),
                 "A curated hot list with no server-side query; account terms are "
                 "applied locally after the fetch."),
        _newsnow("solidot", "奇客Solidot", "solidot", "solidot", ("zh",),
                 "A curated hot list with no server-side query; account terms are "
                 "applied locally after the fetch."),
        Source(
            source_id="trendradar-sqlite",
            name="TrendRadar local database",
            adapter=TRENDRADAR_SQLITE,
            query_mode=LIST_ONLY,
            upstream_id="trend_data",
            endpoint="file://<TRENDRADAR_DB_PATH>",
            platform="trendradar",
            language=("zh", "en"),
            max_items=80,
            note="Read-only access to a TrendRadar SQLite database. TrendRadar "
                 "serves pre-ranked lists, so account terms are applied locally. "
                 "The database is read with a URI in read-only mode and is never "
                 "written to.",
            item_shape="trendradar_rows",
        ),
    )
}


def get_source(source_id: str) -> Optional[Source]:
    return SOURCES.get(source_id)


def supports_native_query(source_id: str) -> bool:
    """Whether a source accepts a query rather than only publishing a list."""
    source = SOURCES.get(source_id)
    return bool(source and source.query_mode == NATIVE_SEARCH)


def all_sources() -> List[Source]:
    """Every source in the catalog, in a stable order."""
    return [SOURCES[key] for key in sorted(SOURCES)]


def resolve_sources(profile: Any) -> Tuple[List[Source], List[Dict[str, Any]]]:
    """The sources an account may contact, and why each rejection happened.

    The order of the rules is the point. A source is contacted only when the
    account put it on the allowlist *and* did not block it *and* it exists in
    this catalog. An unknown id is a rejection, not an error: a typo in an
    account's allowlist should narrow the collection, not crash it.

    A blocklist entry wins over an allowlist entry, because the blocklist is
    the account owner's "not this one" and the allowlist is their "these are
    candidates".
    """
    allowed = list(getattr(profile, "source_allowlist", ()) or ())
    blocked = set(getattr(profile, "source_blocklist", ()) or ())

    selected: List[Source] = []
    rejected: List[Dict[str, Any]] = []
    for source_id in allowed:
        if source_id in blocked:
            rejected.append({
                "source_id": source_id,
                "reason": "BLOCKED_BY_ACCOUNT",
                "detail": "the account lists this source on its blocklist",
            })
            continue
        source = SOURCES.get(source_id)
        if source is None:
            rejected.append({
                "source_id": source_id,
                "reason": "UNKNOWN_SOURCE",
                "detail": "no such source in the registry; nothing was contacted",
            })
            continue
        selected.append(source)

    for source_id in sorted(blocked):
        if source_id not in allowed:
            rejected.append({
                "source_id": source_id,
                "reason": "BLOCKED_NOT_REQUESTED",
                "detail": "the account blocks this source and did not request it",
            })

    # A preferred source keeps its place in the plan; the account's reason for
    # preferring it is looked up separately by `preferred_reason`.
    return selected, rejected


def preferred_reason(profile: Any, source_id: str) -> str:
    """Why the account prefers a source, if it said."""
    for entry in (getattr(profile, "preferred_sources", ()) or ()):
        if isinstance(entry, dict) and entry.get("source_id") == source_id:
            return str(entry.get("why") or "")
    return ""


def query_mode_note(source: Source) -> str:
    """The sentence a search plan carries when it names this source."""
    if source.query_mode == NATIVE_SEARCH:
        return (f"{source.source_id} accepts a server-side query, so the account's "
                f"keywords narrow the result at the source")
    return (f"{source.source_id} publishes a pre-ranked list and offers no keyword "
            f"query; the account's terms are applied locally after the fetch, so "
            f"this is a filtered list rather than a search")
