#!/usr/bin/env python3
"""Launch a dedicated Chromium profile with the Wechatsync extension loaded.

Why a dedicated profile
-----------------------
The Wechatsync CLI does not publish anything itself: it starts a local
WebSocket service and waits for the browser extension to connect, then asks the
extension to call each platform's own web API using the cookies already present
in that browser. Without the extension there is no bridge, which is why every
delivery attempt so far ended in EXTENSION_NOT_CONNECTED.

This launcher does **not** touch the operator's normal Chrome profile. It creates
a separate persistent profile under ``.runtime/wechatsync-browser`` so that:

  * the operator's daily browsing, cookies and extensions stay untouched;
  * the login state used for publishing is isolated and easy to revoke --
    deleting the directory removes every platform session;
  * it is obvious which browser is doing the publishing.

The extension still has to be logged in by a human. This script never types a
password and never reads a credential: it only makes the bridge exist.

Usage
-----
    python scripts/wechatsync_browser.py --hold 900

``--hold`` keeps the browser open for N seconds so the CLI can connect. Ctrl-C
closes it. ``--headless`` is deliberately unsupported: Chromium only loads
unpacked extensions in a headed context, and a headless browser would silently
produce a bridge that never connects.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT_DIR = ROOT / ".runtime" / "wechatsync-ext"
PROFILE_DIR = ROOT / ".runtime" / "wechatsync-browser"


def _fail(message: str) -> int:
    print(f"BLOCKED: {message}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold", type=int, default=900, help="seconds to keep the browser open")
    parser.add_argument("--url", default="https://www.zhihu.com/", help="page to open so the extension boots")
    parser.add_argument("--reset-profile", action="store_true", help="delete the isolated profile first")
    parser.add_argument("--debug-port", type=int, default=9222,
                        help="CDP port so the extension can be verified from outside")
    parser.add_argument("--probe-ui", action="store_true",
                        help="open the extension's own popup page and dump its text")
    parser.add_argument("--probe-settings", action="store_true",
                        help="with --probe-ui, also open the settings panel")
    parser.add_argument("--enable-bridge", action="store_true",
                        help="with --probe-ui, turn on the extension's CLI/MCP bridge switch")
    parser.add_argument("--ensure-bridge", action="store_true",
                        help="idempotent: only flips the bridge switch when it reads 未启用")
    parser.add_argument("--dump-token", action="store_true",
                        help="write the bridge token to .runtime/wechatsync-token.txt (masked on stdout)")
    args = parser.parse_args()

    if not (EXT_DIR / "manifest.json").is_file():
        return _fail(f"扩展未解压到 {EXT_DIR}；先运行安装步骤")

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        return _fail("Playwright 未安装；本脚本需要项目 venv 中的 playwright")

    if args.reset_profile and PROFILE_DIR.exists():
        shutil.rmtree(PROFILE_DIR)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    args_list = [
        f"--disable-extensions-except={EXT_DIR}",
        f"--load-extension={EXT_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        f"--remote-debugging-port={args.debug_port}",
    ]

    print(f"extension : {EXT_DIR}", flush=True)
    print(f"profile   : {PROFILE_DIR}", flush=True)
    print(f"hold      : {args.hold}s", flush=True)
    print("HEADED_ONLY: Chromium 只在有头模式下加载未打包扩展", flush=True)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            args=args_list,
            viewport={"width": 1440, "height": 900},
        )
        # Report the extension's own id so an operator can confirm it really loaded.
        deadline = time.time() + 25
        worker = None
        while time.time() < deadline and worker is None:
            workers = [w for w in context.service_workers if "chrome-extension://" in w.url]
            if workers:
                worker = workers[0]
                break
            time.sleep(0.5)
        if worker:
            ext_id = worker.url.split("/")[2]
            print(f"EXTENSION_LOADED id={ext_id}", flush=True)
        else:
            print("EXTENSION_NOT_OBSERVED: service worker 未在 25s 内出现（扩展可能被 Chromium 拒绝加载）", flush=True)

        # Independent check through CDP: a loaded MV3 extension always exposes a
        # service-worker target. Reading it from the debug port avoids trusting
        # Playwright's own view of the browser.
        try:
            import json as _json
            import urllib.request
            with urllib.request.urlopen(
                f"http://127.0.0.1:{args.debug_port}/json/list", timeout=5
            ) as resp:
                targets = _json.loads(resp.read().decode("utf-8"))
            ext_targets = [t for t in targets if str(t.get("url", "")).startswith("chrome-extension://")]
            print(f"CDP_TARGETS total={len(targets)} extension={len(ext_targets)}", flush=True)
            for t in ext_targets[:5]:
                print(f"  CDP_EXT {t.get('type')} {t.get('url')}", flush=True)
        except Exception as exc:  # noqa: BLE001 - diagnostic only
            print(f"CDP_QUERY_FAILED {type(exc).__name__}: {exc}", flush=True)

        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(args.url, timeout=45_000)
            print(f"OPENED {args.url}", flush=True)
        except Exception as exc:  # noqa: BLE001 - the page is only a boot hook
            print(f"OPEN_FAILED {type(exc).__name__}: {exc}", flush=True)

        if args.probe_ui and worker:
            # MV3 popups cannot be opened as a normal tab via chrome-extension://
            # in every build, but the options/popup pages are ordinary extension
            # pages and can be loaded for inspection. This only reads the UI; it
            # does not click anything and does not store any credential.
            ext_id = worker.url.split("/")[2]
            for candidate in ("src/popup/index.html", "popup.html", "options.html", "index.html"):
                probe = context.new_page()
                try:
                    probe.goto(f"chrome-extension://{ext_id}/{candidate}", timeout=15_000)
                    probe.wait_for_timeout(2500)
                    text = (probe.evaluate("document.body ? document.body.innerText : ''") or "").strip()
                    print(f"PROBE {candidate} chars={len(text)}", flush=True)
                    for line in text.splitlines()[:40]:
                        if line.strip():
                            print(f"  | {line.strip()[:140]}", flush=True)
                    inputs = probe.evaluate(
                        "Array.from(document.querySelectorAll('input,button,select'))"
                        ".map(e=>({tag:e.tagName,type:e.type||'',text:(e.innerText||e.value||'').slice(0,40),ph:e.placeholder||''}))"
                    )
                    for item in inputs[:20]:
                        print(f"  ctrl {item}", flush=True)

                    if args.probe_settings:
                        clicked = probe.evaluate(
                            "(() => {const b=[...document.querySelectorAll('button')]"
                            ".find(e=>/设置|Settings/.test(e.innerText||'')); if(!b) return false;"
                            " b.click(); return true;})()"
                        )
                        print(f"CLICK_SETTINGS {clicked}", flush=True)
                        probe.wait_for_timeout(2500)
                        text2 = (probe.evaluate("document.body ? document.body.innerText : ''") or "").strip()
                        print(f"SETTINGS_TEXT chars={len(text2)}", flush=True)
                        for line in text2.splitlines()[:50]:
                            if line.strip():
                                print(f"  S| {line.strip()[:150]}", flush=True)
                        ctrl2 = probe.evaluate(
                            "Array.from(document.querySelectorAll('input,button,select,[role=switch]'))"
                            ".map(e=>({tag:e.tagName,type:e.type||'',role:e.getAttribute('role')||'',"
                            "text:(e.innerText||'').slice(0,30),val:String(e.value||'').slice(0,30),"
                            "ph:e.placeholder||'',checked:!!e.checked}))"
                        )
                        for item in ctrl2[:30]:
                            print(f"  S ctrl {item}", flush=True)

                    if args.enable_bridge:
                        # Locate the switch that sits in the same row as
                        # "CLI / MCP 连接" and report exactly what it is before
                        # clicking, so the action is auditable.
                        found = probe.evaluate(
                            """(() => {
                              const rows = [...document.querySelectorAll('*')]
                                .filter(e => (e.innerText||'').trim() === 'CLI / MCP 连接');
                              if (!rows.length) return {ok:false, why:'label_not_found'};
                              let node = rows[0];
                              for (let i=0;i<5 && node.parentElement;i++) {
                                node = node.parentElement;
                                const sw = node.querySelector(
                                  'button,[role=switch],input[type=checkbox],.switch,.toggle');
                                if (sw) {
                                  return {ok:true, tag:sw.tagName, cls:String(sw.className).slice(0,80),
                                          role:sw.getAttribute('role')||'',
                                          aria:sw.getAttribute('aria-checked')||'',
                                          before:(sw.innerText||'').slice(0,20)};
                                }
                              }
                              return {ok:false, why:'switch_not_found'};
                            })()"""
                        )
                        print(f"BRIDGE_SWITCH {found}", flush=True)
                        panel_before = probe.evaluate("document.body ? document.body.innerText : ''") or ""
                        if args.ensure_bridge and "未启用" not in panel_before:
                            print("BRIDGE_ALREADY_ENABLED: 跳过点击，避免把开关关掉", flush=True)
                            found = {"ok": False, "why": "already_enabled"}
                        if isinstance(found, dict) and found.get("ok"):
                            probe.evaluate(
                                """(() => {
                                  const rows = [...document.querySelectorAll('*')]
                                    .filter(e => (e.innerText||'').trim() === 'CLI / MCP 连接');
                                  let node = rows[0];
                                  for (let i=0;i<5 && node.parentElement;i++) {
                                    node = node.parentElement;
                                    const sw = node.querySelector(
                                      'button,[role=switch],input[type=checkbox],.switch,.toggle');
                                    if (sw) { sw.click(); return true; }
                                  }
                                  return false;
                                })()"""
                            )
                            probe.wait_for_timeout(3000)
                            after = (probe.evaluate("document.body ? document.body.innerText : ''") or "")
                            state = "ENABLED" if "已启用" in after else (
                                "STILL_DISABLED" if "未启用" in after else "UNKNOWN")
                            print(f"BRIDGE_STATE {state}", flush=True)
                            for line in after.splitlines():
                                if any(k in line for k in ("桥接", "MCP", "已登录", "token", "Token")):
                                    print(f"  B| {line.strip()[:140]}", flush=True)

                    if args.dump_token:
                        token = probe.evaluate(
                            """(() => {
                              const all = [...document.querySelectorAll('input,code,span,div')];
                              const idx = all.findIndex(e => (e.innerText||'').trim() === 'Token:');
                              if (idx >= 0) {
                                for (let i = idx; i < Math.min(idx + 12, all.length); i++) {
                                  const e = all[i];
                                  const v = (e.value || e.innerText || '').trim();
                                  if (v && v !== 'Token:' && v.length >= 8) return v;
                                }
                              }
                              const m = (document.body.innerText||'').match(/Token://s*([A-Za-z0-9_//-]{8,})/);
                              return m ? m[1] : '';
                            })()"""
                        ) or ""
                        token = str(token).strip()
                        if token and token != "Token:":
                            out = ROOT / ".runtime" / "wechatsync-token.txt"
                            out.parent.mkdir(parents=True, exist_ok=True)
                            out.write_text(token + "\n", encoding="utf-8")
                            masked = f"{token[:4]}...{token[-4:]}" if len(token) > 10 else "***"
                            print(f"TOKEN_CAPTURED len={len(token)} masked={masked} saved=.runtime/wechatsync-token.txt", flush=True)
                        else:
                            print("TOKEN_NOT_FOUND: 面板里没有读到 Token", flush=True)
                except Exception as exc:  # noqa: BLE001 - diagnostic only
                    print(f"PROBE_FAILED {candidate}: {type(exc).__name__}", flush=True)
                finally:
                    probe.close()

        end = time.time() + args.hold
        try:
            while time.time() < end:
                time.sleep(2)
        except KeyboardInterrupt:
            print("INTERRUPTED", flush=True)
        finally:
            context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
