"""Router tests: the two entrances, the one contract, and the human gates.

Everything here runs offline. The account DNA is the repository's real one —
copied into a sandbox so a test can change it — and the sources are served
from a fixture, so no network and no credential is involved.

What is being checked, in the order the task states it:

- the account's positioning decides the search, and an account without one is
  refused rather than guessed at;
- the route is never inferred, and a run stays in the route it started in;
- the two routes produce the same contract, and both reach the same project;
- no candidate becomes a brief without a person choosing it, and no brief
  becomes production without a person approving it;
- two accounts share a database and share nothing else.

Run: python tests/test_content_router.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.hotspots.adapters import FetchResult, FixtureAdapter  # noqa: E402
from contentops.hotspots.storage import RouterStore  # noqa: E402
from contentops.routing import hotspot_route  # noqa: E402
from contentops.routing.brief import validate_brief_package  # noqa: E402
from contentops.routing.models import (  # noqa: E402
    APPROVED_FOR_PRODUCTION,
    AWAITING_HUMAN_APPROVAL,
    CANDIDATES_READY,
    OUT_OF_PROFILE_REVIEW_REQUIRED,
    ROUTE_SELECTION_REQUIRED,
    RoutingError,
    can_transition,
)
from contentops.routing.router import ContentRouter  # noqa: E402
from contentops.routing.user_topic_route import UserTopicInput  # noqa: E402

ACCOUNT_EXPLORE = "x-superplay-1024"
ACCOUNT_BUILD = "x-superplay-future-intelligence"
FIXTURES = ROOT / "tests" / "fixtures" / "hotspots" / "sample-pool.json"


def _expect(code: str, fn):
    try:
        fn()
    except RoutingError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc.detail}"
        return
    raise AssertionError(f"expected RoutingError {code}, nothing was raised")


def _sandbox(tmp: str, slugs=(ACCOUNT_EXPLORE, ACCOUNT_BUILD)) -> Path:
    """A repository-shaped sandbox holding the real account DNA."""
    root = Path(tmp) / "repo"
    accounts = root / "config" / "accounts"
    accounts.mkdir(parents=True)
    for slug in slugs:
        shutil.copy(ROOT / "config" / "accounts" / f"{slug}.json",
                    accounts / f"{slug}.json")
    return root


def _fixture_adapter() -> FixtureAdapter:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    resolved = {}
    now = datetime.now(timezone.utc)
    for source_id, rows in payload.items():
        items = []
        for row in rows:
            entry = dict(row)
            stamp = entry.get("published_at")
            if isinstance(stamp, str) and stamp.startswith("NOW"):
                # "NOW-10h" reads as ten hours before now.
                hours = float(stamp[3:].rstrip("h"))
                moment = now.replace(microsecond=0) + timedelta(hours=hours)
                entry["published_at"] = moment.isoformat().replace("+00:00", "Z")
            items.append(entry)
        resolved[source_id] = items
    return FixtureAdapter(resolved)


def _router(root: Path, adapters=None) -> ContentRouter:
    store = RouterStore(root, home=root / "state")
    if adapters is not None and not hasattr(adapters, "get"):
        # The router reads its override as a source-id map. A single adapter
        # that answers for every source is wrapped so both shapes work.
        adapters = _Adapters(adapters)
    return ContentRouter(root, store=store, adapters=adapters)


class _Spy:
    """An adapter that records what it was asked for."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def fetch(self, source, *, limit, timeout=12.0, query=None):
        self.calls.append({"source_id": source.source_id, "query": query, "limit": limit})
        return self.inner.fetch(source, limit=limit, timeout=timeout, query=query)


class _Adapters(dict):
    """The router's adapter override: a source id maps to an adapter.

    It behaves like a dictionary, because that is how the router reads it —
    a source that is not named falls back to the real adapter.
    """

    def __init__(self, adapter):
        super().__init__()
        self._default = adapter

    def get(self, key, default=None):
        if key in self:
            return self[key]
        return self._default


# ---------------------------------------------------------------------------
# the account decides the search
# ---------------------------------------------------------------------------


