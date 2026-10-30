#!/usr/bin/env python3
"""Unit-test the deterministic portion of draft readback verification."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from article_integrity import canonical_html_digest  # noqa: E402
from verify_draft_submission import analyze_readback  # noqa: E402


def main() -> int:
    meta = {"title": "测试标题", "author": "X超玩•未来智能", "digest": "测试摘要"}
    item = {
        "title": "测试标题",
        "author": "X超玩•未来智能",
        "digest": "测试摘要",
        "thumb_media_id": "thumb-test",
        "content": '<p><span leaf="">正文</span></p><img src="https://example.com/a.png" />',
    }
    result = analyze_readback(meta, item, True)
    assert result["title_matches"] is True
    assert result["author_matches"] is True
    assert result["digest_matches"] is True
    assert result["image_count"] == 1
    assert result["content_has_div"] is False
    assert result["html_validator"] == "passed"

    local_html = (
        '<p><span leaf="">正文</span></p>'
        '<img src="imgs/section-01.png" alt="流程" style="display:block;" />'
    )
    wechat_html = (
        '<p><span leaf="">正文</span></p>'
        '<img alt="流程" data-src="https://mmbiz.qpic.cn/demo/640" '
        'style="display:block;">'
    )
    assert canonical_html_digest(local_html) == canonical_html_digest(wechat_html)
    print("DRAFT VERIFICATION TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
