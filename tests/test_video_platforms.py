#!/usr/bin/env python3
"""Offline tests for the VIDEO delivery line and the graphic delivery gate.

Nothing here touches the network, ffmpeg, a browser or an uploader. The point is
that shaping rules, blockers and authorization answers are decisions made in
code, so they can be asserted instead of eyeballed in a browser form.

Run: python tests/test_video_platforms.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Callable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.accounts import load_account  # noqa: E402
from contentops.platforms import video_delivery  # noqa: E402
from contentops.platforms import video_package  # noqa: E402
from contentops.platforms import video_specs  # noqa: E402

ACCOUNT_1024 = ROOT / "config" / "accounts" / "x-superplay-1024.json"
ACCOUNT_FI = ROOT / "config" / "accounts" / "x-superplay-future-intelligence.json"

DNA_1024 = load_account(ACCOUNT_1024)
DNA_FI = load_account(ACCOUNT_FI)

MEDIA = {
    "duration_s": 65.91,
    "width": 1080,
    "height": 1920,
    "size_bytes": 4_700_000,
    "sha256": "0" * 64,
}


# ---------------------------------------------------------------- spec table


def test_six_video_platforms_and_registry_link() -> None:
    assert video_specs.platform_ids() == (
        "douyin", "shipinhao", "xiaohongshu_video", "bilibili", "kuaishou", "youtube",
    ), video_specs.platform_ids()
    assert video_specs.platform_ids(registry_rows_only=True) == (
        "douyin", "shipinhao", "xiaohongshu_video", "bilibili", "youtube",
    )
    assert video_specs.is_registry_row("kuaishou") is False


def test_every_limit_carries_a_basis() -> None:
    """A number without provenance is a guess wearing a spec's clothes."""
    pairs = {
        "title_max_hard": "title_max_hard_basis",
        "title_max_soft": "title_max_soft_basis",
        "desc_max_hard": "desc_max_hard_basis",
        "max_duration_s": "max_duration_basis",
        "max_file_mb": "max_file_mb_basis",
        "tags_max": "tags_basis",
        "tag_style": "tag_style_basis",
        "aspect_required": "aspect_basis",
        "hook_max_s": "hook_basis",
    }
    for pid in video_specs.platform_ids():
        row = video_specs.spec(pid)
        for value_key, basis_key in pairs.items():
            if value_key in row:
                assert row.get(basis_key), f"{pid}.{value_key} 缺少 {basis_key}"
        assert row.get("note"), f"{pid} 没有说明自己为什么这么写"


def test_tag_rendering_matches_each_uploader() -> None:
    """The pinned uploader splits --tags on ',' and strips a leading '#'.

    A space-separated '#a #b' string therefore arrives as ONE tag named 'a #b',
    which is why every row uses the comma form for the argv and keeps the '#'
    form only for the human to paste into the app.
    """
    assert video_specs.tag_tokens("douyin", ["#AI实测", "开源项目"]) == "AI实测,开源项目"
    assert video_specs.tag_tokens("bilibili", ["#AI实测", "开源项目"]) == "AI实测,开源项目"
    assert video_specs.tag_tokens("youtube", ["a", "a", " b "]) == "a,b"
    assert video_specs.tag_display("douyin", ["#AI实测", "开源项目"]) == "#AI实测 #开源项目"


# ------------------------------------------------------------------ checks


def test_hard_limit_is_a_blocker_and_soft_limit_is_a_warning() -> None:
    hard = video_specs.check(
        "xiaohongshu_video", title="超" * 25, desc="d", tags=["a", "b", "c"], aspect="9:16",
    )
    assert [i["code"] for i in hard] == ["TITLE_OVER_HARD_LIMIT"], hard
    assert hard[0]["severity"] == video_specs.ISSUE_BLOCKER

    soft = video_specs.check(
        "douyin", title="正" * 40, desc="d", tags=["a", "b", "c"], aspect="9:16",
    )
    codes = {i["code"]: i["severity"] for i in soft}
    assert codes["TITLE_OVER_SOFT_LIMIT"] == video_specs.ISSUE_WARNING, codes


def test_horizontal_cut_is_refused_not_silently_accepted() -> None:
    issues = video_specs.check(
        "bilibili", title="t", desc="d", tags=["a", "b", "c"], aspect="16:9",
    )
    assert "ASPECT_MISMATCH" in [i["code"] for i in issues], issues
    assert all(i["severity"] == video_specs.ISSUE_BLOCKER for i in issues)


def test_required_uploader_argument_blocks_instead_of_defaulting() -> None:
    without = video_specs.check(
        "bilibili", title="t", desc="d", tags=["a", "b", "c"], aspect="9:16",
    )
    assert "REQUIRED_ARG_MISSING" in [i["code"] for i in without]
    with_tid = video_specs.check(
        "bilibili", title="t", desc="d", tags=["a", "b", "c"], aspect="9:16",
        supplied_args={"category": "231"},
    )
    assert "REQUIRED_ARG_MISSING" not in [i["code"] for i in with_tid]


