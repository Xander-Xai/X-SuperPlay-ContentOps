#!/usr/bin/env python3
"""Offline tests for the WeChat draft shaping, preflight and read-back check.

Nothing here talks to WeChat: no token, no upload, no credential. What is pinned
is the part that used to live only in an operator script outside the repository —
which title, whose byline, what the digest is capped at, and what counts as proof
that a draft exists.

Run: python tests/test_wechat_draft.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.accounts import load_account  # noqa: E402
from contentops.platforms import wechat_draft  # noqa: E402

DNA = load_account(ROOT / "config" / "accounts" / "x-superplay-future-intelligence.json")

ARTICLE = {
    "title": "接管 Easel 宿主，先接管它的边界",
    "content": "<p>接管宿主不是把上游工作台直接暴露出去。</p><p>ADR-016 把宿主限定为回环、只读入口。</p>",
    "digest": "",
    "source_url": "",
}


def test_byline_comes_from_the_account_dna() -> None:
    shaped = wechat_draft.build_articles(ARTICLE, DNA, thumb_media_id="mid")
    assert shaped["article"]["author"] == DNA["account"], shaped["article"]["author"]
    assert shaped["article"]["author"] != ""


def test_long_title_is_shortened_and_the_original_is_kept() -> None:
    long_title = dict(ARTICLE, title="超" * 80)
    shaped = wechat_draft.build_articles(long_title, DNA, thumb_media_id="mid")
    assert len(shaped["article"]["title"]) <= 64, len(shaped["article"]["title"])
    assert shaped["article"]["title_original"] == "超" * 80
    assert "TITLE_TRUNCATED" in [i["code"] for i in shaped["issues"]]


def test_digest_is_derived_when_absent_and_capped() -> None:
    shaped = wechat_draft.build_articles(
        dict(ARTICLE, content="<p>" + "内容描述。" * 40 + "</p>"), DNA, thumb_media_id="mid",
    )
    digest = shaped["article"]["digest"]
    assert 0 < len(digest) <= 120, len(digest)
    assert "<" not in digest, digest  # never ship HTML tags into the summary


def test_missing_cover_blocks_before_anything_is_sent() -> None:
    shaped = wechat_draft.build_articles(ARTICLE, DNA, thumb_media_id="")
    assert shaped["state"] == "BLOCKED"
    assert "COVER_REQUIRED" in [i["code"] for i in shaped["issues"]]


def test_empty_body_blocks() -> None:
    shaped = wechat_draft.build_articles(dict(ARTICLE, content="   "), DNA, thumb_media_id="mid")
    assert shaped["state"] == "BLOCKED"
    assert "CONTENT_EMPTY" in [i["code"] for i in shaped["issues"]]


def test_ready_state_needs_a_cover_and_a_body() -> None:
    shaped = wechat_draft.build_articles(ARTICLE, DNA, thumb_media_id="mid")
    assert shaped["state"] == "READY_FOR_DRAFT"
    assert shaped["content_digest"]


def test_preflight_reports_shape_without_echoing_secrets() -> None:
    secret = "0123456789abcdef0123456789abcdef"
    result = wechat_draft.preflight({"WECHAT_1_APPID": "wx1234567890abcdef", "WECHAT_1_APPSECRET": secret})
    assert result["ok"] is True, result
    assert result["secrets_echoed"] is False
    assert secret not in json.dumps(result), "preflight echoed the secret"


def test_preflight_refuses_placeholders_and_short_values() -> None:
    assert wechat_draft.preflight({})["ok"] is False
    assert wechat_draft.preflight(
        {"WECHAT_1_APPID": "your_appid", "WECHAT_1_APPSECRET": "changeme"}
    )["ok"] is False
    assert wechat_draft.preflight(
        {"WECHAT_1_APPID": "wx1234567890abcdef", "WECHAT_1_APPSECRET": "short"}
    )["ok"] is False


def test_preflight_will_not_pretend_to_know_the_ip_whitelist() -> None:
    result = wechat_draft.preflight(
        {"WECHAT_1_APPID": "wx1234567890abcdef", "WECHAT_1_APPSECRET": "0" * 32}
    )
    assert result["ip_whitelist"] == "UNKNOWN"
    assert "40164" in result["ip_whitelist_note"]


def test_plan_uploads_the_cover_before_creating_the_draft() -> None:
    calls = [step["call"] for step in wechat_draft.plan(cover_to_upload=True)]
    assert calls == ["token", "material_add_image", "draft_add", "draft_get"], calls
    # A draft cannot reference a media id that was never uploaded, so skipping the
    # upload is only correct when the caller already has one.
    no_cover = [step["call"] for step in wechat_draft.plan(cover_to_upload=False)]
    assert "material_add_image" not in no_cover, no_cover


def test_readback_passes_when_wechat_returns_what_was_asked() -> None:
    shaped = wechat_draft.build_articles(ARTICLE, DNA, thumb_media_id="mid")
    result = wechat_draft.readback_check(shaped["article"], shaped["article"])
    assert result["ok"] is True, result["issues"]


def test_readback_detects_a_rewritten_title() -> None:
    shaped = wechat_draft.build_articles(ARTICLE, DNA, thumb_media_id="mid")
    fetched = dict(shaped["article"], title="微信改过的标题")
    result = wechat_draft.readback_check(shaped["article"], fetched)
    assert result["ok"] is False
    assert "TITLE_MISMATCH" in [i["code"] for i in result["issues"]]


def test_readback_detects_dropped_content() -> None:
    shaped = wechat_draft.build_articles(ARTICLE, DNA, thumb_media_id="mid")
    fetched = dict(shaped["article"], content="<p>只剩一段。</p>")
    result = wechat_draft.readback_check(shaped["article"], fetched)
    assert "CONTENT_MISMATCH" in [i["code"] for i in result["issues"]]


def test_formatting_only_differences_are_not_a_mismatch() -> None:
    shaped = wechat_draft.build_articles(ARTICLE, DNA, thumb_media_id="mid")
    respaced = dict(shaped["article"], content=shaped["article"]["content"].replace("><", ">\n  <"))
    assert wechat_draft.readback_check(shaped["article"], respaced)["ok"] is True


def test_readback_refuses_an_empty_response() -> None:
    shaped = wechat_draft.build_articles(ARTICLE, DNA, thumb_media_id="mid")
    assert wechat_draft.readback_check(shaped["article"], {})["ok"] is False


TESTS: List[Tuple[str, Callable[[], None]]] = [
    (name, obj) for name, obj in sorted(globals().items())
    if name.startswith("test_") and callable(obj)
]


def main() -> int:
    failures: List[Tuple[str, str]] = []
    for name, fn in TESTS:
        try:
            fn()
            print(f"[ OK ] {name}")
        except Exception as exc:  # noqa: BLE001
            failures.append((name, repr(exc)))
            print(f"[FAIL] {name}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(TESTS)} wechat draft tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
