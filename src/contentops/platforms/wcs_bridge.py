"""Reusable Wechatsync bridge bootstrap.

Split out of ``wechatsync_bridge_run.py`` so that a single browser session can
serve many CLI invocations (that is what ``graphic_deliver.py`` needs: boot once,
deliver to seven platforms, close once).

The bridge is a two-sided thing and both sides must be alive at the same time:

  * the CLI is a WebSocket **server** on 127.0.0.1:9527
  * the extension inside the browser is the **client**

So "打通" is not a configuration value, it is a process lifetime. That is why
every earlier attempt reported ``EXTENSION_NOT_CONNECTED``: the browser had been
closed before the CLI ran, or the bridge switch was off, or the CLI had no token
to match the extension's.

Nothing here logs in to any platform, types a password, or reads a platform
credential. The token it copies is the local shared secret between this CLI and
this extension.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[3]
_scripts = str(ROOT / "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from process_utils import hidden_run  # noqa: E402
EXT_DIR = ROOT / ".runtime" / "wechatsync-ext"
PROFILE_DIR = ROOT / ".runtime" / "wechatsync-browser"
TOKEN_FILE = ROOT / ".runtime" / "wechatsync-token.txt"
CLI_DIR = ROOT / ".runtime" / "multichannel-tools"
CLI_ENTRY = CLI_DIR / "node_modules" / "@wechatsync" / "cli" / "dist" / "index.js"
OUT_DIR = CLI_DIR / "out"

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

SETTINGS_JS = """(() => {
  const b=[...document.querySelectorAll('button')].find(e=>/设置|Settings/.test(e.innerText||''));
  if(!b) return false; b.click(); return true;
})()"""

SWITCH_JS_FIND = """(() => {
  const rows=[...document.querySelectorAll('*')].filter(e=>(e.innerText||'').trim()==='CLI / MCP 连接');
  if(!rows.length) return null;
  let node=rows[0];
  for(let i=0;i<5 && node.parentElement;i++){
    node=node.parentElement;
    const sw=node.querySelector('button,[role=switch],input[type=checkbox],.switch,.toggle');
    if(sw) return {cls:String(sw.className).slice(0,80)};
  }
  return null;
})()"""

SWITCH_JS_CLICK = """(() => {
  const rows=[...document.querySelectorAll('*')].filter(e=>(e.innerText||'').trim()==='CLI / MCP 连接');
  if(!rows.length) return false;
  let node=rows[0];
  for(let i=0;i<5 && node.parentElement;i++){
    node=node.parentElement;
    const sw=node.querySelector('button,[role=switch],input[type=checkbox],.switch,.toggle');
    if(sw){ sw.click(); return true; }
  }
  return false;
})()"""


class BridgeError(RuntimeError):
    """The bridge could not be brought up."""


def _log(message: str) -> None:
    print(message, flush=True)


def extension_id(context) -> str:
    deadline = time.time() + 30
    while time.time() < deadline:
        workers = [w for w in context.service_workers if "chrome-extension://" in w.url]
        if workers:
            return workers[0].url.split("/")[2]
        time.sleep(0.5)
    raise BridgeError("扩展 service worker 未出现：Chromium 可能拒绝加载未打包扩展")


def read_token(page) -> str:
    """Open the extension's settings panel and return the bridge token."""
    page.wait_for_timeout(1200)
    if page.evaluate(SETTINGS_JS):
        page.wait_for_timeout(1400)
    panel = page.evaluate("document.body ? document.body.innerText : ''") or ""

    switch = page.evaluate(SWITCH_JS_FIND)
    if switch and "未启用" in panel:
        page.evaluate(SWITCH_JS_CLICK)
        page.wait_for_timeout(2200)
        panel = page.evaluate("document.body ? document.body.innerText : ''") or ""
        _log("BRIDGE_SWITCH CLICKED")
    elif switch:
        _log("BRIDGE_SWITCH ALREADY_ON")
    else:
        _log("BRIDGE_SWITCH NOT_FOUND")

    match = UUID_RE.search(panel)
    if match:
        token = match.group(0)
    elif TOKEN_FILE.is_file():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        _log("TOKEN from cache")
    else:
        token = ""

    if token:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
        _log(f"TOKEN {token[:4]}...{token[-4:]}")
    else:
        _log("TOKEN NOT FOUND")

    if "等待连接" in panel:
        _log("BRIDGE_STATE waiting_for_connection")
    elif "已启用" in panel:
        _log("BRIDGE_STATE enabled")
    return token


@contextlib.contextmanager
def bridge_session(pw, *, open_url: str = "about:blank", viewport=(1440, 900)) -> Iterator[dict]:
    """Boot a browser with the extension, yield ``{"token", "ext_id", "context"}``."""
    if not (EXT_DIR / "manifest.json").is_file():
        raise BridgeError(f"扩展未解压到 {EXT_DIR}")
    if not CLI_ENTRY.is_file():
        raise BridgeError(f"CLI 未安装：{CLI_ENTRY}")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        args=[
            f"--disable-extensions-except={EXT_DIR}",
            f"--load-extension={EXT_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        viewport={"width": viewport[0], "height": viewport[1]},
    )
    try:
        ext_id = extension_id(context)
        _log(f"EXTENSION id={ext_id}")
        page = context.pages[0] if context.pages else context.new_page()
        if open_url and open_url != "about:blank":
            try:
                page.goto(open_url, timeout=30_000)
                _log(f"OPENED {open_url}")
            except Exception as exc:  # noqa: BLE001 - the page is only a convenience
                _log(f"OPEN_FAILED {type(exc).__name__}")
        panel = context.new_page()
        panel.goto(f"chrome-extension://{ext_id}/src/popup/index.html", timeout=20_000)
        token = read_token(panel)
        yield {"token": token, "ext_id": ext_id, "context": context}
    finally:
        context.close()


def run_cli(args: list[str], *, timeout_ms: int = 45_000, token: str = "") -> dict:
    """Invoke the CLI with the bridge token in its environment."""
    env = dict(os.environ)
    if token:
        env["WECHATSYNC_TOKEN"] = token
    cmd = ["node", str(CLI_ENTRY), "--timeout", str(timeout_ms), *args]
    try:
        proc = hidden_run(
            cmd, cwd=str(CLI_DIR), capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, input="N\n",
            timeout=timeout_ms / 1000 + 40,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "bridge_connected": "Chrome Extension 已连接" in (proc.stderr or "") + (proc.stdout or ""),
        }
    except subprocess.TimeoutExpired:
        return {"returncode": 124, "stdout": "", "stderr": "CLI_TIMEOUT", "bridge_connected": False}


def parse_sync_result(stdout: str) -> dict:
    """Extract per-platform outcome from ``wechatsync sync`` output.

    Deliberately conservative: a URL is only reported when the line carries one,
    and success is only reported when the CLI itself printed ✓ for that platform.
    """
    result = {"ok": False, "url": "", "platform_line": "", "reason": "", "summary": ""}
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("✓"):
            result["ok"] = True
            result["platform_line"] = stripped
        elif stripped.startswith("✗"):
            result["platform_line"] = stripped
        elif stripped.startswith("http") and result["ok"]:
            result["url"] = stripped
        elif stripped.startswith("同步完成"):
            result["summary"] = stripped
        elif result["platform_line"] and not result["ok"] and stripped and not stripped.startswith("http"):
            # The line right after ✗ is the failure reason.
            if not result["reason"] and "同步完成" not in stripped:
                result["reason"] = stripped
    return result