def test_hook_deadline_is_measured_not_assumed() -> None:
    late = video_specs.check(
        "douyin", title="t", desc="d", tags=["a", "b", "c"], aspect="9:16", hook_s=9.0,
    )
    assert "HOOK_MISSES_DEADLINE" in [i["code"] for i in late]
    early = video_specs.check(
        "douyin", title="t", desc="d", tags=["a", "b", "c"], aspect="9:16", hook_s=2.5,
    )
    assert "HOOK_MISSES_DEADLINE" not in [i["code"] for i in early]


# ----------------------------------------------------------------- packaging


def test_account_dna_decides_which_platforms_are_packaged() -> None:
    # 2026-11-11: the operator put kuaishou on the same Chinese video line as
    # douyin/xiaohongshu, so the DNA now declares five VIDEO targets. The order
    # is DNA order -- primary ``platforms`` first, then ``derived_platforms``.
    assert video_package.targets(DNA_1024) == [
        "douyin", "xiaohongshu_video", "kuaishou", "bilibili", "shipinhao",
    ], video_package.targets(DNA_1024)


def test_other_account_gets_its_own_platform_set() -> None:
    assert video_package.targets(DNA_FI) == ["bilibili", "douyin", "shipinhao"]


def test_text_platforms_never_leak_into_a_video_package() -> None:
    package = video_package.build(project_id="p", account=DNA_1024, media=MEDIA)
    ids = [e["platform_id"] for e in package["platforms"]]
    assert "gzh" not in ids and "zhihu" not in ids, ids


def test_title_shortening_keeps_the_original() -> None:
    entry = video_package.shape_metadata("xiaohongshu_video", DNA_1024)
    assert len(entry["title"]) <= 20, entry["title"]
    assert entry["title_original"] == DNA_1024["title"]
    assert "TITLE_TRUNCATED" in [i["code"] for i in entry["issues"]]


def test_cta_from_platform_role_is_appended_once() -> None:
    role_cta = DNA_1024["platform_roles"]["douyin"]["cta"]
    entry = video_package.shape_metadata("douyin", DNA_1024)
    assert role_cta in entry["desc"], entry["desc"]
    assert entry["desc"].count(role_cta) == 1


def test_package_state_is_blocked_when_any_platform_blocks() -> None:
    package = video_package.build(
        project_id="p", account=DNA_1024, media=MEDIA,
        platforms=["douyin", "bilibili"],
        supplied_args={"category": "231"},
    )
    states = {e["platform_id"]: e["state"] for e in package["platforms"]}
    assert states["douyin"] == video_package.STATE_BLOCKED, states  # 3:4 thumbnail missing
    assert states["bilibili"] == video_package.STATE_READY, states
    assert package["state"] == video_package.STATE_BLOCKED
    assert package["publish_authorized"] is False
    assert package["production_ready"] is False


def test_package_never_claims_authorization_even_when_clean() -> None:
    package = video_package.build(
        project_id="p", account=DNA_1024, media=MEDIA,
        platforms=["xiaohongshu_video"], thumbnails={"3:4": "x.png"},
    )
    assert package["state"] == video_package.STATE_READY, package["blockers"]
    assert package["publish_authorized"] is False
    assert package["production_ready"] is False


def test_no_video_platform_declared_is_a_recorded_blocker() -> None:
    package = video_package.build(project_id="p", account={"slug": "empty"}, media=MEDIA)
    assert package["state"] == video_package.STATE_BLOCKED
    assert "NO_VIDEO_PLATFORM_DECLARED" in package["blockers"][0]


# ------------------------------------------------------------------- argv


def test_douyin_argv_carries_the_three_thumbnail_flags() -> None:
    argv = video_delivery.build_command(
        "douyin", executable="sau", account="acct", video="v.mp4",
        metadata={"title": "t", "desc": "d", "tags_rendered": "#a #b"},
        thumbnails={"3:4": "p.png", "4:3": "l.png"},
    )
    assert argv[:3] == ["sau", "douyin", "upload-video"], argv
    assert argv.count("--thumbnail") == 1, argv
    assert "--thumbnail-landscape" in argv
    assert "--thumbnail-portrait" in argv
    assert "l.png" in argv


def test_bilibili_argv_includes_the_category_only_when_supplied() -> None:
    base = dict(executable="sau", account="a", video="v.mp4",
                metadata={"title": "t", "desc": "d", "tags_rendered": "a,b"})
    without = video_delivery.build_command("bilibili", **base)
    assert "--tid" not in without, without
    with_tid = video_delivery.build_command("bilibili", supplied_args={"category": "231"}, **base)
    assert with_tid[with_tid.index("--tid") + 1] == "231"


def test_argv_is_a_list_so_a_hashtag_cannot_become_a_comment() -> None:
    argv = video_delivery.build_command(
        "xiaohongshu_video", executable="sau", account="a", video="v.mp4",
        metadata={"title": "t", "desc": "d", "tags_rendered": "#a #b"},
    )
    assert isinstance(argv, list)
    assert all(isinstance(item, str) for item in argv)


