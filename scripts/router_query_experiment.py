#!/usr/bin/env python3
"""Compare query expressions for one account's native-search source.

A query expression is a query decision, not a positioning change: every term
in it names a keyword the account already declared. This script measures the
difference, read-only, so the decision can be made on numbers instead of
opinion.

For each variant it reports, for the same source and the same moment:

- how many items the source returned;
- how many of them passed the account's own relevance gate;
- the precision that follows (passed / returned), and the titles that passed.

Nothing is stored: no run, no candidate pool, no plan. The only network calls
are the ones the source needs.

Usage:
    python scripts/router_query_experiment.py --account x-superplay-1024
    python scripts/router_query_experiment.py --account x-superplay-future-intelligence --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.hotspots.adapters import GitHubSearchAdapter  # noqa: E402
from contentops.hotspots.query_planner import build_search_plan  # noqa: E402
from contentops.hotspots.ranking import relevance_verdict  # noqa: E402
from contentops.hotspots.source_registry import get_source  # noqa: E402
from contentops.routing.account_profile import load_profile  # noqa: E402

SOURCE_ID = "github-search"


def _query_from_plan(profile) -> str:
    plan = build_search_plan(profile)
    entry = next(item for item in plan["sources"] if item["source_id"] == SOURCE_ID)
    return str(entry.get("query") or "")


def _evaluate(profile, query: str, limit: int) -> Dict[str, Any]:
    source = get_source(SOURCE_ID)
    result = GitHubSearchAdapter().fetch(source, limit=limit, query=query)
    record: Dict[str, Any] = {
        "query": query,
        "ok": result.ok,
        "returned": len(result.items),
        "error_code": result.error_code,
    }
    if not result.ok:
        return record
    passed = []
    for item in result.items:
        verdict = relevance_verdict(item, profile)
        if verdict["accepted"]:
            passed.append({"title": item.title, "url": item.url})
    record["passed"] = len(passed)
    record["precision"] = round(len(passed) / len(result.items), 3) if result.items else 0.0
    record["passed_titles"] = [entry["title"] for entry in passed[:8]]
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--account", required=True)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    profile = load_profile(ROOT, args.account)
    if not (profile.query_expressions or {}).get("github_search"):
        print(f"{args.account} declares no github_search query expression; nothing to compare")
        return 1

    tuned = _query_from_plan(profile)
    keyword_only = _query_from_plan(replace(profile, query_expressions={}))
    variants = [("expression", tuned)]
    if keyword_only != tuned:
        variants.append(("keyword-derived", keyword_only))
    single = (profile.query_expressions["github_search"])[0]
    if single != tuned:
        variants.append(("single-term", single))

    rows: List[Dict[str, Any]] = []
    for name, query in variants:
        outcome = _evaluate(profile, query, args.limit)
        outcome["variant"] = name
        rows.append(outcome)

    if args.json:
        print(json.dumps({"account": args.account, "variants": rows}, ensure_ascii=False,
                         indent=2))
        return 0

    print(f"account {args.account}  source {SOURCE_ID}  limit {args.limit}")
    print(f"{'variant':16} {'ok':5} {'returned':>8} {'passed':>6} {'precision':>9}  query")
    for row in rows:
        print(f"{row['variant']:16} {str(row['ok']):5} {row['returned']:>8} "
              f"{row.get('passed', 0):>6} {row.get('precision', 0):>9}  {row['query']}")
    for row in rows:
        if row.get("passed_titles"):
            print(f"\n{row['variant']} passed:")
            for title in row["passed_titles"]:
                print(f"  - {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
