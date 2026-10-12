"""Regression tests for the spoken-script stage. Issue #34, narration v2.

These tests pin the contract that makes the editorial derivative admissible:
the original stays locked, numbers survive, protected phrases survive, pause
markers obey the provider's documented rules and the full script covers all
five semantic roles. They also pin the three-way version mapping (original /
spoken / synthesis) against the tracked `narration-version-map.json`, so an
edit to either the script or the map without the other fails here.

Everything runs offline; no provider interaction exists in this stage.
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

from contentops.media.lexicon import default_zh_lexicon  # noqa: E402
from contentops.media.native_rounds import canonical_blob_sha256  # noqa: E402
from contentops.media.spoken_script import (  # noqa: E402
    SpokenScriptError,
    digit_tokens,
    load_spoken_script,
    sample_original_text,
    split_paragraphs,
    synthesis_versions,
    verify_script,
)

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


ORIGINAL = ROOT / "projects/easel-review/script/narration.txt"
EVIDENCE_LOCK = ROOT / "projects/easel-enhanced-golden/evidence/evidence-lock.json"
SPOKEN_SCRIPT = ROOT / "projects/easel-enhanced-golden/script/narration-spoken.json"
VERSION_MAP = ROOT / "projects/easel-enhanced-golden/script/narration-version-map.json"

ORIGINAL_DIGEST = "f2de808c9e723f8430acdc44dc374c5791b249250d8bc585a172360a88b9542a"


def _verify(script, *, lock_digest: str = ORIGINAL_DIGEST):
    return verify_script(
        script,
        original_text=ORIGINAL.read_text(encoding="utf-8"),
        canonical_original_digest=ORIGINAL_DIGEST,
        evidence_lock_digest=lock_digest,
    )


@test
def test_the_tracked_spoken_script_verifies_against_the_locked_original():
    script = load_spoken_script(SPOKEN_SCRIPT)
    report = _verify(script)
    assert report["verified"] is True
    assert report["not_proven_by_this_check"], (
        "the verifier must state what it cannot prove, not only what passed"
    )
    ids = [spec.id for spec in script.segments]
    assert ids == ["S01", "S02", "S03", "S04", "S05", "S06", "S07"]
    assert script.sample_segment_ids == ("S01", "S02", "S03")
    print("[ok] 1. the tracked spoken script verifies against the evidence lock")


@test
def test_the_original_digest_and_lock_still_agree_with_the_repository():
    assert canonical_blob_sha256(ORIGINAL) == ORIGINAL_DIGEST
    lock = json.loads(EVIDENCE_LOCK.read_text(encoding="utf-8"))
    assert lock["narration_text_sha256"] == ORIGINAL_DIGEST
    script = load_spoken_script(SPOKEN_SCRIPT)
    assert script.source_digest == ORIGINAL_DIGEST
    print("[ok] 2. original, lock and spoken script cite the same digest")


@test
def test_the_version_map_matches_a_recomputation():
    script = load_spoken_script(SPOKEN_SCRIPT)
    lexicon = default_zh_lexicon()
    recomputed = synthesis_versions(script, lexicon)
    tracked = json.loads(VERSION_MAP.read_text(encoding="utf-8"))
    assert tracked["schema"] == "contentops.narration-version-map/v1"
    assert tracked["original"]["canonical_blob_sha256"] == ORIGINAL_DIGEST

    working = hashlib.sha256(SPOKEN_SCRIPT.read_bytes()).hexdigest()
    stored = tracked["spoken_script"]
    assert stored["working_tree_sha256"] == working, (
        "the map must describe the spoken script currently on disk; a stale map "
        "is a stale mapping of every synthesis hash derived from it"
    )
    canonical = canonical_blob_sha256(SPOKEN_SCRIPT)
    if canonical is not None:
        assert stored["canonical_blob_sha256"] == canonical == working, (
            "once the spoken script is committed, its blob digest, its working "
            "bytes and the map must all agree"
        )
    assert stored["display_text_sha256"] == hashlib.sha256(
        script.full_text().encode("utf-8")
    ).hexdigest()
    for name, entry in recomputed.items():
        stored_entry = tracked["synthesis"][name]
        assert stored_entry["synthesis_sha256"] == entry["synthesis_sha256"], name
        assert stored_entry["display_sha256"] == entry["display_sha256"], name
    assert set(tracked["synthesis"]) == set(recomputed), (
        "the map must describe exactly the recomputed scopes"
    )
    print("[ok] 3. the tracked version map equals a fresh recomputation")


@test
def test_digit_tokens_ignore_pause_marker_values():
    assert digit_tokens("看<#0.3#>这里，982 个。") == digit_tokens("看这里，982 个。")
    assert digit_tokens("v0.2.1")["0.2.1"] == 1
    print("[ok] 4. pause values are instructions, not digits")


@test
def test_an_invented_number_is_refused():
    script = load_spoken_script(SPOKEN_SCRIPT)
    mutated_segments = list(script.segments)
    mutated_segments[0] = dataclasses.replace(
        mutated_segments[0],
        text=mutated_segments[0].text.replace("装了", "装了 3 个"),
    )
    mutated = dataclasses.replace(script, segments=tuple(mutated_segments))
    try:
        _verify(mutated)
    except SpokenScriptError as exc:
        assert "digit tokens" in str(exc)
    else:
        raise AssertionError("an invented digit token must refuse")
    print("[ok] 5. an invented number fails verification")


@test
def test_a_dropped_protected_phrase_is_refused():
    script = load_spoken_script(SPOKEN_SCRIPT)
    mutated = dataclasses.replace(
        script, protected_phrases=tuple(script.protected_phrases) + ("根本不存在的一句话",)
    )
    try:
        _verify(mutated)
    except SpokenScriptError as exc:
        assert "protected phrase" in str(exc)
    else:
        raise AssertionError("a protected phrase absent from the text must refuse")
    print("[ok] 6. a protected phrase that vanished fails verification")


@test
def test_a_missing_role_is_refused():
    script = load_spoken_script(SPOKEN_SCRIPT)
    mutated = dataclasses.replace(
        script,
        segments=tuple(s for s in script.segments if s.role != "TURN"),
    )
    try:
        _verify(mutated)
    except SpokenScriptError as exc:
        assert "role" in str(exc)
    else:
        raise AssertionError("a script without all five roles must refuse")
    print("[ok] 7. incomplete role coverage fails verification")


@test
def test_an_invalid_pause_marker_or_newline_in_a_segment_is_refused():
    script = load_spoken_script(SPOKEN_SCRIPT)
    bad_marker = dataclasses.replace(
        script,
        segments=tuple(
            dataclasses.replace(s, text="坏<#0.333#>标记。") if s.id == "S01" else s
            for s in script.segments
        ),
    )
    try:
        _verify(bad_marker)
    except SpokenScriptError as exc:
        assert "0.333" in str(exc) or "pause" in str(exc).lower()
    else:
        raise AssertionError("an invalid marker must refuse")

    bad_newline = dataclasses.replace(
        script,
        segments=tuple(
            dataclasses.replace(s, text=s.text + "\n多出来的一行") if s.id == "S01" else s
            for s in script.segments
        ),
    )
    try:
        _verify(bad_newline)
    except SpokenScriptError as exc:
        assert "newline" in str(exc)
    else:
        raise AssertionError("a newline inside a segment must refuse")
    print("[ok] 8. marker and newline violations fail verification")


@test
def test_a_wrong_source_digest_or_lock_mismatch_is_refused():
    script = load_spoken_script(SPOKEN_SCRIPT)
    wrong_source = dataclasses.replace(script, source_digest="0" * 64)
    try:
        _verify(wrong_source)
    except SpokenScriptError as exc:
        assert "sha256" in str(exc) or "digest" in str(exc)
    else:
        raise AssertionError("a mismatched source digest must refuse")

    try:
        _verify(script, lock_digest="1" * 64)
    except SpokenScriptError as exc:
        assert "lock" in str(exc)
    else:
        raise AssertionError("a lock/text disagreement must refuse")
    print("[ok] 9. neither a foreign source nor a divergent lock can be used")


@test
def test_sample_paragraph_selection_is_bounded_and_deterministic():
    text = ORIGINAL.read_text(encoding="utf-8")
    paragraphs = split_paragraphs(text)
    assert len(paragraphs) == 6
    sample = sample_original_text(text, (1, 2, 3))
    assert sample == "\n".join(paragraphs[:3])
    try:
        sample_original_text(text, (7,))
    except SpokenScriptError:
        pass
    else:
        raise AssertionError("an out-of-range paragraph must refuse")
    print("[ok] 10. sample paragraph selection is explicit and bounded")


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
    print(f"\nAll {total} spoken-script tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
