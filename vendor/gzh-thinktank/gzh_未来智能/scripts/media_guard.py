#!/usr/bin/env python3
"""Shared guard for optional video/audio derivatives of a WeChat article."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from route_content import validate_route_document  # noqa: E402
from account_context import ACCOUNT_ID, ACCOUNT_IDS  # noqa: E402


DERIVATIVE_PLATFORMS = {"video", "douyin", "short_video", "audio"}
READY_STAGES = {"final_reviewed", "draft_submitted"}


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (ImportError, OSError, ValueError):
        return {}


def _fresh_final_gate_errors(article_dir: Path) -> list[str]:
    """Re-check the complete primary workflow before allowing derivatives.

    ``matrix-state.json`` is a historical advancement receipt, not proof that
    the current article bytes still satisfy every earlier gate.  Derivative
    generation must therefore use the same high-stakes read-only gate that the
    publisher uses.  The optional external env path is passed through when it
    is available so environment/capability checks remain fail-closed.
    """

    command = [
        sys.executable,
        str(ROOT / "scripts" / "workflow_gate.py"),
        "--article",
        str(article_dir),
        "--stage",
        "final_reviewed",
        "--all",
    ]
    env_path = os.environ.get("CONTENT_ENV_PATH", "").strip() or os.environ.get("WECHAT_ENV_PATH", "").strip()
    if env_path:
        command.extend(["--env", env_path])
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return [f"final_reviewed 门禁复核无法启动：{exc}"]
    if result.returncode == 0:
        return []
    detail = (result.stdout + result.stderr).strip().splitlines()
    return ["主稿未通过当前 final_reviewed 全链门禁：" + (detail[-1] if detail else "无输出")]


def derivative_guard(article_dir: Path, platform: str = "video") -> list[str]:
    """Return blocking reasons; an empty list means a derivative is allowed."""

    article_dir = article_dir.expanduser().resolve()
    platform = platform.strip().lower()
    errors: list[str] = []
    if platform not in DERIVATIVE_PLATFORMS:
        errors.append(f"不支持的派生媒体平台：{platform}")
    state_path = article_dir / "matrix-state.json"
    meta_path = article_dir / "article.yaml"
    route_path = article_dir / "routing.yaml"
    if not state_path.is_file():
        errors.append("缺少 matrix-state.json；派生媒体不能脱离公众号工作区")
    if not meta_path.is_file():
        errors.append("缺少 article.yaml；无法确认账号和公众号内容类型")
    if not route_path.is_file():
        errors.append("缺少 routing.yaml；必须先完成选题路由和账号路由")
    state = _json(state_path)
    meta = _yaml(meta_path)
    route = _yaml(route_path)
    if state:
        stage = str(state.get("current_stage") or state.get("status") or "none").strip().lower()
        if stage not in READY_STAGES:
            errors.append(
                f"公众号主稿尚未完成 final_reviewed；当前阶段是 {stage or 'none'}，不能生成 {platform} 派生内容"
            )
        else:
            errors.extend(_fresh_final_gate_errors(article_dir))
    if meta and str(meta.get("content_medium", "")).strip().lower() != "wechat_article":
        errors.append("派生来源的 content_medium 必须是 wechat_article")
    account = str(meta.get("account", "")).strip().lower() if meta else ""
    if account and account not in ACCOUNT_IDS:
        errors.append(f"账号必须是 {ACCOUNT_ID}（本工作流唯一账号，收到 {account!r}）")
    if route:
        errors.extend(validate_route_document(route, expected_account=account or None))
    return errors


def assert_derivative_allowed(article_dir: Path, platform: str = "video") -> None:
    errors = derivative_guard(article_dir, platform)
    if errors:
        raise RuntimeError("派生媒体门禁未通过：" + "；".join(errors))


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--platform", default="video")
    args = parser.parse_args()
    errors = derivative_guard(args.article, args.platform)
    if errors:
        print("MEDIA DERIVATIVE BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"MEDIA DERIVATIVE ALLOWED: {args.platform}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