def test_two_accounts_produce_two_different_search_plans():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp))
        explore = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        build = router.start(ACCOUNT_BUILD, "HOTSPOT_DISCOVERY")
        plan_a = explore.detail["plan"]
        plan_b = build.detail["plan"]
        assert plan_a["plan_id"] != plan_b["plan_id"]
        assert plan_a["keywords_zh"] != plan_b["keywords_zh"]
        assert plan_a["source_allowlist"] != plan_b["source_allowlist"]
        assert plan_a["account_id"] == ACCOUNT_EXPLORE
        assert plan_b["account_id"] == ACCOUNT_BUILD


def test_a_hotspot_unrelated_to_the_account_is_rejected_before_a_person_sees_it():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        result = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        titles = [candidate["title"] for candidate in result.detail["candidates"]]
        assert "今天菜价怎么样" not in titles
        assert "AI 娱乐向内容盘点" not in titles
        assert "纯新闻搬运" not in " ".join(titles)
        rejected = result.detail["collection"]["rejected"]
        assert rejected >= 1


def test_the_accounts_source_allowlist_and_blocklist_take_effect():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        result = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        contacted = {entry["source_id"]
                     for entry in result.detail["collection"]["sources"]}
        assert "github-search" in contacted
        # The 1024 account blocks the general-interest and entertainment lists.
        assert "baidu-hot" not in contacted
        assert "bilibili-hot" not in contacted
        assert "douyin-hot" not in contacted
        plan = result.detail["plan"]
        blocked = {entry["source_id"] for entry in plan["rejected_sources"]}
        assert {"baidu-hot", "bilibili-hot"} <= blocked


def test_an_account_without_a_discovery_block_may_not_collect():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        path = root / "config" / "accounts" / f"{ACCOUNT_EXPLORE}.json"
        dna = json.loads(path.read_text(encoding="utf-8"))
        del dna["discovery"]
        path.write_text(json.dumps(dna, ensure_ascii=False), encoding="utf-8")

        spy = _Spy(_fixture_adapter())
        router = _router(root, adapters=_Adapters(spy))
        _expect("ACCOUNT_DNA_MISSING",
                lambda: router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY"))
        assert spy.calls == []


def test_an_account_with_no_dna_at_all_is_refused_by_name():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp, slugs=()))
        _expect("ACCOUNT_DNA_MISSING",
                lambda: router.start("no-such-account", "HOTSPOT_DISCOVERY"))


def test_a_changed_profile_version_moves_new_runs_and_leaves_old_ones_alone():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        router = _router(root, adapters=_fixture_adapter())
        first = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")

        path = root / "config" / "accounts" / f"{ACCOUNT_EXPLORE}.json"
        dna = json.loads(path.read_text(encoding="utf-8"))
        dna["discovery"]["profile_version"] = "2026-11-01.1"
        path.write_text(json.dumps(dna, ensure_ascii=False), encoding="utf-8")

        second = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        assert second.detail["plan"]["account_profile_version"] == "2026-11-01.1"

        stored_first = router.store.get_run(first.run_id)
        stored_second = router.store.get_run(second.run_id)
        assert stored_first["account_profile_version"] != \
            stored_second["account_profile_version"]
        # The old run still names the profile it actually searched against.
        assert stored_first["account_profile_version"] != "2026-11-01.1"


def test_two_accounts_share_a_database_and_share_nothing_else():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        router = _router(root, adapters=_fixture_adapter())
        explore = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        build = router.start(ACCOUNT_BUILD, "HOTSPOT_DISCOVERY")

        explore_pool = router.candidates(ACCOUNT_EXPLORE)
        build_pool = router.candidates(ACCOUNT_BUILD)
        assert explore_pool and build_pool
        explore_ids = {item["candidate_id"] for item in explore_pool}
        build_ids = {item["candidate_id"] for item in build_pool}
        assert not (explore_ids & build_ids)

        # The other account's pool is invisible from this one.
        assert router.candidates(ACCOUNT_EXPLORE, run_id=build.run_id) == []
        _expect("ACCOUNT_MISMATCH",
                lambda: router.select(ACCOUNT_EXPLORE, build.run_id,
                                      sorted(build_ids)[0], selected_by="Founder"))
        assert router.store.get_candidate(ACCOUNT_EXPLORE, sorted(build_ids)[0]) is None


