#!/usr/bin/env python3
"""Maintain a small, reviewable topic backlog and publishing calendar."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from runtime_context import ACCOUNT


ACCOUNTS = {ACCOUNT}
STATUSES = {"idea", "queued", "in-progress", "published", "paused"}
SUPPORTED_PLATFORMS = {"douyin", "xiaohongshu", "wechat_channels"}


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid or missing backlog: {error}") from error
    if not isinstance(value, dict) or not isinstance(value.get("items", []), list):
        raise SystemExit("backlog must be a JSON object with an items list")
    return value


def save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def emit(value: Any) -> None:
    """Keep piped JSON ASCII-safe on Windows GBK consoles."""
    interactive = bool(getattr(sys.stdout, "isatty", lambda: False)())
    if interactive and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(value, ensure_ascii=not interactive, indent=2))


def init(args: argparse.Namespace) -> int:
    if Path(args.output).exists() and not args.force:
        raise SystemExit(f"backlog already exists: {args.output}")
    value = {"schema_version": 1, "account": args.account, "status": "active", "items": []}
    save(Path(args.output).expanduser().resolve(), value)
    emit(value)
    return 0


def add(args: argparse.Namespace) -> int:
    path = Path(args.backlog).expanduser().resolve()
    value = load(path)
    if value.get("account") not in {None, args.account}:
        raise SystemExit(f"backlog account does not match requested account: {value.get('account')}")
    if args.account not in ACCOUNTS or args.status not in STATUSES:
        raise SystemExit("invalid account or status")
    target_platforms = [item.strip() for item in args.platforms.split(",") if item.strip()]
    if not target_platforms or any(item not in SUPPORTED_PLATFORMS for item in target_platforms):
        raise SystemExit(f"platforms must be selected from: {', '.join(sorted(SUPPORTED_PLATFORMS))}")
    audience_status = args.audience_status
    audience_validation = {
        "status": audience_status,
        "viewer_quote": args.viewer_quote,
        "viewer_trigger": args.viewer_trigger,
        "current_workaround": args.current_workaround,
        "pain_or_stakes": args.pain_or_stakes,
        "desired_progress": args.desired_progress,
        "source_refs": [item.strip() for item in args.audience_source_refs.split(",") if item.strip()],
    }
    if audience_status == "approved":
        required_audience = ("viewer_quote", "viewer_trigger", "current_workaround", "pain_or_stakes", "desired_progress")
        if any(not str(audience_validation[field]).strip() for field in required_audience) or not audience_validation["source_refs"]:
            raise SystemExit("approved audience validation requires viewer fields and at least one source ref")
    if any(str(item.get("topic_id")) == args.topic_id for item in value["items"] if isinstance(item, dict)):
        raise SystemExit(f"topic_id already exists: {args.topic_id}")
    value["items"].append(
        {
            "topic_id": args.topic_id,
            "content_id": args.content_id,
            "title": args.title,
            "account": args.account,
            "pillar": args.pillar,
            "format": args.format,
            "target_platforms": target_platforms,
            "platform_policy_ref": args.platform_policy_ref,
            "platform_risk_class": "medium",
            "audience_validation": audience_validation,
            "permission_status": "pending_review",
            "human_review_status": "pending",
            "priority": args.priority,
            "status": args.status,
            "evidence_floor": 2,
            "scheduled_for": "",
            "experiment": args.experiment,
            "notes": args.notes,
        }
    )
    save(path, value)
    emit(value["items"][-1])
    return 0


def calendar(args: argparse.Namespace) -> int:
    path = Path(args.backlog).expanduser().resolve()
    value = load(path)
    start = date.fromisoformat(args.start)
    candidates = [
        item for item in value["items"]
        if isinstance(item, dict) and item.get("status") in {"idea", "queued"}
        and item.get("account") == args.account
        and isinstance(item.get("audience_validation"), dict)
        and item.get("audience_validation", {}).get("status") == "approved"
    ]
    blocked_candidates = [
        item for item in value["items"]
        if isinstance(item, dict) and item.get("status") in {"idea", "queued"}
        and item.get("account") == args.account
        and item.get("audience_validation", {}).get("status") != "approved"
    ]
    candidates.sort(key=lambda item: (-int(item.get("priority", 3)), str(item.get("topic_id", ""))))
    selected = candidates[: max(0, args.days)]
    entries: list[dict[str, Any]] = []
    for offset, item in enumerate(selected):
        scheduled = start + timedelta(days=offset)
        item["scheduled_for"] = scheduled.isoformat()
        item["status"] = "queued"
        entries.append({"date": scheduled.isoformat(), "topic_id": item.get("topic_id"), "title": item.get("title"), "account": item.get("account"), "format": item.get("format")})
    save(path, value)
    output = {
        "schema_version": 1,
        "account": args.account,
        "start": args.start,
        "days": args.days,
        "entries": entries,
        "blocked_topics": [str(item.get("topic_id", "")) for item in blocked_candidates],
        "errors": [] if entries or args.days == 0 else ["no audience-approved topics are eligible for queueing"],
    }
    if args.output:
        save(Path(args.output).expanduser().resolve(), output)
    emit(output)
    return 0 if output["entries"] or args.days == 0 else 1


def check(args: argparse.Namespace) -> int:
    """Verify that a content package has a reserved, scheduled topic."""
    path = Path(args.backlog).expanduser().resolve()
    value = load(path)
    expected_date = args.scheduled_for.strip()
    matches: list[dict[str, Any]] = []
    for item in value["items"]:
        if not isinstance(item, dict):
            continue
        account = str(item.get("account", ""))
        if account != args.account:
            continue
        if str(item.get("content_id", "")) != args.content_id and str(item.get("topic_id", "")) != args.content_id:
            continue
        if str(item.get("status", "")) not in {"queued", "in-progress"}:
            continue
        scheduled = str(item.get("scheduled_for", "")).strip()
        if not scheduled:
            continue
        if expected_date and scheduled != expected_date:
            continue
        matches.append(item)
    result = {
        "content_id": args.content_id,
        "account": args.account,
        "passed": bool(matches),
        "matches": matches,
        "errors": [] if matches else ["no queued topic reserved for this content package"],
    }
    emit(result)
    return 0 if result["passed"] or not args.strict else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Maintain a reviewable creator topic backlog.")
    child = parser.add_subparsers(dest="command", required=True)
    init_parser = child.add_parser("init")
    init_parser.add_argument("--output", required=True)
    init_parser.add_argument("--account", choices=sorted(ACCOUNTS), default=ACCOUNT)
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(handler=init)
    add_parser = child.add_parser("add")
    add_parser.add_argument("--backlog", required=True)
    add_parser.add_argument("--topic-id", required=True)
    add_parser.add_argument("--title", required=True)
    add_parser.add_argument("--account", choices=sorted(ACCOUNTS), required=True)
    add_parser.add_argument("--pillar", default="")
    add_parser.add_argument("--format", default="short-video")
    add_parser.add_argument("--priority", type=int, choices=range(1, 6), default=3)
    add_parser.add_argument("--status", choices=sorted(STATUSES), default="idea")
    add_parser.add_argument("--experiment", default="")
    add_parser.add_argument("--notes", default="")
    add_parser.add_argument("--content-id", default="", help="Optional content package id this topic is reserved for.")
    add_parser.add_argument("--platforms", default="douyin", help="Comma-separated target platforms.")
    add_parser.add_argument("--platform-policy-ref", default="configs/platform-policies/multi-platform-safe-publishing-v1.json")
    add_parser.add_argument("--audience-status", choices=["pending", "approved", "blocked"], default="pending")
    add_parser.add_argument("--viewer-quote", default="")
    add_parser.add_argument("--viewer-trigger", default="")
    add_parser.add_argument("--current-workaround", default="")
    add_parser.add_argument("--pain-or-stakes", default="")
    add_parser.add_argument("--desired-progress", default="")
    add_parser.add_argument("--audience-source-refs", default="")
    add_parser.set_defaults(handler=add)
    calendar_parser = child.add_parser("calendar")
    calendar_parser.add_argument("--backlog", required=True)
    calendar_parser.add_argument("--account", choices=sorted(ACCOUNTS), required=True)
    calendar_parser.add_argument("--start", default=date.today().isoformat())
    calendar_parser.add_argument("--days", type=int, default=7)
    calendar_parser.add_argument("--output")
    calendar_parser.set_defaults(handler=calendar)
    check_parser = child.add_parser("check")
    check_parser.add_argument("--backlog", required=True)
    check_parser.add_argument("--content-id", required=True)
    check_parser.add_argument("--account", choices=sorted(ACCOUNTS), required=True)
    check_parser.add_argument("--scheduled-for", default="")
    check_parser.add_argument("--strict", action="store_true")
    check_parser.set_defaults(handler=check)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
