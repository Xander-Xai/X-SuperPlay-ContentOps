#!/usr/bin/env python3
"""Open every target platform's login page in the persistent profile, then hold.

The whole point is *once*: the profile under ``.runtime/wechatsync-browser`` keeps
its cookies, so after one manual login round every later delivery run works
without touching a browser by hand.

This script deliberately does not log in for you and does not type anything. It
opens tabs, prints which platform each tab is for, and keeps the browser alive so
you can sign in normally. Close the window (or let the hold expire) when done.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.platforms import graphic_specs  # noqa: E402

LOGIN_URLS = {
    "wechat_article": "https://mp.weixin.qq.com/",
    "csdn": "https://passport.csdn.net/login",
    "juejin": "https://juejin.cn/login",
    "toutiao": "https://mp.toutiao.com/auth/page/login",
    "weibo": "https://weibo.com/login.php",
    "x": "https://x.com/i/flow/login",
    "zhihu": "https://www.zhihu.com/signin",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platforms", default="",
                        help="逗号分隔；默认全部有登录页的图文平台")
    parser.add_argument("--hold", type=int, default=900, help="保持窗口秒数")
    parser.add_argument("--then-deliver", action="store_true",
                        help="窗口关闭或 hold 结束后，自动对已登录的平台投递草稿并出回执")
    parser.add_argument("--output", default=str(ROOT / ".runtime" / "login-deliver.json"))
    args = parser.parse_args()

    ids = [p.strip() for p in args.platforms.split(",") if p.strip()] or list(LOGIN_URLS)
    ids = [p for p in ids if p in LOGIN_URLS]
    if not ids:
        print("BLOCKED: 没有可打开的登录页", file=sys.stderr)
        return 1

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        print("BLOCKED: Playwright 未安装", file=sys.stderr)
        return 1

    from contentops.platforms.wcs_bridge import EXT_DIR, PROFILE_DIR, extension_id

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            args=[
                f"--disable-extensions-except={EXT_DIR}",
                f"--load-extension={EXT_DIR}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            viewport={"width": 1400, "height": 950},
        )
        try:
            try:
                ext_id = extension_id(context)
                print(f"EXTENSION id={ext_id}", flush=True)
            except Exception as exc:  # noqa: BLE001 - login still works without it
                print(f"EXTENSION_WARN {exc}", flush=True)

            first = True
            for pid in ids:
                page = context.pages[0] if first and context.pages else context.new_page()
                if first:
                    page = context.pages[0]
                    first = False
                try:
                    page.goto(LOGIN_URLS[pid], timeout=30_000)
                    label = graphic_specs.spec(pid)["display_name"]
                    print(f"TAB {pid:16} {label:12} {LOGIN_URLS[pid]}", flush=True)
                except Exception as exc:  # noqa: BLE001 - one bad tab must not stop the rest
                    print(f"TAB_FAILED {pid}: {type(exc).__name__}", flush=True)

            print(f"\n请在窗口里逐个登录：{' / '.join(ids)}", flush=True)
            print(f"登录完成后直接关闭这个窗口即可，最长等待 {args.hold}s", flush=True)

            # Poll instead of sleeping the full hold: closing the window is the
            # natural "I am done" signal, and blocking on sleep would make the
            # operator wait out the timer for no reason.
            deadline = time.time() + args.hold
            while time.time() < deadline:
                time.sleep(2)
                if not context.pages:
                    print("WINDOW_CLOSED", flush=True)
                    break
            else:
                print("HOLD_EXPIRED", flush=True)

            if args.then_deliver:
                _deliver(context, ids, args.output)
        finally:
            context.close()
    return 0


def _deliver(context, ids, output_path) -> None:
    """Run the delivery pass inside the same browser session, then write a receipt."""
    from contentops.platforms.wcs_bridge import parse_sync_result, read_token, run_cli

    token = ""
    try:
        page = context.new_page()
        page.goto(f"chrome-extension://{extension_id_for(context)}/src/popup/index.html", timeout=20_000)
        token = read_token(page)
        page.close()
    except Exception as exc:  # noqa: BLE001 - delivery can still run on the cached token
        print(f"TOKEN_REFRESH_FAILED {type(exc).__name__}", flush=True)

    sys.path.insert(0, str(ROOT / "scripts"))
    import json as _json
    from contentops.platforms import multichannel as mc
    from contentops.platforms.wcs_bridge import OUT_DIR

    package_file = ROOT / "projects" / "bundle-dual-line-graphic" / "receipts" / "graphic-package.json"
    package = _json.loads(package_file.read_text(encoding="utf-8"))
    package["_package_root"] = str(package_file.parent.parent)
    results = []
    for pid in ids:
        try:
            draft = mc.MultiChannelAdapter(pid).pack(package, {"account_slug": "explorer"})
        except Exception as exc:  # noqa: BLE001 - report, never crash the batch
            results.append({"platform_id": pid, "status": "pack_failed", "ok": False, "reason": str(exc)[:120]})
            continue
        adapter = ""
        for ch in graphic_specs.channels(pid):
            if ch["kind"] == "browser_bridge":
                adapter = str(ch["id"]).split(":", 1)[1]
                break
        if not adapter:
            results.append({"platform_id": pid, "status": "no_bridge_channel", "ok": False})
            continue
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        article = OUT_DIR / f"{pid}.md"
        article.write_text(
            f"# {draft.title}\n\n{draft.body}" if draft.title else draft.body, encoding="utf-8")
        argv = ["sync", str(article.resolve()), "-p", adapter, "--title", draft.title or draft.title_hint]
        out = run_cli(argv, timeout_ms=70_000, token=token)
        parsed = parse_sync_result(out["stdout"])
        results.append({
            "platform_id": pid, "status": "draft_created" if parsed["ok"] and parsed["url"] else "failed",
            "ok": bool(parsed["ok"] and parsed["url"]), "url": parsed["url"],
            "reason": parsed["reason"], "bridge_connected": out["bridge_connected"],
        })
        print(f"[{'OK  ' if results[-1]['ok'] else 'FAIL'}] {pid}: {parsed['url'] or parsed['reason']}", flush=True)

    ok = sum(1 for r in results if r["ok"])
    payload = {"schema": "contentops.login-deliver/v1", "attempted": len(results),
               "delivered": ok, "failed": len(results) - ok, "published": False,
               "results": results}
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"DELIVER attempted={len(results)} delivered={ok} receipt={out_path}", flush=True)


def extension_id_for(context) -> str:
    from contentops.platforms.wcs_bridge import extension_id
    return extension_id(context)


if __name__ == "__main__":
    raise SystemExit(main())