# ---------------------------------------------------------------------------
# the route is never inferred
# ---------------------------------------------------------------------------


def test_a_run_with_no_route_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp))
        _expect(ROUTE_SELECTION_REQUIRED,
                lambda: router.start(ACCOUNT_EXPLORE, None))


def test_an_unknown_route_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp))
        _expect(ROUTE_SELECTION_REQUIRED,
                lambda: router.start(ACCOUNT_EXPLORE, "SOMETHING_ELSE"))


def test_the_user_topic_route_never_calls_the_hot_list_collector():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        original = hotspot_route.collect

        def explode(*_args, **_kwargs):
            raise AssertionError("the hot-list collector ran on the topic route")

        hotspot_route.collect = explode
        try:
            result = router.start(
                ACCOUNT_BUILD, "USER_TOPIC",
                UserTopicInput(topic="如何使用 LangGraph 开发可靠的 Agent？"))
        finally:
            hotspot_route.collect = original
        assert result.route_mode == "USER_TOPIC"
        assert result.detail["intent"]["topic"] == "如何使用 LangGraph 开发可靠的 Agent？"


def test_the_hot_list_route_calls_the_collector():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        result = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        assert result.route_mode == "HOTSPOT_DISCOVERY"
        assert result.detail["collection"]["sources"]


def test_a_source_that_says_its_data_is_old_cannot_supply_new_hotspots():
    """A frozen list is evidence of what was hot then, not of what is hot now."""
    inner = _fixture_adapter()

    class Frozen:
        def fetch(self, source, *, limit, timeout=12.0, query=None):
            result = inner.fetch(source, limit=limit, timeout=timeout, query=query)
            result.stale = True
            result.observed_at = "2026-09-01T00:00:00Z"
            return result

    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_Adapters(Frozen()))
        result = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        collection = result.detail["collection"]
        assert collection["candidates"] == 0
        assert set(collection["stale_sources"])
        assert collection["rejected_by_reason"] == {"STALE_SOURCE": collection["rejected"]}


def test_a_run_resumes_in_the_route_it_started_in():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        topic_run = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                                 UserTopicInput(topic="LangGraph 的状态管理怎么设计"))
        resumed = router.resume(ACCOUNT_BUILD, topic_run.run_id)
        assert resumed.route_mode == "USER_TOPIC"
        assert resumed.state != "CANDIDATES_READY"


def test_a_topic_route_never_produces_candidates():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        result = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                              UserTopicInput(topic="LangGraph 的状态管理怎么设计"))
        assert "candidates" not in result.detail
        assert router.candidates(ACCOUNT_BUILD, run_id=result.run_id) == []


# ---------------------------------------------------------------------------
# the human gates
# ---------------------------------------------------------------------------


def test_the_hot_list_route_cannot_skip_the_person_s_choice():
    assert can_transition(CANDIDATES_READY, "BRIEF_READY") is False
    assert can_transition(CANDIDATES_READY, APPROVED_FOR_PRODUCTION) is False
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        run = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        assert run.state == CANDIDATES_READY
        _expect("ILLEGAL_TRANSITION",
                lambda: router.approve(ACCOUNT_EXPLORE, run.run_id,
                                       reviewer="Founder"))


def test_a_choice_needs_a_name():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        run = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        candidate = run.detail["candidates"][0]["candidate_id"]
        _expect("SELECTOR_REQUIRED",
                lambda: router.select(ACCOUNT_EXPLORE, run.run_id, candidate,
                                      selected_by=""))


def test_a_choice_cannot_come_from_another_account():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        explore = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        build = router.start(ACCOUNT_BUILD, "HOTSPOT_DISCOVERY")
        foreign = build.detail["candidates"][0]["candidate_id"]
        # The candidate belongs to the other account's pool, so this account
        # cannot select it even though the run id is its own.
        _expect("CANDIDATE_NOT_FOUND",
                lambda: router.select(ACCOUNT_EXPLORE, explore.run_id, foreign,
                                      selected_by="Founder"))
        # And it cannot select through the other account's run either.
        _expect("ACCOUNT_MISMATCH",
                lambda: router.select(ACCOUNT_EXPLORE, build.run_id, foreign,
                                      selected_by="Founder"))


