#!/usr/bin/env python3
"""Bounded public GitHub issue research with explicit human-selected signal intake."""
import argparse
import csv
import hashlib
import http.client
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import editorial_ops as ops

SCHEMA = "contentops.public-issue-observations/v1"
LIMIT = 2_000_000
MAX_ITEMS = 20
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}")
KEYWORD = re.compile(r"[\w -]{2,80}", re.UNICODE)


def scope(repo, keyword):
    if not REPO.fullmatch(repo) or repo.split("/")[1] in {".", ".."}:
        raise ValueError("explicit owner/repository required")
    if not KEYWORD.fullmatch(keyword) or not any(c.isalnum() for c in keyword):
        raise ValueError("plain keyword/phrase only; no search qualifiers")
    return repo, keyword


def fetch(repo, keyword):
    repo, keyword = scope(repo, keyword)
    query = '"' + keyword.strip() + '" in:title is:issue is:public repo:' + repo
    params = urlencode({"q": query, "per_page": MAX_ITEMS, "sort": "updated", "order": "desc"})
    conn = http.client.HTTPSConnection("api.github.com", timeout=15)
    try:
        conn.request("GET", "/search/issues?" + params, headers={
            "Accept": "application/vnd.github+json", "User-Agent": "ContentOps-IssueResearch/1.0"})
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError("GitHub HTTP %d; no retries, redirects or authentication" % response.status)
        raw = response.read(LIMIT+1)
        if len(raw) > LIMIT:
            raise ValueError("search response exceeds limit")
        return raw
    finally:
        conn.close()


def normalize(raw, repo, keyword, stamp, origin):
    scope(repo, keyword)
    if len(raw) > LIMIT:
        raise ValueError("search response exceeds limit")
    if datetime.fromisoformat(stamp.replace("Z", "+00:00")).utcoffset() is None:
        raise ValueError("observation timestamp must include timezone")
    obj = json.loads(raw)
    if (not isinstance(obj, dict) or obj.get("incomplete_results") is not False
            or not isinstance(obj.get("items"), list) or len(obj["items"]) > MAX_ITEMS):
        raise ValueError("incomplete or malformed bounded issue search")
    items, seen = [], set()
    for issue in obj["items"]:
        if not isinstance(issue, dict) or "pull_request" in issue:
            raise ValueError("non-issue in response")
        number, url = issue.get("number"), issue.get("html_url")
        if (type(number) is not int or number < 1 or number in seen or
                not isinstance(url, str) or url.casefold() !=
                ("https://github.com/" + repo + "/issues/" + str(number)).casefold()):
            raise ValueError("wrong repository, duplicate or invalid issue")
        title = issue.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("invalid issue title")
        items.append({"number": number, "url": url, "title": " ".join(title.split())[:500]})
        seen.add(number)
    return {"schema": SCHEMA, "repo": repo, "keyword": keyword,
            "observed_at": stamp, "origin": origin, "input_sha256": hashlib.sha256(raw).hexdigest(),
            "items": items, "demand_verified": False, "publish_authorized": False}


def ingest(directory, package, number, topic, observation):
    if not isinstance(package, dict) or package.get("schema") != SCHEMA:
        raise ValueError("invalid observation package")
    repo, keyword = scope(package.get("repo", ""), package.get("keyword", ""))
    ops.slug(topic)
    if not isinstance(observation, str) or not observation.strip() or len(observation) > 500:
        raise ValueError("write a brief sanitized human observation")
    if type(number) is not int or number < 1:
        raise ValueError("invalid selected issue number")
    matches = [i for i in package.get("items", []) if isinstance(i, dict)
               and i.get("number") == number]
    if len(matches) != 1:
        raise ValueError("select exactly one issue from preview")
    url = matches[0].get("url")
    if not isinstance(url, str) or url.casefold() != (
            "https://github.com/" + repo + "/issues/" + str(number)).casefold():
        raise ValueError("invalid selected issue URL")
    digest = package.get("input_sha256", "")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("missing observation source digest")
    stamp = package.get("observed_at")
    if not isinstance(stamp, str):
        raise ValueError("missing observation timestamp")
    ident = "issue-" + hashlib.sha256((topic + "\n" + url.casefold()).encode()).hexdigest()[:24]
    row = dict(signal_id=ident, topic=topic, kind="issue", source_url=url,
               observed_at=stamp, observation=observation.strip())
    ops.validate_source(row)
    directory = ops.init(directory)
    rows = ops.load(directory, "signals.csv")
    ops.unique(rows, "signal_id")
    duplicate = any(r["topic"] == topic and r["source_url"].casefold() == url.casefold()
                    for r in rows)
    if not duplicate:
        if any(r["signal_id"] == ident for r in rows):
            raise ValueError("signal ID conflict")
        rows.append(row)
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=ops.FIELDS["signals.csv"])
        writer.writeheader()
        writer.writerows(rows)
        ops.write_atomic(directory, "signals.csv", stream.getvalue())
    return {"schema": "contentops.public-issue-intake/v1",
            "status": "DUPLICATE" if duplicate else "OBSERVED_ONLY",
            "signal_id": ident if not duplicate else None,
            "source_url": url, "source_digest_reported": digest,
            "demand_verified": False, "buyer_verified": False,
            "publish_authorized": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=ops.DEFAULT)
    sub = p.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search")
    search.add_argument("--repo", required=True)
    search.add_argument("--keyword", required=True)
    search.add_argument("--input", type=Path, help="optional local GitHub search API export")
    search.add_argument("--confirm", action="store_true")
    save = sub.add_parser("ingest")
    save.add_argument("--preview", required=True, help="local JSON filename")
    save.add_argument("--issue", required=True, type=int)
    save.add_argument("--topic", required=True)
    save.add_argument("--observation", required=True)
    save.add_argument("--confirm", action="store_true")
    a = p.parse_args()
    try:
        if a.command == "search":
            if a.input:
                if a.input.is_symlink():
                    raise ValueError("symlink input refused")
                ops.local_dir(a.input.resolve().parent)
                with a.input.open("rb") as f:
                    raw = f.read(LIMIT+1)
                origin = "local_export_unverified"
            else:
                if not a.confirm:
                    raise ValueError("live public request requires explicit --confirm")
                raw, origin = fetch(a.repo, a.keyword), "live_public_search"
            result = normalize(raw, a.repo, a.keyword,
                               datetime.now(timezone.utc).isoformat(), origin)
        else:
            if not a.confirm:
                raise ValueError("explicit human selection required")
            file = ops.safe_file(a.data_dir, a.preview)
            if file.suffix != ".json" or file.stat().st_size > LIMIT:
                raise ValueError("invalid local preview")
            result = ingest(a.data_dir, json.loads(file.read_text(encoding="utf-8")),
                            a.issue, a.topic, a.observation)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (OSError, ValueError, http.client.HTTPException) as exc:
        p.exit(1, "issue research refused: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
