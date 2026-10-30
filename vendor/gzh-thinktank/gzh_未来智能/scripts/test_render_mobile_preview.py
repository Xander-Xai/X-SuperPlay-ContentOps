#!/usr/bin/env python3
"""Dependency-free tests for browser DOM checks in mobile preview receipts."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from render_mobile_preview import _dom_checks  # noqa: E402


def main() -> int:
    good = _dom_checks(
        "<html><head><title>公众号测试</title></head><body>"
        + ("正文内容。" * 30)
        + '<img src="imgs/section-01.png" alt="流程" /></body></html>'
    )
    assert good["status"] == "passed"
    assert good["title_present"] is True
    assert good["image_count"] == 1
    bad = _dom_checks("<html><body><img src=\"placeholder\" /></body></html>")
    assert bad["status"] == "blocked"
    assert bad["placeholder_count"] == 1
    print("BROWSER PREVIEW TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