def test_an_approval_needs_a_named_reviewer():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        run = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        candidate = run.detail["candidates"][0]["candidate_id"]
        router.select(ACCOUNT_EXPLORE, run.run_id, candidate, selected_by="Founder")
        _expect("REVIEWER_REQUIRED",
                lambda: router.approve(ACCOUNT_EXPLORE, run.run_id, reviewer=""))


def test_the_router_wires_no_paid_media_or_publishing_path():
    """The router produces a brief. It must not reach a media generator."""
    package = Path(ROOT / "src" / "contentops" / "routing")
    offenders = []
    for path in sorted(package.glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            for forbidden in ("contentops.media", "minimax", "billing", "publish"):
                if forbidden in stripped:
                    offenders.append((path.name, stripped))
    assert not offenders, f"the router reaches a media or publishing path: {offenders}"


# ---------------------------------------------------------------------------
# the two routes, one contract
# ---------------------------------------------------------------------------


def test_both_routes_produce_the_same_brief_schema():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        hotspot = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        candidate = hotspot.detail["candidates"][0]["candidate_id"]
        router.select(ACCOUNT_EXPLORE, hotspot.run_id, candidate, selected_by="Founder")
        topic = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                             UserTopicInput(topic="LangGraph 的状态管理怎么设计"))

        first = router.read_brief(hotspot.run_id)
        second = router.read_brief(topic.run_id)
        assert validate_brief_package(first) == []
        assert validate_brief_package(second) == []
        assert first["schema"] == second["schema"]
        assert set(first["intent"]) == set(second["intent"])
        assert set(first["intent"]["route_context"]) == \
            set(second["intent"]["route_context"])
        assert first["candidate"]["schema"] == second["candidate"]["schema"]
        assert first["forecast"]["schema"] == second["forecast"]["schema"]


def test_both_routes_reach_the_same_project_creation():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        router = _router(root, adapters=_fixture_adapter())

        hotspot = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        candidate = hotspot.detail["candidates"][0]["candidate_id"]
        router.select(ACCOUNT_EXPLORE, hotspot.run_id, candidate, selected_by="Founder")
        router.approve(ACCOUNT_EXPLORE, hotspot.run_id, reviewer="Founder",
                       project_slug="router-hotspot", confirmed=True)

        topic = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                             UserTopicInput(topic="LangGraph 的状态管理怎么设计"))
        router.approve(ACCOUNT_BUILD, topic.run_id, reviewer="Founder",
                       project_slug="router-topic", confirmed=True)

        for slug, account in (("router-hotspot", ACCOUNT_EXPLORE),
                              ("router-topic", ACCOUNT_BUILD)):
            project = root / "projects" / slug
            assert project.is_dir(), project
            brief = project / "00_brief" / "brief.json"
            assert brief.is_file(), brief
            package = json.loads(brief.read_text(encoding="utf-8"))
            assert package["intent"]["account_id"] == account
            # The brief is what the pipeline reads, so the approval has to be
            # in it. A brief frozen at "pending" would tell a producer to stop
            # about a decision that had already been made.
            assert package["intent"]["approval_status"] == "approved"
            yaml_text = (project / "project.yaml").read_text(encoding="utf-8")
            assert f"account_slug: {account}" in yaml_text


def test_the_topic_route_can_fetch_evidence_from_query_accepting_sources_only():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        result = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                              UserTopicInput(topic="LangGraph 的状态管理怎么设计"),
                              fetch_evidence=True)
        detail = result.detail["intent"]["route_context"]["detail"]
        assert detail["fetched_evidence"]
        # A hot list is never consulted for a topic the owner named.
        assert all(item["source_id"] == "github-search"
                   for item in detail["fetched_evidence"])
        assert result.detail["intent"]["evidence"]


