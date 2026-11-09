#!/usr/bin/env python3
"""Create a WeChat Official Account draft from a reviewed article.

This is the in-repository transport for the ``wechatpy:draft`` channel that
``config/platforms/graphic-platforms.yaml`` already declares. It stops at a
**draft**; it never mass-sends, never reads a metric and never records a URL it
did not receive.

    preflight   Check credential shape. Offline. Never echoes a value.
    plan        Show the exact calls and the shaped payload. Offline.
    publish     token -> material/add -> draft/add -> draft/get, then a receipt.
                Requires --execute, an env file and a cover image.
    verify      Re-read an existing draft by media_id and compare it.

What this script will not do
----------------------------
* It will not guess whether the caller's IP is whitelisted. WeChat answers
  ``40164`` for that, and only a real token request can prove it either way.
* It will not write a receipt before ``draft/get`` comes back. A receipt written
  earlier would be a claim about a draft nobody has seen.
* It will not print AppID, AppSecret or access_token. The receipt records lengths
  and digests, not secrets.

``wechatpy`` is imported lazily from the vendored tree so this file's offline
commands work on a machine where the client library's own dependencies are not
installed yet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts", ROOT / "vendor" / "wechatpy"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.accounts import load_account  # noqa: E402
from contentops.platforms import wechat_draft  # noqa: E402

#: WeChat answers this for an IP that is not on the account's whitelist.
IP_NOT_WHITELISTED = "40164"
#: Wrong or missing credential.
BAD_CREDENTIALS = "40001"


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"BLOCKED: 凭证文件不存在 {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _load_account(data: dict[str, Any]) -> dict[str, Any]:
    slug = str(data.get("account_slug") or data.get("account") or "").strip()
    path = ROOT / "config" / "accounts" / f"{slug}.json"
    if not path.is_file():
        raise SystemExit(f"BLOCKED: 账号 DNA 不存在 {path}")
    return load_account(path)


def _import_client() -> Any:
    try:
        from wechatpy import WeChatClient  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "BLOCKED: wechatpy 依赖缺失（缺少 %s）。"
            "在有该依赖的 venv 里运行，或先安装 optionaldict / xmltodict。" % exc.name
        ) from exc
    return WeChatClient


def _wechat_error(exc: Exception) -> str:
    text = repr(exc)
    if IP_NOT_WHITELISTED in text:
        return ("IP_NOT_WHITELISTED: 微信返回 40164——当前出口 IP 不在公众号后台白名单，"
                "这不是代码问题，只能加白后重试")
    if BAD_CREDENTIALS in text:
        return "BAD_CREDENTIALS: 微信返回 40001——AppSecret 不正确或与 AppID 不匹配"
    return f"WECHAT_CALL_FAILED: {text[:300]}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("preflight", "plan", "publish", "verify"))
    parser.add_argument("--article", default="", help="JSON: title/content/digest/source_url")
    parser.add_argument("--account", default="", help="account DNA slug (default from article)")
    parser.add_argument("--cover", default="", help="cover image path (permanent material)")
    parser.add_argument("--env", default="", help="credential file (KEY=VALUE), out of repo")
    parser.add_argument("--media-id", default="", help="existing draft media_id (verify)")
    parser.add_argument("--out", default="", help="receipt path (publish)")
    parser.add_argument("--open-comment", action="store_true")
    parser.add_argument("--fans-only-comment", action="store_true")
    parser.add_argument("--execute", action="store_true", help="actually call WeChat")
    args = parser.parse_args(argv)

    if args.command == "preflight":
        env = _parse_env(Path(args.env)) if args.env else {}
        result = wechat_draft.preflight(env)
        _emit({"schema": "contentops.wechat-preflight/v1", **result,
               "endpoints": wechat_draft.DRAFT_ENDPOINTS})
        return 0 if result["ok"] else 2

    if not args.article:
        _emit({"status": "BLOCKED", "reason": "--article 必填：本脚本只消费已审定的文章 JSON"})
        return 1

    article_file = Path(args.article)
    if not article_file.is_file():
        _emit({"status": "BLOCKED", "reason": f"文章不存在 {article_file}"})
        return 1
    article = json.loads(article_file.read_text(encoding="utf-8"))
    dna = _load_account({**article, **({"account_slug": args.account} if args.account else {})})

    cover = Path(args.cover) if args.cover else None
    if cover and not cover.is_file():
        _emit({"status": "BLOCKED", "reason": f"封面不存在 {cover}"})
        return 1

    if args.command == "plan":
        shaped = wechat_draft.build_articles(
            article, dna,
            thumb_media_id="<cover-upload-id>" if cover else "",
            open_comment=args.open_comment,
            fans_only_comment=args.fans_only_comment,
        )
        _emit({
            "schema": "contentops.wechat-draft-plan/v1",
            "state": shaped["state"],
            "steps": wechat_draft.plan(cover_to_upload=bool(cover)),
            "author": shaped["article"]["author"],
            "title": shaped["article"]["title"],
            "title_original": shaped["article"]["title_original"],
            "digest_len": len(shaped["article"]["digest"]),
            "content_digest": shaped["content_digest"],
            "issues": shaped["issues"],
            "cover_sha256": _sha256_file(cover) if cover else "",
            "note": "plan 不联网、不写草稿；真正写入需要 --execute 与凭证文件",
        })
        return 0 if shaped["state"] == "READY_FOR_DRAFT" else 2

    env = _parse_env(Path(args.env)) if args.env else {}
    preflight = wechat_draft.preflight(env)
    if not preflight["ok"]:
        _emit({"status": "BLOCKED", "reason": "PREFLIGHT_FAILED", "preflight": preflight})
        return 2

    if args.command == "verify":
        if not args.media_id:
            _emit({"status": "BLOCKED", "reason": "--media-id 必填"})
            return 1
        if not args.execute:
            _emit({"status": "BLOCKED", "reason": "verify 会真实请求微信，需显式 --execute"})
            return 1
        WeChatClient = _import_client()
        try:
            client = WeChatClient(env["WECHAT_1_APPID"].strip(), env["WECHAT_1_APPSECRET"].strip())
            fetched = client.draft.get(args.media_id)
        except Exception as exc:  # noqa: BLE001
            _emit({"status": "BLOCKED", "reason": _wechat_error(exc)})
            return 2
        items = fetched.get("news_item") or []
        _emit({
            "schema": "contentops.wechat-draft-verify/v1",
            "media_id": args.media_id,
            "item_count": len(items),
            "title": (items[0].get("title") if items else ""),
            "readback": "PRESENT" if items else "EMPTY",
            "checked_at": _stamp(),
        })
        return 0 if items else 2

    if not args.execute:
        _emit({"status": "BLOCKED",
               "reason": "publish 会真实创建草稿，需显式 --execute（并确认封面与内容已审定）"})
        return 1

    WeChatClient = _import_client()
    receipt: dict[str, Any] = {
        "schema": "contentops.wechat-draft/v1",
        "command": "publish",
        "account": dna.get("account"),
        "started_at": _stamp(),
        "publish_authorized": False,
        "metrics": "NONE",
        "secrets_echoed": False,
    }

    try:
        client = WeChatClient(env["WECHAT_1_APPID"].strip(), env["WECHAT_1_APPSECRET"].strip())
        thumb_id = ""
        if cover:
            with cover.open("rb") as handle:
                material = client.material.add(media_type="image", media_file=handle)
            thumb_id = str(material.get("media_id") or "")
            receipt["cover"] = {"sha256": _sha256_file(cover), "media_id": thumb_id}

        shaped = wechat_draft.build_articles(
            article, dna, thumb_media_id=thumb_id,
            open_comment=args.open_comment, fans_only_comment=args.fans_only_comment,
        )
        receipt["state_before_draft"] = shaped["state"]
        receipt["issues"] = shaped["issues"]
        if shaped["state"] != "READY_FOR_DRAFT":
            receipt["status"] = "BLOCKED"
            receipt["reason"] = "本地成稿未通过（缺封面或正文为空），未调用 draft/add"
            _write_receipt(receipt, args)
            _emit(receipt)
            return 2

        created = client.draft.add(articles=[shaped["article"]])
        media_id = str(created.get("media_id") or "")
        receipt["media_id"] = media_id
        receipt["content_digest"] = shaped["content_digest"]

        fetched = client.draft.get(media_id)
        items = fetched.get("news_item") or []
        check = wechat_draft.readback_check(shaped["article"], items[0] if items else {})
        receipt["readback"] = check
        receipt["status"] = "DRAFT_CREATED" if check["ok"] else "READBACK_MISMATCH"
        receipt["note"] = "只创建草稿，未群发；真实发布需在公众号后台人工确认"
    except Exception as exc:  # noqa: BLE001
        receipt["status"] = "BLOCKED"
        receipt["reason"] = _wechat_error(exc)

    receipt["finished_at"] = _stamp()
    _write_receipt(receipt, args)
    _emit(receipt)
    return 0 if receipt["status"] == "DRAFT_CREATED" else 2


def _write_receipt(receipt: dict[str, Any], args: argparse.Namespace) -> None:
    if not args.out:
        return
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    receipt["receipt_path"] = str(path)


if __name__ == "__main__":
    raise SystemExit(main())
