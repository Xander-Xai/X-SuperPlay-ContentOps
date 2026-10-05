"""M4.6 A/B voice variants — provider-free regression tests.

Both voices are reused from historical artifacts, so these tests make **zero**
provider calls and spend no quota. They check the things that would silently
invalidate the comparison:

1. voice provenance is decided from evidence, never from a filename
2. the tracked ``shot_00..05.wav`` files are NOT the baseline narration
3. A and B share one visual timeline despite different audio lengths
4. only the declared variables differ between the arms
5. the Evidence Lock still holds and no arm touches it
6. both arms are unapproved, with zero provider calls
7. receipts carry portable paths only
8. the stale baseline is never used as a stand-in

Skipped rather than failed when the historical voice artifacts are absent, because a
clean checkout has no ``.verify-tmp`` and the media binaries are gitignored. What is
never skipped is anything checkable from committed state.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.golden.evidence_lock import structural_fingerprint  # noqa: E402
from contentops.golden.identity import compare_evidence_identity  # noqa: E402

EXPERIMENT = ROOT / "projects" / "easel-enhanced-golden"
BASELINE = ROOT / "projects" / "easel-review"
LOCK = EXPERIMENT / "evidence" / "evidence-lock.json"
A_VOICE = ROOT / ".verify-tmp/m2/ab/A-edge-tts.mp3"
B_VOICE = ROOT / ".verify-tmp/m2/ab/B-minimax-mplan.wav"
B_RECEIPT = ROOT / ".verify-tmp/m2/narration/receipt-golden-b.json"
RENDER_AUDIO = BASELINE / "assets" / "voice_easel" / "narration.mp3"

TESTS: List = []


def test(fn):
    TESTS.append(fn)
    return fn


def _skip(number: int, what: str, need: str) -> None:
    print(f"[skip] {number}. {what} (needs {need})")


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# --- 1. voice provenance ----------------------------------------------------


@test
def test_a_is_not_trusted_because_of_its_filename():
    """A is classified from byte-identity with the file the pinned render consumed.

    Not from being called ``A-edge-tts.mp3``. The historical render's storyboard names
    ``assets/voice_easel/narration.mp3`` as its narration, and the audit requires this
    candidate to be byte-identical to it. If that identity fails, A must fall back to
    reconstruction with the weaker label rather than quietly keep the strong one.
    """
    if not A_VOICE.is_file() or not RENDER_AUDIO.is_file():
        _skip(1, "A voice provenance", "historical voice artifacts")
        return
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "scripts"))
    from build_golden_variant_ab import select_a_voice

    selection = select_a_voice()
    assert selection.provenance_class == "CONSISTENT_HISTORICAL_BASELINE", (
        selection.provenance_class
    )
    assert selection.justification["byte_identical_to_render_input"] is True
    assert selection.justification["measurements_agree_with_issue_19"] is True
    assert selection.provider_calls == 0, "A was generated instead of reused"
    assert "No surviving machine receipt" in selection.justification["limitation"], (
        "A must record that no receipt binds it to the locked narration text"
    )
    print("[ok] 1. A is classified by byte-identity, not by filename")


@test
def test_a_is_never_called_a_verified_original():
    """A has no machine receipt binding it to the locked narration text.

    B does. Asserting the distinction is the point: if A were ever labelled
    ``VERIFIED_CURRENT_BASELINE`` on the strength of the file's name, the two arms
    would appear to have equivalent provenance when they do not.
    """
    if not A_VOICE.is_file() or not B_VOICE.is_file():
        _skip(2, "provenance asymmetry", "historical voice artifacts")
        return
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "scripts"))
    from build_golden_variant_ab import select_a_voice, select_b_voice

    a, b = select_a_voice(), select_b_voice()
    assert a.provenance_class != "VERIFIED_CURRENT_BASELINE"
    assert b.provenance_class == "VERIFIED_CURRENT_BASELINE"
    print("[ok] 2. A and B carry honestly different provenance classes")


@test
def test_the_tracked_per_shot_wavs_are_not_the_baseline():
    """``shot_00..05.wav`` are in Git, and that is not evidence they are the narration.

    They are ~4-5 s per shot at 22.05 kHz and total roughly 28 s, against a locked
    narration of ~62 s at 24 kHz. Calling them the baseline because they happen to be
    tracked would have silently swapped the whole voice stack.
    """
    shots_dir = BASELINE / "assets" / "voice"
    if not shots_dir.is_dir():
        _skip(3, "per-shot WAVs are not the baseline", "the historical voice dir")
        return
    from contentops.media.transport import ffprobe_json

    total = 0.0
    rates = set()
    for path in sorted(shots_dir.glob("shot_*.wav")):
        facts = ffprobe_json(path)
        total += float(facts.get("format", {}).get("duration", 0))
        audio = next(
            (s for s in facts.get("streams", []) if s.get("codec_type") == "audio"), {}
        )
        rates.add(int(audio.get("sample_rate", 0)))

    assert total < 45, (
        f"the per-shot WAVs total {total:.1f}s, which is too close to the 61.9s "
        f"narration to dismiss as fragments. Re-examine before assuming."
    )
    assert 24000 not in rates or len(rates) > 1, (
        "the per-shot files share the narration's sample rate; re-examine"
    )
    if A_VOICE.is_file():
        assert _sha(A_VOICE) not in {_sha(p) for p in shots_dir.glob("shot_*.wav")}, (
            "a per-shot WAV is byte-identical to the baseline narration"
        )
    print(f"[ok] 3. per-shot WAVs total {total:.1f}s and are not the 61.9s narration")


@test
def test_b_reuse_proves_every_required_gate():
    """Reuse is proven, not assumed. Each PHASE 5 gate is checked explicitly."""
    if not B_VOICE.is_file() or not B_RECEIPT.is_file():
        _skip(4, "B reuse gates", "the historical B receipt")
        return
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "scripts"))
    from build_golden_variant_ab import select_b_voice

    selection = select_b_voice()
    checks = selection.justification["checks"]
    failed = [name for name, ok in checks.items() if not ok]
    assert not failed, f"B reuse gates failing: {failed}"
    assert selection.provider_calls == 0, "B was generated instead of reused"
    assert checks["payg_not_used"] is True
    assert checks["credit_pack_not_used"] is True
    assert checks["subscription_generation"] is True
    assert checks["not_production_ready_without_review"] is True
    print(f"[ok] 4. B reuse proves {len(checks)} gates with 0 provider calls")


@test
def test_b_receipt_text_binding_is_the_locked_narration_and_says_so():
    """The receipt's text digest is the *normalised* form, not the raw file digest.

    They are different strings over different transformations. Recording that
    distinction is what stops someone later concluding the receipt contradicts the lock,
    or worse, that the two digests are interchangeable.
    """
    if not B_RECEIPT.is_file():
        _skip(5, "B text binding", "the historical B receipt")
        return
    receipt = _load(B_RECEIPT)
    lock = _load(LOCK)
    text = (BASELINE / "script" / "narration.txt").read_text(encoding="utf-8")
    normalized = "\n".join(l for l in text.splitlines() if l.strip())

    import hashlib

    assert receipt["display_text_sha256"] == hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest(), "the receipt text is not the locked narration in normalised form"
    assert receipt["display_text_sha256"] != lock["narration_text_sha256"], (
        "if these were equal the normalisation distinction would be untested"
    )
    print("[ok] 5. B's receipt text binding is the locked narration, normalised")


@test
def test_default_srt_is_not_used_as_a_substitute():
    """It is a different and shorter asset; substituting it would look plausible."""
    other = BASELINE / "assets" / "captions" / "default.srt"
    canonical = EXPERIMENT / "evidence" / "captions" / "easel.srt"
    if not other.is_file() or not canonical.is_file():
        _skip(6, "default.srt is not a substitute", "both caption files")
        return
    assert _sha(other) != _sha(canonical)
    assert other.stat().st_size < canonical.stat().st_size
    print("[ok] 6. default.srt is a different, shorter asset and is not used")


# --- 2. the arms ------------------------------------------------------------


def _variant(variant_id: str) -> Path:
    return EXPERIMENT / "variants" / variant_id


@test
def test_both_arms_share_one_visual_timeline():
    """The confound this stage exists to prevent.

    Upstream divides each arm's narration length across the shots when no explicit
    duration is given. A is 61.920 s and B is 61.768 s, so without explicit durations
    the two arms would have had different shot boundaries and any perceived difference
    would be partly a timing artefact.
    """
    storyboards = {}
    for variant_id in ("A", "B"):
        path = _variant(variant_id) / "script" / "storyboard.json"
        if not path.is_file():
            _skip(7, "shared visual timeline", "a local A/B build")
            return
        storyboards[variant_id] = _load(path)

    durations_a = [shot["duration"] for shot in storyboards["A"]["shots"]]
    durations_b = [shot["duration"] for shot in storyboards["B"]["shots"]]
    assert durations_a == durations_b, (
        f"per-shot durations differ: A={durations_a} B={durations_b}"
    )
    assert all(value is not None for value in durations_a), (
        "a shot has no explicit duration, so upstream would derive it from the "
        "narration length and the arms would drift apart"
    )
    print(f"[ok] 7. both arms share explicit per-shot durations {durations_a[0]}s")


@test
def test_only_the_declared_variables_differ():
    """Recomputed, not declared. A gate that only echoes the plan proves nothing."""
    from build_golden_variant_ab import (
        ARM_LOCAL_STORYBOARD_KEYS, visual_structure,
    )

    storyboards = {}
    for variant_id in ("A", "B"):
        path = _variant(variant_id) / "script" / "storyboard.json"
        if not path.is_file():
            _skip(8, "only declared variables differ", "a local A/B build")
            return
        storyboards[variant_id] = _load(path)

    a, b = storyboards["A"], storyboards["B"]
    assert structural_fingerprint(visual_structure(a)) == structural_fingerprint(
        visual_structure(b)
    ), "visual structure differs between arms"

    for index, (left, right) in enumerate(zip(a["shots"], b["shots"])):
        for key in ("image", "source", "source_type", "duration", "motion"):
            assert left.get(key) == right.get(key), (
                f"shot {index} field {key!r} differs: {left.get(key)!r} vs "
                f"{right.get(key)!r}"
            )
    # The declared variable is expressed through exactly these three fields.
    assert a.get("voice_provider") != b.get("voice_provider")
    assert a["narration"] != b["narration"]
    for key in ARM_LOCAL_STORYBOARD_KEYS:
        assert key not in visual_structure(a), f"{key} was not stripped"
    print("[ok] 8. only narration, subtitle and voice_provider differ")


@test
def test_both_arms_render_the_same_length_from_the_same_caption():
    if not (A_VOICE.is_file() or B_VOICE.is_file()):
        _skip(9, "identical rendered length", "a local A/B build")
        return
    receipts = {}
    for variant_id in ("A", "B"):
        path = _variant(variant_id) / "receipts" / "variant-receipt.json"
        if not path.is_file():
            _skip(9, "identical rendered length", "a local A/B build")
            return
        receipts[variant_id] = _load(path)

    duration_a = receipts["A"]["compose"].get("media", {}).get("duration_s")
    duration_b = receipts["B"]["compose"].get("media", {}).get("duration_s")
    assert duration_a == duration_b, (
        f"rendered durations differ: A={duration_a}s B={duration_b}s. A 0.15s audio "
        f"difference must not move the video."
    )
    lock = _load(LOCK)
    for variant_id, receipt in receipts.items():
        assert receipt["caption_sha256"] == lock["caption_sha256"], variant_id
    print(f"[ok] 9. both arms render {duration_a}s and burn the identical caption")


# --- 3. the human gate ------------------------------------------------------


@test
def test_neither_arm_claims_readiness_or_a_winner():
    for variant_id in ("A", "B"):
        path = _variant(variant_id) / "receipts" / "variant-receipt.json"
        if not path.is_file():
            _skip(10, "no arm claims readiness", "a local A/B build")
            return
        receipt = _load(path)
        assert receipt["production_ready"] is False, variant_id
        assert receipt["human_review"] == "PENDING_FOUNDER_REVIEW", variant_id
        assert receipt["support_assets"] == [], variant_id
        assert receipt["generated_image_shas"] == [], variant_id
        assert receipt["h3_shas"] == [], variant_id
        assert receipt["provider_call_count"] == {
            "speech": 0, "image": 0, "video": 0
        }, variant_id
    print("[ok] 10. neither arm is approved, and neither carries support media")


@test
def test_the_preflight_package_is_neutral():
    """A preflight, not a winner request. No ranking language, no implied preference."""
    path = EXPERIMENT / "review" / "ab-preflight.md"
    if not path.is_file():
        _skip(11, "neutral preflight", "a local A/B build")
        return
    text = path.read_text(encoding="utf-8").replace("Enhanced Golden", "")
    for adjective in (
        "improved", "improvement", "better", "best", "advanced", "superior",
        "premium", "winner", "wins", "preferred", "recommended", "stronger",
    ):
        assert adjective not in text.lower(), (
            f"the preflight package uses {adjective!r}, which decides the comparison "
            f"before a reviewer has listened"
        )
    assert "PENDING_FOUNDER_REVIEW" in text
    assert "does not request a selection and implies none" in text.lower(), (
        "the preflight must state that it requests no selection"
    )
    print("[ok] 11. the A/B preflight package is neutral")


@test
def test_receipts_carry_no_machine_paths():
    for variant_id in ("A", "B"):
        receipt = _variant(variant_id) / "receipts" / "variant-receipt.json"
        if not receipt.is_file():
            _skip(12, "receipts are portable", "a local A/B build")
            return
        blob = json.dumps(_load(receipt), ensure_ascii=False)
        assert not re.search(
            r"(?<![A-Za-z])[A-Za-z]:[\\/]{1,2}[A-Za-z0-9_.\-]", blob
        ), blob[:300]
    print("[ok] 12. variant receipts carry no machine absolute path")


@test
def test_the_evidence_lock_is_untouched_by_the_ab_build():
    """The arms consume the lock; they must not rewrite it.

    If a build could alter the lock, then "evidence identical across arms" would be
    unfalsifiable — both arms would simply be reading whatever the last build left.
    """
    if not LOCK.is_file():
        _skip(13, "the lock is untouched", "no lock written")
        return
    before = LOCK.read_bytes()
    lock = _load(LOCK)
    assert lock["fixture"] is False
    assert lock["fingerprint"] == "af8128b958906e8ebb1f6b4c21038f4fe9d2446bbba45823c90dae53fd4a4511", (
        "the production lock fingerprint changed; the baseline moved under us"
    )
    for variant_id in ("A", "B"):
        receipt = _variant(variant_id) / "receipts" / "variant-receipt.json"
        if receipt.is_file():
            assert _load(receipt)["evidence_lock_fingerprint"] == lock["fingerprint"]
    assert LOCK.read_bytes() == before, "the lock file changed during inspection"
    print("[ok] 13. the Evidence Lock is unchanged and referenced by both arms")


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
    print(f"All {len(TESTS)} M4.6 A/B voice variant tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())