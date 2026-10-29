#!/usr/bin/env python3
"""Check the editorial/workflow documents that have no media artifact.

    python scripts/workflow_docs.py check --kind rights --input rights-ledger.json
    python scripts/workflow_docs.py check --kind sources --input source-candidates.json
    python scripts/workflow_docs.py check --kind forecast --input forecast.json
    python scripts/workflow_docs.py score --input candidate.json
    python scripts/workflow_docs.py rank --inputs a.json b.json c.json
    python scripts/workflow_docs.py fingerprint-skill --dir <skill dir>

Kinds: topics, candidate, strategy, forecast, rights, sources, platform,
visual-route, delivery, improvement, feedback, metrics, provenance, naturalness,
capture-plan.

Exit 0 = the document passes, 1 = it fails with named errors, 2 = usage error.
Nothing here fetches, renders or publishes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.quality.naturalness import validate_naturalness  # noqa: E402
from contentops.workflow import (  # noqa: E402
    capture_plan,
    copy_strategy,
    delivery,
    feedback,
    improvement,
    platform,
    provenance,
    rights,
    sources,
    topics,
    visual_route,
)
from contentops.workflow import human_forecast  # noqa: E402

CHECKS = {
    "topics": topics.validate_backlog,
    "candidate": topics.validate_candidate,
    "strategy": copy_strategy.validate_strategy,
    "forecast": human_forecast.validate_forecast,
    "rights": rights.validate_ledger,
    "sources": sources.validate_candidates,
    "platform": platform.validate_plan,
    "visual-route": visual_route.validate_route,
    "delivery": delivery.validate_manifest,
    "improvement": improvement.validate_log,
    "feedback": feedback.validate_feedback,
    "metrics": feedback.validate_metrics_import,
    "provenance": provenance.validate_provenance,
    "naturalness": validate_naturalness,
    "capture-plan": capture_plan.validate_capture_plan,
}


def _read(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_check(args: argparse.Namespace) -> int:
    validator = CHECKS.get(args.kind)
    if validator is None:
        print(f"unknown kind {args.kind!r}; choose from {sorted(CHECKS)}", file=sys.stderr)
        return 2
    try:
        document = _read(args.input)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"input unreadable: {exc}", file=sys.stderr)
        return 1
    errors = validator(document)
    if args.kind == "forecast":
        print(f"verdict: {human_forecast.forecast_verdict(document)}")
    if args.kind == "platform":
        print(f"verdict: {platform.plan_verdict(document)}")
    if errors:
        for message in errors:
            print(f"  - {message}")
        print(f"[FAIL] {args.kind}")
        return 1
    print(f"[PASS] {args.kind}")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    try:
        document = _read(args.input)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"input unreadable: {exc}", file=sys.stderr)
        return 1
    result = topics.score_candidate(document)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["errors"] else 1


def cmd_rank(args: argparse.Namespace) -> int:
    documents = []
    for path in args.inputs:
        try:
            documents.append(_read(path))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            return 1
    ranked = topics.rank_candidates(documents)
    if args.json:
        print(json.dumps(ranked, ensure_ascii=False, indent=2))
    else:
        for item in ranked:
            flag = "FAIL" if item["errors"] else item["decision"]
            print(f"{item['combined']:>6.2f}  {item['candidate_id']:<32} {flag}")
    return 0 if all(not item["errors"] for item in ranked) else 1


def cmd_fingerprint(args: argparse.Namespace) -> int:
    try:
        fingerprint = provenance.skill_tree_fingerprint(Path(args.dir))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(fingerprint, ensure_ascii=False, indent=2))
    return 0


def cmd_next_id(args: argparse.Namespace) -> int:
    from contentops.workflow.naming import next_content_id
    try:
        print(next_content_id(args.topic, Path(args.root), args.date))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate workflow documents")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="validate one document")
    check.add_argument("--kind", required=True, choices=sorted(CHECKS))
    check.add_argument("--input", required=True)
    check.set_defaults(func=cmd_check)

    score = sub.add_parser("score", help="score a content candidate")
    score.add_argument("--input", required=True)
    score.set_defaults(func=cmd_score)

    rank = sub.add_parser("rank", help="rank candidates by combined score")
    rank.add_argument("--inputs", nargs="+", required=True)
    rank.add_argument("--json", action="store_true")
    rank.set_defaults(func=cmd_rank)

    fingerprint = sub.add_parser("fingerprint-skill", help="fingerprint a skill tree")
    fingerprint.add_argument("--dir", required=True)
    fingerprint.set_defaults(func=cmd_fingerprint)

    next_id = sub.add_parser("next-id", help="allocate the next content id")
    next_id.add_argument("--topic", required=True)
    next_id.add_argument("--root", required=True)
    next_id.add_argument("--date", default="", help="YYYYMMDD; defaults to today")
    next_id.set_defaults(func=cmd_next_id)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
