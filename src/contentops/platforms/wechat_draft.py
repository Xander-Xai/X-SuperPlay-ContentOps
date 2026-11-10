"""WeChat Official Account drafts, built here instead of only outside the repo.

Why this module exists
----------------------
``config/platforms/graphic-platforms.yaml`` declares two channels for
``wechat_article``: a draft-only API channel (``wechatpy:draft``) and a browser
bridge. Only the bridge had code in this repository. The API path lived entirely
in an operator script outside the tree, which meant "the workflow can reach
WeChat" depended on a file no test, no CI and no reviewer could see.

This module is the part that belongs in the repository: shaping an article into
a draft payload, checking the credentials before anything is sent, naming the
exact steps, and deciding whether a read-back proves the draft exists. It is
deliberately **transport-free** — it never imports ``wechatpy``, never opens a
socket and never reads a credential value. ``scripts/wechat_draft.py`` owns those
three things and imports them lazily, only when ``--execute`` is passed.

Account DNA is the input
------------------------
The author name comes from the account DNA (``account``), not from a constant, so
a draft is attributed to the account it belongs to. Title and digest limits come
from ``graphic_specs`` (the same numbers the packer already uses), and a title
that has to be shortened keeps its original.

What this module refuses to pretend
-----------------------------------
* A draft needs a cover. WeChat rejects ``thumb_media_id``-less drafts, so a
  missing cover is a blocker, not a warning.
* IP whitelisting cannot be checked offline. ``preflight`` returns
  ``ip_whitelist: "UNKNOWN"`` and only a real token fetch can settle it.
* No function here claims a draft was created. Only ``readback_check`` on a real
  ``draft/get`` response may do that, and only for the fields it compares.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from . import graphic_specs

__all__ = [
    "CREDENTIAL_KEYS",
    "DRAFT_ENDPOINTS",
    "author_for",
    "build_articles",
    "content_digest",
    "normalise_html",
    "plan",
    "preflight",
    "readback_check",
]

PLATFORM = "wechat_article"

#: The slot naming this repository already uses for the first account.
CREDENTIAL_KEYS = ("WECHAT_1_APPID", "WECHAT_1_APPSECRET")

#: Documented endpoints, recorded so a reviewer can see what the script will
#: call without reading the script.
DRAFT_ENDPOINTS = {
    "token": "GET  /cgi-bin/token?grant_type=client_credential",
    "material_add_image": "POST /cgi-bin/material/add_material?type=image",
    "draft_add": "POST /cgi-bin/draft/add",
    "draft_get": "POST /cgi-bin/draft/get",
}

_PLACEHOLDER = re.compile(r"(your|xxx|changeme|placeholder|todo|<.*>)", re.IGNORECASE)


def author_for(dna: dict[str, Any]) -> str:
    """The byline WeChat will show, taken from the account's own DNA."""
    account = str(dna.get("account") or "").strip()
    if account:
        return account
    brand = dna.get("brand") or {}
    return str(brand.get("name") or brand.get("slogan") or "").strip()


def normalise_html(html: str) -> str:
    """Collapse whitespace so a read-back comparison is about content, not layout."""
    text = re.sub(r">\s+<", "><", str(html or ""))
    return re.sub(r"\s+", " ", text).strip()


def content_digest(html: str) -> str:
    return hashlib.sha256(normalise_html(html).encode("utf-8")).hexdigest()


def _first_sentence(text: str, budget: int) -> str:
    plain = re.sub(r"<[^>]+>", "", str(text or "")).strip()
    if len(plain) <= budget:
        return plain
    head = plain[:budget]
    for mark in ("。", "！", "？", "；", ".", "!", "?", ";"):
        cut = head.rfind(mark)
        if cut >= budget // 2:
            return head[: cut + 1]
    return head.rstrip() + "…"


def build_articles(
    article: dict[str, Any],
    dna: dict[str, Any],
    *,
    thumb_media_id: str = "",
    open_comment: bool = False,
    fans_only_comment: bool = True,
) -> dict[str, Any]:
    """Shape one article into a WeChat draft payload plus the issues found.

    ``article`` carries ``title``, ``content`` (HTML) and optionally ``digest``
    and ``source_url``. The result is data: nothing is uploaded, nothing is
    claimed, and every adjustment is recorded.
    """
    rules = graphic_specs.rules(PLATFORM)
    issues: list[dict[str, Any]] = []

    title_raw = str(article.get("title") or "").strip()
    title = title_raw
    if rules["title_max_hard"] and len(title_raw) > rules["title_max_hard"]:
        title = title_raw[: rules["title_max_hard"] - 1].rstrip("，、,· ") + "…"
        issues.append({
            "code": "TITLE_TRUNCATED",
            "severity": "warning",
            "detail": f"{len(title_raw)} -> {len(title)} 字符，原文保留",
        })
    elif rules["title_max_soft"] and len(title_raw) > rules["title_max_soft"]:
        issues.append({
            "code": "TITLE_OVER_SOFT_LIMIT",
            "severity": "warning",
            "detail": f"{len(title_raw)} > {rules['title_max_soft']} 字符（约定值）",
        })

    content = str(article.get("content") or "")
    if not normalise_html(content):
        issues.append({
            "code": "CONTENT_EMPTY", "severity": "blocker",
            "detail": "草稿正文为空",
        })

    digest_raw = str(article.get("digest") or "").strip()
    digest = digest_raw or _first_sentence(content, rules["summary_max"] or 120)
    if rules["summary_max"] and len(digest) > rules["summary_max"]:
        digest = digest[: rules["summary_max"] - 1].rstrip() + "…"
        issues.append({
            "code": "DIGEST_TRUNCATED", "severity": "warning",
            "detail": f"摘要收敛到 {rules['summary_max']} 字符",
        })

    if not thumb_media_id:
        issues.append({
            "code": "COVER_REQUIRED", "severity": "blocker",
            "detail": "缺少 thumb_media_id；微信不接受没有封面的草稿",
        })

    payload = {
        "title": title,
        "title_original": title_raw if title != title_raw else "",
        "author": author_for(dna),
        "digest": digest,
        "content": content,
        "content_source_url": str(article.get("source_url") or "").strip(),
        "thumb_media_id": thumb_media_id,
        "need_open_comment": 1 if open_comment else 0,
        "only_fans_can_comment": 1 if fans_only_comment else 0,
    }
    blocked = [i for i in issues if i["severity"] == "blocker"]
    return {
        "platform": PLATFORM,
        "article": payload,
        "issues": issues,
        "state": "BLOCKED" if blocked else "READY_FOR_DRAFT",
        "content_digest": content_digest(content),
    }


