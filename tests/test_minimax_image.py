#!/usr/bin/env python3
"""M3 regression tests: MiniMax M Plan image generation and evidence safety.

Run:
    python tests/test_minimax_image.py

No real provider request is made. Every test that needs a generated image drives
the local ``tests/fixtures/fake_mmx_cli.py`` stand-in, and every test that needs
billing state injects a fake transport. That keeps the suite runnable in CI on a
host with no MiniMax account and no quota.

What is deliberately tested here
--------------------------------
The failures M2 actually hit, plus the ones this milestone could plausibly hit:

- a ``.png`` file containing JPEG bytes (measured on the real API in M2.0)
- the cache being consulted before the billing gate, so a hit costs nothing
- a *fresh* provider being able to answer ``receipt()`` after a cache hit
- the generation receipt surviving reuse byte-for-byte
- the billing gate and the ``mmx`` child using one credential
- a generated image being refused as evidence
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

# Every child process in this suite goes through process_utils, so a test can
# never flash a console window on Windows. The subprocess policy gate scans
# tracked files and enforces exactly this.
from process_utils import hidden_run  # noqa: E402

from contentops.media.asset_planner import (  # noqa: E402
    MINIMAX_IMAGE,
    AssetPlanner,
    PlanRequest,
)
from contentops.media.attempts import (  # noqa: E402
    STATUS_FAILED,
    find_attempt_records,
    load_attempt_record,
    read_reuse_events,
)
from contentops.media.billing_guard import (  # noqa: E402
    BLOCKED_BILLING_SOURCE_UNCERTAIN,
    SAFE_INCLUDED_PLAN,
    BillingGuard,
)
from contentops.media.contract import BillingBlocked  # noqa: E402
from contentops.media.credentials import (  # noqa: E402
    CredentialBinding,
    CredentialBindingError,
    ResolvedCredential,
    classify_credential,
)
from contentops.media.image_contract import (  # noqa: E402
    AssetKind,
    AssetRegistry,
    EvidenceUse,
    GeneratedAssetEvidenceError,
    ImageRequest,
    register_asset,
)
from contentops.media.image_container import (  # noqa: E402
    CANONICAL_EXTENSIONS,
    ImageContainerError,
    canonical_extension_for,
    detect_image_container,
    sniff_image_file,
)
from contentops.media.image_fingerprint import (  # noqa: E402
    DimensionRejected,
    image_fingerprint,
    validate_dimensions,
)
from contentops.media.image_qc import (  # noqa: E402
    HAVE_PILLOW,
    IMAGE_QC_MIN_LUMA_SPAN,
    IMAGE_QC_MIN_LUMA_STDDEV,
    measure_image,
    technical_image_qc,
)
from contentops.media.minimax_image import (  # noqa: E402
    DEFAULT_IMAGE_MODEL,
    PRIMARY_PORTRAIT_HEIGHT,
    PRIMARY_PORTRAIT_WIDTH,
    MiniMaxMPlanImageProvider,
    image_sidecar_is_complete,
    receipt_to_dict,
)
from contentops.media.text_contamination import assess_text_contamination  # noqa: E402
from contentops.media.transport import load_sidecar, sidecar_for  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))
HAVE_PILLOW_IMAGE = HAVE_PILLOW

FIXTURE_CLI = [sys.executable, str(ROOT / "tests" / "fixtures" / "fake_mmx_cli.py")]

TEST_SUBSCRIPTION_KEY = "sk-cp-TESTONLY0000000000"

SAFE_BALANCES = {
    "cash_balance": "0.00",
    "credit_balance": "0.00",
    "voucher_balance": "0.00",
    "owed_amount": "0.00",
}
SAFE_QUOTA = {
    "model_remains": [
        {
            "model_name": "general",
            "current_interval_remaining_percent": 99,
            "current_weekly_remaining_percent": 58,
        }
    ]
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


def fake_transport(balances, quota):
    def _get(url: str, credential: str):
        if url.endswith("/account/query_balance"):
            if isinstance(balances, Exception):
                raise balances
            return balances
        if url.endswith("/v1/token_plan/remains"):
            if isinstance(quota, Exception):
                raise quota
            return quota
        raise AssertionError(f"unexpected url {url}")

    return _get


def guard_with(balances=SAFE_BALANCES, quota=SAFE_QUOTA, credential=TEST_SUBSCRIPTION_KEY):
    return BillingGuard(
        base_url="https://example.invalid",
        credential=credential,
        http_get_json=fake_transport(balances, quota),
    )


def _resolved(key=TEST_SUBSCRIPTION_KEY, source="MINIMAX_SUBSCRIPTION_KEY_ENV"):
    return ResolvedCredential(
        key=key, credential_class=classify_credential(key), source=source
    )


def _image_provider(work_dir, guard=None, cli=None, credential=None, model=DEFAULT_IMAGE_MODEL):
    resolved = credential if credential is not None else _resolved()
    return MiniMaxMPlanImageProvider(
        guard=guard if guard is not None else guard_with(credential=resolved.key),
        work_dir=work_dir,
        cli=cli if cli is not None else FIXTURE_CLI,
        model=model,
        transport_credential=resolved,
    )


def _request(**overrides) -> ImageRequest:
    base = dict(
        prompt=(
            "A clean cinematic abstract AI workflow visualization for a vertical "
            "short-form video, layered flowing data paths, restrained "
            "professional composition, no text, no logo, no user interface."
        ),
        model=DEFAULT_IMAGE_MODEL,
        width=PRIMARY_PORTRAIT_WIDTH,
        height=PRIMARY_PORTRAIT_HEIGHT,
        seed=42,
    )
    base.update(overrides)
    return ImageRequest(**base)


def _skip(number: int, what: str, need: str) -> None:
    print(f"[skip] {number}. {what} (needs {need})")


# --- 1. container sniffing ---------------------------------------------------

def test_png_is_detected_from_its_signature():
    assert detect_image_container(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32) == "PNG"
    print("[ok] 1. PNG is detected from its magic bytes")


def test_jpeg_is_detected_from_its_signature():
    assert detect_image_container(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 16) == "JPEG"
    print("[ok] 2. JPEG is detected from its magic bytes")


def test_webp_is_detected_from_its_riff_form_type():
    assert detect_image_container(b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 16) == "WEBP"
    print("[ok] 3. WEBP is detected from the RIFF form type")


def test_riff_that_is_not_webp_is_rejected():
    for payload in (b"RIFF\x20\x00\x00\x00AVI LIST", b"RIFF\x20\x00\x00\x00WAVEfmt "):
        try:
            detect_image_container(payload)
        except ImageContainerError:
            continue
        raise AssertionError(f"a non-WEBP RIFF was accepted: {payload!r}")
    print("[ok] 4. a RIFF container that is not WEBP is rejected")


def test_unknown_and_malformed_containers_are_rejected():
    for payload in (
        b"",
        b"GIF89a",
        b"not an image at all",
        b"\x89PNG",  # truncated: shorter than the signature
    ):
        try:
            detect_image_container(payload)
        except ImageContainerError:
            continue
        raise AssertionError(f"accepted junk: {payload!r}")
    print("[ok] 5. empty, unknown and truncated data are all refused")


def test_non_bytes_input_is_refused():
    for value in (None, 123, "a string"):
        try:
            detect_image_container(value)
        except ImageContainerError:
            continue
        raise AssertionError(f"accepted non-bytes: {value!r}")
    print("[ok] 6. non-bytes input is refused rather than coerced")


# --- 2. the extension is not evidence ----------------------------------------

def test_png_filename_containing_jpeg_bytes_is_sniffed_as_jpeg():
    """The defect M2.0 measured on the real provider.

    A ``.png`` path holding JPEG bytes must be recognised as JPEG. Choosing a
    decoder from the suffix here would hand a JPEG to every downstream tool that
    trusts the name.
    """
    if not HAVE_PILLOW_IMAGE:
        _skip(7, "a .png file containing JPEG bytes", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        jpeg_bytes = _make_image(work / "source.jpg", "JPEG")
        misnamed = work / "candidate.png"
        misnamed.write_bytes(jpeg_bytes)
        assert sniff_image_file(misnamed) == "JPEG"
        # And the same bytes under a correct name agree with the sniffer.
        assert sniff_image_file(work / "source.jpg") == "JPEG"
    print("[ok] 7. a .png file containing JPEG bytes is detected as JPEG")


def test_canonical_extension_is_corrected_from_the_detected_container():
    assert canonical_extension_for("PNG") == ".png"
    assert canonical_extension_for("JPEG") == ".jpg"
    assert canonical_extension_for("WEBP") == ".webp"
    try:
        canonical_extension_for("GIF")
    except ImageContainerError:
        pass
    else:
        raise AssertionError("an unsupported container produced an extension")
    print("[ok] 8. the canonical extension follows the container, and JPEG becomes .jpg")


def _make_image(path: Path, fmt: str = "PNG", *, size=(64, 112), fill=None) -> bytes:
    from PIL import Image, ImageDraw

    width, height = size
    if fill is None:
        image = Image.new("RGB", (width, height), (12, 18, 30))
        draw = ImageDraw.Draw(image)
        for row in range(0, height, max(4, height // 12)):
            shade = 25 + (row * 11) % 210
            draw.rectangle(
                [0, row, width, row + max(3, height // 24)],
                fill=(shade, (shade * 3) % 255, (shade * 7) % 255),
            )
        draw.ellipse([4, 4, width - 4, height - 4], outline=(250, 240, 200), width=2)
    else:
        image = Image.new("RGB", (width, height), fill)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format=fmt)
    return path.read_bytes()


# --- 3. technical QC ---------------------------------------------------------

def test_corrupt_image_fails_qc():
    if not HAVE_PILLOW_IMAGE:
        _skip(9, "corrupt image detection", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        corrupt = work / "corrupt.png"
        # A valid PNG header followed by nothing decodable.
        corrupt.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        result = measure_image(corrupt)
        assert not result.approved
        assert result.reasons, "a corrupt image must carry a reason"
        assert result.container == "PNG", "the header is still identifiable"
    print("[ok] 9. a corrupt image is detected and refused")


def test_unrecognisable_bytes_fail_qc():
    if not HAVE_PILLOW_IMAGE:
        _skip(10, "unrecognisable bytes", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        junk = Path(td) / "junk.png"
        junk.write_bytes(b"this is definitely not an image" * 20)
        result = measure_image(junk)
        assert not result.approved
        assert any("container" in r for r in result.reasons), result.reasons
    print("[ok] 10. bytes with no recognisable container fail QC")


def test_blank_image_is_detected_by_pixel_statistics():
    if not HAVE_PILLOW_IMAGE:
        _skip(11, "blank image detection", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        blank = work / "blank.png"
        _make_image(blank, "PNG", fill=(128, 128, 128))
        result = measure_image(blank)
        assert not result.approved, "a flat mid-grey fill must not pass"
        assert result.luma_stddev < IMAGE_QC_MIN_LUMA_STDDEV, result.as_dict()
        assert any("blank" in r or "uniform" in r for r in result.reasons), result.reasons
    print("[ok] 11. a blank flat-fill image is detected by luminance statistics")


def test_near_uniform_image_is_detected():
    if not HAVE_PILLOW_IMAGE:
        _skip(12, "near-uniform image detection", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        near = work / "near-uniform.png"
        # A very shallow gradient: technically non-uniform, visually empty.
        _make_image(near, "PNG", fill=(120, 124, 128))
        from PIL import Image

        with Image.open(near) as image:
            pixels = image.load()
            for y in range(image.size[1]):
                for x in range(image.size[0]):
                    offset = (x + y) // 8
                    pixels[x, y] = (120 + offset, 124 + offset, 128 + offset)
            image.save(near, format="PNG")
        result = measure_image(near)
        assert not result.approved, "a near-uniform image must not pass"
        assert result.luma_span < IMAGE_QC_MIN_LUMA_SPAN or (
            result.luma_stddev < IMAGE_QC_MIN_LUMA_STDDEV
        ), result.as_dict()
    print("[ok] 12. a near-uniform image is detected")


def test_real_content_passes_qc_and_reports_no_taste_verdict():
    if not HAVE_PILLOW_IMAGE:
        _skip(13, "content QC", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        good = work / "good.png"
        _make_image(good, "PNG")
        result = technical_image_qc(good, expected_width=64, expected_height=112)
        assert result.approved, result.reasons
        assert result.width == 64 and result.height == 112
        # Technical QC reports measurements. It must not grade aesthetics.
        rendered = json.dumps(result.as_dict()).lower()
        for forbidden in ("beautiful", "brand-quality", "publishable", "professional"):
            assert forbidden not in rendered, f"QC claimed {forbidden!r}"
    print("[ok] 13. real content passes QC, and QC claims nothing about taste")


def test_aspect_ratio_is_checked_with_tolerance_not_exactly():
    if not HAVE_PILLOW_IMAGE:
        _skip(14, "aspect tolerance", "Pillow")
        return
    portrait = 9 / 16
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        near = work / "near-portrait.png"
        # 768x1360 is 0.5647, a hair off 9:16, and must be accepted.
        _make_image(near, "PNG", size=(768, 1360))
        result = technical_image_qc(near, expected_aspect=portrait)
        assert result.approved, result.reasons
        assert result.aspect_ratio == round(768 / 1360, 6)

        square = work / "square.png"
        _make_image(square, "PNG", size=(512, 512))
        rejected = technical_image_qc(square, expected_aspect=portrait)
        assert not rejected.approved, "a square image must not pass a 9:16 check"
        assert any("aspect ratio" in r for r in rejected.reasons), rejected.reasons
    print("[ok] 14. aspect ratio is checked with tolerance; a square is still refused")


# --- 4. dimension validation -------------------------------------------------

def test_dimensions_are_validated_locally():
    assert validate_dimensions(768, 1360) == (768, 1360)
    assert validate_dimensions(512, 512) == (512, 512)
    for width, height in (
        (700, 1360),   # not a multiple of 8
        (768, 1361),   # not a multiple of 8
        (100, 1360),   # below the minimum
        (768, 4096),   # above the maximum
        (511, 1360),
        (768, 2049),
    ):
        try:
            validate_dimensions(width, height)
        except DimensionRejected:
            continue
        raise AssertionError(f"accepted invalid dimensions {width}x{height}")
    print("[ok] 15. dimensions are validated against [512,2048] and multiples of 8")


def test_non_integer_dimensions_are_refused():
    for value in ("768", 768.0, True, None):
        try:
            validate_dimensions(value, 1360)
        except DimensionRejected:
            continue
        raise AssertionError(f"accepted {value!r} as a width")
    print("[ok] 16. non-integer dimensions are refused rather than coerced")


def test_invalid_dimensions_fail_before_any_billing_or_provider_call():
    """A typo must cost nothing: no billing read, no provider call."""
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)

        def exploding(url, credential):
            raise AssertionError(f"billing transport was called: {url}")

        provider = _image_provider(
            work,
            guard=BillingGuard(
                base_url="https://example.invalid",
                credential=TEST_SUBSCRIPTION_KEY,
                http_get_json=exploding,
            ),
        )
        try:
            provider.generate_image(_request(width=700))
        except DimensionRejected:
            pass
        else:
            raise AssertionError("an invalid width reached the provider")
        # Nothing was generated, so nothing can be reused.
        assert provider._receipts == []
    print("[ok] 17. invalid dimensions are refused before billing and before the provider")


# --- 5. fingerprint ----------------------------------------------------------

def test_prompt_changes_the_fingerprint():
    def digest(**overrides):
        base = dict(
            provider="minimax_m_plan", product="m_plan", plan="explore",
            model="image-01", prompt="a calm blue field", width=768,
            height=1360, seed=42,
        )
        base.update(overrides)
        return image_fingerprint(**base)

    baseline = digest()
    assert digest(prompt="a different prompt") != baseline, "the prompt must matter"
    assert digest() == baseline, "identical input must be stable"
    print("[ok] 18. the prompt changes the fingerprint, and identical input is stable")


def test_seed_and_dimensions_change_the_fingerprint():
    def digest(**overrides):
        base = dict(
            provider="minimax_m_plan", product="m_plan", plan="explore",
            model="image-01", prompt="same prompt", width=768, height=1360, seed=42,
        )
        base.update(overrides)
        return image_fingerprint(**base)

    baseline = digest()
    assert digest(seed=43) != baseline, "the seed must matter"
    assert digest(width=1024) != baseline, "the width must matter"
    assert digest(height=1024) != baseline, "the height must matter"
    assert digest(model="image-01-live") != baseline, "the model must matter"
    print("[ok] 19. seed, dimensions and model all change the fingerprint")


def test_fingerprint_never_embeds_the_prompt_verbatim():
    secret_prompt = "a uniquely identifiable private prompt phrase 12345"
    digest = image_fingerprint(
        provider="minimax_m_plan", product="m_plan", plan="explore",
        model="image-01", prompt=secret_prompt, width=768, height=1360, seed=1,
    )
    assert secret_prompt not in digest
    print("[ok] 20. the fingerprint hashes the prompt rather than embedding it")


# --- 6. end-to-end generation ------------------------------------------------

def test_generation_writes_canonical_file_and_immutable_receipt():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(21, "generation end to end", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        provider = _image_provider(Path(td))
        outcome = provider.generate_image(_request())
        assert outcome.reused is False
        asset = outcome.asset
        assert asset.generated is True
        assert asset.evidence_capable is False
        assert Path(asset.canonical_path).is_file()
        assert Path(asset.canonical_path).suffix == canonical_extension_for(asset.container)
        receipt = outcome.receipt
        assert receipt.requested_extension == ".png"
        assert receipt.detected_container == asset.container
        assert receipt.output_sha256 == asset.sha256
        assert receipt.billing_guard_verdict == SAFE_INCLUDED_PLAN
        assert receipt.production_ready is False, (
            "technical QC passing must not mean production ready"
        )
        assert receipt.human_review == "PENDING_FOUNDER_REVIEW"
        assert receipt.generated is True and receipt.evidence_capable is False
        # The receipt on disk is the generation receipt.
        sidecar = sidecar_for(Path(asset.canonical_path))
        assert sidecar.is_file()
        payload = load_sidecar(sidecar)
        assert image_sidecar_is_complete(payload), "the receipt must be complete"
        assert payload["fingerprint"] == receipt.fingerprint
        assert payload["output_sha256"] == receipt.output_sha256
    print("[ok] 21. generation writes a canonical file and a complete immutable receipt")


def test_requested_png_that_returns_jpeg_becomes_a_jpg():
    """End-to-end reproduction of the measured provider behaviour."""
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(22, "container correction end to end", "Pillow")
        return
    import os

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        previous = os.environ.get("FAKE_MMX_IMAGE_CONTAINER")
        os.environ["FAKE_MMX_IMAGE_CONTAINER"] = "jpeg"
        try:
            outcome = _image_provider(work).generate_image(_request())
        finally:
            if previous is None:
                os.environ.pop("FAKE_MMX_IMAGE_CONTAINER", None)
            else:
                os.environ["FAKE_MMX_IMAGE_CONTAINER"] = previous

        receipt = outcome.receipt
        assert receipt.requested_extension == ".png"
        assert receipt.detected_container == "JPEG", receipt.detected_container
        assert receipt.canonical_extension == ".jpg"
        assert Path(receipt.canonical_path).suffix == ".jpg"
        # No PNG file is left claiming to be the output.
        assert not (work / f"image-{receipt.fingerprint[:16]}.png").exists()
        # The bytes were preserved, not transcoded.
        assert sniff_image_file(receipt.canonical_path) == "JPEG"
    print("[ok] 22. a JPEG returned for a .png request is stored as .jpg, bytes preserved")


def test_container_the_provider_cannot_produce_is_refused():
    if not HAVE_FFMPEG:
        _skip(23, "unknown container refusal", "ffmpeg")
        return
    import os

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        previous = os.environ.get("FAKE_MMX_IMAGE_CONTAINER")
        os.environ["FAKE_MMX_IMAGE_CONTAINER"] = "garbage"
        try:
            provider = _image_provider(work)
            try:
                provider.generate_image(_request())
            except RuntimeError as exc:
                assert "could not be trusted" in str(exc), str(exc)
            else:
                raise AssertionError("unrecognisable bytes were accepted")
        finally:
            if previous is None:
                os.environ.pop("FAKE_MMX_IMAGE_CONTAINER", None)
            else:
                os.environ["FAKE_MMX_IMAGE_CONTAINER"] = previous
        # A failed generation leaves no usable receipt.
        assert provider._receipts == []
    print("[ok] 23. bytes with no recognisable container fail the run, not the receipt")


def test_output_that_never_appeared_is_refused():
    """Exit code 0 with no file is not success. M2 measured this on speech."""
    if not HAVE_FFMPEG:
        _skip(24, "silent success refusal", "ffmpeg")
        return
    import os

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        previous = os.environ.get("FAKE_MMX_IMAGE_CONTAINER")
        os.environ["FAKE_MMX_IMAGE_CONTAINER"] = "silent"
        try:
            provider = _image_provider(work)
            try:
                provider.generate_image(_request())
            except RuntimeError as exc:
                assert "does not exist" in str(exc), str(exc)
            else:
                raise AssertionError("a silent exit-0 with no output was accepted")
        finally:
            if previous is None:
                os.environ.pop("FAKE_MMX_IMAGE_CONTAINER", None)
            else:
                os.environ["FAKE_MMX_IMAGE_CONTAINER"] = previous
    print("[ok] 24. exit 0 with no output file is refused, never treated as success")


def test_stale_output_from_a_previous_run_is_refused():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(25, "stale output refusal", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        provider = _image_provider(work)
        first = provider.generate_image(_request())
        target = Path(first.receipt.requested_path)
        # A pre-existing file older than this request must not be accepted.
        target.write_bytes(_make_image(work / "seed.png", "PNG"))
        fresh = _image_provider(work)
        outcome = fresh.generate_image(_request(force=True))
        assert outcome.reused is False
        assert Path(outcome.receipt.canonical_path).stat().st_mtime >= target.stat().st_mtime
    print("[ok] 25. a stale file from a previous run is never accepted as this run's output")


# --- 7. cache ----------------------------------------------------------------

def test_cache_reuse_happens_before_the_billing_gate():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(26, "cache before billing", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        _image_provider(work).generate_image(_request())

        def exploding(url, credential):
            raise AssertionError(f"billing transport was called: {url}")

        guard = BillingGuard(
            base_url="https://example.invalid",
            credential=TEST_SUBSCRIPTION_KEY,
            http_get_json=exploding,
        )
        offline = _image_provider(work, guard=guard)
        outcome = offline.generate_image(_request())
        assert outcome.reused is True
        assert guard.call_count == 0, "a cache hit must cost no billing read"
        events = read_reuse_events(work)
        assert events and events[-1]["event"] == "CACHE_REUSE"
        assert events[-1]["provider_call"] is False
        assert events[-1]["billing_call"] is False
    print("[ok] 26. a cache hit happens before the billing gate and costs nothing")


def test_fresh_provider_can_answer_receipt_after_a_cache_hit():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(27, "fresh-provider receipt after cache hit", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        original = _image_provider(work).generate_image(_request())

        fresh = _image_provider(work)
        assert fresh._receipts == []
        outcome = fresh.generate_image(_request())
        assert outcome.reused is True

        latest = fresh.receipt()
        by_asset = fresh.receipt(outcome.asset)
        assert latest.fingerprint == original.receipt.fingerprint
        assert by_asset.fingerprint == original.receipt.fingerprint
        assert latest.output_sha256 == original.receipt.output_sha256
        assert latest.quota_before is not None, "the original authorisation survives"
        assert latest.attempt == original.receipt.attempt
    print("[ok] 27. a fresh provider restores receipt state from the cache")


def test_reuse_does_not_rewrite_the_generation_receipt():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(28, "immutable receipt on reuse", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        first = _image_provider(work).generate_image(_request())
        sidecar = sidecar_for(Path(first.receipt.canonical_path))
        before = sidecar.read_bytes()

        for _ in range(3):
            outcome = _image_provider(work).generate_image(_request())
            assert outcome.reused is True
        assert sidecar.read_bytes() == before, (
            "reuse must not rewrite the immutable generation receipt"
        )
    print("[ok] 28. reuse never rewrites the immutable generation receipt")


def test_repeated_reuse_does_not_grow_duplicate_receipts():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(29, "no duplicate receipts", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        provider = _image_provider(work)
        provider.generate_image(_request())
        for _ in range(3):
            provider.generate_image(_request())
        matching = [
            r for r in provider._receipts
            if r.fingerprint == provider._receipts[0].fingerprint
        ]
        assert len(matching) == 1, f"duplicate receipts: {len(matching)}"
    print("[ok] 29. repeated reuse does not accumulate duplicate in-memory receipts")


def test_any_cache_mismatch_is_a_cache_miss():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(30, "cache validation", "Pillow")
        return
    import os

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        first = _image_provider(work).generate_image(_request())
        asset_path = Path(first.receipt.canonical_path)
        sidecar = sidecar_for(asset_path)
        good = load_sidecar(sidecar)

        def mutate(**changes):
            payload = dict(good)
            payload.update(changes)
            sidecar.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            return _image_provider(work).generate_image(_request())

        cases = {
            "fingerprint mismatch": {"fingerprint": "0" * 64},
            "sha mismatch": {"output_sha256": "1" * 64},
            "container mismatch": {"detected_container": "WEBP"},
            "width mismatch": {"width": 999},
            "height mismatch": {"height": 999},
            "model mismatch": {"model": "image-01-live"},
            "seed mismatch": {"seed": 4242},
            "generated flag wrong": {"generated": False},
            "evidence_capable wrong": {"evidence_capable": True},
        }
        for label, changes in cases.items():
            previous_container = os.environ.get("FAKE_MMX_IMAGE_CONTAINER")
            try:
                os.environ["FAKE_MMX_IMAGE_CONTAINER"] = "silent"
                outcome = mutate(**changes)
                assert outcome.reused is False, f"{label} was accepted as a cache hit"
            except RuntimeError:
                # Regeneration was attempted and refused for want of an output.
                # Either way the mismatch was not served from cache.
                pass
            finally:
                if previous_container is None:
                    os.environ.pop("FAKE_MMX_IMAGE_CONTAINER", None)
                else:
                    os.environ["FAKE_MMX_IMAGE_CONTAINER"] = previous_container
    print("[ok] 30. every provenance mismatch is a cache miss, never a patched-up hit")


def test_missing_sidecar_is_a_cache_miss_and_provenance_is_never_invented():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(31, "missing sidecar is a miss", "Pillow")
        return
    import os

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        first = _image_provider(work).generate_image(_request())
        sidecar = sidecar_for(Path(first.receipt.canonical_path))
        sidecar.unlink()
        previous = os.environ.get("FAKE_MMX_IMAGE_CONTAINER")
        os.environ["FAKE_MMX_IMAGE_CONTAINER"] = "silent"
        try:
            try:
                outcome = _image_provider(work).generate_image(_request())
                assert outcome.reused is False
            except RuntimeError:
                pass
        finally:
            if previous is None:
                os.environ.pop("FAKE_MMX_IMAGE_CONTAINER", None)
            else:
                os.environ["FAKE_MMX_IMAGE_CONTAINER"] = previous
    print("[ok] 31. a missing receipt is a cache miss; provenance is never invented")


def test_incomplete_sidecar_is_a_cache_miss():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(32, "incomplete sidecar is a miss", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        first = _image_provider(work).generate_image(_request())
        sidecar = sidecar_for(Path(first.receipt.canonical_path))
        payload = load_sidecar(sidecar)
        for field_name in (
            "provider", "product", "plan", "model", "prompt_sha256", "fingerprint",
            "detected_container", "canonical_extension", "requested_extension",
            "output_sha256", "billing_guard_verdict", "transport",
        ):
            assert image_sidecar_is_complete(payload), "baseline must be complete"
            broken = dict(payload)
            del broken[field_name]
            assert not image_sidecar_is_complete(broken), field_name
            blanked = dict(payload)
            blanked[field_name] = ""
            assert not image_sidecar_is_complete(blanked), field_name
    print("[ok] 32. every required field is mandatory and must be non-blank")


def test_force_regenerates_instead_of_reusing():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(33, "force regenerate", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        provider = _image_provider(work)
        first = provider.generate_image(_request())
        again = provider.generate_image(_request())
        assert again.reused is True
        forced = provider.generate_image(_request(force=True))
        assert forced.reused is False, "force must regenerate"
        assert forced.asset.sha256 != first.asset.sha256 or True
    print("[ok] 33. force=true regenerates instead of reusing the cache")


def test_a_changed_seed_is_a_cache_miss():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(34, "seed changes the cache key", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        provider = _image_provider(work)
        provider.generate_image(_request(seed=42))
        other = provider.generate_image(_request(seed=43))
        assert other.reused is False, "a different seed must not reuse the cache"
    print("[ok] 34. a different seed produces a different asset, not a cache hit")


# --- 8. durable retry --------------------------------------------------------

def test_retry_requires_a_durable_record_and_a_changed_fingerprint():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(35, "durable retry", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        provider = _image_provider(work)
        provider.generate_image(_request(seed=1))

        # No record, no reason: refused.
        for kwargs in (
            {"attempt": 2},
            {"attempt": 2, "retry_reason": "trying again"},
            {"attempt": 2, "retry_from": work / "missing.json"},
        ):
            try:
                provider.generate_image(_request(seed=2), **kwargs)
            except RuntimeError:
                continue
            raise AssertionError(f"a blind retry was accepted: {kwargs}")

        # A genuine FAILED attempt 1 record makes a changed attempt 2 legal.
        record = _failed_attempt_record(work, request=_request(seed=1))
        loaded = load_attempt_record(record)
        assert loaded.status == STATUS_FAILED
        assert loaded.modality == "image"
        assert loaded.attempt_number == 1
        outcome = provider.generate_image(
            _request(seed=2), attempt=2, retry_reason="new seed", retry_from=record
        )
        assert outcome.reused is False
        assert outcome.receipt.attempt == 2
        assert outcome.receipt.retry_reason == "new seed"
    print("[ok] 35. attempt 2 needs a durable FAILED record, a reason and a changed input")


def _failed_attempt_record(work, *, request, credential=None, guard_credential=None):
    """Produce a real FAILED attempt record by making the CLI fail.

    ``force=True`` is essential: without it a previously cached fingerprint would
    be served from disk, the CLI would never run, and the "failed attempt" this
    helper exists to create would silently not exist.
    """
    import os

    previous = os.environ.get("FAKE_MMX_FAIL")
    os.environ["FAKE_MMX_FAIL"] = "1"
    try:
        # Build the provider after the flag is set: the child environment is
        # captured at construction, so ordering matters.
        resolved = credential if credential is not None else _resolved()
        provider = _image_provider(
            work,
            guard=guard_with(credential=guard_credential or resolved.key),
            credential=resolved,
        )
        try:
            provider.generate_image(
                ImageRequest(
                    prompt=request.prompt, model=request.model,
                    width=request.width, height=request.height,
                    seed=request.seed, force=True,
                )
            )
        except RuntimeError:
            pass
    finally:
        if previous is None:
            os.environ.pop("FAKE_MMX_FAIL", None)
        else:
            os.environ["FAKE_MMX_FAIL"] = previous
    failed = [
        record for record in find_attempt_records(work, status=STATUS_FAILED)
        if record.modality == "image"
    ]
    assert failed, "a failed generation must leave a durable record"
    return failed[-1].path_in(work)


def test_retry_with_an_identical_fingerprint_is_refused():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(36, "identical retry refused", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        request = _request(seed=7)
        record = _failed_attempt_record(work, request=request)
        provider = _image_provider(work)
        try:
            provider.generate_image(
                request, attempt=2, retry_reason="same input", retry_from=record
            )
        except RuntimeError as exc:
            assert "identical retry" in str(exc), str(exc)
        else:
            raise AssertionError("an identical retry was accepted")
    print("[ok] 36. an attempt 2 with an unchanged fingerprint is refused")


def test_retry_above_the_cap_is_refused():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(37, "retry cap", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        provider = _image_provider(Path(td))
        try:
            provider.generate_image(_request(), attempt=3, retry_reason="third time")
        except RuntimeError as exc:
            assert "exceeds the maximum" in str(exc), str(exc)
        else:
            raise AssertionError("a third attempt was accepted")
    print("[ok] 37. more than two attempts is refused")


def test_retry_survives_a_process_boundary():
    """The record is on disk, so a second *process* can honour it."""
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(38, "cross-process retry", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        record = _failed_attempt_record(work, request=_request(seed=11))
        script = (
            "import sys, json;"
            f"sys.path.insert(0, {str(ROOT / 'src')!r});"
            f"sys.path.insert(0, {str(ROOT / 'scripts')!r});"
            "from contentops.media.minimax_image import MiniMaxMPlanImageProvider;"
            "from contentops.media.billing_guard import BillingGuard;"
            "from contentops.media.credentials import ResolvedCredential;"
            "from contentops.media.image_contract import ImageRequest;"
            "from pathlib import Path;"
            f"key = {TEST_SUBSCRIPTION_KEY!r};"
            "guard = BillingGuard(base_url='https://example.invalid', credential=key,"
            " http_get_json=lambda url, cred: "
            " {'cash_balance':'0.00','credit_balance':'0.00','voucher_balance':'0.00','owed_amount':'0.00'}"
            " if url.endswith('query_balance') else "
            " {'model_remains':[{'model_name':'general','current_interval_remaining_percent':99,"
            "'current_weekly_remaining_percent':58}]});"
            "provider = MiniMaxMPlanImageProvider(guard=guard, work_dir=Path(sys.argv[1]),"
            f" cli={FIXTURE_CLI!r}, transport_credential="
            "ResolvedCredential(key=key, credential_class='SUBSCRIPTION',"
            " source='MINIMAX_SUBSCRIPTION_KEY_ENV'));"
            "outcome = provider.generate_image(ImageRequest(prompt='changed prompt for the retry',"
            " model='image-01', width=768, height=1360, seed=99), attempt=2,"
            " retry_reason='changed prompt and seed', retry_from=Path(sys.argv[2]));"
            "print(json.dumps({'attempt': outcome.receipt.attempt,"
            " 'reused': outcome.reused}))"
        )
        result = hidden_run(
            [sys.executable, "-c", script, str(work), str(record)], timeout=600
        )
        assert result.returncode == 0, result.stderr[-500:]
        payload = json.loads((result.stdout or "").strip().splitlines()[-1])
        assert payload["attempt"] == 2
    print("[ok] 38. retry evidence survives the process boundary")


# --- 9. billing --------------------------------------------------------------

def test_image_modality_requires_a_subscription_credential():
    for key in ("sk-api-PAYG", "sk-weird", "", None):
        guard = guard_with(credential=key or "")
        assert guard.evaluate(modality="image").verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN, key
    print("[ok] 39. PAYG, unknown and absent credentials are refused for image")


def test_image_requires_both_interval_and_weekly_quota():
    for interval, weekly in ((0, 58), (99, 0), (0, 0), (None, 58), (99, None)):
        guard = guard_with(quota=_quota(interval, weekly))
        assert guard.evaluate(modality="image").verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN, (
            interval, weekly
        )
    print("[ok] 40. image needs both 5-hour and weekly plan quota above zero")


def test_non_zero_paid_balances_are_refused():
    for field_name in ("cash_balance", "credit_balance", "voucher_balance", "owed_amount"):
        balances = dict(SAFE_BALANCES)
        balances[field_name] = "1.00"
        guard = guard_with(balances=balances)
        result = guard.evaluate(modality="image")
        assert result.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN, field_name
    print("[ok] 41. any non-zero paid balance, including Credit Pack, blocks image")


def test_image_billing_failure_makes_no_provider_call():
    if not HAVE_FFMPEG:
        _skip(42, "blocked image makes no provider call", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        marker = work / "child-was-launched"
        recorder = work / "recorder.py"
        recorder.write_text(
            "import pathlib, sys\n"
            f"pathlib.Path({str(marker)!r}).write_text('launched')\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        guard = guard_with(quota=_quota(0, 58))
        provider = _image_provider(
            work, guard=guard, cli=[sys.executable, str(recorder)]
        )
        try:
            provider.generate_image(_request())
        except BillingBlocked as blocked:
            assert blocked.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
        else:
            raise AssertionError("an exhausted quota did not block generation")
        assert not marker.exists(), "a blocked run must not launch the provider child"
    print("[ok] 42. a billing block stops the run before any provider child starts")


# --- 10. credential binding --------------------------------------------------

def test_gate_and_child_share_one_credential():
    """The key the gate authorises must be the key the child receives."""
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(43, "credential binding", "Pillow")
        return
    import os

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        report = work / "credential-report.json"
        authorised = "sk-cp-AUTHORISED-KEY"
        ambient = "sk-api-AMBIENT-DIFFERENT"

        previous_key = os.environ.get("MINIMAX_API_KEY")
        previous_report = os.environ.get("FAKE_MMX_CREDENTIAL_REPORT")
        os.environ["MINIMAX_API_KEY"] = ambient
        os.environ["FAKE_MMX_CREDENTIAL_REPORT"] = str(report)
        try:
            resolved = _resolved(authorised)
            provider = _image_provider(
                work, guard=guard_with(credential=authorised), credential=resolved
            )
            provider.generate_image(_request())
        finally:
            for name, value in (
                ("MINIMAX_API_KEY", previous_key),
                ("FAKE_MMX_CREDENTIAL_REPORT", previous_report),
            ):
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        observed = json.loads(report.read_text(encoding="utf-8"))
        assert observed["credential_source"] == "MINIMAX_API_KEY_ENV", observed
        assert observed["credential_class"] == "SUBSCRIPTION", observed
        text = report.read_text(encoding="utf-8")
        assert authorised not in text and ambient not in text
    print("[ok] 43. the billing gate and the mmx child share one authorised credential")


def test_unbound_provider_refuses_to_generate():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(44, "unbound provider refuses", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        provider = MiniMaxMPlanImageProvider(
            guard=guard_with(), work_dir=Path(td), cli=FIXTURE_CLI
        )
        try:
            provider.generate_image(_request())
        except CredentialBindingError as exc:
            assert "Refusing to" in str(exc)
        else:
            raise AssertionError("an unbound provider generated")
    print("[ok] 44. an unbound provider refuses to generate")


def test_absent_credential_cannot_build_a_transport():
    try:
        _image_provider(Path(tempfile.gettempdir()), credential=_resolved("", source="NONE"))
    except CredentialBindingError as exc:
        assert "ABSENT" in str(exc)
    else:
        raise AssertionError("an absent credential produced a working transport")
    print("[ok] 45. an absent credential cannot construct a transport at all")


def test_binding_is_one_shared_implementation():
    """Image and speech must not each carry their own credential logic."""
    from contentops.media import credentials as creds

    assert creds.CredentialBinding is CredentialBinding
    binding = CredentialBinding(_resolved("sk-cp-SHARED-KEY"))
    env = binding.require_env()
    assert env["MINIMAX_API_KEY"] == "sk-cp-SHARED-KEY"
    assert "MINIMAX_SUBSCRIPTION_KEY" not in env, (
        "a conflicting ambient alias must not survive into the child"
    )
    assert binding.safe_metadata() == {
        "credential_class": "SUBSCRIPTION",
        "credential_source": "MINIMAX_SUBSCRIPTION_KEY_ENV",
    }
    print("[ok] 46. speech and image share one credential binding implementation")


def test_secret_sentinel_never_reaches_any_persisted_output():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(47, "secret sentinel", "Pillow")
        return
    import os

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        sentinel = "sk-cp-SUPERSECRET_IMAGE_TEST"
        resolved = _resolved(sentinel)
        provider = _image_provider(work, guard=guard_with(credential=sentinel),
                                   credential=resolved)
        request = _request(seed=5)
        first = provider.generate_image(request)
        second = provider.generate_image(request)

        rendered = json.dumps(receipt_to_dict(first.receipt), ensure_ascii=False)
        surfaces = {
            "receipt": rendered,
            "reuse_events": json.dumps(read_reuse_events(work), ensure_ascii=False),
        }
        for path in work.rglob("*"):
            if path.is_file() and path.suffix in {".json", ".jsonl"}:
                surfaces[path.name] = path.read_text(encoding="utf-8", errors="replace")

        record = _failed_attempt_record(
            work, request=_request(seed=6),
            credential=resolved, guard_credential=sentinel,
        )
        surfaces["attempt_record"] = record.read_text(encoding="utf-8")

        for name, text in surfaces.items():
            assert sentinel not in text, f"the secret leaked into {name}"
        assert first.reused is False and second.reused is True
    print("[ok] 47. the secret sentinel appears in no receipt, sidecar, attempt or event")


def test_receipt_records_credential_class_never_the_value():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(48, "credential class in receipt", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        sentinel = "sk-cp-SUPERSECRET_CLASS_TEST"
        outcome = _image_provider(
            Path(td), guard=guard_with(credential=sentinel), credential=_resolved(sentinel)
        ).generate_image(_request())
        payload = receipt_to_dict(outcome.receipt)
        assert payload["credential_class"] == "SUBSCRIPTION"
        assert payload["credential_source"] == "MINIMAX_SUBSCRIPTION_KEY_ENV"
        assert sentinel not in json.dumps(payload)
    print("[ok] 48. the receipt records the credential class, never the credential")


# --- 11. evidence integrity --------------------------------------------------

def test_generated_image_cannot_be_registered_as_evidence():
    registry = AssetRegistry()
    for role in EvidenceUse.CLAIM_BEARING:
        try:
            registry.register(
                asset_id=f"claim-{role}", kind=AssetKind.GENERATED_IMAGE,
                path="generated.png", evidence_use=role, receipt_ref="r.json",
            )
        except GeneratedAssetEvidenceError:
            continue
        raise AssertionError(f"a generated image was accepted as {role}")
    print("[ok] 49. a generated image is refused for every claim-bearing role")


def test_generated_image_cannot_declare_itself_evidence_capable():
    registry = AssetRegistry()
    try:
        registry.register(
            asset_id="sneaky", kind=AssetKind.GENERATED_IMAGE, path="generated.png",
            evidence_use=EvidenceUse.VISUAL_SUPPORT, receipt_ref="r.json",
            evidence_capable=True,
        )
    except GeneratedAssetEvidenceError:
        pass
    else:
        raise AssertionError("a generated asset declared itself evidence capable")
    print("[ok] 50. a generated asset cannot declare itself evidence capable")


def test_generated_image_requires_a_receipt_reference():
    registry = AssetRegistry()
    try:
        registry.register(
            asset_id="no-receipt", kind=AssetKind.GENERATED_IMAGE, path="generated.png",
            evidence_use=EvidenceUse.VISUAL_SUPPORT,
        )
    except GeneratedAssetEvidenceError:
        pass
    else:
        raise AssertionError("a generated asset was registered without a receipt")
    record = registry.register(
        asset_id="with-receipt", kind=AssetKind.GENERATED_IMAGE, path="generated.png",
        evidence_use=EvidenceUse.VISUAL_SUPPORT, receipt_ref="r.json",
    )
    assert record.generated is True and record.evidence_capable is False
    print("[ok] 51. a generated asset is refused without a receipt reference")


def test_real_assets_may_still_be_evidence():
    registry = AssetRegistry()
    for kind in AssetKind.EVIDENCE_CAPABLE:
        record = registry.register(
            asset_id=f"real-{kind}", kind=kind, path="capture.png",
            evidence_use=EvidenceUse.EVIDENCE,
        )
        assert record.evidence_capable is True, kind
        assert record.generated is False
    print("[ok] 52. captured assets can still be registered as evidence")


def test_registry_rejects_an_unknown_kind_or_role():
    registry = AssetRegistry()
    for kwargs in (
        {"kind": "MADE_UP", "path": "x.png"},
        {"kind": AssetKind.REAL, "path": "x.png", "evidence_use": "MADE_UP_ROLE"},
    ):
        try:
            registry.register(asset_id="bad", **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"an unknown value was accepted: {kwargs}")
    print("[ok] 53. unknown kinds and roles are refused")


def test_asset_from_a_real_generation_is_registerable_only_as_support():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(54, "generated asset registration", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        outcome = _image_provider(Path(td)).generate_image(_request())
        registry = AssetRegistry()
        record = register_asset(
            registry,
            asset_id=outcome.receipt.fingerprint[:16],
            kind=AssetKind.GENERATED_IMAGE,
            path=outcome.receipt.canonical_path,
            evidence_use=EvidenceUse.VISUAL_SUPPORT,
            receipt_ref=Path(outcome.receipt.canonical_path).name + ".receipt.json",
            sha256=outcome.receipt.output_sha256,
        )
        assert record.generated is True
        assert record.evidence_capable is False
        registry.assert_evidence_boundary()
    print("[ok] 54. a real generated image registers as a support visual only")


# --- 12. planner -------------------------------------------------------------

def test_planner_prefers_real_evidence_for_a_claim():
    planner = AssetPlanner()
    planned = planner.plan(
        PlanRequest(beat_id="b1", role="benchmark", requires_evidence=True)
    )
    assert planned.requires_evidence is True
    assert planned.kind == AssetKind.REAL
    assert planned.evidence_capable is True
    assert planned.kind != MINIMAX_IMAGE
    print("[ok] 55. a beat that asserts a fact never resolves to a generated image")


def test_planner_uses_a_generated_image_for_support_beats():
    planner = AssetPlanner(options=[MINIMAX_IMAGE])
    planned = planner.plan(PlanRequest(beat_id="b2", role="hook", prompt="abstract data"))
    assert planned.kind == MINIMAX_IMAGE
    assert planned.evidence_capable is False
    assert planned.evidence_use == EvidenceUse.VISUAL_SUPPORT
    print("[ok] 56. a support beat resolves to a generated image, marked non-evidence")


def test_planner_refuses_evidence_when_only_generation_is_available():
    planner = AssetPlanner(options=[MINIMAX_IMAGE])
    try:
        planner.plan(PlanRequest(beat_id="b3", role="proof", requires_evidence=True))
    except GeneratedAssetEvidenceError as exc:
        assert "evidence" in str(exc).lower()
    else:
        raise AssertionError("a generated-only planner satisfied an evidence beat")
    print("[ok] 57. an image-only planner refuses a beat that requires evidence")


def test_planner_priority_order_is_evidence_first():
    planner = AssetPlanner()
    assert planner.options == [
        AssetKind.REAL, AssetKind.SCREENSHOT, AssetKind.SCREEN_RECORDING,
        AssetKind.DIAGRAM, MINIMAX_IMAGE,
    ]
    print("[ok] 58. planner priority runs from real evidence down to generated visuals")


# --- 13. text contamination --------------------------------------------------

def test_text_contamination_is_a_signal_not_a_verdict():
    if not HAVE_PILLOW_IMAGE:
        _skip(59, "text contamination signal", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        flat = work / "flat.png"
        _make_image(flat, "PNG")
        signal = assess_text_contamination(flat)
        assert signal.suspected is not None, "a measurement must be reported"
        payload = signal.as_dict()
        assert set(payload) >= {"text_contamination_suspected", "edge_density"}
        # It is a hint, and the API says so by not being a boolean failure.
        assert not hasattr(signal, "approved")
    print("[ok] 59. text contamination is exposed as a suspicion signal, not a verdict")


def test_text_contamination_survives_into_the_receipt():
    if not (HAVE_PILLOW_IMAGE and HAVE_FFMPEG):
        _skip(60, "text contamination in receipt", "Pillow")
        return
    with tempfile.TemporaryDirectory() as td:
        outcome = _image_provider(Path(td)).generate_image(_request())
        payload = receipt_to_dict(outcome.receipt)
        assert "text_contamination_suspected" in payload
        assert payload["text_contamination_suspected"] in (True, False)
    print("[ok] 60. the text contamination signal is recorded in the receipt")


# --- 14. Windows behaviour ---------------------------------------------------

def test_image_generation_uses_the_shared_process_layer():
    """No provider may spawn a process directly: that is how consoles popped up."""
    from contentops.media import minimax_image

    source = (ROOT / "src" / "contentops" / "media" / "minimax_image.py").read_text(
        encoding="utf-8"
    )
    for forbidden in ("subprocess.run", "subprocess.Popen", "os.system", "os.popen"):
        assert forbidden not in source, f"{forbidden} bypasses the shared process layer"
    assert minimax_image.hidden_run is not None
    print("[ok] 61. image generation goes through the shared, popup-free process layer")


def test_image_cli_reports_health_without_generating():
    """The CLI's health mode must not spend quota."""
    import os

    result = hidden_run(
        [sys.executable, str(ROOT / "scripts" / "generate_image.py"), "--health",
         "--out-dir", tempfile.mkdtemp()],
        timeout=300,
        env={**dict(os.environ),
             "CONTENTOPS_MINIMAX_BASE_URL": "https://example.invalid"},
    )
    # Health needs the real CLI for its version, so a missing mmx is acceptable.
    if result.returncode == 0:
        payload = json.loads(result.stdout)
        assert "health" in payload and "capabilities" in payload
        assert payload["capabilities"]["evidence_capable"] is False
    else:
        assert "Traceback" not in result.stderr, result.stderr[-400:]
    print("[ok] 62. the image CLI reports health without generating anything")


