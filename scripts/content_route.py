#!/usr/bin/env python3
"""Route a topic into a brief, for one account, by one of two routes.

    python scripts/content_route.py accounts
    python scripts/content_route.py start --account x-superplay-1024 --mode hotspot
    python scripts/content_route.py start --account x-superplay-1024 --mode topic \
        --topic "如何使用 LangGraph 开发可靠的 Agent？"
    python scripts/content_route.py candidates --account x-superplay-1024
    python scripts/content_route.py select --candidate CAND-XXXX --by "Founder"
    python scripts/content_route.py status --run RUN-XXXX
    python scripts/content_route.py resume --run RUN-XXXX
    python scripts/content_route.py approve --run RUN-XXXX --reviewer "Founder" --confirm

The route is never inferred. ``--mode`` is required, and a run that started in
one route resumes in that route, whatever happened in between.

Exit codes: 0 the operation succeeded, 1 the router refused, 2 usage error.
A refusal prints its code, because the code is the contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.routing import ContentRouter, RoutingError  # noqa: E402
from contentops.routing import hotspot_route  # noqa: E402
from contentops.routing.user_topic_route import UserTopicInput, read_draft  # noqa: E402

MODES = ("hotspot", "topic")


def _mode_to_route(mode: str) -> str:
    if mode == "hotspot":
        return "HOTSPOT_DISCOVERY"
    if mode == "topic":
        return "USER_TOPIC"
    raise RoutingError("ROUTE_SELECTION_REQUIRED",
                       f"mode {mode!r} is not one of {list(MODES)}")


def _router(args: argparse.Namespace) -> ContentRouter:
    return ContentRouter(ROOT, trendradar_db=getattr(args, "trendradar_db", None))


def _emit(payload: object, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def _print_accounts(entries) -> None:
    print(f"{'account':<36} {'pipeline':<14} {'version':<16} pillars / sources")
    print("-" * 100)
    for entry in entries:
        if not entry.get("usable"):
            print(f"{entry['account_id']:<36} {'-':<14} {'-':<16} "
                  f"UNUSABLE: {entry.get('code')}")
            print(f"{'':<36} {entry.get('reason', '')}")
            continue
        print(f"{entry['account_id']:<36} {entry['target_pipeline']:<14} "
              f"{entry['profile_version']:<16} "
              f"{len(entry.get('pillars', []))} pillars / "
              f"{len(entry.get('sources', []))} sources")
        print(f"{'':<36} {entry.get('positioning', '')}")


def _print_candidates(candidates) -> None:
    if not candidates:
        print("no candidates")
        return
    for index, candidate in enumerate(candidates, start=1):
        relevance = candidate.get("relevance") or {}
        print(f"{index}. {candidate.get('title')}")
        print(f"   id        {candidate.get('candidate_id')}")
        print(f"   source    {candidate.get('source_id')}  rank {candidate.get('source_rank')}")
        print(f"   pillar    {candidate.get('pillar') or '-'}")
        print(f"   category  {candidate.get('category')}")
        angles = candidate.get("angles") or []
        if angles:
            print(f"   angles    {' / '.join(str(a) for a in angles)}")
        print(f"   score     {relevance.get('score')}  "
              f"(verification: {candidate.get('verification_status')})")
        if candidate.get("url"):
            print(f"   link      {candidate.get('url')}")
        for reason in (candidate.get("reasons_for") or [])[:3]:
            print(f"   + {reason}")
        for reason in (candidate.get("reasons_against") or [])[:2]:
            print(f"   - {reason}")
        print()


def cmd_sources(args: argparse.Namespace) -> int:
    """The source catalog: what exists and what each one can actually do."""
    from contentops.hotspots.source_registry import all_sources
    entries = [source.to_dict() for source in all_sources()]
    if args.json:
        _emit(entries, True)
        return 0
    print(f"{'source':<20} {'mode':<14} {'platform':<12} {'max':<5} why")
    print("-" * 100)
    for entry in entries:
        print(f"{entry['source_id']:<20} {entry['query_mode']:<14} "
              f"{entry['platform']:<12} {entry['max_items']:<5} {entry['note']}")
    print()
    print("An account names the sources it may contact in its discovery block;")
    print("a source that is not on that list is never contacted.")
    return 0


def cmd_accounts(args: argparse.Namespace) -> int:
    router = _router(args)
    entries = router.accounts()
    if args.json:
        _emit(entries, True)
    else:
        _print_accounts(entries)
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    router = _router(args)
    payload = None
    if args.mode == "topic":
        draft = read_draft(args.draft) if args.draft else None
        payload = UserTopicInput(
            topic=args.topic or "",
            urls=list(args.url or []),
            local_paths=list(args.doc or []),
            draft=draft,
            notes=args.notes or "",
        )
    result = router.start(
        args.account,
        _mode_to_route(args.mode),
        payload,
        pillar=args.pillar,
        freshness_hours=args.freshness_hours,
        per_source_limit=args.per_source_limit,
        accept_off_profile=args.accept_off_profile,
        override_note=args.note or "",
        selected_by=args.by or "",
        fetch_evidence=args.fetch_evidence,
        collect=not args.plan_only,
    )
    if args.json:
        _emit(result.to_dict(), True)
        return 0 if result.ok else 1

    print(f"run        {result.run_id}")
    print(f"account    {result.account_id}")
    print(f"route      {result.route_mode}")
    print(f"state      {result.state}")
    if result.state == "SEARCH_PLAN_READY":
        plan = result.detail.get("plan") or {}
        print()
        print(plan.get("summary", ""))
        native = hotspot_route.native_query_sources(plan)
        listed = hotspot_route.list_only_sources(plan)
        print(f"server-side query on: {', '.join(native) or 'none'}")
        print(f"read as a list and filtered locally: {', '.join(listed) or 'none'}")
        for entry in plan.get("sources") or []:
            print(f"  - {entry['source_id']:<20} {entry['query_mode']:<14} "
                  f"max {entry['max_items']}")
            print(f"    {entry['capability_note']}")
        for rejected in plan.get("rejected_sources") or []:
            print(f"  x {rejected['source_id']:<20} {rejected['reason']}: "
                  f"{rejected['detail']}")
        print()
        print("run again without --plan-only to collect")
        return 0
    if result.state == "CANDIDATES_READY":
        collection = result.detail.get("collection") or {}
        print()
        print(f"collected {collection.get('fetched')} item(s) from "
              f"{len(collection.get('sources') or [])} source(s); "
              f"{collection.get('rejected')} rejected as off-profile or stale")
        for failure in collection.get("failures") or []:
            print(f"  ! {failure['source_id']}: {failure['error_code']} — "
                  f"{failure['error_detail']}")
        print()
        _print_candidates(result.detail.get("candidates") or [])
        print(f"choose one: content route select --candidate <id> --by <name>")
        return 0
    if not result.ok:
        alignment = result.detail.get("alignment") or {}
        print()
        print(f"BLOCKED {result.state}: {result.detail.get('message', '')}")
        if alignment:
            print(f"  {alignment.get('detail', '')}")
        return 1
    intent = result.detail.get("intent") or {}
    print()
    print(f"topic      {intent.get('topic')}")
    print(f"brief      {result.detail.get('brief')}")
    print(f"next       approve the brief: content route approve --run {result.run_id} "
          f"--reviewer <name> --confirm")
    return 0


def cmd_candidates(args: argparse.Namespace) -> int:
    router = _router(args)
    candidates = router.candidates(args.account, run_id=args.run)
    if args.json:
        _emit(candidates, True)
    else:
        _print_candidates(candidates)
    return 0


def cmd_select(args: argparse.Namespace) -> int:
    router = _router(args)
    account = args.account
    run_id = args.run
    if not run_id:
        if not account:
            raise RoutingError("ACCOUNT_REQUIRED",
                               "name the account, or the run, so the candidate can "
                               "be found")
        run_id = router.store.find_candidate_run(account, args.candidate)
        if not run_id:
            raise RoutingError(
                "CANDIDATE_NOT_FOUND",
                f"no candidate {args.candidate!r} in account {account!r}")
    else:
        account = account or router.store.account_of_run(run_id)
    if not account:
        raise RoutingError("ACCOUNT_REQUIRED", "the run names no account")
    result = router.select(account, run_id, args.candidate, selected_by=args.by or "")
    if args.json:
        _emit(result.to_dict(), True)
        return 0
    print(f"run        {result.run_id}")
    print(f"state      {result.state}")
    print(f"topic      {(result.detail.get('intent') or {}).get('topic')}")
    print(f"brief      {result.detail.get('brief')}")
    print(f"next       approve the brief: content route approve --run {result.run_id} "
          f"--reviewer <name> --confirm")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    router = _router(args)
    account = args.account or router.store.account_of_run(args.run)
    if not account:
        raise RoutingError("RUN_NOT_FOUND", f"no run {args.run!r}")
    result = router.status(account, args.run)
    if args.json:
        _emit(result.to_dict(), True)
        return 0
    print(f"run        {result.run_id}")
    print(f"account    {result.account_id}")
    print(f"route      {result.route_mode}")
    print(f"state      {result.state}")
    print(f"next       {result.detail.get('next')}")
    plan = result.detail.get("plan")
    if plan:
        print()
        print(plan.get("summary", ""))
    intent = result.detail.get("intent")
    if intent:
        print()
        print(f"topic      {intent.get('topic')}")
        print(f"approval   {intent.get('approval_status')}")
        print(f"evidence   {intent.get('evidence_status')}")
    events = result.detail.get("events") or []
    if events:
        print()
        print("trail:")
        for event in events:
            print(f"  {event['at']}  {event['state']:<32} {event.get('detail') or ''}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    router = _router(args)
    account = args.account or router.store.account_of_run(args.run)
    if not account:
        raise RoutingError("RUN_NOT_FOUND", f"no run {args.run!r}")
    result = router.resume(account, args.run,
                           accept_off_profile=args.accept_off_profile,
                           override_note=args.note or "")
    if args.json:
        _emit(result.to_dict(), True)
        return 0 if result.ok else 1
    print(f"run        {result.run_id}")
    print(f"route      {result.route_mode}")
    print(f"state      {result.state}")
    print(f"next       {result.detail.get('next')}")
    candidates = result.detail.get("candidates")
    if candidates:
        print()
        _print_candidates(candidates)
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    if not args.confirm:
        raise RoutingError("CONFIRMATION_REQUIRED",
                           "approval requires --confirm; there is no implicit approval")
    router = _router(args)
    account = args.account or router.store.account_of_run(args.run)
    if not account:
        raise RoutingError("RUN_NOT_FOUND", f"no run {args.run!r}")
    result = router.approve(account, args.run, reviewer=args.reviewer or "",
                            note=args.note or "", project_slug=args.project,
                            confirmed=True, actor_kind=args.actor_kind)
    if args.json:
        _emit(result.to_dict(), True)
        return 0
    print(f"run        {result.run_id}")
    print(f"state      {result.state}")
    print(f"reviewer   {result.detail.get('reviewer')} "
          f"({result.detail.get('actor_kind')})")
    print(f"digest     {str(result.detail.get('content_digest'))[:16]}")
    if result.detail.get("project"):
        print(f"project    {result.detail.get('project')}")
    print()
    print("the copy review is still the gate before anything is rendered")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    router = _router(args)
    verdict = router.verify_approval(args.run)
    if args.json:
        _emit(verdict, True)
        return 0 if verdict["ok"] else 1
    print(f"run        {args.run}")
    print(f"approval   {'VALID' if verdict['ok'] else verdict['reason']}")
    print(f"detail     {verdict.get('detail') or 'the brief still matches what was approved'}")
    return 0 if verdict["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Account-aware content router: pick an account, pick a route, "
                    "get a brief.")
    parser.add_argument("--trendradar-db", default=None,
                        help="path to a TrendRadar SQLite database (read-only)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help_text: str):
        # `--json` is added to every subcommand as well as to the root, so
        # it works on either side of the subcommand name.
        child = sub.add_parser(name, help=help_text)
        child.add_argument("--json", action="store_true", help="machine-readable output")
        return child

    accounts = add("accounts", "list the accounts and their profiles")
    accounts.set_defaults(func=cmd_accounts)

    sources = add("sources", "list the source catalog and what each can do")
    sources.set_defaults(func=cmd_sources)

    start = add("start", "begin a run")
    start.add_argument("--account", required=True)
    start.add_argument("--mode", required=True, choices=list(MODES),
                       help="hotspot or topic; the router never picks for you")
    start.add_argument("--topic", default="", help="the topic, for --mode topic")
    start.add_argument("--url", action="append", help="a reference link (repeatable)")
    start.add_argument("--doc", action="append", help="a local document (repeatable)")
    start.add_argument("--draft", help="a local draft file")
    start.add_argument("--notes", default="", help="notes about the topic")
    start.add_argument("--pillar", default=None, help="restrict a hotspot run to one pillar")
    start.add_argument("--freshness-hours", type=int, default=72)
    start.add_argument("--per-source-limit", type=int, default=30)
    start.add_argument("--plan-only", action="store_true",
                       help="write the search plan and stop")
    start.add_argument("--accept-off-profile", action="store_true",
                       help="approve an off-profile topic explicitly")
    start.add_argument("--fetch-evidence", action="store_true",
                       help="for --mode topic, also look for supporting material "
                            "in the sources that accept a query")
    start.add_argument("--note", default="", help="why an exception was approved")
    start.add_argument("--by", default="", help="who made the choice")
    start.set_defaults(func=cmd_start)

    candidates = add("candidates", "list the candidate pool")
    candidates.add_argument("--account", required=True)
    candidates.add_argument("--run", default=None)
    candidates.set_defaults(func=cmd_candidates)

    select = add("select", "choose one candidate")
    select.add_argument("--candidate", required=True)
    select.add_argument("--run", default=None)
    select.add_argument("--account", default=None)
    select.add_argument("--by", required=True, help="who chose it")
    select.set_defaults(func=cmd_select)

    status = add("status", "show a run")
    status.add_argument("--run", required=True)
    status.add_argument("--account", default=None)
    status.set_defaults(func=cmd_status)

    resume = add("resume", "continue a run in its own route")
    resume.add_argument("--run", required=True)
    resume.add_argument("--account", default=None)
    resume.add_argument("--accept-off-profile", action="store_true")
    resume.add_argument("--note", default="")
    resume.set_defaults(func=cmd_resume)

    approve = add("approve", "approve a brief for the pipeline")
    approve.add_argument("--run", required=True)
    approve.add_argument("--account", default=None)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--note", default="")
    approve.add_argument("--project", default=None,
                         help="also create this project and put the brief in it")
    approve.add_argument("--confirm", action="store_true")
    approve.add_argument("--actor-kind", choices=("human", "automation"),
                         default="human",
                         help="who is approving; an automation approval is always "
                              "refused from this command line")
    approve.set_defaults(func=cmd_approve)

    verify = add("verify", "check that an approval still matches the brief")
    verify.add_argument("--run", required=True)
    verify.set_defaults(func=cmd_verify)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        return args.func(args)
    except RoutingError as exc:
        print(f"BLOCKED [{exc.code}]: {exc.detail}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"BLOCKED [UNEXPECTED]: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
