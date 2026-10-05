"""M4.6 Enhanced Golden infrastructure — provider-free.

Every test here runs on fixtures. No MiniMax speech, image or H3 request is made,
no quota is spent, and no fixture result is reported as the real Golden. That last
part is the one worth being pedantic about: the fixtures produce a structurally
identical EvidenceLock and a structurally identical set of variant receipts, so the
only thing separating a test result from a reported experiment is the ``fixture``
flag travelling with both. These tests assert that flag is present and that a
fixture lock cannot be promoted to production.

What is covered
---------------
1.  the nested A/B/C/D model and that each step changes exactly one variable
2.  the evidence lock freezes script, narration text, storyboard and captions
3.  a generated asset can never occupy a factual placement
4.  B/C/D narration reuse, C/D image reuse
5.  the H3 cap
6.  every dirty-experiment guard refuses by name
7.  declared changes are checked against recomputed actual changes
8.  cross-arm evidence identity
9.  the Founder package is neutral, and A and NONE remain available
10. no arm can claim production readiness
11. receipts carry portable paths only

Run standalone with ``python tests/test_enhanced_golden.py``.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.golden.evidence_lock import (  # noqa: E402
    EVIDENCE_LOCK_SCHEMA,
    EvidenceAsset,
    EvidenceLock,
    EvidenceLockError,
    assert_production_lock,
    build_evidence_lock,
    structural_fingerprint,
)
from contentops.golden.identity import compare_evidence_identity  # noqa: E402
from contentops.golden.review import (  # noqa: E402
    ALLOWED_SELECTIONS,
    PENDING,
    FounderReview,
    ReviewPackageError,
    render_review_markdown,
)
from contentops.golden.variant import (  # noqa: E402
    MAX_H3_INSERTS,
    SUPPORT_LAYER_ROLE,
    VARIANT_IDS,
    VARIANT_SPECS,
    DirtyExperimentError,
    EnhancedGoldenBuilder,
    VariantPlan,
    compute_variant_diff,
)
from contentops.media.media_paths import serialize_media_path  # noqa: E402

TESTS: List[Any] = []


def test(fn):
    TESTS.append(fn)
    return fn


def _skip(number: int, what: str, need: str) -> None:
    print(f"[skip] {number}. {what} (needs {need})")


# --- fixtures ----------------------------------------------------------------


def _png(path: Path) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (240, 426), (40, 60, 90)).save(path, format="PNG")
    return path


def _wav(path: Path, seed: int) -> Path:
    """A tiny deterministic WAV. Not speech; it stands in for an audio asset."""
    import math
    import struct
    import wave

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        frames = bytearray()
        for index in range(8000):
            value = int(6000 * math.sin(2 * math.pi * 220 * index / 8000 + seed))
            frames += struct.pack("<h", value)
        handle.writeframes(bytes(frames))
    return path


def _make_baseline(root: Path, *, evidence_count: int = 4) -> Dict[str, Any]:
    """A miniature baseline project: script, narration text, storyboard, shots."""
    project = root / "baseline"
    shots_dir = project / "sources" / "screenshots"
    (project / "script").mkdir(parents=True, exist_ok=True)

    (project / "script" / "master.md").write_text(
        "# Fixture baseline script\n\nFactual claims live here.\n", encoding="utf-8"
    )
    (project / "script" / "narration.txt").write_text(
        "doctor reports green\nversion is pinned\nskills are layered\nping is ok\n",
        encoding="utf-8",
    )

    shots: List[Dict[str, Any]] = []
    asset_paths: Dict[str, Path] = {}
    for index in range(evidence_count):
        name = f"shot_{index:02d}-evidence.png"
        path = _png(shots_dir / name)
        shots.append({
            "shot_id": f"shot_{index:02d}",
            "image": f"sources/screenshots/{name}",
            "source_type": "real_screenshot",
        })
        asset_paths[f"shot_{index:02d}"] = path

    (project / "script" / "storyboard.json").write_text(
        json.dumps({"size": "1080x1920", "shots": shots}, indent=2), encoding="utf-8"
    )
    (project / "assets" / "captions").mkdir(parents=True, exist_ok=True)
    (project / "assets" / "captions" / "captions.srt").write_text(
        "1\n00:00:00,000 --> 00:00:02,000\ndoctor reports green\n\n",
        encoding="utf-8",
    )
    return {
        "project": project,
        "shots_dir": shots_dir,
        "asset_paths": asset_paths,
        "storyboard": project / "script" / "storyboard.json",
    }


def _resolver_for(project: Path):
    def resolve(local: Path) -> str:
        reference = serialize_media_path(
            Path(local), repo_root=project, project_root=project
        )
        if reference is None:
            raise ValueError(f"{local} is not under {project}")
        return reference

    return resolve


def _fixture_lock(root: Path, *, evidence_count: int = 4) -> EvidenceLock:
    base = _make_baseline(root, evidence_count=evidence_count)
    return build_evidence_lock(
        source_project="project://fixture-baseline",
        master_script_path=base["project"] / "script" / "master.md",
        narration_text_path=base["project"] / "script" / "narration.txt",
        storyboard_path=base["storyboard"],
        caption_path=base["project"] / "assets" / "captions" / "captions.srt",
        asset_paths=base["asset_paths"],
        resolve_logical=_resolver_for(base["project"]),
        fixture=True,
    )


def _repo_resolver_for(root: Path):
    """One resolver for the whole fixture tree.

    ``repo_root`` is the fixture root and ``project_root`` the baseline project, so
    baseline evidence serialises as ``project://`` and the voice/support assets as
    ``repo://``. Using one root for both serialise and resolve is the point: an
    earlier version mixed them, every ``repo://`` reference resolved against the
    project directory instead, and the failure surfaced as a confusing
    "does not resolve to a file" rather than as a root mismatch.
    """
    project = root / "baseline"

    def resolve(logical: str) -> Path:
        from contentops.media.media_paths import resolve_media_path

        return resolve_media_path(
            logical, repo_root=root, project_root=project
        )

    return resolve


def _to_logical(root: Path):
    def convert(local: Path) -> str:
        reference = serialize_media_path(
            Path(local), repo_root=root, project_root=root / "baseline"
        )
        if reference is None:
            raise ValueError(f"{local} is not under {root}")
        return reference

    return convert


def _arm_voices(root: Path) -> Dict[str, Path]:
    """One baseline voice for A, one shared MiniMax voice for B, C and D.

    Sharing is the experiment's premise, so the fixture has to honour it. An earlier
    version handed each arm its own file and the reuse guard correctly refused the
    build — the fixture was wrong, not the guard.
    """
    baseline = _wav(root / "v" / "baseline.wav", 0)
    shared = _wav(root / "v" / "minimax-shared.wav", 1)
    return {"A": baseline, "B": shared, "C": shared, "D": shared}


def _builder(root: Path, *, lock: EvidenceLock, narration: Dict[str, Path],
             support: Dict[str, List[Dict[str, Any]]] | None = None) -> EnhancedGoldenBuilder:
    convert = _to_logical(root)
    builder = EnhancedGoldenBuilder(
        lock=lock,
        narration_assets={key: convert(value) for key, value in narration.items()},
        support_assets=support or {},
    )
    builder.set_resolver(_repo_resolver_for(root))
    return builder


def _support(anchor: str, path: Path, *, modality: str, digest: str,
             purpose: str) -> Dict[str, Any]:
    return {
        "anchor": anchor,
        "asset_path": f"project://support/{path.name}",
        "asset_sha256": digest,
        "modality": modality,
        "purpose": purpose,
        "evidence_use": SUPPORT_LAYER_ROLE,
    }


# --- 1. the nested variant model --------------------------------------------


@test
def test_the_four_arms_are_nested_single_variable_steps():
    """Each arm changes exactly one thing relative to the arm below it.

    If this is not true the experiment cannot attribute an outcome to a variable, and
    an unattributable result is worse than no result because it invites a policy
    decision.
    """
    assert list(VARIANT_SPECS) == list(VARIANT_IDS)
    assert VARIANT_SPECS["A"].base is None
    for variant_id, expected_base in (("B", "A"), ("C", "B"), ("D", "C")):
        assert VARIANT_SPECS[variant_id].base == expected_base, variant_id

    # A changes nothing at all.
    assert VARIANT_SPECS["A"].narration == "baseline"
    assert VARIANT_SPECS["A"].generated_images == 0
    assert VARIANT_SPECS["A"].h3_inserts == 0

    # B changes narration only.
    b = VARIANT_SPECS["B"]
    assert b.narration == "minimax" and b.generated_images == 0 and b.h3_inserts == 0

    # C adds an image, and keeps B's narration.
    c = VARIANT_SPECS["C"]
    assert c.narration == b.narration and c.generated_images == 1 and c.h3_inserts == 0

    # D adds H3, and keeps B's narration and C's image count.
    d = VARIANT_SPECS["D"]
    assert d.narration == b.narration and d.generated_images == 1 and d.h3_inserts == 1
    assert d.h3_inserts <= MAX_H3_INSERTS
    print("[ok] 1. A/B/C/D is nested and each step changes one variable")


# --- 2. the evidence lock ----------------------------------------------------


@test
def test_the_lock_freezes_script_narration_storyboard_and_captions():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lock = _fixture_lock(root)
        body = lock.as_dict()
        assert body["schema"] == EVIDENCE_LOCK_SCHEMA
        assert body["fixture"] is True, "a fixture lock must declare itself"
        for field_name in (
            "master_script_sha256", "narration_text_sha256",
            "storyboard_fingerprint", "caption_sha256",
        ):
            assert body[field_name], field_name
        assert len(lock.evidence) == 4, lock.evidence
        # Changing the script must change the fingerprint, and the asset digest must
        # not care: those are two different questions.
        before = lock.fingerprint()
        (root / "baseline" / "script" / "master.md").write_text(
            "# changed\n", encoding="utf-8"
        )
        after = EvidenceLock(
            source_project=lock.source_project,
            master_script_sha256="0" * 64,
            narration_text_sha256=lock.narration_text_sha256,
            storyboard_fingerprint=lock.storyboard_fingerprint,
            caption_sha256=lock.caption_sha256,
            evidence=lock.evidence,
            fixture=True,
        )
        assert after.fingerprint() != before
        assert after.asset_digest() == lock.asset_digest()
    print("[ok] 2. the lock freezes script, narration text, storyboard and captions")


@test
def test_a_lock_with_no_resolver_or_no_assets_is_refused():
    """A lock that cannot produce portable refs, or that locks nothing, is refused."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        base = _make_baseline(root)
        common = dict(
            source_project="project://fixture",
            master_script_path=base["project"] / "script" / "master.md",
            narration_text_path=base["project"] / "script" / "narration.txt",
            storyboard_path=base["storyboard"],
        )
        for kwargs, expect_code in (
            ({"asset_paths": base["asset_paths"]}, "LOGICAL_RESOLVER_MISSING"),
            (
                {"asset_paths": {}, "resolve_logical": _resolver_for(base["project"])},
                "LOCK_HAS_NO_ASSETS",
            ),
        ):
            try:
                build_evidence_lock(**common, **kwargs)
            except EvidenceLockError as exc:
                assert exc.code == expect_code, f"{exc.code} != {expect_code}"
            else:
                raise AssertionError(f"a lock was built despite {expect_code}")
        # A declared asset that does not exist must not be silently dropped.
        ghost = dict(base["asset_paths"])
        ghost["shot_99"] = base["project"] / "sources" / "screenshots" / "ghost.png"
        try:
            build_evidence_lock(
                **common, asset_paths=ghost,
                resolve_logical=_resolver_for(base["project"]),
            )
        except EvidenceLockError as exc:
            assert exc.code == "LOCK_ASSET_MISSING", exc.code
        else:
            raise AssertionError("a lock silently omitted a missing evidence asset")
    print("[ok] 3. a lock needs a resolver, needs assets, and keeps missing ones")


