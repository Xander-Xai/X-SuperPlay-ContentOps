#!/usr/bin/env python3
"""Regression tests for article-first derivative media policy."""

from __future__ import annotations

import json
import sys
import tempfile
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from media_guard import derivative_guard  # noqa: E402
from route_content import build_route  # noqa: E402
from account_context import ACCOUNT_ID  # noqa: E402


def test_derivative_blocks_stale_final_reviewed_state() -> None:
    with tempfile.TemporaryDirectory(prefix="media-guard-stale-qa-") as raw:
        article = Path(raw)
        (article / "article.yaml").write_text(
            f"account: {ACCOUNT_ID}\ncontent_medium: wechat_article\n", encoding="utf-8"
        )
        route = build_route("hotspot", "AI工具实测", "", ACCOUNT_ID, "test")
        (article / "routing.yaml").write_text(json.dumps(route, ensure_ascii=False, indent=2), encoding="utf-8")
        (article / "matrix-state.json").write_text(
            json.dumps({"schema_version": 4, "current_stage": "final_reviewed"}), encoding="utf-8"
        )
        with patch("media_guard._fresh_final_gate_errors", return_value=["stale gate"]):
            errors = derivative_guard(article, "video")
        assert any("stale gate" in message for message in errors)


def test_derivative_allows_only_after_fresh_final_reviewed_gate() -> None:
    with tempfile.TemporaryDirectory(prefix="media-guard-fresh-qa-") as raw:
        article = Path(raw)
        (article / "article.yaml").write_text(
            f"account: {ACCOUNT_ID}\ncontent_medium: wechat_article\n", encoding="utf-8"
        )
        route = build_route("hotspot", "AI工具实测", "", ACCOUNT_ID, "test")
        (article / "routing.yaml").write_text(json.dumps(route, ensure_ascii=False, indent=2), encoding="utf-8")
        (article / "matrix-state.json").write_text(
            json.dumps({"schema_version": 4, "current_stage": "final_reviewed"}), encoding="utf-8"
        )
        with patch("media_guard._fresh_final_gate_errors", return_value=[]):
            assert derivative_guard(article, "video") == []


def main() -> int:
    test_derivative_blocks_stale_final_reviewed_state()
    test_derivative_allows_only_after_fresh_final_reviewed_gate()
    with tempfile.TemporaryDirectory(prefix="media-guard-qa-") as raw:
        article = Path(raw)
        (article / "article.yaml").write_text(
            f"account: {ACCOUNT_ID}\ncontent_medium: wechat_article\n", encoding="utf-8"
        )
        route = build_route("hotspot", "AI工具实测", "", ACCOUNT_ID, "test")
        (article / "routing.yaml").write_text(json.dumps(route, ensure_ascii=False, indent=2), encoding="utf-8")
        (article / "matrix-state.json").write_text(
            json.dumps({"schema_version": 4, "current_stage": "draft_complete"}), encoding="utf-8"
        )
        blocked = derivative_guard(article, "video")
        assert any("final_reviewed" in message for message in blocked)
        (article / "matrix-state.json").write_text(
            json.dumps({"schema_version": 4, "current_stage": "final_reviewed"}), encoding="utf-8"
        )
        with patch("media_guard._fresh_final_gate_errors", return_value=[]):
            assert derivative_guard(article, "douyin") == []
    print("MEDIA GUARD TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
