#!/usr/bin/env python3
"""Scan-code login adapter for the VIDEO line's uploader (``sau``).

Why this exists
---------------
``sau <platform> login`` calls ``page.goto(url)`` with Playwright's default
``wait_until="load"``. On this machine every attempt died with
``Page.goto: Timeout 30000ms exceeded ... waiting until "load"`` while the same
URL loaded in 2.8 s over curl and in a bare patchright browser with either
``domcontentloaded`` or ``load``. The failure is therefore inside the uploader's
navigation semantics, not in the network or in the browser.

AGENTS.md ranks an ADAPTER above an UPSTREAM PATCH, so this script does not edit
the pinned ``.runtime/sau`` tree. It drives the same browsers, waits with
``domcontentloaded``, and writes exactly the ``storage_state`` file the uploader
expects at ``cookies/<sau_platform>_<account>.json``.

What it will never do
---------------------
* It never types an account name, a password, an OTP or a 2FA code.
* It never reads, prints or stores a credential value.
* It never claims a login succeeded because a file exists: each success is a
  platform-specific signal (a session cookie for the domestic platforms, a URL
  that actually rests on ``studio.youtube.com`` for YouTube), and the caller is
  expected to confirm with ``sau <platform> check``.

Usage
-----
    python scripts/sau_login.py --platform douyin --account <name>
    python scripts/sau_login.py --platform douyin,tencent,xiaohongshu --account <name>
    python scripts/sau_login.py --platform youtube --account <name> --proxy socks5://127.0.0.1:10808

Exit codes: 0 all requested platforms confirmed, 1 at least one not confirmed,
2 bad usage / missing runtime.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SAU_ROOT = ROOT / ".runtime" / "sau"
COOKIE_DIR = SAU_ROOT / "cookies"
PROFILE_DIR = SAU_ROOT / "profiles"


@dataclass(frozen=True)
class Target:
    """One platform's login contract.

    ``session_cookie`` is the cookie whose presence proves a session for the
    domestic platforms. ``requires_studio`` marks YouTube, where Google writes
    partial cookies on the password-challenge page, so cookie presence alone
    would record an unauthenticated state.
    """

    platform_id: str
    sau_platform: str
    url: str
    session_cookie: str
    needs_proxy: bool = False
    requires_studio: bool = False


TARGETS: dict[str, Target] = {
    "douyin": Target("douyin", "douyin", "https://creator.douyin.com/", "sessionid"),
    "shipinhao": Target("shipinhao", "tencent", "https://channels.weixin.qq.com/platform", "sessionid"),
    "xiaohongshu_video": Target("xiaohongshu_video", "xiaohongshu", "https://creator.xiaohongshu.com/", "web_session"),
    "kuaishou": Target("kuaishou", "kuaishou", "https://cp.kuaishou.com/", "kuaishou.web.cp.api_ph"),
    "bilibili": Target("bilibili", "bilibili", "https://member.bilibili.com/platform/home", "SESSDATA"),
    "youtube": Target(
        "youtube",
        "youtube",
        "https://studio.youtube.com/",
        "SID",
        needs_proxy=True,
        requires_studio=True,
    ),
}


class LoginError(RuntimeError):
    """The adapter could not even start (missing runtime, unknown platform)."""


def cookie_file(account: str, target: Target) -> Path:
    return COOKIE_DIR / f"{target.sau_platform}_{account}.json"


def resolve_targets(names: str) -> list[Target]:
    wanted = [n.strip() for n in names.split(",") if n.strip()]
    if not wanted:
        raise LoginError("--platform 不能为空")
    unknown = [n for n in wanted if n not in TARGETS]
    if unknown:
        raise LoginError(f"未知平台 {unknown}；可选 {sorted(TARGETS)}")
    return [TARGETS[n] for n in wanted]


def _playwright():
    try:
        from patchright.sync_api import sync_playwright  # noqa: PLC0415
    except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
        raise LoginError(
            "patchright 未安装。请用项目 venv 运行：.runtime/sau-venv/Scripts/python.exe"
        ) from exc
    return sync_playwright


def _login_one(pw, target: Target, account: str, *, timeout_s: int, proxy: str) -> dict[str, Any]:
    dest = cookie_file(account, target)
    launch_kw: dict[str, Any] = {"headless": False, "channel": "chromium"}
    if target.needs_proxy and proxy:
        launch_kw["proxy"] = {"server": proxy}

    profile = PROFILE_DIR / f"{target.sau_platform}_{account}"
    profile.mkdir(parents=True, exist_ok=True)

    # A persistent profile is not a convenience: the first non-persistent run
    # lost a completed Google login because the window was closed before the
    # confirmation poll fired, and the operator had to log in again. With a
    # stored profile a second attempt reuses the session instead of repeating it.
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        viewport={"width": 1280, "height": 880},
        args=["--no-first-run", "--no-default-browser-check"],
        **launch_kw,
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    record: dict[str, Any] = {
        "platform_id": target.platform_id,
        "sau_platform": target.sau_platform,
        "cookie_file": str(dest),
        "profile_dir": str(profile),
        "proxy_used": bool(launch_kw.get("proxy")),
        "confirmed": False,
        "reason": "",
    }
    nudged = 0
    try:
        page.goto(target.url, wait_until="domcontentloaded", timeout=60_000)
        record["landed_url"] = page.url
        stable = 0
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            url = page.url
            if target.requires_studio:
                on_studio = url.startswith("https://studio.youtube.com") and "accounts.google.com" not in url
                if on_studio:
                    stable += 1
                    if stable >= 3:
                        record["confirmed"] = True
                        break
                else:
                    stable = 0
                    # A finished Google login can land on the YouTube home page
                    # instead of Studio. Nudge once, and never fight the operator
                    # while the sign-in pages are still on screen.
                    signed_in_elsewhere = (
                        "youtube.com" in url
                        and "accounts.google.com" not in url
                        and nudged < 2
                    )
                    if signed_in_elsewhere:
                        nudged += 1
                        record["nudged_to_studio"] = nudged
                        try:
                            page.goto(target.url, wait_until="domcontentloaded", timeout=45_000)
                        except Exception as exc:  # noqa: BLE001
                            record["nudge_error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
            else:
                if any(c.get("name") == target.session_cookie for c in ctx.cookies()):
                    record["confirmed"] = True
                    break
            time.sleep(3)

        record["final_url"] = page.url
        if record["confirmed"]:
            time.sleep(3)
            dest.parent.mkdir(parents=True, exist_ok=True)
            ctx.storage_state(path=str(dest))
            data = json.loads(dest.read_text(encoding="utf-8"))
            names = {c.get("name") for c in data.get("cookies", [])}
            # A saved state without the proven cookie would be worse than none.
            if target.session_cookie not in names and not target.requires_studio:
                dest.unlink(missing_ok=True)
                record["confirmed"] = False
                record["reason"] = f"storage_state 缺少 {target.session_cookie}，已删除不留下假状态"
            else:
                record["cookies_saved"] = len(names)
                record["reason"] = "confirmed"
        else:
            record["reason"] = "TIMEOUT: 未观察到登录完成信号，未写 cookie"
    except Exception as exc:  # noqa: BLE001 - report, never crash the batch
        record["reason"] = f"ERROR {type(exc).__name__}: {str(exc)[:160]}"
    finally:
        ctx.close()
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="扫码登录 VIDEO 线上传器；只等人工操作，不输入任何凭据。",
    )
    parser.add_argument("--platform", required=True, help="逗号分隔：douyin,shipinhao,xiaohongshu_video,kuaishou,bilibili,youtube")
    parser.add_argument("--account", required=True, help="cookie 文件主名，需与 video_deliver 的 --account 一致")
    parser.add_argument("--timeout", type=int, default=300, help="每个平台等待人工登录的秒数")
    parser.add_argument("--proxy", default="", help="需要代理的平台使用；如 socks5://127.0.0.1:10808")
    parser.add_argument("--json", action="store_true", help="输出 JSON 回执")
    args = parser.parse_args(argv)

    try:
        targets = resolve_targets(args.platform)
    except LoginError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    try:
        sync_playwright = _playwright()
    except LoginError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    with sync_playwright() as pw:
        for target in targets:
            print(f"[{target.platform_id}] 打开登录页 {target.url} —— 请人工完成登录", flush=True)
            results.append(_login_one(pw, target, args.account, timeout_s=args.timeout, proxy=args.proxy))

    payload = {
        "schema": "contentops.sau-login/v1",
        "account": args.account,
        "results": results,
        "confirmed": [r["platform_id"] for r in results if r["confirmed"]],
        "unconfirmed": [r["platform_id"] for r in results if not r["confirmed"]],
        "note": "本脚本只落 storage_state；登录是否可用请再跑 sau <platform> check 确认。",
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = "OK  " if r["confirmed"] else "FAIL"
            print(f"  {mark} {r['platform_id']:20s} {r['reason']}")
        print(f"confirmed={payload['confirmed']} unconfirmed={payload['unconfirmed']}")
    return 0 if not payload["unconfirmed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
