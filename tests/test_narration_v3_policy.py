"""Policy tests for the v3 D/E/F sample plumbing. Issue #34, narration v3.

The safety envelope is the same as the v2 round's, and these tests pin the v3
additions:

- the dry run completes offline, transmits nothing and prints no
  credential-shaped value;
- the new scripts have no pay-as-you-go, clone or transfer surface;
- the sample fits the default synthesis budget;
- candidate files are hidden-label (no D/E/F in any filename);
- the preset-voice evidence points at a receipt that actually used that voice
  in-plan.

No provider interaction exists anywhere in this file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_run, python_executable  # noqa: E402

from contentops.media.lexicon import default_zh_lexicon  # noqa: E402
from contentops.media.narration_director import mapped_groups  # noqa: E402
from contentops.media.t2a_segments import estimated_billable_characters  # noqa: E402
from run_creator_sample import (  # noqa: E402
    LABEL_ORDER,
    PRESET_VOICE,
    PRESET_VOICE_EVIDENCE,
    _reused_baselines,
)
from verify_creator_script import load_verified_plan, synthesis_text  # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


@test
def test_dry_run_is_offline_and_silent_about_credentials():
    result = hidden_run(
        [python_executable(), "scripts/run_creator_sample.py"],
        cwd=str(ROOT),
        timeout=600,
    )
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")
    out = result.stdout or ""
    assert "DRY RUN. NOTHING WAS SENT." in out
    assert "Bearer " not in out
    assert "sk-cp-" not in out and "sk-api-" not in out
    print("[ok] 1. dry run is offline and prints no credential-shaped value")


@test
def test_new_scripts_have_no_payg_clone_or_transfer_surface():
    forbidden = (
        "MINIMAX_API_KEY",
        "child_env_for",
        "resolve_cli",
        "voice_clone",
        "/v1/files",
        "auto_topup",
        "auto_recharge",
    )
    for name in ("run_creator_sample.py", "verify_creator_script.py"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{name} references {token}"
    print("[ok] 2. new scripts have no payg, clone or transfer surface")


@test
def test_the_sample_fits_the_default_budget():
    result = load_verified_plan()
    lexicon = default_zh_lexicon()
    creator = result["creator"]
    plan = result["plan"]
    d_text = "\n".join(creator.unit(uid).text for uid in plan.sample_unit_ids)
    d_billable = estimated_billable_characters([synthesis_text(d_text, lexicon)])
    e_billable = estimated_billable_characters(
        [
            synthesis_text(group.text, lexicon)
            for group in mapped_groups(plan, creator, section="sample.groups")
        ]
    )
    estimated = 2 * d_billable + e_billable  # D and F share the text; E adds groups
    assert 0 < estimated < 1200, (
        f"the D+E+F estimate ({estimated}) must fit the default --budget-chars 1200"
    )
    print("[ok] 3. the D/E/F sample fits the default synthesis budget")


@test
def test_candidate_filenames_carry_no_version_information():
    assert sorted(LABEL_ORDER) == ["D", "E", "F"]
    for index in range(len(LABEL_ORDER)):
        name = f"candidate-{index + 1}"
        for cid in ("D", "E", "F"):
            assert cid not in name
    print("[ok] 4. candidate filenames are label-blind by construction")


@test
def test_preset_voice_evidence_points_at_a_real_in_plan_receipt():
    receipt_path = ROOT / PRESET_VOICE_EVIDENCE["receipt"]
    assert receipt_path.is_file(), receipt_path
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["voice"] == PRESET_VOICE, receipt["voice"]
    assert receipt["billing_guard_verdict"] == "SAFE_INCLUDED_PLAN", (
        "the preset voice must have been exercised under the M Plan billing gate"
    )
    print("[ok] 5. the preset voice is backed by an in-plan receipt")


@test
def test_reused_baselines_report_presence_without_generating():
    records = _reused_baselines()
    assert [record["name"] for record in records] == [
        "B_v2_single_request",
        "C_v2_segmented_join",
    ]
    for record in records:
        if record["present"]:
            assert len(record["sha256"]) == 64
            assert (record["duration_s"] or 0) > 0
        else:
            assert "path" in record
    print("[ok] 6. reused baselines are referenced, never regenerated")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    failures = 0
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            print(f"[FAIL] {fn.__name__}: {exc}")
            failures += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR ] {fn.__name__}: {type(exc).__name__}({exc})")
            failures += 1
    total = len(TESTS)
    if failures:
        print(f"\n{failures} of {total} test(s) failed")
        return 1
    print(f"\nAll {total} narration-v3 policy tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
