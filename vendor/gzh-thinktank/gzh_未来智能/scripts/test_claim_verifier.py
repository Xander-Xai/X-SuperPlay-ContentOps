#!/usr/bin/env python3
"""Negative/positive tests for deterministic claim provenance verification."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from article_integrity import sha256_file  # noqa: E402
from verify_claims import verify  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="claim-verifier-") as raw:
        article = Path(raw)
        snapshots = article / "source-snapshots"
        snapshots.mkdir()
        snap = snapshots / "fixture.raw"
        snap.write_bytes(b"evidence fixture")
        source = {
            "id": "fixture",
            "title": "fixture",
            "url": "https://example.com/fixture",
            "kind": "test-fixture",
            "evidence_level": "fixture",
            "content_sha256": sha256_file(snap),
        }
        claim = {
            "id": "claim-1",
            "statement": "可定位的测试主张",
            "claim_type": "test-result",
            "source_ids": ["fixture"],
            "evidence_locator": {"source_id": "fixture", "kind": "snapshot", "ref": "source-snapshots/fixture.raw#fixture"},
        }
        (article / "sources.json").write_text(json.dumps({"sources": [source], "claims": [claim]}, ensure_ascii=False), encoding="utf-8")
        assert verify(article) == 0
        claim.pop("evidence_locator")
        (article / "sources.json").write_text(json.dumps({"sources": [source], "claims": [claim]}, ensure_ascii=False), encoding="utf-8")
        assert verify(article) == 1, "missing evidence_locator must block"
    print("CLAIM VERIFIER TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
