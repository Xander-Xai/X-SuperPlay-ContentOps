"""Interim Claim Map contract tests.

Run: python tests/test_claim_map.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.evidence.claim_map import ClaimMap  # noqa: E402
from contentops.evidence._common import ContractError  # noqa: E402

SHA = "a" * 64


def terminal_evidence(**overrides):
    item = {
        "evidence_id": "E-001",
        "kind": "terminal_recording",
        "sha256": SHA,
        "logical_path": "project://work/redacted/cli.mp4",
        "time_range": "00:01.000-00:05.000",
        "permission_scope": "publishable",
    }
    item.update(overrides)
    return item


def claim(claim_id="C-001", **overrides):
    item = {
        "claim_id": claim_id,
        "revision": 1,
        "text": "CLI 与 Skill 已验证",
        "kind": "runtime",
        "assertion_about": "cli",
        "support_status": "SUPPORTED",
        "permission_scope": "publishable",
        "limitation": "",
        "evidence": [terminal_evidence()],
        "appearances": [
            {"surface": "narration", "text": "CLI 与 Skill 已验证",
             "time_range": "00:02.000-00:04.000"},
            {"surface": "caption", "text": "CLI 与 Skill 已验证",
             "time_range": "00:02.000-00:04.000"},
        ],
    }
    item.update(overrides)
    return item


def document(claims=None):
    return {
        "schema": "contentops.claim-map/v1",
        "map_id": "MAP-1024-001",
        "package_id": "easel-1024-proof",
        "claims": claims if claims is not None else [claim()],
    }


def rejects(code, claims):
    try:
        ClaimMap.from_dict(document(claims))
    except ContractError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"a map with {claims} was accepted")


def test_a_bound_factual_claim_is_accepted():
    mapping = ClaimMap.from_dict(document())
    found = mapping.claim_for("caption", "CLI 与 Skill 已验证")
    assert found.claim_id == "C-001"
    assert mapping.claim_ids() if hasattr(mapping, "claim_ids") else True
    print("[ok] a factual claim bound to terminal evidence is accepted")


def test_partial_must_state_its_limitation_and_cannot_assert():
    partial = claim(support_status="PARTIAL", limitation="only the CLI path",
                    appearances=[{"surface": "transition", "text": "CLI 与 Skill 已验证"}])
    mapping = ClaimMap.from_dict(document([partial]))
    assert mapping.claims[0].support_status == "PARTIAL"

    rejects("PARTIAL_WITHOUT_LIMITATION",
            [claim(support_status="PARTIAL", limitation="")])
    rejects("UNSUPPORTED_ASSERTION",
            [claim(support_status="PARTIAL", limitation="only the CLI path")])
    print("[ok] PARTIAL needs a limitation and cannot appear on an asserted surface")


def test_blocked_cannot_appear_anywhere():
    rejects("BLOCKED_CLAIM_APPEARS", [claim(support_status="BLOCKED")])
    blocked = ClaimMap.from_dict(document([
        claim(support_status="BLOCKED", appearances=[])
    ]))
    assert blocked.claims[0].appearances == []
    print("[ok] BLOCKED claims cannot carry any appearance")


def test_generated_and_diagram_evidence_is_refused():
    for kind in ("generated_image", "generated_video", "diagram"):
        rejects("UNSUPPORTED_EVIDENCE_KIND",
                [claim(evidence=[terminal_evidence(kind=kind)])])
    print("[ok] generated and diagram visuals cannot support a factual claim")


def test_a_ui_claim_needs_ui_evidence():
    rejects("UI_CLAIM_WITHOUT_UI_EVIDENCE", [claim(assertion_about="ui")])
    ui = claim(
        assertion_about="ui",
        evidence=[terminal_evidence(kind="ui_screenshot",
                                    logical_path="project://work/redacted/ui.png")],
    )
    assert ClaimMap.from_dict(document([ui])).claims[0].assertion_about == "ui"
    print("[ok] a UI claim without UI evidence is refused")


def test_terminal_output_cannot_prove_a_cli_claim_when_it_is_ui_only():
    rejects("CLI_CLAIM_WITHOUT_TERMINAL_EVIDENCE", [claim(
        evidence=[terminal_evidence(kind="ui_recording",
                                    logical_path="project://work/redacted/ui.mp4")],
    )])
    print("[ok] a CLI claim needs terminal evidence, not UI evidence")


def test_appearance_wording_cannot_change_after_binding():
    rejects("APPEARANCE_TEXT_CHANGED", [claim(appearances=[
        {"surface": "caption", "text": "CLI 与 Skill 基本可用"},
    ])])
    print("[ok] a reworded caption is a different claim and is refused")


def test_duplicates_and_permission_mismatches_are_refused():
    rejects("DUPLICATE_CLAIM_ID", [claim(), claim()])
    rejects("PERMISSION_INCOMPATIBLE", [claim(
        evidence=[terminal_evidence(permission_scope="internal")])])
    print("[ok] duplicate ids and publishable claims over internal evidence are refused")


def test_unknown_ids_and_surfaces_are_refused():
    rejects("UNKNOWN_SURFACE", [claim(appearances=[
        {"surface": "thumbnail", "text": "CLI 与 Skill 已验证"}])])
    rejects("INVALID_ID", [claim(claim_id="x")])
    print("[ok] unknown surfaces and malformed ids are refused")


def test_the_fingerprint_changes_when_a_claim_changes():
    original = ClaimMap.from_dict(document())
    changed = copy.deepcopy(document())
    changed["claims"][0]["text"] = "CLI 已验证"
    changed["claims"][0]["appearances"] = [
        {"surface": "caption", "text": "CLI 已验证"}
    ]
    assert original.fingerprint() != ClaimMap.from_dict(changed).fingerprint()
    print("[ok] the map fingerprint changes when claim text changes")


def test_an_unbound_surface_is_refused():
    mapping = ClaimMap.from_dict(document())
    try:
        mapping.claim_for("cover_title", "Easel 已经可以放心使用")
    except ContractError as exc:
        assert exc.code == "UNBOUND_SURFACE", exc
    else:
        raise AssertionError("an unbound cover title was accepted")
    print("[ok] unbound output text is refused")


def main() -> int:
    failures = []
    tests = (
        test_a_bound_factual_claim_is_accepted,
        test_partial_must_state_its_limitation_and_cannot_assert,
        test_blocked_cannot_appear_anywhere,
        test_generated_and_diagram_evidence_is_refused,
        test_a_ui_claim_needs_ui_evidence,
        test_terminal_output_cannot_prove_a_cli_claim_when_it_is_ui_only,
        test_appearance_wording_cannot_change_after_binding,
        test_duplicates_and_permission_mismatches_are_refused,
        test_unknown_ids_and_surfaces_are_refused,
        test_the_fingerprint_changes_when_a_claim_changes,
        test_an_unbound_surface_is_refused,
    )
    for fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(tests)} claim-map tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
