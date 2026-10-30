#!/usr/bin/env python3
"""Ensure the publisher cannot be called before final_reviewed."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "gzh-draft-publisher" / "scripts"))
import publish  # noqa: E402
from route_content import build_route  # noqa: E402
from account_context import ACCOUNT_ID, PUBLISH_SLOT  # noqa: E402


def main() -> int:
    parser_probe = subprocess.run(
        [sys.executable, str(ROOT / "skills" / "gzh-draft-publisher" / "scripts" / "publish.py"), "publish", "unbound-media"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert parser_probe.returncode != 0 and "--article" in (parser_probe.stdout + parser_probe.stderr), "裸 media_id 仍可调用 publish"
    with tempfile.TemporaryDirectory(prefix="publish-guard-qa-") as raw:
        article = Path(raw)
        (article / "article.yaml").write_text(
            f"account: {ACCOUNT_ID}\ncontent_medium: wechat_article\n", encoding="utf-8"
        )
        route = build_route("hotspot", "AI教程", "", ACCOUNT_ID, "test")
        (article / "routing.yaml").write_text(json.dumps(route, ensure_ascii=False, indent=2), encoding="utf-8")
        (article / "matrix-state.json").write_text(
            json.dumps({"schema_version": 4, "current_stage": "draft_complete"}), encoding="utf-8"
        )
        errors = publish._article_publish_guard(article)
        assert any("final_reviewed" in message for message in errors)
        env_path = article / "outside.env"
        env_path.write_text(f"WECHAT_{PUBLISH_SLOT}_APPID=test\nWECHAT_{PUBLISH_SLOT}_APPSECRET=test\n", encoding="utf-8")
        old_env = publish._cli_env_path
        try:
            publish._cli_env_path = str(env_path)
            assert publish._resolve_env_path() == env_path
        finally:
            publish._cli_env_path = old_env
    print("PUBLISH GUARD TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
