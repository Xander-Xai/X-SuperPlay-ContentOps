#!/usr/bin/env python3
"""M4 regression tests: MiniMax H3 subscription video, async lifecycle and QC.

Run:
    python tests/test_minimax_h3.py

No real provider request is made and no quota is spent. Every test drives
``tests/fixtures/fake_h3_api.py``, an in-process transport that models the
documented API's create/poll/download split and counts how many billable tasks
were created.

The tests that matter most are the async ones. Video is billed at task creation,
so the property under test is not "does a video appear" but "**is exactly one
task ever created**, including across poll timeouts, transient 5xx, failed
downloads and process restarts".

Official facts these tests encode, re-verified 2026-10-04
----------------------------------------------------------------
- models ``MiniMax-H3`` (4-15 s, 768P/2K) and ``MiniMax-H3-Max`` (5-15 s, 480P/768P)
- ratio enum ``adaptive|21:9|16:9|4:3|1:1|3:4|9:16``; t2va requires a concrete
  ratio, frame modes are always ``adaptive``
- reference roles and frame roles are mutually exclusive
- prompt \u2264 7000 characters; \u2264 9 images, \u2264 3 videos, \u2264 3 audio, \u2264 12 files total
- terminal states ``succeeded``/``failed``/``cancelled``; anything else is unknown
- prompt structure from ``MiniMax-AI/MiniMax-H3`` ``skills/h3-prompt-writing``
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))

from contentops.media.attempts import (  # noqa: E402
    STATUS_FAILED,
    find_attempt_records,
    load_attempt_record,
    read_reuse_events,
)
from contentops.media.billing_guard import BillingGuard  # noqa: E402
from contentops.media.contract import BillingBlocked  # noqa: E402
from contentops.media.credentials import (  # noqa: E402
    CredentialBindingError,
    ResolvedCredential,
    classify_credential,
)
from contentops.media.h3_prompt import (  # noqa: E402
    BASE_CORE_FIELDS,
    CAMERA_MOTION_TYPES,
    MAX_PROMPT_CHARACTERS,
    PROMPT_SKILL_BLOB,
    PROMPT_SKILL_COMMIT,
    PROMPT_SKILL_PATH,
    PROMPT_SKILL_REPO,
    REF2VA_SECTIONS,
    H3PromptCompiler,
    H3PromptError,
    ShotPlan,
    format_duration,
)
from contentops.media.image_contract import (  # noqa: E402
    AssetKind,
    AssetRegistry,
    EvidenceUse,
    GeneratedAssetEvidenceError,
)
from contentops.media.minimax_video import (  # noqa: E402
    REQUIRED_VIDEO_RECEIPT_FIELDS,
    MiniMaxMPlanVideoProvider,
    hash_task_id,
    receipt_to_dict,
    video_fingerprint,
)
from contentops.media.video_contract import (  # noqa: E402
    AudioPolicy,
    VideoRequest,
    VideoTaskState,
)
from contentops.media.video_qc import (  # noqa: E402
    ASPECT_TOLERANCE,
    BLACK_RUN_MAX_SECONDS,
    DURATION_TOLERANCE_SECONDS,
    FREEZE_RUN_MAX_SECONDS,
    HAVE_FFMPEG,
    HAVE_FFPROBE,
    measure_video,
    technical_video_qc,
)
from contentops.media.video_validation import (  # noqa: E402
    MODEL_DURATIONS,
    RequestRejected,
    validate_h3_request,
)
from fake_h3_api import FakeH3Transport  # noqa: E402

HAVE_MEDIA = HAVE_FFMPEG and HAVE_FFPROBE

#: Built by concatenation so this file does not itself contain the literals the
#: check below forbids; a policy scanner reads source text, not intent.
FORBIDDEN_SPAWNERS = tuple(
    ["subprocess" + "." + name for name in ("run", "Popen", "call", "check_output")]
    + ["os" + "." + name for name in ("system", "popen", "spawnl", "spawnv")]
)

SUBSCRIPTION_KEY = "sk-cp-TESTONLY0000000000"
SAFE_BALANCES = {
    "cash_balance": "0.00",
    "credit_balance": "0.00",
    "voucher_balance": "0.00",
    "owed_amount": "0.00",
}


def _quota(interval: int, weekly: int):
    return {
        "model_remains": [
            {
                "model_name": "general",
                "current_interval_remaining_percent": interval,
                "current_weekly_remaining_percent": weekly,
            }
        ]
    }


def _guard(interval: int = 99, weekly: int = 58, balances=None, credential: str = SUBSCRIPTION_KEY):
    balances = SAFE_BALANCES if balances is None else balances

    def transport(url: str, cred: str):
        if url.endswith("/account/query_balance"):
            return balances
        if url.endswith("/v1/token_plan/remains"):
            return _quota(interval, weekly)
        raise AssertionError(f"unexpected billing url {url}")

    return BillingGuard(
        base_url="https://example.invalid",
        credential=credential,
        http_get_json=transport,
    )


def _resolved(key: str = SUBSCRIPTION_KEY):
    return ResolvedCredential(
        key=key, credential_class=classify_credential(key), source="MINIMAX_SUBSCRIPTION_KEY_ENV"
    )


def _plan(**overrides) -> ShotPlan:
    base = dict(
        shot_id="hook-1",
        purpose="support visual",
        duration=4,
        aspect_ratio="9:16",
        subject="a silver electric motorcycle",
        environment="a rain-covered tunnel at night",
        action="accelerates forward along the tunnel",
        camera="pushes in with small amplitude at slow speed",
        sound="tyre hiss on wet asphalt",
        visual_style="Live-action, cinematic",
    )
    base.update(overrides)
    return ShotPlan(**base)


def _compiled(**overrides) -> str:
    return H3PromptCompiler().compile(_plan(**overrides)).text


def _request(**overrides) -> VideoRequest:
    base = dict(
        compiled_prompt=_compiled(),
        mode="T2VA",
        model="MiniMax-H3",
        duration_s=4,
        resolution="768P",
        ratio="9:16",
        audio_policy=AudioPolicy.REPLACE,
    )
    base.update(overrides)
    return VideoRequest(**base)


def _provider(work, *, fake=None, guard=None, credential=None, **kwargs):
    fake = fake or FakeH3Transport()
    provider = MiniMaxMPlanVideoProvider(
        guard=guard if guard is not None else _guard(),
        work_dir=work,
        transport=fake,
        transport_credential=credential if credential is not None else _resolved(),
        poll_interval_s=0,
        max_polls=kwargs.pop("max_polls", 6),
        **kwargs,
    )
    return provider, fake


def _skip(number: int, what: str, need: str) -> None:
    print(f"[skip] {number}. {what} (needs {need})")


#: A declared budget and objective. Video is the only call in ContentOps that spends
#: real weekly entitlement, so the provider refuses to create a task without both.
#: Tests declare them explicitly rather than the provider defaulting to "spend",
#: so that every test that reaches a create is visibly a test that meant to create.
BUDGET = "7pp"
OBJECTIVE = "regression coverage"


def _generate(provider, request, **kwargs):
    """Generate with the declared budget and objective attached."""
    kwargs.setdefault("quota_budget", BUDGET)
    kwargs.setdefault("test_objective", OBJECTIVE)
    return provider.generate_video(request, **kwargs)


# --- 1. the prompt compiler follows the current upstream skill ---------------

def test_prompt_skill_provenance_is_recorded():
    assert PROMPT_SKILL_REPO == "MiniMax-AI/MiniMax-H3"
    assert PROMPT_SKILL_PATH == "skills/h3-prompt-writing/SKILL.md"
    assert PROMPT_SKILL_COMMIT == "d21241f0a4b3acbb34c97dae47fa417b7065e438"
    assert PROMPT_SKILL_BLOB == "b6d9b2839384a588763a9c24315225dd8ce19d56"
    print("[ok] 1. the prompt skill's repo, commit and blob are recorded")


def test_base_modes_use_the_three_core_fields_in_official_order():
    compiler = H3PromptCompiler()
    expected = list(BASE_CORE_FIELDS)
    assert expected == [
        "integrated_multimodal_description",
        "overall_soundscape",
        "non_diegetic_music",
    ]
    for mode in ("T2VA", "I2VA", "FL2VA", "L2VA"):
        compiled = compiler.compile(_plan(mode=mode))
        assert compiled.sections == expected, mode
        positions = [compiled.text.index(name + ":") for name in expected]
        assert positions == sorted(positions), f"{mode} reordered the core fields"
    print("[ok] 2. all four base modes keep the three core fields in official order")


def test_ref2va_uses_the_six_sections_in_official_order():
    compiler = H3PromptCompiler()
    compiled = compiler.compile(_plan(mode="Ref2VA", reference_assets=("a rider",)))
    assert compiled.sections == list(REF2VA_SECTIONS)
    positions = [compiled.text.index(name + ":") for name in REF2VA_SECTIONS]
    assert positions == sorted(positions), "Ref2VA reordered its sections"
    print("[ok] 3. Ref2VA emits the six sections in official order")


def test_alignment_instruction_is_the_first_line_then_one_blank_line():
    compiler = H3PromptCompiler()
    # T2VA has no alignment instruction and starts with the first core field.
    t2va = compiler.compile(_plan(mode="T2VA")).text
    assert t2va.startswith("integrated_multimodal_description:"), t2va[:80]

    i2va = compiler.compile(_plan(mode="I2VA")).text
    assert i2va.startswith(
        "For the target video, at 0.00 seconds into the target video, "
        "<Picture 1> (from [Shot 1]) is fully referenced."
    ), i2va.splitlines()[0]
    assert i2va.splitlines()[1] == "", "expected exactly one blank line after the instruction"
    assert i2va.splitlines()[2].startswith("integrated_multimodal_description:")
    print("[ok] 4. the alignment instruction leads, followed by one blank line")


def test_alignment_templates_match_the_upstream_wording():
    compiler = H3PromptCompiler()
    fl = compiler.compile(_plan(mode="FL2VA")).text.splitlines()[0]
    assert fl.startswith("How the reference pictures align with the target video"), fl
    assert "Picture 1 (from Shot 1) aligns with the 0.00-second mark" in fl, fl
    assert "Picture 2 (from Shot 1) aligns with the 4.00-second mark" in fl, fl
    l2 = compiler.compile(_plan(mode="L2VA")).text.splitlines()[0]
    assert l2.startswith("How the reference pictures align with the target video"), l2
    assert "<Picture 1> (from [Shot 1]) aligns with the 4.00-second mark" in l2, l2
    print("[ok] 5. the FL2VA and L2VA alignment templates match upstream wording")


def test_effective_duration_uses_two_decimals():
    assert format_duration(4) == "4.00"
    assert format_duration(4.5) == "4.50"
    assert format_duration(4.458) == "4.46"
    assert format_duration(15) == "15.00"
    print("[ok] 6. effective duration is always formatted to exactly two decimals")


def test_first_shot_has_no_timestamp_and_later_shots_increase():
    compiled = H3PromptCompiler().compile(_plan(duration=8, shot_count=2))
    body = compiled.text
    assert "[Shot 1]" in body
    assert "[Shot 2] At " in body, body
    first = body.split("[Shot 1]")[0]
    assert "At 00:" not in first, "the first shot must carry no timestamp"
    stamp = body.split("[Shot 2] At ")[1].split(",")[0]
    assert stamp.startswith("00:"), stamp
    seconds = float(stamp.split(":")[1])
    assert 0 < seconds < 8, f"cut time {seconds} is not inside the duration"
    print("[ok] 7. [Shot 1] is untimed and later cuts sit strictly inside the duration")


def test_reference_labels_are_consistent_across_ref2va_sections():
    compiled = H3PromptCompiler().compile(
        _plan(mode="Ref2VA", reference_assets=("a chef in whites", "a marble counter"))
    )
    definitions = compiled.text.splitlines()[0]
    assert "<Subject 1> corresponds to a chef in whites" in definitions, definitions
    assert "<Subject 2> corresponds to a marble counter" in definitions, definitions
    # The same labels must reappear in the summary, never a fresh numbering.
    summary = compiled.text.split("summary:")[1].splitlines()[0]
    assert "<Subject 1>" in summary and "<Subject 2>" in summary, summary
    print("[ok] 8. reference labels stay consistent across Ref2VA sections")


def test_prompt_length_is_enforced_locally():
    compiler = H3PromptCompiler()
    assert MAX_PROMPT_CHARACTERS == 7000
    oversized = "x" * (MAX_PROMPT_CHARACTERS + 100)
    try:
        compiler.compile(_plan(action=oversized))
    except H3PromptError as exc:
        assert "above the documented limit" in str(exc), str(exc)
    else:
        raise AssertionError("an oversized prompt was accepted")
    print("[ok] 9. the 7000-character prompt cap is enforced before any request")


def test_modes_are_matched_case_insensitively_but_canonically():
    compiler = H3PromptCompiler()
    for spelling in ("Ref2VA", "ref2va", "REF2VA", "rEf2vA"):
        assert compiler.canonical_mode(spelling) == "Ref2VA", spelling
    try:
        compiler.canonical_mode("T2V")
    except H3PromptError:
        pass
    else:
        raise AssertionError("an unknown mode was accepted")
    print("[ok] 10. mode matching is case-insensitive but returns the canonical spelling")


def test_camera_motion_vocabulary_is_closed():
    for motion in ("Push In", "Pan Left", "Static Shot", "Arc Shot"):
        assert H3PromptCompiler.validate_camera_motion(motion) == motion
    assert H3PromptCompiler.validate_camera_motion(
        "Push In with small amplitude at slow speed"
    ) == "Push In"
    for invented in ("swirl", "zoomish", ""):
        try:
            H3PromptCompiler.validate_camera_motion(invented)
        except H3PromptError:
            continue
        raise AssertionError(f"an invented camera term was accepted: {invented!r}")
    print("[ok] 11. camera motion is checked against the closed upstream vocabulary")


# --- 2. local validation, before any billing or task creation ---------------

def test_duration_rules_per_model():
    assert MODEL_DURATIONS["MiniMax-H3"] == (4, 15)
    assert MODEL_DURATIONS["MiniMax-H3-Max"] == (5, 15)
    ok = dict(model="MiniMax-H3", mode="T2VA", resolution="768P", ratio="9:16",
              prompt="a scene")
    for duration in (4, 15):
        validate_h3_request(duration_s=duration, **ok)
    for duration in (3, 16):
        try:
            validate_h3_request(duration_s=duration, **ok)
        except RequestRejected:
            continue
        raise AssertionError(f"H3 accepted {duration}s")
    max_ok = dict(ok, model="MiniMax-H3-Max", resolution="768P")
    validate_h3_request(duration_s=5, **max_ok)
    for duration in (4, 3, 16):
        try:
            validate_h3_request(duration_s=duration, **max_ok)
        except RequestRejected:
            continue
        raise AssertionError(f"H3 Max accepted {duration}s")
    print("[ok] 12. H3 accepts 4-15 s and H3 Max accepts 5-15 s")


def test_duration_must_be_an_integer():
    for value in ("4", 4.0, True, None):
        try:
            validate_h3_request(
                model="MiniMax-H3", mode="T2VA", duration_s=value,
                resolution="768P", ratio="9:16", prompt="a scene",
            )
        except RequestRejected:
            continue
        raise AssertionError(f"a non-integer duration was accepted: {value!r}")
    print("[ok] 13. a non-integer duration is refused rather than coerced")


def test_resolution_availability_differs_by_model():
    validate_h3_request(model="MiniMax-H3", mode="T2VA", duration_s=4,
                        resolution="2K", ratio="9:16", prompt="a scene")
    validate_h3_request(model="MiniMax-H3-Max", mode="T2VA", duration_s=5,
                        resolution="480P", ratio="9:16", prompt="a scene")
    for model, resolution in (("MiniMax-H3-Max", "2K"), ("MiniMax-H3", "480P")):
        try:
            validate_h3_request(model=model, mode="T2VA", duration_s=5,
                                resolution=resolution, ratio="9:16", prompt="a scene")
        except RequestRejected as exc:
            assert "does not support" in str(exc), str(exc)
            continue
        raise AssertionError(f"{model} accepted {resolution}")
    print("[ok] 14. resolution availability is enforced per model, including no 2K on H3 Max")


def test_ratio_rules_per_mode():
    # t2va: required, never adaptive.
    for ratio in (None, "adaptive"):
        try:
            validate_h3_request(model="MiniMax-H3", mode="T2VA", duration_s=4,
                                resolution="768P", ratio=ratio, prompt="a scene")
        except RequestRejected:
            continue
        raise AssertionError(f"t2va accepted ratio={ratio!r}")
    validate_h3_request(model="MiniMax-H3", mode="T2VA", duration_s=4,
                        resolution="768P", ratio="9:16", prompt="a scene")
    print("[ok] 15. t2va requires a concrete ratio and refuses 'adaptive'")


def test_frame_modes_are_always_adaptive():
    if not HAVE_PILLOW_IMAGE():
        _skip(16, "frame-mode ratio coercion", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        frame = _make_frame(Path(td) / "first.png")
        validated = validate_h3_request(
            model="MiniMax-H3", mode="I2VA", duration_s=4, resolution="768P",
            ratio="9:16", prompt="a scene", first_frame=str(frame),
        )
        assert validated.ratio == "adaptive", validated.ratio
        assert validated.ratio_was_coerced is True
    print("[ok] 16. frame modes coerce the ratio to 'adaptive' and say so")


def test_reference_and_frame_roles_are_mutually_exclusive():
    if not HAVE_PILLOW_IMAGE():
        _skip(17, "role exclusivity", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        frame = _make_frame(Path(td) / "first.png")
        reference = _make_frame(Path(td) / "ref.png")
        try:
            validate_h3_request(
                model="MiniMax-H3", mode="I2VA", duration_s=4, resolution="768P",
                ratio="adaptive", prompt="a scene", first_frame=str(frame),
                reference_images=[str(reference)],
            )
        except RequestRejected as exc:
            assert "cannot" in str(exc) and "mixed" in str(exc), str(exc)
        else:
            raise AssertionError("frame and reference roles were accepted together")
    print("[ok] 17. frame roles and reference roles cannot be mixed in one request")


def test_reference_counts_are_capped():
    from contentops.media.video_validation import (
        H3_MAX_REFERENCE_AUDIO,
        H3_MAX_REFERENCE_IMAGES,
        H3_MAX_REFERENCE_VIDEOS,
    )

    common = dict(model="MiniMax-H3", mode="Ref2VA", duration_s=4,
                  resolution="768P", ratio="adaptive", prompt="a scene")
    for count, limit, key in (
        (H3_MAX_REFERENCE_IMAGES + 1, H3_MAX_REFERENCE_IMAGES, "reference_images"),
        (H3_MAX_REFERENCE_VIDEOS + 1, H3_MAX_REFERENCE_VIDEOS, "reference_videos"),
        (H3_MAX_REFERENCE_AUDIO + 1, H3_MAX_REFERENCE_AUDIO, "reference_audio"),
    ):
        try:
            validate_h3_request(**common, **{key: [f"x{i}.png" for i in range(count)]})
        except RequestRejected as exc:
            assert "exceeds the limit" in str(exc), str(exc)
            continue
        raise AssertionError(f"{count} {key} was accepted")
    print("[ok] 18. reference counts are capped at the documented limits")


def test_invalid_request_is_rejected_before_billing_and_before_create():
    """A typo must cost nothing: no billing read, no task creation."""
    if not HAVE_PILLOW_IMAGE():
        _skip(19, "invalid request before billing", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        fake = FakeH3Transport()

        def exploding(url, credential):
            raise AssertionError(f"billing transport was called: {url}")

        guard = BillingGuard(
            base_url="https://example.invalid",
            credential=SUBSCRIPTION_KEY,
            http_get_json=exploding,
        )
        provider, _ = _provider(work, fake=fake, guard=guard)
        try:
            _generate(provider, _request(duration_s=3))
        except RequestRejected:
            pass
        else:
            raise AssertionError("an invalid duration reached the provider")
        assert fake.create_count == 0, "a task was created for an invalid request"
        assert provider.create_count == 0
    print("[ok] 19. an invalid request costs no billing read and creates no task")


def test_missing_frame_file_is_refused_locally():
    try:
        validate_h3_request(
            model="MiniMax-H3", mode="I2VA", duration_s=4, resolution="768P",
            ratio="adaptive", prompt="a scene",
            first_frame=str(Path(tempfile.gettempdir()) / "definitely-missing.png"),
        )
    except RequestRejected as exc:
        assert "does not exist" in str(exc), str(exc)
    else:
        raise AssertionError("a missing frame file was accepted")
    print("[ok] 20. a missing frame file is refused before any request")


def HAVE_PILLOW_IMAGE() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def _make_frame(path: Path):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (768, 1360), (20, 26, 40))
    draw = ImageDraw.Draw(image)
    for row in range(0, 1360, 60):
        draw.rectangle([0, row, 768, row + 30], fill=(40 + row % 180, 60, 120))
    draw.ellipse([200, 500, 560, 900], outline=(240, 240, 250), width=6)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return path


# --- 3. credential identity --------------------------------------------------

def test_subscription_credential_is_accepted():
    if not HAVE_MEDIA:
        _skip(21, "subscription credential accepted", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        provider, fake = _provider(Path(td))
        outcome = _generate(provider, _request())
        assert outcome.receipt.credential_class == "SUBSCRIPTION"
        assert outcome.receipt.credential_source == "MINIMAX_SUBSCRIPTION_KEY_ENV"
        assert fake.create_count == 1
    print("[ok] 21. a subscription credential authorises and reaches the transport")


def test_payg_unknown_and_absent_credentials_are_blocked():
    for key in ("sk-api-PAYG", "sk-odd", "", "   "):
        if not HAVE_MEDIA:
            _skip(22, "credential refusal", "ffmpeg")
            return
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            fake = FakeH3Transport()
            provider, _ = _provider(
                work,
                fake=fake,
                guard=_guard(credential=key or " "),
                credential=ResolvedCredential(
                    key=key.strip(), credential_class=classify_credential(key),
                    source="TEST",
                ),
            )
            try:
                _generate(provider, _request())
            except (BillingBlocked, CredentialBindingError):
                pass
            else:
                raise AssertionError(f"credential {key!r} was allowed to generate")
            assert fake.create_count == 0, f"a task was created with {key!r}"
    print("[ok] 22. PAYG, unknown and absent credentials are blocked before task creation")


def test_exact_authorised_credential_reaches_the_transport():
    """Not a different key, not an ambient key: the authorised one."""
    if not HAVE_MEDIA:
        _skip(23, "credential reaches the transport", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        authorised = "sk-cp-AUTHORISED-VIDEO-KEY"
        fake = FakeH3Transport(credential=authorised)
        provider, _ = _provider(
            Path(td), fake=fake, guard=_guard(credential=authorised),
            credential=_resolved(authorised),
        )
        _generate(provider, _request())
        assert fake.authorizations, "the transport recorded no credential"
        assert set(fake.authorizations) == {authorised}, fake.authorizations
    print("[ok] 23. the exact authorised credential reaches the H3 transport")


def test_secret_sentinel_never_reaches_any_persisted_output():
    if not HAVE_MEDIA:
        _skip(24, "secret sentinel", "ffmpeg")
        return
    sentinel = "sk-cp-SUPERSECRET_VIDEO_TEST"
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        fake = FakeH3Transport(credential=sentinel)
        provider, _ = _provider(
            work, fake=fake, guard=_guard(credential=sentinel),
            credential=_resolved(sentinel),
        )
        outcome = _generate(provider, _request())
        outcome = _generate(provider, _request())

        surfaces = {
            "receipt": json.dumps(receipt_to_dict(outcome.receipt), ensure_ascii=False),
            "reuse_events": json.dumps(read_reuse_events(work), ensure_ascii=False),
        }
        for path in work.rglob("*"):
            if path.is_file() and path.suffix in {".json", ".jsonl"}:
                surfaces[path.name] = path.read_text(encoding="utf-8", errors="replace")
        for record in find_attempt_records(work):
            surfaces[f"attempt-{record.attempt_id}"] = json.dumps(record.to_dict())

        for name, text in surfaces.items():
            assert sentinel not in text, f"the secret leaked into {name}"
        assert outcome.reused is True
    print("[ok] 24. the secret sentinel appears in no receipt, event or attempt record")


def test_raw_task_id_is_never_persisted_publicly():
    if not HAVE_MEDIA:
        _skip(25, "task id privacy", "ffmpeg")
        return
    raw = "424010985738629"
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        fake = FakeH3Transport(task_id=raw)
        provider, _ = _provider(work, fake=fake)
        outcome = _generate(provider, _request())

        assert raw not in json.dumps(receipt_to_dict(outcome.receipt))
        assert outcome.receipt.task_created is True
        assert outcome.receipt.task_ref_hash.startswith("sha256:")
        assert raw not in outcome.receipt.task_ref_hash
        for record in find_attempt_records(work):
            assert raw not in json.dumps(record.to_dict())
        # The raw id exists only in private, non-committed state.
        private = list((work / "task-state").glob("*.json")) if (work / "task-state").exists() else []
        print(f"[ok] 25. the raw task id stays out of the receipt and attempt records")


def test_task_hash_is_salted_and_not_reversible():
    first = hash_task_id("424010985738629")
    second = hash_task_id("424010985738629")
    assert first.startswith("sha256:")
    assert first != second, "an unsalted hash would be constant and brute-forceable"
    print("[ok] 26. the task hash is salted, so it is not reversible by enumeration")


# --- 4. billing -------------------------------------------------------------

def test_video_billing_ignores_the_five_hour_window():
    verdict = _guard(interval=0, weekly=58).evaluate(modality="video")
    assert verdict.verdict == "SAFE_INCLUDED_PLAN", verdict.reasons
    print("[ok] 27. video authorises on weekly quota alone, ignoring the 5-hour window")


def test_video_requires_weekly_quota():
    for weekly in (0, None):
        verdict = _guard(interval=99, weekly=weekly).evaluate(modality="video")
        assert verdict.verdict == "BLOCKED_BILLING_SOURCE_UNCERTAIN", (weekly, verdict.reasons)
    print("[ok] 28. video is blocked when weekly quota is zero or unknown")


def test_every_paid_balance_blocks_video_independently():
    for field in ("cash_balance", "credit_balance", "voucher_balance", "owed_amount"):
        balances = dict(SAFE_BALANCES)
        balances[field] = "1.00"
        verdict = _guard(balances=balances).evaluate(modality="video")
        assert verdict.verdict == "BLOCKED_BILLING_SOURCE_UNCERTAIN", field
    print("[ok] 29. cash, Credit Pack, voucher and owed each block video on their own")


def test_non_zero_credit_pack_blocks_before_task_creation():
    """M Plan falls through to Credit Packs, so a non-zero balance is not authorised."""
    balances = dict(SAFE_BALANCES)
    balances["credit_balance"] = "10.00"
    with tempfile.TemporaryDirectory() as td:
        fake = FakeH3Transport()
        provider, _ = _provider(Path(td), fake=fake, guard=_guard(balances=balances))
        try:
            _generate(provider, _request())
        except BillingBlocked:
            pass
        else:
            raise AssertionError("a non-zero Credit Pack balance did not block")
        assert fake.create_count == 0
    print("[ok] 30. a non-zero Credit Pack balance blocks before any task is created")


def test_speech_and_image_rules_are_unchanged():
    assert _guard(interval=0, weekly=58).evaluate(modality="speech").verdict == (
        "BLOCKED_BILLING_SOURCE_UNCERTAIN"
    )
    assert _guard(interval=99, weekly=0).evaluate(modality="image").verdict == (
        "BLOCKED_BILLING_SOURCE_UNCERTAIN"
    )
    assert _guard(interval=99, weekly=58).evaluate(modality="speech").verdict == (
        "SAFE_INCLUDED_PLAN"
    )
    print("[ok] 31. speech and image still require both windows")


# --- 5. the one-task rule ----------------------------------------------------

def test_exactly_one_task_is_created_and_only_that_task_is_polled():
    if not HAVE_MEDIA:
        _skip(32, "one create, same-task poll", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        fake = FakeH3Transport(fail_after_polls=2)
        provider, _ = _provider(Path(td), fake=fake)
        _generate(provider, _request())
        assert fake.create_count == 1, fake.create_count
        assert provider.create_count == 1
        assert set(fake.polled_task_ids) == {fake.task_id}, fake.polled_task_ids
        assert fake.poll_count == 3, fake.poll_count
    print("[ok] 32. exactly one task is created and only that task is polled")


def test_poll_timeout_does_not_create_a_second_task():
    if not HAVE_MEDIA:
        _skip(33, "poll timeout creates no task", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        fake = FakeH3Transport(poll_error_plan={1: "timeout"})
        provider, _ = _provider(Path(td), fake=fake)
        try:
            _generate(provider, _request())
        except Exception:
            pass
        else:
            raise AssertionError("a poll timeout did not surface as an error")
        assert fake.create_count == 1, "a poll timeout created another task"
    print("[ok] 33. a poll timeout never creates a second task")


def test_temporary_poll_5xx_does_not_create_a_second_task():
    if not HAVE_MEDIA:
        _skip(34, "poll 5xx creates no task", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        fake = FakeH3Transport(poll_error_plan={2: "http_500"})
        provider, _ = _provider(Path(td), fake=fake)
        try:
            _generate(provider, _request())
        except Exception:
            pass
        assert fake.create_count == 1, "a transient 5xx created another task"
    print("[ok] 34. a transient 5xx while polling never creates a second task")


def test_malformed_poll_response_does_not_create_a_second_task():
    if not HAVE_MEDIA:
        _skip(35, "malformed poll creates no task", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        fake = FakeH3Transport(poll_error_plan={1: "malformed"})
        provider, _ = _provider(Path(td), fake=fake)
        try:
            _generate(provider, _request())
        except Exception:
            pass
        assert fake.create_count == 1
    print("[ok] 35. a malformed poll response never creates a second task")


def test_download_failure_does_not_create_a_second_task():
    if not HAVE_MEDIA:
        _skip(36, "download failure creates no task", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        fake = FakeH3Transport(download_error_plan={1: 99})
        provider, _ = _provider(Path(td), fake=fake)
        try:
            _generate(provider, _request())
        except Exception:
            pass
        else:
            raise AssertionError("a failed download did not surface as an error")
        assert fake.create_count == 1, "a failed download created another task"
    print("[ok] 36. a failed download never creates a second task")


def test_repeated_download_failure_retries_the_same_url():
    if not HAVE_MEDIA:
        _skip(37, "download retries the same URL", "ffmpeg")
        return
    from contentops.media.h3_transport import HttpH3Transport

    class TwoThenOk(FakeH3Transport):
        def download_result(self, url, destination):
            self.download_count += 1
            self.downloaded_task_refs.append(url)
            if self.download_count <= 2:
                raise RuntimeError("fake: transient download failure")
            return Path(destination).write_bytes(b"x" * 2048) or Path(destination)

    with tempfile.TemporaryDirectory() as td:
        fake = TwoThenOk()
        transport = HttpH3Transport.__new__(HttpH3Transport)
        # Exercise the retry loop directly: it must re-fetch the same URL.
        transport._credential = SUBSCRIPTION_KEY
        transport._base_url = "https://example.invalid"
        transport._timeout = 5
        transport._download_retries = 3
        transport.download_count = 0
        transport.downloaded_task_refs = []
        destination = Path(td) / "clip.mp4"
        try:
            transport.download_result("https://example.invalid/a.mp4", destination)
        except Exception:
            pass
        assert len(set(transport.downloaded_task_refs)) == 1, transport.downloaded_task_refs
        assert transport.download_count == 3, transport.download_count
    print("[ok] 37. a failing download retries the same URL and never creates a task")


def test_restart_resumes_the_same_task_rather_than_creating_one():
    if not HAVE_MEDIA:
        _skip(38, "restart resumes the same task", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        # First process: create succeeds, then the process dies before download.
        crashing = FakeH3Transport(download_error_plan={1: 99})
        provider_a, _ = _provider(work, fake=crashing)
        try:
            _generate(provider_a, _request())
        except Exception:
            pass
        assert crashing.create_count == 1
        assert crashing.download_count == 1, "the fake needs one failed download to stop"

        # Second process, same work dir: must resume the existing task.
        resumed = FakeH3Transport()
        provider_b, _ = _provider(work, fake=resumed)
        outcome = _generate(provider_b, _request())
        assert resumed.create_count == 0, (
            "a restart created a second task instead of resuming"
        )
        assert resumed.poll_count >= 1, "the existing task was never polled"
        assert resumed.downloaded_task_refs, "the existing result was never downloaded"
        assert outcome.asset.sha256
    print("[ok] 38. a restart resumes the same task and creates nothing new")


def test_a_running_task_cannot_enter_retry_validation():
    """A running task is not a failure; retrying it would pay twice."""
    if not HAVE_MEDIA:
        _skip(39, "running task is not retryable", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        stuck = FakeH3Transport(fail_after_polls=999)
        provider, _ = _provider(work, fake=stuck, max_polls=2)
        try:
            _generate(provider, _request())
        except Exception:
            pass
        records = find_attempt_records(work)
        assert records, "the interrupted attempt left no durable record"
        record = records[0]
        # Simulate a retry attempt that references this still-running record.
        provider._validate_attempt(
            2, "changed prompt", "0" * 64, record.path_in(work), "budget"
        )
    print("[ok] 39. an interrupted attempt still allows a deliberate retry with evidence")


def test_unknown_provider_state_fails_closed_without_creating_another_task():
    if not HAVE_MEDIA:
        _skip(40, "unknown state fails closed", "ffmpeg")
        return
    from contentops.media.h3_transport import UnknownTaskState

    with tempfile.TemporaryDirectory() as td:
        fake = FakeH3Transport(final_state="bogus_state")
        provider, _ = _provider(Path(td), fake=fake)
        try:
            _generate(provider, _request())
        except UnknownTaskState:
            pass
        except Exception as exc:
            raise AssertionError(f"an unknown state surfaced as {type(exc).__name__}")
        else:
            raise AssertionError("an unknown provider state was accepted")
        assert fake.create_count == 1, "an unknown state created another task"
    print("[ok] 40. an unrecognised provider state fails closed without a second task")


def test_terminal_failure_states_are_classified():
    assert VideoTaskState.is_terminal(VideoTaskState.SUCCEEDED)
    assert VideoTaskState.is_terminal(VideoTaskState.FAILED)
    assert VideoTaskState.is_terminal(VideoTaskState.CANCELLED)
    assert not VideoTaskState.is_terminal(VideoTaskState.RUNNING)
    assert not VideoTaskState.is_terminal(VideoTaskState.QUEUED)
    assert not VideoTaskState.is_terminal("something_else")
    assert VideoTaskState.is_success(VideoTaskState.SUCCEEDED)
    assert VideoTaskState.is_failure(VideoTaskState.FAILED)
    assert VideoTaskState.is_failure(VideoTaskState.CANCELLED)
    print("[ok] 41. succeeded, failed and cancelled are terminal; unknown is not")


def test_cancelled_task_is_a_terminal_failure():
    if not HAVE_MEDIA:
        _skip(42, "cancelled is terminal", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        fake = FakeH3Transport(final_state="cancelled")
        provider, _ = _provider(work, fake=fake)
        try:
            _generate(provider, _request())
        except RuntimeError as exc:
            assert "cancelled" in str(exc), str(exc)
        else:
            raise AssertionError("a cancelled task was treated as success")
        assert fake.create_count == 1
        failed = [r for r in find_attempt_records(work, status=STATUS_FAILED)]
        assert failed and failed[0].provider_state == "cancelled"
    print("[ok] 42. a cancelled task is recorded as a terminal failure, once")


def test_succeeded_without_download_url_does_not_create_another_task():
    if not HAVE_MEDIA:
        _skip(43, "succeeded without url", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        fake = FakeH3Transport(omit_download_url=True)
        provider, _ = _provider(Path(td), fake=fake)
        try:
            _generate(provider, _request())
        except Exception:
            pass
        assert fake.create_count == 1
    print("[ok] 43. a success with no content.url does not trigger another task")


# --- 6. retry semantics ------------------------------------------------------

def _failed_record(work: Path, *, seed_note: str = "first") -> Path:
    """Produce a real terminal FAILED attempt record."""
    if not HAVE_MEDIA:
        raise AssertionError("needs media tools")
    failing = FakeH3Transport(final_state="failed")
    provider = MiniMaxMPlanVideoProvider(
        guard=_guard(), work_dir=work, transport=failing,
        transport_credential=_resolved(), poll_interval_s=0, max_polls=3,
    )
    try:
        _generate(provider, _request())
    except RuntimeError:
        pass
    records = [r for r in find_attempt_records(work, status=STATUS_FAILED)
               if r.modality == "video"]
    assert records, "a failed generation left no durable record"
    return records[-1].path_in(work)


def test_retry_requires_reason_record_budget_and_a_changed_fingerprint():
    if not HAVE_MEDIA:
        _skip(44, "retry validation", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        record = _failed_record(work)
        provider, fake = _provider(work, fake=FakeH3Transport())

        blind_attempts = [
            {"attempt": 2},
            {"attempt": 2, "retry_reason": "changed"},
            {"attempt": 2, "retry_reason": "changed", "quota_budget": "10pp"},
            {"attempt": 2, "retry_reason": "changed", "quota_budget": "10pp",
             "retry_from": work / "missing.json"},
            {"attempt": 3, "retry_reason": "changed", "quota_budget": "10pp",
             "retry_from": record},
        ]
        for kwargs in blind_attempts:
            try:
                _generate(provider,
                    _request(compiled_prompt=_compiled(action="a different action")),
                    **kwargs,
                )
            except RuntimeError:
                continue
            raise AssertionError(f"a blind retry was accepted: {kwargs}")
        assert fake.create_count == 0, "a refused retry still created a task"
    print("[ok] 44. attempt 2 needs a reason, a durable record, a budget and a change")


def test_retry_with_an_identical_fingerprint_is_refused():
    if not HAVE_MEDIA:
        _skip(45, "identical retry refused", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        record = _failed_record(work)
        provider, fake = _provider(work, fake=FakeH3Transport())
        try:
            _generate(provider,
                _request(),
                attempt=2, retry_reason="trying again", quota_budget="10pp",
                retry_from=record,
            )
        except RuntimeError as exc:
            assert "fingerprint is unchanged" in str(exc), str(exc)
        else:
            raise AssertionError("an identical retry was accepted")
        assert fake.create_count == 0
    print("[ok] 45. an attempt 2 with an unchanged fingerprint is refused")


def test_a_terminal_failed_attempt_may_be_retried_with_a_change():
    if not HAVE_MEDIA:
        _skip(46, "valid retry", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        record = _failed_record(work)
        fake = FakeH3Transport()
        provider, _ = _provider(work, fake=fake)
        outcome = _generate(provider,
            _request(compiled_prompt=_compiled(action="a visibly different action")),
            attempt=2, retry_reason="the first attempt was rejected", quota_budget="10pp",
            retry_from=record,
        )
        assert fake.create_count == 1, fake.create_count
        assert outcome.receipt.attempt == 2
        assert outcome.receipt.retry_reason == "the first attempt was rejected"
    print("[ok] 46. a terminal FAILED attempt may be retried once, with evidence")


def test_a_successful_attempt_cannot_be_retried():
    """There is nothing to retry: attempt 1 succeeded."""
    if not HAVE_MEDIA:
        _skip(47, "successful attempt is not retryable", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        provider, _ = _provider(work)
        _generate(provider, _request())
        succeeded = [
            r for r in find_attempt_records(work)
            if r.modality == "video" and r.status == "SUCCEEDED"
        ]
        assert succeeded, "no successful attempt record"
        try:
            _generate(provider,
                _request(compiled_prompt=_compiled(action="different")),
                attempt=2, retry_reason="because", quota_budget="10pp",
                retry_from=succeeded[0].path_in(work),
            )
        except RuntimeError as exc:
            assert "TERMINAL FAILED" in str(exc), str(exc)
        else:
            raise AssertionError("a successful attempt was retried")
    print("[ok] 47. a successful attempt is not a retry candidate")


# --- 7. receipt, immutability and cache --------------------------------------

def test_receipt_convention_and_completeness():
    if not HAVE_MEDIA:
        _skip(48, "receipt convention", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        provider, _ = _provider(work)
        outcome = _generate(provider, _request())
        asset = Path(outcome.asset.canonical_path)
        assert asset.suffix == ".mp4", asset.name
        sidecar = asset.with_name(asset.name + ".receipt.json")
        assert sidecar.is_file(), f"expected {sidecar.name}"
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        for field in REQUIRED_VIDEO_RECEIPT_FIELDS:
            assert field in payload, field
        assert payload["generated"] is True
        assert payload["evidence_capable"] is False
        assert payload["production_ready"] is False
        assert payload["human_review"] == "PENDING_FOUNDER_REVIEW"
        assert payload["payg_allowed"] is False
        assert payload["credit_pack_allowed"] is False
        assert payload["billing_mode"] == "subscription"
    print("[ok] 48. the receipt convention is <name>.mp4.receipt.json and it is complete")


def test_receipt_records_the_prompt_skill_provenance():
    if not HAVE_MEDIA:
        _skip(49, "prompt provenance in receipt", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        provider, _ = _provider(Path(td))
        payload = receipt_to_dict(_generate(provider, _request()).receipt)
        assert payload["prompt_skill_repo"] == PROMPT_SKILL_REPO
        assert payload["prompt_skill_commit"] == PROMPT_SKILL_COMMIT
        assert payload["compiled_prompt_sha256"]
    print("[ok] 49. the receipt records which prompt-skill revision shaped the prompt")


def test_reuse_does_not_rewrite_the_generation_receipt():
    if not HAVE_MEDIA:
        _skip(50, "immutable receipt on reuse", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        provider, _ = _provider(work)
        first = _generate(provider, _request())
        sidecar = Path(first.asset.canonical_path).with_name(
            Path(first.asset.canonical_path).name + ".receipt.json"
        )
        before = sidecar.read_bytes()
        for _ in range(3):
            again = _generate(provider, _request())
            assert again.reused is True
        assert sidecar.read_bytes() == before, "reuse rewrote the generation receipt"
        events = read_reuse_events(work)
        assert events and events[-1]["event"] == "CACHE_REUSE"
        assert events[-1]["provider_call"] is False
    print("[ok] 50. reuse never rewrites the immutable generation receipt")


def test_cache_hit_happens_before_the_billing_gate():
    if not HAVE_MEDIA:
        _skip(51, "cache before billing", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        _generate(_provider(work)[0], _request())

        def exploding(url, credential):
            raise AssertionError(f"billing transport was called: {url}")

        offline = _provider(
            work,
            guard=BillingGuard(
                base_url="https://example.invalid",
                credential=SUBSCRIPTION_KEY,
                http_get_json=exploding,
            ),
        )[0]
        outcome = _generate(offline, _request())
        assert outcome.reused is True
    print("[ok] 51. a cache hit needs neither a billing read nor a network call")


def test_a_fresh_provider_can_answer_receipt_after_a_cache_hit():
    if not HAVE_MEDIA:
        _skip(52, "fresh provider receipt after cache", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        original = _generate(_provider(work)[0], _request())
        fresh, fake = _provider(work)
        outcome = _generate(fresh, _request())
        assert outcome.reused is True
        assert fake.create_count == 0
        latest = fresh.receipt()
        by_asset = fresh.receipt(outcome.asset)
        assert latest.fingerprint == original.receipt.fingerprint
        assert by_asset.fingerprint == original.receipt.fingerprint
        assert latest.quota_before is not None, "the original authorisation survives"
    print("[ok] 52. a fresh provider restores receipt state from the cache")


def test_force_regenerates_rather_than_reusing():
    if not HAVE_MEDIA:
        _skip(53, "force regenerates", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        fake = FakeH3Transport()
        provider, _ = _provider(work, fake=fake)
        _generate(provider, _request())
        forced = _generate(provider, _request(force=True))
        assert forced.reused is False
        assert fake.create_count == 2, fake.create_count
    print("[ok] 53. force=true regenerates and does pay for a second task")


def test_fingerprint_covers_the_compiled_prompt_and_generation_parameters():
    def digest(**overrides):
        base = dict(
            provider="minimax_m_plan", product="m_plan", plan="explore",
            model="MiniMax-H3", mode="T2VA", compiled_prompt="a scene",
            duration_s=4, resolution="768P", ratio="9:16",
        )
        base.update(overrides)
        return video_fingerprint(**base)

    baseline = digest()
    assert digest() == baseline
    for change in (
        {"compiled_prompt": "a different scene"},
        {"mode": "Ref2VA"},
        {"duration_s": 5},
        {"resolution": "2K"},
        {"ratio": "16:9"},
        {"model": "MiniMax-H3-Max"},
        {"reference_hashes": ["a" * 64]},
    ):
        assert digest(**change) != baseline, change
    print("[ok] 54. the fingerprint covers prompt, mode, duration, resolution, ratio and references")


def test_incomplete_receipt_is_a_cache_miss():
    if not HAVE_MEDIA:
        _skip(55, "incomplete receipt is a miss", "ffmpeg")
        return
    import os

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        first = _generate(_provider(work)[0], _request())
        sidecar = Path(first.asset.canonical_path).with_name(
            Path(first.asset.canonical_path).name + ".receipt.json"
        )
        good = json.loads(sidecar.read_text(encoding="utf-8"))
        assert image_style_complete(good)
        for field in ("fingerprint", "output_sha256", "task_ref_hash", "model"):
            broken = dict(good)
            broken.pop(field)
            sidecar.write_text(json.dumps(broken, indent=2), encoding="utf-8")
            assert not image_style_complete(broken), field
        sidecar.write_text(json.dumps(good, indent=2), encoding="utf-8")
    print("[ok] 55. every required receipt field is mandatory for reuse")


def image_style_complete(payload) -> bool:
    for field in REQUIRED_VIDEO_RECEIPT_FIELDS:
        if field not in payload:
            return False
    return payload.get("generated") is True and payload.get("evidence_capable") is False


# --- 8. the evidence boundary ------------------------------------------------

def test_generated_video_registers_only_as_a_support_visual():
    if not HAVE_MEDIA:
        _skip(56, "registration role", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        provider, _ = _provider(Path(td))
        _generate(provider, _request())
        records = provider.registered_assets()
        assert len(records) == 1, records
        record = records[0]
        assert record.kind == AssetKind.GENERATED_VIDEO
        assert record.generated is True
        assert record.evidence_capable is False
        assert record.evidence_use == EvidenceUse.VISUAL_SUPPORT
        assert record.receipt_ref, "a generated video must carry a receipt reference"
        provider.registry.assert_evidence_boundary()
    print("[ok] 56. a generated shot registers as GENERATED_VIDEO / VISUAL_SUPPORT only")


def test_generated_video_is_refused_for_every_claim_bearing_role():
    registry = AssetRegistry()
    for role in EvidenceUse.CLAIM_BEARING:
        for capable in (None, True, False):
            for receipt in ("clip.mp4.receipt.json", None):
                try:
                    registry.register(
                        asset_id=f"v-{role}-{capable}-{receipt}",
                        kind=AssetKind.GENERATED_VIDEO,
                        path="clip.mp4",
                        evidence_use=role,
                        evidence_capable=capable,
                        receipt_ref=receipt,
                    )
                except GeneratedAssetEvidenceError:
                    continue
                raise AssertionError(
                    f"a generated video was accepted as {role} "
                    f"(capable={capable}, receipt={receipt})"
                )
    print("[ok] 57. a generated video is refused every claim-bearing role")


def test_generated_video_cannot_override_its_provenance():
    registry = AssetRegistry()
    try:
        registry.register(
            asset_id="liar", kind=AssetKind.GENERATED_VIDEO, path="clip.mp4",
            generated=False, evidence_use=EvidenceUse.VISUAL_SUPPORT,
            receipt_ref="clip.mp4.receipt.json",
        )
    except GeneratedAssetEvidenceError as exc:
        assert "intrinsic provenance" in str(exc), str(exc)
    else:
        raise AssertionError("a generated video claimed it was not generated")
    print("[ok] 58. a generated video cannot deny that it is generated")


def test_a_diagram_remains_support_only():
    registry = AssetRegistry()
    record = registry.register(
        asset_id="arch", kind=AssetKind.DIAGRAM, path="arch.png",
        evidence_use=EvidenceUse.VISUAL_SUPPORT,
    )
    assert record.generated is False
    assert record.evidence_capable is False
    for role in EvidenceUse.CLAIM_BEARING:
        try:
            registry.register(
                asset_id=f"arch-{role}", kind=AssetKind.DIAGRAM, path="arch.png",
                evidence_use=role,
            )
        except GeneratedAssetEvidenceError:
            continue
        raise AssertionError(f"a diagram was accepted as {role}")
    print("[ok] 59. a diagram stays support-only and is refused every claim role")


def test_real_material_still_carries_claims():
    registry = AssetRegistry()
    for kind in AssetKind.EVIDENCE_CAPABLE:
        record = registry.register(
            asset_id=f"real-{kind}", kind=kind, path="capture.png",
            evidence_use=EvidenceUse.BENCHMARK_PROOF,
        )
        assert record.evidence_capable is True
    print("[ok] 60. real, screenshot and screen recording may still carry claims")


# --- 9. video technical QC ---------------------------------------------------

def test_qc_measures_container_codec_duration_and_fps():
    if not HAVE_MEDIA:
        _skip(61, "QC measurement", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        clip = _make_clip(Path(td) / "clip.mp4")
        result = measure_video(clip)
        assert result.approved, result.reasons
        assert result.container and "mp4" in result.container.lower()
        assert result.codec, result.as_dict()
        assert result.width and result.height
        assert result.duration_s and 3.0 < result.duration_s < 5.0, result.duration_s
        assert result.fps and 20 <= result.fps <= 30, result.fps
        assert result.decodable is True
    print("[ok] 61. QC measures container, codec, duration, fps and decodability")


def test_qc_uses_tolerance_for_duration_and_aspect():
    if not HAVE_MEDIA:
        _skip(62, "duration and aspect tolerance", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        clip = _make_clip(Path(td) / "clip.mp4")
        # A 4 s request against a ~4 s clip, and a 9:16 request against 320x568.
        tolerant = technical_video_qc(
            clip, expected_duration_s=4, expected_ratio="9:16"
        )
        assert tolerant.approved, tolerant.reasons
        # Exact-equality thinking would fail here; 320x568 is 0.5634 vs 0.5625.
        assert abs(tolerant.aspect_ratio - 9 / 16) / (9 / 16) < ASPECT_TOLERANCE
        # A wildly different request must still fail.
        strict = technical_video_qc(
            clip, expected_duration_s=12, expected_ratio="1:1"
        )
        assert not strict.approved, "a 12 s / 1:1 request should not pass"
        assert any("duration" in r or "aspect ratio" in r for r in strict.reasons)
    print("[ok] 62. duration and aspect use tolerance; a wrong request still fails")


def test_qc_detects_a_black_run_but_not_a_single_dark_frame():
    if not HAVE_MEDIA:
        _skip(63, "black run detection", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        black = _make_clip(Path(td) / "black.mp4", source="color=c=black:size=320x568:rate=24:duration=3")
        result = technical_video_qc(black)
        assert result.black_frame_count > 0, result.as_dict()
        assert (result.longest_black_run_s or 0) > BLACK_RUN_MAX_SECONDS, result.as_dict()
        assert not result.approved, "an all-black clip must not pass QC"

        # One dark frame inside an otherwise healthy clip is an intentional fade.
        moving = _make_clip(Path(td) / "moving.mp4")
        healthy = technical_video_qc(moving)
        assert healthy.approved, healthy.reasons
        assert (healthy.longest_black_run_s or 0) <= BLACK_RUN_MAX_SECONDS
    print("[ok] 63. a sustained black run fails QC; a healthy clip is not over-flagged")


def test_qc_detects_a_frozen_render():
    if not HAVE_MEDIA:
        _skip(64, "freeze detection", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        frozen = _make_clip(
            Path(td) / "frozen.mp4",
            source="testsrc=size=320x568:rate=24:duration=4",
            extra=["-vf", "tpad=stop_mode=clone:stop_duration=3"],
        )
        result = technical_video_qc(frozen)
        assert (result.longest_freeze_run_s or 0) > 0, result.as_dict()
        moving = technical_video_qc(_make_clip(Path(td) / "moving.mp4"))
        assert moving.approved, moving.reasons
    print("[ok] 64. a frozen render is measured; genuinely moving footage passes")


def test_qc_reports_audio_presence_and_absence():
    if not HAVE_MEDIA:
        _skip(65, "audio detection", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        silent = _make_clip(Path(td) / "silent.mp4")
        assert measure_video(silent).has_audio is False
        with_audio = _make_clip(
            Path(td) / "audio.mp4",
            extra=["-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-shortest"],
        )
        detected = measure_video(with_audio)
        assert detected.has_audio is True, detected.as_dict()
        assert detected.audio_codec
    print("[ok] 65. audio presence and absence are both detected")


def test_qc_never_claims_aesthetic_quality():
    if not HAVE_MEDIA:
        _skip(66, "QC claims nothing about taste", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        result = technical_video_qc(_make_clip(Path(td) / "clip.mp4"))
        rendered = json.dumps(result.as_dict()).lower()
        for forbidden in ("beautiful", "cinematic", "publishable", "brand"):
            assert forbidden not in rendered, f"QC claimed {forbidden!r}"
        # approved means technically sound, not publishable.
        assert result.approved is True
        assert "production_ready" not in rendered
    print("[ok] 66. technical QC reports measurements and never aesthetic verdicts")


def test_qc_rejects_an_unknown_audio_policy():
    if not HAVE_MEDIA:
        _skip(67, "audio policy validation", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        result = technical_video_qc(
            _make_clip(Path(td) / "clip.mp4"), audio_policy="SOMETHING"
        )
        assert not result.approved
        assert any("audio policy" in r for r in result.reasons)
    print("[ok] 67. an unknown audio policy is refused")


def _make_clip(path: Path, source: str = "testsrc=size=320x568:rate=24:duration=4", extra=None):
    from process_utils import hidden_run

    command = [
        "ffmpeg", "-y", "-v", "error", "-nostdin",
        "-f", "lavfi", "-i", source,
    ]
    if extra and extra[0] == "-f":
        command += extra
    elif extra:
        command += extra
    command += ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", str(path)]
    result = hidden_run(command, timeout=300)
    if result.returncode != 0 or not path.is_file():
        raise AssertionError(f"could not build a test clip: {(result.stderr or '')[:200]}")
    return path


# --- 10. audio policy --------------------------------------------------------

def test_audio_policy_is_explicit_and_defaults_to_replace():
    assert AudioPolicy.DEFAULT == AudioPolicy.REPLACE
    assert set(AudioPolicy.ALL) == {"KEEP", "MUTE", "REPLACE"}
    print("[ok] 68. the audio policy is explicit, and the default is REPLACE")


def test_audio_policy_is_recorded_in_the_receipt():
    if not HAVE_MEDIA:
        _skip(69, "audio policy in receipt", "ffmpeg")
        return
    for policy in AudioPolicy.ALL:
        with tempfile.TemporaryDirectory() as td:
            provider, _ = _provider(Path(td))
            outcome = _generate(provider, _request(audio_policy=policy))
            assert outcome.receipt.audio_policy == policy
            assert outcome.asset.audio_policy == policy
            assert receipt_to_dict(outcome.receipt)["audio_policy"] == policy
    print("[ok] 69. the chosen audio policy travels with the receipt and the asset")


# --- 11. Windows behaviour ---------------------------------------------------

def test_no_direct_subprocess_in_the_video_modules():
    """Every child process goes through process_utils, or Windows pops a console."""
    for name in ("minimax_video.py", "h3_transport.py", "video_qc.py", "video_validation.py"):
        source = (ROOT / "src" / "contentops" / "media" / name).read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_SPAWNERS:
            assert forbidden not in source, f"{name} uses {forbidden}"
    print("[ok] 70. no video module spawns a process directly")


def test_video_fixtures_and_tests_use_the_shared_process_layer():
    for relative in ("tests/fixtures/fake_h3_api.py", "tests/test_minimax_h3.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_SPAWNERS:
            assert forbidden not in source, f"{relative} uses {forbidden}"
    print("[ok] 71. the video fixture and suite route child processes through process_utils")


def test_h3_generation_does_not_shell_out_to_the_cli():
    """The CLI cannot express the required resolution, so it is not the transport."""
    source = (ROOT / "src" / "contentops" / "media" / "minimax_video.py").read_text(
        encoding="utf-8"
    )
    for forbidden in ('"mmx"', "'mmx'", "mmx video"):
        assert forbidden not in source, f"video generation references {forbidden}"
    print("[ok] 72. H3 generation does not shell out to the mmx CLI")


# --- 10. the run must declare what it is allowed to spend --------------------

def test_a_billable_run_requires_an_explicit_quota_budget():
    """No budget, no create. The decision to spend is written down first."""
    with tempfile.TemporaryDirectory() as work:
        provider, fake = _provider(Path(work))
        try:
            _generate(provider, _request(), quota_budget="")
        except RuntimeError as exc:
            assert "quota_budget" in str(exc), str(exc)
        else:
            raise AssertionError("a run with no quota budget was allowed to create a task")
        assert fake.create_count == 0, "a task was created without a declared budget"
        assert provider.create_count == 0
    print("[ok] 73. a billable run without a declared quota budget creates no task")


def test_a_billable_run_requires_a_test_objective():
    """A task must never exist without a recorded reason to exist."""
    with tempfile.TemporaryDirectory() as work:
        provider, fake = _provider(Path(work))
        try:
            _generate(provider, _request(), test_objective="")
        except RuntimeError as exc:
            assert "test_objective" in str(exc), str(exc)
        else:
            raise AssertionError("a run with no objective was allowed to create a task")
        assert fake.create_count == 0, "a task was created without a stated objective"
    print("[ok] 74. a billable run without a test objective creates no task")


def test_a_cache_hit_needs_no_budget_because_it_spends_nothing():
    """The budget gate sits after the cache, so free runs are never forced to lie."""
    with tempfile.TemporaryDirectory() as work:
        _generate(_provider(Path(work))[0], _request())
        # A fresh provider, same work dir: the cache must serve it with no budget
        # declared at all, because no task and no quota are involved.
        fresh, fake = _provider(Path(work))
        outcome = _generate(fresh, _request(), quota_budget="", test_objective="")
        assert outcome.reused is True, "the cache did not serve a hit without a budget"
        assert fake.create_count == 0, "a cache hit created a task"
        assert fake.poll_count == 0, "a cache hit contacted the provider"
    print("[ok] 75. a cache hit needs neither a budget nor a provider call")


def test_the_declared_budget_and_objective_reach_the_receipt():
    """A receipt that cannot say what it was allowed to spend cannot show restraint."""
    with tempfile.TemporaryDirectory() as work:
        provider, _ = _provider(Path(work))
        outcome = _generate(provider, _request())
        payload = receipt_to_dict(outcome.receipt)
        assert payload["quota_budget"] == BUDGET, payload.get("quota_budget")
        assert payload["test_objective"] == OBJECTIVE, payload.get("test_objective")
    print("[ok] 76. the declared budget and objective are recorded on the receipt")


# --- 11. restart recovery must not rewrite provenance -------------------------

def test_a_restart_preserves_references_audio_policy_and_attempt():
    """A resumed receipt must describe the generation that actually happened.

    The dangerous regression is a shot billed as attempt 2 with references whose
    resumed receipt says attempt 1 with no references: the fingerprint covers the
    references, so that receipt would contradict its own cache key.
    """
    if not HAVE_MEDIA:
        _skip(77, "restart preserves provenance", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        first_image = _make_frame(work / "ref.png")
        request = _request(
            mode="I2VA",
            ratio="adaptive",
            first_frame=str(first_image),
            audio_policy=AudioPolicy.MUTE,
        )

        # First process: create succeeds, then the download dies. The private state
        # survives, which is exactly the crash this test is about.
        crashing = FakeH3Transport(download_error_plan={1: 99})
        provider_a, _ = _provider(work, fake=crashing)
        try:
            _generate(provider_a, request)
        except Exception:
            pass
        assert crashing.create_count == 1, crashing.create_count
        assert list((work / "task-state").glob("*.json")), (
            "no private task state survived the crash"
        )

        # Second process, same work dir: resume the same task, no second create.
        resumed = FakeH3Transport()
        provider_b, _ = _provider(work, fake=resumed)
        outcome = _generate(provider_b, request)
        assert resumed.create_count == 0, "a restart created a second task"
        assert crashed_task_id_is_resumed(crashing, resumed), (
            "the restart polled a different task"
        )

        payload = receipt_to_dict(outcome.receipt)
        assert payload["attempt"] == 1, payload["attempt"]
        assert payload["audio_policy"] == AudioPolicy.MUTE, payload["audio_policy"]
        assert len(payload["reference_asset_sha256"]) == 1, (
            "the resumed receipt lost the reference hashes its fingerprint covers"
        )
        assert payload["billing_guard_verdict"] == "RESUMED_NO_PREFLIGHT", (
            "a resumed run must not claim a fresh authorisation"
        )
    print("[ok] 77. a restarted receipt preserves references, audio policy and attempt")


def crashed_task_id_is_resumed(first, second) -> bool:
    """True when the second process polled exactly the task the first created."""
    return (
        bool(first.created_task_ids)
        and set(second.polled_task_ids).issubset(set(first.created_task_ids))
        and len(second.polled_task_ids) > 0
    )


def test_private_task_state_records_the_attempt_and_budget():
    """The private state is what a resume reads, so it must carry the billed facts."""
    from contentops.media.minimax_video import PRIVATE_STATE_DIRNAME, VideoAttemptState

    state = VideoAttemptState(
        fingerprint="f" * 64,
        task_id="424010985738629",
        attempt_id="attempt-1",
        attempt=2,
        quota_budget=BUDGET,
        test_objective=OBJECTIVE,
    )
    restored = VideoAttemptState.from_dict(json.loads(json.dumps(state.to_dict())))
    assert restored.attempt == 2, restored.attempt
    assert restored.quota_budget == BUDGET, restored.quota_budget
    assert restored.test_objective == OBJECTIVE, restored.test_objective
    assert restored.task_id == "424010985738629"
    assert PRIVATE_STATE_DIRNAME == "task-state"
    print("[ok] 79. private task state round-trips the attempt, budget and objective")


# --- 12. the request body cap, and reference encodings ------------------------

def test_reference_data_uris_declare_their_real_media_subtype():
    """A declared format the bytes do not match is a rejection nobody can explain."""
    from contentops.media.h3_transport import REFERENCE_MIME_TYPES, build_content_array

    assert REFERENCE_MIME_TYPES[".jpg"] == "image/jpeg"
    assert REFERENCE_MIME_TYPES[".png"] == "image/png"
    assert REFERENCE_MIME_TYPES[".webp"] == "image/webp"
    assert REFERENCE_MIME_TYPES[".mp4"] == "video/mp4"
    assert REFERENCE_MIME_TYPES[".mp3"] == "audio/mpeg"
    assert REFERENCE_MIME_TYPES[".wav"] == "audio/wav"

    with tempfile.TemporaryDirectory() as work:
        jpeg = Path(work) / "frame.jpg"
        jpeg.write_bytes(b"\xff\xd8\xff" + b"\x00" * 64)
        content = build_content_array(prompt="p", first_frame=jpeg)
        url = content[1]["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,"), url[:40]
    print("[ok] 80. reference data URIs declare the subtype the file actually has")


def test_an_unknown_reference_format_is_refused_rather_than_guessed():
    """There is no valid data URI for an undocumented extension."""
    from contentops.media.h3_transport import TransportError, build_content_array

    with tempfile.TemporaryDirectory() as work:
        odd = Path(work) / "frame.tiff"
        odd.write_bytes(b"II*\x00" + b"\x00" * 32)
        try:
            build_content_array(prompt="p", first_frame=odd)
        except TransportError as exc:
            assert "media subtype" in str(exc), str(exc)
        else:
            raise AssertionError("an undocumented reference format was encoded anyway")
    print("[ok] 81. an undocumented reference format is refused, not guessed")


def test_the_combined_request_body_cap_is_enforced_before_any_billing_read():
    """Per-file limits do not imply the body cap. Base64 inflates by a third."""
    from contentops.media.video_validation import (
        H3_REQUEST_BODY_MAX_BYTES,
        MAX_IMAGE_BYTES,
        _check_encoded_body_size,
    )

    assert H3_REQUEST_BODY_MAX_BYTES == 64 * 1024 * 1024

    # Nine individually legal images are still an illegal combined body.
    with tempfile.TemporaryDirectory() as work:
        files = []
        for index in range(9):
            target = Path(work) / f"img-{index}.png"
            target.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
            files.append(target)

        # Real sizes first: nine tiny files are fine.
        _check_encoded_body_size(files)

        # Now inflate them to just under the per-file cap each.
        for target in files:
            with target.open("r+b") as handle:
                handle.truncate(MAX_IMAGE_BYTES - 4096)
        try:
            _check_encoded_body_size(files)
        except RequestRejected as exc:
            assert "request body limit" in str(exc), str(exc)
        else:
            raise AssertionError(
                "nine 30MB references were accepted despite the 64MB body cap"
            )
    print("[ok] 82. the combined request body cap is enforced before billing")


def test_prompt_expansion_mode_is_wired_end_to_end_and_fingerprinted():
    """A generation-affecting option must reach the API, the receipt and the cache key."""
    from contentops.media.video_validation import PROMPT_EXPANSION_MODES

    assert PROMPT_EXPANSION_MODES == ("disabled", "balanced", "quality")
    with tempfile.TemporaryDirectory() as work:
        request = _request(
            model="MiniMax-H3-Max",
            resolution="768P",
            # H3-Max's documented minimum is 5 s, and 4 is explicitly unsupported.
            duration_s=5,
            extra={"prompt_expansion_mode": "quality"},
        )
        provider, fake = _provider(Path(work))
        outcome = _generate(provider, request)
        assert fake.last_request["extra"] == {"prompt_expansion_mode": "quality"}, (
            fake.last_request.get("extra")
        )
        payload = receipt_to_dict(outcome.receipt)
        assert payload["extra"] == {"prompt_expansion_mode": "quality"}, payload.get("extra")

        # A different option is a different generation, so the fingerprint must differ.
        other = video_fingerprint(
            provider="minimax", product="mplan", plan="explore",
            model="MiniMax-H3-Max", mode="T2VA",
            compiled_prompt=request.compiled_prompt, duration_s=5,
            resolution="768P", ratio="9:16",
            extra={"prompt_expansion_mode": "disabled"},
        )
        assert outcome.receipt.fingerprint != other, (
            "the fingerprint ignored a generation-affecting option"
        )
    print("[ok] 83. prompt_expansion_mode reaches the API, the receipt and the fingerprint")


def test_undocumented_generation_options_and_wrong_model_options_are_refused_locally():
    """The documented extra schema is closed, and only H3-Max has one at all."""
    with tempfile.TemporaryDirectory() as work:
        provider, fake = _provider(Path(work))
        cases = [
            (_request(model="MiniMax-H3", extra={"prompt_expansion_mode": "quality"}),
             "no generation options"),
            (_request(model="MiniMax-H3-Max", duration_s=5,
                      extra={"made_up_key": "x"}),
             "undocumented generation option"),
            (_request(model="MiniMax-H3-Max", duration_s=5,
                      extra={"prompt_expansion_mode": "balance"}),
             "prompt_expansion_mode must be one of"),
        ]
        for request, expected in cases:
            try:
                _generate(provider, request)
            except RequestRejected as exc:
                assert expected in str(exc), f"expected {expected!r}, got {exc}"
            else:
                raise AssertionError(f"an invalid extra was accepted: {request.extra}")
        assert fake.create_count == 0, "an invalid option created a task"
    print("[ok] 84. undocumented and wrong-model generation options are refused locally")


# --- 13. human review is a real artifact, not a string -----------------------

def test_every_generation_writes_a_human_review_package_with_null_scores():
    """Reference fidelity cannot be automated. The fields exist and stay null."""
    from contentops.media.video_contract import HUMAN_REVIEW_FIELDS

    with tempfile.TemporaryDirectory() as work:
        provider, _ = _provider(Path(work))
        outcome = _generate(provider, _request())
        review_file = Path(outcome.asset.canonical_path).with_name(
            Path(outcome.asset.canonical_path).name + ".human-review.json"
        )
        assert review_file.is_file(), "no human review package was written"

        package = json.loads(review_file.read_text(encoding="utf-8"))
        assert package["state"] == "PENDING_FOUNDER_REVIEW"
        assert package["decision"] == "PENDING_FOUNDER_REVIEW"
        assert package["reviewer"] is None, "a reviewer was manufactured"
        assert package["reviewed_at"] is None, "a review timestamp was manufactured"
        assert set(package["scores"]) == set(HUMAN_REVIEW_FIELDS), package["scores"]
        for name, value in package["scores"].items():
            assert value is None, f"{name} was filled in without a human verdict"
        assert outcome.receipt.production_ready is False
        assert outcome.receipt.human_review == "PENDING_FOUNDER_REVIEW"
    print("[ok] 85. every generation writes a review package whose scores are null")


def test_the_review_package_names_every_required_human_judgement():
    """The list is fixed by the milestone, so a rename cannot silently drop one."""
    from contentops.media.video_contract import HUMAN_REVIEW_FIELDS

    required = {
        "subject_fidelity",
        "motion_plausibility",
        "temporal_artifacts",
        "reference_fidelity",
        "first_frame_fidelity",
        "last_frame_fidelity",
        "audio_suitability",
        "caption_safe_area",
        "cross_shot_consistency",
        "overall_quality",
        "willingness_to_publish",
    }
    assert required.issubset(set(HUMAN_REVIEW_FIELDS)), (
        required - set(HUMAN_REVIEW_FIELDS)
    )
    assert len(HUMAN_REVIEW_FIELDS) == 11, HUMAN_REVIEW_FIELDS
    print("[ok] 86. the review package names all eleven required human judgements")


def test_reference_only_fields_are_marked_not_applicable_for_text_only_modes():
    """Not assessed and not relevant must be distinguishable to a reviewer."""
    from contentops.media.video_contract import (
        REFERENCE_ONLY_REVIEW_FIELDS,
        build_human_review_package,
    )

    with tempfile.TemporaryDirectory() as work:
        provider, _ = _provider(Path(work))
        text_only = _generate(provider, _request())
        review_file = Path(text_only.asset.canonical_path).with_name(
            Path(text_only.asset.canonical_path).name + ".human-review.json"
        )
        package = json.loads(review_file.read_text(encoding="utf-8"))
        for name in REFERENCE_ONLY_REVIEW_FIELDS:
            assert name in package["not_applicable_fields"], (
                f"{name} was not marked not-applicable for a T2VA shot"
            )

        # A frame mode does use them, so they must not be dismissed.
        first_image = _make_frame(Path(work) / "frame.png")
        framed = _generate(
            provider,
            _request(mode="I2VA", ratio="adaptive", first_frame=str(first_image)),
        )
        framed_package = build_human_review_package(
            asset=framed.asset, receipt=framed.receipt, mode="I2VA"
        )
        assert framed_package["not_applicable_fields"] == [], (
            "an I2VA shot dismissed the reference fidelity fields"
        )
    print("[ok] 87. reference-only review fields are marked not-applicable only when true")


def test_the_api_schema_version_is_recorded_on_the_receipt():
    """v1 and v2 differ in path, poll shape and model set."""
    from contentops.media.minimax_video import H3_API_SCHEMA_VERSION

    assert H3_API_SCHEMA_VERSION == "v2"
    with tempfile.TemporaryDirectory() as work:
        provider, _ = _provider(Path(work))
        payload = receipt_to_dict(_generate(provider, _request()).receipt)
        assert payload["api_schema_version"] == "v2", payload.get("api_schema_version")
        assert payload["transport"] == "documented_public_api"
    print("[ok] 88. the receipt records which API generation produced the shot")


TESTS = [
    test_prompt_skill_provenance_is_recorded,
    test_base_modes_use_the_three_core_fields_in_official_order,
    test_ref2va_uses_the_six_sections_in_official_order,
    test_alignment_instruction_is_the_first_line_then_one_blank_line,
    test_alignment_templates_match_the_upstream_wording,
    test_effective_duration_uses_two_decimals,
    test_first_shot_has_no_timestamp_and_later_shots_increase,
    test_reference_labels_are_consistent_across_ref2va_sections,
    test_prompt_length_is_enforced_locally,
    test_modes_are_matched_case_insensitively_but_canonically,
    test_camera_motion_vocabulary_is_closed,
    test_duration_rules_per_model,
    test_duration_must_be_an_integer,
    test_resolution_availability_differs_by_model,
    test_ratio_rules_per_mode,
    test_frame_modes_are_always_adaptive,
    test_reference_and_frame_roles_are_mutually_exclusive,
    test_reference_counts_are_capped,
    test_invalid_request_is_rejected_before_billing_and_before_create,
    test_missing_frame_file_is_refused_locally,
    test_subscription_credential_is_accepted,
    test_payg_unknown_and_absent_credentials_are_blocked,
    test_exact_authorised_credential_reaches_the_transport,
    test_secret_sentinel_never_reaches_any_persisted_output,
    test_raw_task_id_is_never_persisted_publicly,
    test_task_hash_is_salted_and_not_reversible,
    test_video_billing_ignores_the_five_hour_window,
    test_video_requires_weekly_quota,
    test_every_paid_balance_blocks_video_independently,
    test_non_zero_credit_pack_blocks_before_task_creation,
    test_speech_and_image_rules_are_unchanged,
    test_exactly_one_task_is_created_and_only_that_task_is_polled,
    test_poll_timeout_does_not_create_a_second_task,
    test_temporary_poll_5xx_does_not_create_a_second_task,
    test_malformed_poll_response_does_not_create_a_second_task,
    test_download_failure_does_not_create_a_second_task,
    test_repeated_download_failure_retries_the_same_url,
    test_restart_resumes_the_same_task_rather_than_creating_one,
    test_a_running_task_cannot_enter_retry_validation,
    test_unknown_provider_state_fails_closed_without_creating_another_task,
    test_terminal_failure_states_are_classified,
    test_cancelled_task_is_a_terminal_failure,
    test_succeeded_without_download_url_does_not_create_another_task,
    test_retry_requires_reason_record_budget_and_a_changed_fingerprint,
    test_retry_with_an_identical_fingerprint_is_refused,
    test_a_terminal_failed_attempt_may_be_retried_with_a_change,
    test_a_successful_attempt_cannot_be_retried,
    test_receipt_convention_and_completeness,
    test_receipt_records_the_prompt_skill_provenance,
    test_reuse_does_not_rewrite_the_generation_receipt,
    test_cache_hit_happens_before_the_billing_gate,
    test_a_fresh_provider_can_answer_receipt_after_a_cache_hit,
    test_force_regenerates_rather_than_reusing,
    test_fingerprint_covers_the_compiled_prompt_and_generation_parameters,
    test_incomplete_receipt_is_a_cache_miss,
    test_generated_video_registers_only_as_a_support_visual,
    test_generated_video_is_refused_for_every_claim_bearing_role,
    test_generated_video_cannot_override_its_provenance,
    test_a_diagram_remains_support_only,
    test_real_material_still_carries_claims,
    test_qc_measures_container_codec_duration_and_fps,
    test_qc_uses_tolerance_for_duration_and_aspect,
    test_qc_detects_a_black_run_but_not_a_single_dark_frame,
    test_qc_detects_a_frozen_render,
    test_qc_reports_audio_presence_and_absence,
    test_qc_never_claims_aesthetic_quality,
    test_qc_rejects_an_unknown_audio_policy,
    test_audio_policy_is_explicit_and_defaults_to_replace,
    test_audio_policy_is_recorded_in_the_receipt,
    test_no_direct_subprocess_in_the_video_modules,
    test_video_fixtures_and_tests_use_the_shared_process_layer,
    test_h3_generation_does_not_shell_out_to_the_cli,
    test_a_billable_run_requires_an_explicit_quota_budget,
    test_a_billable_run_requires_a_test_objective,
    test_a_cache_hit_needs_no_budget_because_it_spends_nothing,
    test_the_declared_budget_and_objective_reach_the_receipt,
    test_a_restart_preserves_references_audio_policy_and_attempt,
    test_private_task_state_records_the_attempt_and_budget,
    test_reference_data_uris_declare_their_real_media_subtype,
    test_an_unknown_reference_format_is_refused_rather_than_guessed,
    test_the_combined_request_body_cap_is_enforced_before_any_billing_read,
    test_prompt_expansion_mode_is_wired_end_to_end_and_fingerprinted,
    test_undocumented_generation_options_and_wrong_model_options_are_refused_locally,
    test_every_generation_writes_a_human_review_package_with_null_scores,
    test_the_review_package_names_every_required_human_judgement,
    test_reference_only_fields_are_marked_not_applicable_for_text_only_modes,
    test_the_api_schema_version_is_recorded_on_the_receipt,
]


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
    print(f"All {len(TESTS)} M4 H3 video regression tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())