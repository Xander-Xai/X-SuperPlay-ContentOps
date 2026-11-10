#!/usr/bin/env python3
"""Offline tests for the graphic delivery gate.

The gate exists because ``scripts/graphic_deliver.py`` used to print
``NOTE hard blockers present (仍会尝试投递)`` and deliver anyway: validation was
a log line, not a precondition. These tests pin the decision at the point where
it is cheap to check — before a browser session exists.

Run: python tests/test_delivery_gate.py
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

from contentops.platforms import delivery_gate  # noqa: E402


def test_gate_refuses_hard_blockers_instead_of_delivering_anyway() -> None:
    decision = delivery_gate.authorize_delivery("csdn", blockers=["TITLE_OVER_HARD_LIMIT"])
    assert decision.outcome == delivery_gate.REFUSED, decision.to_dict()
    assert "HARD_BLOCKERS" in decision.reasons[0]


def test_gate_allows_the_draft_boundary_on_a_declared_channel() -> None:
    decision = delivery_gate.authorize_delivery("csdn")
    assert decision.outcome == delivery_gate.DRAFT_ONLY, decision.to_dict()
    assert decision.channel == "wechatsync:csdn"


def test_gate_refuses_anything_that_is_not_a_draft() -> None:
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
