"""Regression tests for the CreatorScriptEditor stage. Issue #34, narration v3.

The v2 failure was a spoken script that was 96.9% character-identical to the
written original. The v3 contract is different in kind: the creator script may
re-order, drop declared details and ask questions -- but must not invent a
number, preserve a fact that was never there, use template marketing language,
or slip a first-person claim in without a declared basis. These tests pin each
of those refusals plus the version map.

Everything runs offline.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.creator_script import (  # noqa: E402
    CreatorScriptError,
    load_creator_script,
    verify_creator_script,
)
from contentops.media.lexicon import default_zh_lexicon  # noqa: E402
from contentops.media.native_rounds import canonical_blob_sha256  # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


FACT = ROOT / "projects/easel-review/script/narration.txt"
CREATOR = ROOT / "projects/easel-enhanced-golden/script/creator-script.json"
VERSION_MAP = ROOT / "projects/easel-enhanced-golden/script/creator-version-map.json"
LOCK = ROOT / "projects/easel-enhanced-golden/evidence/evidence-lock.json"
FACT_DIGEST = "f2de808c9e723f8430acdc44dc374c5791b249250d8bc585a172360a88b9542a"


def _verify(script, *, lock_digest: str = FACT_DIGEST):
    return verify_creator_script(
        script,
        original_text=FACT.read_text(encoding="utf-8"),
        canonical_original_digest=FACT_DIGEST,
        evidence_lock_digest=lock_digest,
    )


def _mutate_unit(script, unit_id: str, **changes):
    units = tuple(
        dataclasses.replace(unit, **changes) if unit.id == unit_id else unit
        for unit in script.units
    )
    return dataclasses.replace(script, units=units)


@test
def test_the_tracked_creator_script_verifies():
    script = load_creator_script(CREATOR)
    report = _verify(script)
    assert report["verified"] is True
    assert report["not_proven_by_this_check"], "the verifier states its limits"
    assert [unit.id for unit in script.units] == [f"U{i:02d}" for i in range(1, 9)]
    assert script.sample_unit_ids == ("U01", "U03", "U05")
    assert script.units[0].beat == "HOOK" and script.units[-1].beat == "ENDING"
    print("[ok] 1. the tracked creator script verifies")


@test
def test_source_digest_agrees_with_the_evidence_lock():
    assert canonical_blob_sha256(FACT) == FACT_DIGEST
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    assert lock["narration_text_sha256"] == FACT_DIGEST
    script = load_creator_script(CREATOR)
    assert script.source_digest == FACT_DIGEST
    print("[ok] 2. fact script, lock and creator script cite one digest")


@test
def test_the_version_map_matches_a_recomputation():
    script = load_creator_script(CREATOR)
    lexicon = default_zh_lexicon()
    tracked = json.loads(VERSION_MAP.read_text(encoding="utf-8"))
    assert tracked["fact_script"]["canonical_blob_sha256"] == FACT_DIGEST
    working = hashlib.sha256(CREATOR.read_bytes()).hexdigest()
    assert tracked["creator_script"]["working_tree_sha256"] == working
    from contentops.media.minimax_native_tts import normalize_paragraph_newlines

    d_text = "\n".join(
        script.unit(uid).text for uid in script.sample_unit_ids
    )
    d_synth = normalize_paragraph_newlines(lexicon.spoken_text(d_text))
    stored = tracked["synthesis"]["candidate_D_single_request"]
    assert stored["synthesis_sha256"] == hashlib.sha256(
        d_synth.encode("utf-8")
    ).hexdigest()
    assert stored["display_sha256"] == hashlib.sha256(d_text.encode("utf-8")).hexdigest()
    assert "planned_full_groups_not_executed" in tracked["synthesis"], (
        "the map must separate planned-but-not-executed synthesis from produced ones"
    )
    print("[ok] 3. the tracked version map equals a fresh recomputation")


@test
def test_an_invented_number_is_refused():
    script = load_creator_script(CREATOR)
    mutated = _mutate_unit(
        script, "U02", text=script.unit("U02").text.replace("114 个", "114 个, 999 个")
    )
    try:
        _verify(mutated)
    except CreatorScriptError as exc:
        assert "digit tokens not present" in str(exc)
    else:
        raise AssertionError("an invented number must refuse")
    print("[ok] 4. an invented number fails verification")


@test
def test_a_dropped_number_needs_a_declared_omission():
    script = load_creator_script(CREATOR)
    dropped = _mutate_unit(
        script, "U02", text=script.unit("U02").text.replace("有 52 个", "有不少")
    )
    try:
        _verify(dropped)
    except CreatorScriptError as exc:
        assert "without a declared omission" in str(exc)
    else:
        raise AssertionError("a dropped number without an omission must refuse")

    declared = dataclasses.replace(
        script,
        omitted_details=script.omitted_details
        + ({"text": "52 个", "reason": "test declaration"},),
        # remove the phrase-level protection for this mutation so the omission is the only issue
        preserved_facts=tuple(f for f in script.preserved_facts if f != "52 个"),
    )
    declared = _mutate_unit(
        declared, "U02", text=script.unit("U02").text.replace("有 52 个", "有不少")
    )
    report = _verify(declared)
    assert report["verified"] is True
    print("[ok] 5. a dropped number is admissible only when declared")


@test
def test_a_reintroduced_omitted_detail_is_refused():
    script = load_creator_script(CREATOR)
    mutated = _mutate_unit(
        script, "U06", text=script.unit("U06").text.replace("依赖没装", "fastapi、uvicorn 没装")
    )
    try:
        _verify(mutated)
    except CreatorScriptError as exc:
        assert "still present" in str(exc)
    else:
        raise AssertionError("a reintroduced omission must refuse")
    print("[ok] 6. an omitted detail cannot silently return")


@test
def test_a_fact_that_never_existed_cannot_be_preserved():
    script = load_creator_script(CREATOR)
    mutated = dataclasses.replace(
        script, preserved_facts=script.preserved_facts + ("完全不存在的事实",)
    )
    try:
        _verify(mutated)
    except CreatorScriptError as exc:
        assert "never there" in str(exc)
    else:
        raise AssertionError("a fabricated preserved fact must refuse")
    print("[ok] 7. preserved facts must exist in the fact script")


@test
def test_template_marketing_language_is_refused():
    script = load_creator_script(CREATOR)
    mutated = _mutate_unit(
        script, "U01", text="家人们，" + script.unit("U01").text
    )
    try:
        _verify(mutated)
    except CreatorScriptError as exc:
        assert "家人们" in str(exc)
    else:
        raise AssertionError("template marketing language must refuse")
    print("[ok] 8. template marketing language fails verification")


@test
def test_first_person_without_a_declared_basis_is_refused():
    script = load_creator_script(CREATOR)
    mutated = _mutate_unit(
        script,
        "U02",
        text=script.unit("U02").text + "我自己试过，很顺。",
        first_person_basis=None,
    )
    try:
        _verify(mutated)
    except CreatorScriptError as exc:
        assert "first_person_basis" in str(exc)
    else:
        raise AssertionError("first person without a basis must refuse")
    print("[ok] 9. first person without a declared basis fails verification")


@test
def test_beat_structure_is_enforced():
    script = load_creator_script(CREATOR)
    no_value = dataclasses.replace(
        script,
        units=tuple(u for u in script.units if u.beat != "VALUE"),
        sample_unit_ids=script.sample_unit_ids,
    )
    try:
        _verify(no_value)
    except CreatorScriptError as exc:
        assert "missing" in str(exc) and "VALUE" in str(exc)
    else:
        raise AssertionError("a missing beat must refuse")

    bad_first = _mutate_unit(script, "U01", beat="SETUP")
    try:
        _verify(bad_first)
    except CreatorScriptError as exc:
        assert "HOOK" in str(exc)
    else:
        raise AssertionError("a script not opening on the hook must refuse")

    bad_last = _mutate_unit(script, "U08", beat="VALUE")
    try:
        _verify(bad_last)
    except CreatorScriptError as exc:
        assert "ENDING" in str(exc)
    else:
        raise AssertionError("a script not ending on the ending must refuse")
    print("[ok] 10. beat coverage, hook-first and ending-last are enforced")


@test
def test_newlines_markers_and_question_overload_are_refused():
    script = load_creator_script(CREATOR)
    newline = _mutate_unit(script, "U01", text=script.unit("U01").text + "\n第二行")
    try:
        _verify(newline)
    except CreatorScriptError as exc:
        assert "newline" in str(exc)
    else:
        raise AssertionError("a newline inside a unit must refuse")

    marker = _mutate_unit(
        script, "U01", text=script.unit("U01").text.replace("？", "？<#0.3#>")
    )
    try:
        _verify(marker)
    except CreatorScriptError as exc:
        assert "marker" in str(exc)
    else:
        raise AssertionError("a marker inside an editor unit must refuse")

    questions = _mutate_unit(
        script, "U02", text=script.unit("U02").text + "真的吗？"
    )
    try:
        _verify(questions)
    except CreatorScriptError as exc:
        assert "question" in str(exc)
    else:
        raise AssertionError("question overload must refuse")
    print("[ok] 11. newline, marker and question-density rules hold")


@test
def test_sample_bounds_and_order_are_enforced():
    script = load_creator_script(CREATOR)
    unknown = dataclasses.replace(script, sample_unit_ids=("U01", "U99"))
    try:
        _verify(unknown)
    except CreatorScriptError as exc:
        assert "unknown unit" in str(exc)
    else:
        raise AssertionError("an unknown sample unit must refuse")

    reordered = dataclasses.replace(script, sample_unit_ids=("U05", "U01", "U03"))
    try:
        _verify(reordered)
    except CreatorScriptError as exc:
        assert "order" in str(exc)
    else:
        raise AssertionError("a re-ordered excerpt must refuse")

    bad_range = dataclasses.replace(script, target_duration_s=(2.0, 3.0))
    try:
        _verify(bad_range)
    except CreatorScriptError as exc:
        assert "sane range" in str(exc)
    else:
        raise AssertionError("an insane target range must refuse")
    print("[ok] 12. sample references, order and target range are bounded")


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
    print(f"\nAll {total} creator-script tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
