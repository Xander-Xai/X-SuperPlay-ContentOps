#!/usr/bin/env python3
"""
微信公众号发布工具（skills/gzh-draft-publisher/scripts/publish.py）

- check-screening：校验仓库 **`.aws-article/config.yaml`** 的 **`publish_method`**（`draft` / `published` / `none`）。
- 其余子命令：token、上传、草稿、发布、一键 full 等。

**publish_method**（`config.yaml` 顶层）：
  - **`draft`**（默认）：`full` 仅 **创建草稿**（进公众号草稿箱），不调用 freepublish 发出。
  - **`published`**：`full` 只允许创建草稿；草稿必须完成回读、外部 `external_publish` 审批后，再用 `publish --article ... <media_id>` 提交公开发布。
    `full --publish` 仍接受旧参数，但会在创建草稿后安全阻断，不会直接调用 freepublish。
  - **`none`**：用户明确不填微信时写入；**`full` 直接退出**，不调任何微信接口；其它子命令（`token`、`create-draft` 等）仍须凭证，照常报错。

微信发布配置分工：
  - 仓库 **`.aws-article/config.yaml`**：`wechat_accounts`、`wechat_{i}_name`（1..N 槽位的数量与名称）
  - 仓库外凭证文件（通过 `--env` 或 `WECHAT_ENV_PATH` 指定）：`WECHAT_{i}_APPID`、`WECHAT_{i}_APPSECRET`、`WECHAT_{i}_API_BASE`
  - `WECHAT_N_API_BASE` 可空（空则使用官方 https://api.weixin.qq.com）。

在仓库根执行示例：
    python skills/gzh-draft-publisher/scripts/publish.py check-screening
    python skills/gzh-draft-publisher/scripts/publish.py --env D:/secrets/wechat.env full path/to/article-dir/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# base 仅域名；接口路径 /cgi-bin 拼在请求 URL 上
DEFAULT_API_BASE = "https://api.weixin.qq.com"
API_PATH = "/cgi-bin"
API_BASE = DEFAULT_API_BASE  # 运行时从 config 覆盖
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from account_context import ACCOUNT_ID, PUBLISH_SLOT  # noqa: E402
from article_integrity import canonical_html_digest, sha256_file  # noqa: E402
from receipt_integrity import verify as verify_receipt_integrity  # noqa: E402
from record_approval import approval_event_map  # noqa: E402
from workspace_hygiene import manifest_signature_errors  # noqa: E402
from workflow_security import (  # noqa: E402
    ensure_article_path,
    is_test_mode,
    load_json as strict_load_json,
    load_yaml as strict_load_yaml,
)


def _err(msg: str):
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def _ok(msg: str):
    print(f"[OK] {msg}")


def _info(msg: str):
    print(f"[INFO] {msg}")


def _configure_stdio() -> None:
    """Keep publisher diagnostics printable on Windows GBK consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass


# ── config.yaml（publish_method）──────────────────────────────

def _load_yaml_config(path: Path) -> dict | None:
    if not path.is_file():
        return None
    data = strict_load_yaml(path, default=None)
    if data is None:
        print(f"[ERROR] 无法解析 YAML 或发现重复键（{path}）: fail closed", file=sys.stderr)
        return None
    if data is None:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def errors_for_publish_method(data: dict) -> list[str]:
    """config.yaml 顶层的 publish_method：缺省视为 draft；有值则须为 draft | published | none。"""
    raw = data.get("publish_method")
    if raw is None:
        return []
    s = str(raw).strip()
    if not s:
        return []
    pm = s.lower()
    if pm in ("draft", "published", "none"):
        return []
    return [f"publish_method 非法: {raw!r}，须为 draft、published 或 none"]


def cmd_check_screening(config_path: Path) -> int:
    """校验仓库 config.yaml 中的 publish_method（子命令名沿用 check-screening）。"""
    data = _load_yaml_config(config_path)
    if data is None:
        print(f"[ERROR] 未找到文件: {config_path.resolve()}", file=sys.stderr)
        return 1
    errs = errors_for_publish_method(data)
    if errs:
        print("[ERROR] config.yaml 中 publish_method 校验未通过：", file=sys.stderr)
        for line in errs:
            print(f"   - {line}", file=sys.stderr)
        return 1
    raw = data.get("publish_method")
    if raw is None or not str(raw).strip():
        print("[OK] publish_method 未设置（将按默认 draft：仅创建公众号草稿，不自动发布）")
    else:
        pm = str(raw).strip().lower()
        print(f"[OK] publish_method={pm} 合法")
        if pm == "draft":
            print("[INFO] draft：`full` 默认只进草稿箱；若要发出请改 published 或执行 full --publish")
        elif pm == "published":
            print(
                "[INFO] published：`full` 只创建草稿；完成回读和 external_publish 审批后，必须单独运行 publish --article。"
            )
        elif pm == "none":
            print(
                "[INFO] none：`full` 将不调微信接口；其它子命令（token、create-draft 等）仍需要凭证"
            )
    return 0


def load_repo_config(config_path: Path | None = None) -> dict:
    """读取仓库 .aws-article/config.yaml；缺失或无效返回 {}。"""
    # Resolve workflow-owned config from the script location, not cwd.
    p = config_path if config_path is not None else PROJECT_ROOT / ".aws-article/config.yaml"
    data = _load_yaml_config(p)
    if data is None or not isinstance(data, dict):
        return {}
    return data


def _parse_wechat_accounts_cfg(cfg: dict) -> int:
    raw = cfg.get("wechat_accounts")
    if raw is None or isinstance(raw, bool):
        return 0
    if isinstance(raw, int):
        return raw if raw >= 1 else 0
    s = str(raw).strip()
    if not s:
        return 0
    try:
        n = int(s)
    except ValueError:
        return 0
    return n if n >= 1 else 0


# ── access_token ────────────────────────────────────────────

def get_access_token(appid: str, appsecret: str) -> str:
    """获取 access_token（有效期 2 小时）。网络类失败会自动重试 1 次。"""
    url = (
        f"{API_BASE}{API_PATH}/token?"
        f"grant_type=client_credential&appid={appid}&secret={appsecret}"
    )
    data = _api_get(url)
    if "access_token" not in data:
        errcode = data.get("errcode")
        hint = ""
        if errcode in (40013, 40125, 40164, 89004):
            hint = "（多为 AppID/AppSecret 错误或 IP 未加白名单，请检查 aws.env 对应槽位）"
        elif errcode == 40001:
            hint = "（access_token 无效类错误，请核对凭证）"
        _err(f"获取 access_token 失败: {data}{hint}")
    return data["access_token"]


# ── 图片压缩 ────────────────────────────────────────────────

def _compress_image(image_path: str, max_bytes: int, for_content: bool = False) -> str:
    """压缩图片到指定大小以内，返回压缩后的路径（可能是临时文件）。

    封面/永久素材：max 10MB
    正文图片：max 1MB
    """
    path = Path(image_path)
    size = path.stat().st_size
    if size <= max_bytes:
        return image_path

    _info(f"图片 {path.name} ({size/1024:.0f}KB) 超过限制 ({max_bytes/1024:.0f}KB)，压缩中...")

    try:
        from PIL import Image
    except ImportError:
        _info("未安装 Pillow，跳过压缩（pip install Pillow）")
        return image_path

    img = Image.open(path)
    if img.mode == "RGBA":
        img = img.convert("RGB")

    compressed_path = path.parent / f"{path.stem}_compressed.jpg"

    quality = 85
    while quality >= 20:
        img.save(compressed_path, "JPEG", quality=quality, optimize=True)
        if compressed_path.stat().st_size <= max_bytes:
            new_size = compressed_path.stat().st_size
            _ok(f"压缩完成: {new_size/1024:.0f}KB (quality={quality})")
            return str(compressed_path)
        quality -= 10

    max_dim = 1920 if not for_content else 1080
    img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    img.save(compressed_path, "JPEG", quality=60, optimize=True)
    new_size = compressed_path.stat().st_size
    _ok(f"压缩+缩放完成: {new_size/1024:.0f}KB")
    return str(compressed_path)


