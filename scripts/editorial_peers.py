#!/usr/bin/env python3
"""Compare public peer observations against same-account, same-format age baselines."""
import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

import editorial_ops as ops
import platform_learning_loop as learning

FIELDS = ("case_id", "peer_alias", "published_at", "definition", "window", "organic_paid")


def init(directory):
    directory = ops.init(directory)
    p = ops.safe_file(directory, "peer-context.csv")
    if not p.exists():
        with p.open("x", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(FIELDS)


def analyze(directory):
    directory = ops.local_dir(directory)
    cases = ops.load(directory, "peers.csv")
    ops.unique(cases, "case_id")
    case_by_id = {r["case_id"]: r for r in cases}
    path = ops.safe_file(directory, "peer-context.csv")
    if path.stat().st_size > 5_000_000:
        raise ValueError("peer context too large")
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(FIELDS):
            raise ValueError("invalid peer context columns")
        context = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in context):
        raise ValueError("malformed peer context")
    ops.unique(context, "case_id")
    grouped = defaultdict(list)
    skipped = defaultdict(int)
    used_urls = set()
    for c in context:
        ops.required(c, FIELDS)
        if c["case_id"] not in case_by_id:
            raise ValueError("unknown peer case")
        p = case_by_id[c["case_id"]]
        ops.validate_source(p)
        ops.slug(c["peer_alias"])
        ops.slug(c["definition"])
        window = c["window"]
        if window not in learning.WINDOW_HOURS:
            raise ValueError("unsupported observation window")
        if c["organic_paid"] != "organic":
            skipped["non_organic_or_unknown"] += 1
            continue
        published = datetime.fromisoformat(c["published_at"].replace("Z", "+00:00"))
        observed = datetime.fromisoformat(p["observed_at"].replace("Z", "+00:00"))
        if published.utcoffset() is None:
            raise ValueError("publication time requires timezone")
        low, high = learning.WINDOW_HOURS[window]
        if not low <= (observed - published).total_seconds() / 3600 <= high:
            skipped["wrong_age"] += 1
            continue
        if p["format"] not in ops.FORMATS or not p["metric_name"] or not p["metric_value"]:
            skipped["missing_metric_or_format"] += 1
            continue
        value = float(p["metric_value"])
        if not math.isfinite(value) or value < 0:
            raise ValueError("invalid observed metric")
        # Account-local baseline; no cross-platform or cross-format comparison.
        key = (p["platform"], c["peer_alias"], p["format"], p["metric_name"], c["definition"], window)
        if (key, p["source_url"]) in used_urls:
            raise ValueError("duplicate peer publication in one cohort")
        used_urls.add((key, p["source_url"]))
        grouped[key].append((p, value))
    results = []
    for key, rows in sorted(grouped.items()):
        for p, value in rows:
            baseline = [v for other, v in rows if other["case_id"] != p["case_id"]]
            med = median(baseline) if len(baseline) >= 5 else None
            ratio = round(value / med, 3) if med is not None and med > 0 else None
            results.append({"case_id": p["case_id"], "source_url": p["source_url"],
                            "topic": p["topic"], "hook": p["hook"], "lesson": p["lesson"],
                            "cohort": dict(zip(("platform", "peer_alias", "format", "metric",
                                                 "definition", "window"), key)),
                            "observed_value": value, "baseline_count": len(baseline),
                            "baseline_median": med, "ratio_to_peer_median": ratio,
                            "status": "OBSERVED_OUTLIER" if ratio is not None and ratio >= 2
                            else "DESCRIPTIVE_ONLY" if ratio is not None else "INSUFFICIENT_BASELINE"})
    results.sort(key=lambda x: (x["ratio_to_peer_median"] is None,
                                -(x["ratio_to_peer_median"] or 0), x["case_id"]))
    report = {"schema": "contentops.peer-observations/v1", "status": "ADVISORY_ONLY",
              "source": "LOCAL_USER_SUPPLIED_UNVERIFIED", "baseline": "leave_one_out_median",
              "threshold": 2, "minimum_other_posts": 5, "results": results,
              "skipped": dict(skipped), "publish_authorized": False,
              "finding": "An observed outlier is a research lead, not proof of a winning hook or causality."}
    ops.write_atomic(directory, "peer-review.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "review"))
    parser.add_argument("--data-dir", type=Path, default=ops.DEFAULT)
    a = parser.parse_args(argv)
    try:
        if a.command == "init":
            init(a.data_dir)
            print("READY: peer-context.csv")
        else:
            report = analyze(a.data_dir)
            print("ADVISORY_ONLY: %d observations" % len(report["results"]))
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
