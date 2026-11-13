#!/usr/bin/env python3
"""Offline human-rated X discussion triage for Inspiration vs Timeline pilot.

Reads only operator-entered CSV data. Never discovers posts, fetches an URL,
posts replies, infers X algorithm weights, or creates automated X actions.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / ".local" / "x-growth-en"
INPUT_NAME = "discussion-candidates.csv"
OUTPUT_NAME = "candidates-ranked.csv"
SOURCES = ("inspiration_broad", "inspiration_ai", "timeline_ai")
DIMENSIONS = ("topic_relevance", "audience_fit", "incremental_value",
              "evidence_quality", "discussion_potential",
              "duplication_risk", "compliance_risk")
HEADERS = (
    "source_url", "account_handle", "language", "discovery_source",
    "topic_cluster", "observed_at", "source_access", "author_active",
    "trend_signal", "source_impressions", *DIMENSIONS,
)
OUTPUT_HEADERS = (
    "source_url", "account_handle", "language", "discovery_source",
    "topic_cluster", "observed_at", "source_impressions", "decision",
    "score", "reason", "source_verification",
)
STATUS_URL = re.compile(r"^/[A-Za-z0-9_]{1,15}/status/[0-9]+/?$")
ACCOUNT = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
LANGUAGE = re.compile(r"^[a-z]{2,3}(?:-[a-z]{2})?$")
TOPIC = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def guard_local(directory: Path):
    target = directory.resolve()
    try:
        path = target.relative_to(ROOT.resolve())
    except ValueError:
        return  # explicit external local drive is allowed
    if not path.parts or path.parts[0] != ".local":
        raise ValueError("inside repo, private data must be under ignored .local/")


def _valid_url(value: str):
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and url.hostname in ("x.com", "twitter.com")
                and not url.username and not url.password
                and not url.query and not url.fragment
                and bool(STATUS_URL.fullmatch(url.path)))
    except (TypeError, ValueError):
        return False


def _date(value: str):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.utcoffset() is not None
    except (TypeError, ValueError, AttributeError):
        return False


def _score_value(value: str):
    try:
        number = float(value)
        if math.isfinite(number) and 0 <= number <= 5:
            return number
    except (ValueError, TypeError):
        pass
    return None


def initialize(directory: Path):
    guard_local(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / INPUT_NAME
    if not path.exists():
        with path.open("x", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerow(HEADERS)
        created = True
    else:
        created = False
    return {"status": "READY", "created": created, "local_path": str(path),
            "network_used": False, "x_actions": "none"}


def rank(directory: Path, account: str, language: str):
    guard_local(directory)
    if not ACCOUNT.fullmatch(account) or not LANGUAGE.fullmatch(language):
        raise ValueError("invalid account or language")
    path = directory / INPUT_NAME
    if not path.is_file() or path.stat().st_size > 5_000_000:
        raise ValueError("candidate CSV missing or too large; run init")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(HEADERS).issubset(reader.fieldnames):
            raise ValueError("candidate CSV columns do not match contract")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("malformed candidate CSV")

    used_urls = set()
    output = []
    skipped = Counter()
    for row in rows:
        if row["account_handle"] != account or row["language"].lower() != language:
            skipped["another_account_or_language"] += 1
            continue
        source = row["discovery_source"]
        url = row["source_url"]
        reasons = []
        if source not in SOURCES:
            reasons.append("INVALID_DISCOVERY_SOURCE")
        if not TOPIC.fullmatch(row["topic_cluster"] or ""):
            reasons.append("INVALID_TOPIC_CLUSTER")
        if not _valid_url(url) or not _date(row["observed_at"]):
            reasons.append("MISSING_SOURCE_OR_OBSERVATION")
        if url in used_urls:
            reasons.append("DUPLICATE_SOURCE_URL")
        used_urls.add(url)
        if row["source_access"] != "operator_viewed":
            reasons.append("SOURCE_NOT_OPERATOR_VERIFIED")
        dims = {dim: _score_value(row[dim]) for dim in DIMENSIONS}
        if any(value is None for value in dims.values()):
            reasons.append("MISSING_OR_INVALID_HUMAN_RATING")
        trend = _score_value(row.get("trend_signal", ""))
        if row["trend_signal"].strip() and trend is None:
            reasons.append("INVALID_TREND")
        author = row["author_active"].strip().lower()
        if author not in ("yes", "no", "unknown", ""):
            reasons.append("INVALID_AUTHOR_ACTIVITY")
        impressions = row["source_impressions"].strip()
        if impressions:
            try:
                n = int(impressions)
                if n < 0:
                    raise ValueError()
            except ValueError:
                reasons.append("INVALID_SOURCE_IMPRESSIONS")
        if not reasons:
            if dims["audience_fit"] < 3 or dims["topic_relevance"] < 3:
                reasons.append("OUTSIDE_TARGET_AUDIENCE")
            if dims["incremental_value"] < 2 or dims["evidence_quality"] < 2:
                reasons.append("INSUFFICIENT_NEW_VALUE_OR_EVIDENCE")
            if dims["compliance_risk"] >= 4 or dims["duplication_risk"] >= 4:
                reasons.append("HIGH_RISK_OR_DUPLICATE")
        score = None
        if not reasons:
            # Deliberately subjective heuristic; heat has max +1, never dominant.
            score = round(
                2 * dims["audience_fit"] + 2 * dims["incremental_value"]
                + 1.5 * dims["topic_relevance"] + dims["evidence_quality"]
                + dims["discussion_potential"] - 2 * dims["duplication_risk"]
                - 2 * dims["compliance_risk"]
                + (trend or 0) * 0.2 + (0.5 if author == "yes" else 0),
                2,
            )
        decision = "REVIEW_CANDIDATE" if not reasons else "SKIP"
        output.append({
            "source_url": url if _valid_url(url) else "",
            "account_handle": account, "language": language,
            "discovery_source": source, "topic_cluster": row["topic_cluster"],
            "observed_at": row["observed_at"],
            "source_impressions": impressions,
            "decision": decision, "score": score if score is not None else "",
            "reason": ";".join(reasons) if reasons else "HUMAN_CONTEXT_REVIEW_REQUIRED",
            "source_verification": "OPERATOR_ASSERTED_ONLY",
        })
    output.sort(key=lambda r: (r["decision"] != "REVIEW_CANDIDATE",
                               -float(r["score"]) if r["score"] != "" else float("inf"),
                               r["source_url"]))
    destination = directory / OUTPUT_NAME
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_HEADERS)
        writer.writeheader()
        writer.writerows(output)
    return {
        "status": "REVIEW_REQUIRED" if output else "DATA_UNAVAILABLE",
        "schema": "contentops.x-discussion-candidates/v1",
        "account": account, "language": language, "total": len(output),
        "review_candidates": sum(r["decision"] == "REVIEW_CANDIDATE" for r in output),
        "skipped": sum(r["decision"] == "SKIP" for r in output),
        "not_for_this_account": skipped["another_account_or_language"],
        "output_local": str(destination),
        "score_type": "OPERATOR_SUPPLIED_SUBJECTIVE_HEURISTIC_NOT_X_ALGORITHM",
        "publication_authorized": False, "network_used": False, "x_actions": "none",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "rank"))
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--account", default="x-superplay-english")
    parser.add_argument("--language", default="en")
    args = parser.parse_args(argv)
    try:
        result = initialize(args.data_dir) if args.command == "init" else rank(
            args.data_dir, args.account, args.language)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, csv.Error) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc),
                          "network_used": False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