THUMB_MAX_BYTES = 10 * 1024 * 1024    # 封面 10MB
CONTENT_MAX_BYTES = 1 * 1024 * 1024   # 正文 1MB


# ── 上传图片 ────────────────────────────────────────────────

def upload_thumb(token: str, image_path: str) -> dict:
    """上传封面图为永久素材，返回 {media_id, url}。自动压缩到 10MB 以内。"""
    image_path = _compress_image(image_path, THUMB_MAX_BYTES)
    url = f"{API_BASE}{API_PATH}/material/add_material?access_token={token}&type=image"
    data = _upload_file(url, image_path, field_name="media")
    if "media_id" not in data:
        _err(f"上传封面图失败: {data}")
    return {"media_id": data["media_id"], "url": data.get("url", "")}


def upload_content_image(token: str, image_path: str) -> str:
    """上传正文内图片，返回可在正文中使用的 URL。自动压缩到 1MB 以内。"""
    image_path = _compress_image(image_path, CONTENT_MAX_BYTES, for_content=True)
    url = f"{API_BASE}{API_PATH}/media/uploadimg?access_token={token}"
    data = _upload_file(url, image_path, field_name="media")
    if "url" not in data:
        _err(f"上传正文图片失败: {data}")
    return data["url"]


# ── 草稿 ────────────────────────────────────────────────────

def create_draft(token: str, articles: list[dict]) -> str:
    """创建草稿，返回 media_id。

    articles 中每个元素包含：
        title, content, thumb_media_id,
        author(可选), digest(可选),
        content_source_url(可选),
        need_open_comment(可选, 0/1),
        only_fans_can_comment(可选, 0/1)
    """
    _validate_article_metadata(articles)
    url = f"{API_BASE}{API_PATH}/draft/add?access_token={token}"
    body = {"articles": articles}
    data = _api_post_json(url, body)
    if "media_id" not in data:
        _err(f"创建草稿失败: {data}")
    return data["media_id"]


def _validate_article_metadata(articles: list[dict]) -> None:
    """Reject double-escaped Unicode before it reaches the WeChat draft box.

    A value such as ``\\u667a\\u5e93`` is not Chinese text; it is a literal
    backslash-u sequence produced by serializing an already serialized JSON
    string.  WeChat stores that value verbatim, so fail early with a useful
    message instead of creating a visibly broken draft.  The body is not
    rejected here because a code sample may legitimately contain JSON escape
    sequences; the title/author/digest fields are unambiguous metadata.
    """
    for index, article in enumerate(articles, start=1):
        for field in ("title", "author", "digest"):
            value = str(article.get(field) or "")
            if re.search(r"\\u[0-9a-fA-F]{4}", value):
                _err(
                    f"第 {index} 篇 {field} 检测到字面量 \\uXXXX 转义（例如 \\u667a），"
                    "这通常表示文本被 JSON 双重序列化。请先还原为实际中文，再提交草稿。"
                )


# ── 发布 ────────────────────────────────────────────────────

def publish_draft(token: str, media_id: str) -> str:
    """发布草稿（异步），返回 publish_id。"""
    url = f"{API_BASE}{API_PATH}/freepublish/submit?access_token={token}"
    data = _api_post_json(url, {"media_id": media_id})
    if "publish_id" not in data:
        _err(f"提交发布失败: {data}")
    return data["publish_id"]


def get_publish_status(token: str, publish_id: str) -> dict:
    """查询发布状态。

    返回 publish_status:
        0=成功, 1=发布中, 2=原创失败, 3=常规失败,
        4=审核不通过, 5=已删除, 6=已封禁
    """
    url = f"{API_BASE}{API_PATH}/freepublish/get?access_token={token}"
    return _api_post_json(url, {"publish_id": publish_id})


# ── 往期文章 ────────────────────────────────────────────────

def get_published_articles(token: str, offset: int = 0, count: int = 10,
                           no_content: bool = True) -> dict:
    """获取已发布的文章列表。

    Args:
        offset: 偏移位置，0 = 从最新开始
        count: 返回数量，1-20
        no_content: True = 不返回正文（省流量）
    """
    url = f"{API_BASE}{API_PATH}/freepublish/batchget?access_token={token}"
    body = {"offset": offset, "count": count, "no_content": 1 if no_content else 0}
    return _api_post_json(url, body)


def list_recent_articles(token: str, count: int = 10) -> list[dict]:
    """获取最近发布的文章，返回 [{title, url, update_time}]。"""
    result = get_published_articles(token, offset=0, count=count)
    articles = []
    for item in result.get("item", []):
        content = item.get("content", {})
        for art in content.get("news_item", []):
            articles.append({
                "title": art.get("title", ""),
                "url": art.get("url", ""),
                "digest": art.get("digest", ""),
                "update_time": item.get("update_time", ""),
            })
    return articles


# ── 全流程 ──────────────────────────────────────────────────

def _article_publish_guard(article_dir: Path) -> list[str]:
    """Require a routed WeChat article at the pre-submit boundary.

    ``draft_submitted`` is the post-publish/readback gate.  A draft-only
    workflow may intentionally re-submit an already verified article (for
    example after a platform-side draft was deleted or when the operator asks
    for a fresh copy), so ``draft_submitted`` is also accepted when
    ``publish_method`` is ``draft``.  Public publishing remains restricted to
    the normal ``final_reviewed`` boundary.
    """

    errors: list[str] = []
    state_path = article_dir / "matrix-state.json"
    meta_path = article_dir / "article.yaml"
    route_path = article_dir / "routing.yaml"
    if not state_path.is_file():
        errors.append("缺少 matrix-state.json；不能把任意 HTML 当作公众号草稿")
    if not meta_path.is_file():
        errors.append("缺少 article.yaml；不能确认公众号账号")
    if not route_path.is_file():
        errors.append("缺少 routing.yaml；必须先完成选题路由和账号路由")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        state = {}
        errors.append("matrix-state.json 无法解析")
    stage = str(state.get("current_stage") or state.get("status") or "none").strip().lower()
    try:
        import yaml

        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    except (ImportError, OSError, ValueError):
        meta = {}
    if not isinstance(meta, dict) or str(meta.get("content_medium", "")).strip().lower() != "wechat_article":
        errors.append("article.yaml 的 content_medium 必须是 wechat_article")
    # The split target is intentionally single-account.  Publishing must bind
    # the article, identity document and config slot before any token is read.
    try:
        from account_context import ACCOUNT_ID, PUBLISH_SLOT
    except Exception:
        ACCOUNT_ID, PUBLISH_SLOT = "", None
    if isinstance(meta, dict) and ACCOUNT_ID:
        article_account = str(meta.get("account") or "").strip().lower()
        if article_account != ACCOUNT_ID:
            errors.append(f"article.yaml 的 account 必须是 {ACCOUNT_ID}，当前是 {article_account or '空值'}")
    cfg = load_repo_config()
    publish_method = str(cfg.get("publish_method") or "draft").strip().lower() or "draft"
    if stage != "final_reviewed" and not (stage == "draft_submitted" and publish_method == "draft"):
        errors.append(
            f"发布前工作区必须停在 final_reviewed（或 draft 模式下重提 draft_submitted），当前是 {stage or 'none'}"
        )
    raw_slot = cfg.get("wechat_publish_slot")
    try:
        config_slot = int(raw_slot)
    except (TypeError, ValueError):
        config_slot = None
        errors.append(".aws-article/config.yaml 的 wechat_publish_slot 必须是整数")
    if PUBLISH_SLOT is not None and config_slot != PUBLISH_SLOT:
        errors.append(
            f"config.yaml 的 wechat_publish_slot={config_slot!r} 与 workflow-identity slot={PUBLISH_SLOT} 不一致"
        )
    if config_slot is not None:
        account_count = _parse_wechat_accounts_cfg(cfg)
        if config_slot < 1 or config_slot > account_count:
            errors.append(
                f"wechat_publish_slot={config_slot} 超出 wechat_accounts={account_count}；"
                "发布账号必须在配置声明的槽位范围内"
            )
    return errors


