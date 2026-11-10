#!/usr/bin/env python3
"""Run one Wechatsync CLI command with the bridge alive.

The CLI is a WebSocket server on 127.0.0.1:9527 and the browser extension is the
client, so a command only works while a browser carrying the extension is running
with the bridge switch on and a token that matches. Doing those three things by
hand is what made every earlier attempt report "需要安装 Chrome 扩展".

Usage
-----
    python scripts/wechatsync_bridge_run.py -- platforms
    python scripts/wechatsync_bridge_run.py -- auth
    python scripts/wechatsync_bridge_run.py -- sync <abs-path.md> -p zhihu --title "..." --cover <abs.png>

Paths passed to ``sync`` must be absolute: the CLI resolves relative paths against
its own working directory, not the caller's.
"""

from __future__ import annotations

import argparse
import sys

from contentops.platforms.wcs_bridge import BridgeError, bridge_session, run_cli

# Platforms whose login page it is worth opening when the operator asks to log in.
LOGIN_URLS = {
    "zhihu": "https://www.zhihu.com/signin",
    "csdn": "https://passport.csdn.net/login",
    "juejin": "https://juejin.cn/login",
    "toutiao": "https://mp.toutiao.com/auth/page/login",
    "weibo": "https://weibo.com/login.php",
    "weixin": "https://mp.weixin.qq.com/",
    "x": "https://x.com/i/flow/login",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cli_args", nargs=argparse.REMAINDER,
                        help="everything after -- goes to the wechatsync CLI")
    parser.add_argument("--open-url", default="about:blank",
                        help="page to open first; blank by default so no platform is contacted")
    parser.add_argument("--login-page", default="",
                        help="open one platform's login page instead (zhihu/csdn/juejin/...")
    parser.add_argument("--hold", type=int, default=0,
                        help="keep the browser open N extra seconds (for manual login)")
    parser.add_argument("--timeout", default="45000", help="CLI bridge timeout in ms")
    args = parser.parse_args()

    cli_args = [a for a in args.cli_args if a != "--"] or ["platforms"]
    open_url = LOGIN_URLS.get(args.login_page, args.open_url) if args.login_page else args.open_url

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        print("BLOCKED: Playwright 未安装", file=sys.stderr)
        return 1

    try:
        with sync_playwright() as pw:
            with bridge_session(pw, open_url=open_url) as session:
                print(f"RUN {' '.join(cli_args)}", flush=True)
                out = run_cli(cli_args, timeout_ms=int(args.timeout), token=session["token"])
                print(f"BRIDGE_CONNECTED {out['bridge_connected']}", flush=True)
                print(f"CLI EXIT={out['returncode']}", flush=True)
                if out["stdout"].strip():
                    print("--- stdout ---", flush=True)
                    print(out["stdout"].strip()[:6000], flush=True)
                if out["stderr"].strip():
                    print("--- stderr ---", flush=True)
                    print(out["stderr"].strip()[:3000], flush=True)
                if args.hold:
                    print(f"HOLDING {args.hold}s — 请在这个窗口里完成登录", flush=True)
                    import time
                    time.sleep(args.hold)
                return 0 if out["returncode"] == 0 else 1
    except BridgeError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
