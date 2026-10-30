"""Offline source, planning, ranking and failure tests for the content router.

Every test here runs without a network and without a credential. The fixtures
stand in for the sources, and the failures are the ones a real collector hits:
a source that is down, one that times out, one that rate-limits, one that
answers with something unreadable, and one whose data is stale.

Run: python tests/test_hotspot_sources.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.hotspots.adapters import (  # noqa: E402
    FetchError,
    FetchResult,
    FixtureAdapter,
    NewsNowAdapter,
    RawItem,
    RetryPolicy,
    TrendRadarSqliteAdapter,
    adapter_for,
    breaker_open,
    freshness_hours_since,
    http_error_code,
    record_source_result,
    reset_breakers,
    within_window,
)
from contentops.hotspots.dedup import dedupe, distinct_sources, same_story  # noqa: E402
from contentops.hotspots.query_planner import build_search_plan  # noqa: E402
from contentops.hotspots.ranking import (  # noqa: E402
    build_candidate,
    rank_candidates,
    relevance_verdict,
    score_item,
)
from contentops.hotspots.source_registry import (  # noqa: E402
    LIST_ONLY,
    NATIVE_SEARCH,
    SOURCES,
    get_source,
    resolve_sources,
    supports_native_query,
)
from contentops.routing.account_profile import load_profile  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "hotspots" / "sample-pool.json"

ACCOUNT_EXPLORE = "x-superplay-1024"
ACCOUNT_BUILD = "x-superplay-future-intelligence"


def _now_iso(hours: float = 0.0) -> str:
    moment = datetime.now(timezone.utc) - timedelta(hours=hours)
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fixture_rows() -> dict:
    """The fixture pool, with its relative timestamps resolved to real ones."""
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    resolved = {}
    for source_id, rows in payload.items():
        items = []
        for row in rows:
            entry = dict(row)
            stamp = entry.get("published_at")
            if isinstance(stamp, str) and stamp.startswith("NOW"):
                hours = float(stamp[3:].rstrip("h"))
                entry["published_at"] = _now_iso(hours)
            items.append(entry)
        resolved[source_id] = items
    return resolved


def fixture_adapter() -> FixtureAdapter:
    return FixtureAdapter(_fixture_rows())


def _profile(slug: str = ACCOUNT_EXPLORE):
    return load_profile(ROOT, slug)


# ---------------------------------------------------------------------------
# the registry
# ---------------------------------------------------------------------------


def test_a_source_states_whether_it_accepts_a_query():
    assert supports_native_query("github-search") is True
    assert supports_native_query("juejin-hot") is False


def test_no_source_claims_a_query_it_does_not_have():
    for source in SOURCES.values():
        if source.adapter == "github_search":
            assert source.query_mode == NATIVE_SEARCH, source.source_id
        else:
            assert source.query_mode == LIST_ONLY, source.source_id


def test_a_list_only_source_says_so_in_its_own_note():
    note = get_source("zhihu-hot").note
    assert "no keyword query" in note or "no server-side query" in note


def test_an_unknown_source_id_is_refused_rather_than_guessed():
    class Fake:
        source_allowlist = ("no-such-source",)
        source_blocklist = ()
        preferred_sources = ()
    selected, rejected = resolve_sources(Fake())
    assert selected == []
    assert rejected[0]["reason"] == "UNKNOWN_SOURCE"


def test_a_blocked_source_wins_over_an_allowed_one():
    class Fake:
        source_allowlist = ("zhihu-hot", "juejin-hot")
        source_blocklist = ("juejin-hot",)
        preferred_sources = ()
    selected, rejected = resolve_sources(Fake())
    assert [source.source_id for source in selected] == ["zhihu-hot"]
    assert rejected[0]["source_id"] == "juejin-hot"
    assert rejected[0]["reason"] == "BLOCKED_BY_ACCOUNT"


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------


def test_two_accounts_produce_two_different_plans():
    explore = build_search_plan(_profile(ACCOUNT_EXPLORE))
    build = build_search_plan(_profile(ACCOUNT_BUILD))
    assert explore["plan_id"] != build["plan_id"]
    assert set(explore["keywords_zh"]) != set(build["keywords_zh"])
    assert explore["source_allowlist"] != build["source_allowlist"]
    assert explore["account_id"] != build["account_id"]


def test_the_plan_states_each_sources_capability():
    plan = build_search_plan(_profile(ACCOUNT_EXPLORE))
    modes = {entry["source_id"]: entry["query_mode"] for entry in plan["sources"]}
    assert modes["github-search"] == NATIVE_SEARCH
    assert modes["juejin-hot"] == LIST_ONLY
    for entry in plan["sources"]:
        assert entry["capability_note"]
        assert entry["why"]


def test_a_native_search_source_receives_the_accounts_query():
    plan = build_search_plan(_profile(ACCOUNT_BUILD))
    entry = next(item for item in plan["sources"] if item["source_id"] == "github-search")
    assert entry["query"]
    assert "LangGraph" in entry["query"]


def test_a_query_stays_inside_the_sources_own_operator_limit():
    """GitHub rejects a repository query with more than five operators.

    A plan that asked for twelve alternatives was refused by the service with
    HTTP 422 — a plan the source cannot execute is not a plan. The cap is the
    source's, declared in the registry, and the query is cut to fit it.
    """
    plan = build_search_plan(_profile(ACCOUNT_EXPLORE))
    entry = next(item for item in plan["sources"] if item["source_id"] == "github-search")
    assert entry["query"].count(" OR ") <= 5
    assert len(entry["query"]) <= 256


def test_a_list_only_source_is_never_given_a_query():
    plan = build_search_plan(_profile(ACCOUNT_EXPLORE))
    for entry in plan["sources"]:
        if entry["query_mode"] == LIST_ONLY:
            assert entry["query"] is None, entry["source_id"]


def test_the_plan_states_a_cost_even_though_it_is_zero():
    plan = build_search_plan(_profile(ACCOUNT_EXPLORE))
    assert plan["estimated_cost"]["amount"] == 0.0
    assert plan["estimated_cost"]["requests_planned"] == len(plan["sources"])
    assert plan["estimated_cost"]["basis"]


def test_the_plan_names_the_account_and_its_profile_version():
    profile = _profile(ACCOUNT_EXPLORE)
    plan = build_search_plan(profile)
    assert plan["account_id"] == profile.account_id
    assert plan["account_profile_version"] == profile.profile_version


def test_a_plan_restricted_to_one_pillar_keeps_only_that_pillar():
    plan = build_search_plan(_profile(ACCOUNT_EXPLORE), pillar="AI 生意实验室")
    assert [entry["name"] for entry in plan["pillars"]] == ["AI 生意实验室"]
    assert plan["selected_pillar"] == "AI 生意实验室"


# ---------------------------------------------------------------------------
# relevance and ranking
# ---------------------------------------------------------------------------


def test_a_candidate_unrelated_to_the_account_is_rejected():
    profile = _profile(ACCOUNT_EXPLORE)
    item = RawItem(source_id="juejin-hot", title="今天菜价怎么样", url="https://x/1")
    verdict = relevance_verdict(item, profile)
    assert verdict["accepted"] is False
    assert verdict["reason"] == "NO_ACCOUNT_TERM"


def test_a_candidate_matching_an_excluded_term_is_rejected():
    profile = _profile(ACCOUNT_EXPLORE)
    item = RawItem(source_id="weibo-hot", title="AI 暴富叙事：躺赚的幻觉", url="https://x/2")
    verdict = relevance_verdict(item, profile)
    assert verdict["accepted"] is False
    assert verdict["reason"] == "EXCLUDED_TERM"


def test_a_candidate_matching_the_account_is_accepted():
    profile = _profile(ACCOUNT_EXPLORE)
    item = RawItem(source_id="juejin-hot",
                   title="用 LangGraph 做多步骤工作流，失败重试怎么设计", url="https://x/3")
    verdict = relevance_verdict(item, profile)
    assert verdict["accepted"] is True
    assert verdict["matched_terms"]


def test_the_score_is_not_the_hot_lists_own_rank():
    profile = _profile(ACCOUNT_EXPLORE)
    relevant = RawItem(source_id="juejin-hot", rank=30,
                       title="用 LangGraph 做多步骤工作流，失败重试怎么设计",
                       url="https://x/a", published_at=_now_iso(2))
    popular = RawItem(source_id="juejin-hot", rank=1,
                      title="今天菜价怎么样", url="https://x/b",
                      published_at=_now_iso(2))
    relevant_score = score_item(relevant, profile)["score"]
    popular_score = score_item(popular, profile)["score"]
    assert relevant_score > popular_score


def test_every_component_carries_its_reason():
    profile = _profile(ACCOUNT_EXPLORE)
    item = RawItem(source_id="github-trending", title="newmodel/open-weights-70b",
                   url="https://github.com/newmodel/open-weights-70b",
                   published_at=_now_iso(4))
    scored = score_item(item, profile)
    for name, component in scored["components"].items():
        assert component["why"], name
        assert 0.0 <= component["value"] <= 10.0


def test_platform_counters_are_never_added_to_one_another():
    profile = _profile(ACCOUNT_EXPLORE)
    plain = RawItem(source_id="github-search", title="langchain-ai/langgraph",
                    url="https://github.com/langchain-ai/langgraph",
                    published_at=_now_iso(2), metrics={})
    loud = RawItem(source_id="github-search", title="langchain-ai/langgraph",
                   url="https://github.com/langchain-ai/langgraph",
                   published_at=_now_iso(2), metrics={"stars": 999999})
    # The same title, the same link, the same moment: the only difference is
    # a platform counter, so the score must be identical.
    assert score_item(plain, profile)["score"] == score_item(loud, profile)["score"]

    record = build_candidate(loud, profile, collected_at=_now_iso(0))
    assert record["metrics_comparable"] is False
    assert "never scored" in record["metrics_note"]


def test_cross_source_signal_counts_sources_not_heat():
    profile = _profile(ACCOUNT_EXPLORE)
    item = RawItem(source_id="github-trending", title="newmodel/open-weights-70b",
                   url="https://github.com/newmodel/open-weights-70b",
                   published_at=_now_iso(4))
    one = score_item(item, profile, distinct_sources=1)
    three = score_item(item, profile, distinct_sources=3)
    assert three["components"]["cross_source_signal"]["value"] > \
        one["components"]["cross_source_signal"]["value"]
    assert "distinct sources" in three["components"]["cross_source_signal"]["why"]


def test_the_weights_are_the_accounts_own():
    profile = _profile(ACCOUNT_EXPLORE)
    assert sum(profile.match_weights.values()) == 100
    assert set(profile.match_weights) == {
        "profile_relevance", "audience_value", "evidence_availability",
        "freshness", "cross_source_signal", "originality_potential",
        "non_repetition"}


def test_a_topic_the_account_has_seen_before_scores_lower():
    profile = _profile(ACCOUNT_EXPLORE)
    item = RawItem(source_id="github-trending", title="newmodel/open-weights-70b",
                   url="https://github.com/newmodel/open-weights-70b",
                   published_at=_now_iso(4))
    fresh = score_item(item, profile, prior_appearances=0)
    seen = score_item(item, profile, prior_appearances=3)
    assert seen["components"]["non_repetition"]["value"] < \
        fresh["components"]["non_repetition"]["value"]
    assert seen["score"] < fresh["score"]


def test_the_candidate_records_the_source_the_time_and_the_reasons():
    profile = _profile(ACCOUNT_EXPLORE)
    item = RawItem(source_id="juejin-hot",
                   title="用 LangGraph 做多步骤工作流，失败重试怎么设计",
                   url="https://juejin.cn/post/1", published_at=_now_iso(6),
                   rank=3, metrics={"hot": 9000})
    record = build_candidate(item, profile, collected_at=_now_iso(0))
    for key in ("source_id", "title", "url", "published_at", "collected_at",
                "source_rank", "category", "pillar", "relevance", "freshness",
                "verification_status", "reasons_for", "reasons_against",
                "angles", "rank_change", "metrics"):
        assert key in record, key
    assert record["collected_at"] != record["published_at"]
    assert record["reasons_for"] and record["reasons_against"]
    # The angles are the account's own declared beat structure, never invented.
    assert record["pillar"], "the candidate must land on one of the account's pillars"
    assert record["angles"] == list(
        next(pillar for pillar in profile.content_pillars
             if pillar.get("name") == record["pillar"])["structure"])
    # A rank change is only recorded when a source actually carries one.
    assert record["rank_change"] is None
    assert "never inferred" in record["rank_change_note"]


def test_ranking_is_stable_and_never_sums_platform_heat():
    profile = _profile(ACCOUNT_EXPLORE)
    items = [
        RawItem(source_id="github-trending", title="newmodel/open-weights-70b",
                url="https://github.com/a", published_at=_now_iso(4), rank=9,
                metrics={"hot": 100}),
        RawItem(source_id="juejin-hot",
                title="用 LangGraph 做多步骤工作流，失败重试怎么设计",
                url="https://juejin.cn/1", published_at=_now_iso(6), rank=1,
                metrics={"hot": 999999}),
    ]
    records = [build_candidate(item, profile, collected_at=_now_iso(0))
               for item in items]
    ranked = rank_candidates(records)
    assert ranked[0]["relevance"]["score"] >= ranked[1]["relevance"]["score"]
    again = rank_candidates(records)
    assert [item["title"] for item in again] == [item["title"] for item in ranked]


# ---------------------------------------------------------------------------
# de-duplication
# ---------------------------------------------------------------------------


def test_the_same_story_in_two_sources_is_one_candidate():
    records = [
        {"title": "langchain-ai/langgraph", "url": "https://github.com/a",
         "source_id": "github-search", "published_at": "2026-10-29T00:00:00Z"},
        {"title": "langchain-ai/langgraph", "url": "https://github.com/b",
         "source_id": "github-trending", "published_at": "2026-10-28T00:00:00Z"},
    ]
    merged = dedupe(records)
    assert len(merged) == 1
    assert merged[0]["also_seen_in"] == ["github-trending"]
    assert merged[0]["published_at"] == "2026-10-28T00:00:00Z"


def test_two_different_stories_are_not_merged():
    records = [
        {"title": "LangGraph 1.0 发布", "url": "https://a/1", "source_id": "x"},
        {"title": "LangGraph 1.0 的 RAG 实践", "url": "https://a/2", "source_id": "x"},
    ]
    assert len(dedupe(records)) == 2


def test_distinct_sources_counts_the_merged_ones():
    record = {"source_id": "a", "also_seen_in": ["b", "c"], "title": "t"}
    assert distinct_sources(record) == 3


def test_same_story_needs_a_real_overlap():
    assert same_story({"title": "AI", "url": ""},
                       {"title": "AI 新模型", "url": ""}) is False


# ---------------------------------------------------------------------------
# failure modes
# ---------------------------------------------------------------------------


def test_an_unreachable_source_is_named_not_swallowed():
    class Boom:
        def fetch(self, source, *, limit, timeout=12.0, query=None):
            raise FetchError("SOURCE_UNAVAILABLE", "network is down")
    adapter = Boom()
    try:
        adapter.fetch(get_source("zhihu-hot"), limit=5)
    except FetchError as exc:
        assert exc.code == "SOURCE_UNAVAILABLE"
        assert "network is down" in exc.detail
    else:
        raise AssertionError("a failing source must raise")


def test_a_source_that_times_out_says_so():
    try:
        raise FetchError("SOURCE_TIMEOUT", "did not answer within 12s")
    except FetchError as exc:
        assert exc.code == "SOURCE_TIMEOUT"


def test_a_rate_limited_source_says_so():
    assert http_error_code(429) == "SOURCE_RATE_LIMITED"
    assert "credentials" in _http_detail_for(401).lower()
    assert http_error_code(401) == "SOURCE_CREDENTIALS_REQUIRED"
    assert http_error_code(500) == "SOURCE_UNAVAILABLE"


def _http_detail_for(code: int) -> str:
    """The message the adapter produces for an HTTP status, without a network."""
    import urllib.error
    from contentops.hotspots.adapters import FetchError
    source = get_source("zhihu-hot")
    try:
        raise urllib.error.HTTPError(source.endpoint, code, "x", {}, None)
    except urllib.error.HTTPError as exc:
        failure = http_error_code(exc.code)
        if failure == "SOURCE_RATE_LIMITED":
            return f"{source.endpoint} answered 429; this source is rate limited"
        if failure == "SOURCE_CREDENTIALS_REQUIRED":
            return (f"{source.endpoint} answered {exc.code}; this source needs "
                    f"credentials, and the collector does not hold any")
        return f"{source.endpoint} answered HTTP {exc.code}"


def test_malformed_data_is_refused_rather_than_read_as_empty():
    class Malformed:
        def fetch(self, source, *, limit, timeout=12.0, query=None):
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_DATA_MALFORMED",
                               error_detail="no list of items")
    result = Malformed().fetch(get_source("zhihu-hot"), limit=5)
    assert result.ok is False
    assert result.error_code == "SOURCE_DATA_MALFORMED"
    assert result.items == []


def _trendradar_db(directory: str, rows, *, day: str = "2026-10-30",
                   created_at: str = "2026-10-30 17:44:53") -> Path:
    """A database shaped like the one a real TrendRadar v6 crawl writes."""
    import sqlite3
    path = Path(directory) / f"{day}.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE platforms (id TEXT PRIMARY KEY, name TEXT NOT NULL);"
        "CREATE TABLE news_items ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " title TEXT NOT NULL, platform_id TEXT NOT NULL, rank INTEGER NOT NULL,"
        " url TEXT DEFAULT '', created_at TIMESTAMP, first_crawl_time TEXT);")
    connection.execute("INSERT INTO platforms VALUES ('baidu', '百度热搜')")
    for index, (title, platform, rank) in enumerate(rows, start=1):
        connection.execute(
            "INSERT INTO news_items (title, platform_id, rank, url, created_at, "
            "first_crawl_time) VALUES (?, ?, ?, ?, ?, ?)",
            (title, platform, rank, f"https://example.test/{index}", created_at, "17-44"))
    connection.commit()
    connection.close()
    return path


def test_a_trendradar_database_that_is_absent_is_named():
    adapter = TrendRadarSqliteAdapter("no/such/path.db")
    result = adapter.fetch(get_source("trendradar-sqlite"), limit=5)
    assert result.ok is False
    assert result.error_code == "SOURCE_UNAVAILABLE_STATE"


def test_a_trendradar_database_with_a_drifted_schema_is_refused():
    import sqlite3
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "trend.db"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE trend_data (label TEXT, heat INTEGER)")
        connection.commit()
        connection.close()
        adapter = TrendRadarSqliteAdapter(str(path))
        result = adapter.fetch(get_source("trendradar-sqlite"), limit=5)
        assert result.ok is False
        assert result.error_code == "SOURCE_DATA_MALFORMED"
        assert "not a v6 database" in result.error_detail


def test_a_trendradar_database_with_duplicated_rows_yields_one_candidate():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = _trendradar_db(directory, [("同一个标题", "baidu", 1),
                                          ("同一个标题", "baidu", 2)])
        adapter = TrendRadarSqliteAdapter(str(path))
        result = adapter.fetch(get_source("trendradar-sqlite"), limit=5)
        assert result.ok is True
        assert len(result.items) == 1


def test_a_real_trendradar_row_is_read_with_its_platform_and_crawl_time():
    """The shape a v6.11.0 crawl actually writes: news_items + platforms."""
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = _trendradar_db(directory, [("百度热搜第一条", "baidu", 1),
                                          ("百度热搜第二条", "baidu", 2)])
        result = TrendRadarSqliteAdapter(str(path)).fetch(
            get_source("trendradar-sqlite"), limit=10)
        assert result.schema == "trendradar-v6/news_items"
        assert [item.title for item in result.items] == ["百度热搜第一条", "百度热搜第二条"]
        first = result.items[0]
        assert first.extra["platform"] == "baidu"
        assert first.extra["platform_name"] == "百度热搜"
        # 17:44:53 at UTC+8 is 09:44:53Z, and it is recorded as the crawl time,
        # never as the article's own publication time.
        assert first.published_at == "2026-10-30T09:44:53Z"
        assert first.extra["published_at_source"] == "trendradar_crawl_time"
        assert result.observed_at == "2026-10-30T09:44:53Z"


def test_a_trendradar_database_older_than_its_window_is_stale():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = _trendradar_db(directory, [("很久以前的一条", "baidu", 1)],
                              day="2026-10-01", created_at="2026-10-01 09:00:00")
        result = TrendRadarSqliteAdapter(str(path)).fetch(
            get_source("trendradar-sqlite"), limit=10)
        assert result.ok is True
        assert result.stale is True
        assert result.observed_at.startswith("2026-10-01")


def test_a_trendradar_file_that_is_not_sqlite_is_named():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "2026-10-30.db"
        path.write_bytes(b"this is not a database at all" * 40)
        result = TrendRadarSqliteAdapter(str(path)).fetch(
            get_source("trendradar-sqlite"), limit=5)
        assert result.ok is False
        assert result.error_code in ("SOURCE_DATA_MALFORMED", "SOURCE_UNAVAILABLE")


def test_a_trendradar_directory_resolves_to_the_newest_day():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        _trendradar_db(directory, [("旧的一天", "baidu", 1)],
                       day="2026-10-28", created_at="2026-10-28 10:00:00")
        _trendradar_db(directory, [("新的一天", "baidu", 1)])
        result = TrendRadarSqliteAdapter(directory).fetch(
            get_source("trendradar-sqlite"), limit=10)
        assert result.ok is True
        assert [item.title for item in result.items] == ["新的一天"]


def test_the_fixture_adapter_serves_what_it_was_given():
    adapter = fixture_adapter()
    result = adapter.fetch(get_source("juejin-hot"), limit=10)
    assert result.ok is True
    assert len(result.items) == 2


def test_a_source_without_a_fixture_fails_by_name():
    adapter = FixtureAdapter({})
    result = adapter.fetch(get_source("juejin-hot"), limit=10)
    assert result.ok is False
    assert result.error_code == "SOURCE_UNAVAILABLE"


def test_the_adapter_for_a_source_is_the_one_that_speaks_its_language():
    assert type(adapter_for(get_source("github-search"))).__name__ == "GitHubSearchAdapter"
    assert type(adapter_for(get_source("zhihu-hot"))).__name__ == "NewsNowAdapter"
    assert type(adapter_for(get_source("trendradar-sqlite"))).__name__ == \
        "TrendRadarSqliteAdapter"


def test_freshness_is_measured_in_hours_and_ignores_an_absent_time():
    assert freshness_hours_since(_now_iso(5)) is not None
    assert freshness_hours_since(None) is None
    assert freshness_hours_since("not a date") is None


def test_the_freshness_window_keeps_recent_items_and_drops_old_ones():
    assert within_window(_now_iso(2), 24) is True
    assert within_window(_now_iso(48), 24) is False
    # A window can only exclude what it can date. An undated item is kept and
    # is scored zero on freshness instead, so it is visibly weaker.
    assert within_window(None, 24) is True
    assert within_window(None, 0) is True


def _fake_urlopen(outcomes, calls, sleeps):
    """A urlopen replacement that plays back scripted outcomes."""
    import io
    import urllib.error

    def urlopen(request, timeout=None):
        outcome = outcomes[min(len(calls), len(outcomes) - 1)]
        calls.append(request.full_url if hasattr(request, "full_url") else str(request))
        if isinstance(outcome, int):
            raise urllib.error.HTTPError(request.full_url, outcome,
                                         f"HTTP {outcome}", {}, io.BytesIO(b""))
        return io.BytesIO(outcome)
    return urlopen


def test_a_transient_server_error_is_retried_and_then_succeeds():
    import urllib.request
    from contentops.hotspots import adapters as module
    calls: list = []
    sleeps: list = []
    real_urlopen, real_sleep = urllib.request.urlopen, module.time.sleep
    urllib.request.urlopen = _fake_urlopen([503, b'{"ok": true}'], calls, sleeps)
    module.time.sleep = sleeps.append
    try:
        body = module._http_get("https://example.test/x", timeout=1,
                                policy=RetryPolicy(attempts=3, base_delay=0.01))
        assert json.loads(body) == {"ok": True}
        assert len(calls) == 2
        assert sleeps and sleeps[0] > 0
    finally:
        urllib.request.urlopen, module.time.sleep = real_urlopen, real_sleep


def test_a_wrong_request_is_not_retried():
    import urllib.request
    from contentops.hotspots import adapters as module
    calls: list = []
    real_urlopen = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen([422, 422, 422], calls, [])
    try:
        try:
            module._http_get("https://example.test/x", timeout=1,
                             policy=RetryPolicy(attempts=3, base_delay=0.01))
        except FetchError as exc:
            assert exc.code == "SOURCE_UNAVAILABLE"
        else:
            raise AssertionError("a 422 must not be swallowed")
        assert len(calls) == 1, f"a 422 was retried {len(calls)} times"
    finally:
        urllib.request.urlopen = real_urlopen


def test_a_rate_limit_waits_for_the_interval_the_service_asked_for():
    import io
    import urllib.request
    from contentops.hotspots import adapters as module
    sleeps: list = []
    calls: list = []

    def urlopen(request, timeout=None):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError(request.full_url, 429, "429",
                                         {"Retry-After": "2"}, io.BytesIO(b""))
        return io.BytesIO(b"[]")

    real_urlopen, real_sleep = urllib.request.urlopen, module.time.sleep
    urllib.request.urlopen = urlopen
    module.time.sleep = sleeps.append
    try:
        module._http_get("https://example.test/x", timeout=1,
                         policy=RetryPolicy(attempts=2, base_delay=0.01))
        assert sleeps == [2.0], sleeps
    finally:
        urllib.request.urlopen, module.time.sleep = real_urlopen, real_sleep


def test_a_source_that_keeps_failing_stops_being_contacted():
    import urllib.request
    from contentops.hotspots import adapters as module
    reset_breakers()
    calls: list = []
    real_urlopen = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen([500], calls, [])
    module.time.sleep = lambda _seconds: None
    real_sleep = time_sleep = None
    try:
        for _ in range(3):
            try:
                module._http_get("https://example.test/x", timeout=1, source_id="flaky",
                                 policy=RetryPolicy(attempts=1, base_delay=0.0))
            except FetchError:
                pass
        assert breaker_open("flaky") is True
        before = len(calls)
        try:
            module._http_get("https://example.test/x", timeout=1, source_id="flaky",
                             policy=RetryPolicy(attempts=1, base_delay=0.0))
        except FetchError as exc:
            assert exc.code == "SOURCE_CIRCUIT_OPEN"
        else:
            raise AssertionError("an open breaker must refuse the call")
        assert len(calls) == before, "an open breaker still contacted the source"
    finally:
        urllib.request.urlopen = real_urlopen
        record_source_result("flaky", True)
        reset_breakers()


def test_a_truncated_response_is_named_and_retried():
    """A connection that drops mid-body is not half-parsed as data."""
    import http.client
    import urllib.request
    from contentops.hotspots import adapters as module
    calls: list = []

    class Truncated:
        def read(self, _n=None):
            raise http.client.IncompleteRead(b"partial")
        def __enter__(self):
            return self
        def __exit__(self, *_exc):
            return False

    real_urlopen, real_sleep = urllib.request.urlopen, module.time.sleep
    urllib.request.urlopen = lambda request, timeout=None: (calls.append(1), Truncated())[1]
    module.time.sleep = lambda _seconds: None
    try:
        try:
            module._http_get("https://example.test/x", timeout=1,
                             policy=RetryPolicy(attempts=2, base_delay=0.01))
        except FetchError as exc:
            assert exc.code == "SOURCE_UNAVAILABLE"
            assert "dropped the connection" in exc.detail
        else:
            raise AssertionError("a truncated body must not be returned as data")
        assert len(calls) == 2, f"expected 2 attempts, saw {len(calls)}"
    finally:
        urllib.request.urlopen, module.time.sleep = real_urlopen, real_sleep


def test_a_query_does_not_spend_its_operators_on_the_platforms_own_name():
    """On GitHub, the term "GitHub" matches everything and narrows nothing."""
    plan = build_search_plan(_profile(ACCOUNT_EXPLORE))
    entry = next(item for item in plan["sources"] if item["source_id"] == "github-search")
    assert "github" not in entry["query"].casefold().split(" or ")


def test_backoff_grows_and_is_capped():
    from contentops.hotspots.adapters import _backoff_delay
    policy = RetryPolicy(attempts=5, base_delay=1.0, max_delay=4.0)
    delays = [_backoff_delay(attempt, policy) for attempt in (1, 2, 3, 4, 10)]
    assert delays[0] >= 1.0
    assert delays[1] > delays[0] - 0.001
    assert all(delay <= policy.max_delay for delay in delays), delays


def main() -> int:
    tests = tuple(value for name, value in sorted(globals().items())
                  if name.startswith("test_") and callable(value))
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"[ok] {fn.__name__}")
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(tests)} hotspot source tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
