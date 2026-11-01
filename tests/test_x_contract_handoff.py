"""The handoff from the growth skill's PARTIAL_CONTRACT to the real X Post Gate.

The growth skill maps a draft to a record that declares what it could not
establish: ``contract_completeness: PARTIAL_CONTRACT`` and
``upstream_validator: NOT_APPLIED``. That record is deliberately incomplete.

This suite feeds the literal record into the real gate and asserts that the
gate names the missing fields instead of accepting the record, and that nothing
in the partial shape can be mistaken for a human review or a publication. It
does not import the growth skill: the fixture is the contract between the two
branches, so either side can run this without the other being merged.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.publish import post_verdict, validate_post  # noqa: E402

ACCOUNT_PATH = ROOT / "config" / "accounts" / "x-superplay-english.json"
FIXTURE = ROOT / "tests" / "fixtures" / "x-post-partial-contract.json"

#: The fields the growth skill does not produce, and the gate must therefore name.
EXPECTED_GAPS = (
    "MODE_UNKNOWN",
    "ALT_MISSING",
    "IMAGE_ABSENT",
    "THESES_INSUFFICIENT",
    "RECOVERY_FIELD_MISSING",
    "REVIEW_MISSING",
)

TESTS: list = []


def test(fn):
    TESTS.append(fn)
    return fn


def _account() -> dict:
    return json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))


def _record() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _codes(record: dict) -> set:
    return {issue.code for issue in validate_post(record, _account(), root=ROOT)}


@test
def test_the_fixture_is_the_contract_the_skill_declares():
    record = _record()
    assert record["schema"] == "contentops.x-post/v1"
    assert record["account_slug"] == "x-superplay-english"
    assert record["contract_completeness"] == "PARTIAL_CONTRACT"
    assert record["upstream_validator"] == "NOT_APPLIED"
    assert record["review_status"] == "UNREVIEWED"
    assert record["status"] == "draft"
    print("[ok] 1. the fixture carries the skill's own partial-contract claims")


@test
def test_the_gate_names_every_missing_field_instead_of_accepting_the_record():
    codes = _codes(_record())
    missing = [code for code in EXPECTED_GAPS if code not in codes]
    assert not missing, (missing, sorted(codes))
    print(f"[ok] 2. the gate names all {len(EXPECTED_GAPS)} missing-field families")


@test
def test_a_partial_contract_record_is_blocked_and_not_ready():
    verdict = post_verdict(_record(), _account(), root=ROOT)
    assert verdict == "BLOCKED", verdict
    print("[ok] 3. a partial-contract record is BLOCKED, never READY")


@test
def test_unreviewed_is_not_a_human_review_and_the_gate_says_so():
    record = _record()
    record["review_status"] = "APPROVED"
    codes = _codes(record)
    assert "REVIEW_MISSING" in codes, codes
    print("[ok] 4. a label in the skill's contract is not a recorded human review")


@test
def test_a_partial_contract_record_may_not_be_marked_published():
    record = _record()
    record["status"] = "published"
    verdict = post_verdict(record, _account(), root=ROOT)
    codes = _codes(record)
    assert verdict == "BLOCKED", verdict
    assert "PUBLISHED_WITHOUT_URL" in codes, codes
    print("[ok] 5. the partial shape cannot be promoted to published")


@test
def test_unknown_contract_fields_are_ignored_rather_than_trusted():
    record = _record()
    record["upstream_validator"] = "APPLIED"
    record["contract_completeness"] = "COMPLETE"
    record["ready_for_publish"] = True
    assert _codes(record) == _codes(_record()), \
        "fields the gate does not own must not change its verdict"
    assert post_verdict(record, _account(), root=ROOT) == "BLOCKED"
    print("[ok] 6. a caller cannot promote the record by adding a flag")


@test
def test_the_gate_is_deterministic_on_the_same_fixture():
    first = [issue.as_dict() for issue in validate_post(
        copy.deepcopy(_record()), _account(), root=ROOT)]
    second = [issue.as_dict() for issue in validate_post(
        copy.deepcopy(_record()), _account(), root=ROOT)]
    assert first == second
    print("[ok] 7. the same partial record produces the same refusal list")


def main() -> int:
    failures = []
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    print()
    if failures:
        print(f"{len(failures)} of {len(TESTS)} test(s) failed")
        return 1
    print(f"All {len(TESTS)} X contract-handoff tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