@test
def test_a_fixture_lock_cannot_be_promoted_to_production():
    """The one check standing between a test result and a reported experiment."""
    with tempfile.TemporaryDirectory() as td:
        lock = _fixture_lock(Path(td))
        try:
            assert_production_lock(lock)
        except EvidenceLockError as exc:
            assert exc.code == "FIXTURE_LOCK_IS_NOT_PRODUCTION", exc.code
        else:
            raise AssertionError("a fixture lock passed the production assertion")

        # And a non-fixture lock of the same shape passes, so the guard is not just
        # refusing everything.
        production = EvidenceLock(
            source_project=lock.source_project,
            master_script_sha256=lock.master_script_sha256,
            narration_text_sha256=lock.narration_text_sha256,
            storyboard_fingerprint=lock.storyboard_fingerprint,
            caption_sha256=lock.caption_sha256,
            evidence=lock.evidence,
            fixture=False,
        )
        assert_production_lock(production)
    print("[ok] 4. a fixture lock is refused where production is required")


@test
def test_claim_refs_are_recorded_empty_rather_than_invented():
    """No Claim Ledger exists yet, so the field is empty and says so."""
    with tempfile.TemporaryDirectory() as td:
        lock = _fixture_lock(Path(td))
        for asset in lock.evidence:
            assert asset.claim_refs == [], asset
        body = lock.as_dict()
        assert "NOT_AVAILABLE" in body["claim_ledger_status"], body["claim_ledger_status"]
    print("[ok] 5. claim_refs are empty and declared unavailable, not invented")


