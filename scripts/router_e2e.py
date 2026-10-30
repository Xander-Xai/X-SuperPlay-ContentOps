#!/usr/bin/env python3
"""Run both routes end to end and write one receipt of what happened.

Why this exists
---------------
The unit suites prove the parts. This proves the path: a real account, a
real source collection, a real brief, and a real project.

Two runs, and they are deliberately different in kind:

**E2E-A, the hot-list route.** A real search against the real sources. When
the network is down, or a source is down, the receipt says so and names the
failure — it does not fall back to a fixture and call that a live run.

**E2E-B, the topic route.** A topic the account owner names, with no hot-list
collection at all. It must work whether or not every hot-list source is
reachable, which is the point of keeping the two routes separate.

What this script does *not* do
------------------------------
It does not publish, and it does not reach a media generator. The two
human steps — choosing a topic and approving a brief — are performed here by
the acceptance run itself, under the operator's name, and the receipt says so
in as many words. That is an acceptance run, not a standing approval: the
copy review is still the gate before anything is rendered.

Usage:
    python scripts/router_e2e.py --actor "Founder"
    python scripts/router_e2e.py --actor "Founder" --offline
    python scripts/router_e2e.py --actor "Founder" --out .verify-tmp/router-e2e.json

Exit codes: 0 both runs produced a valid brief, 1 at least one did not.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.routing import ContentRouter, RoutingError  # noqa: E402
from contentops.routing.brief import validate_brief_package  # noqa: E402
from contentops.routing.user_topic_route import UserTopicInput  # noqa: E402
from contentops.hotspots.storage import RouterStore  # noqa: E402

RECEIPT_SCHEMA = "contentops.router-e2e/v1"

#: The account the acceptance run uses for the hot-list route.
HOTSPOT_ACCOUNT = "x-superplay-1024"

#: The account the acceptance run uses for the topic route.
TOPIC_ACCOUNT = "x-superplay-future-intelligence"

#: The topic for E2E-B. It is deliberately *not* a recent hot topic: the
#: topic route has to work for a subject nobody is currently discussing.
#: It names terms the Future Intelligence account declares in its own
#: "AI 工程拆解" pillar, so it is on-profile by the account's own declaration.
TOPIC = "LangGraph 的状态管理怎么做，才能让 Agent 在长任务里不丢上下文"
TOPIC_URL = "https://github.com/langchain-ai/langgraph"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sandbox(root: Path) -> Path:
    """A throwaway home for the run's own state, so the receipt is isolated."""
    return root / ".verify-tmp" / "router-e2e"


def _approve_and_materialise(router: ContentRouter, account: str, run_id: str,
                              actor: str, slug: str) -> Dict[str, Any]:
    """Approve a brief and create the project it belongs to.

    This is the acceptance run standing in for the person who would do it.
    The receipt says so; it is not a standing approval.
    """
    outcome: Dict[str, Any] = {}
    try:
        approved = router.approve(account, run_id, reviewer=actor,
                                  note="acceptance run", project_slug=slug,
                                  confirmed=True, actor_kind="automation",
                                  allow_automation=True)
    except RoutingError as exc:
        outcome["approved"] = False
        outcome["code"] = exc.code
        outcome["reason"] = exc.detail
        return outcome
    except (OSError, ValueError) as exc:
        # A project with this slug already exists from an earlier acceptance
        # run. The scaffolder refuses to overwrite it, and it is right to.
        outcome["approved"] = False
        outcome["code"] = "PROJECT_EXISTS"
        outcome["reason"] = str(exc)
        return outcome
    outcome["approved"] = True
    outcome["state"] = approved.state
    outcome["actor_kind"] = approved.detail.get("actor_kind")
    outcome["content_digest"] = approved.detail.get("content_digest")
    outcome["approval_valid"] = router.verify_approval(run_id)["ok"]
    outcome["project"] = approved.detail.get("project")
    project = Path(str(approved.detail.get("project") or ""))
    if project.is_dir():
        brief = project / "00_brief" / "brief.json"
        outcome["project_brief"] = str(brief)
        outcome["project_brief_present"] = brief.is_file()
        yaml_path = project / "project.yaml"
        if yaml_path.is_file():
            text = yaml_path.read_text(encoding="utf-8")
            outcome["project_declares_account"] = f"account_slug: {account}" in text
    return outcome