def test_a_waiting_run_can_be_resumed_with_the_exception_approved():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        waiting = router.start(ACCOUNT_EXPLORE, "USER_TOPIC",
                               UserTopicInput(topic="今天的菜价"))
        assert waiting.state == OUT_OF_PROFILE_REVIEW_REQUIRED
        resumed = router.resume(ACCOUNT_EXPLORE, waiting.run_id,
                                accept_off_profile=True,
                                override_note="创始人自己的副业")
        assert resumed.state == AWAITING_HUMAN_APPROVAL
        # The run keeps its identity: an approval continues it, it does not
        # start a second one.
        assert resumed.run_id == waiting.run_id
        override = resumed.detail["intent"]["route_context"]["off_profile_override"]
        assert override["note"] == "创始人自己的副业"


def test_a_run_reports_that_its_plan_is_behind_a_revised_account():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        router = _router(root, adapters=_fixture_adapter())
        run = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        fresh = router.resume(ACCOUNT_EXPLORE, run.run_id)
        assert fresh.detail["plan_currency"]["current"] is True

        path = root / "config" / "accounts" / f"{ACCOUNT_EXPLORE}.json"
        dna = json.loads(path.read_text(encoding="utf-8"))
        dna["discovery"]["profile_version"] = "2026-11-01.1"
        path.write_text(json.dumps(dna, ensure_ascii=False), encoding="utf-8")
        stale = router.resume(ACCOUNT_EXPLORE, run.run_id)
        assert stale.detail["plan_currency"]["current"] is False
        assert "2026-11-01.1" in stale.detail["plan_currency"]["reason"]
        # The run still holds the version it actually searched against.
        assert stale.detail["plan_currency"]["plan_profile_version"] != \
            stale.detail["plan_currency"]["account_profile_version"]


def test_the_topic_route_keeps_the_users_own_words():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        topic = "如何使用 LangGraph 开发可靠的 Agent？（含失败重试）"
        result = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                              UserTopicInput(topic=topic))
        stored = result.detail["intent"]
        assert stored["topic"] == topic
        assert stored["route_context"]["topic_origin"] == "USER_INPUT"
        package = router.read_brief(result.run_id)
        assert package["intent"]["topic"] == topic
        assert package["intent"]["route_context"]["user_input"] == topic


def test_an_off_profile_topic_needs_a_person_to_approve_the_exception():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        result = router.start(ACCOUNT_EXPLORE, "USER_TOPIC",
                              UserTopicInput(topic="今天的菜价"))
        assert result.state == OUT_OF_PROFILE_REVIEW_REQUIRED
        assert result.ok is False
        assert result.detail["alignment"]["alignment"] == "OFF_POSITIONING"

        # The run waits; it does not proceed on its own.
        assert router.store.get_run(result.run_id)["state"] == \
            OUT_OF_PROFILE_REVIEW_REQUIRED


def test_an_approved_exception_is_recorded_with_who_and_why():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        result = router.start(ACCOUNT_EXPLORE, "USER_TOPIC",
                              UserTopicInput(topic="今天的菜价"),
                              accept_off_profile=True,
                              override_note="创始人自己的副业",
                              selected_by="Founder")
        assert result.state == AWAITING_HUMAN_APPROVAL
        override = result.detail["intent"]["route_context"]["off_profile_override"]
        assert override["accepted_by"] == "Founder"
        assert override["note"] == "创始人自己的副业"


def test_the_brief_records_where_the_topic_came_from():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        hotspot = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        candidate = hotspot.detail["candidates"][0]["candidate_id"]
        router.select(ACCOUNT_EXPLORE, hotspot.run_id, candidate, selected_by="Founder")
        intent = router.store.get_run(hotspot.run_id)["intent_json"]
        context = json.loads(intent)["route_context"]
        assert context["topic_origin"] == "HOTSPOT_SELECTION"
        assert context["candidate_id"] == candidate
        assert context["selected_by"] == "Founder"
        assert context["search_plan_id"]


# ---------------------------------------------------------------------------
# the collection trail
# ---------------------------------------------------------------------------


def test_the_run_records_every_step_it_took():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        run = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        candidate = run.detail["candidates"][0]["candidate_id"]
        router.select(ACCOUNT_EXPLORE, run.run_id, candidate, selected_by="Founder")
        events = router.store.list_events(run.run_id)
        states = [event["state"] for event in events]
        assert states[0] == "SEARCH_PLAN_READY"
        assert "CANDIDATES_READY" in states
        assert "TOPIC_SELECTED" in states
        assert states[-1] == AWAITING_HUMAN_APPROVAL