def test_headed_flag_is_reachable_without_a_headless_shell() -> None:
    base = dict(executable="sau", account="a", video="v.mp4",
                metadata={"title": "t", "desc": "d", "tags_rendered": "a,b"})
    assert "--headed" not in video_delivery.build_command("douyin", **base)
    assert video_delivery.build_command("douyin", headed=True, **base)[-1] == "--headed"


# -------------------------------------------------------------- authorization


def test_package_only_without_an_execution_request() -> None:
    decision = video_delivery.authorize("douyin", package_state="READY_FOR_HANDOFF")
    assert decision.outcome == video_delivery.PACKAGE_ONLY, decision.outcome
    assert decision.allowed and not decision.executable


def test_blocked_package_is_refused_before_any_grant_is_considered() -> None:
    decision = video_delivery.authorize(
        "bilibili", package_state="BLOCKED", execute_requested=True,
        grant={"platforms": {"bilibili": {"execute": True}}}, cookie_ready=True,
    )
    assert decision.outcome == video_delivery.REFUSED
    assert "PACKAGE_BLOCKED" in decision.reasons[0]


def test_execute_needs_a_grant() -> None:
    decision = video_delivery.authorize(
        "bilibili", package_state="READY_FOR_HANDOFF", execute_requested=True,
        grant={}, cookie_ready=True,
    )
    assert decision.outcome == video_delivery.REFUSED
    assert "NO_EXECUTION_GRANT" in " ".join(decision.reasons)


def test_douyin_needs_a_policy_acknowledgement_on_top_of_the_grant() -> None:
    grant = {"platforms": {"douyin": {"execute": True}}}
    refused = video_delivery.authorize(
        "douyin", package_state="READY_FOR_HANDOFF", execute_requested=True,
        grant=grant, cookie_ready=True,
    )
    assert refused.outcome == video_delivery.REFUSED
    assert "POLICY_ACK_MISSING" in " ".join(refused.reasons)

    grant["platforms"]["douyin"]["douyin_policy_ack"] = True
    allowed = video_delivery.authorize(
        "douyin", package_state="READY_FOR_HANDOFF", execute_requested=True,
        grant=grant, cookie_ready=True,
    )
    assert allowed.outcome == video_delivery.ELIGIBLE, allowed.reasons


def test_missing_login_is_refused_with_the_expected_path() -> None:
    decision = video_delivery.authorize(
        "bilibili", package_state="READY_FOR_HANDOFF", execute_requested=True,
        grant={"platforms": {"bilibili": {"execute": True}}},
        cookie_ready=False, cookie_expected="cookies/bilibili_acct.json",
    )
    assert decision.outcome == video_delivery.REFUSED
    assert "cookies/bilibili_acct.json" in " ".join(decision.required_conditions)


def test_package_may_not_assert_its_own_authorization() -> None:
    decision = video_delivery.authorize(
        "bilibili", package_state="READY_FOR_HANDOFF", publish_authorized_claim=True,
        execute_requested=True, grant={"platforms": {"bilibili": {"execute": True}}},
    )
    assert decision.outcome == video_delivery.REFUSED
    assert "PACKAGE_ASSERTS_AUTHORIZATION" in decision.reasons[0]


def test_cookie_glob_resolves_to_a_platform_specific_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = video_delivery.cookie_path(root, "xiaohongshu_video", "acct1")
        assert path == root / "cookies" / "xiaohongshu_acct1.json", path
        assert video_delivery.cookie_present(root, "xiaohongshu_video", "acct1")[0] is False


# ------------------------------------------------- category + published URL


def test_category_precedence_is_most_specific_first() -> None:
    """A category id files the work under a section; guessing is worse than blocking."""
    assert video_delivery.resolve_category(
        "bilibili", cli_value="231", project_value="17", dna_value="9",
    ) == ("231", "cli")
    assert video_delivery.resolve_category(
        "bilibili", project_value="17", dna_value="9",
    ) == ("17", "project.yaml")
    assert video_delivery.resolve_category("bilibili", dna_value="9") == ("9", "account_dna")
    assert video_delivery.resolve_category("bilibili") == ("", "unresolved")


def test_published_url_must_belong_to_the_platform() -> None:
    bad = video_delivery.record_publication("bilibili", "https://example.com/v/1")
    assert bad["accepted"] is False
    assert "URL_HOST_MISMATCH" in bad["reasons"][0]

    good = video_delivery.record_publication("bilibili", "https://www.bilibili.com/video/BV1xx")
    assert good["accepted"] is True
    assert good["state"] == video_delivery.URL_RECORDED
    assert good["host"] == "www.bilibili.com"


def test_published_url_must_be_absolute() -> None:
    assert video_delivery.record_publication("douyin", "final/out.mp4")["accepted"] is False


def test_metrics_are_kept_only_as_numbers_and_labelled_as_manual() -> None:
    receipt = video_delivery.record_publication(
        "youtube", "https://youtu.be/abc123", metrics={"views": 12, "note": "x", "liked": True},
    )
    assert receipt["accepted"] is True
    assert receipt["metrics"] == {"views": 12}, receipt["metrics"]
    assert "人工" in receipt["metrics_note"]
    assert receipt["state"] != "PUBLISHED"


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
    print(f"\nAll {len(TESTS)} video platform tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
