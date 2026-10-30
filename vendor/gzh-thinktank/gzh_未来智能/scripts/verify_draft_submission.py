#!/usr/bin/env python3
"""Read a WeChat draft back and write the auditable submission receipt.

The publisher creates a draft; this companion command performs the required
``draft/get`` readback and only then marks ``publish_completed`` true.  The
credential file is supplied out-of-repository through ``--env`` or
``WECHAT_ENV_PATH`` and is never copied or printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from article_integrity import canonical_html_digest, sha256_file  # noqa: E402
from receipt_integrity import ROOT as WORKFLOW_ROOT, stamp as stamp_receipt  # noqa: E402
from account_context import PUBLISH_SLOT  # noqa: E402
from workflow_security import load_json as strict_load_json, load_yaml as strict_load_yaml, ensure_article_path  # noqa: E402


GETDRAFT = ROOT / "skills" / "gzh-draft-publisher" / "scripts" / "getdraft.py"
VALIDATOR = ROOT / "skills" / "gzh-design-skill" / "scripts" / "validate_gzh_html.py"


def _yaml(path: Path) -> dict[str, Any]:
    value = strict_load_yaml(path, default={})
    return value if isinstance(value, dict) else {}


def _readback_item(data: dict[str, Any]) -> dict[str, Any]:
    items = data.get("news_item")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise ValueError("draft/get 没有返回 news_item")
    return items[0]


def analyze_readback(
    meta: dict[str, Any],
    item: dict[str, Any],
    validator_passed: bool,
    local_html: str = "",
) -> dict[str, Any]:
    html = str(item.get("content") or "")
    title = str(item.get("title") or "")
    author = str(item.get("author") or "")
    digest = str(item.get("digest") or "")
    remote_digest = canonical_html_digest(html)
    local_digest = canonical_html_digest(local_html) if local_html else ""
    local_image_count = len(re.findall(r"<img\b", local_html, flags=re.I)) if local_html else 0
    local_formula_count = len(re.findall(r"imgs/formulas/|/formulas/", local_html, flags=re.I)) if local_html else 0
    return {
        "title_matches": title == str(meta.get("title") or ""),
        "author_matches": author == str(meta.get("author") or ""),
        "digest_matches": digest == str(meta.get("digest") or ""),
        "literal_unicode_escapes": len(re.findall(r"\\u[0-9a-fA-F]{4}", html)),
        "replacement_characters": html.count("\ufffd"),
        "content_has_div": bool(re.search(r"<div\b", html, flags=re.I)),
        "html_validator": "passed" if validator_passed else "failed",
        "local_html_digest": local_digest,
        "remote_html_digest": remote_digest,
        "html_digest_matches": bool(local_digest) and local_digest == remote_digest,
        "html_normalization_status": (
            "exact" if local_digest and local_digest == remote_digest else "wechat_draft_normalized"
        ),
        "image_count": len(re.findall(r"<img\b", html, flags=re.I)),
        "body_anchor_count": max(0, len(re.findall(r"<img\b", html, flags=re.I)) - local_formula_count),
        "formula_image_count": local_formula_count,
        "remote_content_chars": len(html),
    }


def _validator_passed(article_html: Path) -> bool:
    if not VALIDATOR.is_file():
        return False
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--strict", str(article_html)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode == 0


def _verified_attempt_payload(
    attempt: dict[str, Any],
    *,
    media_id: str,
    thumb_media_id: str,
    verified_at: str,
    html_digest: str,
    operation_id: str,
) -> dict[str, Any]:
    """Return the normalized, post-readback attempt transaction outcome."""

    result = dict(attempt)
    result.update({
        "schema_version": 1,
        "status": "passed",
        "draft_status": "draft_created_and_verified",
        "mode": "draft",
        "account_slot": int(PUBLISH_SLOT),
        "media_id": media_id,
        "thumb_media_id": thumb_media_id,
        "verified_at": verified_at,
        "html_digest": html_digest,
        "operation_id": operation_id,
    })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--media-id", help="草稿 media_id；省略时从 publish-attempt.json 自动读取")
    parser.add_argument("--account", help="微信槽位序号或名称；省略时从 publish-attempt.json/article.yaml 读取")
    parser.add_argument("--env", type=Path, help="仓库外 aws.env 路径")
    args = parser.parse_args()

    try:
        article_dir = ensure_article_path(args.article, allow_test_fixture=False)
    except ValueError as exc:
        print(f"DRAFT VERIFY BLOCKED: {exc}", file=sys.stderr)
        return 1
    meta_path = article_dir / "article.yaml"
    html_path = article_dir / "article.html"
    if not meta_path.is_file() or not html_path.is_file():
        print("DRAFT VERIFY BLOCKED: article.yaml 或 article.html 缺失", file=sys.stderr)
        return 1
    attempt_path = article_dir / "publish-attempt.json"
    attempt: dict[str, Any] = {}
    if attempt_path.is_file():
        try:
            raw_attempt = strict_load_json(attempt_path, default={})
            attempt = raw_attempt if isinstance(raw_attempt, dict) else {}
        except (OSError, json.JSONDecodeError):
            attempt = {}
    media_id = str(args.media_id or attempt.get("media_id") or "").strip()
    account = str(args.account or attempt.get("account_slot") or "").strip()
    if not account:
        account = str(PUBLISH_SLOT)
    if not media_id:
        print("DRAFT VERIFY BLOCKED: 缺少 media_id；请先执行 publish.py full", file=sys.stderr)
        return 1
    try:
        if int(account) != int(PUBLISH_SLOT):
            print(
                f"DRAFT VERIFY BLOCKED: 账号槽位 {account} 与工作流固定槽位 {PUBLISH_SLOT} 不一致",
                file=sys.stderr,
            )
            return 1
    except (TypeError, ValueError):
        print("DRAFT VERIFY BLOCKED: --account 必须是当前工作流的数值槽位", file=sys.stderr)
        return 1
    env_raw = str(args.env or os.environ.get("WECHAT_ENV_PATH") or "").strip()
    env_path = Path(env_raw).expanduser().resolve() if env_raw else None
    if env_path is None:
        print("DRAFT VERIFY BLOCKED: 必须通过 --env 或 WECHAT_ENV_PATH 指定仓库外凭证文件", file=sys.stderr)
        return 1
    try:
        env_path.relative_to(WORKFLOW_ROOT.resolve())
        print("DRAFT VERIFY BLOCKED: 凭证文件必须位于仓库外", file=sys.stderr)
        return 1
    except ValueError:
        pass
    if not env_path.is_file():
        print(f"DRAFT VERIFY BLOCKED: 凭证文件不存在：{env_path}", file=sys.stderr)
        return 1

    environment = os.environ.copy()
    if env_path:
        environment["WECHAT_ENV_PATH"] = str(env_path)
    # The desktop shell may use a GBK code page.  Force the child JSON
    # producer to emit UTF-8 so Chinese titles/content are not decoded as
    # replacement characters by the parent process.
    environment["PYTHONIOENCODING"] = "utf-8"
    command = [
        sys.executable,
        str(GETDRAFT),
        "get",
        media_id,
        "--account",
        account,
    ]
    remote = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if remote.returncode:
        print("DRAFT VERIFY BLOCKED: draft/get 读取失败", file=sys.stderr)
        if remote.stderr:
            print(remote.stderr.strip(), file=sys.stderr)
        return remote.returncode
    try:
        data = json.loads(remote.stdout)
        item = _readback_item(data)
        meta = _yaml(meta_path)
    except (json.JSONDecodeError, ValueError, OSError, ImportError) as exc:
        print(f"DRAFT VERIFY BLOCKED: 无法解析草稿回读：{exc}", file=sys.stderr)
        return 1

    local_html = html_path.read_text(encoding="utf-8", errors="replace")
    readback = analyze_readback(meta, item, _validator_passed(html_path), local_html)
    required = (
        readback["title_matches"],
        readback["author_matches"],
        readback["digest_matches"],
        readback["literal_unicode_escapes"] == 0,
        readback["replacement_characters"] == 0,
        not readback["content_has_div"],
        readback["html_validator"] == "passed",
        readback["image_count"] >= 1,
    )
    if not all(required):
        print("DRAFT VERIFY BLOCKED: 草稿回读存在不一致或不合规内容", file=sys.stderr)
        print(json.dumps(readback, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    receipt = {
        "status": "draft_created_and_verified",
        "mode": "draft",
        "target_kind": "wechat",
        "account": str(meta.get("account") or ""),
        "account_slot": int(PUBLISH_SLOT),
        "media_id": media_id,
        "thumb_media_id": str(item.get("thumb_media_id") or ""),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "html_digest": sha256_file(html_path),
        "readback": readback,
        "publish_completed": True,
        "draft_submitted": True,
        "draft_verified": True,
        "public_published": False,
        "publish_completed_reason": "草稿创建成功并通过 draft/get 回读；未调用群发接口。",
    }
    receipt = stamp_receipt(
        receipt,
        article_dir,
        receipt_kind="publish-receipt",
        account_slot=PUBLISH_SLOT,
        env_path=env_path,
        operation_id=str(attempt.get("operation_id") or "") or None,
    )
    (article_dir / "publish-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    meta["thumb_media_id"] = str(item.get("thumb_media_id") or meta.get("thumb_media_id") or "")
    meta["publish_completed"] = True
    meta["draft_submitted"] = True
    meta["draft_verified"] = True
    meta["public_published"] = False
    import yaml

    meta_path.write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")
    attempt = _verified_attempt_payload(
        attempt,
        media_id=media_id,
        thumb_media_id=str(item.get("thumb_media_id") or ""),
        verified_at=receipt["submitted_at"],
        html_digest=receipt["html_digest"],
        operation_id=receipt["operation_id"],
    )
    attempt = stamp_receipt(
        attempt,
        article_dir,
        receipt_kind="publish-attempt",
        account_slot=PUBLISH_SLOT,
        env_path=env_path,
        operation_id=str(attempt.get("operation_id") or "") or None,
    )
    attempt_path.write_text(json.dumps(attempt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"DRAFT VERIFIED: {media_id}")
    print("RECEIPT WRITTEN: publish-receipt.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
