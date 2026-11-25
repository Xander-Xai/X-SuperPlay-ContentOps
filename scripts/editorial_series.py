#!/usr/bin/env python3
"""Series-level descriptive learning, using the existing native metrics contract."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

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


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("init", "review"))
    p.add_argument("--data-dir", type=Path, default=ops.DEFAULT)
    p.add_argument("--metrics-dir", type=Path, default=learning.DEFAULT_DATA)
    for name in ("experiment", "platform", "account", "format", "topic"):
        p.add_argument("--" + name)
    p.add_argument("--window", default="T+24H", choices=learning.WINDOW_HOURS)
    p.add_argument("--definition", default="native_v1")
    p.add_argument("--primary", default="views_or_reads", choices=learning.METRICS)
    p.add_argument("--interest", default="saves", choices=learning.RATE_METRICS)
    a = p.parse_args(argv)
    try:
        if a.command == "init":
            init(a.data_dir)
            print("READY: series-links.csv")
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
