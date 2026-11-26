#!/usr/bin/env python3
"""Series-level descriptive learning, using the existing native metrics contract."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from datetime import date, timedelta

import editorial_ops as ops
import platform_learning_loop as learning

FIELDS = ("content_id", "post_url", "experiment_id", "series")
MIN_SAMPLES = 5


def init(directory):
    directory = ops.init(directory)
    p = ops.safe_file(directory, "series-links.csv")
    if not p.exists():
        with p.open("x", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(FIELDS)


def assignments(directory, experiment):
    path = ops.safe_file(ops.local_dir(directory), "series-links.csv")
    if path.stat().st_size > 5_000_000:
        raise ValueError("series links too large")
    result = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(FIELDS):
            raise ValueError("invalid series link columns")
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError("malformed series link")
            if row["experiment_id"] != experiment:
                continue
            ops.required(row, FIELDS)
            if not learning._url(row["post_url"]):
                raise ValueError("invalid post URL")
            key = (row["content_id"], row["post_url"])
            if key in result:
                raise ValueError("duplicate series assignment")
            result[key] = ops.slug(row["series"])
    if not result:
        raise ValueError("no selected experiment assignments")
    return result


def review(directory, metrics, *, experiment, platform, account, content_format,
           topic, window, definition, primary, interest):
    ops.slug(experiment)
    ops.account_allows(account, platform)
    directory = ops.local_dir(directory)
    metrics = ops.local_dir(metrics)
    for name in ("content-index.csv", "metric-snapshots.csv"):
        ops.safe_file(metrics, name)
    mapping = assignments(directory, experiment)
    data = learning.analyze(metrics, platform=platform, account=account, content_format=content_format,
                            topic_cluster=topic, window=window, metric_name=primary,
                            definition=definition, interest_metric=interest,
                            experiment_id=experiment, variant_labels=mapping)
    groups = []
    for item in data["groups"]:
        row = dict(item)
        row["series"] = row.pop("variant")
        row["review_status"] = ("ELIGIBLE_FOR_HUMAN_COMPARISON"
                                if row["sample_count"] >= MIN_SAMPLES and row["valid_rate_samples"] >= MIN_SAMPLES
                                else "INSUFFICIENT_DATA")
        groups.append(row)
    eligible = [r for r in groups if r["review_status"] == "ELIGIBLE_FOR_HUMAN_COMPARISON"]
    eligible.sort(key=lambda r: (-r["median_interest_per_1000_post"], r["series"]))
    result = {"schema": "contentops.series-review/v1", "status": data["status"],
              "experiment_id": experiment, "account": account, "platform": platform,
              "format": content_format, "topic": topic, "window": window,
              "definition": definition, "primary": primary, "interest": interest,
              "groups": groups, "skipped": data["skipped"], "input_sha256": data["input_sha256"],
              "assignment_sha256": hashlib.sha256(json.dumps(sorted((k[0], k[1], v) for k, v in mapping.items())).encode()).hexdigest(),
              "research_priority": eligible[0]["series"] if data["status"] == "DESCRIPTIVE_ONLY"
              and len(eligible) >= 2 and eligible[0]["median_interest_per_1000_post"] >
              eligible[1]["median_interest_per_1000_post"] else None,
              "next_action": "HUMAN_REVIEW_REQUIRED", "publish_authorized": False,
              "finding": "Compare comparable observations and founder effort. New episodes need new evidence; no causal claim or automatic repetition."}
    ops.write_atomic(directory, "series-review.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def schedule(directory, *, series, account, platform, content_format, start, end, weekly_target):
    """Series planning over the current queue; no publication or historical evidence claim."""
    for value in (series, account, platform):
        ops.slug(value)
    ops.account_allows(account, platform)
    if content_format not in ops.FORMATS:
        raise ValueError("unsupported format")
    if type(weekly_target) is not int or not 1 <= weekly_target <= 35:
        raise ValueError("weekly target must be 1..35")
    begin, finish = date.fromisoformat(start), date.fromisoformat(end)
    days = (finish - begin).days + 1
    if not 1 <= days <= 84 or days % 7:
        raise ValueError("select 1..12 complete seven-day planning windows")
    directory = ops.local_dir(directory)
    plan = ops.plan(directory)
    scoped = [q for q in plan["queue"] if
              (q["series"], q["account"], q["platform"], q["format"]) ==
              (series, account, platform, content_format)]
    scoped.sort(key=lambda q: (q["planned_date"], q["id"]))
    prior_urls, episodes = set(), []
    weeks = [{"start": (begin+timedelta(days=i)).isoformat(),
              "end": (begin+timedelta(days=i+6)).isoformat(),
              "target": weekly_target, "planned": 0, "eligible_unrouted": 0,
              "route_receipts": 0} for i in range(0, days, 7)]
    for q in scoped:
        day = date.fromisoformat(q["planned_date"])
        if day > finish:
            break
        urls = set(q["source_urls"])
        new_urls = urls - prior_urls
        if day < begin:
            prior_urls.update(urls)
            continue
        week = weeks[(day-begin).days//7]
        week["planned"] += 1
        routed = ops.safe_file(directory, "route-"+q["id"]+".json").exists()
        eligible = q["decision"] in {"CANDIDATE", "LOW_COST_VALIDATION"}
        if routed:
            status = "ROUTE_RECEIPT_EXISTS"
            week["route_receipts"] += 1
        elif not eligible:
            status = q["decision"]
        else:
            status = "NEW_SOURCE_REVIEW" if new_urls else "REUSED_SOURCE_REVIEW"
            week["eligible_unrouted"] += 1
        episodes.append({"candidate_id": q["id"], "topic": q["topic"],
                         "angle": q["angle"], "date": q["planned_date"], "status": status,
                         "cost_lane": q["cost_lane"], "estimated_minutes": int(q["minutes"]),
                         "source_url_count": len(urls), "new_source_url_count": len(new_urls),
                         "evidence_review": "NO_SOURCE" if not urls else
                                            "NEW_URL_PRESENT" if new_urls else "REUSED_URLS_ONLY",
                         "publish_authorized": False})
        prior_urls.update(urls)
    for week in weeks:
        week["planning_gap"] = max(0, weekly_target-week["planned"])
    return {"schema": "contentops.series-schedule/v1", "status": "ADVISORY_ONLY",
            "series": series, "account": account, "platform": platform, "format": content_format,
            "start": start, "end": end, "weeks": weeks, "episodes": episodes,
            "plan_sha256": hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            "limitations": "Current queue source URLs are topic-level, not historical episode evidence. "
                           "A new URL is not a verified new fact; a route receipt is not publication. "
                           "Same-day ordering is deterministic by candidate ID, not actual production order.",
            "production_ready": False, "publish_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("init", "review", "schedule"))
    p.add_argument("--data-dir", type=Path, default=ops.DEFAULT)
    p.add_argument("--metrics-dir", type=Path, default=learning.DEFAULT_DATA)
    for name in ("experiment", "platform", "account", "format", "topic"):
        p.add_argument("--" + name)
    p.add_argument("--series")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--weekly-target", type=int)
    p.add_argument("--window", default="T+24H", choices=learning.WINDOW_HOURS)
    p.add_argument("--definition", default="native_v1")
    p.add_argument("--primary", default="views_or_reads", choices=learning.METRICS)
    p.add_argument("--interest", default="saves", choices=learning.RATE_METRICS)
    a = p.parse_args(argv)
    try:
        if a.command == "init":
            init(a.data_dir)
            print("READY: series-links.csv")
        elif a.command == "schedule":
            if not all((a.series, a.account, a.platform, a.format, a.start, a.end)) or a.weekly_target is None:
                raise ValueError("series, account, platform, format, start, end and weekly target required")
            result = schedule(a.data_dir, series=a.series, account=a.account, platform=a.platform,
                              content_format=a.format, start=a.start, end=a.end, weekly_target=a.weekly_target)
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            if not all((a.experiment, a.platform, a.account, a.format, a.topic)):
                raise ValueError("experiment, platform, account, format, topic required")
            print(review(a.data_dir, a.metrics_dir, experiment=a.experiment, platform=a.platform,
                         account=a.account, content_format=a.format, topic=a.topic,
                         window=a.window, definition=a.definition, primary=a.primary,
                         interest=a.interest)["status"])
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
