"""Regression tests for the NarrationDirector. Issue #34, narration v3.

The v2 failure pinned in the diagnosis: calm was the explicit emotion on 5 of
7 segments (71%) and pauses were two fixed values. The director's rules exist
to make both impossible by construction:

- auto emotion is the default and explicit emotions must be justified, documented
  and a minority; calm at most once;
- speeds are bounded and direction-consistent with every member unit;
- pauses are 0.2-0.5 s, at most two per unit, anchored to unique text;
- synthesis groups follow narrative intent: at least one multi-unit group,
  fewer groups than units, single-unit groups only with a declared reason and a
  differing control.

Everything runs offline.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.creator_script import load_creator_script  # noqa: E402
from contentops.media.minimax_native_tts import validate_pause_markers  # noqa: E402
from contentops.media.narration_director import (  # noqa: E402
    DirectorUnit,
    NarrationDirectorError,
    PauseIntent,
    SynthesisGroup,
    estimate_seconds,
    group_synthesis_text,
    load_director_plan,
    mapped_groups,
    unit_synthesis_text,
    verify_director_plan,
)

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


CREATOR = ROOT / "projects/easel-enhanced-golden/script/creator-script.json"
PLAN = ROOT / "projects/easel-enhanced-golden/script/narration-plan.json"


def _load_pair():
    creator = load_creator_script(CREATOR)
    plan = load_director_plan(PLAN)
    return creator, plan


def _verify(plan, creator):
    return verify_director_plan(plan, creator)


def _mutate_unit(plan, unit_id: str, **changes):
    units = tuple(
        dataclasses.replace(unit, **changes) if unit.id == unit_id else unit
        for unit in plan.units
    )
    return dataclasses.replace(plan, units=units)


def _mutate_group(plan, group_id: str, *, sample: bool = False, **changes):
    attribute = "sample_groups" if sample else "groups"
    groups = tuple(
        dataclasses.replace(group, **changes) if group.id == group_id else group
        for group in getattr(plan, attribute)
    )
    return dataclasses.replace(plan, **{attribute: groups})


@test
def test_the_tracked_plan_verifies_and_states_its_limits():
    creator, plan = _load_pair()
    report = _verify(plan, creator)
    assert report["verified"] is True
    assert report["units"] == 8 and report["groups"] == 4
    assert report["explicit_emotions"] == {"U05": "surprised"}
    assert report["sample_groups"] == ["S-G1", "S-G2"]
    assert 18 <= report["sample_estimated_seconds"] <= 26, report["sample_estimated_seconds"]
    assert report["not_proven_by_this_check"], "the verifier states its limits"
    print("[ok] 1. the tracked director plan verifies; auto is the default")


@test
def test_the_mapped_sample_is_exactly_what_will_be_sent():
    creator, plan = _load_pair()
    groups = mapped_groups(plan, creator, section="sample.groups")
    assert [group.id for group in groups] == ["S-G1", "S-G2"]
    s1, s2 = groups
    assert s1.emotion is None and s1.speed == 1.0
    assert "<#0.35#>" in s1.text and "<#0.3#>" in s1.text
    assert s2.emotion == "surprised" and s2.speed == 0.98
    assert "<#0.35#>" in s2.text
    for group in groups:
        validate_pause_markers(group.text)
        assert group.billable_characters > 0
        assert group.estimated_seconds > 0
    print("[ok] 2. the conservative mapping produces valid, controlled text")


@test
def test_calm_cannot_become_a_repeated_default():
    creator, plan = _load_pair()
    twice = plan
    for unit_id in ("U01", "U02"):
        twice = _mutate_unit(
            twice, unit_id, explicit_emotion="calm",
            emotion_justification="test",
        )
    try:
        _verify(twice, creator)
    except NarrationDirectorError as exc:
        assert "calm" in str(exc)
    else:
        raise AssertionError("calm twice must refuse")

    most = plan
    for unit_id in ("U01", "U02", "U03", "U04", "U06"):
        most = _mutate_unit(
            most, unit_id, explicit_emotion="happy",
            emotion_justification="test",
        )
    try:
        _verify(most, creator)
    except NarrationDirectorError as exc:
        assert "majority" in str(exc)
    else:
        raise AssertionError("explicit emotions as a majority must refuse")
    print("[ok] 3. calm stays at most once; explicit emotions stay a minority")


@test
def test_explicit_emotions_need_justification_and_model_support():
    creator, plan = _load_pair()
    unjustified = _mutate_unit(plan, "U05", emotion_justification=None)
    try:
        _verify(unjustified, creator)
    except NarrationDirectorError as exc:
        assert "justification" in str(exc)
    else:
        raise AssertionError("an unjustified emotion must refuse")

    whisper = _mutate_unit(
        plan, "U05", explicit_emotion="whisper",
        emotion_justification="test",
    )
    try:
        _verify(whisper, creator)
    except NarrationDirectorError as exc:
        assert "whisper" in str(exc)
    else:
        raise AssertionError("whisper on speech-2.8-hd must refuse")

    unknown = _mutate_unit(
        plan, "U05", explicit_emotion="excited",
        emotion_justification="test",
    )
    try:
        _verify(unknown, creator)
    except NarrationDirectorError as exc:
        assert "documented" in str(exc)
    else:
        raise AssertionError("an undocumented emotion must refuse")
    print("[ok] 4. emotions are documented, justified and model-applicable")


@test
def test_speed_must_match_every_member_units_intent():
    creator, plan = _load_pair()
    faster_turn = _mutate_group(plan, "G3", speed=1.05)
    try:
        _verify(faster_turn, creator)
    except NarrationDirectorError as exc:
        assert "slower" in str(exc)
    else:
        raise AssertionError("a speed against the unit intents must refuse")

    steady_with_speed = _mutate_group(plan, "G1", speed=0.98)
    try:
        _verify(steady_with_speed, creator)
    except NarrationDirectorError as exc:
        assert "STEADY" in str(exc)
    else:
        raise AssertionError("a non-steady group of steady units must refuse")

    out_of_bounds = _mutate_group(plan, "G3", speed=0.5)
    try:
        _verify(out_of_bounds, creator)
    except NarrationDirectorError as exc:
        assert "conservative" in str(exc)
    else:
        raise AssertionError("out-of-bounds speed must refuse")

    unjustified = _mutate_group(plan, "G3", justification=None)
    try:
        _verify(unjustified, creator)
    except NarrationDirectorError as exc:
        assert "justification" in str(exc)
    else:
        raise AssertionError("a non-steady speed without justification must refuse")
    print("[ok] 5. group speed is bounded, homogeneous and justified")


@test
def test_pause_intents_are_bounded_and_anchored():
    creator, plan = _load_pair()
    too_long = _mutate_unit(
        plan, "U01",
        pause_intent=(PauseIntent(after="跑不跑得起来？", duration_s=0.9, role="x"),),
    )
    try:
        _verify(too_long, creator)
    except NarrationDirectorError as exc:
        assert "outside" in str(exc)
    else:
        raise AssertionError("an out-of-range pause must refuse")

    too_many = _mutate_unit(
        plan, "U02",
        pause_intent=(
            PauseIntent(after="，", duration_s=0.3, role="a"),
            PauseIntent(after="。", duration_s=0.3, role="b"),
            PauseIntent(after="——", duration_s=0.3, role="c"),
        ),
    )
    try:
        _verify(too_many, creator)
    except NarrationDirectorError as exc:
        assert "cap" in str(exc)
    else:
        raise AssertionError("more than two pauses must refuse")

    missing_anchor = _mutate_unit(
        plan, "U01",
        pause_intent=(PauseIntent(after="不存在的锚点", duration_s=0.3, role="x"),),
    )
    try:
        _verify(missing_anchor, creator)
    except NarrationDirectorError as exc:
        assert "exactly once" in str(exc)
    else:
        raise AssertionError("a missing anchor must refuse")

    ambiguous_anchor = _mutate_unit(
        plan, "U03",
        pause_intent=(PauseIntent(after="。", duration_s=0.3, role="x"),),
    )
    try:
        _verify(ambiguous_anchor, creator)
    except NarrationDirectorError as exc:
        assert "exactly once" in str(exc)
    else:
        raise AssertionError("an ambiguous anchor must refuse")
    print("[ok] 6. pause intents are capped, ranged and uniquely anchored")


@test
def test_groups_cannot_slice_per_sentence_or_scramble_order():
    creator, plan = _load_pair()
    sliced = dataclasses.replace(
        plan,
        groups=tuple(
            SynthesisGroup(
                id=f"S{unit.id}", units=(unit.id,),
                single_unit_reason="test", emotion="happy", speed=1.0,
            )
            for unit in plan.units
        ),
    )
    try:
        _verify(sliced, creator)
    except NarrationDirectorError as exc:
        assert "slicing" in str(exc) or "multi-unit" in str(exc)
    else:
        raise AssertionError("per-sentence slicing must refuse")

    missing = _mutate_group(plan, "G4", units=("U07",))
    try:
        _verify(missing, creator)
    except NarrationDirectorError as exc:
        assert "cover" in str(exc)
    else:
        raise AssertionError("a group plan that drops a unit must refuse")

    scrambled = _mutate_group(plan, "G1", units=("U02", "U01"))
    try:
        _verify(scrambled, creator)
    except NarrationDirectorError as exc:
        assert "cover" in str(exc)
    else:
        raise AssertionError("a re-ordered group must refuse")

    no_multi = dataclasses.replace(
        plan,
        groups=(
            SynthesisGroup(id="A", units=("U01", "U02")),
            SynthesisGroup(id="B", units=("U03",)),
            SynthesisGroup(id="C", units=("U04",)),
            SynthesisGroup(id="D", units=("U05",)),
            SynthesisGroup(id="E", units=("U06",)),
            SynthesisGroup(id="F", units=("U07",)),
            SynthesisGroup(id="G", units=("U08",)),
        ),
    )
    try:
        _verify(no_multi, creator)
    except NarrationDirectorError as exc:
        assert "slicing" in str(exc) or "multi-unit" in str(exc)
    else:
        raise AssertionError("mostly single-unit groups must refuse")
    print("[ok] 7. grouping cannot slice per sentence or scramble order")


@test
def test_single_unit_sample_group_needs_a_reason_and_control():
    creator, plan = _load_pair()
    naked = _mutate_group(
        plan, "S-G2", sample=True,
        single_unit_reason=None, emotion=None, speed=0.98,
    )
    try:
        _verify(naked, creator)
    except NarrationDirectorError as exc:
        assert "reason" in str(exc)
    else:
        raise AssertionError("a single-unit group without a reason must refuse")

    no_control = _mutate_group(
        plan, "S-G2", sample=True, single_unit_reason="test",
        emotion=None, speed=1.0,
    )
    try:
        _verify(no_control, creator)
    except NarrationDirectorError as exc:
        assert "differing control" in str(exc)
    else:
        raise AssertionError("a single-unit group without a control must refuse")
    print("[ok] 8. single-unit sample groups are declared and controlled")


@test
def test_mapping_is_deterministic_and_inserts_markers_in_order():
    creator, plan = _load_pair()
    first = [group.text for group in mapped_groups(plan, creator, section="sample.groups")]
    second = [group.text for group in mapped_groups(plan, creator, section="sample.groups")]
    assert first == second

    unit = DirectorUnit(
        id="X", communicative_intent="i", delivery_style="d",
        emphasis_terms=(), pace_intent="STEADY",
        emotional_transition="e", context_before="b", context_after="a",
        pause_intent=(
            PauseIntent(after="甲", duration_s=0.2, role="a"),
            PauseIntent(after="乙", duration_s=0.4, role="b"),
        ),
    )
    mapped = unit_synthesis_text(unit, "甲文乙文。")
    assert mapped == "甲<#0.2#>文乙<#0.4#>文。"
    assert estimate_seconds(mapped) > estimate_seconds("甲文乙文。")
    print("[ok] 9. mapping is deterministic; markers insert in anchor order")


@test
def test_stale_creator_digest_is_refused():
    creator, plan = _load_pair()
    try:
        verify_director_plan(plan, creator, expected_creator_digest="0" * 64)
    except NarrationDirectorError as exc:
        assert "stale" in str(exc) or "hashes to" in str(exc)
    else:
        raise AssertionError("a stale plan must refuse")
    print("[ok] 10. a plan pinned to a different creator digest is refused")


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
    print(f"\nAll {total} narration-director tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
