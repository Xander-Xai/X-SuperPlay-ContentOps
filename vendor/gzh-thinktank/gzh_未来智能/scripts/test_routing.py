#!/usr/bin/env python3
"""Regression tests for mandatory topic/account routing (single-account split)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from route_content import build_route, load_route, route_digest, validate_route_document  # noqa: E402
from account_context import ACCOUNT_ID, ACCOUNT_IDS  # noqa: E402

OTHER = sorted(ACCOUNT_IDS - {ACCOUNT_ID})[0] if len(ACCOUNT_IDS - {ACCOUNT_ID}) == 1 else "other"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="routing-qa-") as raw:
        root = Path(raw)
        reference = root / "user-notes.md"
        reference.write_text("用户提供的公众号选题资料。", encoding="utf-8")
        route = build_route("user_material", "门禁为什么会失效", str(reference), ACCOUNT_ID, "test")
        assert validate_route_document(route, expected_account=ACCOUNT_ID) == []
        broken = dict(route)
        broken["sequence"] = ["account_route", "topic_route"]
        assert validate_route_document(broken, expected_account=ACCOUNT_ID)
        assert validate_route_document(route, expected_account=OTHER)

        # Relative user-material references resolve from the workflow root,
        # not from whichever directory launched the CLI.
        root_reference = ROOT / ".audit-routing-reference.md"
        root_reference.write_text("relative reference fixture", encoding="utf-8")
        old_cwd = Path.cwd()
        try:
            os.chdir(root)
            relative_route = build_route("user_material", "相对路径测试", root_reference.name, ACCOUNT_ID, "test")
            assert validate_route_document(relative_route, expected_account=ACCOUNT_ID) == []
        finally:
            os.chdir(old_cwd)
            root_reference.unlink(missing_ok=True)

        artifact_root = root / "artifact-root"
        interactive_path = artifact_root / "registry" / "routes" / "interactive-route.yaml"
        interactive_path.parent.mkdir(parents=True)
        test_env = os.environ.copy()
        test_env["GZH_ARTIFACT_ROOT"] = str(artifact_root)
        interactive = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "route_content.py"), "--interactive", "--output", str(interactive_path)],
            cwd=ROOT,
            env=test_env,
            input="1\nAI工具热点\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert interactive.returncode == 0, interactive.stdout + interactive.stderr
        interactive_route = load_route(interactive_path)
        assert interactive_route["sequence"] == ["topic_route", "account_route"]
        assert interactive_route["topic_route"]["mode"] == "hotspot"
        assert interactive_route["account_route"]["account"] == ACCOUNT_ID

        route_path = artifact_root / "registry" / "routes" / "route.yaml"
        route_path.parent.mkdir(parents=True, exist_ok=True)
        route_path.write_text(json.dumps(route, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        article_root = artifact_root / "active"
        missing_route = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "matrix_init.py"),
                "--account",
                ACCOUNT_ID,
                "--title",
                "无路由不得初始化",
                "--root",
                str(article_root),
            ],
                cwd=ROOT,
                env=test_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert missing_route.returncode != 0
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "matrix_init.py"),
                "--account",
                ACCOUNT_ID,
                "--title",
                "路由测试文章",
                "--root",
                str(article_root),
                "--route",
                str(route_path),
            ],
                cwd=ROOT,
                env=test_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        articles = list(article_root.glob("*"))
        assert len(articles) == 1
        article = articles[0]
        assert (article / "routing.yaml").is_file()
        metadata = (article / "article.yaml").read_text(encoding="utf-8")
        assert "content_medium: wechat_article" in metadata
        state = json.loads((article / "matrix-state.json").read_text(encoding="utf-8"))
        assert state["schema_version"] == 4
        assert state["routing_digest"] == route_digest(article / "routing.yaml")
        assert state["workspace_id"].startswith("THK-")
        assert (article / "workspace-manifest.json").is_file()
        metrics = json.loads((article / "metrics.json").read_text(encoding="utf-8"))
        assert metrics["attribution"]["primary_cta"]
        assert metrics["attribution"]["reply_keyword"]
        assert metrics["attribution"]["lead_magnet"]
        assert "article_预览.html" in state["artifacts"]
        assert "preview_screenshot.png" in state["artifacts"]
    print("ROUTING TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