def test_the_candidate_records_where_it_came_from():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        run = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        candidate = run.detail["candidates"][0]
        assert candidate["source_id"]
        assert candidate["collected_at"]
        assert candidate["relevance"]["components"]
        assert candidate["verification_status"]


# ---------------------------------------------------------------------------
# stability
# ---------------------------------------------------------------------------


def test_a_second_run_of_the_same_account_does_not_duplicate_the_first():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        first = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        second = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        assert first.run_id != second.run_id
        first_pool = router.candidates(ACCOUNT_EXPLORE, run_id=first.run_id)
        second_pool = router.candidates(ACCOUNT_EXPLORE, run_id=second.run_id)
        assert first_pool, "the first run's pool must survive the second run"
        assert second_pool
        # The same story found twice is the same candidate identity, but the
        # two runs keep their own pools.
        first_ids = {item["candidate_id"] for item in first_pool}
        second_ids = {item["candidate_id"] for item in second_pool}
        assert first_ids & second_ids
        # Storing the same pool twice must not double it.
        count = len(first_pool)
        router.store.save_candidates(first.run_id, account_id=ACCOUNT_EXPLORE,
                                     profile_version="v",
                                     candidates=first.detail["candidates"])
        assert len(router.candidates(ACCOUNT_EXPLORE, run_id=first.run_id)) == count


def test_a_failing_source_does_not_stop_the_others():
    class Failing:
        def fetch(self, source, *, limit, timeout=12.0, query=None):
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_UNAVAILABLE",
                               error_detail="network is down")

    working = _fixture_adapter()

    class Mixed:
        def fetch(self, source, *, limit, timeout=12.0, query=None):
            if source.source_id == "zhihu-hot":
                return Failing().fetch(source, limit=limit, timeout=timeout, query=query)
            return working.fetch(source, limit=limit, timeout=timeout, query=query)

    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_Adapters(Mixed()))
        result = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        failures = result.detail["collection"]["failures"]
        assert [failure["source_id"] for failure in failures] == ["zhihu-hot"]
        assert result.detail["collection"]["candidates"]


def test_the_topic_route_still_works_when_every_source_is_down():
    class Dead:
        def fetch(self, source, *, limit, timeout=12.0, query=None):
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_UNAVAILABLE",
                               error_detail="the hot-list service is off")

    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_Adapters(Dead()))
        hotspot = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        assert hotspot.detail["collection"]["candidates"] == 0
        assert hotspot.detail["collection"]["failures"]

        topic = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                             UserTopicInput(topic="LangGraph 的状态管理怎么设计"))
        assert topic.state == AWAITING_HUMAN_APPROVAL
        assert validate_brief_package(router.read_brief(topic.run_id)) == []


def test_the_store_refuses_a_schema_it_does_not_understand():
    """A store whose shape may differ is refused, not half-read."""
    import sqlite3
    from contentops.hotspots.storage import StorageError
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "state"
        home.mkdir(parents=True)
        connection = sqlite3.connect(str(home / "router.db"))
        connection.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_version (version) VALUES (999)")
        connection.commit()
        connection.close()
        store = RouterStore(Path(tmp), home=home)
        try:
            store.connect()
        except StorageError as exc:
            assert "schema version" in str(exc)
        else:
            raise AssertionError("a mismatched schema version must be refused")


def test_chinese_content_and_windows_paths_survive_a_whole_run():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        router = _router(root, adapters=_fixture_adapter())
        topic = "AI 编程助手：真实职业任务里的失败重试与成本"
        result = router.start(ACCOUNT_EXPLORE, "USER_TOPIC",
                              UserTopicInput(topic=topic,
                                             notes="备注：含中文标点，测试编码"))
        package = router.read_brief(result.run_id)
        assert package["intent"]["topic"] == topic
        assert package["intent"]["route_context"]["detail"]["input"]["notes"] == \
            "备注：含中文标点，测试编码"
        router.approve(ACCOUNT_EXPLORE, result.run_id, reviewer="创始人",
                       project_slug="router-chinese", confirmed=True)
        project = root / "projects" / "router-chinese"
        assert (project / "00_brief" / "brief.json").is_file()
        text = (project / "00_brief" / "brief.json").read_text(encoding="utf-8")
        assert topic in text


