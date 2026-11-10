#!/usr/bin/env python3
"""Record, verify and audit manual publication receipts — after a human posted.

Why this exists
---------------
``publisher.py`` stops at ``AWAITING_MANUAL_PUBLISH`` and ``scripts/x_post.py
--mark-published`` records an X status URL. Every other track had nowhere to
bring the fact of publication back. A publish count that cannot name its URL,
its time, its version and who confirmed it is not evidence; this command makes
that record strict, per platform, or refuses.

The receipt this command writes is a claim by a person, on the record. It is
never produced by any code path that posts. A later independent readback
(``--verify``) is also a human observation; nothing here scrapes.

Usage
-----
    python scripts/publish_backfill.py record --project projects/<slug> \
        --platform bilibili --id 20261101-001 \
        --url "https://www.bilibili.com/video/BV..." \
        --published-at "2026-11-09T14:00:00+08:00" \
        --confirmed-by "<name>" \
        --artifact-sha256 <64 hex> \
        --package-receipt receipts/x-package-20261101-001.json

    python scripts/publish_backfill.py verify --project projects/<slug> \
        --receipt receipts/publish_backfill/backfill-bilibili-20261101-001.json \
        --method MANUAL_INSPECT --evidence "screenshots/bilibili-live.png"

    python scripts/publish_backfill.py list --project projects/<slug> [--json]

Receipts live under ``<project>/receipts/publish_backfill/``. Exit codes:
0 pass, 1 refusal, 2 misuse.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.publish.backfill import (  # noqa: E402
    BackfillError,
    iter_backfills,
    mark_readback_failed,
    record_backfill,
    summary,
    verify_readback,
)

BACKFILL_DIR = Path("receipts") / "publish_backfill"


def _fail(exc: BackfillError) -> int:
    print(f"REFUSED: {exc}", file=sys.stderr)
    return 1


def _receipts_dir(project: Path) -> Path:
    return project / BACKFILL_DIR


def _cmd_record(args: argparse.Namespace) -> int:
    payload = {
        "platform": args.platform,
        "content_id": args.content_id,
        "post_url": args.url,
        "published_at": args.published_at,
        "confirmed_by": args.confirmed_by,
        "confirmed_at": args.confirmed_at,
        "artifact_sha256": args.artifact_sha256,
        "source_commit": args.source_commit,
        "package_receipt_ref": args.package_receipt,
        "note": args.note,
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    project = Path(args.project).resolve()
    document = record_backfill(
        payload, _receipts_dir(project), project=project)
    path = document.pop("receipt")
    print(json.dumps({"recorded": str(path), "receipt": document},
                     indent=2, ensure_ascii=False))
    return 0


def _find_receipt(project: Path, receipt: Optional[str], platform: Optional[str],
                  content_id: Optional[str]) -> Optional[Path]:
    if receipt:
        return project / receipt
    if platform and content_id:
        candidate = _receipts_dir(project) / f"backfill-{platform}-{content_id}.json"
        return candidate if candidate.is_file() else None
    return None


def _cmd_verify(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    path = _find_receipt(project, args.receipt, args.platform, args.content_id)
    if path is None or not path.is_file():
        print("REFUSED: [BACKFILL_MISSING] name --receipt or --platform with --id",
              file=sys.stderr)
        return 2
    if args.failed:
        document = mark_readback_failed(
            path, method=args.method, note=args.note or "")
    else:
        document = verify_readback(
            path, method=args.method, evidence_ref=args.evidence or "",
            note=args.note or "")
    print(json.dumps(document, indent=2, ensure_ascii=False))
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    documents = iter_backfills(_receipts_dir(project))
    if args.json:
        print(json.dumps({"receipts": documents, "summary": summary(_receipts_dir(project))},
                         indent=2, ensure_ascii=False))
        return 0
    if not documents:
        print("no publication backfills recorded")
        return 0
    for document in documents:
        readback = document.get("readback") or {}
        line = (f"{document.get('platform')} {document.get('content_id')} "
                f"{document.get('status')} {document.get('post_url')} "
                f"readback={readback.get('status', 'PENDING')}")
        print(line)
    print(json.dumps(summary(_receipts_dir(project)), ensure_ascii=False))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Record and verify manual publication receipts. Never publishes.")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--record", action="store_true",
                         help="record a person's publication claim")
    actions.add_argument("--verify", action="store_true",
                         help="record an independent readback of a live post")
    actions.add_argument("--verify-failed", dest="failed", action="store_true",
                         help="record a readback that could not confirm the post")
    actions.add_argument("--list", action="store_true",
                         help="list recorded publications")
    parser.add_argument("--project", default=".",
                        help="project directory holding receipts/ (default: cwd)")
    parser.add_argument("--platform", help="x | bilibili | xiaohongshu | douyin | gzh | shipinhao")
    parser.add_argument("--id", dest="content_id", help="content id the receipt is about")
    parser.add_argument("--url", help="the real post URL, copied from the platform")
    parser.add_argument("--published-at", dest="published_at",
                        help="ISO-8601 observation of when it went live")
    parser.add_argument("--confirmed-by", dest="confirmed_by",
                        help="who asserts this publication happened")
    parser.add_argument("--confirmed-at", dest="confirmed_at",
                        help="ISO-8601; defaults to now")
    parser.add_argument("--artifact-sha256", dest="artifact_sha256",
                        help="sha-256 of the exact published artifact")
    parser.add_argument("--source-commit", dest="source_commit",
                        help="git commit of the exact published version")
    parser.add_argument("--package-receipt", dest="package_receipt",
                        help="path to the package receipt this publication fulfils")
    parser.add_argument("--receipt", help="backfill receipt path, for --verify/--verify-failed")
    parser.add_argument("--method", default="MANUAL_INSPECT",
                        help="MANUAL_INSPECT | SCREENSHOT | PLATFORM_EXPORT")
    parser.add_argument("--evidence", help="evidence path for a VERIFIED readback")
    parser.add_argument("--note", help="verbatim human note")
    parser.add_argument("--json", action="store_true", help="machine-readable --list output")
    args = parser.parse_args(argv)

    try:
        if args.record:
            missing = [name for name in ("platform", "content_id", "url", "published_at",
                                         "confirmed_by") if not getattr(args, name)]
            if missing:
                parser.error(f"--record requires: {', '.join('--' + name for name in missing)}")
            return _cmd_record(args)
        if args.verify or args.failed:
            if not args.method:
                parser.error("--verify requires --method")
            return _cmd_verify(args)
        return _cmd_list(args)
    except BackfillError as exc:
        return _fail(exc)


if __name__ == "__main__":
    sys.exit(main())