def _configure_article_slot(article_dir: Path) -> list[str]:
    """Bind credential resolution to the article's fixed workflow slot."""

    global _draft_wechat_slot
    errors: list[str] = []
    try:
        article_dir = ensure_article_path(article_dir, allow_test_fixture=False)
    except ValueError as exc:
        return [str(exc)]
    cfg = load_repo_config()
    try:
        slot = int(cfg.get("wechat_publish_slot"))
    except (TypeError, ValueError):
        return ["无法为文章解析 wechat_publish_slot；禁止使用未绑定槽位的凭证"]
    account_count = _parse_wechat_accounts_cfg(cfg)
    if slot < 1 or slot > account_count:
        errors.append(
            f"文章发布槽位 {slot} 不在 wechat_accounts={account_count} 范围内"
        )
    try:
        from account_context import PUBLISH_SLOT
        if slot != int(PUBLISH_SLOT):
            errors.append(
                f"文章发布槽位 {slot} 与 workflow-identity 的固定槽位 {PUBLISH_SLOT} 不一致"
            )
    except Exception as exc:
        errors.append(f"无法加载 workflow-identity 的发布槽位：{exc}")
    if errors:
        return errors
    _draft_wechat_slot = slot
    return []


def _article_attempt_guard(article_dir: Path, media_id: str) -> list[str]:
    """Require a signed, read-back attempt created for this exact article.

    A media_id is an opaque remote identifier; matching that string and a
    slot is not causal binding.  The attempt must be the current article's
    signed post-readback transaction and its content digest must still match.
    """

    errors: list[str] = []
    try:
        article_dir = ensure_article_path(article_dir, allow_test_fixture=False)
    except ValueError as exc:
        return [str(exc)]
    path = article_dir / "publish-attempt.json"
    if not path.is_file():
        return ["缺少 publish-attempt.json；不能凭裸 media_id 发布"]
    try:
        attempt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["publish-attempt.json 无法解析；不能凭裸 media_id 发布"]
    if not isinstance(attempt, dict):
        return ["publish-attempt.json 必须是对象"]
    if str(attempt.get("media_id") or "").strip() != str(media_id).strip():
        errors.append("media_id 与当前文章的 publish-attempt.json 不一致")
    if str(attempt.get("status") or "").strip() != "passed":
        errors.append("publish-attempt.json 必须是 draft/get 回读后的 status=passed")
    errors.extend(
        f"publish-attempt 完整性：{error}"
        for error in verify_receipt_integrity(
            attempt,
            article_dir,
            receipt_kind="publish-attempt",
            account_slot=_draft_wechat_slot,
            env_path=_resolve_env_path() if _resolve_env_path().is_file() else None,
        )
    )
    if str(attempt.get("mode") or "").strip().lower() != "draft":
        errors.append("publish-attempt.json 的 mode 必须是 draft")
    if str(attempt.get("draft_status") or "").strip() != "draft_created_and_verified":
        errors.append("publish-attempt.json 缺少 draft_created_and_verified 回读状态")
    html_digest = str(attempt.get("html_digest") or "").strip().lower()
    current_html_digest = sha256_file(article_dir / "article.html") if (article_dir / "article.html").is_file() else ""
    if not html_digest or html_digest != current_html_digest:
        errors.append("publish-attempt.json 的 html_digest 与当前 article.html 不一致")
    if not str(attempt.get("thumb_media_id") or "").strip():
        errors.append("publish-attempt.json 缺少已回读确认的 thumb_media_id")
    if _draft_wechat_slot is not None:
        try:
            if int(attempt.get("account_slot")) != int(_draft_wechat_slot):
                errors.append("publish-attempt.json 的 account_slot 与当前文章槽位不一致")
        except (TypeError, ValueError):
            errors.append("publish-attempt.json 缺少数值 account_slot")
    return errors


def _external_publish_guard(article_dir: Path, media_id: str) -> list[str]:
    """Require an external, current-scope human approval before freepublish."""

    if is_test_mode():
        return ["测试模式禁止调用公开发布 API"]
    try:
        article_dir = ensure_article_path(article_dir, allow_test_fixture=False)
    except ValueError as exc:
        return [str(exc)]
    attempt_path = article_dir / "publish-attempt.json"
    attempt = strict_load_json(attempt_path, default={})
    if not isinstance(attempt, dict) or str(attempt.get("media_id") or "").strip() != str(media_id).strip():
        return ["external_publish 审批必须绑定当前 publish-attempt.json 与 media_id"]
    events = approval_event_map(article_dir).get("external_publish", [])
    current: list[dict] = []
    for event in events:
        if str(event.get("reviewer_type") or "").strip().lower() != "human":
            continue
        if not str(event.get("reviewer") or "").strip() or not str(event.get("signed_by") or "").strip():
            continue
        scopes = event.get("scope")
        hashes = event.get("scope_sha256")
        if not isinstance(scopes, list) or not isinstance(hashes, dict):
            continue
        scope_names = {str(item).strip().replace("\\", "/") for item in scopes if str(item).strip()}
        required = {"article.md", "article.html", "publish-attempt.json"}
        if not required.issubset(scope_names):
            continue
        valid = True
        for name in scope_names:
            candidate = (article_dir / name).resolve()
            try:
                candidate.relative_to(article_dir.resolve())
            except ValueError:
                valid = False
                break
            if not candidate.is_file() or str(hashes.get(name) or "").lower() != sha256_file(candidate):
                valid = False
                break
        if valid:
            current.append(event)
    if not current:
        return ["缺少绑定当前 article.md/article.html/publish-attempt.json 的 external_publish human approval"]
    # For high-risk external actions, a local append-only event is not an
    # independent trust root.  Require the externally configured signature
    # chain whenever the broker is actually asked to publish.
    policy_path = os.environ.get("APPROVAL_SIGNATURE_POLICY_PATH", "").strip()
    key_path = os.environ.get("APPROVAL_SIGNATURE_KEY_PATH", "").strip()
    if not policy_path or not key_path:
        return ["external_publish 必须提供外部 APPROVAL_SIGNATURE_POLICY_PATH/APPROVAL_SIGNATURE_KEY_PATH"]
    try:
        from sign_approval_events import verify_events

        signature_errors = verify_events(article_dir, policy_path, key_path)
    except Exception as exc:  # noqa: BLE001
        signature_errors = [str(exc)]
    if signature_errors:
        return [f"external_publish approval-signature: {error}" for error in signature_errors]
    manifest_errors = manifest_signature_errors(PROJECT_ROOT, required=True)
    if manifest_errors:
        return [f"external_publish manifest-integrity: {error}" for error in manifest_errors]
    return []