def run_hotspot(router: ContentRouter, actor: str, offline: bool) -> dict:
    """E2E-A: a real hot-list run, from a real account."""
    record: dict = {"name": "E2E-A", "route": "HOTSPOT_DISCOVERY",
                    "account": HOTSPOT_ACCOUNT, "offline": offline,
                    "started_at": _now()}
    try:
        result = router.start(HOTSPOT_ACCOUNT, "HOTSPOT_DISCOVERY")
    except RoutingError as exc:
        record["status"] = "BLOCKED"
        record["code"] = exc.code
        record["reason"] = exc.detail
        record["finished_at"] = _now()
        return record

    collection = result.detail.get("collection") or {}
    plan = result.detail.get("plan") or {}
    record.update({
        "run_id": result.run_id,
        "status": "COLLECTED",
        "plan_id": plan.get("plan_id"),
        "plan_summary": plan.get("summary"),
        "profile_version": plan.get("account_profile_version"),
        "sources_planned": [entry.get("source_id") for entry in plan.get("sources") or []],
        "sources_contacted": [entry.get("source_id")
                              for entry in collection.get("sources") or []],
        "source_failures": collection.get("failures") or [],
        # Every source, successful or not, with what it contributed. This is
        # the per-source record the daily observation keeps.
        "source_summary": [
            {"source_id": entry.get("source_id"), "ok": entry.get("ok"),
             "count": entry.get("count"), "stale": entry.get("stale"),
             "schema": entry.get("schema"), "observed_at": entry.get("observed_at"),
             "query": entry.get("query"), "error_code": entry.get("error_code")}
            for entry in collection.get("sources") or []
        ],
        "rejected_by_reason": collection.get("rejected_by_reason") or {},
        "stale_sources": collection.get("stale_sources") or [],
        "fetched": collection.get("fetched"),
        "rejected_off_profile": collection.get("rejected"),
        "candidates": len(result.detail.get("candidates") or []),
    })

    if offline:
        record["status"] = "BLOCKED"
        record["code"] = "OFFLINE_BY_REQUEST"
        record["reason"] = ("the run was asked not to use the network, so no real "
                            "hot list was collected")
        record["finished_at"] = _now()
        return record

    candidates = result.detail.get("candidates") or []
    if not candidates:
        record["status"] = "BLOCKED"
        record["code"] = "NO_CANDIDATES"
        record["reason"] = ("the sources were contacted and no candidate survived "
                            "the account's relevance filter")
        record["finished_at"] = _now()
        return record

    chosen = candidates[0]
    try:
        selected = router.select(HOTSPOT_ACCOUNT, result.run_id,
                                 chosen["candidate_id"], selected_by=actor)
    except RoutingError as exc:
        record["status"] = "BLOCKED"
        record["code"] = exc.code
        record["reason"] = exc.detail
        record["finished_at"] = _now()
        return record

    package = router.read_brief(result.run_id)
    failures = validate_brief_package(package) if package else ["no brief was written"]
    record.update({
        "status": "BRIEF_READY" if not failures else "BRIEF_INVALID",
        "chosen_candidate": chosen["candidate_id"],
        "chosen_title": chosen["title"],
        "chosen_source": chosen.get("source_id"),
        "chosen_url": chosen.get("url"),
        "chosen_score": (chosen.get("relevance") or {}).get("score"),
        "chosen_pillar": chosen.get("pillar"),
        "chosen_angles": chosen.get("angles"),
        "brief_path": str(router.brief_path(result.run_id)),
        "brief_failures": failures,
        "state_after_select": selected.state,
        "human_steps": ("the topic selection was performed by this acceptance run "
                        f"under the name {actor!r}; it is not a standing approval"),
    })
    record["production"] = _approve_and_materialise(
        router, HOTSPOT_ACCOUNT, result.run_id, actor, "e2e-hotspot")
    record["finished_at"] = _now()
    return record


