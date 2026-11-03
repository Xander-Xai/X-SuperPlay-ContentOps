#!/usr/bin/env python3
"""Collect the material a technical episode is made of, and freeze it.

Given URLs — official documentation, a repository page, a release note — this
saves what was actually read, hashes it, and writes the pack the script stage
consumes. It does not summarise, interpret or generate: the text it saves is the
page's own text, so a claim quoting it is quoting the source.

Usage:
    python scripts/evidence_pack.py --topic "LangGraph 状态管理" \
        --out projects/my-episode \
        https://langchain-ai.github.io/langgraph/concepts/persistence/

Exit codes: 0 the pack was written; 4 nothing usable was collected.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.hotspots.adapters import FetchError, _http_get  # noqa: E402
from contentops.script.evidence import PACK_FILE, PACK_SCHEMA  # noqa: E402

#: Enough text for several beats without dragging a whole manual into a video.
EXCERPT_CHARS = 1800


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _title_of(markup: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", markup, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return html.unescape(" ".join(match.group(1).split()))[:160]


def _text_of(markup: str) -> str:
    """Readable text from a page, without a parser dependency.

    Script and style blocks are removed first: their contents are code for the
    browser, and quoting them as the document's text would be wrong. Then tags
    are stripped and entities decoded.
    """
    stripped = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", markup,
                      flags=re.IGNORECASE | re.DOTALL)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    text = html.unescape(stripped)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def collect(urls, out: Path, topic: str) -> dict:
    documents = out / "script" / "evidence"
    documents.mkdir(parents=True, exist_ok=True)
    items = []
    for index, url in enumerate(urls, start=1):
        evidence_id = f"EV-{index:02d}"
        try:
            body = _http_get(url, timeout=20.0, source_id="evidence-pack")
        except FetchError as exc:
            items.append({"evidence_id": evidence_id, "kind": "documentation",
                          "title": "", "url": url, "excerpt": "",
                          "error": f"{exc.code}: {exc.detail}"})
            continue
        markup = body.decode("utf-8", "replace")
        text = _text_of(markup)
        excerpt = " ".join(text.split())[:EXCERPT_CHARS]
        if len(excerpt) < 80:
            items.append({"evidence_id": evidence_id, "kind": "documentation",
                          "title": _title_of(markup), "url": url, "excerpt": "",
                          "error": "页面没有可引用的正文"})
            continue
        payload = (f"source: {url}\ntitle: {_title_of(markup)}\n"
                   f"retrieved_at: {_now()}\n"
                   f"note: the page's own text as fetched; not summarised, not verified\n\n"
                   f"{text}\n").encode("utf-8")
        path = documents / f"{evidence_id}.txt"
        path.write_bytes(payload)
        items.append({
            "evidence_id": evidence_id, "kind": "documentation",
            "title": _title_of(markup), "url": url, "excerpt": excerpt,
            "document": f"script/evidence/{evidence_id}.txt",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "retrieved_at": _now(),
        })
    pack = {"schema": PACK_SCHEMA, "topic": topic, "items": items}
    target = out / PACK_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return pack


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--topic", default="")
    parser.add_argument("--out", required=True, help="project directory")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    out = Path(args.out)
    if not out.is_absolute():
        out = (ROOT / out).resolve()
    pack = collect(args.urls, out, args.topic)
    usable = [item for item in pack["items"] if item.get("excerpt")]
    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
    else:
        print(f"pack       {out / PACK_FILE}")
        print(f"items      {len(usable)} usable of {len(pack['items'])}")
        for item in pack["items"]:
            status = "ok" if item.get("excerpt") else f"failed: {item.get('error')}"
            print(f"  {item['evidence_id']} {status} · {item['url']}")
    return 0 if usable else 4


if __name__ == "__main__":
    sys.exit(main())