def test_timestamps_are_utc_and_carry_their_zone():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        result = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        candidate = result.detail["candidates"][0]
        assert candidate["collected_at"].endswith("Z")
        if candidate["published_at"]:
            assert candidate["published_at"].endswith("Z")


def test_the_account_cannot_exempt_itself_from_the_human_gates():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        path = root / "config" / "accounts" / f"{ACCOUNT_EXPLORE}.json"
        dna = json.loads(path.read_text(encoding="utf-8"))
        dna["discovery"]["approval_policy"]["topic_selection_required"] = False
        path.write_text(json.dumps(dna, ensure_ascii=False), encoding="utf-8")
        router = _router(root, adapters=_fixture_adapter())
        _expect("ACCOUNT_DNA_MALFORMED",
                lambda: router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY"))


def test_a_brief_that_would_not_pass_the_repository_contracts_is_not_written():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        result = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                              UserTopicInput(topic="LangGraph 的状态管理怎么设计"))
        # The brief on disk is valid against the repository's own contracts.
        package = router.read_brief(result.run_id)
        assert validate_brief_package(package) == []
        from contentops.workflow.human_forecast import validate_forecast
        from contentops.workflow.topics import validate_candidate
        assert validate_forecast(package["forecast"]) == []
        assert validate_candidate(package["candidate"]) == []


def _approved_run(router, account, slug=None):
    run = router.start(account, "USER_TOPIC",
                       UserTopicInput(topic="LangGraph 的状态管理怎么设计"))
    router.approve(account, run.run_id, reviewer="Founder", confirmed=True,
                   project_slug=slug)
    return run


def test_an_approval_must_be_confirmed_explicitly():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        run = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                           UserTopicInput(topic="LangGraph 的状态管理怎么设计"))
        _expect("CONFIRMATION_REQUIRED",
                lambda: router.approve(ACCOUNT_BUILD, run.run_id, reviewer="Founder"))


def test_an_automation_cannot_approve_without_opting_in():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        run = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                           UserTopicInput(topic="LangGraph 的状态管理怎么设计"))
        _expect("AUTOMATION_APPROVAL_REFUSED",
                lambda: router.approve(ACCOUNT_BUILD, run.run_id, reviewer="Acceptance",
                                       confirmed=True, actor_kind="automation"))


def test_an_automation_approval_is_recorded_as_one():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        run = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                           UserTopicInput(topic="LangGraph 的状态管理怎么设计"))
        result = router.approve(ACCOUNT_BUILD, run.run_id, reviewer="Acceptance",
                                confirmed=True, actor_kind="automation",
                                allow_automation=True)
        assert result.detail["actor_kind"] == "automation"
        approval = router.status(ACCOUNT_BUILD, run.run_id).detail["intent"][
            "route_context"]["detail"]["approval"]
        assert approval["actor_kind"] == "automation"


def test_an_approval_records_who_when_and_what():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        run = _approved_run(router, ACCOUNT_BUILD)
        verdict = router.verify_approval(run.run_id)
        assert verdict["ok"] is True
        approval = verdict["approval"]
        assert approval["reviewer"] == "Founder"
        assert approval["approved_at"].endswith("Z")
        assert len(approval["content_digest"]) == 64
        assert approval["actor_kind"] == "human"


def test_an_approval_stops_applying_when_the_brief_changes():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        run = _approved_run(router, ACCOUNT_BUILD)
        path = router.brief_path(run.run_id)
        package = json.loads(path.read_text(encoding="utf-8"))
        package["intent"]["topic"] = "换了一个完全不同的主题"
        path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
        verdict = router.verify_approval(run.run_id)
        assert verdict["ok"] is False
        assert verdict["reason"] == "APPROVAL_STALE"
        assert verdict["current_digest"] != verdict["approval"]["content_digest"]


