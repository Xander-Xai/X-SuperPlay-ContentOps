#!/usr/bin/env python3
"""Operator-approved public feed intake; no account credentials or auto-publishing."""
import argparse
import csv
import hashlib
import http.client
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import editorial_ops as ops

LIMIT = 2_000_000
MAX_ITEMS = 200
ATOM = "{http://www.w3.org/2005/Atom}"


def public_url(value):
    u = urlsplit(value)
    if (u.scheme != "https" or not u.hostname or u.username or u.password
            or u.fragment or u.query or u.port not in (None, 443)):
        raise ValueError("use an HTTPS public URL without credentials, query or fragment")
    return u


def fetch(url):
    """One explicitly chosen endpoint, no redirects, cookies, or auth."""
    u = public_url(url)
    conn = http.client.HTTPSConnection(u.hostname, 443, timeout=15)
    try:
        conn.request("GET", u.path or "/", headers={
            "Accept": "application/rss+xml, application/atom+xml, application/feed+json, application/xml",
            "User-Agent": "ContentOps-Feed/1.0"})
        response = conn.getresponse()
        if response.status in (401, 403):
            raise ValueError("feed HTTP %d: access refused; use an authorized instance or local export" % response.status)
        if response.status == 429:
            raise ValueError("feed HTTP 429: rate limited; no automatic retry")
        if response.status != 200:
            raise ValueError("feed HTTP status %d; redirects are not followed" % response.status)
        raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("feed exceeds byte limit")
        return raw
    finally:
        conn.close()


def parse(raw):
    if len(raw) > LIMIT:
        raise ValueError("feed exceeds byte limit")
    # Restrict encoding, disable DTD/entity expansion before handing input to XML.
    content = raw.decode("utf-8-sig")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", content, re.I):
        raise ValueError("DTD/entities forbidden")
    if content.lstrip().startswith("{"):
        obj = json.loads(content)
        if not isinstance(obj, dict) or not str(obj.get("version", "")).startswith("https://jsonfeed.org/version/"):
            raise ValueError("invalid JSON Feed")
        items = obj.get("items")
        if not isinstance(items, list):
            raise ValueError("missing feed items")
        rows = [(v.get("title"), v.get("url") or v.get("external_url"))
                for v in items[:MAX_ITEMS] if isinstance(v, dict)]
    else:
        root = ET.fromstring(content)
        if root.tag == "rss":
            rows = [(v.findtext("title"), v.findtext("link"))
                    for v in root.findall("./channel/item")[:MAX_ITEMS]]
        elif root.tag == ATOM + "feed":
            rows = []
            for entry in root.findall(ATOM + "entry")[:MAX_ITEMS]:
                link = next((v.get("href") for v in entry.findall(ATOM + "link")
                             if v.get("rel", "alternate") == "alternate"), None)
                rows.append((entry.findtext(ATOM + "title"), link))
        else:
            raise ValueError("unsupported feed format")
    items, skipped = [], 0
    for title, link in rows:
        if not isinstance(title, str) or not isinstance(link, str):
            skipped += 1
            continue
        title = " ".join(title.split())[:500]
        link = link.strip()
        try:
            public_url(link)
        except ValueError:
            skipped += 1
            continue
        if not title:
            skipped += 1
            continue
        items.append((title, link))
    return items, skipped


def ingest(directory, raw, *, topic, source_id, observed_at=None, origin="local_export"):
    directory = ops.init(directory)
    ops.slug(topic)
    ops.slug(source_id)
    stamp = observed_at or datetime.now(timezone.utc).isoformat()
    if datetime.fromisoformat(stamp.replace("Z", "+00:00")).utcoffset() is None:
        raise ValueError("observation requires timezone")
    items, skipped = parse(raw)
    rows = ops.load(directory, "signals.csv")
    ops.unique(rows, "signal_id")
    seen = {(r["topic"], r["source_url"]) for r in rows}
    ids = {r["signal_id"] for r in rows}
    added = 0
    for title, url in items:
        if (topic, url) in seen:
            skipped += 1
            continue
        ident = "rss-" + hashlib.sha256((topic + "\n" + url).encode()).hexdigest()[:24]
        if ident in ids:
            raise ValueError("signal ID conflict")
        row = dict(signal_id=ident, topic=topic, kind="rss", source_url=url,
                   observed_at=stamp, observation="[" + source_id + "] " + title)
        ops.validate_source(row)
        rows.append(row)
        seen.add((topic, url))
        ids.add(ident)
        added += 1
    if added:
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=ops.FIELDS["signals.csv"])
        writer.writeheader()
        writer.writerows(rows)
        ops.write_atomic(directory, "signals.csv", stream.getvalue())
    receipt = {"schema": "contentops.feed-intake/v1", "status": "OBSERVED_ONLY",
               "source_id": source_id, "topic": topic, "observed_at": stamp,
               "origin": origin, "input_sha256": hashlib.sha256(raw).hexdigest(),
               "added": added, "skipped": skipped, "item_limit": MAX_ITEMS,
               "publish_authorized": False, "demand_verified": False}
    ops.write_atomic(directory, "feed-intake.json", json.dumps(receipt, indent=2) + "\n")
    return receipt


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=ops.DEFAULT)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path)
    source.add_argument("--url")
    p.add_argument("--source-id", required=True)
    p.add_argument("--topic", required=True)
    p.add_argument("--confirm", action="store_true",
                   help="required for a live public HTTPS request")
    a = p.parse_args(argv)
    try:
        if a.url:
            if not a.confirm:
                raise ValueError("live fetch requires --confirm")
            raw = fetch(a.url)
            origin = "live_public_https"
        else:
            if a.input.is_symlink():
                raise ValueError("symlink input refused")
            ops.local_dir(a.input.resolve().parent)
            with a.input.open("rb") as f:
                raw = f.read(LIMIT + 1)
            origin = "local_export"
        print(json.dumps(ingest(a.data_dir, raw, topic=a.topic, source_id=a.source_id,
                                origin=origin), ensure_ascii=False))
        return 0
    except (ValueError, OSError, ET.ParseError, http.client.HTTPException) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