# --- 3. generated media may never occupy a factual slot ----------------------


@test
def test_generated_media_cannot_occupy_a_factual_placement():
    """The rule that keeps C and D honest.

    The baseline is real screenshots, each the picture a sentence points at. A
    generated image in one of those slots would look fine and assert things nobody
    verified. Support insertions must therefore name a relationship to a placement,
    never be one.
    """
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lock = _fixture_lock(root)
        baseline_voice = _wav(root / "voice" / "baseline.wav", 0)
        mmx_voice = _wav(root / "voice" / "minimax.wav", 1)
        support_image = _png(root / "support" / "generated.png")

        # A bare placement id is refused: it reads as a replacement.
        builder = _builder(
            root, lock=lock,
            narration={"A": baseline_voice, "B": mmx_voice, "C": mmx_voice, "D": mmx_voice},
            support={"C": [_support("shot_00", support_image, modality="image",
                                    digest="a" * 64, purpose="decorative")]},
        )
        try:
            builder.plan("C")
        except DirtyExperimentError as exc:
            assert exc.code == "SUPPORT_ANCHOR_MUST_BE_RELATIONAL", exc.code
        else:
            raise AssertionError("a generated asset was allowed to take a factual slot")

        # A relational anchor is accepted.
        ok = _builder(
            root, lock=lock,
            narration={"A": baseline_voice, "B": mmx_voice, "C": mmx_voice, "D": mmx_voice},
            support={"C": [_support("follows:shot_00", support_image, modality="image",
                                    digest="a" * 64, purpose="abstract transition")]},
        )
        plan = ok.plan("C")
        assert len(plan.support) == 1
        assert plan.support[0].evidence_use == SUPPORT_LAYER_ROLE
        assert plan.lock.asset_digest() == lock.asset_digest(), (
            "a support insertion must not touch the evidence timeline"
        )

        # An anchor to an unknown placement is refused.
        bad = _builder(
            root, lock=lock,
            narration={"A": baseline_voice, "B": mmx_voice, "C": mmx_voice, "D": mmx_voice},
            support={"C": [_support("follows:shot_99", support_image, modality="image",
                                    digest="a" * 64, purpose="x")]},
        )
        try:
            bad.plan("C")
        except DirtyExperimentError as exc:
            assert exc.code == "SUPPORT_ANCHOR_UNKNOWN_PLACEMENT", exc.code
        else:
            raise AssertionError("a support insert anchored to a phantom placement")

        # A support asset claiming an evidence role is refused outright.
        escalating = _support("follows:shot_00", support_image, modality="image",
                              digest="a" * 64, purpose="pretend to be evidence")
        escalating["evidence_use"] = "EVIDENCE"
        overreach = _builder(
            root, lock=lock,
            narration={"A": baseline_voice, "B": mmx_voice, "C": mmx_voice, "D": mmx_voice},
            support={"C": [escalating]},
        )
        try:
            overreach.plan("C")
        except DirtyExperimentError as exc:
            assert exc.code == "GENERATED_REPLACED_EVIDENCE", exc.code
        else:
            raise AssertionError("generated media was allowed an evidence role")
    print("[ok] 6. generated media can never occupy a factual placement")


