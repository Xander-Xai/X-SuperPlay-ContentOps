#!/usr/bin/env python3
"""Run the installed Huashu Art Motion renderer with a narrow Windows fix.

Chromium asks for /favicon.ico even though the upstream clip page has no icon.
The upstream renderer treats that browser-only 404 as a page error and exits 1
after writing a valid video. This wrapper answers only that exact request with
204 No Content. Every other 404 and page error keeps the upstream failure path.
"""
from __future__ import annotations

import http.server
import os
import runpy
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
for base in (ROOT / "src", ROOT / "scripts"):
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
from process_utils import hidden_run, python_executable  # noqa: E402
from contentops.media.huashu_runtime import find_runtime  # noqa: E402


def is_favicon_request(path: str) -> bool:
    """Match Chromium's exact root favicon request, including query strings."""
    return urlsplit(path).path == "/favicon.ico"


def exit_code_from_system_exit(code) -> int:
    """Preserve upstream textual render errors as failures, without a cast crash."""
    return code if isinstance(code, int) and not isinstance(code, bool) else (0 if code is None else 1)


class Favicon204Handler(http.server.SimpleHTTPRequestHandler):
    """Serve no icon without turning the browser's optional request into error."""

    def send_error(self, code, message=None, explain=None):
        if code == 404 and is_favicon_request(self.path):
            self.send_response(204, "No Content")
            self.end_headers()
            return
        return super().send_error(code, message, explain)


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    if os.environ.get("CONTENTOPS_HUASHU_RENDER_CHILD") != "1":
        child_env = dict(os.environ)
        child_env["CONTENTOPS_HUASHU_RENDER_CHILD"] = "1"
        child_env["PYTHONUTF8"] = "1"
        child_env["PYTHONIOENCODING"] = "utf-8"
        proc = hidden_run(
            [python_executable(), str(Path(__file__).resolve()), *arguments],
            timeout=3600,
            env=child_env,
        )
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        return int(proc.returncode)

    try:
        skill_root = find_runtime(ROOT)
    except FileNotFoundError as exc:
        print(f"Huashu Art Motion runtime not found: {exc}", file=sys.stderr)
        return 2
    engine = skill_root / "scripts" / "engine" / "render.py"
    if not engine.is_file():
        print(f"Huashu Art Motion renderer not found: {engine}", file=sys.stderr)
        return 2

    # The installed renderer creates Q as a subclass of this stdlib handler.
    # Patching the handler class only in this child process leaves the shared
    # Skill installation untouched and does not mask non-favicon errors.
    http.server.SimpleHTTPRequestHandler = Favicon204Handler
    sys.argv = [str(engine), *arguments]
    try:
        runpy.run_path(str(engine), run_name="__main__")
    except SystemExit as exc:
        if not isinstance(exc.code, (int, type(None))):
            print(str(exc.code), file=sys.stderr)
        return exit_code_from_system_exit(exc.code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
