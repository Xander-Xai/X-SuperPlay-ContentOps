#!/usr/bin/env python3
"""Record one day of routing per account, so a week can be judged from data.

Run this once a day. It collects for one account (or both), writes a JSONL
line per account per day under the router's own state directory, and prints
the day's numbers. It does not choose a topic and it does not approve
anything: an observation run is a measurement, not a decision.

The record answers, per source: did it answer, how many rows did it give, was
its data stale, and what did the account's filter do with them. After a week
the ``--report`` view prints the per-source success rate and the candidate
yield, which is what tells you whether a source earns its place on the
allowlist.

Usage:
    python scripts/router_observe.py                      # both accounts, today
    python scripts/router_observe.py --account x-superplay-1024
    python scripts/router_observe.py --report --days 7
    python scripts/router_observe.py --home .verify-tmp/observe --dry-run

Exit codes: 0 the observation was recorded; 4 a run was blocked (the record is
still written, because a blocked run is data too).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.hotspots.storage import RouterStore  # noqa: E402
from contentops.routing import RoutingError  # noqa: E402
from contentops.routing.router import ContentRouter  # noqa: E402

ACCOUNTS = ("x-superplay-1024", "x-superplay-future-intelligence")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def observation_path(home: Path) -> Path:
    """Where the daily observation lines live, next to the router's own state."""
    return Path(home) / "observation" / "daily.jsonl"


def _record(router: ContentRouter, account: str, trendradar_db: Optional[str]) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"at": _now(), "account": account, "route": "HOTSPOT_DISCOVERY"}
    try:
        result = router.start(account, "HOTSPOT_DISCOVERY")
    except RoutingError as exc:
        entry.update({"status": "BLOCKED", "code": exc.code, "detail": exc.detail})
        return entry
    return entry_from_result(account, result, trendradar_db)


def entry_from_result(account: str, result: Any, trendradar_db: Optional[str]
                      ) -> Dict[str, Any]:
    """One observation line, from a run that already happened.

    Split out so the scheduled collection records the same shape as the manual
    one: a week of data is only comparable if both wrote it the same way.
    """
    entry: Dict[str, Any] = {"at": _now(), "account": account,
                             "route": "HOTSPOT_DISCOVERY"}
    collection = (result.detail or {}).get("collection") or {}
    sources = collection.get("sources") or []
    entry.update({
        "status": result.state,
        "run_id": result.run_id,
        "plan_id": collection.get("plan_id"),
        "trendradar_db": trendradar_db,
        "fetched": collection.get("fetched"),
        "rejected_by_reason": collection.get("rejected_by_reason") or {},
        "candidates": collection.get("candidates"),
        "stale_sources": collection.get("stale_sources") or [],
        "sources": [
            {"source_id": source.get("source_id"), "ok": source.get("ok"),
             "count": source.get("count"), "stale": source.get("stale"),
             "observed_at": source.get("observed_at"),
             "error_code": source.get("error_code")}
            for source in sources
        ],
        "candidate_titles": [
            {"title": candidate.get("title"),
             "score": (candidate.get("relevance") or {}).get("score"),
             "source_id": candidate.get("source_id"),
             "pillar": candidate.get("pillar")}
            for candidate in (result.detail.get("candidates") or [])
        ],
    })
    return entry


def append_entry(path: Path, entry: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read(path: Path, days: int) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    kept = []
    for row in rows:
        try:
            moment = datetime.fromisoformat(str(row.get("at")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if moment.timestamp() >= cutoff:
            kept.append(row)
    return kept


def _report(rows: List[Dict[str, Any]], days: int) -> None:
    print(f"observation window: last {days} day(s), {len(rows)} recorded run(s)")
    if not rows:
        print("no observations yet; run the script once a day to build a window")
        return
    per_source: Dict[str, Dict[str, int]] = {}
    for row in rows:
        for source in row.get("sources") or []:
            stats = per_source.setdefault(source.get("source_id") or "?",
                                          {"ok": 0, "failed": 0, "stale": 0, "rows": 0})
            if source.get("ok"):
                stats["ok"] += 1
                stats["rows"] += int(source.get("count") or 0)
            else:
                stats["failed"] += 1
            if source.get("stale"):
                stats["stale"] += 1
    print(f"\n{'source':22} {'ok':>4} {'fail':>5} {'stale':>6} {'rows':>6}")
    for source_id in sorted(per_source):
        stats = per_source[source_id]
        print(f"{source_id:22} {stats['ok']:>4} {stats['failed']:>5} "
              f"{stats['stale']:>6} {stats['rows']:>6}")

    print(f"\n{'day':12} {'account':34} {'fetched':>8} {'cands':>6}")
    for row in rows:
        print(f"{str(row.get('at'))[:10]:12} {str(row.get('account')):34} "
              f"{str(row.get('fetched')):>8} {str(row.get('candidates')):>6}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Record one day of routing per account.")
    parser.add_argument("--account", default=None,
                        help=f"one account (default: {' and '.join(ACCOUNTS)})")
    parser.add_argument("--home", default=None,
                        help="router state directory (default: .local/content-router)")
    parser.add_argument("--trendradar-db", default=None,
                        help="path to a real TrendRadar database")
    parser.add_argument("--dry-run", action="store_true",
                        help="run the collection but do not append to the log")
    parser.add_argument("--report", action="store_true", help="print the window instead")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    store = RouterStore(ROOT, home=Path(args.home) if args.home else None)
    log_path = observation_path(store.home)

    if args.report:
        rows = _read(log_path, args.days)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            _report(rows, args.days)
        return 0

    accounts = (args.account,) if args.account else ACCOUNTS
    router = ContentRouter(ROOT, store=store, trendradar_db=args.trendradar_db)
    entries = []
    for account in accounts:
        entry = _record(router, account, args.trendradar_db)
        entries.append(entry)
        print(f"{account}: {entry.get('status')} fetched={entry.get('fetched')} "
              f"candidates={entry.get('candidates')} stale={entry.get('stale_sources')}")
        if not args.dry_run:
            append_entry(log_path, entry)
    if args.json:
        print(json.dumps(entries, ensure_ascii=False, indent=2))
    if not args.dry_run:
        print(f"\nrecorded in {log_path}")
    return 0 if all(entry.get("candidates") is not None for entry in entries) else 4


if __name__ == "__main__":
    sys.exit(main())
