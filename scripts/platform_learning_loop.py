#!/usr/bin/env python3
"""Local-only cross-platform learning; no API, login, scraping or publishing.

The snapshot columns mirror Strategy/90-Templates/metric-snapshot.yaml.
A tiny local content index adds discovery context; it does not redefine metrics.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from urllib.parse import urlparse

from process_utils import hidden_run, python_executable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / ".local" / "platform-learning"
INDEX_COLUMNS = (
    "content_id", "platform", "account_alias", "content_format", "discovery_source",
    "topic_cluster", "experiment_id", "post_url", "published_at", "publish_status")
SNAPSHOT_COLUMNS = (
    "metric_snapshot_id", "content_id", "experiment_id", "platform", "observed_at",
    "published_at", "post_url", "account_alias", "content_format", "window",
    "metric_source", "metric_definition_version", "data_access", "missing_reason",
    "organic_paid", "timezone", "denominator_available", "impressions", "reach",
    "views_or_reads", "ctr", "avg_watch_time", "completion_or_retention",
    "likes", "comments", "saves", "shares", "profile_visits", "follows",
    "follows_attributed", "account_net_follower_change", "dms",
    "external_clicks", "github_actions", "qualified_signals", "founder_hours", "notes")
METRICS = ("impressions", "views_or_reads", "reach", "saves", "shares",
           "profile_visits", "qualified_signals", "external_clicks")
RATE_METRICS = ("profile_visits", "saves", "shares", "qualified_signals",
                "external_clicks")
WINDOW_HOURS = {"T+24H": (18, 36), "T+72H": (60, 84), "T+7D": (144, 192)}
VALID_STATUS = {"published", "reported_published", "verified_published"}
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SCHEMA = "contentops.platform-learning/v1"
DECISIONS = ("CONTINUE", "ADJUST", "PAUSE", "INCONCLUSIVE")


def _safe_slug(value, label):
    if not SLUG.fullmatch(value or ""):
        raise ValueError(f"{label}: use a lowercase slug (letters, digits, '-' or '_')")
    return value


def _local_guard(path: Path):
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(ROOT.resolve())
    except ValueError:
        return
    if not relative.parts or relative.parts[0] != ".local":
        raise ValueError("inside repository, raw metrics must live under ignored .local/")


def _date(value):
    try:
        stamp = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        return stamp if stamp.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None


def _metric(value):
    if value is None or not value.strip():
        return None
    try:
        result = float(value)
        if result >= 0 and result != float("inf") and result == result:
            return result
    except (ValueError, TypeError):
        pass
    return None


def _url(value):
    try:
        parsed = urlparse(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and not (
            parsed.username or parsed.password) and not parsed.fragment
    except (ValueError, TypeError):
        return False


def _load(path: Path, required):
    if not path.is_file():
        raise ValueError(f"local input missing: {path.name}; run init")
    if path.stat().st_size > 25_000_000:
        raise ValueError(f"input too large: {path.name}")
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise ValueError(f"wrong CSV columns in {path.name}")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError(f"malformed CSV in {path.name}")
    return rows


def initialize(directory: Path):
    _local_guard(directory)
    directory.mkdir(parents=True, exist_ok=True)
    created = []
    for name, columns in (("content-index.csv", INDEX_COLUMNS),
                          ("metric-snapshots.csv", SNAPSHOT_COLUMNS)):
        file = directory / name
        if file.exists():
            continue
        with file.open("x", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(columns)
        created.append(name)
    return {"schema": SCHEMA, "status": "READY", "created": created,
            "local_path": str(directory), "external_action": "none"}


def analyze(directory: Path, *, platform: str, account: str, content_format: str,
            topic_cluster: str, window: str, metric_name: str,
            definition: str, interest_metric: str):
    _local_guard(directory)
    for label, value in (("platform", platform), ("account", account),
                         ("format", content_format), ("topic", topic_cluster),
                         ("definition", definition)):
        _safe_slug(value, label)
    if window not in WINDOW_HOURS or metric_name not in METRICS or interest_metric not in RATE_METRICS:
        raise ValueError("unsupported metric/window selection")
    if metric_name == interest_metric:
        raise ValueError("primary and interest metrics must differ")
    index = _load(directory / "content-index.csv", INDEX_COLUMNS)
    snapshots = _load(directory / "metric-snapshots.csv", SNAPSHOT_COLUMNS)
    candidates = {}
    skipped = Counter()
    for item in index:
        if (item["platform"], item["account_alias"], item["content_format"],
                item["topic_cluster"]) != (platform, account, content_format, topic_cluster):
            continue
        source = item.get("discovery_source", "")
        if not SLUG.fullmatch(source or ""):
            skipped["invalid_discovery_source"] += 1
            continue
        if item["publish_status"] not in VALID_STATUS:
            skipped["not_published"] += 1
            continue
        if not _date(item["published_at"]) or not _url(item["post_url"]):
            skipped["invalid_publication"] += 1
            continue
        key = (item["content_id"], item["post_url"])
        if not item["content_id"] or key in candidates:
            skipped["duplicate_or_blank_content"] += 1
            candidates[key] = None
            continue
        candidates[key] = item
    matched = defaultdict(list)
    for snapshot in snapshots:
        if (snapshot.get("platform"), snapshot.get("account_alias"),
                snapshot.get("content_format"), snapshot.get("window"),
                snapshot.get("metric_definition_version")) != (
                    platform, account, content_format, window, definition):
            continue
        key = (snapshot.get("content_id"), snapshot.get("post_url"))
        if key in candidates and candidates[key] is not None:
            matched[key].append(snapshot)
    grouped = defaultdict(list)
    for key, records in matched.items():
        if len(records) != 1:
            skipped["duplicate_snapshot"] += 1
            continue
        post, snap = candidates[key], records[0]
        published, observed = _date(post["published_at"]), _date(snap["observed_at"])
        if (not published or not observed or
                not WINDOW_HOURS[window][0] <=
                (observed - published).total_seconds() / 3600 <= WINDOW_HOURS[window][1]):
            skipped["wrong_age_window"] += 1
            continue
        if (snap.get("published_at") and
                _date(snap["published_at"]) != published):
            skipped["publication_timestamp_mismatch"] += 1
            continue
        if post["experiment_id"] and snap["experiment_id"] != post["experiment_id"]:
            skipped["experiment_mismatch"] += 1
            continue
        if (snap["organic_paid"] != "organic"
                or snap["data_access"] not in {"available", "partial"}
                or snap["metric_source"] not in {"native_manual", "native_export", "official_api"}):
            skipped["paid_or_unverifiable_snapshot"] += 1
            continue
        primary = _metric(snap[metric_name])
        interest = _metric(snap[interest_metric])
        if primary is None:
            skipped["missing_primary_metric"] += 1
            continue
        if interest is not None and (primary == 0 and interest > 0):
            skipped["invalid_denominator"] += 1
            continue
        hours = _metric(snap.get("founder_hours", ""))
        quality = _metric(snap.get("qualified_signals", ""))
        grouped[post["discovery_source"]].append((primary, interest, hours, quality))
    groups = []
    for surface, items in sorted(grouped.items()):
        with_interest = [(p, i) for p, i, _, _ in items if i is not None]
        positive = [(p, i) for p, i in with_interest if p > 0]
        work = [(h, q) for _, _, h, q in items if h is not None and h > 0 and q is not None]
        denominator = sum(p for p, _ in positive)
        post_rates = [i * 1000 / p for p, i in positive]
        groups.append({
            "discovery_source": surface, "sample_count": len(items),
            "median_primary": median(p for p, _, _, _ in items),
            "total_primary": sum(p for p, _, _, _ in items),
            "median_interest_per_1000_post": round(median(post_rates), 3) if post_rates else None,
            "qualified_signals_per_hour": round(sum(q for _, q in work) / sum(h for h, _ in work), 3) if work else None,
            "effort_sample_count": len(work),
            "interest_sample_count": len(with_interest),
            "valid_rate_samples": len(positive),
            "missing_interest": len(items) - len(with_interest),
            "interest_per_1000_primary": round(
                sum(i for _, i in positive) * 1000 / denominator, 3
            ) if denominator > 0 else None,
        })
    compared = [g for g in groups if g["sample_count"] >= 5 and g["valid_rate_samples"] >= 5]
    status = "DESCRIPTIVE_ONLY" if len(compared) >= 2 else "INSUFFICIENT_DATA"
    leaders = sorted(compared, key=lambda item: (item["median_interest_per_1000_post"] if item["median_interest_per_1000_post"] is not None else -1), reverse=True)
    recommendation = ("Observed higher post-median interest for " + leaders[0]["discovery_source"] +
                      " (descriptive only). Review confounders and founder-hours before continuing one-variable experiment."
                      if status == "DESCRIPTIVE_ONLY" else
                      "Keep discovery-source allocation unchanged until two groups have five complete comparable observations.")
    input_digest = hashlib.sha256()
    for filename in ("content-index.csv", "metric-snapshots.csv"):
        input_digest.update((directory / filename).read_bytes())
    return {
        "schema": SCHEMA, "status": status, "platform": platform,
        "input_sha256": input_digest.hexdigest(),
        "report_id": "PL-" + hashlib.sha256(json.dumps([platform, account, content_format, topic_cluster, window, definition, groups, input_digest.hexdigest()], sort_keys=True).encode()).hexdigest()[:16],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account_alias": account, "content_format": content_format,
        "topic_cluster": topic_cluster, "metric_definition_version": definition,
        "window": window, "primary_metric": metric_name,
        "interest_metric": interest_metric, "groups": groups,
        "skipped": dict(skipped), "data_origin": "LOCAL_USER_SUPPLIED_UNVERIFIED",
        "source_interpretation": "Discovery source is where the author found the topic, "
                                 "NOT official platform traffic attribution.",
        "finding": ("Group differences are descriptive, not proof of algorithmic "
                    "boosts, user attribution or causality." if status == "DESCRIPTIVE_ONLY"
                    else "At least two sources need >=5 comparable published organic snapshots."),
        "handoff": {
            "status": "HUMAN_REVIEW_REQUIRED", "proposed_topic": None,
            "next_variable": "discovery_source", "recommendation": recommendation,
            "production_authorized": False},
        "network_used": False, "published": False
    }


def _report_markdown(result):
    lines = [
        "# Cross-platform learning brief (local)", "",
        f"**{result['platform']} / {result['account_alias']} / "
        f"{result['content_format']} / {result['topic_cluster']}**",
        f"Window: {result['window']}; primary: {result['primary_metric']}; "
        f"interest: {result['interest_metric']}",
        f"Metric definition: {result['metric_definition_version']}",
        f"Status: {result['status']}; local data is not externally verified.", "",
        "| Discovery source | N | Median primary | Interest / 1,000 primary |",
        "|---|---:|---:|---:|"]
    for row in result["groups"]:
        rate = row["interest_per_1000_primary"]
        lines.append(f"| {row['discovery_source']} | {row['sample_count']} | "
                     f"{row['median_primary']} | {rate if rate is not None else 'unknown'} |")
    lines += ["", result["finding"], "", result["source_interpretation"], "",
              "Primary metrics across different platforms or formats are not interchangeable.",
              "Missing metrics are unknown, not zero; account follower change is never "
              "attributed to a single post.", "",
              "## Decision", "Requires explicit founder review, a real evidence source, "
              "and a separate topic-route step. No autopublish."]
    return "\n".join(lines) + "\n"


def handoff(directory: Path, *, account_profile: str, topic: str,
            reviewer: str, evidence_url: str, report_id: str = "", decision: str = ""):
    _local_guard(directory)
    _safe_slug(account_profile, "account-profile")
    latest = directory / "learning" / "latest.json"
    if not latest.is_file():
        raise ValueError("analyze first; latest Learning Brief not found")
    report = json.loads(latest.read_text(encoding="utf-8"))
    if report.get("schema") != SCHEMA or report.get("report_id") != report_id:
        raise ValueError("Learning Brief schema/report-id mismatch")
    if report.get("status") != "DESCRIPTIVE_ONLY" or decision not in ("CONTINUE", "ADJUST"):
        raise ValueError("route requires a comparable report and approved CONTINUE/ADJUST decision")
    if not topic.strip() or not reviewer.strip() or not _url(evidence_url):
        raise ValueError("handoff requires a topic, reviewer and real HTTPS evidence URL")
    profile = ROOT / "config" / "accounts" / (account_profile + ".json")
    if not profile.is_file():
        raise ValueError("account profile is not registered in ContentOps")
    account_spec = json.loads(profile.read_text(encoding="utf-8"))
    if report.get("account_alias") != account_profile or account_spec.get("slug") != account_profile:
        raise ValueError("report account alias does not match route account profile")
    if report.get("platform") not in (account_spec.get("platforms") or []):
        raise ValueError("account profile does not authorize this platform; "
                         "do not route cross-platform learning to an unrelated account")
    cmd = [python_executable(), str(ROOT / "scripts" / "content_route.py"),
           "start", "--account", account_profile, "--mode", "topic", "--topic", topic,
           "--url", evidence_url, "--by", reviewer]
    result = hidden_run(cmd, cwd=str(ROOT), timeout=90)
    receipt = {
        "schema": "contentops.reviewed-learning-handoff/v1",
        "learning_schema": SCHEMA,
        "platform": report["platform"], "account_alias": report["account_alias"],
        "reviewer": reviewer, "evidence_url": evidence_url, "topic": topic,
        "report_id": report_id, "decision": decision,
        "router_account_profile": account_profile,
        "router_exit_code": result.returncode,
        "status": "ROUTED_FOR_HUMAN_REVIEW" if result.returncode == 0 else "ROUTE_BLOCKED",
        "production_authorized": False, "published": False, "network_used": False}
    output = directory / "learning" / "handoff.json"
    output.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "analyze", "route"))
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--platform")
    parser.add_argument("--account")
    parser.add_argument("--format")
    parser.add_argument("--topic-cluster")
    parser.add_argument("--window", default="T+24H", choices=WINDOW_HOURS)
    parser.add_argument("--metric", default="views_or_reads", choices=METRICS)
    parser.add_argument("--interest", default="saves", choices=RATE_METRICS)
    parser.add_argument("--definition", default="native_v1")
    parser.add_argument("--account-profile")
    parser.add_argument("--topic")
    parser.add_argument("--reviewer")
    parser.add_argument("--evidence-url")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--report-id")
    parser.add_argument("--decision", choices=DECISIONS)
    args = parser.parse_args()
    try:
        if args.command == "init":
            result = initialize(args.data_dir)
        elif args.command == "route":
            if not args.confirm or not args.report_id or not args.decision:
                raise ValueError("route requires --confirm --report-id --decision")
            result = handoff(args.data_dir, account_profile=args.account_profile or "",
                             topic=args.topic or "", reviewer=args.reviewer or "",
                             evidence_url=args.evidence_url or "", report_id=args.report_id,
                             decision=args.decision)
        else:
            if not all((args.platform, args.account, args.format, args.topic_cluster)):
                raise ValueError("analyze requires --platform --account --format --topic-cluster")
            result = analyze(args.data_dir, platform=args.platform, account=args.account,
                             content_format=args.format, topic_cluster=args.topic_cluster,
                             window=args.window, metric_name=args.metric,
                             definition=args.definition, interest_metric=args.interest)
            output = args.data_dir / "learning"
            output.mkdir(parents=True, exist_ok=True)
            (output / "latest.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (output / "latest.md").write_text(_report_markdown(result), encoding="utf-8")
            history = output / "history"
            history.mkdir(parents=True, exist_ok=True)
            archive = history / (result["report_id"] + ".json")
            if not archive.exists():
                archive.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") != "ROUTE_BLOCKED" else 2
    except (ValueError, OSError, csv.Error) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc),
                          "network_used": False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
