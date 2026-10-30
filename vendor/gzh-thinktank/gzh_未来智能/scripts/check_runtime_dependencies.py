#!/usr/bin/env python3
"""Fail-fast runtime dependency preflight for the local workflow.

The gate scripts intentionally do not install packages or read credentials.
This command makes a clean environment actionable before a long article run:
install ``requirements-workflow.txt`` and then rerun the check.
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"yaml": "PyYAML", "PIL": "Pillow"}
WINDOWS_BROWSER_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
)


def check(*, require_chrome: bool = False) -> list[str]:
    errors: list[str] = []
    for module, package in REQUIRED.items():
        if importlib.util.find_spec(module) is None:
            errors.append(f"缺少 Python 依赖 {package}（请执行 python -m pip install -r requirements-workflow.txt）")
    if require_chrome and not any(shutil.which(name) for name in ("chrome", "chromium", "msedge")) and not any(path.is_file() for path in WINDOWS_BROWSER_CANDIDATES):
        errors.append("缺少 Chrome/Chromium/Edge；确定性 SVG/HTML 栅格化与 source→raster 等价检查无法执行")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-chrome", action="store_true", help="同时要求可用浏览器渲染器")
    args = parser.parse_args()
    errors = check(require_chrome=args.require_chrome)
    if errors:
        print("RUNTIME DEPENDENCIES BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("RUNTIME DEPENDENCIES PASSED: PyYAML, Pillow" + (", browser" if args.require_chrome else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
