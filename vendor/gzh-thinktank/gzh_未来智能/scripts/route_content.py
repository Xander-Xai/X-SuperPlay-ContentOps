#!/usr/bin/env python3
"""Confirm the topic and account route before a WeChat article workspace exists.

The route is deliberately separate from article content.  It records whether
the topic should be discovered by a hotspot skill or expanded from material
provided by the user, then records the target matrix account.  Downstream
initialization and gates consume this file; they do not infer either choice
from an old article or conversation memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from workspace_paths import artifact_root, resolve_route_path  # noqa: E402
from account_context import (  # noqa: E402
    ACCOUNT_ID, ACCOUNT_IDS, DISPLAY_NAME, PUBLIC_BRAND, check_identity_consistency,
)
ACCOUNTS = {ACCOUNT_ID: DISPLAY_NAME}
TOPIC_MODES = {"hotspot", "user_material"}
MEDIUM = "wechat_article"
SEQUENCE = ("topic_route", "account_route")


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _yaml_load(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except ImportError:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}
    except (OSError, ValueError):
        return {}


def _yaml_dump(path: Path, value: dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore

        path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")
    except ImportError:
        # JSON is valid YAML 1.2 and keeps the route portable on minimal hosts.
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def route_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_route(path: Path) -> dict[str, Any]:
    """Load a route file for matrix initialization and gate checks."""

    return _yaml_load(path.expanduser().resolve())


def _looks_like_url(value: str) -> bool:
    return bool(re.match(r"^https?://\S+$", value.strip(), flags=re.I))


def validate_route_document(
    route: dict[str, Any],
    expected_account: str | None = None,
    base_dir: Path | None = None,
) -> list[str]:
    """Validate a route without reading credentials or making network calls."""

    errors: list[str] = []
    if not isinstance(route, dict):
        return ["routing.yaml 必须是对象"]
    try:
        schema_version = int(route.get("schema_version", 0) or 0)
    except (TypeError, ValueError):
        schema_version = 0
    if schema_version < 1:
        errors.append("routing.yaml 缺少有效 schema_version")
    if str(route.get("status", "")).strip().lower() != "confirmed":
        errors.append("routing.yaml 的 status 必须是 confirmed")
    if str(route.get("content_medium", "")).strip().lower() != MEDIUM:
        errors.append("公众号矩阵只允许 content_medium: wechat_article")
    sequence = route.get("sequence")
    if sequence != list(SEQUENCE):
        errors.append("路由顺序必须严格是 topic_route → account_route")

    topic = route.get("topic_route")
    if not isinstance(topic, dict):
        errors.append("缺少 topic_route")
    else:
        mode = str(topic.get("mode", "")).strip().lower()
        if mode not in TOPIC_MODES:
            errors.append("topic_route.mode 必须是 hotspot 或 user_material")
        if not str(topic.get("selected_skill", "")).strip():
            errors.append("topic_route 必须记录 selected_skill")
        if mode == "hotspot" and topic.get("selected_skill") not in {
            "gzh-topic-research",
            "wechat-viral-topic",
            "exa-web-search-free",
        }:
            errors.append("热点路由必须指向热点/检索 Skill")
        if mode == "user_material":
            if topic.get("selected_skill") not in {"gzh-article-writing", "content-production"}:
                errors.append("用户资料路由必须指向文案/内容生产 Skill")
            reference = str(topic.get("reference", "")).strip()
            if not reference:
                errors.append("user_material 路由必须记录用户提供的选题或文档")
            elif not _looks_like_url(reference):
                reference_path = Path(reference).expanduser()
                if not reference_path.is_absolute():
                    reference_path = (base_dir or ROOT) / reference_path
                if not reference_path.is_file():
                    errors.append(f"用户资料路由引用不存在：{reference}")
        if not str(topic.get("routed_at", "")).strip():
            errors.append("topic_route 缺少 routed_at")

    account = route.get("account_route")
    if not isinstance(account, dict):
        errors.append("缺少 account_route")
    else:
        account_id = str(account.get("account", "")).strip().lower()
        if account_id not in ACCOUNTS:
            errors.append(f"account_route.account 必须是 {ACCOUNT_ID}（本工作流唯一账号）")
        if expected_account and account_id != expected_account.strip().lower():
            errors.append("routing.yaml 的账号与 article.yaml 不一致")
        if str(account.get("display_name", "")).strip() != ACCOUNTS.get(account_id, ""):
            errors.append("account_route.display_name 与账号不一致")
        if not str(account.get("routed_at", "")).strip():
            errors.append("account_route 缺少 routed_at")
    if not str(route.get("operator", "")).strip():
        errors.append("routing.yaml 缺少 operator")
    return errors


def _prompt_choice(prompt: str, choices: dict[str, str]) -> str:
    print(prompt)
    for key, label in choices.items():
        print(f"  {key}. {label}")
    while True:
        answer = input("请选择：").strip()
        if answer in choices:
            return answer
        print("输入无效，请重新选择。")


def _interactive_values() -> tuple[str, str, str, str, str]:
    topic_choice = _prompt_choice(
        "第一步：选题路由（先决定热点检索还是使用你提供的材料）",
        {"1": "调用热点/趋势筛选 Skill", "2": "使用我提供的选题或文档扩展文案"},
    )
    topic_mode = "hotspot" if topic_choice == "1" else "user_material"
    topic = input("选题或热点关键词（热点模式可留空）：").strip()
    reference = ""
    if topic_mode == "user_material":
        reference = input("请提供选题原文、文档路径或 URL：").strip()
    print(f"第二步：账号已固定为 {DISPLAY_NAME} / {ACCOUNT_ID}（仅记录确认，不需要二选一）")
    return topic_mode, topic, reference, ACCOUNT_ID, "interactive-user"


def build_route(topic_mode: str, topic: str, reference: str, account: str, operator: str) -> dict[str, Any]:
    topic_mode = topic_mode.strip().lower()
    account = account.strip().lower()
    if account not in ACCOUNT_IDS:
        raise ValueError(f"本工作流只允许账号 {ACCOUNT_ID}，收到 {account!r}")
    now = _now()
    selected_skill = "gzh-topic-research" if topic_mode == "hotspot" else "gzh-article-writing"
    return {
        "schema_version": 1,
        "status": "confirmed",
        "content_medium": MEDIUM,
        "sequence": list(SEQUENCE),
        "topic_route": {
            "mode": topic_mode,
            "topic": topic.strip(),
            "reference": reference.strip(),
            "selected_skill": selected_skill,
            "routed_at": now,
        },
        "account_route": {
            "account": account,
            "display_name": ACCOUNTS.get(account, ""),
            "routed_at": now,
        },
        "operator": operator.strip() or "interactive-user",
        "confirmed_at": now,
    }


def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interactive", action="store_true", help="按顺序向用户询问选题路由和账号路由")
    parser.add_argument("--topic-mode", choices=sorted(TOPIC_MODES))
    parser.add_argument("--topic", default="")
    parser.add_argument("--reference", default="")
    parser.add_argument("--account", default=ACCOUNT_ID, choices=sorted(ACCOUNT_IDS),
                        help=f"固定为本工作流账号 {ACCOUNT_ID}，传其他值会被拒绝")
    parser.add_argument("--operator", default="cli-user")
    parser.add_argument("--output", type=Path, help="路由文件路径；默认写入外部 artifact root/registry/routes")
    args = parser.parse_args()

    if args.interactive:
        if args.topic_mode is not None:
            parser.error("--interactive 不能与 --topic-mode 混用")
        if args.account not in ACCOUNT_IDS:
            parser.error(f"账号必须为 {ACCOUNT_ID}（单账号工作流）")
        topic_mode, topic, reference, account, operator = _interactive_values()
    else:
        if not args.topic_mode:
            parser.error("必须先运行 --interactive，或提供 --topic-mode")
        topic_mode, topic, reference, account, operator = (
            args.topic_mode,
            args.topic,
            args.reference,
            args.account,
            args.operator,
        )
    route = build_route(topic_mode, topic, reference, ACCOUNT_ID, operator)
    errors = validate_route_document(route, expected_account=ACCOUNT_ID)
    if errors:
        print("ROUTE BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    routes_root = artifact_root(create=True) / "registry" / "routes"
    output = args.output.expanduser() if args.output else routes_root / f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-{account}.yaml"
    if not output.is_absolute():
        output = routes_root / output
    try:
        output = resolve_route_path(
            output,
            allow_test_fixture=os.environ.get("WORKFLOW_TEST_MODE") == "1",
            allow_repo=False,
        )
    except ValueError as exc:
        print(f"ROUTE BLOCKED: {exc}")
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    _yaml_dump(output, route)
    print(f"ROUTE CONFIRMED: {output.resolve()}")
    print(f"TOPIC_ROUTE={topic_mode}")
    print(f"ACCOUNT_ROUTE={account}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
