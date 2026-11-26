#!/usr/bin/env python3
"""Human-observed peer creative patterns linked to the existing peer baseline."""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

import editorial_ops as ops
import editorial_peers as peers

FIELDS = ("case_id", "hook_type", "title_promise", "cover_type", "narrative",
          "evidence_location", "original_application", "reviewer")
DIMENSIONS = {
    "hook_type": {"question", "result", "contrast", "story", "problem", "demonstration", "unknown"},
    "title_promise": {"tutorial", "comparison", "explanation", "result", "news", "story", "unknown"},
    "cover_type": {"result", "diagram", "person", "object", "text", "none", "unknown"},
    "narrative": {"problem_solution", "walkthrough", "comparison", "story", "list", "explanation", "unknown"},
}
MIN_GROUP = 5


def init(directory):
    peers.init(directory)
    p = ops.safe_file(directory, "peer-patterns.csv")
    if not p.exists():
        with p.open("x", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(FIELDS)


def read(directory):
    p = ops.safe_file(directory, "peer-patterns.csv")
    if p.stat().st_size > 5_000_000:
        raise ValueError("peer pattern file too large")
    with p.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(FIELDS):
            raise ValueError("invalid pattern columns")
        rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError("malformed pattern row")
    ops.unique(rows, "case_id")
    for row in rows:
        ops.required(row, FIELDS)
        for dim, values in DIMENSIONS.items():
            if row[dim] not in values:
                raise ValueError("unknown pattern category: " + dim)
        if any(len(row[k]) > 500 for k in ("evidence_location", "original_application", "reviewer")):
            raise ValueError("oversized human observation")
    return rows


def analyze(directory):
    directory = ops.local_dir(directory)
    tags = read(directory)
    cases = {r["case_id"] for r in ops.load(directory, "peers.csv")}
    if any(t["case_id"] not in cases for t in tags):
        raise ValueError("unknown peer case in pattern annotations")
    tagged = {t["case_id"]: t for t in tags}
    report = peers.analyze(directory)
    rows, skipped = [], defaultdict(int)
    cohorts = defaultdict(list)
    for observation in report["results"]:
        ident = observation["case_id"]
        if ident not in tagged:
            skipped["unannotated"] += 1
            continue
        if observation["ratio_to_peer_median"] is None:
            skipped["insufficient_baseline"] += 1
            continue
        t = tagged[ident]
        # Include topic as an extra filter beyond the existing peer baseline.
        key = tuple(observation["cohort"][k] for k in
                    ("platform", "peer_alias", "format", "metric", "definition", "window")) + (observation["topic"],)
        cohorts[key].append((observation, t))
        rows.append({"case_id": ident, "source_url": observation["source_url"],
                     "observed_ratio": observation["ratio_to_peer_median"],
                     "evidence_location": t["evidence_location"],
                     "original_application": t["original_application"],
                     "reviewer": t["reviewer"],
                     "patterns": {k: t[k] for k in DIMENSIONS}})
    comparisons = []
    for key, observations in sorted(cohorts.items()):
        for dim in DIMENSIONS:
            known = [(o, t) for o, t in observations if t[dim] != "unknown"]
            values = sorted({t[dim] for _, t in known})
            for value in values:
                yes = [o["ratio_to_peer_median"] for o, t in known if t[dim] == value]
                no = [o["ratio_to_peer_median"] for o, t in known if t[dim] != value]
                comparable = len(yes) >= MIN_GROUP and len(no) >= MIN_GROUP
                comparisons.append({
                    "cohort": dict(zip(("platform", "peer_alias", "format", "metric",
                                        "definition", "window", "topic"), key)),
                    "dimension": dim, "pattern": value,
                    "pattern_count": len(yes), "other_count": len(no),
                    "unknown_count": len(observations) - len(known),
                    "pattern_median_ratio": median(yes) if comparable else None,
                    "other_median_ratio": median(no) if comparable else None,
                    "status": "DESCRIPTIVE_ONLY" if comparable else "INSUFFICIENT_DATA",
                })
    digest = hashlib.sha256()
    for name in ("peers.csv", "peer-context.csv", "peer-patterns.csv"):
        digest.update(hashlib.sha256(ops.safe_file(directory, name).read_bytes()).digest())
    result = {"schema": "contentops.peer-creative-patterns/v1",
              "status": "ADVISORY_ONLY", "input_sha256": digest.hexdigest(),
              "source": "LOCAL_HUMAN_OBSERVATIONS_UNVERIFIED", "cases": rows,
              "comparisons": comparisons, "skipped": dict(skipped),
              "limitations": ["No automatic transcript or image analysis.",
                              "Five samples per arm is not statistical significance.",
                              "Pattern associations do not prove causality or predict reach.",
                              "Use own evidence and expression; do not copy peer content."],
              "publish_authorized": False, "production_ready": False}
    ops.write_atomic(directory, "peer-pattern-review.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("init", "review"))
    p.add_argument("--data-dir", type=Path, default=ops.DEFAULT)
    a = p.parse_args()
    try:
        if a.command == "init":
            init(a.data_dir)
            print("READY: peer-patterns.csv")
        else:
            result = analyze(a.data_dir)
            print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
    except (ValueError, OSError, TypeError) as exc:
        p.exit(4, "BLOCKED: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
