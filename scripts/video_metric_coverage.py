#!/usr/bin/env python3
"""Audit video metric readiness; never infer organic traffic from public counters."""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import editorial_ops as ops
import platform_learning_loop as learning

METRICS = ("impressions", "views_or_reads", "ctr", "avg_watch_time",
           "completion_or_retention", "likes", "comments", "saves", "shares",
           "qualified_signals", "founder_hours")
NATIVE = {"native_manual", "native_export", "official_api"}


def report(directory, *, platform, account, topic, experiment, window, definition):
    if platform not in {"douyin", "bilibili"}:
        raise ValueError("video coverage pilot: douyin or bilibili")
    ops.account_allows(account, platform)
    for value in (topic, experiment, definition):
        ops.slug(value)
    if window not in learning.WINDOW_HOURS:
        raise ValueError("unsupported observation window")
    directory = ops.local_dir(directory)
    ix = ops.safe_file(directory, "content-index.csv")
    ms = ops.safe_file(directory, "metric-snapshots.csv")
    def fingerprint():
        return hashlib.sha256(ix.read_bytes() + ms.read_bytes()).hexdigest()
    # Bound size before reading bytes.
    if any(p.stat().st_size > 25_000_000 for p in (ix, ms)):
        raise ValueError("input too large")
    before = fingerprint()
    index = learning._load(ix, learning.INDEX_COLUMNS)
    snapshots = learning._load(ms, learning.SNAPSHOT_COLUMNS)
    posts = [p for p in index if (p["platform"], p["account_alias"], p["content_format"],
             p["topic_cluster"], p["experiment_id"]) == (platform, account, "video", topic, experiment)]
    ids = Counter(p["content_id"] for p in posts)
    urls = Counter(p["post_url"].rstrip("/") for p in posts)
    matched = defaultdict(list)
    for s in snapshots:
        if (s["platform"], s["account_alias"], s["content_format"], s["window"],
                s["metric_definition_version"]) == (platform, account, "video", window, definition):
            matched[(s["content_id"], s["post_url"])].append(s)
    reasons = Counter()
    coverage = {name: {"observed": 0, "organic_eligible": 0} for name in METRICS}
    output = []
    low, high = learning.WINDOW_HOURS[window]
    for p in posts:
        cid, url = p["content_id"], p["post_url"]
        published = learning._date(p["published_at"])
        rows = matched[(cid, url)]
        status, observed_metrics, organic_metrics = "", [], []
        if not cid or not learning._url(url) or not published or p["publish_status"] not in learning.VALID_STATUS:
            status = "INVALID_PUBLICATION"
        elif ids[cid] != 1 or urls[url.rstrip("/")] != 1:
            status = "DUPLICATE_PUBLICATION"
        elif not rows:
            status = "MISSING_SNAPSHOT"
        elif len(rows) != 1:
            status = "DUPLICATE_SNAPSHOT"
        else:
            s = rows[0]
            observed = learning._date(s["observed_at"])
            if (not observed or learning._date(s["published_at"]) != published or
                    s["experiment_id"] != experiment or not low <=
                    (observed-published).total_seconds()/3600 <= high):
                status = "IDENTITY_OR_AGE_MISMATCH"
            elif (s["metric_source"] not in NATIVE | {"api_public"} or
                  s["data_access"] not in {"available", "partial"}):
                status = "UNSUPPORTED_SOURCE"
            else:
                observed_metrics = [m for m in METRICS if learning._metric(s.get(m, "")) is not None]
                if s["metric_source"] in NATIVE and s["organic_paid"] == "organic":
                    status = "ORGANIC_OBSERVATION"
                    organic_metrics = observed_metrics.copy()
                else:
                    status = "OBSERVATION_ONLY"
                for m in observed_metrics:
                    coverage[m]["observed"] += 1
                for m in organic_metrics:
                    coverage[m]["organic_eligible"] += 1
        reasons[status] += 1
        output.append({"content_id": cid, "post_url": url, "status": status,
                       "observed_metrics": observed_metrics,
                       "missing_organic_metrics": [m for m in METRICS if m not in organic_metrics]})
    if before != fingerprint():
        raise ValueError("metric inputs changed during audit")
    return {"schema": "contentops.video-metric-coverage/v1", "scope": {
                "platform": platform, "account": account, "topic": topic,
                "experiment": experiment, "window": window, "definition": definition},
            "input_sha256": before, "publication_rows": len(posts),
            "reasons": dict(reasons), "coverage": coverage, "works": output,
            "status": "DATA_GAP_REVIEW_REQUIRED",
            "limitations": "Counts are coverage only, not growth or cohort comparability. "
                           "Public/cumulative or unknown paid/organic observations are never organic benchmark inputs. "
                           "A separately sourced native organic snapshot needs its own documented definition; "
                           "do not relabel imported counters.",
            "publish_authorized": False, "network_used": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--metrics-dir", type=Path, default=learning.DEFAULT_DATA)
    for k in ("platform", "account", "topic", "experiment", "definition"):
        p.add_argument("--"+k, required=True)
    p.add_argument("--window", choices=learning.WINDOW_HOURS, default="T+24H")
    a = p.parse_args()
    try:
        print(json.dumps(report(a.metrics_dir, **{k: getattr(a,k) for k in
              ("platform", "account", "topic", "experiment", "window", "definition")}),
              ensure_ascii=True, indent=2, allow_nan=False))
    except (OSError, ValueError, TypeError) as exc:
        p.exit(4, "BLOCKED: "+str(exc)+"\n")


if __name__ == "__main__":
    main()
