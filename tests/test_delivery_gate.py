#!/usr/bin/env python3
"""Offline tests for the graphic delivery gate.

The gate exists because ``scripts/graphic_deliver.py`` used to print
``NOTE hard blockers present (仍会尝试投递)`` and deliver anyway: validation was
a log line, not a precondition. These tests pin the decision at the point where
it is cheap to check — before a browser session exists.

Run: python tests/test_delivery_gate.py
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
from argparse import Namespace
from pathlib import Path
from typing import Callable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.graphic import GraphicPackageError  # noqa: E402
from contentops.platforms import delivery_gate, multichannel  # noqa: E402
import graphic_deliver  # noqa: E402
import platform_delivery  # noqa: E402


def test_cover_verification_refuses_bytes_changed_after_package_preflight() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        cover_path = project / "assets" / "cover.png"
        cover_path.parent.mkdir()
        cover_path.write_bytes(b"reviewed-cover-bytes")
        image = {
            "path": "assets/cover.png",
            "sha256": hashlib.sha256(b"reviewed-cover-bytes").hexdigest(),
            "scope": "project",
        }
        package = {"images": [image]}
        cover = graphic_deliver._resolve_cover(package, project)
        assert cover == cover_path.resolve()

        cover_path.write_bytes(b"different-cover-bytes")
        try:
            graphic_deliver._verify_cover_current(package, cover, project)
        except GraphicPackageError as exc:
            assert exc.code == "COVER_ASSET_CHANGED"
        else:
            raise AssertionError("cover changes after verification must be refused")


def test_cover_resolution_refuses_symlink_escape():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project = root / "project"
        project.mkdir()
        outside = root / "outside.png"
        outside.write_bytes(b"outside")
        link = project / "cover.png"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            return
        package = {"images": [{"path": "cover.png", "sha256": "x", "scope": "project"}]}
        try:
            graphic_deliver._resolve_cover(package, project)
        except GraphicPackageError as exc:
            assert exc.code == "COVER_PATH_INVALID"
        else:
            raise AssertionError("cover symlink leaving the project must be refused")


def test_legacy_dispatch_refuses_without_starting_external_cli() -> None:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = platform_delivery.cmd_dispatch(Namespace())
    payload = json.loads(output.getvalue())
    assert code == 1
    assert payload["status"] == "blocked"
    assert payload["network_called"] is False
    assert "GUARDED_GRAPHIC_DELIVER_REQUIRED" in payload["reason"]


def test_adapter_propagates_package_blockers_to_every_platform_draft() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "draft.md").write_text("# A title\n\nA test draft.\n", encoding="utf-8")
        package = {
            "schema": "contentops.graphic-package/v1",
            "bundle_sha256": "a" * 64,
            "bundle_id": "CB-1",
            "title": "A title",
            "draft": {"path": "draft.md"},
            "images": [],
            "blockers": ["PLATFORM_PLACEHOLDER"],
            "status": "AWAITING_MANUAL_REVIEW",
            "human_review": "NOT_STARTED",
            "publish_authorized": False,
        }
        package["_package_root"] = str(root)
        draft = multichannel.MultiChannelAdapter("wechat_article").pack(
            package, {"account_slug": "test"})

        assert "PLATFORM_PLACEHOLDER" in draft.blockers


def test_delivery_decision_includes_structural_validation_errors():
    decision = delivery_gate.authorize_adapted_draft(
        "wechat_article", package_blockers=[], draft_blockers=[],
        validation_errors=["ABSOLUTE_HOST_PATH_IN_DRAFT"])
    assert decision.outcome == delivery_gate.REFUSED
    assert "VALIDATION_FAILED" in decision.reasons[0]


def test_gate_refuses_hard_blockers_instead_of_delivering_anyway() -> None:
    decision = delivery_gate.authorize_delivery("csdn", blockers=["TITLE_OVER_HARD_LIMIT"])
    assert decision.outcome == delivery_gate.REFUSED, decision.to_dict()
    assert "HARD_BLOCKERS" in decision.reasons[0]


def test_gate_allows_the_draft_boundary_on_a_declared_channel() -> None:
    decision = delivery_gate.authorize_delivery("csdn")
    assert decision.outcome == delivery_gate.DRAFT_ONLY, decision.to_dict()
    assert decision.channel == "wechatsync:csdn"


def test_gate_refuses_a_different_declared_draft_channel() -> None:
    decision = delivery_gate.authorize_delivery("csdn", channel_id="wechatsync:zhihu")
    assert decision.outcome == delivery_gate.REFUSED
    assert "NO_DRAFT_CHANNEL" in decision.reasons[0]


def test_adapted_gate_preserves_the_requested_channel() -> None:
    decision = delivery_gate.authorize_adapted_draft("csdn", channel_id="wechatsync:csdn")
    assert decision.outcome == delivery_gate.DRAFT_ONLY
    assert decision.channel == "wechatsync:csdn"


    decision = delivery_gate.authorize_delivery("wechat_article", mode="mass_send")
    assert decision.outcome == delivery_gate.REFUSED
    assert "MODE_NOT_AUTHORIZED" in decision.reasons[0]


def test_gate_refuses_douyin_even_with_a_clean_draft() -> None:
    """Douyin is not a graphic platform at all; the policy reason must still win.

    Reporting UNKNOWN_PLATFORM here would invite someone to "fix" it by adding a
    spec row, which is the opposite of the intent.
    """
    decision = delivery_gate.authorize_delivery("douyin")
    assert decision.outcome == delivery_gate.REFUSED
    assert "DOUYIN" in decision.reasons[0], decision.reasons


def test_gate_refuses_unknown_platform() -> None:
    assert delivery_gate.authorize_delivery("myspace").outcome == delivery_gate.REFUSED


def test_gate_refuses_a_draft_that_authorises_itself() -> None:
    decision = delivery_gate.authorize_delivery("zhihu", publish_authorized_claim=True)
    assert decision.outcome == delivery_gate.REFUSED
    assert "AUTHORIZATION" in decision.reasons[0]


def test_gate_decision_serialises_for_a_receipt() -> None:
    payload = delivery_gate.authorize_delivery("zhihu").to_dict()
    assert json.loads(json.dumps(payload))["outcome"] == delivery_gate.DRAFT_ONLY


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
    print(f"\nAll {len(TESTS)} delivery gate tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