def test_a_project_cannot_be_made_from_a_stale_approval():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        run = _approved_run(router, ACCOUNT_BUILD)
        path = router.brief_path(run.run_id)
        package = json.loads(path.read_text(encoding="utf-8"))
        package["forecast"]["topic_id"] = "TOPIC-SOMETHING-ELSE"
        path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
        profile = router.profile(ACCOUNT_BUILD)
        _expect("APPROVAL_NOT_VALID",
                lambda: router.materialize_project(profile, run.run_id, None,
                                                   "router-stale"))


def test_an_old_brief_cannot_be_replayed_into_another_run():
    with tempfile.TemporaryDirectory() as tmp:
        router = _router(_sandbox(tmp), adapters=_fixture_adapter())
        first = _approved_run(router, ACCOUNT_BUILD)
        second = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                              UserTopicInput(topic="Agent 的记忆机制怎么设计"))
        router.approve(ACCOUNT_BUILD, second.run_id, reviewer="Founder", confirmed=True)
        # Put the first run's approved package where the second run reads its own.
        shutil.copy(router.brief_path(first.run_id), router.brief_path(second.run_id))
        verdict = router.verify_approval(second.run_id)
        assert verdict["ok"] is False
        assert verdict["reason"] == "APPROVAL_STALE"


def test_an_approved_project_hands_off_to_its_pipeline():
    from contentops.routing import handoff
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        router = _router(root, adapters=_fixture_adapter())
        run = _approved_run(router, ACCOUNT_BUILD, slug="handoff-ok")
        project = root / "projects" / "handoff-ok"
        package = handoff.read_brief(project)
        verdict = handoff.check(package)
        assert verdict["ok"] is True, verdict
        record = handoff.handoff_record(project, package)
        assert record["schema"] == "contentops.brief-handoff/v1"
        assert record["account_id"] == ACCOUNT_BUILD
        assert record["route_mode"] == "USER_TOPIC"
        assert record["topic"]
        assert record["approval"]["content_digest"] == verdict["content_digest"]
        # The handoff is the start of the pipeline, not a pass through it.
        assert any("copy review" in item for item in record["still_gated_by"])
        path = handoff.write_handoff(project, record)
        assert path.is_file()


def test_a_degraded_forecast_blocks_the_handoff():
    from contentops.routing import handoff
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        router = _router(root, adapters=_fixture_adapter())
        run = router.start(ACCOUNT_EXPLORE, "USER_TOPIC",
                           UserTopicInput(topic="AI 新工具实测",
                                          urls=["https://example.test/a"]))
        router.approve(ACCOUNT_EXPLORE, run.run_id, reviewer="Founder",
                       confirmed=True, project_slug="handoff-degraded")
        project = root / "projects" / "handoff-degraded"
        verdict = handoff.check(handoff.read_brief(project))
        if verdict["ok"]:
            # This account's forecast happens to be feasible; the rule is
            # still exercised below by forcing the verdict.
            package = handoff.read_brief(project)
            package["forecast_verdict"] = "DEGRADED"
            verdict = handoff.check(package)
        assert verdict["ok"] is False
        assert verdict["reason"] == "EVIDENCE_REQUIRED"


def test_a_project_whose_brief_changed_after_approval_is_refused():
    from contentops.routing import handoff
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        router = _router(root, adapters=_fixture_adapter())
        _approved_run(router, ACCOUNT_BUILD, slug="handoff-tampered")
        project = root / "projects" / "handoff-tampered"
        path = project / "00_brief" / "brief.json"
        package = json.loads(path.read_text(encoding="utf-8"))
        package["intent"]["topic"] = "被改过的主题"
        path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
        verdict = handoff.check(handoff.read_brief(project))
        assert verdict["ok"] is False
        assert verdict["reason"] == "APPROVAL_STALE"


def test_a_project_with_no_brief_cannot_hand_off():
    from contentops.routing import handoff
    with tempfile.TemporaryDirectory() as tmp:
        verdict = handoff.check(handoff.read_brief(Path(tmp)))
        assert verdict["ok"] is False
        assert verdict["reason"] == "BRIEF_MISSING"


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
    print(f"\nAll {len(tests)} content router tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