def _asset_upload_guard(article_dir: Path, image_path: str) -> list[str]:
    """Bind raw uploads to an article, approved asset ledger and safe mode."""

    errors: list[str] = []
    if is_test_mode():
        return ["测试模式禁止调用外部素材上传 API"]
    try:
        article_dir = ensure_article_path(article_dir, allow_test_fixture=False)
    except ValueError as exc:
        return [str(exc)]
    try:
        raw_image = Path(image_path).expanduser()
        if not raw_image.is_absolute():
            article_candidate = (article_dir / raw_image).resolve()
            image = article_candidate if article_candidate.is_file() else raw_image.resolve()
        else:
            image = raw_image.resolve()
        image.relative_to(article_dir.resolve())
    except ValueError:
        return ["上传素材必须位于当前文章目录内；禁止读取任意本机路径"]
    if not image.is_file():
        errors.append("上传素材文件不存在")
    ledger = strict_load_json(article_dir / "image-sources.json", default={})
    assets = ledger.get("assets") if isinstance(ledger, dict) else None
    if not isinstance(assets, list):
        errors.append("缺少 image-sources.json assets 资产账本")
    else:
        rel = image.relative_to(article_dir.resolve()).as_posix()
        rows = [item for item in assets if isinstance(item, dict) and str(item.get("path") or item.get("asset") or "").replace("\\", "/") == rel]
        if not rows:
            errors.append(f"素材 {rel} 未登记在 image-sources.json")
        elif not any(bool(row.get("reuse_approved")) or str(row.get("origin") or "").strip().lower() in {"generated", "user-provided"} for row in rows):
            errors.append(f"素材 {rel} 缺少 reuse_approved 或受控 origin")
    return errors


def _run_publish_gate(article_dir: Path) -> list[str]:
    """Re-run the final-review gate before any upload or draft creation."""

    env_path = _resolve_env_path()
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "workflow_gate.py"),
        "--article",
        str(article_dir),
        "--stage",
        "final_reviewed",
        "--all",
    ]
    if env_path.is_file():
        command.extend(["--env", str(env_path)])
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 0:
        return []
    detail = (result.stdout + result.stderr).strip().splitlines()
    return ["final_reviewed 门禁复核失败：" + (detail[-1] if detail else "无输出")]