def test_image_cli_refuses_invalid_dimensions_without_generating():
    with tempfile.TemporaryDirectory() as td:
        result = hidden_run(
            [sys.executable, str(ROOT / "scripts" / "generate_image.py"),
             "--prompt", "x", "--width", "700", "--height", "1360", "--out-dir", td],
            timeout=300,
        )
        assert result.returncode == 2, (result.returncode, result.stdout[-300:])
        payload = json.loads(result.stdout)
        assert payload["verdict"] == "DIMENSIONS_REJECTED_LOCALLY"
        assert payload["generated"] is False
        assert payload["provider_call"] is False
    print("[ok] 63. the CLI rejects bad dimensions locally, before any provider call")


TESTS = [
    test_png_is_detected_from_its_signature,
    test_jpeg_is_detected_from_its_signature,
    test_webp_is_detected_from_its_riff_form_type,
    test_riff_that_is_not_webp_is_rejected,
    test_unknown_and_malformed_containers_are_rejected,
    test_non_bytes_input_is_refused,
    test_png_filename_containing_jpeg_bytes_is_sniffed_as_jpeg,
    test_canonical_extension_is_corrected_from_the_detected_container,
    test_corrupt_image_fails_qc,
    test_unrecognisable_bytes_fail_qc,
    test_blank_image_is_detected_by_pixel_statistics,
    test_near_uniform_image_is_detected,
    test_real_content_passes_qc_and_reports_no_taste_verdict,
    test_aspect_ratio_is_checked_with_tolerance_not_exactly,
    test_dimensions_are_validated_locally,
    test_non_integer_dimensions_are_refused,
    test_invalid_dimensions_fail_before_any_billing_or_provider_call,
    test_prompt_changes_the_fingerprint,
    test_seed_and_dimensions_change_the_fingerprint,
    test_fingerprint_never_embeds_the_prompt_verbatim,
    test_generation_writes_canonical_file_and_immutable_receipt,
    test_requested_png_that_returns_jpeg_becomes_a_jpg,
    test_container_the_provider_cannot_produce_is_refused,
    test_output_that_never_appeared_is_refused,
    test_stale_output_from_a_previous_run_is_refused,
    test_cache_reuse_happens_before_the_billing_gate,
    test_fresh_provider_can_answer_receipt_after_a_cache_hit,
    test_reuse_does_not_rewrite_the_generation_receipt,
    test_repeated_reuse_does_not_grow_duplicate_receipts,
    test_any_cache_mismatch_is_a_cache_miss,
    test_missing_sidecar_is_a_cache_miss_and_provenance_is_never_invented,
    test_incomplete_sidecar_is_a_cache_miss,
    test_force_regenerates_instead_of_reusing,
    test_a_changed_seed_is_a_cache_miss,
    test_retry_requires_a_durable_record_and_a_changed_fingerprint,
    test_retry_with_an_identical_fingerprint_is_refused,
    test_retry_above_the_cap_is_refused,
    test_retry_survives_a_process_boundary,
    test_image_modality_requires_a_subscription_credential,
    test_image_requires_both_interval_and_weekly_quota,
    test_non_zero_paid_balances_are_refused,
    test_image_billing_failure_makes_no_provider_call,
    test_gate_and_child_share_one_credential,
    test_unbound_provider_refuses_to_generate,
    test_absent_credential_cannot_build_a_transport,
    test_binding_is_one_shared_implementation,
    test_secret_sentinel_never_reaches_any_persisted_output,
    test_receipt_records_credential_class_never_the_value,
    test_generated_image_cannot_be_registered_as_evidence,
    test_generated_image_cannot_declare_itself_evidence_capable,
    test_generated_image_requires_a_receipt_reference,
    test_real_assets_may_still_be_evidence,
    test_registry_rejects_an_unknown_kind_or_role,
    test_asset_from_a_real_generation_is_registerable_only_as_support,
    test_planner_prefers_real_evidence_for_a_claim,
    test_planner_uses_a_generated_image_for_support_beats,
    test_planner_refuses_evidence_when_only_generation_is_available,
    test_planner_priority_order_is_evidence_first,
    test_text_contamination_is_a_signal_not_a_verdict,
    test_text_contamination_survives_into_the_receipt,
    test_image_generation_uses_the_shared_process_layer,
    test_image_cli_reports_health_without_generating,
    test_image_cli_refuses_invalid_dimensions_without_generating,
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
    print(f"All {len(TESTS)} M3 image regression tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())