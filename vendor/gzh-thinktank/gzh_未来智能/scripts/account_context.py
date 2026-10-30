#!/usr/bin/env python3
"""Single source of truth for the split workflow identity.

Every split target carries exactly one workflow-identity.yaml.  This module is
copied into each target and is the ONLY way gate/router/init/visual scripts
learn the fixed account id, themes and publish slot.  It deliberately performs
no network calls and reads no secrets.

Usage:
    from account_context import (
        ACCOUNT_ID, ACCOUNT_IDS, PROFILE_NAME, FORMatter_THEME,
        IMAGE_THEME, PUBLISH_SLOT, identity, check_identity_consistency,
        assert_account,
    )

Design (v0.2 plan):
  * 单账号身份: account 是一个常量, 不再是运行时二选一.
  * 一致性校验: 目录名/profile/identity/主题/发布槽位 必须一致,
    不一致时 environment_ready 必须阻断.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# ── identity document ─────────────────────────────────────────────────────
IDENTITY_PATH = ROOT / "workflow-identity.yaml"

def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        from workflow_security import load_yaml as strict_load_yaml

        data = strict_load_yaml(path, default={}) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def identity() -> dict[str, Any]:
    if not IDENTITY_PATH.is_file():
        raise RuntimeError(f"缺少 workflow-identity.yaml：{IDENTITY_PATH}")
    data = _load_yaml(IDENTITY_PATH)
    if not data or not str(data.get("account_id", "")).strip():
        raise RuntimeError("workflow-identity.yaml 无法解析或缺少 account_id")
    return data


_IDENTITY = identity()
ACCOUNT_ID = str(_IDENTITY["account_id"]).strip().lower()
ACCOUNT_IDS = frozenset({ACCOUNT_ID})
PROFILE_NAME = f"{ACCOUNT_ID}.yaml"
DISPLAY_NAME = str(_IDENTITY.get("display_name") or _IDENTITY.get("public_brand") or ACCOUNT_ID)
PUBLIC_BRAND = str(_IDENTITY.get("public_brand") or DISPLAY_NAME)
INTERNAL_ACCOUNT_NAME = str(_IDENTITY.get("internal_account_name") or DISPLAY_NAME)
FORMATTER_THEME = str(_IDENTITY.get("formatter_theme") or f"{ACCOUNT_ID}-radar")
IMAGE_THEME = str(_IDENTITY.get("image_theme") or f"{ACCOUNT_ID}-radar")
PUBLISH_SLOT = int(_IDENTITY.get("wechat_publish_slot") or 1)
CONTENT_MEDIUM = str(_IDENTITY.get("content_medium") or "wechat_article")
CONTENT_LENGTH = str(_IDENTITY.get("content_length") or "")


def assert_account(value: Any) -> bool:
    """Return True if ``value`` matches the fixed account id (or is empty).

    Anything that is not the single legal account is rejected by design.
    """
    if value is None:
        return False
    return str(value).strip().lower() == ACCOUNT_ID


def require_account(value: Any) -> str:
    """Validate an explicit account argument against this split target."""
    if not assert_account(value):
        raise ValueError(f"本工作流只允许账号 {ACCOUNT_ID}，收到 {value!r}")
    return ACCOUNT_ID


def check_identity_consistency(root: Path | None = None) -> list[str]:
    """Verify directory name / profile / identity / themes / slot agree.

    Returns a list of human-readable problems (empty when consistent).
    """
    root = root or ROOT
    errors: list[str] = []
    identity_file = root / "workflow-identity.yaml"
    if not identity_file.is_file():
        errors.append("缺少 workflow-identity.yaml")
        return errors
    ident = _load_yaml(identity_file)
    aid = str(ident.get("account_id", "")).strip().lower()
    if aid != ACCOUNT_ID:
        errors.append(f"workflow-identity.yaml account_id={aid!r} 与模块固定账号 {ACCOUNT_ID!r} 不一致")
    # profile must exist and carry the same account
    profile = root / "profiles" / PROFILE_NAME
    if not profile.is_file():
        errors.append(f"缺少本账号 profile: profiles/{PROFILE_NAME}")
    else:
        pdata = _load_yaml(profile)
        if str(pdata.get("account_id", "")).strip().lower() != ACCOUNT_ID:
            errors.append(f"profiles/{PROFILE_NAME} account_id 与 workflow-identity 不一致")
    # visual-styles must carry this account theme block
    vstyles = root / "profiles" / "visual-styles.yaml"
    if vstyles.is_file():
        text = vstyles.read_text(encoding="utf-8")
        if f"{ACCOUNT_ID}:" not in text:
            errors.append(f"profiles/visual-styles.yaml 缺少本账号主题块 {ACCOUNT_ID}:")
    # config slot
    config = root / ".aws-article" / "config.yaml"
    if config.is_file():
        text = config.read_text(encoding="utf-8")
        slot_marker = f"wechat_publish_slot: {PUBLISH_SLOT}"
        if slot_marker not in text:
            errors.append(f".aws-article/config.yaml 缺少 {slot_marker}（发布槽位不一致）")
    return errors


if __name__ == "__main__":
    problems = check_identity_consistency()
    if problems:
        print("ACCOUNT CONTEXT INCONSISTENT")
        for p in problems:
            print(f"- {p}")
        sys.exit(1)
    print(f"ACCOUNT CONTEXT OK: {ACCOUNT_ID} slot={PUBLISH_SLOT} theme={FORMATTER_THEME}")
