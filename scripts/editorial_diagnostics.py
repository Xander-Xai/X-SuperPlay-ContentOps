#!/usr/bin/env python3
"""Local same-cohort video diagnostics; advice only, never a publishing gate."""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

import platform_learning_loop as learning

# Native ratios retain the selected definition's units; no assumed percentages.
METRICS = {
    "impressions": "distribution",
    "ctr": "title_or_cover",
    "avg_watch_time": "opening_or_pacing",
    "completion_or_retention": "structure_or_duration",
    "saves_per_1000_views": "practical_value",
    "qualified_signals_per_hour": "production_efficiency",
}
FORMATS = {"video", "shorts"}


def rate(numerator, denominator, scale=1):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    result = numerator / denominator * scale
    return result if result < float("inf") else None


def diagnostics(directory, *, platform, account, content_format, topic, window,
                definition, experiment):
    directory = Path(directory)
    learning._local_guard(directory)
    for label, value in (("platform", platform), ("account", account),
                         ("format", content_format), ("topic", topic),
                         ("definition", definition), ("experiment", experiment)):
        learning._safe_slug(value, label)
    if content_format not in FORMATS or window not in learning.WINDOW_HOURS:
        raise ValueError("video/shorts and supported age window required")
    paths = [directory / "content-index.csv", directory / "metric-snapshots.csv"]
    for path in paths:
        if path.is_symlink() or path.resolve().parent != directory.resolve():
            raise ValueError("metric input must be a direct local file")
    index = learning._load(paths[0], learning.INDEX_COLUMNS)
    snapshots = learning._load(paths[1], learning.SNAPSHOT_COLUMNS)
    scope = (platform, account, content_format, topic, experiment)
    posts = [p for p in index if (
        p["platform"], p["account_alias"], p["content_format"],
        p["topic_cluster"], p["experiment_id"]) == scope]
    ids = Counter(p["content_id"] for p in posts)
    urls = Counter(p["post_url"] for p in posts)
    skipped = Counter()
    matched = defaultdict(list)
    for s in snapshots:
        if (s["platform"], s["account_alias"], s["content_format"],
            s["window"], s["metric_definition_version"]) == (
                platform, account, content_format, window, definition):
            matched[(s["content_id"], s["post_url"])].append(s)
    items = []
    for p in posts:
        cid, url = p["content_id"], p["post_url"]
        published = learning._date(p["published_at"])
        if (not cid or not learning._url(url) or not published or
                p["publish_status"] not in learning.VALID_STATUS):
            skipped["invalid_or_unpublished"] += 1
            continue
        if ids[cid] != 1 or urls[url] != 1:
            skipped["duplicate_identity"] += 1
            continue
        matches = matched[(cid, url)]
        if len(matches) != 1:
            skipped["missing_snapshot" if not matches else "duplicate_snapshot"] += 1
            continue
        s = matches[0]
        observed = learning._date(s["observed_at"])
        if (not observed or learning._date(s["published_at"]) != published or
                s["experiment_id"] != experiment or not
                learning.WINDOW_HOURS[window][0] <=
                (observed - published).total_seconds() / 3600 <=
                learning.WINDOW_HOURS[window][1]):
            skipped["wrong_time_or_experiment"] += 1
            continue
        if (s["organic_paid"] != "organic" or
                s["data_access"] not in {"available", "partial"} or
                s["metric_source"] not in {"native_manual", "native_export", "official_api"}):
            skipped["paid_or_unverifiable"] += 1
            continue
        def metric(name):
            return learning._metric(s.get(name, ""))
        values = {name: metric(name) for name in (
            "impressions", "ctr", "avg_watch_time", "completion_or_retention")}
        values["saves_per_1000_views"] = rate(metric("saves"), metric("views_or_reads"), 1000)
        values["qualified_signals_per_hour"] = rate(
            metric("qualified_signals"), metric("founder_hours"))
        items.append({"content_id": cid, "post_url": url, "metrics": values,
                      "founder_hours": metric("founder_hours")})
    coverage = {}
    for name in METRICS:
        vals = [p["metrics"][name] for p in items if p["metrics"][name] is not None]
        coverage[name] = {"observed": len(vals), "missing": len(items) - len(vals),
                          "median_native": median(vals) if vals else None}
    for p in items:
        comparisons = {}
        candidates = []
        for name, variable in METRICS.items():
            value = p["metrics"][name]
            peers = [q["metrics"][name] for q in items if q is not p
                     and q["metrics"][name] is not None]
            baseline = median(peers) if len(peers) >= 5 else None
            relative = rate(value, baseline)
            comparisons[name] = {"peer_count": len(peers), "peer_median": baseline,
                                 "relative_to_peer_median": relative}
            if relative is not None and relative < 1:
                candidates.append((relative, name, variable))
        p["comparisons"] = comparisons
        if candidates:
            relative, name, variable = min(candidates)
            p["next_hypothesis"] = {"observed_metric": name, "variable_to_review": variable,
                                    "relative_to_peer_median": relative,
                                    "status": "HUMAN_REVIEW_REQUIRED"}
        else:
            p["next_hypothesis"] = None
    digest = hashlib.sha256()
    for path in paths:
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return {"schema": "contentops.editorial-diagnostics/v1",
            "status": "DESCRIPTIVE_ONLY" if any(v["observed"] >= 6 for v in coverage.values())
                      else "INSUFFICIENT_DATA",
            "scope": {"platform": platform, "account": account, "format": content_format,
                      "topic": topic, "experiment": experiment, "window": window,
                      "definition": definition},
            "input_sha256": digest.hexdigest(), "coverage": coverage,
            "sample_count": len(items), "skipped": dict(skipped), "works": items,
            "limits": ["Local user-supplied data, not independently authenticated.",
                       "Native ratio units are not normalized across definitions or platforms.",
                       "Relative differences are descriptive; no causal diagnosis or algorithm claims.",
                       "Five other valid works are a minimum observation threshold, not significance.",
                       "Review one creative hypothesis, never modify DNA or authorize production."],
            "publish_authorized": False, "production_ready": False,
            "network_used": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=learning.DEFAULT_DATA)
    for name in ("platform", "account", "format", "topic", "definition", "experiment"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--window", choices=learning.WINDOW_HOURS, default="T+24H")
    a = parser.parse_args()
    try:
        result = diagnostics(a.data_dir, platform=a.platform, account=a.account,
                             content_format=a.format, topic=a.topic, window=a.window,
                             definition=a.definition, experiment=a.experiment)
        print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
    except (OSError, ValueError) as exc:
        parser.exit(1, "diagnostics refused: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
