#!/usr/bin/env python3
"""Local-only X metrics -> descriptive analysis -> human-reviewed learning brief.

Reads the existing X CSV contracts. No X login, scraping, remote upload,
publication, follower attribution, or automatic production changes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from process_utils import hidden_run, python_executable

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "x-growth-en"
DEFAULT_DATA = ROOT / ".local" / "x-growth-en"
FILES = ("posts.csv", "x-metric-snapshots.csv", "x-account-snapshots.csv")
CONTEXT_FILE = "x-experiment-context.csv"
CONTEXT_COLUMNS = ("content_id", "x_post_url", "experiment_id", "topic_cluster", "language", "founder_minutes", "qualified_conversations")
SCOPE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
DECISIONS = ("CONTINUE", "ADJUST", "PAUSE", "INCONCLUSIVE")
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


def _nonnegative_float(value: str):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def _valid_http_source(value: str):
    try:
        parsed = urlparse(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password
    except (TypeError, ValueError):
        return False


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
    context_path = data_dir / CONTEXT_FILE
    if not context_path.exists():
        with context_path.open("x", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerow(CONTEXT_COLUMNS)
        created.append(CONTEXT_FILE)
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


def analyze(data_dir: Path, account: str, window: str, *, experiment_id=None,
            topic_cluster=None, language=None, definition=None, compare=False):
    _guard_local(data_dir)
    if window not in WINDOWS:
        raise ValueError("unsupported metric window")
    scope = (experiment_id, topic_cluster, language, definition)
    if compare and (not all(scope) or not all(SCOPE_PATTERN.fullmatch(v) for v in scope)):
        raise ValueError("--compare requires valid --experiment-id --topic-cluster --language --definition")
    if not SCOPE_PATTERN.fullmatch(account):
        raise ValueError("invalid account alias")
    controlled = compare and all(scope)
    if controlled:
        profile_path = ROOT / "config" / "accounts" / (account + ".json")
        if not profile_path.is_file():
            raise ValueError("registered X account DNA required for a controlled comparison")
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        if (profile.get("slug") != account or profile.get("language") != language or
                "x" not in (profile.get("platforms") or [])):
            raise ValueError("experiment language/account does not match registered X DNA")
    contexts = _read_table(data_dir / CONTEXT_FILE, CONTEXT_COLUMNS) if controlled else []
    context_index = {}
    for ctx in contexts:
        key = (ctx["content_id"], ctx["x_post_url"])
        if key in context_index:
            context_index[key] = None  # ambiguous, do not count
        else:
            context_index[key] = ctx
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
        if controlled:
            key = (post.get("content_id"), post.get("x_post_url"))
            ctx = context_index.get(key)
            if ctx is None:
                skipped["missing_or_duplicate_experiment_context"] += 1
                continue
            if (ctx["experiment_id"], ctx["topic_cluster"], ctx["language"]) != (experiment_id, topic_cluster, language):
                continue
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
        if controlled and record.get("metric_definition_version") != definition:
            skipped["metric_definition_mismatch"] += 1
            continue
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
        ctx = context_index.get(key) if controlled else None
        minutes = _nonnegative_float(ctx["founder_minutes"]) if ctx else None
        quality = _integer(ctx["qualified_conversations"]) if ctx else None
        collected[eligible[key]].append((impressions, clicks, minutes, quality))
    groups = []
    for name in GROUPS:
        items = collected[name]
        complete = [(views, clicks) for views, clicks, _, _ in items if clicks is not None]
        positive = [(views, clicks) for views, clicks in complete if views > 0]
        per_post_rates = [clicks * 1000 / views for views, clicks in positive]
        work = [(mins, quality) for _, _, mins, quality in items
                if mins is not None and mins > 0 and quality is not None]
        total_complete_views = sum(views for views, _ in positive)
        groups.append({
            "source": name,
            "sample_count": len(items),
            "median_impressions": statistics.median(x[0] for x in items) if items else None,
            "total_impressions": sum(x[0] for x in items) if items else None,
            "median_profile_clicks_per_1000": round(statistics.median(per_post_rates), 3) if per_post_rates else None,
            "quality_per_founder_hour": round(sum(q for _, q in work) * 60 / sum(m for m, _ in work), 3) if work else None,
            "work_samples": len(work),
            "profile_click_samples": len(complete),
            "valid_rate_samples": len(positive),
            "profile_clicks_per_1000_impressions": (
                round(sum(clicks for _, clicks in positive) * 1000 / total_complete_views, 3)
                if complete and total_complete_views > 0 else None),
            "profile_clicks_missing": len(items) - len(complete)
        })
    by_source = {g["source"]: g for g in groups}
    bc_ready = all(by_source[g]["sample_count"] >= 5 and by_source[g]["valid_rate_samples"] >= 5
                   for g in ("inspiration_ai", "timeline_ai"))
    status = ("EXPLORATORY_ONLY" if not controlled else
              "DESCRIPTIVE_ONLY" if bc_ready else "INSUFFICIENT_DATA")
    b = by_source["inspiration_ai"]["median_profile_clicks_per_1000"]
    c = by_source["timeline_ai"]["median_profile_clicks_per_1000"]
    if status == "DESCRIPTIVE_ONLY" and b is not None and c is not None:
        difference = "timeline_ai" if c > b else "inspiration_ai" if b > c else "equal"
        suggestion = ("Observed higher median post-level interest in " + difference +
                      "; review source, topic matching and time cost; do not infer causal lift.")
    else:
        suggestion = "Hold the source-allocation decision; collect matched B/C observations with complete profile clicks."
    input_digest = hashlib.sha256()
    for filename in (*FILES, CONTEXT_FILE):
        input_digest.update((data_dir / filename).read_bytes() if (data_dir / filename).exists() else b"")
    return {
        "schema": "contentops.local-learning-brief/v1",
        "input_sha256": input_digest.hexdigest(),
        "status": status, "account": account, "platform": "x", "window": window,
        "scope": {"experiment_id": experiment_id, "topic_cluster": topic_cluster,
                  "language": language, "metric_definition_version": definition},
        "comparison_controlled": controlled,
        "report_id": "XL-" + hashlib.sha256(json.dumps([account, window, scope, groups, input_digest.hexdigest()], sort_keys=True).encode()).hexdigest()[:16],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "USER_SUPPLIED_LOCAL_CSV_UNVERIFIED",
        "groups": groups, "skipped": dict(skipped),
        "account_context": _account_context(accounts, account),
        "interpretation": ("Matched B/C groups each have >=5 complete post-level observations. "
                           "Difference is descriptive, not causal." if status == "DESCRIPTIVE_ONLY" else
                           "Exploratory summary only: require --compare and four matching context dimensions."
                           if status == "EXPLORATORY_ONLY" else
                           "Not enough matching B/C reply observations with nonmissing clicks."),
        "next_experiment": {
            "primary_variable": "discovery_source",
            "recommendation": suggestion,
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
             "| Discovery source | Samples | Median impressions | Median clicks / 1k per post | Pooled clicks / 1k | Quality / founder hour |",
             "|---|---:|---:|---:|---:|---:|"]
    for g in report["groups"]:
        median = "unknown" if g["median_impressions"] is None else str(g["median_impressions"])
        rate = ("unknown" if g["profile_clicks_per_1000_impressions"] is None
                else str(g["profile_clicks_per_1000_impressions"]))
        lines.append(f"| {g['source']} | {g['sample_count']} | {median} | "
                     f"{g['median_profile_clicks_per_1000'] if g['median_profile_clicks_per_1000'] is not None else 'unknown'} | "
                     f"{rate} | {g['quality_per_founder_hour'] if g['quality_per_founder_hour'] is not None else 'unknown'} |")
    lines.extend(["", f"Report ID: {report['report_id']} | Scope: {report['scope']}",
                  report["interpretation"], "",
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
    parser.add_argument("--experiment-id")
    parser.add_argument("--topic-cluster")
    parser.add_argument("--language")
    parser.add_argument("--definition")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--report-id")
    parser.add_argument("--decision", choices=DECISIONS)
    parser.add_argument("--evidence-url")
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
            if not all((args.confirm, args.topic, args.reviewer, args.report_id,
                        args.decision, args.evidence_url)):
                raise ValueError("route requires --confirm --topic --reviewer --report-id --decision --evidence-url")
            if not _valid_http_source(args.evidence_url):
                raise ValueError("evidence URL must be HTTPS without credentials")
            if not latest.is_file():
                raise ValueError("run analyze first; no local learning brief")
            evidence = json.loads(latest.read_text(encoding="utf-8"))
            if (evidence.get("account") != args.account or evidence.get("schema") != "contentops.local-learning-brief/v1"
                    or evidence.get("report_id") != args.report_id or not evidence.get("comparison_controlled")):
                raise ValueError("learning brief account/schema mismatch")
            if evidence.get("status") != "DESCRIPTIVE_ONLY" or args.decision not in ("CONTINUE", "ADJUST"):
                raise ValueError("only comparable reviewed reports can route approved CONTINUE/ADJUST")
            profile_path = ROOT / "config" / "accounts" / (args.account + ".json")
            if not profile_path.is_file():
                raise ValueError("X account profile is not registered")
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            if profile.get("slug") != args.account or "x" not in (profile.get("platforms") or []):
                raise ValueError("report account does not match authorized X profile")
            command = [python_executable(), str(ROOT / "scripts" / "content_route.py"),
                       "start", "--account", args.account, "--mode", "topic", "--topic", args.topic,
                       "--url", args.evidence_url, "--by", args.reviewer]
            run = hidden_run(command, cwd=str(ROOT), timeout=60)
            print(run.stdout or run.stderr)
            return run.returncode
        else:
            result = analyze(args.data_dir, args.account, args.window, experiment_id=args.experiment_id,
                             topic_cluster=args.topic_cluster, language=args.language,
                             definition=args.definition, compare=args.compare)
            out = args.data_dir / "learning"
            out.mkdir(parents=True, exist_ok=True)
            (out / "latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (out / "latest.md").write_text(_markdown(result), encoding="utf-8")
            history = out / "history"
            history.mkdir(parents=True, exist_ok=True)
            archive = history / (result["report_id"] + ".json")
            if not archive.exists():
                archive.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result["local_report"] = str(out / "latest.md")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, csv.Error) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc), "network_used": False},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