def preflight(env: dict[str, Any]) -> dict[str, Any]:
    """Check the credential *shape* without ever echoing a value.

    An offline check cannot prove the secret works, and it cannot see whether the
    caller's exit IP is whitelisted — WeChat answers ``40164`` for that. Both are
    reported as unknown rather than guessed, because a fake green here is what
    sends someone into a 30-minute debugging session.
    """
    checks: list[dict[str, Any]] = []

    appid = str(env.get("WECHAT_1_APPID") or "").strip()
    secret = str(env.get("WECHAT_1_APPSECRET") or "").strip()

    if not appid:
        checks.append({"name": "appid_present", "ok": False, "detail": "缺少 WECHAT_1_APPID"})
    elif not appid.startswith("wx") or len(appid) < 16:
        checks.append({"name": "appid_shape", "ok": False,
                       "detail": f"AppID 形状不像微信的（长度 {len(appid)}，应以 wx 开头）"})
    elif _PLACEHOLDER.search(appid):
        checks.append({"name": "appid_placeholder", "ok": False, "detail": "AppID 仍是占位符"})
    else:
        checks.append({"name": "appid_present", "ok": True, "detail": f"长度 {len(appid)}"})

    if not secret:
        checks.append({"name": "secret_present", "ok": False, "detail": "缺少 WECHAT_1_APPSECRET"})
    elif len(secret) < 32:
        checks.append({"name": "secret_shape", "ok": False,
                       "detail": f"AppSecret 长度 {len(secret)}，通常为 32"})
    elif _PLACEHOLDER.search(secret):
        checks.append({"name": "secret_placeholder", "ok": False, "detail": "AppSecret 仍是占位符"})
    else:
        checks.append({"name": "secret_present", "ok": True, "detail": f"长度 {len(secret)}"})

    ok = all(check["ok"] for check in checks)
    return {
        "ok": ok,
        "checks": checks,
        "ip_whitelist": "UNKNOWN",
        "ip_whitelist_note": "出口 IP 是否加白只能靠真实 token 请求判定；40164 即为未加白",
        "secrets_echoed": False,
    }


def plan(*, cover_to_upload: bool) -> list[dict[str, Any]]:
    """The ordered calls this script will make, with the reason for each.

    ``cover_to_upload`` means "a cover file is about to be uploaded", not "a
    thumb_media_id already exists". The distinction matters: passing a cover path
    and skipping the upload step would send ``draft/add`` without a media id and
    WeChat would reject it.
    """
    steps = [
        {"step": 1, "call": "token", "endpoint": DRAFT_ENDPOINTS["token"],
         "why": "拿 access_token；40164 说明出口 IP 未加白"},
    ]
    if cover_to_upload:
        steps.append({
            "step": 2, "call": "material_add_image",
            "endpoint": DRAFT_ENDPOINTS["material_add_image"],
            "why": "上传封面为永久素材，换取 thumb_media_id",
        })
    steps.extend([
        {"step": len(steps) + 1, "call": "draft_add", "endpoint": DRAFT_ENDPOINTS["draft_add"],
         "why": "创建草稿；只到草稿边界，不群发"},
        {"step": len(steps) + 2, "call": "draft_get", "endpoint": DRAFT_ENDPOINTS["draft_get"],
         "why": "回读草稿内容，回读通过才允许写 publish_completed"},
    ])
    return steps


def readback_check(requested: dict[str, Any], fetched: dict[str, Any]) -> dict[str, Any]:
    """Compare what we asked WeChat to store with what WeChat says it stored.

    Only the fields this module shaped are compared. A mismatch is a real failure:
    it means the platform edited, truncated or replaced something, and a receipt
    written before this check would be a claim about a draft that never existed.
    """
    issues: list[dict[str, Any]] = []

    if not fetched:
        return {"ok": False, "issues": [{"code": "DRAFT_NOT_FOUND", "detail": "draft/get 无返回"}]}

    for field in ("title", "digest"):
        want = str(requested.get(field) or "")
        got = str(fetched.get(field) or "")
        if want and got and want != got:
            issues.append({
                "code": f"{field.upper()}_MISMATCH",
                "detail": f"请求 {len(want)} 字符，回读 {len(got)} 字符",
            })

    want_digest = content_digest(str(requested.get("content") or ""))
    got_digest = content_digest(str(fetched.get("content") or ""))
    if want_digest != got_digest:
        issues.append({
            "code": "CONTENT_MISMATCH",
            "detail": f"请求 {want_digest[:12]}… vs 回读 {got_digest[:12]}…",
        })

    return {"ok": not issues, "issues": issues}
