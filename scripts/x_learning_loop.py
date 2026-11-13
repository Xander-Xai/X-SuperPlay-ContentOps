#!/usr/bin/env python3
"""Local-only X metrics -> descriptive analysis -> human-reviewed learning brief.

Reads the existing X CSV contracts. No X login, scraping, remote upload,
publication, follower attribution, or automatic production changes.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "x-growth-en"
DEFAULT_DATA = ROOT / ".local" / "x-growth-en"
FILES = ("posts.csv", "x-metric-snapshots.csv", "x-account-snapshots.csv")
GROUPS = ("inspiration_broad", "inspiration_ai", "timeline_ai", "original")
WINDOWS = ("T+24H", "T+72H", "T+7D")
AGE_HOURS = {"T+24H": (18, 36), "T+72H": (60, 84), "T+7D": (144, 192)}
PUBLISHED = {"published", "verified_published", "reported_published"}
STATUS_URL = re.compile(r"^/[^/]+/status/[0-9]+/?$")


def _timestamp(value: str):
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date if date.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None


def _integer(value: str):
    if value is None or value.strip() == "":
        return None
    try:
        number = int(value)
        return number if number >= 0 else None
    except (ValueError, TypeError):
        return None


def _valid_status_url(value: str):
    try:
        url = urlparse(value)
        return (url.scheme == "https" and url.hostname in {"x.com", "twitter.com"}
                and not url.username and not url.password and bool(STATUS_URL.fullmatch(url.path)))
    except ValueError:
        return False


def _read_table(path: Path, required: tuple[str, ...]):
    if not path.is_file():
        raise ValueError(f"missing local CSV: {path}")
    if path.stat().st_size > 20_000_000:
        raise ValueError(f"local CSV too large: {path.name}")
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise ValueError(f"{path.name} is missing required columns: {required}")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError(f"malformed CSV row in {path.name}")
    return rows


def _guard_local(data_dir: Path):
    """Never write private exports into tracked repository directories."""
    target = data_dir.resolve()
    try:
        relative = target.relative_to(ROOT.resolve())
    except ValueError:
        return
    if not relative.parts or relative.parts[0] != ".local":
        raise ValueError("data-dir inside repository must be under ignored .local/")


def initialize(data_dir: Path):
    _guard_local(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    created = []
    for name in FILES:
        target = data_dir / name
        if target.exists():
            continue
        header = (PROJECT / "templates" / name).read_text(encoding="utf-8").splitlines()[0]
        with target.open("x", encoding="utf-8", newline="") as handle:
            handle.write(header + "\n")
        created.append(name)
    return {"status": "READY", "data_dir": str(data_dir), "created": created,
            "existing_preserved": sorted(set(FILES) - set(created)), "network_used": False}


def _source(post):
    marker = (post.get("experiment_variable") or "").strip()
    for part in marker.split(";"):
        part = part.strip()
        if part.startswith("source:") and part[7:] in GROUPS:
            return part[7:]
    return None


def _account_context(rows, account):
    valid = []
    for row in rows:
        if row.get("account_handle") != account:
            continue
        stamp = _timestamp(row.get("observed_at", ""))
        if stamp and (row.get("observation_source") or "").strip():
            valid.append((stamp, row))
    if not valid:
        return None
    row = sorted(valid, key=lambda pair: pair[0])[-1][1]
    return {"observed_at": row["observed_at"],
            "observation_source": row.get("observation_source"),
            "followers_count": _integer(row.get("followers_count", "")),
            "account_impressions": _integer(row.get("account_impressions", "")),
            "account_profile_visits": _integer(row.get("account_profile_visits", "")),
            "platform_reported_net_follows": row.get("platform_reported_net_follows") or None,
            "attribution": "ACCOUNT_LEVEL_ONLY"}


def analyze(data_dir: Path, account: str, window: str):
    _guard_local(data_dir)
    if window not in WINDOWS:
        raise ValueError("unsupported metric window")
    posts = _read_table(data_dir / FILES[0],
                        ("content_id", "mode", "status", "x_post_url", "account_handle",
                         "experiment_variable", "post_published_at"))
    metrics = _read_table(data_dir / FILES[1],
                          ("content_id", "x_post_url", "age_window", "observed_at",
                           "metric_source", "data_access", "organic_paid", "impressions",
                           "profile_clicks"))
    accounts = _read_table(data_dir / FILES[2],
                           ("account_handle", "observed_at", "observation_source"))
    eligible = {}
    skipped = defaultdict(int)
    for post in posts:
        if post["account_handle"] != account:
            continue
        group = _source(post)
        if not group:
            skipped["untagged_posts"] += 1
            continue
        if (post.get("status") or "").strip().lower() not in PUBLISHED:
            skipped["unpublished_or_unverified_state"] += 1
            continue
        if not (_valid_status_url(post.get("x_post_url") or "")
                and _timestamp(post.get("post_published_at") or "")):
            skipped["invalid_post_url_or_time"] += 1
            continue
        mode = (post.get("mode") or "").strip().lower()
        if (group == "original" and mode not in {"original", "original_post", "post", "source_analysis", "workflow_artifact"}) or (group != "original" and mode not in {"reply", "reply_draft"}):
            skipped["mode_source_mismatch"] += 1
            continue
        key = (post["content_id"], post["x_post_url"])
        if key in eligible:
            skipped["duplicate_post_key"] += 1
            eligible[key] = None
        else:
            eligible[key] = group
    matching = defaultdict(list)
    for row in metrics:
        if row.get("age_window", "").upper() != window:
            continue
        key = (row.get("content_id"), row.get("x_post_url"))
        if key not in eligible or eligible[key] is None:
            continue
        matching[key].append(row)
    collected = defaultdict(list)
    for key, records in matching.items():
        if len(records) != 1:
            skipped["duplicate_snapshot_window"] += 1
            continue
        record = records[0]
        pub = next((p for p in posts if p.get("content_id") == key[0] and p.get("x_post_url") == key[1]), None)
        published = _timestamp((pub or {}).get("post_published_at", ""))
        observed = _timestamp(record.get("observed_at", ""))
        hours = ((observed - published).total_seconds() / 3600
                 if observed and published else -1)
        low, high = AGE_HOURS[window]
        if not low <= hours <= high:
            skipped["snapshot_age_mismatch"] += 1
            continue
        if (record.get("organic_paid") != "organic"
                or record.get("data_access") not in {"available", "partial"}
                or not (record.get("metric_source") or "").strip()
                or not _timestamp(record.get("observed_at", ""))):
            skipped["invalid_provenance_or_paid"] += 1
            continue
        impressions = _integer(record.get("impressions", ""))
        if impressions is None:
            skipped["missing_impressions"] += 1
            continue
        raw_clicks = record.get("profile_clicks", "")
        clicks = _integer(raw_clicks)
        if raw_clicks and raw_clicks.strip() and clicks is None:
            skipped["invalid_profile_clicks"] += 1
            continue
        if clicks is not None and impressions == 0 and clicks > 0:
            skipped["inconsistent_click_denominator"] += 1
            continue
        collected[eligible[key]].append((impressions, clicks))
    groups = []
    for name in GROUPS:
        items = collected[name]
        complete = [(views, clicks) for views, clicks in items if clicks is not None]
        total_complete_views = sum(views for views, _ in complete)
        groups.append({
            "source": name,
            "sample_count": len(items),
            "median_impressions": statistics.median(x[0] for x in items) if items else None,
            "total_impressions": sum(x[0] for x in items) if items else None,
            "profile_click_samples": len(complete),
            "profile_clicks_per_1000_impressions": (
                round(sum(clicks for _, clicks in complete) * 1000 / total_complete_views, 3)
                if complete and total_complete_views > 0 else None),
            "profile_clicks_missing": len(items) - len(complete)
        })
    compared = [g for g in groups if g["source"] != "original" and g["sample_count"] >= 5]
    status = "DESCRIPTIVE_ONLY" if len(compared) >= 2 else "INSUFFICIENT_DATA"
    return {
        "schema": "contentops.local-learning-brief/v1",
        "status": status, "account": account, "platform": "x", "window": window,
        "source": "USER_SUPPLIED_LOCAL_CSV_UNVERIFIED",
        "groups": groups, "skipped": dict(skipped),
        "account_context": _account_context(accounts, account),
        "interpretation": ("Two or more source groups have >=5 observations. "
                           "Differences are descriptive, not causal."
                           if status == "DESCRIPTIVE_ONLY" else
                           "Need >=5 comparable, published, organic observations "
                           "in at least two reply-source groups."),
        "next_experiment": {
            "primary_variable": "discovery_source",
            "recommendation": "Compare same account/language/topic family/time windows; "
                              "review exposure and profile-interest separately.",
            "proposed_topic": None,
            "approval": "FOUNDER_REVIEW_REQUIRED",
            "production_status": "NOT_AUTHORIZED",
            "manual_route": "python scripts/content_route.py start --account <approved-account> "
                            "--mode topic --topic <approved-evidence-backed-topic>"
        },
        "network_used": False, "publication_performed": False,
        "cross_platform_metrics_comparable": False
    }


def _markdown(report):
    lines = ["# Local X learning brief", "",
             f"Account: {report['account']} | Window: {report['window']}",
             f"Status: {report['status']} | Source: local user-supplied CSV (unverified)", "",
             "| Discovery source | Samples | Median impressions | Profile clicks / 1k impressions |",
             "|---|---:|---:|---:|"]
    for g in report["groups"]:
        median = "unknown" if g["median_impressions"] is None else str(g["median_impressions"])
        rate = ("unknown" if g["profile_clicks_per_1000_impressions"] is None
                else str(g["profile_clicks_per_1000_impressions"]))
        lines.append(f"| {g['source']} | {g['sample_count']} | {median} | {rate} |")
    lines.extend(["", report["interpretation"], "",
                  "Account-level followers are never attributed to individual replies.",
                  "A missing metric is unknown, not zero. Group comparisons require "
                  "matching window, account, organic status and metric definition.",
                  "", "## Next decision (manual approval required)",
                  report["next_experiment"]["recommendation"],
                  "Select a real, evidenced topic before running content_route.py.",
                  "This report cannot authorize production, publication or strategy changes.",
                  ""])
    if report["skipped"]:
        lines.extend(["## Skipped records", ""])
        lines.extend(f"- {k}: {v}" for k, v in sorted(report["skipped"].items()))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "analyze", "route"))
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--account", default="x-superplay-english")
    parser.add_argument("--window", default="T+24H", choices=WINDOWS)
    parser.add_argument("--topic", help="Founder-approved topic for routing")
    parser.add_argument("--reviewer", help="Human reviewer name for route")
    parser.add_argument("--confirm", action="store_true", help="Explicitly create a draft routing run")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = initialize(args.data_dir)
        elif args.command == "route":
            _guard_local(args.data_dir)
            latest = args.data_dir / "learning" / "latest.json"
            if not args.confirm or not args.topic or not args.reviewer:
                raise ValueError("route requires --confirm, --topic and --reviewer")
            if not latest.is_file():
                raise ValueError("run analyze first; no local learning brief")
            evidence = json.loads(latest.read_text(encoding="utf-8"))
            if evidence.get("account") != args.account or evidence.get("schema") != "contentops.local-learning-brief/v1":
                raise ValueError("learning brief account/schema mismatch")
            command = [sys.executable, str(ROOT / "scripts" / "content_route.py"),
                       "start", "--account", args.account, "--mode", "topic", "--topic", args.topic]
            run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=60)
            print(run.stdout or run.stderr)
            return run.returncode
        else:
            result = analyze(args.data_dir, args.account, args.window)
            out = args.data_dir / "learning"
            out.mkdir(parents=True, exist_ok=True)
            (out / "latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (out / "latest.md").write_text(_markdown(result), encoding="utf-8")
            result["local_report"] = str(out / "latest.md")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, csv.Error) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc), "network_used": False},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
