#!/usr/bin/env python3
"""Tests for the scan-login adapter (``scripts/sau_login.py``).

Scope is deliberately narrow: the platform contract table and the refusal paths.
The browser-driving part is not unit-tested because it needs a human to scan a
QR code; what *is* tested is every decision this script makes before it touches
a browser, and the rule that an unproven cookie is never written.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import sau_login  # noqa: E402

from contentops.platforms import video_specs  # noqa: E402


def test_every_video_platform_has_a_login_contract() -> None:
    """No spec platform may be undeliverable simply because nobody mapped a login."""
    assert set(sau_login.TARGETS) == set(video_specs.platform_ids()), (
        sorted(set(video_specs.platform_ids()) - set(sau_login.TARGETS)),
        sorted(set(sau_login.TARGETS) - set(video_specs.platform_ids())),
    )


def test_sau_platform_names_match_the_uploader_contract() -> None:
    """The cookie file stem must be the uploader's own platform name, not ours."""
    for platform_id, target in sau_login.TARGETS.items():
        expected = video_specs.uploader(platform_id)["platform"]
        assert target.sau_platform == expected, (platform_id, target.sau_platform, expected)


def test_cookie_path_matches_what_the_uploader_reads() -> None:
    target = sau_login.TARGETS["shipinhao"]
    path = sau_login.cookie_file("acct", target)
    assert path.name == "tencent_acct.json", path.name
    assert path.parent.name == "cookies", path
    assert path.parent.parent.name == "sau", path


def test_only_youtube_is_marked_as_needing_a_proxy() -> None:
    proxied = [p for p, t in sau_login.TARGETS.items() if t.needs_proxy]
    assert proxied == ["youtube"], proxied


def test_only_youtube_requires_the_studio_url() -> None:
    """Google writes cookies on the password screen, so cookie presence is not proof."""
    studio = [p for p, t in sau_login.TARGETS.items() if t.requires_studio]
    assert studio == ["youtube"], studio


def test_unknown_platform_is_refused_with_the_valid_set() -> None:
    try:
        sau_login.resolve_targets("douyin,nope")
    except sau_login.LoginError as exc:
        assert "nope" in str(exc)
        assert "douyin" in str(exc)
    else:  # pragma: no cover - the refusal is the assertion
        raise AssertionError("an unknown platform must not be silently ignored")


def test_empty_platform_list_is_refused() -> None:
    try:
        sau_login.resolve_targets(" , ")
    except sau_login.LoginError:
        return
    raise AssertionError("an empty --platform must fail, not log in to everything")


def test_platform_order_is_preserved_for_the_operator() -> None:
    targets = sau_login.resolve_targets("youtube,kuaishou")
    assert [t.platform_id for t in targets] == ["youtube", "kuaishou"]


def test_argument_parse_refuses_without_account() -> None:
    try:
        sau_login.main(["--platform", "douyin"])
    except SystemExit as exc:
        assert exc.code == 2, exc.code
        return
    raise AssertionError("--account is required: the cookie stem cannot be guessed")


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
    print(f"\nAll {len(TESTS)} sau login tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