# --- 4. reuse rules ----------------------------------------------------------


@test
def test_b_c_and_d_share_one_narration_asset():
    """Sharing is a property of the build, not a claim in a document."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lock = _fixture_lock(root)
        baseline_voice = _wav(root / "voice" / "baseline.wav", 0)
        mmx_voice = _wav(root / "voice" / "minimax.wav", 1)
        other_voice = _wav(root / "voice" / "other.wav", 2)

        shared = _builder(
            root, lock=lock,
            narration={"A": baseline_voice, "B": mmx_voice, "C": mmx_voice, "D": mmx_voice},
            support={
                "C": [_support("follows:shot_00", _png(root / "s" / "g.png"),
                               modality="image", digest="b" * 64, purpose="support")],
                "D": [_support("follows:shot_00", _png(root / "s" / "g2.png"),
                               modality="image", digest="b" * 64, purpose="support"),
                      _support("precedes:shot_01", _png(root / "s" / "h3.png"),
                               modality="video", digest="c" * 64, purpose="hook")],
            },
        )
        digests = {vid: shared.plan(vid).narration_sha256 for vid in ("B", "C", "D")}
        assert len(set(digests.values())) == 1, digests
        assert digests["B"] != shared.plan("A").narration_sha256

        # D using a different narration is refused.
        mismatched = _builder(
            root, lock=lock,
            narration={"A": baseline_voice, "B": mmx_voice, "C": other_voice, "D": other_voice},
            support={
                "C": [_support("follows:shot_00", _png(root / "s" / "g.png"),
                               modality="image", digest="b" * 64, purpose="support")],
                "D": [_support("follows:shot_00", _png(root / "s" / "g2.png"),
                               modality="image", digest="b" * 64, purpose="support")],
            },
        )
        try:
            mismatched.plan("C")
        except DirtyExperimentError as exc:
            assert exc.code == "B_C_D_NARRATION_MISMATCH", exc.code
        else:
            raise AssertionError("C was allowed a different narration from B")
    print("[ok] 7. B, C and D share one narration asset and a mismatch is refused")


@test
def test_d_reuses_c_s_exact_image():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lock = _fixture_lock(root)
        voices = _arm_voices(root)
        image_a = _png(root / "s" / "a.png")
        image_b = _png(root / "s" / "b.png")

        reused = _builder(
            root, lock=lock, narration=voices,
            support={
                "C": [_support("follows:shot_00", image_a, modality="image",
                               digest="d" * 64, purpose="support")],
                "D": [_support("follows:shot_00", image_b, modality="image",
                               digest="d" * 64, purpose="support")],
            },
        )
        assert reused.plan("D").support[0].asset_sha256 == "d" * 64

        diverged = _builder(
            root, lock=lock, narration=voices,
            support={
                "C": [_support("follows:shot_00", image_a, modality="image",
                               digest="d" * 64, purpose="support")],
                "D": [_support("follows:shot_00", image_b, modality="image",
                               digest="e" * 64, purpose="support")],
            },
        )
        try:
            diverged.plan("D")
        except DirtyExperimentError as exc:
            assert exc.code == "C_D_IMAGE_MISMATCH", exc.code
        else:
            raise AssertionError("D was allowed a different image from C")
    print("[ok] 8. D must reuse C's exact generated image")


@test
def test_the_h3_cap_is_enforced():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lock = _fixture_lock(root)
        voices = _arm_voices(root)
        support: Dict[str, List[Dict[str, Any]]] = {
            "C": [_support("follows:shot_00", _png(root / "s" / "g.png"),
                           modality="image", digest="d" * 64, purpose="support")],
            # D keeps C's image, then adds one insert too many. Including the image
            # matters: without it the reuse guard fires first and the cap is never
            # reached, so the test would pass without ever testing the cap.
            "D": [_support("follows:shot_00", _png(root / "s" / "g-copy.png"),
                           modality="image", digest="d" * 64, purpose="support")],
        }
        for index in range(MAX_H3_INSERTS + 1):
            support["D"].append(
                _support(f"precedes:shot_{index:02d}", _png(root / "s" / f"h{index}.png"),
                         modality="video", digest="f" * 64, purpose="insert")
            )
        builder = _builder(root, lock=lock, narration=voices, support=support)
        try:
            builder.plan("D")
        except DirtyExperimentError as exc:
            assert exc.code == "TOO_MANY_H3_INSERTS", exc.code
            assert str(MAX_H3_INSERTS) in exc.detail
        else:
            raise AssertionError("the H3 cap was not enforced")
    print("[ok] 9. the H3 insert cap is enforced")


# --- 5. the difference engine ------------------------------------------------


@test
def test_the_difference_engine_recomputes_rather_than_trusting_declarations():
    """Declared differences are recorded next to computed ones, not instead of them."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lock = _fixture_lock(root)
        voices = _arm_voices(root)
        builder = _builder(
            root, lock=lock, narration=voices,
            support={
                "C": [_support("follows:shot_00", _png(root / "s" / "g.png"),
                               modality="image", digest="d" * 64, purpose="support")],
                "D": [_support("follows:shot_00", _png(root / "s" / "g2.png"),
                               modality="image", digest="d" * 64, purpose="support"),
                      _support("precedes:shot_01", _png(root / "s" / "h3.png"),
                               modality="video", digest="c" * 64, purpose="hook",
                               )],
            },
        )
        diff_c = compute_variant_diff(builder.plan("C"), builder.plan("B"))
        assert diff_c["declared_changes"]["support_images_added"] == 1
        assert len(diff_c["actual_asset_changes"]["images_added"]) == 1
        assert diff_c["actual_narration_changes"]["changed"] is False
        assert diff_c["actual_evidence_changes"]["changed"] is False

        diff_d = compute_variant_diff(builder.plan("D"), builder.plan("C"))
        assert diff_d["declared_changes"]["h3_inserts_added"] == 1
        assert len(diff_d["actual_asset_changes"]["h3_added"]) == 1
        assert diff_d["actual_asset_changes"]["images_added"] == []
        assert diff_d["actual_narration_changes"]["changed"] is False
    print("[ok] 10. the difference engine recomputes actual changes")


