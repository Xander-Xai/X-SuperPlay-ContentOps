#!/usr/bin/env python3
"""Ensure diagnostics never print access-token prefixes."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    source = (ROOT / "skills" / "gzh-draft-publisher" / "scripts" / "publish.py").read_text(
        encoding="utf-8"
    )
    forbidden = ("token: {tok[:", "token: {token[:")
    assert not any(marker in source for marker in forbidden), "publish.py 仍可能把 token 前缀写入日志"
    assert "令牌不会写入日志" in source
    print("PUBLISH TOKEN REDACTION TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
