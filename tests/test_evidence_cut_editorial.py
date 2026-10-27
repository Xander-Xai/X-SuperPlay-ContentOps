"""Editorial-package tests: two cuts, one evidence base, different arguments.

These tests do not judge taste. They check the properties that make the two cuts
genuinely different and honestly bound:

- every narration row in the script resolves to the claim it names, with exact
  wording;
- every asserted appearance appears in the script;
- no generated visual supports a claim;
- the two cuts differ in audience framing, opening, argument order, target and
  CTA rather than in colour only.

Run: python tests/test_evidence_cut_editorial.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.evidence.claim_map import ClaimMap  # noqa: E402
from contentops.media.cut_plan import CutPlan  # noqa: E402

PACKAGES = ("easel-1024-proof", "easel-engineering-proof")

#: Citation cards quote a tracked document. They are not generated imagery, but
#: they are also not footage, so they must stay a small share of the cut.
CITATION_CARD_ASSETS = {"A-DOC-WEB", "A-MATRIX"}


def package(name: str):
    base = ROOT / "projects" / name / "script"
    claim_map = ClaimMap.from_dict(
        json.loads((base / "claim-map.json").read_text(encoding="utf-8")))
    cut_plan = CutPlan.from_dict(
        json.loads((base / "cut-plan.json").read_text(encoding="utf-8")))
    cut_plan.validate_claims(claim_map)
    master = (base / "master.md").read_text(encoding="utf-8")
    return claim_map, cut_plan, master


def narration_rows(master: str) -> list[tuple[str, str]]:
    section = master.split("## Narration", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cols = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(cols) != 3:
            continue
        claim_id, text = cols[1], cols[2]
        if claim_id in ("Claim", "---") or set(claim_id) <= set("-: "):
            continue
        rows.append((claim_id, text))
    return rows


def test_both_packages_validate_against_their_contracts():
    for name in PACKAGES:
        claim_map, cut_plan, _ = package(name)
        assert claim_map.claims, name
        assert cut_plan.placements, name
        print(f"[ok] 1. {name}: {len(claim_map.claims)} claims, "
              f"{len(cut_plan.placements)} placements")


def test_every_narration_row_resolves_to_the_claim_it_names():
    for name in PACKAGES:
        claim_map, _, master = package(name)
        rows = narration_rows(master)
        assert rows, f"{name} has no narration table"
        for claim_id, text in rows:
            claim = claim_map.by_id(claim_id)
            assert claim.text == text, (
                f"{name}: {claim_id} script says {text!r}, map says {claim.text!r}")
            found = claim_map.claim_for("narration", text)
            assert found.claim_id == claim_id
        print(f"[ok] 2. {name}: all {len(rows)} narration lines are claim-bound")


def test_every_asserted_appearance_appears_in_the_master():
    for name in PACKAGES:
        claim_map, _, master = package(name)
        for claim in claim_map.claims:
            for appearance in claim.appearances:
                if appearance["surface"] == "transition":
                    continue
                assert appearance["text"] in master, (
                    f"{name}: {claim.claim_id} appears as "
                    f"{appearance['surface']} but is absent from the script")
        print(f"[ok] 3. {name}: every asserted appearance exists in the script")


def test_no_claim_is_blocked_and_no_generated_visual_is_evidence():
    for name in PACKAGES:
        claim_map, _, _ = package(name)
        blocked = [c.claim_id for c in claim_map.claims
                   if c.support_status == "BLOCKED"]
        assert not blocked, f"{name} still contains blocked claims: {blocked}"
        for claim in claim_map.claims:
            for item in claim.evidence:
                assert item["kind"] in (
                    "terminal_recording", "terminal_screenshot", "ui_screenshot",
                    "ui_recording", "document", "data",
                ), f"{name}: {claim.claim_id} binds {item['kind']}"
        print(f"[ok] 4. {name}: no blocked claim, no generated evidence")


def test_the_two_cuts_argue_differently():
    a_map, a_plan, a_master = package("easel-1024-proof")
    b_map, b_plan, b_master = package("easel-engineering-proof")

    a_open = a_map.claim_for("narration", narration_rows(a_master)[0][1])
    b_open = b_map.claim_for("narration", narration_rows(b_master)[0][1])
    assert a_open.text != b_open.text, "both cuts open with the same assertion"

    assert (a_plan.target["width"], a_plan.target["height"]) == (1080, 1920)
    assert (b_plan.target["width"], b_plan.target["height"]) == (1920, 1080)

    a_order = [c for _, c in narration_rows(a_master)]
    b_order = [c for _, c in narration_rows(b_master)]
    assert a_order != b_order, "the argument order is identical"

    a_cta = a_map.claim_for("cta", "先看证据，再决定接不接。")
    b_cta = b_map.claim_for("cta", "要复核，就从这些回执开始。")
    assert a_cta.text != b_cta.text

    # The 1024 cut's length is the plan's own target; the engineering cut's
    # deviation is asserted separately.
    a_low, a_high = a_plan.target["duration_ms_range"]
    assert a_low <= a_plan.placements[-1].end_ms <= a_high
    assert b_plan.placements[-1].end_ms == 62000
    print("[ok] 5. the cuts differ in opening, order, target, CTA and length")


def test_citation_cards_are_a_minority_of_the_cut():
    for name in PACKAGES:
        _, cut_plan, _ = package(name)
        total = sum(p.end_ms - p.start_ms for p in cut_plan.placements)
        cards = sum(p.end_ms - p.start_ms for p in cut_plan.placements
                    if p.asset_id in CITATION_CARD_ASSETS)
        assert cards / total < 0.30, (
            f"{name}: citation cards are {cards / total:.0%} of the cut; the cap is 30%")
        # The design reserves 30% for citation/matrix frames; generated media has
        # its own, much stricter, rule.
        print(f"[ok] 6. {name}: citation cards {cards / total:.0%} of runtime")


def test_the_engineering_duration_deviation_is_recorded():
    text = (ROOT / "projects" / "easel-engineering-proof" / "project.yaml").read_text(
        encoding="utf-8")
    assert "design_deviation" in text, (
        "the shorter engineering cut must record why it deviates from 78-90s")
    print("[ok] 7. the engineering duration deviation is documented")


def main() -> int:
    failures = []
    tests = (
        test_both_packages_validate_against_their_contracts,
        test_every_narration_row_resolves_to_the_claim_it_names,
        test_every_asserted_appearance_appears_in_the_master,
        test_no_claim_is_blocked_and_no_generated_visual_is_evidence,
        test_the_two_cuts_argue_differently,
        test_citation_cards_are_a_minority_of_the_cut,
        test_the_engineering_duration_deviation_is_recorded,
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
    print(f"\nAll {len(tests)} editorial-package tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