def run_topic(router: ContentRouter, actor: str) -> dict:
    """E2E-B: the owner names a topic, and no hot list is consulted."""
    record: dict = {"name": "E2E-B", "route": "USER_TOPIC",
                    "account": TOPIC_ACCOUNT, "started_at": _now()}
    payload = UserTopicInput(topic=TOPIC, urls=[TOPIC_URL],
                              notes="acceptance run: a topic that is not a hot topic")
    try:
        result = router.start(TOPIC_ACCOUNT, "USER_TOPIC", payload)
    except RoutingError as exc:
        record["status"] = "BLOCKED"
        record["code"] = exc.code
        record["reason"] = exc.detail
        record["finished_at"] = _now()
        return record

    package = router.read_brief(result.run_id)
    failures = validate_brief_package(package) if package else ["no brief was written"]
    alignment = (package or {}).get("intent", {}).get("profile_alignment", {})
    record.update({
        "run_id": result.run_id,
        "status": "BRIEF_READY" if not failures else "BRIEF_INVALID",
        "topic": result.detail.get("intent", {}).get("topic"),
        "alignment": alignment.get("alignment"),
        "alignment_detail": alignment.get("detail"),
        "brief_path": str(router.brief_path(result.run_id)),
        "brief_failures": failures,
        "state": result.state,
        "hot_list_consulted": False,
        "human_steps": ("the brief approval was performed by this acceptance run "
                        f"under the name {actor!r}; it is not a standing approval"),
    })
    record["production"] = _approve_and_materialise(
        router, TOPIC_ACCOUNT, result.run_id, actor, "e2e-topic")
    record["finished_at"] = _now()
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Content router end-to-end acceptance")
    parser.add_argument("--actor", default="acceptance-run",
                        help="the name the acceptance run acts under")
    parser.add_argument("--offline", action="store_true",
                        help="do not use the network; the hot-list leg is reported "
                             "as blocked rather than faked")
    parser.add_argument("--out", default=None, help="where to write the receipt")
    parser.add_argument("--home", default=None,
                        help="where the run's own state lives")
    parser.add_argument("--trendradar-db", default=None,
                        help="path to a real TrendRadar database (defaults to "
                             "TRENDRADAR_DB_PATH when set)")
    args = parser.parse_args(argv)

    # The acceptance run is the one caller allowed to approve as an automation,
    # and it has to say so twice: in code (allow_automation=True at the call
    # site) and in the environment. A production job does not set this, so it
    # cannot inherit the exception by copying a command line.
    os.environ.setdefault("CONTENTOPS_TEST_SANDBOX", "1")

    home = Path(args.home) if args.home else _sandbox(ROOT)
    sandbox_reset = False
    if not args.home and home.exists():
        # The acceptance run owns this directory. A previous receipt's
        # projects would make the scaffolder refuse a slug it created itself,
        # so the run starts from an empty sandbox and says so in the receipt.
        shutil.rmtree(home)
        sandbox_reset = True
    store = RouterStore(ROOT, home=home)
    router = ContentRouter(ROOT, store=store,
                            projects_root=home / "projects",
                            trendradar_db=args.trendradar_db)

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "started_at": _now(),
        "actor": args.actor,
        "offline": bool(args.offline),
        "store": str(home),
        "sandbox_reset": sandbox_reset,
        "human_steps_note": (
            "The topic selection and the brief approval were performed by this "
            "acceptance run under the operator's name, so that the two routes "
            "could be checked end to end. They are not standing approvals. The "
            "copy review remains the gate before anything is rendered, and "
            "nothing here published or generated any media."),
        "runs": [],
    }

    for leg in (run_hotspot(router, args.actor, args.offline),
                run_topic(router, args.actor)):
        receipt["runs"].append(leg)
        print(f"[{leg['name']}] {leg['status']}"
              + (f" ({leg.get('code')})" if leg.get("code") else ""))
        for key in ("reason", "plan_summary", "chosen_title", "brief_failures",
                    "alignment_detail", "topic"):
            if leg.get(key):
                print(f"    {key}: {leg[key]}")

    receipt["finished_at"] = _now()
    # A valid brief is not the end of the acceptance: the brief has to reach
    # a project, with the account recorded, or the handover is unproven.
    ok = all(leg["status"] == "BRIEF_READY"
             and (leg.get("production") or {}).get("approved")
             and (leg.get("production") or {}).get("project_brief_present")
             and (leg.get("production") or {}).get("approval_valid")
             and (leg.get("production") or {}).get("actor_kind") == "automation"
             for leg in receipt["runs"])
    receipt["overall"] = "PASS" if ok else "INCOMPLETE"

    out = Path(args.out) if args.out else home / "router-e2e.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print()
    print(f"overall: {receipt['overall']}")
    print(f"receipt: {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
