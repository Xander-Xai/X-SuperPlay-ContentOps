"""Who owns the evidence policy: the account, or the episode?

The probe that started this carried ``evidence_mode: EXPLANATORY`` in
``lines.json`` and ``real_source_ratio_min_70`` in the account DNA at the same
time, and the two gates read different documents. Each declaration was fine on
its own; together they described a film that could never satisfy the floor it
was measured against.

Ownership is the answer: the account decides whether a film is proven or
explained, the episode decides its mix, and the mix has to satisfy the mode.
These tests pin that split.

Run: python tests/test_account_evidence_policy.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from audio_first_plan import _account_policy  # noqa: E402
from contentops.media.claim_coverage import (  # noqa: E402
    REAL_COMPOSITION_ROLES,
    composition_policy_errors,
)

PROOF = "x-superplay-1024"
EXPLAIN = "x-superplay-future-intelligence"


def _blocked(call) -> dict:
    """The JSON block a refused call raises, or a failure if it did not refuse."""
    try:
        result = call()
    except SystemExit as exc:
        assert isinstance(exc.code, str), f"expected a JSON block, got {exc.code!r}"
        return json.loads(exc.code)
    raise AssertionError(f"expected the call to block, got {result!r}")


# --- the composition rule -------------------------------------------------


def test_vector_animation_is_not_a_real_composition_role():
    assert "vector_animation" not in REAL_COMPOSITION_ROLES
    assert "screen_recording_evidence" in REAL_COMPOSITION_ROLES


def test_a_vector_led_mix_cannot_reach_the_proof_floor():
    """The exact pair the probe shipped: 70% animation against a 70% floor."""
    problems = composition_policy_errors("EVIDENCE_LED", [
        {"role": "vector_animation", "pct": 70},
        {"role": "code_snapshot", "pct": 25},
        {"role": "metric_chart", "pct": 5},
    ])
    assert any("tops out at 30%" in problem for problem in problems), problems


def test_the_explanatory_mode_accepts_the_mix_the_proof_mode_refuses():
    mix = [{"role": "vector_animation", "pct": 100}]
    assert composition_policy_errors("EXPLANATORY", mix) == []
    assert composition_policy_errors("EVIDENCE_LED", mix)


def test_the_explanatory_mode_refuses_a_recording_segment():
    problems = composition_policy_errors("EXPLANATORY", [
        {"role": "screen_recording_evidence", "pct": 60},
        {"role": "vector_animation", "pct": 40},
    ])
    assert any("screen_recording_evidence" in problem for problem in problems), problems


def test_a_mix_that_does_not_sum_to_one_hundred_is_refused():
    problems = composition_policy_errors("EXPLANATORY", [
        {"role": "vector_animation", "pct": 90},
    ])
    assert any("sums to 90" in problem for problem in problems), problems


def test_an_unknown_mode_is_refused_rather_than_defaulted():
    try:
        composition_policy_errors("PROBABLY_FINE", [{"role": "vector_animation", "pct": 100}])
    except ValueError:
        return
    raise AssertionError("an unknown mode must raise, not fall through to a default")


# --- the plan's resolution of the two fields ------------------------------


def test_the_account_owns_the_mode_and_the_episode_inherits_it():
    explained = _account_policy({"account_slug": EXPLAIN}, {})
    assert explained["evidence_mode"] == "EXPLANATORY"
    assert explained["manual_recording"] == "FORBIDDEN"
    assert sum(segment["pct"] for segment in explained["composition"]) == 100

    proven = _account_policy({"account_slug": PROOF}, {})
    assert proven["evidence_mode"] == "EVIDENCE_LED"
    assert proven["manual_recording"] == "ALLOWED_CROPPED"


def test_an_episode_may_not_override_the_account_policy():
    """The gap this closes: an omitted field used to flip recording to allowed."""
    for field, value in (("evidence_mode", "EVIDENCE_LED"),
                         ("manual_recording", "ALLOWED_CROPPED")):
        block = _blocked(
            lambda f=field, v=value: _account_policy({"account_slug": EXPLAIN}, {f: v}))
        assert block["code"] == "ACCOUNT_POLICY_OVERRIDE", block
        assert field in block["reason"], block


def test_an_episode_may_declare_its_own_composition_within_the_mode():
    mix = [{"role": "vector_animation", "pct": 100}]
    policy = _account_policy({"account_slug": EXPLAIN}, {"composition": mix})
    assert policy["composition"] == mix


def test_a_proof_episode_may_not_be_animation_led():
    block = _blocked(lambda: _account_policy(
        {"account_slug": PROOF},
        {"composition": [{"role": "vector_animation", "pct": 100}]}))
    assert block["code"] == "COMPOSITION_OUT_OF_POLICY", block


def test_a_project_without_an_account_slug_is_refused():
    block = _blocked(lambda: _account_policy({}, {}))
    assert block["code"] == "ACCOUNT_SLUG_MISSING", block


def test_a_project_naming_an_account_that_does_not_exist_is_refused():
    block = _blocked(lambda: _account_policy({"account_slug": "no-such-account"}, {}))
    assert block["code"] == "ACCOUNT_DNA_MISSING", block


def main() -> int:
    failures = []
    tests = (
        test_vector_animation_is_not_a_real_composition_role,
        test_a_vector_led_mix_cannot_reach_the_proof_floor,
        test_the_explanatory_mode_accepts_the_mix_the_proof_mode_refuses,
        test_the_explanatory_mode_refuses_a_recording_segment,
        test_a_mix_that_does_not_sum_to_one_hundred_is_refused,
        test_an_unknown_mode_is_refused_rather_than_defaulted,
        test_the_account_owns_the_mode_and_the_episode_inherits_it,
        test_an_episode_may_not_override_the_account_policy,
        test_an_episode_may_declare_its_own_composition_within_the_mode,
        test_a_proof_episode_may_not_be_animation_led,
        test_a_project_without_an_account_slug_is_refused,
        test_a_project_naming_an_account_that_does_not_exist_is_refused,
    )
    for fn in tests:
        try:
            fn()
            print(f"[ok] {fn.__name__}")
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print("\nAll account evidence policy tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