@test
def test_an_undeclared_asset_difference_refuses_the_build():
    """Sneaking a second image into C must fail the build, not the review."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lock = _fixture_lock(root)
        voices = _arm_voices(root)
        sneaky = _builder(
            root, lock=lock, narration=voices,
            support={"C": [
                _support("follows:shot_00", _png(root / "s" / "one.png"),
                         modality="image", digest="1" * 64, purpose="declared"),
                _support("follows:shot_01", _png(root / "s" / "two.png"),
                         modality="image", digest="2" * 64, purpose="undeclared"),
            ]},
        )
        try:
            sneaky.build("C")
        except DirtyExperimentError as exc:
            assert exc.code == "UNDECLARED_ASSET_DIFFERENCE", exc.code
        else:
            raise AssertionError("an undeclared second image was built")
    print("[ok] 11. an undeclared asset difference refuses the build")


@test
def test_a_changed_evidence_sha_refuses_the_build():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lock = _fixture_lock(root)
        voices = _arm_voices(root)
        builder = _builder(root, lock=lock, narration=voices)
        plan = builder.plan("B")
        # A drifted lock, built separately. Mutating the shared lock in place would
        # have drifted every arm at once and made the comparison vacuous, so the
        # drifted copy stands alone the way a rebuilt experiment would.
        drifted = EvidenceLock(
            source_project=lock.source_project,
            master_script_sha256=lock.master_script_sha256,
            narration_text_sha256=lock.narration_text_sha256,
            storyboard_fingerprint=lock.storyboard_fingerprint,
            caption_sha256=lock.caption_sha256,
            evidence=[
                EvidenceAsset(
                    placement_id=asset.placement_id,
                    asset_path=asset.asset_path,
                    asset_sha256="0" * 64 if index == 0 else asset.asset_sha256,
                    asset_kind=asset.asset_kind,
                    evidence_use=asset.evidence_use,
                    claim_refs=list(asset.claim_refs),
                    source_ref=asset.source_ref,
                )
                for index, asset in enumerate(lock.evidence)
            ],
            fixture=True,
        )
        drifted_plan = VariantPlan(
            spec=VARIANT_SPECS["B"], lock=drifted,
            narration_path=plan.narration_path, narration_sha256=plan.narration_sha256,
        )
        diff = compute_variant_diff(drifted_plan, builder.plan("A"))
        assert diff["actual_evidence_changes"]["changed"] is True
        try:
            builder._enforce_clean(
                VARIANT_SPECS["B"], drifted_plan, builder.plan("A"), diff
            )
        except DirtyExperimentError as exc:
            assert exc.code == "EVIDENCE_SHA_CHANGED", exc.code
        else:
            raise AssertionError("a changed evidence digest did not refuse the build")
    print("[ok] 12. a changed evidence digest refuses the build")


# --- 6. cross-arm identity ---------------------------------------------------


@test
def test_evidence_identity_accepts_identical_arms_and_rejects_drift():
    lock_fields = {
        "placement_id": "shot_00",
        "asset_path": "project://sources/screenshots/shot_00.png",
        "asset_sha256": "a" * 64,
        "asset_kind": "SCREENSHOT",
        "evidence_use": "EVIDENCE",
        "claim_refs": [],
        "source_ref": None,
    }
    identical = {arm: [dict(lock_fields)] for arm in VARIANT_IDS}
    good = compare_evidence_identity(identical)
    assert good["verdict"] == "EXPERIMENT_VALID", good
    assert good["all_identical"] is True
    assert good["placements_compared"] == 1

    drifted = {arm: [dict(lock_fields)] for arm in VARIANT_IDS}
    drifted["D"] = [{**dict(lock_fields), "asset_sha256": "b" * 64}]
    bad = compare_evidence_identity(drifted)
    assert bad["verdict"] == "EXPERIMENT_INVALID", bad
    assert bad["mismatches"], "a digest drift produced no mismatch record"

    removed = {arm: [dict(lock_fields)] for arm in VARIANT_IDS}
    removed["C"] = []
    gone = compare_evidence_identity(removed)
    assert gone["verdict"] == "EXPERIMENT_INVALID"
    assert any(m["kind"] == "EVIDENCE_ASSET_REMOVED" for m in gone["mismatches"])

    replaced = {arm: [dict(lock_fields)] for arm in VARIANT_IDS}
    replaced["B"] = [{**dict(lock_fields), "asset_path": "project://generated/fake.png"}]
    swapped = compare_evidence_identity(replaced)
    assert swapped["verdict"] == "EXPERIMENT_INVALID"
    assert any(m["kind"] == "EVIDENCE_ASSET_REPLACED" for m in swapped["mismatches"])

    # Claim-binding drift is called out under its own name.
    claims = {arm: [dict(lock_fields)] for arm in VARIANT_IDS}
    claims["D"] = [{**dict(lock_fields), "claim_refs": ["claim-1"]}]
    re_claimed = compare_evidence_identity(claims)
    assert re_claimed["verdict"] == "EXPERIMENT_INVALID"
    assert any(m["kind"] == "CLAIM_BINDING_CHANGED" for m in re_claimed["mismatches"])

    # One arm is not a comparison.
    try:
        compare_evidence_identity({"A": [dict(lock_fields)]})
    except ValueError as exc:
        assert "at least two arms" in str(exc), str(exc)
    else:
        raise AssertionError("a single arm was reported as identical across arms")
    print("[ok] 13. cross-arm evidence identity accepts agreement and rejects drift")


# --- 7. receipts and the human gate ------------------------------------------


@test
def test_every_variant_receipt_stays_unapproved_and_fixture_flagged():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lock = _fixture_lock(root)
        voices = _arm_voices(root)
        builder = _builder(
            root, lock=lock, narration=voices,
            support={
                "C": [_support("follows:shot_00", _png(root / "s" / "g.png"),
                               modality="image", digest="d" * 64, purpose="support")],
                "D": [_support("follows:shot_00", _png(root / "s" / "g2.png"),
                               modality="image", digest="d" * 64, purpose="support"),
                      _support("precedes:shot_01", _png(root / "s" / "h3.png"),
                               modality="video", digest="c" * 64, purpose="hook")],
            },
        )
        receipts = {arm: builder.build(arm) for arm in VARIANT_IDS}
        for arm, receipt in receipts.items():
            body = receipt.as_dict()
            assert body["production_ready"] is False, arm
            assert body["human_review"] == PENDING, arm
            assert body["fixture"] is True, arm
            assert body["evidence_lock_fingerprint"] == lock.fingerprint(), arm
            assert body["provider_calls"] == {"speech": 0, "image": 0, "video": 0}, arm

        # A was not composed because no compose callable was supplied, and the
        # receipt says so rather than claiming a render happened.
        assert receipts["A"].compose["status"] == "NOT_COMPOSED"

        # The real comparison, over the receipts.
        identity = compare_evidence_identity({
            arm: receipt.as_dict()["factual_assets"] for arm, receipt in receipts.items()
        })
        assert identity["verdict"] == "EXPERIMENT_VALID", identity
    print("[ok] 14. every variant receipt is unapproved, fixture-flagged, zero calls")


@test
def test_variant_receipts_carry_no_machine_paths():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lock = _fixture_lock(root)
        voices = _arm_voices(root)
        builder = _builder(root, lock=lock, narration=voices)
        blob = json.dumps(builder.build("B").as_dict(), ensure_ascii=False)
        # The negative lookbehind is required, not decorative: without it every
        # ``repo://`` reference matches as drive letter ``o`` plus ``://v`` and the
        # scan reports correct portable paths as leaks. Same trap as the M4.5
        # canonical-artifact scanner.
        assert not re.search(
            r"(?<![A-Za-z])[A-Za-z]:[\\/]{1,2}[A-Za-z0-9_.\-]", blob
        ), blob[:400]
        assert not re.search(r"/home/[A-Za-z0-9_.\-]+/", blob)
        assert str(root) not in blob
        # And the paths it does carry are logical.
        assert "repo://" in blob or "project://" in blob
    print("[ok] 15. variant receipts carry no machine absolute path")


# --- 8. the Founder review package -------------------------------------------


@test
def test_the_review_package_is_neutral_and_keeps_a_and_none_available():
    receipts = {
        arm: {
            "variant_id": arm,
            "declared_changes": {},
            "factual_assets": [],
            "production_ready": False,
            "human_review": PENDING,
        }
        for arm in VARIANT_IDS
    }
    review = FounderReview(
        variant_ids=list(VARIANT_IDS),
        variant_receipts=receipts,
        evidence_identity={"verdict": "EXPERIMENT_VALID", "all_identical": True,
                           "placements_compared": 4, "mismatches": []},
        artifacts={arm: f"project://variants/{arm}/final.mp4" for arm in VARIANT_IDS},
    )
    assert review.selection() == PENDING
    assert "A" in ALLOWED_SELECTIONS and "NONE" in ALLOWED_SELECTIONS

    body = json.dumps(review.as_dict(), ensure_ascii=False)
    markdown = render_review_markdown(review)
    combined = body + markdown

    # No arm may be described favourably. These are the words a review package
    # reaches for when it has already decided the answer.
    #
    # "enhanced" is checked only outside the milestone name, because
    # "Enhanced Golden" is this project's established name for the experiment and
    # banning it would be banning the project, not the ranking language.
    scannable = combined.replace("Enhanced Golden", "")
    for adjective in (
        "best", "better", "improved", "improvement", "most advanced", "advanced",
        "superior", "upgrade", "upgraded", "enhanced", "recommended", "preferred",
        "wins", "winner", "stronger", "weaker",
    ):
        assert adjective not in scannable.lower(), (
            f"the review package describes an arm as {adjective!r}, which decides "
            f"the result before the reviewer has watched"
        )
    # And the rubric must not be ordered as a preference.
    for dimension in ("voice_naturalness", "overall_publishability", "h3_usefulness"):
        assert dimension in combined, dimension
    assert "PENDING_FOUNDER_REVIEW" in combined
    print("[ok] 16. the review package is neutral and A/NONE stay available")


@test
def test_a_review_cannot_be_recorded_partially_or_with_an_invented_selection():
    receipts = {arm: {"variant_id": arm, "factual_assets": []} for arm in VARIANT_IDS}
    review = FounderReview(
        variant_ids=list(VARIANT_IDS), variant_receipts=receipts,
        evidence_identity={"verdict": "EXPERIMENT_VALID", "all_identical": True},
    )
    # Partial review refused.
    try:
        review.record_review(
            reviewer="founder", selection="A", reviewed_at="2026-10-05T00:00:00Z",
            per_variant={"A": {"overall_publishability": "yes"}},
        )
    except ReviewPackageError as exc:
        assert "B" in str(exc) and "C" in str(exc), str(exc)
    else:
        raise AssertionError("a review covering one arm of four was accepted")

    # A selection outside the allowed set is refused.
    try:
        review.record_review(
            reviewer="founder", selection="D is the winner", reviewed_at="x",
            per_variant={arm: {} for arm in VARIANT_IDS},
        )
    except ReviewPackageError as exc:
        assert "NONE" in str(exc), str(exc)
    else:
        raise AssertionError("an invented selection string was accepted")

    # NONE is a complete, legitimate answer.
    review.record_review(
        reviewer="founder", selection="NONE", reviewed_at="2026-10-05T00:00:00Z",
        per_variant={arm: {"overall_publishability": "no"} for arm in VARIANT_IDS},
        comments={arm: "not publishable yet" for arm in VARIANT_IDS},
    )
    assert review.selection() == "NONE"
    # And the baseline may win.
    review.record_review(
        reviewer="founder", selection="A", reviewed_at="2026-10-05T00:00:00Z",
        per_variant={arm: {} for arm in VARIANT_IDS},
        comments={arm: "" for arm in VARIANT_IDS},
    )
    assert review.selection() == "A"
    print("[ok] 17. partial and invented reviews are refused; NONE and A are valid")


@test
def test_the_review_template_will_not_render_a_score_that_was_never_given():
    receipts = {arm: {"variant_id": arm, "factual_assets": []} for arm in VARIANT_IDS}
    review = FounderReview(
        variant_ids=list(VARIANT_IDS), variant_receipts=receipts,
        evidence_identity={"verdict": "EXPERIMENT_VALID", "all_identical": True},
    )
    markdown = render_review_markdown(review)
    assert "to be filled" in markdown
    # No numeric score exists anywhere, because nothing computed one.
    assert not re.search(r"\bscore\b\s*[:=]\s*\d", markdown, re.IGNORECASE)
    assert "PENDING_FOUNDER_REVIEW" in markdown
    print("[ok] 18. the review template renders no unearned score")


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
    print(f"All {len(TESTS)} M4.6 enhanced golden infrastructure tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())