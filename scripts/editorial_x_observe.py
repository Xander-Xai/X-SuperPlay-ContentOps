#!/usr/bin/env python3
"""Authorized X API public metric observations, separate from organic benchmarks."""
import argparse
import hashlib
import http.client
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import editorial_ops as ops

LIMIT = 2_000_000
MAX_IDS = 20
METRICS = ("impression_count", "like_count", "reply_count", "retweet_count", "quote_count", "bookmark_count")


def ids(values):
    if not values or len(values) > MAX_IDS or len(set(values)) != len(values):
        raise ValueError("select 1..20 distinct post IDs")
    if any(not isinstance(v, str) or not re.fullmatch(r"[0-9]{1,20}", v) for v in values):
        raise ValueError("invalid post ID")
    return values


def fetch(post_ids, token):
    ids(post_ids)
    if not token or any(c.isspace() for c in token):
        raise ValueError("authorized X API credential required")
    params = urlencode({"ids": ",".join(post_ids), "tweet.fields": "author_id,created_at,public_metrics,lang"})
    conn = http.client.HTTPSConnection("api.x.com", timeout=20)
    try:
        conn.request("GET", "/2/tweets?" + params, headers={"Authorization": "Bearer " + token,
                     "Accept": "application/json", "User-Agent": "ContentOps-ReadOnly/1.0"})
        resp = conn.getresponse()
        if resp.status != 200:
            raise ValueError("X API HTTP %d; check authorization/quota; no retry performed" % resp.status)
        raw = resp.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("response exceeds byte limit")
        return raw
    finally:
        conn.close()


def normalize(raw, requested, observed_at):
    ids(requested)
    if len(raw) > LIMIT:
        raise ValueError("response exceeds byte limit")
    observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if observed.utcoffset() is None:
        raise ValueError("observation requires timezone")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("no authorized post data returned")
    if len(payload["data"]) > len(requested):
        raise ValueError("too many returned posts")
    seen = set()
    result = []
    for post in payload["data"]:
        if not isinstance(post, dict):
            raise ValueError("invalid post")
        ident, author = post.get("id"), post.get("author_id")
        if ident not in requested or ident in seen:
            raise ValueError("unexpected or duplicate post ID")
        if not isinstance(author, str) or not re.fullmatch(r"[0-9]{1,20}", author):
            raise ValueError("missing author ID")
        stamp = post.get("created_at")
        if not isinstance(stamp, str):
            raise ValueError("missing creation time")
        published = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if published.utcoffset() is None or published > observed:
            raise ValueError("invalid creation time")
        metrics = post.get("public_metrics")
        if not isinstance(metrics, dict):
            raise ValueError("missing public metrics")
        selected = {}
        for key in METRICS:
            value = metrics.get(key)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("invalid public metric")
            selected[key] = value
        result.append({"post_id": ident, "source_url": "https://x.com/i/web/status/" + ident,
                       "peer_alias": "x-" + author, "created_at": stamp, "observed_at": observed_at,
                       "language": post.get("lang") if post.get("lang") in {"zh", "en"} else "other_or_unknown",
                       "metrics": selected, "organic_paid": "unknown",
                       "benchmark_eligible": False})
        seen.add(ident)
    return result, sorted(set(requested) - seen)


def collect(directory, *, post_ids, topic, confirmed, token=None, raw=None, observed_at=None):
    if not confirmed:
        raise ValueError("authorized source and --confirm required")
    ids(post_ids)
    ops.slug(topic)
    if raw is None:
        raw = fetch(post_ids, token)
        stamp = datetime.now(timezone.utc).isoformat()
        origin = "official_api_live"
    else:
        if not observed_at:
            raise ValueError("export requires original observation timestamp")
        stamp = observed_at
        origin = "operator_supplied_api_export"
    rows, missing = normalize(raw, post_ids, stamp)
    directory = ops.init(directory)
    digest = hashlib.sha256(raw).hexdigest()
    batch = hashlib.sha256(json.dumps([digest, topic, stamp, sorted(post_ids)], sort_keys=True).encode()).hexdigest()[:24]
    result = {"schema": "contentops.x-peer-observation/v1", "status": "PUBLIC_METRICS_ONLY",
              "source": origin, "topic": topic, "input_sha256": digest, "observed_at": stamp,
              "observations": rows, "missing_ids": missing, "paid_or_organic_verified": False,
              "benchmark_eligible": False, "publish_authorized": False}
    path = ops.safe_file(directory, "x-peer-" + batch + ".json")
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != result:
            raise ValueError("observation collision")
    else:
        ops.write_atomic(directory, path.name, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=ops.DEFAULT)
    p.add_argument("--post-id", action="append", required=True)
    p.add_argument("--topic", required=True)
    p.add_argument("--input", type=Path)
    p.add_argument("--observed-at")
    p.add_argument("--confirm", action="store_true")
    a = p.parse_args(argv)
    try:
        if not a.confirm:
            raise ValueError("authorized source and --confirm required")
        raw = None
        if a.input:
            if a.input.is_symlink():
                raise ValueError("symlink input refused")
            ops.local_dir(a.input.resolve().parent)
            with a.input.open("rb") as f:
                raw = f.read(LIMIT + 1)
        report = collect(a.data_dir, post_ids=a.post_id, topic=a.topic, confirmed=a.confirm,
                         token=os.environ.get("CONTENTOPS_X_BEARER_TOKEN"), raw=raw, observed_at=a.observed_at)
        print("PUBLIC_METRICS_ONLY: %d observations; %d missing" % (len(report["observations"]), len(report["missing_ids"])))
        return 0
    except (ValueError, OSError, TypeError, http.client.HTTPException):
        # Avoid raw exception strings that could contain request data.
        print("BLOCKED: invalid input, authorization, quota or network; inspect configuration locally", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
