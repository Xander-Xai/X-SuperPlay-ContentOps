#!/usr/bin/env python3
"""Read-only X growth diagnostic. No X API, account credentials or fabricated zeros.

Usage:
  python scripts/x_growth_report.py
  python -m unittest discover -s tests -p 'test_x_growth_report.py'
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
AGE_WINDOWS = ("T+2H", "T+24H", "T+72H", "T+7D")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def observed_number(row: dict[str, str], key: str) -> int | None:
    raw = (row.get(key) or "").strip()
    if not raw:
        return None
    try:
        result = int(raw)
    except ValueError:
        return None
    return result if result >= 0 else None


def valid_x_url(url: str) -> bool:
    try:
        parsed = urlparse((url or "").strip())
        parts = [p for p in parsed.path.split("/") if p]
        return (parsed.scheme == "https" and
                (parsed.hostname or "").lower() in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"} and
                len(parts) >= 3 and parts[1].lower() == "status" and
                parts[2].isdigit())
    except ValueError:
        return False


def rate(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def when(row: dict[str, str]) -> datetime | None:
    raw = (row.get("observed_at") or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def diagnose(posts: list[dict[str, str]],
             snapshots: list[dict[str, str]],
             accounts: list[dict[str, str]]) -> dict:
    known = {r.get("content_id", ""): r for r in posts if r.get("content_id")}
    pending = sorted([k for k, p in known.items()
                      if p.get("status") == "reported_published_url_pending"])
    invalid_publications = sorted([k for k, p in known.items()
                                   if p.get("status") == "published" and
                                   not valid_x_url(p.get("x_post_url", ""))])
    verified = {k for k, p in known.items()
                if p.get("status") == "published" and valid_x_url(p.get("x_post_url", ""))}
    observations: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    rejected_snapshot_count = 0
    for s in snapshots:
        k = s.get("content_id", "")
        w = s.get("age_window", "")
        if k not in verified or w not in AGE_WINDOWS or not when(s):
            rejected_snapshot_count += 1
            continue
        if s.get("data_access") not in ("available", "partial"):
            rejected_snapshot_count += 1
            continue
        observations[(k, w)].append(s)

    # Multiple observations at the same intended window: use the latest actual read.
    # Never sum cumulative metrics across different snapshot rows.
    cohorts: dict[str, list[dict]] = defaultdict(list)
    for (content_id, window), readings in observations.items():
        latest = max(readings, key=when)
        impressions = observed_number(latest, "impressions")
        components = [observed_number(latest, k) for k in
                      ("likes", "reposts", "replies", "bookmarks")]
        interaction_count = sum(components) if all(x is not None for x in components) else None
        profile = observed_number(latest, "profile_clicks")
        signal = observed_number(latest, "qualified_signal_count")
        cohorts[window].append({
            "content_id": content_id,
            "impressions": impressions,
            "interaction_rate": rate(interaction_count, impressions),
            "profile_visit_rate": rate(profile, impressions),
            "qualified_signal_per_1000_views": (
                round(rate(signal, impressions) * 1000, 3)
                if rate(signal, impressions) is not None else None),
        })

    summaries = {}
    for window, records in sorted(cohorts.items()):
        # Unknown account handles must not be joined into a cross-account winner claim.
        with_impressions = [r["impressions"] for r in records if r["impressions"] is not None]
        summaries[window] = {
            "verified_posts_with_snapshot": len(records),
            "posts_with_observed_impressions": len(with_impressions),
            "median_observed_impressions": statistics.median(with_impressions) if with_impressions else None,
            "inference": "directional_only" if len(with_impressions) < 10 else "review_cohort_and_format_before_inference",
            "per_post": records,
        }

    account_series: dict[str, list[tuple[datetime, int]]] = defaultdict(list)
    for row in accounts:
        handle = (row.get("account_handle") or "").strip()
        followers = observed_number(row, "followers_count")
        ts = when(row)
        if handle and followers is not None and ts:
            account_series[handle].append((ts, followers))

    follower_trends = {}
    for handle, series in account_series.items():
        ordered = sorted(series)
        follower_trends[handle] = {
            "observations": len(ordered),
            "start_followers": ordered[0][1],
            "end_followers": ordered[-1][1],
            "net_change_observed": (ordered[-1][1] - ordered[0][1]) if len(ordered) >= 2 else None,
            "note": "account-level only; no post attribution",
        }

    return {
        "status": "observational_audit_not_causal_attribution",
        "total_indexed_posts": len(known),
        "owner_reported_published_url_pending": pending,
        "published_rows_without_valid_url": invalid_publications,
        "verified_published_posts": len(verified),
        "snapshots_not_comparable_or_not_verified": rejected_snapshot_count,
        "age_matched_windows": summaries,
        "account_followers": follower_trends,
        "needs_actual_post_urls": bool(pending or invalid_publications),
        "needs_native_metrics": not bool(summaries),
        "needs_account_follower_history": not any(v["net_change_observed"] is not None
                                                   for v in follower_trends.values()),
        "warning": "Never interpret blank metrics as zero, infer a shadowban, or assign net account follower loss to one post.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.root
    result = diagnose(
        read_csv(root / "templates" / "posts.csv"),
        read_csv(root / "templates" / "x-metric-snapshots.csv"),
        read_csv(root / "templates" / "x-account-snapshots.csv"),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
