#!/usr/bin/env python3
"""Regression tests for content-addressed asset indexing."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from build_asset_index import build, check


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="asset-index-") as raw:
        article = Path(raw) / "article"
        (article / "imgs").mkdir(parents=True)
        asset = article / "imgs" / "section-01.png"
        asset.write_bytes(b"deterministic-image")
        digest = __import__("hashlib").sha256(asset.read_bytes()).hexdigest()
        (article / "image-sources.json").write_text(json.dumps({
            "schema_version": 1,
            "assets": [{
                "path": "imgs/section-01.png", "origin": "generated",
                "source": "test", "license": "test-license",
                "reuse_approved": False, "sha256": digest,
            }],
        }), encoding="utf-8")
        library = Path(raw) / "library.json"
        assert build(article, library) == 0
        assert check(article) == 0
        doc = json.loads((article / "asset-index.json").read_text(encoding="utf-8"))
        assert doc["contract"] == "asset-index-v1"
        assert doc["assets"][0]["asset_id"] == digest
        asset.write_bytes(b"tampered")
        assert check(article) == 1
    print("ASSET INDEX TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
