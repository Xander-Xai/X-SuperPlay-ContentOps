#!/usr/bin/env python3
"""Report PR size / coupling metrics from a `git log --name-only` stream.

Reads stdin (or --input file). No subprocess, no network: CI can pipe a log
into this script without violating the repository subprocess policy.

Input format: git log --format='@@@%h' --name-only <base>...<head>
Default is report-only. --strict makes threshold breaches a FAIL.
"""
import argparse
import sys
from collections import Counter

THRESHOLDS = {"commits": 40, "unique_files": 80, "cross_group_ratio": 0.6, "hot_file_max": 20}


def group_of(path):
    if path.startswith(".github/"):
        return "CI"
    if path.startswith("tests/"):
        return "TESTS"
    if path.startswith("docs/"):
        return "DOCS"
    if path.startswith("config/"):
        return "CONFIG"
    if path.startswith("scripts/"):
        return "SCRIPTS"
    if path.startswith("src/"):
        return "SRC"
    return "OTHER"


def analyze(text):
    commits, cur = [], None
    for line in text.splitlines():
        if line.startswith("@@@"):
            cur = {"sha": line[3:].strip(), "files": []}
            commits.append(cur)
        elif line.strip() and cur is not None:
            cur["files"].append(line.strip())
    file_counter = Counter(f for c in commits for f in c["files"])
    cross = sum(1 for c in commits if len({group_of(f) for f in c["files"]}) > 1)
    return {
        "commits": len(commits),
        "unique_files": len(file_counter),
        "cross_group_commits": cross,
        "cross_group_ratio": round(cross / len(commits), 3) if commits else 0.0,
        "hot_file_max": file_counter.most_common(1)[0][1] if file_counter else 0,
        "hot_file": file_counter.most_common(1)[0][0] if file_counter else None,
    }


def breaches(metrics):
    out = []
    for key, limit in THRESHOLDS.items():
        if metrics[key] > limit:
            out.append("%s=%s > %s" % (key, metrics[key], limit))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="read log text from this file instead of stdin")
    ap.add_argument("--strict", action="store_true", help="exit 1 when a threshold is breached")
    args = ap.parse_args()
    text = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
    if not text.strip():
        print("pr-size SKIP: empty log stream (no metrics computed, not a pass)")
        return 0
    metrics = analyze(text)
    for k, v in metrics.items():
        print("  %-22s %s" % (k, v))
    bad = breaches(metrics)
    if bad:
        print("pr-size BREACH: %s" % "; ".join(bad))
        return 1 if args.strict else 0
    print("pr-size OK (report-only=%s)" % (not args.strict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
