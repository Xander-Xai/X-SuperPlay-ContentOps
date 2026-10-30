#!/usr/bin/env python3
"""Regression tests for the public article leakage guard."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from article_integrity import public_content_findings  # noqa: E402


def main() -> int:
    unsafe = '请把凭证放在 D:\\Projects\\private\\aws.env，并设置 WECHAT_1_APPSECRET。'
    findings = public_content_findings(unsafe)
    assert {item["rule"] for item in findings} == {"local-path", "credential-file", "wechat-secret-key"}
    safe = "请通过外部环境变量注入凭证，文章正文只保留脱敏后的通用命令。"
    assert public_content_findings(safe) == []
    print("PUBLIC CONTENT SAFETY TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
