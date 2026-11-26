#!/usr/bin/env python3
"""Import authorized Douyin response / existing Bilibili receipt into local metrics.

No network, login, OAuth, publication or organic-traffic inference. An operator
attestation is not remote proof of account ownership or publication.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import editorial_ops as ops
import platform_learning_loop as learning

MAX_BYTES = 2_000_000
SCHEMA = "contentops.video-metric-intake/v1"
DOUYIN = {"play_count": "views_or_reads", "digg_count": "likes",
          "comment_count": "comments", "share_count": "shares"}
BILIBILI = {"view": "views_or_reads", "like": "likes", "reply": "comments",
            "favorite": "saves", "share": "shares"}


def parse_time(value):
    stamp = learning._date(value)
    if stamp is None:
        raise ValueError("timezone-aware original timestamp required")
    return stamp


def counters(raw, mapping):
    if not isinstance(raw, dict):
        raise ValueError("missing counters")
    result = {}
    for source, dest in mapping.items():
        if source not in raw:
            continue
        value = raw[source]
        if type(value) is not int or value < 0:
            raise ValueError("invalid counter " + source)
        result[dest] = str(value)
    if not result:
        raise ValueError("no supported counters")
    return result


def decode(raw, platform, video_id, account, observed_at, published_at):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("empty or oversized source")
    document = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(document, dict):
        raise ValueError("invalid source document")
    if platform == "douyin":
        if not re.fullmatch(r"[0-9]{1,24}", video_id):
            raise ValueError("numeric Douyin video ID required")
        data = document.get("data")
        extra = document.get("extra")
        if not isinstance(data, dict) or type(data.get("error_code")) is not int or data["error_code"] != 0:
            raise ValueError("Douyin response did not succeed")
        if extra is not None and (not isinstance(extra, dict) or type(extra.get("error_code")) is not int or extra["error_code"] != 0):
            raise ValueError("Douyin response extra reports error")
        rows = data.get("list")
        if not isinstance(rows, list):
            raise ValueError("no authorized video response list")
        matches = [row for row in rows if isinstance(row, dict) and row.get("video_id") == video_id]
        if len(matches) != 1:
            raise ValueError("requested video ID must match exactly one response row")
        post = matches[0]
        created = post.get("create_time")
        if type(created) is not int or created <= 0 or datetime.fromtimestamp(created, timezone.utc) != published_at:
            raise ValueError("response creation timestamp differs from publication index")
        result = counters(post.get("statistics"), DOUYIN)
        # Do not infer save count from downloads or sum overlapping share/forward.
        return result, "official_api", "douyin_api_counts_v1"
    if platform == "bilibili":
        if not re.fullmatch(r"BV[0-9A-Za-z]{10}", video_id):
            raise ValueError("valid BV required")
        if (document.get("schema") != "contentops.bilibili-metrics/v1"
                or document.get("platform") != "bilibili" or document.get("channel") != "api_public"
                or document.get("account_slug") != account or document.get("bvid") != video_id
                or document.get("mode") != "ACCOUNT_DELIVERY" or document.get("bvid_source") not in {"project", "dna"}
                or any(document.get(k) is not False for k in ("modifies_script", "modifies_qc", "modifies_production_ready"))
                or document.get("issues") or parse_time(document.get("fetched_at")) != observed_at):
            raise ValueError("Bilibili receipt must be an exact account-bound successful observation, not transport smoke")
        return counters(document.get("metrics"), BILIBILI), "api_public", "bilibili_public_counts_v1"
    raise ValueError("unsupported platform")


def import_observation(directory, raw, *, platform, account, content_id, video_id, observed_at, confirmed):
    if not confirmed:
        raise ValueError("operator authorization and confirmation required")
    if platform not in {"bilibili", "douyin"}:
        raise ValueError("unsupported platform")
    ops.account_allows(account, platform)
    ops.slug(content_id)
    observed = parse_time(observed_at)
    directory = ops.local_dir(directory)
    index = ops.safe_file(directory, "content-index.csv")
    snapshots = ops.safe_file(directory, "metric-snapshots.csv")
    records = learning._load(index, learning.INDEX_COLUMNS)
    matches = [row for row in records if row["content_id"] == content_id and row["platform"] == platform
               and row["account_alias"] == account and row["content_format"] == "video"]
    if len(matches) != 1 or matches[0]["publish_status"] not in learning.VALID_STATUS:
        raise ValueError("unique existing published index entry required")
    item = matches[0]
    if platform == "douyin":
        canonical = "https://www.douyin.com/video/" + video_id
    else:
        canonical = "https://www.bilibili.com/video/" + video_id
    if item["post_url"].rstrip("/") != canonical:
        raise ValueError("publication URL differs from selected native video ID")
    published = parse_time(item["published_at"])
    age = (observed - published).total_seconds() / 3600
    windows = [name for name, (low, high) in learning.WINDOW_HOURS.items() if low <= age <= high]
    if len(windows) != 1:
        raise ValueError("observation outside supported age window")
    metrics, source, definition = decode(raw, platform, video_id, account, observed, published)
    source_hash = hashlib.sha256(raw).hexdigest()
    # Stable key per publication/cohort, not response bytes; different observations
    # in one window need explicit operator reconciliation, never silent overwrite.
    identity = hashlib.sha256(json.dumps([platform, account, content_id, canonical, windows[0], definition],
                                         separators=(",", ":")).encode()).hexdigest()[:24]
    row = {key: "" for key in learning.SNAPSHOT_COLUMNS}
    row.update(metric_snapshot_id="video-" + identity, content_id=content_id,
               experiment_id=item["experiment_id"], platform=platform,
               observed_at=observed.isoformat(), published_at=published.isoformat(),
               post_url=item["post_url"], account_alias=account, content_format="video",
               window=windows[0], metric_source=source, metric_definition_version=definition,
               data_access="partial", missing_reason="only supported returned counters imported",
               organic_paid="unknown", timezone=str(observed.tzinfo),
               denominator_available="yes" if "views_or_reads" in metrics else "no",
               notes="operator-attested source sha256:" + source_hash, **metrics)
    lock = ops.safe_file(directory, "video-metric-intake.lock")
    with lock.open("x", encoding="utf-8") as handle:
        handle.write("single local writer; do not edit metrics concurrently\n")
    try:
        old = snapshots.read_bytes()
        index_bytes = index.read_bytes()
        # Re-read exact index under lock. Other producers must obey single-writer
        # convention; external manual editors are not synchronized by this lock.
        if learning._load(index, learning.INDEX_COLUMNS) != records:
            raise ValueError("publication index changed")
        with snapshots.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(learning.SNAPSHOT_COLUMNS):
                raise ValueError("snapshot columns must exactly match existing schema")
            existing = list(reader)
        if any(None in x or any(v is None for v in x.values()) for x in existing):
            raise ValueError("malformed snapshot CSV")
        same = [x for x in existing if x["metric_snapshot_id"] == row["metric_snapshot_id"]
                or (x["content_id"], x["platform"], x["account_alias"], x["post_url"].rstrip("/"), x["window"],
                    x["metric_definition_version"]) == (content_id, platform, account, canonical, windows[0], definition)]
        if same:
            if same != [row]:
                raise ValueError("conflicting existing observation; reconcile manually")
            replayed = True
        else:
            buf = io.StringIO(newline="")
            writer = csv.DictWriter(buf, fieldnames=learning.SNAPSHOT_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(existing + [row])
            if len(buf.getvalue().encode("utf-8")) > 25_000_000:
                raise ValueError("snapshot size exceeds local reader limit")
            if index.read_bytes() != index_bytes or snapshots.read_bytes() != old:
                raise ValueError("local source changed; no write")
            ops.write_atomic(directory, "metric-snapshots.csv", buf.getvalue())
            replayed = False
    finally:
        lock.unlink()
    return {"schema": SCHEMA, "status": "REPLAYED" if replayed else "IMPORTED",
            "snapshot_id": row["metric_snapshot_id"], "platform": platform,
            "window": windows[0], "input_sha256": source_hash, "metric_count": len(metrics),
            "organic_paid": "unknown", "benchmark_eligible": False,
            "publish_authorized": False, "external_action": "none"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--metrics-dir", type=Path, default=learning.DEFAULT_DATA)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--platform", choices=("douyin", "bilibili"), required=True)
    for name in ("account", "content-id", "video-id", "observed-at"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--confirm", action="store_true")
    a = p.parse_args(argv)
    try:
        if not a.confirm or a.input.is_symlink():
            raise ValueError("confirmation required; symlink refused")
        ops.local_dir(a.input.resolve().parent)
        with a.input.open("rb") as f:
            raw = f.read(MAX_BYTES + 1)
        result = import_observation(a.metrics_dir, raw, platform=a.platform, account=a.account,
                                    content_id=a.content_id, video_id=a.video_id, observed_at=a.observed_at,
                                    confirmed=a.confirm)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, TypeError, KeyError, OverflowError):
        print("BLOCKED: authorization, source identity, response, age window or local write conflict", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