def full_publish(
    token: str,
    article_dir: str,
    do_publish: bool = False,
    account_slot: int | None = None,
):
    """一键全流程：读取文章目录 → 上传图片 → 创建草稿 → 可选发布。

    文章目录结构：
        article_dir/
        ├── article.yaml    文章元信息（title, author, digest 等）
        ├── article.html    排版后的正文 HTML
        ├── cover.jpg       封面图
        └── imgs/           正文内图片（可选）
            ├── 01-xxx.png
            └── 02-xxx.jpg
    """
    article_dir = Path(article_dir)

    guard_errors = _article_publish_guard(article_dir)
    guard_errors.extend(_run_publish_gate(article_dir))
    if guard_errors:
        _err("发布前门禁未通过：" + "；".join(guard_errors))

    meta_path = article_dir / "article.yaml"
    if not meta_path.exists():
        _err(f"未找到 {meta_path}")

    import yaml  # lazy import，仅全流程需要
    with open(meta_path, encoding="utf-8") as f:
        meta = yaml.safe_load(f)

    cfg = load_repo_config()
    author = (meta.get("author") or "").strip() or str(
        cfg.get("default_author") or ""
    ).strip()

    content_path = article_dir / "article.html"
    if not content_path.exists():
        _err(f"未找到 {content_path}")
    content = content_path.read_text(encoding="utf-8")

    # 上传封面（优先 article_dir/cover.*，fallback imgs/cover.* 和 imgs/*-cover.*）
    _cover_names = ["cover.jpg", "cover.png", "cover.jpeg", "cover.webp"]
    cover_path = _find_file(article_dir, _cover_names)
    if not cover_path:
        _imgs = article_dir / "imgs"
        if _imgs.is_dir():
            cover_path = _find_file(_imgs, _cover_names)
            if not cover_path:
                for _sfx in (".jpg", ".png", ".jpeg", ".webp"):
                    _cands = sorted(_imgs.glob(f"*-cover{_sfx}"))
                    if _cands:
                        cover_path = _cands[0]
                        break
    if not cover_path:
        _err("未找到封面图（cover.jpg/png/jpeg/webp）；支持 article_dir/ 或 imgs/ 下")
    _info(f"上传封面图: {cover_path}")
    thumb = upload_thumb(token, str(cover_path))
    _ok(f"封面图上传成功: media_id={thumb['media_id']}")

    # 上传正文图片并替换路径（仅上传 HTML 中实际引用的 imgs/ 文件）
    imgs_dir = article_dir / "imgs"
    if imgs_dir.exists():
        for fname in _content_image_refs_flat(content):
            img_file = imgs_dir / fname
            if not img_file.is_file():
                _err(f"正文引用了不存在的图片: imgs/{fname}")
            _info(f"上传正文图片: imgs/{fname}")
            img_url = upload_content_image(token, str(img_file))
            # Keep nested paths intact (for example imgs/formulas/f-001.png)
            # so a formula asset cannot be uploaded successfully while the
            # article HTML still points at a local path.
            content = content.replace(f"imgs/{fname}", img_url)
            _ok(f"  → {img_url}")

    if "tempkey=" in content or "tempkey%3D" in content:
        _err(
            "正文 HTML 仍含 tempkey 预览链（常见于 getdraft list-fields 返回的 url）。"
            "微信 draft/add 常因此返回 45166 invalid content。"
            "请改用已群发文章的永久链接（后台对该文「复制链接」），或从正文去掉相关超链后重试。"
        )

    # 构建草稿（author 优先 article.yaml，为空时用 config.yaml default_author）
    article = {
        "title": meta.get("title", ""),
        "author": author,
        "digest": meta.get("digest", ""),
        "content": content,
        "thumb_media_id": thumb["media_id"],
        "content_source_url": meta.get("content_source_url", ""),
        "need_open_comment": meta.get("need_open_comment", 0),
        "only_fans_can_comment": meta.get("only_fans_can_comment", 0),
    }
    _info("创建草稿...")
    media_id = create_draft(token, [article])
    _ok(f"草稿创建成功: media_id={media_id}")
    attempt = {
        "schema_version": 1,
        "status": "draft_created_unverified",
        "mode": "published" if do_publish else "draft",
        "account_slot": account_slot,
        "media_id": media_id,
        "thumb_media_id": thumb["media_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "html_digest": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "draft_status": "draft_created_unverified",
    }
    from receipt_integrity import stamp as stamp_receipt
    attempt = stamp_receipt(
        attempt,
        article_dir,
        receipt_kind="publish-attempt",
        account_slot=account_slot,
        env_path=_resolve_env_path() if _resolve_env_path().is_file() else None,
    )
    (article_dir / "publish-attempt.json").write_text(
        json.dumps(attempt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"DRAFT_MEDIA_ID={media_id}")

    # 公开发布必须是独立的第二阶段：创建草稿本身没有远端回读，也没有
    # external_publish 人工批准，所以一键路径只能安全停止在草稿箱。
    if do_publish:
        _err(
            "已创建草稿但拒绝一键公开发布：请先运行 verify_draft_submission.py 完成 draft/get 回读，"
            "由外部人审记录 external_publish 审批，再使用 publish --article <文章目录> <media_id>。"
        )
    else:
        _info("草稿已创建，未发布。如需发布：")
        print(
            "  python skills/gzh-draft-publisher/scripts/publish.py publish "
            f"{media_id}"
        )

    return media_id


def _poll_publish_status(token: str, publish_id: str, max_wait: int = 60):
    """轮询发布状态，最多等待 max_wait 秒。"""
    status_map = {
        0: "[OK] 发布成功",
        1: "[INFO] 发布中",
        2: "[ERROR] 原创失败",
        3: "[ERROR] 常规失败",
        4: "[ERROR] 平台审核不通过",
        5: "[ERROR] 已删除",
        6: "[ERROR] 已封禁",
    }
    start = time.time()
    while time.time() - start < max_wait:
        result = get_publish_status(token, publish_id)
        status = result.get("publish_status", -1)
        print(f"  状态: {status_map.get(status, f'未知({status})')}")
        if status != 1:
            return result
        time.sleep(3)
    _info(f"已等待 {max_wait}s，发布仍在进行中。可稍后查询：")
    print(
        "  python skills/gzh-draft-publisher/scripts/publish.py status "
        f"{publish_id}"
    )


# ── HTTP 工具 ───────────────────────────────────────────────

def _is_transient_network_error(e: BaseException) -> bool:
    if isinstance(e, urllib.error.URLError):
        return True
    if isinstance(e, TimeoutError):
        return True
    if isinstance(e, urllib.error.HTTPError) and e.code >= 500:
        return True
    return False


def _api_get(url: str) -> dict:
    last: BaseException | None = None
    t_req, _ = _wechat_http_timeouts()
    for attempt in range(2):
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=t_req) as resp:
                return json.loads(resp.read())
        except Exception as e:
            last = e
            if attempt == 0 and _is_transient_network_error(e):
                _info("【网络】请求失败，1 秒后重试一次…")
                time.sleep(1)
                continue
            raise
    raise last  # pragma: no cover


def _api_post_json(url: str, body: dict) -> dict:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    last: BaseException | None = None
    t_req, _ = _wechat_http_timeouts()
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            with urllib.request.urlopen(req, timeout=t_req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last = e
            if attempt == 0 and _is_transient_network_error(e):
                _info("【网络】请求失败，1 秒后重试一次…")
                time.sleep(1)
                continue
            raise
    raise last  # pragma: no cover


def _upload_file(url: str, file_path: str, field_name: str = "media") -> dict:
    """multipart/form-data 文件上传（纯标准库实现）。"""
    boundary = f"----WechatPublish{int(time.time() * 1000)}"
    file_path = Path(file_path)
    if not file_path.exists():
        _err(f"文件不存在: {file_path}")

    mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    file_data = file_path.read_bytes()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; '
        f'filename="{file_path.name}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    last: BaseException | None = None
    _, t_up = _wechat_http_timeouts()
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            with urllib.request.urlopen(req, timeout=t_up) as resp:
                return json.loads(resp.read())
        except Exception as e:
            last = e
            if attempt == 0 and _is_transient_network_error(e):
                _info("【网络】上传失败，1 秒后重试一次…")
                time.sleep(1)
                continue
            raise
    raise last  # pragma: no cover


def _find_file(directory: Path, candidates: list[str]) -> Path | None:
    for name in candidates:
        p = directory / name
        if p.exists():
            return p
    return None


def _content_image_refs_flat(html: str) -> list[str]:
    """解析正文引用的 imgs/ 相对路径并保持子目录。

    公式 PNG 位于 ``imgs/formulas``，不能再把所有素材压平成文件名。
    """
    seen: set[str] = set()
    out: list[str] = []
    for m in re.finditer(r'imgs/([^"\'<>\s]+)', html, flags=re.IGNORECASE):
        name = m.group(1).strip()
        if not name or "\\" in name or ".." in name:
            continue
        low = name.lower()
        if not low.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            continue
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


# ── 仓库外凭证文件 ───────────────────────────────────────────

_cli_env_path: str | None = None


def _resolve_env_path() -> Path:
    override = (_cli_env_path or os.environ.get("WECHAT_ENV_PATH", "")).strip()
    # Credentials are intentionally outside the repository.  Do not fall back
    # to ROOT/aws.env or ROOT/.env: a missing explicit path must fail closed.
    return Path(override) if override else PROJECT_ROOT / "__external_env_required__"


def _parse_dotenv(content: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key] = val
    return out


def _load_env_map() -> dict[str, str]:
    path = _resolve_env_path()
    if not path.is_file():
        return {}
    try:
        return _parse_dotenv(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


# 微信 HTTP 超时（秒）：默认较原 30/60 放宽，慢代理或大图上传统计更稳
_DEFAULT_WECHAT_REQUEST_TIMEOUT = 60
_DEFAULT_WECHAT_UPLOAD_TIMEOUT = 120


def _wechat_http_timeouts() -> tuple[int, int]:
    """从仓库根 env 文件读取 (普通请求超时, 文件上传超时)，单位秒。"""
    env = _load_env_map()
    req = _DEFAULT_WECHAT_REQUEST_TIMEOUT
    up = _DEFAULT_WECHAT_UPLOAD_TIMEOUT
    raw_req = (env.get("WECHAT_REQUEST_TIMEOUT") or "").strip()
    if raw_req:
        try:
            req = max(5, int(raw_req))
        except ValueError:
            pass
    raw_up = (env.get("WECHAT_UPLOAD_TIMEOUT") or "").strip()
    if raw_up:
        try:
            up = max(10, int(raw_up))
        except ValueError:
            pass
    return req, up


def _wechat_slot_keys(i: int) -> tuple[str, str, str]:
    return (
        f"WECHAT_{i}_APPID",
        f"WECHAT_{i}_APPSECRET",
        f"WECHAT_{i}_API_BASE",
    )


def wechat_slot(cfg: dict, env: dict[str, str], i: int) -> dict:
    ak, sk, bk = _wechat_slot_keys(i)
    return {
        "slot": i,
        "name": str(cfg.get(f"wechat_{i}_name") or "").strip(),
        "appid": (env.get(ak) or "").strip(),
        "appsecret": (env.get(sk) or "").strip(),
        "api_base": (env.get(bk) or "").strip(),
    }


def missing_wechat_slot_fields(slot: dict) -> list[str]:
    """用于完整性提示：APPID、APPSECRET；API_BASE 可空。"""
    miss: list[str] = []
    if not slot["appid"]:
        miss.append("APPID")
    if not slot["appsecret"]:
        miss.append("APPSECRET")
    return miss


def list_wechat_slots(cfg: dict, env: dict[str, str]) -> list[dict]:
    n = _parse_wechat_accounts_cfg(cfg)
    return [wechat_slot(cfg, env, i) for i in range(1, n + 1)]


def selected_wechat_slots(cfg: dict, env: dict[str, str]) -> list[dict]:
    """Return the target slot for scoped checks, or all slots when unspecified."""
    slots = list_wechat_slots(cfg, env)
    if not _cli_account:
        return slots
    raw = str(_cli_account).strip()
    if raw.isdigit():
        index = int(raw)
        return [slot for slot in slots if slot["slot"] == index]
    return [slot for slot in slots if slot["name"] and (raw == slot["name"] or raw in slot["name"])]


def cmd_check_wechat_env() -> int:
    """按 config.yaml 槽位检查 aws.env 中 WECHAT_N_APPID/APPSECRET 是否齐全。"""
    cfg = load_repo_config()
    env = _load_env_map()
    env_path = _resolve_env_path()
    if not env and not env_path.is_file():
        print("[ERROR] 未找到显式外部凭证文件（请使用 --env 或 WECHAT_ENV_PATH）", file=sys.stderr)
        return 1
    n = _parse_wechat_accounts_cfg(cfg)
    if n < 1:
        print("[ERROR] config.yaml 中 wechat_accounts 无效或未设置（须为 ≥1 的整数）", file=sys.stderr)
        return 1
    bad = False
    slots = selected_wechat_slots(cfg, env)
    if _cli_account and not slots:
        print(f"[ERROR] 未找到目标微信槽位：{_cli_account}", file=sys.stderr)
        return 1
    for slot in slots:
        miss = missing_wechat_slot_fields(slot)
        if miss:
            bad = True
            keys = ", ".join(f"WECHAT_{slot['slot']}_{m}" for m in miss)
            print(
                f"[ERROR] 第 {slot['slot']} 个微信账号未填完整：缺少 {', '.join(miss)}（{keys}）",
                file=sys.stderr,
            )
        else:
            _ok(
                f"槽位 {slot['slot']}: {slot['name'] or '(未命名)'} — APPID/SECRET 已填"
            )
    return 1 if bad else 0


# full 流程从 config.yaml wechat_publish_slot 写入的槽位（1..N），供 _get_credentials 使用
_draft_wechat_slot: int | None = None


def _resolve_slot_index(
    cfg: dict,
    env: dict[str, str],
    account_alias: str | None,
    preferred_slot: int | None,
) -> int:
    n = _parse_wechat_accounts_cfg(cfg)
    if n < 1:
        _err(
            "config.yaml 中 wechat_accounts 无效或未设置。\n"
            "请设置 wechat_accounts=1，并在 config.yaml 填写 wechat_1_name。"
        )
    # 命令行 --account 优先于 config.yaml 的 wechat_publish_slot
    if account_alias:
        s = str(account_alias).strip()
        if s.isdigit():
            si = int(s)
            if 1 <= si <= n:
                if preferred_slot is not None and si != preferred_slot:
                    _err(
                        f"--account={si} 与当前文章固定发布槽位 {preferred_slot} 不一致；"
                        "禁止跨账号发布"
                    )
                _info(f"使用 --account 指定槽位 {si}")
                return si
            _err(f"--account 槽位序号须在 1..{n} 之间")
        for i in range(1, n + 1):
            sl = wechat_slot(cfg, env, i)
            nm = sl["name"]
            if nm and (s == nm or s in nm):
                if preferred_slot is not None and i != preferred_slot:
                    _err(
                        f"--account={s} 匹配槽位 {i}，与当前文章固定发布槽位 {preferred_slot} 不一致；"
                        "禁止跨账号发布"
                    )
                _info(f"使用名称匹配的槽位 {i}: {nm}")
                return i
        _err(
            f"未找到账号 '{account_alias}'。"
            f"请使用槽位序号 1..{n} 或 config.yaml 中 wechat_N_name 的展示名。"
        )
    if preferred_slot is not None:
        if 1 <= preferred_slot <= n:
            _info(f"使用 config.yaml 中的 wechat_publish_slot={preferred_slot}")
            return preferred_slot
        _err(
            f"config.yaml 中 wechat_publish_slot={preferred_slot} 超出范围，"
            f"当前 wechat_accounts={n}（有效 1..{n}）"
        )
    if n == 1:
        return 1
    _err(
        f"配置了 {n} 个微信槽位，请指定账号：\n"
        "  --account <1..N 或 wechat_N_name 子串>\n"
        "或在 .aws-article/config.yaml 中设置 wechat_publish_slot: <整数>"
    )


def _active_slot_dict(cfg: dict, env: dict[str, str], slot_index: int) -> dict:
    return wechat_slot(cfg, env, slot_index)


def _get_credentials(account_alias: str | None) -> tuple[str, str]:
    cfg = load_repo_config()
    env = _load_env_map()
    if not _resolve_env_path().is_file():
        _err(
            "未找到外部凭证文件。请通过 --env 或 WECHAT_ENV_PATH 指定仓库外路径，"
            "并填写对应槽位的 WECHAT_N_APPID/WECHAT_N_APPSECRET。"
        )
    slot_i = _resolve_slot_index(cfg, env, account_alias, _draft_wechat_slot)
    slot = _active_slot_dict(cfg, env, slot_i)
    if not slot["appid"] or not slot["appsecret"]:
        miss = missing_wechat_slot_fields(slot)
        _err(
            f"第 {slot_i} 个账号缺少微信凭证（需 APPID、APPSECRET）。"
            f"缺: {', '.join(miss) if miss else 'APPID/APPSECRET'}\n"
            f"请补全 WECHAT_{slot_i}_APPID / WECHAT_{slot_i}_APPSECRET"
        )
    return slot["appid"], slot["appsecret"]


# ── CLI ─────────────────────────────────────────────────────

_cli_account: str | None = None


def _slot_for_api_base(cfg: dict, env: dict[str, str]) -> int | None:
    """不抛错；无法唯一确定槽位时返回 None。CLI --account 优先于 wechat_publish_slot。"""
    n = _parse_wechat_accounts_cfg(cfg)
    if n < 1:
        return None
    if _draft_wechat_slot is not None and 1 <= _draft_wechat_slot <= n:
        return _draft_wechat_slot
    if _cli_account:
        s = str(_cli_account).strip()
        if s.isdigit():
            si = int(s)
            if 1 <= si <= n:
                return si
            return None
        for i in range(1, n + 1):
            sl = wechat_slot(cfg, env, i)
            nm = sl["name"]
            if nm and (s == nm or s in nm):
                return i
        return None
    if n == 1:
        return 1
    return None


def _normalize_api_base(raw: str) -> str:
    api_base = raw.strip().rstrip("/")
    if api_base.endswith("/cgi-bin"):
        api_base = api_base[:-8].rstrip("/")
    return api_base


def _resolve_api_base(cfg: dict, slot: dict) -> str:
    """槽位 WECHAT_N_API_BASE 优先；为空时回退 config.yaml.wechat_api_base。"""
    slot_base = (slot.get("api_base") or "").strip()
    if slot_base:
        return _normalize_api_base(slot_base)
    cfg_base = str(cfg.get("wechat_api_base") or "").strip()
    if cfg_base:
        return _normalize_api_base(cfg_base)
    return ""


def _init_api_base():
    """优先用槽位 WECHAT_N_API_BASE；为空则回退 config.yaml.wechat_api_base。"""
    global API_BASE
    API_BASE = DEFAULT_API_BASE
    cfg = load_repo_config()
    env = _load_env_map()
    if not env:
        return
    slot_i = _slot_for_api_base(cfg, env)
    if slot_i is None:
        return
    slot = _active_slot_dict(cfg, env, slot_i)
    api_base = _resolve_api_base(cfg, slot)
    if not api_base:
        return
    API_BASE = api_base
    _info(f"API 端点: {API_BASE}{API_PATH}")

def _get_token() -> str:
    if is_test_mode():
        _err("WORKFLOW_TEST_MODE=1 仅允许离线夹具；禁止读取凭证或调用微信 API")
    _init_api_base()
    appid, appsecret = _get_credentials(_cli_account)
    return get_access_token(appid, appsecret)


def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        description="微信公众号发布工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--account",
        help="微信槽位：填 1..N 或 config.yaml 中 wechat_N_name 的展示名",
    )
    parser.add_argument(
        "--env",
        help="仓库外的凭证文件路径；优先级高于 WECHAT_ENV_PATH，不会打印密钥值",
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    p_scr = sub.add_parser(
        "check-screening",
        help="校验仓库 .aws-article/config.yaml 中的 publish_method（draft / published / none）",
    )
    p_scr.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / ".aws-article/config.yaml",
        metavar="FILE",
        help="默认 .aws-article/config.yaml",
    )

    sub.add_parser("token", help="获取 access_token")

    p_thumb = sub.add_parser("upload-thumb", help="上传封面图（必须绑定当前文章与资产账本）")
    p_thumb.add_argument("image", help="图片路径")
    p_thumb.add_argument("--article", required=True, help="当前文章目录（必须在仓库内）")

    p_img = sub.add_parser("upload-content-image", help="上传正文图片（必须绑定当前文章与资产账本）")
    p_img.add_argument("image", help="图片路径")
    p_img.add_argument("--article", required=True, help="当前文章目录（必须在仓库内）")

    p_draft = sub.add_parser("create-draft", help="从 YAML 创建草稿")
    p_draft.add_argument("article_yaml", help="article.yaml 路径")

    p_pub = sub.add_parser("publish", help="发布草稿（必须绑定当前文章并重跑最终门禁）")
    p_pub.add_argument("media_id", help="草稿 media_id")
    p_pub.add_argument(
        "--article",
        required=True,
        help="当前文章目录；用于绑定 routing、final_reviewed、账号槽位和 publish-attempt",
    )

    p_status = sub.add_parser("status", help="查询发布状态")
    p_status.add_argument("publish_id", help="发布任务 publish_id")

    p_full = sub.add_parser("full", help="一键全流程")
    p_full.add_argument("article_dir", help="文章目录路径")
    p_full.add_argument("--publish", action="store_true", help="创建草稿后立即发布")

    sub.add_parser("accounts", help="列出 config.yaml 中的微信槽位与名称")
    sub.add_parser("check", help="检查发布环境（仓库外凭证与微信槽位）")
    sub.add_parser(
        "check-wechat-env",
        help="按 config.yaml 槽位检查 aws.env 的 WECHAT_N_APPID/APPSECRET 是否已填写",
    )

    p_recent = sub.add_parser("recent-articles", help="获取最近发布的文章")
    p_recent.add_argument("-n", "--count", type=int, default=5, help="数量（默认5）")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    global _cli_account, _cli_env_path, _draft_wechat_slot
    _cli_account = args.account
    _cli_env_path = args.env

    if args.command == "check-screening":
        return cmd_check_screening(args.config)

    if args.command == "accounts":
        cfg = load_repo_config()
        env = _load_env_map()
        ep = _resolve_env_path()
        if not ep.is_file():
            print("[ERROR] 未找到显式外部凭证文件（请使用 --env 或 WECHAT_ENV_PATH）")
            return 1
        n = _parse_wechat_accounts_cfg(cfg)
        if n < 1:
            print("[ERROR] config.yaml 中 wechat_accounts 无效")
            return 1
        print(f"微信槽位（共 {n} 个，名称来自 config.yaml，凭证来自 {ep.name}）：")
        for i in range(1, n + 1):
            s = wechat_slot(cfg, env, i)
            miss = missing_wechat_slot_fields(s)
            mark = " [OK]" if not miss else f" [WARN] 缺: {','.join(miss)}"
            print(f"  {i}. {s['name'] or '(未命名)'}{mark}")
        return 0

    if args.command == "check-wechat-env":
        return cmd_check_wechat_env()

    if args.command == "check":
        _run_checks()
        return 0

    if args.command == "recent-articles":
        token = _get_token()
        articles = list_recent_articles(token, count=args.count)
        if not articles:
            _info("暂无已发布文章")
        else:
            print(f"最近 {len(articles)} 篇已发布文章：\n")
            for i, art in enumerate(articles, 1):
                print(f"  {i}. {art['title']}")
                print(f"     {art['url']}")
                print()
        return 0

    if args.command == "token":
        token = _get_token()
        _ok("access_token 探测通过（令牌不会写入日志）")
        print(token)

    elif args.command == "upload-thumb":
        upload_article = Path(args.article).expanduser().resolve()
        upload_errors = _asset_upload_guard(upload_article, args.image)
        if upload_errors:
            for line in upload_errors:
                print(f"[ERROR] {line}", file=sys.stderr)
            return 1
        token = _get_token()
        result = upload_thumb(token, args.image)
        _ok(f"media_id: {result['media_id']}")
        _ok(f"url: {result['url']}")

    elif args.command == "upload-content-image":
        upload_article = Path(args.article).expanduser().resolve()
        upload_errors = _asset_upload_guard(upload_article, args.image)
        if upload_errors:
            for line in upload_errors:
                print(f"[ERROR] {line}", file=sys.stderr)
            return 1
        token = _get_token()
        url = upload_content_image(token, args.image)
        _ok(f"url: {url}")

    elif args.command == "create-draft":
        draft_article_dir = Path(args.article_yaml).expanduser().resolve().parent
        slot_errors = _configure_article_slot(draft_article_dir)
        guard_errors = slot_errors + _article_publish_guard(draft_article_dir)
        guard_errors.extend(_run_publish_gate(draft_article_dir))
        if guard_errors:
            for line in guard_errors:
                print(f"[ERROR] {line}", file=sys.stderr)
            return 1
        try:
            token = _get_token()
            import yaml

            ay = Path(args.article_yaml)
            with open(ay, encoding="utf-8") as f:
                meta = yaml.safe_load(f)
            default_author = str(load_repo_config().get("default_author") or "").strip()
            articles = meta.get("articles", [meta])
            for art in articles:
                if not (art.get("author") or "").strip():
                    art["author"] = default_author
            media_id = create_draft(token, articles)
            _ok(f"草稿 media_id: {media_id}")
        finally:
            _draft_wechat_slot = None

    elif args.command == "publish":
        article_dir = Path(args.article).expanduser().resolve()
        slot_errors = _configure_article_slot(article_dir)
        guard_errors = slot_errors + _article_publish_guard(article_dir)
        guard_errors.extend(_article_attempt_guard(article_dir, args.media_id))
        guard_errors.extend(_external_publish_guard(article_dir, args.media_id))
        guard_errors.extend(_run_publish_gate(article_dir))
        cfg = load_repo_config()
        pm = str(cfg.get("publish_method") or "draft").strip().lower() or "draft"
        if pm == "none":
            guard_errors.append("publish_method=none；当前配置禁止调用发布 API")
        if guard_errors:
            for line in guard_errors:
                print(f"[ERROR] {line}", file=sys.stderr)
            _draft_wechat_slot = None
            return 1
        try:
            token = _get_token()
            publish_id = publish_draft(token, args.media_id)
            _ok(f"publish_id: {publish_id}")
            _poll_publish_status(token, publish_id)
            attempt = strict_load_json(article_dir / "publish-attempt.json", default={})
            result = {
                "schema_version": 1,
                "status": "publish_submitted",
                "mode": "published",
                "target_kind": "wechat",
                "media_id": args.media_id,
                "publish_id": publish_id,
                "operation_id": attempt.get("operation_id") if isinstance(attempt, dict) else "",
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }
            from receipt_integrity import stamp as stamp_receipt
            result = stamp_receipt(
                result,
                article_dir,
                receipt_kind="publish-result",
                account_slot=_draft_wechat_slot,
                env_path=_resolve_env_path() if _resolve_env_path().is_file() else None,
                operation_id=str(result.get("operation_id") or "") or None,
            )
            (article_dir / "publish-result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        finally:
            _draft_wechat_slot = None

    elif args.command == "status":
        token = _get_token()
        result = get_publish_status(token, args.publish_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "full":
        ad = Path(args.article_dir)
        _draft_wechat_slot = None
        cfg = load_repo_config()
        pe = errors_for_publish_method(cfg)
        if pe:
            for line in pe:
                print(f"[ERROR] {line}", file=sys.stderr)
            return 1
        pm = str(cfg.get("publish_method") or "draft").strip().lower() or "draft"
        if pm == "none":
            if args.publish:
                _info("已忽略 --publish：config.yaml 中 publish_method 为 none。")
            _info("publish_method: none — 不调用微信 API，不执行发布或草稿上传。")
            _ok("已按配置跳过 publish.py full（可继续本地写稿/排版等）")
            return 0
        if pm not in ("draft", "published"):
            print(
                f"[ERROR] config.yaml 中 publish_method 须为 draft、published 或 none，当前: {pm!r}",
                file=sys.stderr,
            )
            return 1
        slot_errors = _configure_article_slot(ad.resolve())
        guard_errors = slot_errors + _article_publish_guard(ad.resolve())
        if guard_errors:
            for line in guard_errors:
                print(f"[ERROR] {line}", file=sys.stderr)
            return 1
        gate_errors = _run_publish_gate(ad.resolve())
        if gate_errors:
            for line in gate_errors:
                print(f"[ERROR] {line}", file=sys.stderr)
            return 1
        do_publish = bool(args.publish) or (pm == "published")
        ws = cfg.get("wechat_publish_slot")
        if ws is not None and str(ws).strip() != "":
            try:
                _draft_wechat_slot = int(ws)
            except (TypeError, ValueError):
                print(
                    "[ERROR] config.yaml 中 wechat_publish_slot 须为整数",
                    file=sys.stderr,
                )
                return 1
        try:
            token = _get_token()
            full_publish(token, args.article_dir, do_publish=do_publish, account_slot=_draft_wechat_slot)
        finally:
            _draft_wechat_slot = None

    return 0


def _run_checks():
    """检查发布环境（仓库外凭证、微信槽位与依赖等）。"""
    print("=== 发布环境检查 ===\n")
    issues: list[str] = []
    cfg = load_repo_config()
    n_cfg = _parse_wechat_accounts_cfg(cfg)

    ep = _resolve_env_path()
    if not ep.is_file():
        print("[ERROR] 未找到显式外部凭证文件（请使用 --env 或 WECHAT_ENV_PATH）")
        issues.append("通过 --env 或 WECHAT_ENV_PATH 指定仓库外凭证文件")
        env = {}
    else:
        _ok(f"环境文件找到: {ep.resolve()}")
        env = _load_env_map()
    if n_cfg < 1:
        print("[ERROR] config.yaml 中 wechat_accounts 无效")
        issues.append("在 config.yaml 中设置 wechat_accounts=1（或更多）")
    else:
        slots = selected_wechat_slots(cfg, env)
        if _cli_account and not slots:
            print(f"[ERROR] 未找到目标微信槽位：{_cli_account}")
            issues.append(f"无法解析目标微信槽位：{_cli_account}")
        for s in slots:
            i = s["slot"]
            if not s["name"]:
                print(f"  [ERROR] 槽位 {i}: config.yaml 缺少 wechat_{i}_name")
                issues.append(f"补全 config.yaml: wechat_{i}_name")
            miss = missing_wechat_slot_fields(s)
            if miss:
                print(f"  [ERROR] 槽位 {i} ({s['name'] or '未命名'}): 缺少 {', '.join(miss)}")
                keys = ", ".join(f"WECHAT_{i}_{m}" for m in miss)
                issues.append(f"补全 aws.env 槽位 {i}: {keys}")
            elif s["name"]:
                _ok(f"  槽位 {i} ({s['name']}): APPID/SECRET 已填")
            else:
                _ok(f"  槽位 {i}: APPID/SECRET 已填")

    # API 连通性：目标账号只探测目标槽位；未指定账号时探测第一个完整槽位。
    probe_i: int | None = None
    for s in selected_wechat_slots(cfg, env):
        i = s["slot"]
        if s["appid"] and s["appsecret"]:
            probe_i = i
            break
    if probe_i is not None:
        s = wechat_slot(cfg, env, probe_i)
        global API_BASE
        API_BASE = DEFAULT_API_BASE
        api_base = _resolve_api_base(cfg, s)
        if api_base:
            API_BASE = api_base
        try:
            url = (
                f"{API_BASE}{API_PATH}/token?"
                f"grant_type=client_credential&appid={s['appid']}&secret={s['appsecret']}"
            )
            data = _api_get(url)
            if "access_token" in data:
                _ok(f"API 连通正常（槽位 {probe_i}；令牌不会写入日志）")
            else:
                print(f"[ERROR] 微信接口返回: {data}")
                issues.append(
                    f"槽位 {probe_i} 凭证或白名单有误（见 errcode/errmsg），请检查 .env"
                )
        except Exception as e:
            print(f"[ERROR] API 连通失败: {e}")
            issues.append("网络异常或微信接口不可用，可稍后重试")

    try:
        import yaml
        _ok("PyYAML 已安装")
    except ImportError:
        print("[ERROR] PyYAML 未安装")
        issues.append("pip install pyyaml")

    try:
        from PIL import Image
        _ok("Pillow 已安装（图片压缩可用）")
    except ImportError:
        print("[WARN] Pillow 未安装（大图上传可能失败）")
        issues.append("建议: pip install Pillow")

    # 生图模型固定为 Agnes；写作由当前 Agent 完成，不再检查外部写作模型。
    im = cfg.get("image_model")
    i_ok = (
        isinstance(im, dict)
        and str(im.get("provider") or "").strip().lower() == "agnes"
        and str(im.get("base_url") or "").strip().rstrip("/") == "https://apihub.agnes-ai.com/v1/images/generations"
        and str(im.get("model") or "").strip() == "agnes-image-2.1-flash"
        and bool((env.get("AGNES_API_KEY") or "").strip())
    )
    if i_ok:
        _ok("图片模型已配置（Agnes Image 2.1 Flash + 外部环境 AGNES_API_KEY）")
    else:
        print("[WARN] Agnes 图片模型未齐（不影响纯发布，生图需 image_model 固定配置 + AGNES_API_KEY）")

    print("\n=== 检查完成 ===")
    if issues:
        print(f"\n需要处理的问题（{len(issues)} 个）：")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        _ok("发布相关检查通过！")


if __name__ == "__main__":
    raise SystemExit(main())
