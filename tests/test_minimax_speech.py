"""M2 speech regression tests: billing guard, lexicon, audio, fingerprint, policy.

No real provider request happens here. Every network path is injected, and the
one test that touches media uses ffmpeg on a locally synthesised tone rather
than a provider asset.

Run: python tests/test_minimax_speech.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from process_utils import hidden_run, python_executable  # noqa: E402

from contentops.media.asr_backcheck import token_overlap  # noqa: E402
from contentops.media.audio import (  # noqa: E402
    NORMALISATION_TARGET_LUFS,
    NORMALISATION_TRUE_PEAK_DB,
    measure_audio,
    normalise_speech,
    technical_qc,
)
from contentops.media.asr_backcheck import _multiplicity  # noqa: E402
from contentops.media.attempts import read_reuse_events  # noqa: E402
from contentops.media.billing_guard import (  # noqa: E402
    ZERO_REQUIRED_BALANCE_FIELDS,
    BALANCE_DEPENDENCY_CLASS,
    BLOCKED_BILLING_SOURCE_UNCERTAIN,
    SAFE_INCLUDED_PLAN,
    BillingGuard,
    classify_credential,
)
from contentops.media.contract import BillingBlocked  # noqa: E402
from contentops.media.fingerprint import speech_fingerprint  # noqa: E402
from contentops.media.lexicon import (  # noqa: E402
    LEXICON_VERSION,
    REGRESSION_VOCABULARY,
    coverage_report,
    default_en_lexicon,
    default_zh_lexicon,
)
from contentops.media.minimax_speech import (  # noqa: E402
    EASEL_COMPATIBILITY,
    MAX_ATTEMPTS,
    flatten_for_cli,
    load_sidecar,
    REQUIRED_SIDECAR_FIELDS,
    sidecar_is_complete,
    receipt_to_dict,
    resolve_cli,
    sidecar_for,
    verify_output,
    write_sidecar,
)
from contentops.media.contract import SpeechRequest  # noqa: E402
from contentops.media.test_duration_policy import (  # noqa: E402
    H3_DURATION_SPEC,
    H3_MAX_DURATION_SPEC,
    PREFERRED_TEST_DURATION_RANGE,
    ProviderDurationSpec,
    decide_test_duration,
)

HAVE_FFMPEG = bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))

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


def guard_with(balances=SAFE_BALANCES, quota=SAFE_QUOTA,
               credential="sk-cp-TESTONLY0000000000"):
    return BillingGuard(
        base_url="https://example.invalid",
        credential=credential,
        http_get_json=fake_transport(balances, quota),
    )


# --- 1. credential policy ---------------------------------------------------

def test_credential_classification():
    assert classify_credential("sk-cp-abc") == "SUBSCRIPTION"
    assert classify_credential("sk-api-abc") == "PAYG"
    assert classify_credential("sk-unknown") == "UNKNOWN"
    assert classify_credential("") == "ABSENT"
    assert classify_credential(None) == "ABSENT"
    print("[ok] 1. credential classes identified, PAYG/UNKNOWN/ABSENT distinguished")


def test_non_subscription_credential_is_refused():
    for credential in ("sk-api-abc", "sk-weird", "", None):
        guard = guard_with(credential=credential)
        result = guard.evaluate()
        assert result.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN, credential
        assert any("credential class" in r for r in result.reasons), result.reasons
    print("[ok] 2. PAYG, unknown, absent and empty credentials are all refused")


def test_guard_never_exposes_the_credential():
    secret = "sk-cp-SUPERSECRETVALUE"
    guard = guard_with(credential=secret)
    result = guard.evaluate()
    rendered = json.dumps(result.__dict__, default=str)
    assert secret not in rendered
    assert "SUPERSECRET" not in rendered
    assert result.credential_class == "SUBSCRIPTION"
    print("[ok] 3. guard output carries the credential class and never the value")


# --- 2. billing guard -------------------------------------------------------

def test_guard_allows_only_safe_state():
    result = guard_with().evaluate()
    assert result.verdict == SAFE_INCLUDED_PLAN, result.reasons
    assert result.reasons == []
    print("[ok] 4. zero balances plus remaining plan usage is SAFE_INCLUDED_PLAN")


def test_guard_blocks_each_nonzero_paid_field():
    for field in ("cash_balance", "credit_balance", "voucher_balance"):
        balances = dict(SAFE_BALANCES, **{field: "5.00"})
        result = guard_with(balances=balances).evaluate()
        assert result.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN, field
        assert any(field in r for r in result.reasons), (field, result.reasons)
    owed = dict(SAFE_BALANCES, owed_amount="1.00")
    result = guard_with(balances=owed).evaluate()
    assert result.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    print("[ok] 5. any non-zero paid balance or outstanding amount blocks")


def test_guard_fails_closed_on_unreadable_balance():
    result = guard_with(balances=TimeoutError("no route")).evaluate()
    assert result.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    assert any("balance read failed" in r for r in result.reasons), result.reasons
    print("[ok] 6. unreadable balance blocks and is never treated as zero")


def test_guard_fails_closed_on_schema_change():
    # A missing field is the realistic schema-change signal.
    partial = {k: v for k, v in SAFE_BALANCES.items() if k != "credit_balance"}
    result = guard_with(balances=partial).evaluate()
    assert result.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    assert any("credit_balance" in r and "missing" in r for r in result.reasons), (
        result.reasons
    )
    print("[ok] 7. a missing balance field blocks as a possible schema change")


def test_guard_blocks_on_exhausted_or_unreadable_plan_quota():
    exhausted = {
        "model_remains": [
            {
                "model_name": "general",
                "current_interval_remaining_percent": 0,
                "current_weekly_remaining_percent": 0,
            }
        ]
    }
    result = guard_with(quota=exhausted).evaluate()
    assert result.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    assert any("weekly_remaining_percent" in r and "exhausted" in r
               for r in result.reasons), result.reasons

    result = guard_with(quota=TimeoutError("down")).evaluate()
    assert result.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    assert any("could not be read" in r for r in result.reasons)
    print("[ok] 8. exhausted or unreadable plan usage blocks")


def test_require_safe_raises_with_verdict():
    guard = guard_with(balances=dict(SAFE_BALANCES, credit_balance="1.00"))
    try:
        guard.require_safe()
    except BillingBlocked as blocked:
        assert blocked.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
        assert blocked.reasons
        print("[ok] 9. require_safe raises BillingBlocked carrying the verdict")
        return
    raise AssertionError("require_safe did not raise")


def test_balance_endpoint_is_declared_undocumented():
    assert BALANCE_DEPENDENCY_CLASS == "UNDOCUMENTED_FIRST_PARTY_IMPLEMENTATION_DEPENDENCY"
    source = (ROOT / "src/contentops/media/billing_guard.py").read_text(encoding="utf-8")
    assert "/account/query_balance" in source
    print("[ok] 10. the undocumented balance dependency is declared, not hidden")


def test_balance_endpoint_lives_in_exactly_one_module():
    hits = []
    for path in (ROOT / "src").rglob("*.py"):
        if "query_balance" in path.read_text(encoding="utf-8"):
            hits.append(path.relative_to(ROOT).as_posix())
    for path in (ROOT / "scripts").glob("*.py"):
        if path.name in {"billing_guard.py"}:
            continue
        if "query_balance" in path.read_text(encoding="utf-8"):
            hits.append(path.relative_to(ROOT).as_posix())
    assert hits == ["src/contentops/media/billing_guard.py"], hits
    print("[ok] 11. the undocumented endpoint exists in exactly one implementation")


# --- 3. Easel compatibility -------------------------------------------------

def test_easel_compatibility_recorded_as_incompatible():
    assert EASEL_COMPATIBILITY == "EASEL_MPLAN_AUTH_INCOMPATIBLE"
    print("[ok] 12. pinned Easel incompatibility is recorded as measured fact")


def test_pinned_easel_requires_group_id():
    """The real reason Easel cannot be used, asserted against the pinned source.

    If a future Easel upgrade drops GroupId this test fails, which is the point:
    the architecture decision must be revisited rather than silently inherited.
    """
    script = ROOT / ".runtime" / "easel" / "skills" / "shared" / "scripts" / "voice_clone.py"
    if not script.is_file():
        print("[skip] 13. pinned Easel runtime not present on this host")
        return
    text = script.read_text(encoding="utf-8", errors="ignore")
    assert 'require_env("MINIMAX_GROUP_ID")' in text, (
        "pinned Easel no longer requires MINIMAX_GROUP_ID; re-run the Easel "
        "compatibility test before trusting EASEL_MPLAN_AUTH_INCOMPATIBLE"
    )
    assert "speech-01" in text, "pinned Easel default model changed; re-verify"
    print("[ok] 13. pinned Easel still hard-requires MINIMAX_GROUP_ID and defaults to speech-01")


# --- 4. pronunciation lexicon ----------------------------------------------

def test_lexicon_uses_plain_text_expansion_only():
    lexicon = default_zh_lexicon()
    args = lexicon.provider_arguments()
    assert args, "expected pronunciation arguments"
    joined = " ".join(args)
    assert "IPA" not in joined
    for entry in lexicon.rules.values():
        # A plain-text expansion never contains IPA bracket notation.
        assert "(" not in entry and ")" not in entry, entry
    print("[ok] 14. lexicon emits plain-text expansion and never IPA")


def test_lexicon_keeps_display_and_spoken_apart():
    lexicon = default_zh_lexicon()
    display = "Claude Code 与 Easel 的版本 v0.2.1"
    spoken = lexicon.spoken_text(display)
    assert "Claude Code" in display, "display text must not be mutated"
    assert "Claude Code" not in spoken, "spoken text should use the expansion"
    assert "克劳德代码" in spoken
    assert "v零点二点一" in spoken
    print("[ok] 15. display text is preserved while spoken text is rewritten")


def test_lexicon_covers_the_regression_vocabulary():
    lexicon = default_zh_lexicon()
    report = coverage_report(lexicon)
    measured_failures = {"Claude Code", "Easel", "LangGraph", "Qwen", "v0.2.1"}
    for token in measured_failures:
        assert report[token], f"regression token not covered: {token}"
    print("[ok] 16. every M2.0-measured failure has a lexicon entry")


def test_lexicon_version_enters_the_fingerprint():
    lexicon = default_zh_lexicon()
    base = speech_fingerprint(
        provider="p", product="m_plan", plan="explore", model="speech-2.8-hd",
        voice="v", spoken_text="你好", lexicon_component=lexicon.fingerprint_component(),
    )
    bumped = speech_fingerprint(
        provider="p", product="m_plan", plan="explore", model="speech-2.8-hd",
        voice="v", spoken_text="你好",
        lexicon_component=default_zh_lexicon(
            {"Claude Code": "克劳德码"}
        ).fingerprint_component(),
    )
    assert base != bumped, "a lexicon rule change must change the fingerprint"
    assert lexicon.version == LEXICON_VERSION
    print("[ok] 17. lexicon version participates in the generation fingerprint")


def test_english_lexicon_is_empty_without_evidence():
    lexicon = default_en_lexicon()
    assert lexicon.rules == {}
    assert lexicon.spoken_text("Claude Code") == "Claude Code"
    print("[ok] 18. the English lexicon adds no rule that M2.0 did not measure")


# --- 5. fingerprint / idempotency -----------------------------------------

def test_fingerprint_changes_with_every_material_input():
    base = dict(
        provider="minimax_m_plan", product="m_plan", plan="explore",
        model="speech-2.8-hd", voice="v1", spoken_text="你好",
        lexicon_component="abc",
    )
    reference = speech_fingerprint(**base)
    for field, value in (
        ("provider", "other"), ("product", "other"), ("plan", "build"),
        ("model", "speech-2.6-hd"), ("voice", "v2"),
        ("spoken_text", "你好啊"), ("lexicon_component", "def"),
        ("speed", 1.2), ("text_normalization", False),
        ("normalisation_target_lufs", -14.0),
    ):
        mutated = dict(base)
        mutated[field] = value
        assert speech_fingerprint(**mutated) != reference, field
    print("[ok] 19. fingerprint changes with every input that affects the audio")


def test_fingerprint_is_stable_for_identical_input():
    args = dict(
        provider="minimax_m_plan", product="m_plan", plan="explore",
        model="speech-2.8-hd", voice="v1", spoken_text="你好", lexicon_component="abc",
    )
    assert speech_fingerprint(**args) == speech_fingerprint(**args)
    print("[ok] 20. identical inputs produce an identical fingerprint")


# --- 6. retry discipline ---------------------------------------------------

def test_retry_cap_is_two():
    assert MAX_ATTEMPTS == 2
    print("[ok] 21. maximum provider attempts is 2")


def test_second_attempt_requires_a_named_reason():
    source = (ROOT / "src/contentops/media/minimax_speech.py").read_text(encoding="utf-8")
    assert "retry_reason" in source
    assert "A second attempt requires a named failure reason" in source
    print("[ok] 22. a second attempt demands a named reason and a changed input")


# --- 7. receipt sanitation --------------------------------------------------

def test_receipt_records_credential_class_not_value():
    receipt = {
        "provider": "minimax_m_plan", "product": "m_plan", "plan": "explore",
        "billing_mode": "subscription", "payg_allowed": False,
        "credit_pack_allowed": False, "transport": "official_cli",
        "transport_version": "mmx 1.0.27", "model": "speech-2.8-hd", "voice": "v",
        "display_text_sha256": "a", "spoken_text_sha256": "b",
        "lexicon_version": LEXICON_VERSION, "fingerprint": "c",
        "quota_before": None, "quota_after": None,
        "billing_guard_verdict": SAFE_INCLUDED_PLAN, "billing_guard_reasons": [],
        "technical_qc": {}, "semantic_qc": {"can_approve_quality": False},
        "raw_sha256": "d", "normalized_sha256": "e", "attempt": 1,
        "retry_reason": None, "fallback": {"used": False},
        "production_ready": False, "human_review": "PENDING_FOUNDER_REVIEW",
        "post_generation_billing_state": {},
    }
    rendered = json.dumps(receipt_to_dict(type("R", (), receipt)()))
    assert "sk-" not in rendered, rendered
    assert "payg_allowed" in rendered and "credit_pack_allowed" in rendered
    assert "PENDING_FOUNDER_REVIEW" in rendered
    print("[ok] 23. receipt carries the class, the hashes and the review state only")


def test_asr_is_a_detector_and_never_approves():
    source = (ROOT / "src/contentops/media/asr_backcheck.py").read_text(encoding="utf-8")
    assert "DETECTOR_ONLY" in source
    assert "can_approve_quality" in source
    print("[ok] 24. ASR backcheck is declared incapable of approving quality")


def test_asr_detects_missing_and_duplicated_tokens():
    assert token_overlap("版本 v0.2.1 已发布", "版本 v0.2.1 已发布") == 1.0
    assert token_overlap("版本 v0.2.1 已发布", "版本 已发布") < 0.9
    assert token_overlap("Claude Code", "Cloud Code") < 1.0
    print("[ok] 25. ASR comparison detects missing and mangled tokens")


# --- 8. edge-tts fallback semantics ---------------------------------------

def test_fallback_is_explicit_and_never_silent():
    source = (ROOT / "src/contentops/media/minimax_speech.py").read_text(encoding="utf-8")
    assert '"used": False' in source
    assert "explicit only" in source
    assert "production_ready = False" in source
    cli = (ROOT / "scripts/synthesize_narration.py").read_text(encoding="utf-8")
    assert "A silent swap to edge-tts is forbidden" in cli
    print("[ok] 26. edge-tts stays available but can never be used silently")


# --- 9. test video duration policy ---------------------------------------

def test_duration_policy_prefers_shortest_legal_value():
    for minimum in (1, 2, 3):
        spec = ProviderDurationSpec(
            model="m", minimum_s=minimum, maximum_s=15, allowed=tuple(range(minimum, 16))
        )
        decision = decide_test_duration(spec)
        assert decision.duration_s == minimum, minimum
        assert decision.is_provider_minimum
    print("[ok] 27. provider minimums of 1s, 2s and 3s are used as-is")


def test_duration_policy_uses_minimum_when_above_three():
    for minimum in (4, 5, 6):
        spec = ProviderDurationSpec(
            model="m", minimum_s=minimum, maximum_s=15, allowed=tuple(range(minimum, 16))
        )
        decision = decide_test_duration(spec)
        assert decision.duration_s == minimum, minimum
        assert decision.is_provider_minimum
        assert not decision.preferred_applied
        assert "exceeds the preferred" in decision.reason
    assert PREFERRED_TEST_DURATION_RANGE == (1, 3)
    print("[ok] 28. minimums above 3s fall back to the provider minimum, never lower")


def test_duration_policy_rejects_unsupported_short_request():
    spec = ProviderDurationSpec(
        model="MiniMax-H3", minimum_s=4, maximum_s=15, allowed=tuple(range(4, 16))
    )
    try:
        decide_test_duration(spec, requested_s=2)
    except ValueError as exc:
        assert "does not support 2s" in str(exc)
        print("[ok] 29. an unsupported shorter request is refused, not sent")
        return
    raise AssertionError("unsupported duration was accepted")


def test_duration_policy_demands_justification_above_minimum():
    spec = H3_DURATION_SPEC
    decision = decide_test_duration(
        spec, objective="", why_minimum_is_insufficient="", quota_budget=""
    )
    assert decision.duration_s == 4
    assert not decision.requires_justification
    longer = decide_test_duration(
        spec, requested_s=10, objective="camera move needs 10s",
        why_minimum_is_insufficient="4s truncates the move", quota_budget="1 job",
    )
    assert longer.duration_s == 10
    assert longer.requires_justification
    undocumented = decide_test_duration(spec, requested_s=10)
    assert set(undocumented.justification_fields) == {
        "test_objective", "why_minimum_is_insufficient", "quota_budget",
    }
    print("[ok] 30. a test longer than the minimum requires the three justifications")


def test_verified_h3_duration_ranges():
    assert (H3_DURATION_SPEC.minimum_s, H3_DURATION_SPEC.maximum_s) == (4, 15)
    assert H3_DURATION_SPEC.supports(4) and H3_DURATION_SPEC.supports(15)
    assert not H3_DURATION_SPEC.supports(3)
    assert (H3_MAX_DURATION_SPEC.minimum_s, H3_MAX_DURATION_SPEC.maximum_s) == (5, 15)
    assert not H3_MAX_DURATION_SPEC.supports(4)
    assert decide_test_duration(H3_DURATION_SPEC).duration_s == 4
    assert decide_test_duration(H3_MAX_DURATION_SPEC).duration_s == 5
    print("[ok] 31. H3 is 4-15 and H3 Max is 5-15, so test durations are 4s and 5s")


def test_duration_policy_does_not_touch_production():
    source = (ROOT / "src/contentops/media/test_duration_policy.py").read_text(
        encoding="utf-8"
    )
    assert "no authority over production shot duration" in source
    print("[ok] 32. the policy states it does not constrain production duration")


# --- 10. audio normalisation and QC (local ffmpeg only) -------------------

def _make_tone(path: Path, seconds: float = 3.0, freq: int = 440) -> bool:
    if not HAVE_FFMPEG:
        return False
    result = hidden_run(
        ["ffmpeg", "-y", "-hide_banner", "-nostdin",
         "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}",
         "-ar", "32000", "-ac", "1", "-c:a", "pcm_s16le", str(path)],
        timeout=180,
    )
    return result.returncode == 0 and path.is_file()


def test_normalisation_moves_level_toward_target():
    """Normalisation must move the level toward the target, in either direction.

    Asserting "peak always goes down" would be wrong: M2.0 measured MiniMax
    output near 0 dB, which needs attenuating, but a quiet input needs lifting.
    The invariant is distance-to-target, not direction.
    """
    if not HAVE_FFMPEG:
        print("[skip] 33. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "raw.wav"
        if not _make_tone(raw, 3.0):
            print("[skip] 33. could not synthesise a local test tone")
            return
        out = Path(td) / "norm.wav"
        report = normalise_speech(raw, out)
        assert report["ok"], report
        before_lufs = report["before"]["integrated_lufs"]
        after_lufs = report["after"]["integrated_lufs"]
        assert before_lufs is not None and after_lufs is not None, report
        target = NORMALISATION_TARGET_LUFS
        assert abs(after_lufs - target) <= abs(before_lufs - target) + 0.5, (
            f"normalisation moved away from target: {before_lufs} -> {after_lufs} "
            f"(target {target})"
        )
        assert report["target_lufs"] == target
        assert report["target_true_peak_db"] == NORMALISATION_TRUE_PEAK_DB
        after_peak = report["after"]["peak_db"]
        assert after_peak is not None and after_peak <= -0.1, (
            f"normalised output must keep true-peak headroom, got {after_peak}"
        )
    print("[ok] 33. normalisation moves the level toward target and keeps headroom")


def test_normalisation_is_not_applied_twice():
    if not HAVE_FFMPEG:
        print("[skip] 34. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "raw.wav"
        if not _make_tone(raw, 3.0):
            print("[skip] 34. could not synthesise a local test tone")
            return
        once = Path(td) / "once.wav"
        twice = Path(td) / "twice.wav"
        first = normalise_speech(raw, once)
        second = normalise_speech(once, twice)
        assert first["ok"] and second["ok"]
        # Re-normalising an already-normalised file must not keep moving the level.
        assert abs(second["after"]["peak_db"] - first["after"]["peak_db"]) < 0.6, (
            first["after"]["peak_db"], second["after"]["peak_db"]
        )
    print("[ok] 34. re-normalising an already-normalised file barely moves the level")


def test_technical_qc_rejects_silence_and_accepts_tone():
    if not HAVE_FFMPEG:
        print("[skip] 35. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        tone = Path(td) / "tone.wav"
        if not _make_tone(tone, 2.0):
            print("[skip] 35. could not synthesise a local test tone")
            return
        good = technical_qc(tone, expected_sample_rate_hz=32000)
        assert good["approved"], good["checks"]

        silent = Path(td) / "silent.wav"
        made = hidden_run(
            ["ffmpeg", "-y", "-hide_banner", "-nostdin",
             "-f", "lavfi", "-i", "anullsrc=r=32000:cl=mono",
             "-t", "2", "-c:a", "pcm_s16le", str(silent)],
            timeout=180,
        )
        if made.returncode == 0 and silent.is_file():
            bad = technical_qc(silent, expected_sample_rate_hz=32000)
            assert not bad["approved"], "silence must not pass the gate"
            names = {c["check"] for c in bad["checks"] if not c["passed"]}
            assert names, bad
    print("[ok] 35. technical QC approves a tone and rejects digital silence")


def test_technical_qc_rejects_missing_file():
    result = technical_qc(Path("does-not-exist.wav"))
    assert not result["approved"]
    assert result["checks"][0]["check"] == "file_exists"
    print("[ok] 36. a missing asset is never approved")


def test_measure_audio_reports_format():
    if not HAVE_FFMPEG:
        print("[skip] 37. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        tone = Path(td) / "tone.wav"
        if not _make_tone(tone, 2.0):
            print("[skip] 37. could not synthesise a local test tone")
            return
        measured = measure_audio(tone)
        assert measured.sample_rate_hz == 32000, measured
        assert measured.channels == 1, measured
        assert measured.duration_s and measured.duration_s > 1.5, measured
    print("[ok] 37. measurement reports sample rate, channels and duration")


# --- 11. no provider call in CI, no popup on Windows --------------------

def test_provider_module_makes_no_network_call_at_import():
    source = (ROOT / "src/contentops/media/minimax_speech.py").read_text(encoding="utf-8")
    # The provider shells out to the official CLI only; it never calls a
    # generation endpoint directly, and never at import time.
    assert "urlopen" not in source, "provider must delegate to the official CLI"
    tree_src = source
    assert "import urllib" not in tree_src
    print("[ok] 38. provider delegates to the CLI and opens no generation socket")


def test_subprocess_policy_covers_the_new_modules():
    result = hidden_run(
        [python_executable(), "scripts/check_subprocess_policy.py"], cwd=str(ROOT),
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in (result.stdout or "")
    print("[ok] 39. the subprocess policy gate passes with the new modules tracked")


def test_cli_entrypoint_help_runs():
    result = hidden_run(
        [python_executable(), "scripts/synthesize_narration.py", "--help"],
        cwd=str(ROOT), timeout=180,
    )
    assert result.returncode == 0, result.stderr
    assert "--text" in (result.stdout or "")
    assert "MINIMAX_SUBSCRIPTION_KEY" in (result.stdout or "")
    print("[ok] 40. the narration CLI entry point loads and documents itself")


def test_transport_flattens_newlines_before_calling_the_cli():
    """Newline in --text silently truncates narration and ignores --out.

    Measured 2026-10-04: with a newline the official CLI exits 0, writes an MP3
    into the working directory, ignores ``--out`` and ``--format``, and
    synthesises only the first line. The text must therefore be flattened.
    """
    multiline = "第一行内容测试。\n第二行内容测试。"
    flat = flatten_for_cli(multiline)
    assert "\n" not in flat and "\r" not in flat
    assert flat == "第一行内容测试。 第二行内容测试。"
    assert flatten_for_cli(flat) == flat, "flattening must be idempotent"
    assert flatten_for_cli("单行无换行") == "单行无换行"
    print("[ok] 41. multi-line narration is flattened to one CLI-safe line")


def test_transport_never_uses_the_rejected_pause_marker():
    source = (ROOT / "src/contentops/media/minimax_speech.py").read_text(encoding="utf-8")
    assert 'PAUSE_JOIN = " "' in source
    assert "rejected" in source
    print("[ok] 42. the documented pause marker was rejected by the CLI and is not used")


def test_verify_output_rejects_missing_stale_and_trivial_files():
    import time

    with tempfile.TemporaryDirectory() as td:
        missing = Path(td) / "missing.wav"
        try:
            verify_output(missing, not_before=time.time())
        except RuntimeError as exc:
            assert "does not exist" in str(exc)
        else:
            raise AssertionError("a missing output must be rejected")

        empty = Path(td) / "empty.wav"
        empty.write_bytes(b"RIFF" + b"\0" * 16)
        try:
            verify_output(empty, not_before=time.time())
        except RuntimeError as exc:
            assert "bytes" in str(exc)
        else:
            raise AssertionError("a trivial output must be rejected")

        stale = Path(td) / "stale.wav"
        stale.write_bytes(b"RIFF" + b"\0" * 4096)
        old = time.time() - 3600
        import os

        os.utime(stale, (old, old))
        try:
            verify_output(stale, not_before=time.time())
        except RuntimeError as exc:
            assert "stale" in str(exc)
        else:
            raise AssertionError("a stale output must be rejected")

        fresh = Path(td) / "fresh.wav"
        fresh.write_bytes(b"RIFF" + b"\0" * 4096)
        verify_output(fresh, not_before=time.time() - 5)
    print("[ok] 43. output verification rejects missing, stale and trivial files")


def test_lexicon_covers_the_narration_asr_findings():
    lexicon = default_zh_lexicon()
    # "Web 工作台" was transcribed as "外部工作台" in the M2 narration check.
    assert lexicon.spoken_text("Web 工作台这条路有六项没过") == (
        "网页工作台这条路有六项没过"
    )
    print("[ok] 44. the lexicon entry added from the narration ASR check applies")


def test_asr_coverage_is_meaningful_for_chinese():
    """A whitespace tokeniser scores a perfect Chinese reading near zero.

    Measured before the fix: coverage 0.3125 on a transcript that was correct,
    because the narration has almost no spaces. Per-character comparison for CJK
    plus word tokens for latin is what makes the number usable.
    """
    expected = "我把它锁在 v0.2.1，982 个文件逐个比对过哈希"
    same = "我把它锁在v0.2.1，982个文件逐个比对过哈希"
    assert token_overlap(expected, same) > 0.95, token_overlap(expected, same)
    truncated = "我把它锁在v0.2.1"
    assert token_overlap(expected, truncated) < 0.7
    print("[ok] 45. ASR coverage is meaningful for Chinese, not near-zero on success")


def test_asr_reconciles_chinese_numerals_with_digits():
    from contentops.media.asr_backcheck import _normalise

    assert _normalise("九百八十二") == "982"
    assert _normalise("五十二") == "52"
    assert _normalise("零点二点一") == "0.21"
    # A converter that cannot model 万 must leave the text alone, not mangle it.
    assert _normalise("一万二千") == "一万二千"
    print("[ok] 46. numeral forms reconcile, and unrepresentable ones stay untouched")


def test_loudness_is_measured_not_predicted():
    """The integrated loudness in a receipt must be a measurement.

    The ``loudnorm`` filter reports the loudness it *predicts* it would produce.
    Recording that as a measurement produced a wrong conclusion that the -16
    LUFS target was unreachable; a real ebur128 meter showed -17.0 LUFS
    achieved. Checked with ``ast`` so the docstring that explains the
    distinction cannot produce a false failure.
    """
    import ast as _ast

    source = (ROOT / "src/contentops/media/audio.py").read_text(encoding="utf-8")
    assert "ebur128=peak=true" in source
    tree = _ast.parse(source)
    # Scope the check to measure_audio. loudnorm is legitimately used elsewhere
    # to *process* audio; it must not be used to *measure* it.
    measure_fn = next(
        node
        for node in _ast.walk(tree)
        if isinstance(node, _ast.FunctionDef) and node.name == "measure_audio"
    )
    meter_filters = [
        node.value
        for node in _ast.walk(measure_fn)
        if isinstance(node, _ast.Constant)
        and isinstance(node.value, str)
        and ("loudnorm=" in node.value or "ebur128=" in node.value)
    ]
    assert meter_filters, "expected an explicit meter filter string"
    assert any("ebur128=" in f for f in meter_filters), meter_filters
    assert not any("loudnorm=" in f for f in meter_filters), (
        f"measurement must not use the loudnorm filter: {meter_filters}"
    )
    print("[ok] 47. integrated loudness is metered by ebur128, not predicted by loudnorm")




def _failed_attempt_record(work_dir, *, request=None, provider=None):
    """Drive one real failing attempt and return its durable record path.

    The fixture CLI exits non-zero under FAKE_MMX_FAIL, so this produces genuine
    retry evidence rather than a hand-written fixture file.
    """
    import os

    from contentops.media.attempts import find_attempt_records

    previous = os.environ.get("FAKE_MMX_FAIL")
    os.environ["FAKE_MMX_FAIL"] = "1"
    try:
        # Build the provider *after* the flag is set: the child environment is
        # captured at construction, so ordering matters.
        provider = provider or _fixture_provider(work_dir)
        provider.synthesize_speech(
            request or SpeechRequest(display_text="你好，这是测试。", language="zh")
        )
    except RuntimeError:
        pass
    finally:
        if previous is None:
            os.environ.pop("FAKE_MMX_FAIL", None)
        else:
            os.environ["FAKE_MMX_FAIL"] = previous

    failed = find_attempt_records(work_dir, status="FAILED")
    assert failed, "the failed attempt must leave a durable record"
    return failed[-1].path_in(work_dir)


# --- 12. BLOCKER 1: modality-aware billing ---------------------------------

def _quota(interval, weekly):
    row = {"model_name": "general"}
    if interval is not None:
        row["current_interval_remaining_percent"] = interval
    if weekly is not None:
        row["current_weekly_remaining_percent"] = weekly
    return {"model_remains": [row]}


def test_modality_windows_follow_verified_mplan_behaviour():
    """speech/image need both windows; video is weekly-only. Proved by behaviour."""
    guard = guard_with(quota=_quota(98, 58))
    assert guard.evaluate(modality="speech").verdict == SAFE_INCLUDED_PLAN

    exhausted_5h = guard_with(quota=_quota(0, 58))
    assert exhausted_5h.evaluate(modality="speech").verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    assert any("interval_remaining_percent" in r for r in exhausted_5h.evaluate("speech").reasons)

    unknown_5h = guard_with(quota=_quota(None, 58))
    assert unknown_5h.evaluate(modality="speech").verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN

    assert exhausted_5h.evaluate(modality="image").verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN

    # video does not consume the 5-hour window, so an empty one must not block it
    assert exhausted_5h.evaluate(modality="video").verdict == SAFE_INCLUDED_PLAN

    no_weekly = guard_with(quota=_quota(98, 0))
    assert no_weekly.evaluate(modality="video").verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    print("[ok] 48. modality windows enforced: speech/image need 5h+weekly, video weekly only")


def test_unknown_modality_is_blocked_not_defaulted():
    for modality in ("audio", "", "SPEECH", "tts", None):
        result = guard_with(quota=_quota(98, 58)).evaluate(modality=modality)
        assert result.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN, modality
        assert any("unknown modality" in r for r in result.reasons), (modality, result.reasons)
    print("[ok] 49. an unknown modality blocks instead of silently defaulting")


def test_weekly_only_never_implies_all_modalities_safe():
    """The bug this fixes: weekly>0 used to be treated as safe for everything."""
    guard = guard_with(quota=_quota(0, 58))
    assert guard.evaluate("video").safe is True
    assert guard.evaluate("speech").safe is False
    assert guard.evaluate("image").safe is False
    print("[ok] 50. weekly-only quota never implies speech or image are safe")


# --- 13. BLOCKER 2: owed_amount fails closed --------------------------------

def test_owed_amount_is_required_and_must_be_zero():
    assert "owed_amount" in ZERO_REQUIRED_BALANCE_FIELDS

    missing = {k: v for k, v in SAFE_BALANCES.items() if k != "owed_amount"}
    r = guard_with(balances=missing).evaluate()
    assert r.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    assert any("owed_amount" in x and "missing" in x for x in r.reasons)

    for bad in (None, "", "not-a-number", "abc"):
        r = guard_with(balances=dict(SAFE_BALANCES, owed_amount=bad)).evaluate()
        assert r.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN, bad

    r = guard_with(balances=dict(SAFE_BALANCES, owed_amount="0.01")).evaluate()
    assert r.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    assert any("owed_amount" in x for x in r.reasons)

    r = guard_with(balances=dict(SAFE_BALANCES, owed_amount="0.00")).evaluate()
    assert r.verdict == SAFE_INCLUDED_PLAN, r.reasons
    print("[ok] 51. owed_amount must be present, numeric and exactly zero")


def test_every_required_balance_field_fails_closed_on_schema_change():
    for field in ZERO_REQUIRED_BALANCE_FIELDS:
        partial = {k: v for k, v in SAFE_BALANCES.items() if k != field}
        r = guard_with(balances=partial).evaluate()
        assert r.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN, field
    print("[ok] 52. a schema change on any required balance field blocks")


# --- 14. BLOCKER 3: receipt state and cache provenance ----------------------

FIXTURE_CLI = [sys.executable, str(ROOT / "tests" / "fixtures" / "fake_mmx_cli.py")]


#: A synthetic subscription credential. It never reaches a real provider: the
#: fixture CLI ignores the value, and every test that matters uses a local stub.
TEST_SUBSCRIPTION_KEY = "sk-cp-TESTONLY0000000000"


def _resolved(key=TEST_SUBSCRIPTION_KEY, source="MINIMAX_SUBSCRIPTION_KEY_ENV"):
    from contentops.media.credentials import ResolvedCredential, classify_credential

    return ResolvedCredential(
        key=key,
        credential_class=classify_credential(key),
        source=source,
    )


def _fixture_provider(work_dir, guard=None, cli=None, credential=None):
    """Build a provider with the authorised credential bound to the transport.

    Binding is mandatory: an unbound provider refuses to generate rather than
    letting the child discover its own credential.
    """
    from contentops.media.minimax_speech import MiniMaxMPlanProvider

    resolved = credential if credential is not None else _resolved()
    return MiniMaxMPlanProvider(
        guard=guard if guard is not None else guard_with(credential=resolved.key),
        work_dir=work_dir,
        cli=cli if cli is not None else FIXTURE_CLI,
        transport_credential=resolved,
    )


def test_receipt_before_any_synthesis_raises():
    if not HAVE_FFMPEG:
        print("[skip] 53. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        provider = _fixture_provider(Path(td))
        try:
            provider.receipt()
        except RuntimeError as exc:
            assert "no receipt available" in str(exc)
            print("[ok] 53. receipt() before any synthesis raises instead of faking one")
            return
        raise AssertionError("receipt() returned placeholder provenance")


def test_receipt_is_persisted_and_retrievable_after_synthesis():
    if not HAVE_FFMPEG:
        print("[skip] 54. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        provider = _fixture_provider(Path(td))
        outcome = provider.synthesize_speech(
            SpeechRequest(display_text="你好，这是测试。", language="zh")
        )
        latest = provider.receipt()
        assert latest.fingerprint == outcome.receipt.fingerprint
        assert latest.model == outcome.receipt.model
        assert latest.voice, "a generated receipt must record the real voice"
        assert latest.display_text_sha256, "a generated receipt must record the text hash"
        assert latest.spoken_text_sha256
        assert latest.lexicon_version, "must record the lexicon version actually used"
        assert latest.raw_sha256 and latest.normalized_sha256

        by_asset = provider.receipt(outcome.asset)
        assert by_asset.fingerprint == outcome.receipt.fingerprint
        assert by_asset.raw_sha256 == outcome.receipt.raw_sha256

        sidecar = sidecar_for(Path(outcome.asset.normalized_path))
        assert sidecar.is_file(), "a sidecar receipt must be written next to the asset"
        stored = load_sidecar(sidecar)
        assert stored["fingerprint"] == outcome.receipt.fingerprint
        assert stored["normalized_sha256"] == outcome.asset.normalized_sha256
        assert stored["provider_call"] is True
    print("[ok] 54. receipt() works after synthesis, by asset, and is persisted as a sidecar")


def test_reused_asset_carries_truthful_provenance():
    if not HAVE_FFMPEG:
        print("[skip] 55. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        provider = _fixture_provider(Path(td))
        request = SpeechRequest(display_text="你好，这是测试。", language="zh")
        first = provider.synthesize_speech(request)
        second = provider.synthesize_speech(request)
        assert second.reused is True
        # The old implementation returned blank voice and blank text hashes here.
        assert second.asset.voice == first.asset.voice and second.asset.voice
        assert second.asset.display_text_sha256 == first.asset.display_text_sha256
        assert second.receipt.lexicon_version == first.receipt.lexicon_version
        assert second.receipt.model == first.receipt.model
        assert second.receipt.normalized_sha256 == first.receipt.normalized_sha256
    print("[ok] 55. a reused asset preserves the original voice, hashes and lexicon version")


def test_cache_is_rejected_when_the_sidecar_disagrees():
    if not HAVE_FFMPEG:
        print("[skip] 56. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        provider = _fixture_provider(Path(td))
        request = SpeechRequest(display_text="你好，这是测试。", language="zh")
        outcome = provider.synthesize_speech(request)
        sidecar = sidecar_for(Path(outcome.asset.normalized_path))

        # fingerprint mismatch
        payload = load_sidecar(sidecar)
        payload["fingerprint"] = "0" * 64
        write_sidecar(sidecar, payload)
        assert provider._reuse(
            normalized_path=Path(outcome.asset.normalized_path),
            raw_path=Path(outcome.asset.raw_path),
            sidecar_path=sidecar,
            fingerprint=outcome.receipt.fingerprint,
        ) is None

        # hash mismatch
        original = json.loads(sidecar.read_text(encoding="utf-8"))
        original["normalized_sha256"] = "1" * 64
        write_sidecar(sidecar, original)
        assert provider._reuse(
            normalized_path=Path(outcome.asset.normalized_path),
            raw_path=Path(outcome.asset.raw_path),
            sidecar_path=sidecar,
            fingerprint=outcome.receipt.fingerprint,
        ) is None

        # corrupt sidecar
        sidecar.write_text("{not json", encoding="utf-8")
        assert load_sidecar(sidecar) is None
        assert provider._reuse(
            normalized_path=Path(outcome.asset.normalized_path),
            raw_path=Path(outcome.asset.raw_path),
            sidecar_path=sidecar,
            fingerprint=outcome.receipt.fingerprint,
        ) is None

        # missing sidecar
        sidecar.unlink()
        assert provider._reuse(
            normalized_path=Path(outcome.asset.normalized_path),
            raw_path=Path(outcome.asset.raw_path),
            sidecar_path=sidecar,
            fingerprint=outcome.receipt.fingerprint,
        ) is None
    print("[ok] 56. cache reuse is refused on sidecar mismatch, hash mismatch, corruption or absence")


def test_cache_reuse_makes_no_billing_or_network_call():
    """A valid cache must work with the billing transport broken.

    The previous order called require_safe() before checking the cache, so reuse
    needed quota and network. Reuse must need neither.
    """
    if not HAVE_FFMPEG:
        print("[skip] 57. ffmpeg not installed")
        return

    def exploding(url, credential):
        raise AssertionError(f"billing transport was called: {url}")

    with tempfile.TemporaryDirectory() as td:
        warm = _fixture_provider(Path(td))
        request = SpeechRequest(display_text="你好，这是测试。", language="zh")
        warm.synthesize_speech(request)

        offline_guard = BillingGuard(
            base_url="https://example.invalid", credential="sk-cp-EXAMPLE",
            http_get_json=exploding,
        )
        offline = _fixture_provider(Path(td), guard=offline_guard)
        outcome = offline.synthesize_speech(request)
        assert outcome.reused is True, "a valid cache must be reused"
        assert offline_guard.call_count == 0, "reuse must not touch the billing transport"
        assert outcome.asset.normalized_path
        assert Path(outcome.asset.normalized_path).is_file()
        assert outcome.asset.voice, "reused provenance must still be truthful"
        assert outcome.receipt.human_review == "PENDING_FOUNDER_REVIEW"
    print("[ok] 57. cache reuse needs no billing call, no network and no quota")


def test_force_bypasses_the_cache():
    if not HAVE_FFMPEG:
        print("[skip] 58. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        provider = _fixture_provider(Path(td))
        request = SpeechRequest(display_text="你好，这是测试。", language="zh")
        provider.synthesize_speech(request)
        forced = provider.synthesize_speech(
            SpeechRequest(display_text="你好，这是测试。", language="zh", force=True)
        )
        assert forced.reused is False
        assert forced.receipt.attempt == 1
    print("[ok] 58. force=true bypasses the cache and regenerates")


# --- 15. BLOCKER 5: retry must change a generation input -------------------

def test_retry_requires_a_named_reason():
    if not HAVE_FFMPEG:
        print("[skip] 59. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        record_path = _failed_attempt_record(work)
        provider = _fixture_provider(work)
        try:
            provider.synthesize_speech(
                SpeechRequest(display_text="你好，这是测试。", language="zh"),
                attempt=2, retry_reason=None, retry_from=record_path,
            )
        except RuntimeError as exc:
            assert "named failure reason" in str(exc)
        else:
            raise AssertionError("attempt 2 without a reason was allowed")
    print("[ok] 59. attempt 2 without a named failure reason is refused")


def test_retry_without_a_durable_record_is_refused():
    """A reason alone is not evidence: the previous fingerprint must persist."""
    if not HAVE_FFMPEG:
        print("[skip] 64. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        provider = _fixture_provider(Path(td))
        try:
            provider.synthesize_speech(
                SpeechRequest(display_text="你好，这是测试。", language="zh"),
                attempt=2, retry_reason="first attempt looked clipped",
            )
        except RuntimeError as exc:
            assert "--retry-from" in str(exc)
        else:
            raise AssertionError("attempt 2 with no record was allowed")
    print("[ok] 64. attempt 2 without --retry-from is refused")


def test_invalid_retry_records_are_refused():
    if not HAVE_FFMPEG:
        print("[skip] 65. ffmpeg not installed")
        return
    import json as _json

    from contentops.media.attempts import GenerationAttemptRecord

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        good = _failed_attempt_record(work)

        # missing file
        provider = _fixture_provider(work)
        try:
            provider.synthesize_speech(
                SpeechRequest(display_text="你好，这是测试。", language="zh"),
                attempt=2, retry_reason="r", retry_from=work / "nope.json",
            )
        except RuntimeError as exc:
            assert "retry record not found" in str(exc)
        else:
            raise AssertionError("a missing retry record was accepted")

        # wrong schema
        bad = work / "bad-schema.json"
        bad.write_text(_json.dumps({"schema_version": "wrong/v9"}), encoding="utf-8")
        try:
            provider.synthesize_speech(
                SpeechRequest(display_text="你好，这是测试。", language="zh"),
                attempt=2, retry_reason="r", retry_from=bad,
            )
        except RuntimeError as exc:
            assert "not usable" in str(exc)
        else:
            raise AssertionError("a wrong-schema retry record was accepted")

        # wrong modality
        wrong = work / "wrong-modality.json"
        GenerationAttemptRecord(
            provider="minimax_m_plan", modality="video",
            fingerprint="a" * 64, attempt_number=1, status="FAILED",
        ).write(work)
        source = GenerationAttemptRecord(
            provider="minimax_m_plan", modality="video",
            fingerprint="a" * 64, attempt_number=1, status="FAILED",
        )
        wrong.write_text(_json.dumps(source.to_dict()), encoding="utf-8")
        try:
            provider.synthesize_speech(
                SpeechRequest(display_text="你好，这是测试。", language="zh"),
                attempt=2, retry_reason="r", retry_from=wrong,
            )
        except RuntimeError as exc:
            assert "modality" in str(exc)
        else:
            raise AssertionError("a wrong-modality retry record was accepted")

        # previous attempt did not fail
        succeeded = work / "succeeded.json"
        record = GenerationAttemptRecord(
            provider="minimax_m_plan", modality="speech",
            fingerprint="b" * 64, attempt_number=1, status="SUCCEEDED",
        )
        succeeded.write_text(_json.dumps(record.to_dict()), encoding="utf-8")
        try:
            provider.synthesize_speech(
                SpeechRequest(display_text="你好，这是测试。", language="zh"),
                attempt=2, retry_reason="r", retry_from=succeeded,
            )
        except RuntimeError as exc:
            assert "only a FAILED first attempt" in str(exc)
        else:
            raise AssertionError("a SUCCEEDED record was accepted for retry")

        assert good.is_file()
    print("[ok] 65. invalid, wrong-modality and non-FAILED retry records are refused")


def test_retry_with_identical_fingerprint_is_refused():
    if not HAVE_FFMPEG:
        print("[skip] 60. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        record_path = _failed_attempt_record(work)
        # a brand new provider instance: the old in-memory fingerprint is gone
        provider = _fixture_provider(work)
        assert provider._last_attempt_fingerprint is None
        try:
            provider.synthesize_speech(
                SpeechRequest(display_text="你好，这是测试。", language="zh"),
                attempt=2, retry_reason="clipping suspected",
                retry_from=record_path,
            )
        except RuntimeError as exc:
            assert "must change a generation input" in str(exc)
        else:
            raise AssertionError("an identical retry was allowed")
    print("[ok] 60. attempt 2 with an unchanged fingerprint is refused across instances")


def test_retry_with_changed_input_is_accepted():
    if not HAVE_FFMPEG:
        print("[skip] 61. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        record_path = _failed_attempt_record(work)
        provider = _fixture_provider(work)
        outcome = provider.synthesize_speech(
            SpeechRequest(
                display_text="你好，这是测试。",
                language="zh",
                voice="Chinese (Mandarin)_Warm_Bestie",
            ),
            attempt=2,
            retry_reason="first voice read the brand token unclearly",
            retry_from=record_path,
        )
        assert outcome.reused is False
        assert outcome.receipt.attempt == 2
        assert outcome.receipt.retry_reason == "first voice read the brand token unclearly"
    print("[ok] 61. attempt 2 is accepted when a real generation input changed")


def test_retry_refused_before_any_billing_or_provider_call():
    """The refusal has to be cheap: no balance read, no quota read, no provider."""
    if not HAVE_FFMPEG:
        print("[skip] 66. ffmpeg not installed")
        return

    def exploding(url, credential):
        raise AssertionError(f"billing transport was called: {url}")

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        record_path = _failed_attempt_record(work)

        guard = BillingGuard(
            base_url="https://example.invalid", credential="sk-cp-EXAMPLE",
            http_get_json=exploding,
        )
        provider = _fixture_provider(work, guard=guard)
        try:
            provider.synthesize_speech(
                SpeechRequest(display_text="你好，这是测试。", language="zh"),
                attempt=2, retry_reason="r", retry_from=record_path,
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("identical retry was not refused")
        assert guard.call_count == 0, "refusal must precede the billing call"
    print("[ok] 66. an invalid retry is refused before any billing or provider call")


# --- 16. BLOCKER 4: ASR multiplicity --------------------------------------

def test_asr_multiplicity_behaviour():
    cases = [
        ("哈哈", "哈哈", [], []),
        ("哈哈", "哈", ["哈"], []),
        ("哈", "哈哈", [], ["哈"]),
        ("version version", "version", ["version"], []),
        (
            "the system is ready and the user is ready",
            "the system is ready and the user is ready",
            [], [],
        ),
    ]
    for expected, actual, want_missing, want_excess in cases:
        diff = _multiplicity(expected, actual)
        assert diff["missing"] == want_missing, (expected, actual, diff)
        assert diff["excess"] == want_excess, (expected, actual, diff)
    print("[ok] 62. ASR multiplicity separates missing from excess, repeated units included")


def test_asr_coverage_is_multiset_recall():
    assert token_overlap("version version", "version") == 0.5
    assert token_overlap("哈哈", "哈哈") == 1.0
    assert token_overlap("the ready system", "the ready system") == 1.0
    print("[ok] 63. coverage is multiset recall, so repeated content cannot be hidden")




# --- 17. BLOCKER 2: the generation receipt is immutable ----------------------

def test_generation_sidecar_is_immutable_on_cache_hit():
    """Reuse must not rewrite the receipt of the paid generation."""
    if not HAVE_FFMPEG:
        print("[skip] 67. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        provider = _fixture_provider(work)
        request = SpeechRequest(display_text="你好，这是测试。", language="zh")
        first = provider.synthesize_speech(request)
        sidecar = sidecar_for(Path(first.asset.normalized_path))
        before_bytes = sidecar.read_bytes()
        before = json.loads(before_bytes.decode("utf-8"))

        second = provider.synthesize_speech(request)
        after_bytes = sidecar.read_bytes()

        assert second.reused is True
        assert before_bytes == after_bytes, "cache reuse overwrote the generation receipt"
        after = json.loads(after_bytes.decode("utf-8"))
        for key in ("quota_before", "quota_after", "attempt", "provider_call"):
            assert after.get(key) == before.get(key), key
        assert after["provider_call"] is True, "the generation evidence must survive"
    print("[ok] 67. the generation sidecar is byte-identical after a cache hit")


def test_reused_receipt_carries_the_original_generation_evidence():
    if not HAVE_FFMPEG:
        print("[skip] 68. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        provider = _fixture_provider(work)
        request = SpeechRequest(display_text="你好，这是测试。", language="zh")
        first = provider.synthesize_speech(request)
        second = provider.synthesize_speech(request)

        assert second.reused is True
        assert second.receipt.attempt == 1, "reuse must not restate the attempt number"
        assert second.receipt.billing_guard_verdict == first.receipt.billing_guard_verdict
        assert second.receipt.quota_after is not None, (
            "the original post-generation observation must survive reuse"
        )
        assert second.receipt.raw_sha256 == first.receipt.raw_sha256
        assert second.receipt.human_review == "PENDING_FOUNDER_REVIEW"

        events = read_reuse_events(work)
        assert events and events[-1]["event"] == "CACHE_REUSE"
        assert events[-1]["provider_call"] is False
    print("[ok] 68. a reused receipt is the original generation receipt, reuse is audited separately")


def test_incomplete_sidecar_is_a_cache_miss():
    """Never fill a blank field in to make a cache hit succeed."""
    if not HAVE_FFMPEG:
        print("[skip] 69. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        provider = _fixture_provider(work)
        request = SpeechRequest(display_text="你好，这是测试。", language="zh")
        outcome = provider.synthesize_speech(request)
        sidecar = sidecar_for(Path(outcome.asset.normalized_path))
        original = json.loads(sidecar.read_text(encoding="utf-8"))

        def miss_with(mutate):
            payload = dict(original)
            mutate(payload)
            write_sidecar(sidecar, payload)
            return provider._reuse(
                normalized_path=Path(outcome.asset.normalized_path),
                raw_path=Path(outcome.asset.raw_path),
                sidecar_path=sidecar,
                fingerprint=outcome.receipt.fingerprint,
            )

        assert miss_with(lambda p: p.pop("voice")) is None
        assert miss_with(lambda p: p.update({"voice": ""})) is None
        assert miss_with(lambda p: p.update({"voice": "   "})) is None
        assert miss_with(lambda p: p.update({"display_text_sha256": ""})) is None
        assert miss_with(lambda p: p.update({"spoken_text_sha256": ""})) is None
        assert miss_with(lambda p: p.update({"lexicon_version": ""})) is None
        assert miss_with(lambda p: p.update({"normalized_sha256": ""})) is None
        assert miss_with(lambda p: p.update({"billing_guard_verdict": ""})) is None
        assert miss_with(lambda p: p.update({"human_review": ""})) is None
        assert miss_with(lambda p: p.update({"technical_qc": "not-a-dict"})) is None
        assert miss_with(lambda p: p.update({"semantic_qc": None})) is None
        assert miss_with(lambda p: p.update({"attempt": "one"})) is None
        assert miss_with(lambda p: p.update({"attempt": True})) is None
        assert miss_with(lambda p: p.pop("provider")) is None
    print("[ok] 69. a missing, blank or wrongly typed sidecar field is a cache miss")


def test_sidecar_completeness_helper_is_strict():
    assert sidecar_is_complete(None) is False
    assert sidecar_is_complete({}) is False
    good = {
        "provider": "minimax_m_plan", "product": "m_plan", "plan": "explore",
        "model": "speech-2.8-hd", "voice": "v",
        "display_text_sha256": "a", "spoken_text_sha256": "b",
        "lexicon_version": "zh-1", "fingerprint": "c",
        "raw_sha256": "d", "normalized_sha256": "e",
        "technical_qc": {}, "semantic_qc": {},
        "billing_guard_verdict": "SAFE_INCLUDED_PLAN",
        "attempt": 1, "human_review": "PENDING_FOUNDER_REVIEW",
    }
    assert sidecar_is_complete(good) is True
    for field in REQUIRED_SIDECAR_FIELDS:
        broken = dict(good)
        broken.pop(field)
        assert sidecar_is_complete(broken) is False, field
    print("[ok] 70. sidecar completeness requires every provenance field")


# --- 18. BLOCKER 3: the receipt records the authorisation, not the aftermath

def test_receipt_records_preflight_verdict_not_post_state():
    """A generation may exhaust the window it was authorised against.

    That must not turn the receipt into a claim that the call was unauthorised.
    """
    if not HAVE_FFMPEG:
        print("[skip] 71. ffmpeg not installed")
        return

    state = {"interval": 1, "weekly": 58}

    def shifting(url, credential):
        if url.endswith("query_balance"):
            return dict(SAFE_BALANCES)
        if url.endswith("token_plan/remains"):
            return _quota(state["interval"], state["weekly"])
        raise AssertionError(url)

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        guard = BillingGuard(
            base_url="https://example.invalid", credential="sk-cp-EXAMPLE",
            http_get_json=shifting,
        )
        provider = _fixture_provider(work, guard=guard)

        # The generation itself consumes the last of the 5-hour window.
        original_synthesize = provider._finish
        def consume_then_finish(**kwargs):
            state["interval"] = 0
            return original_synthesize(**kwargs)
        provider._finish = consume_then_finish

        outcome = provider.synthesize_speech(
            SpeechRequest(display_text="你好，这是测试。", language="zh")
        )

        assert outcome.receipt.billing_guard_verdict == SAFE_INCLUDED_PLAN, (
            "the receipt must record the verdict that authorised the request"
        )
        assert outcome.receipt.quota_before is not None
        assert outcome.receipt.quota_before.interval_remaining_percent == 1
        post = outcome.receipt.post_generation_billing_state
        assert post.get("quota_after", {}).get("interval_remaining_percent") == 0, (
            "the exhausted window must still be observable"
        )
        assert outcome.receipt.quota_after is not None
        assert outcome.receipt.quota_after.interval_remaining_percent == 0
    print("[ok] 71. the receipt records the authorisation, and post state separately")


def test_authorize_returns_the_full_verdict():
    guard = guard_with(quota=_quota(98, 58))
    preflight = guard.authorize(modality="speech")
    assert preflight.verdict == SAFE_INCLUDED_PLAN
    assert preflight.modality == "speech"
    assert preflight.credential_class == "SUBSCRIPTION"
    assert preflight.quota is not None and preflight.quota.weekly_remaining_percent == 58

    from contentops.media.contract import BillingBlocked

    unsafe = guard_with(balances=dict(SAFE_BALANCES, credit_balance="2.00"))
    try:
        unsafe.authorize(modality="video")
    except BillingBlocked as blocked:
        assert blocked.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    else:
        raise AssertionError("authorize did not raise")
    print("[ok] 72. authorize() returns the complete verdict and raises when unsafe")


def test_generation_makes_one_balance_read_not_a_second_authorisation():
    """B12: avoid re-running the undocumented balance read after generation."""
    if not HAVE_FFMPEG:
        print("[skip] 73. ffmpeg not installed")
        return

    counts = {"balance": 0}

    def counting(url, credential):
        if url.endswith("query_balance"):
            counts["balance"] += 1
            return dict(SAFE_BALANCES)
        return _quota(98, 58)

    with tempfile.TemporaryDirectory() as td:
        counts["balance"] = 0
        guard = BillingGuard(
            base_url="https://example.invalid", credential="sk-cp-EXAMPLE",
            http_get_json=counting,
        )
        provider = _fixture_provider(Path(td), guard=guard)
        provider.synthesize_speech(
            SpeechRequest(display_text="你好，这是测试。", language="zh")
        )
        # pre-flight balances + post quota read = one balance call, one quota call
        assert counts["balance"] == 1, (
            f"the undocumented balance endpoint was read {counts['balance']} times"
        )
    print("[ok] 73. one pre-flight balance read, no redundant post-generation authorisation")


# --- 19. previous five fixes must not have regressed ----------------------

def test_previous_fixes_still_hold():
    # 1 modality-aware
    assert guard_with(quota=_quota(0, 58)).evaluate("video").verdict == SAFE_INCLUDED_PLAN
    assert guard_with(quota=_quota(0, 58)).evaluate("speech").verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    assert guard_with(quota=_quota(98, 0)).evaluate("image").verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    # 2 owed_amount
    assert "owed_amount" in ZERO_REQUIRED_BALANCE_FIELDS
    assert guard_with(balances=dict(SAFE_BALANCES, owed_amount="1")).evaluate().verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    assert guard_with(balances=dict(SAFE_BALANCES, owed_amount="not-a-number")).evaluate().verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    # 3 receipt() state
    if HAVE_FFMPEG:
        with tempfile.TemporaryDirectory() as td:
            try:
                _fixture_provider(Path(td)).receipt()
            except RuntimeError:
                pass
            else:
                raise AssertionError("receipt() before synthesis must raise")
    # 4 ASR multiplicity
    assert _multiplicity("哈哈", "哈哈") == {"missing": [], "excess": []}
    assert token_overlap("version version", "version") == 0.5
    # 5 retry cap
    assert MAX_ATTEMPTS == 2
    print("[ok] 74. modality awareness, owed_amount, ASR multiplicity and retry cap all hold")




# --- 20. B5: the retry rule must survive a real process boundary ------------

class _StubBillingServer:
    """Local stand-in for the two billing reads, so CI never contacts a provider.

    It only ever reports zero paid balances, and the base URL points at
    127.0.0.1, so no MiniMax host is contacted and no real quota can move.
    """

    def __init__(self, quota):
        self.quota = quota
        self.calls = []

    def __enter__(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        quota = self.quota
        calls = self.calls

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - name fixed by the base class
                calls.append(self.path)
                if "query_balance" in self.path:
                    body = dict(SAFE_BALANCES)
                elif "token_plan/remains" in self.path:
                    body = quota
                else:
                    self.send_error(404)
                    return
                raw = json.dumps(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                return

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self._server.server_port}"
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
        return False


def _run_cli(args, env_extra, base_url):
    """Run the narration CLI in a genuinely separate process."""
    import os as _os

    env = dict(_os.environ)
    env.update(env_extra)
    # The fixture is a Python script, so the transport is an argv list.
    env["CONTENTOPS_MINIMAX_CLI"] = json.dumps(
        [sys.executable, str(ROOT / "tests" / "fixtures" / "fake_mmx_cli.py")]
    )
    env["CONTENTOPS_MINIMAX_BASE_URL"] = base_url
    env["MINIMAX_SUBSCRIPTION_KEY"] = "sk-cp-TESTONLY0000"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "scripts"), str(ROOT / "src"), env.get("PYTHONPATH", "")]
    )
    return hidden_run(
        [python_executable(), "scripts/synthesize_narration.py", *args],
        cwd=str(ROOT), env=env, timeout=900,
    )


def test_retry_rule_survives_a_process_boundary():
    """Three separate processes: identical inputs must still be refused.

    This is the bug an in-memory fingerprint could not catch. Each CLI run is a
    fresh interpreter with a fresh provider, so only the durable attempt record
    carries the previous fingerprint across.
    """
    if not HAVE_FFMPEG:
        print("[skip] 75. ffmpeg not installed")
        return

    from contentops.media.attempts import find_attempt_records

    with tempfile.TemporaryDirectory() as td:
        work = Path(td).resolve()
        base = ["--text", "你好，这是测试。", "--language", "zh",
                "--out-dir", str(work)]

        with _StubBillingServer(_quota(98, 58)) as stub:
            # process 1: the fixture fails, so a FAILED attempt record is written
            first = _run_cli(base, {"FAKE_MMX_FAIL": "1"}, stub.base_url)
            assert first.returncode != 0, (
                "a failing generation must not report success: "
                + ((first.stdout or "") + (first.stderr or ""))[-300:]
            )
            failed = find_attempt_records(work, status="FAILED")
            assert failed, (
                "process 1 must leave a durable FAILED attempt record; stderr="
                + ((first.stdout or "") + (first.stderr or ""))[-300:]
            )
            record_path = str(failed[-1].path_in(work))

            # process 2: new interpreter, same inputs, retry from process 1
            second = _run_cli(
                base + ["--retry-from", record_path,
                        "--retry-reason", "transient failure"],
                {},
                stub.base_url,
            )
            assert second.returncode != 0, "an identical retry must be refused"
            combined = (second.stdout or "") + (second.stderr or "")
            assert "must change a generation input" in combined, combined[-400:]

            # process 3: same record, but a material input changed
            third = _run_cli(
                base + ["--retry-from", record_path,
                        "--retry-reason", "transient failure",
                        "--voice", "Chinese (Mandarin)_Warm_Bestie"],
                {},
                stub.base_url,
            )
            assert third.returncode == 0, (
                "a retry with a changed voice must be accepted: "
                + ((third.stdout or "") + (third.stderr or ""))[-400:]
            )
            payload = json.loads(third.stdout)
            assert payload["attempt"] == 2, payload.get("attempt")
            assert payload["provider_request_made"] is True
    print("[ok] 75. the retry rule is enforced across three separate processes")


def test_retry_reference_is_validated_inside_a_separate_process():
    """A bad retry reference fails in a fresh interpreter too."""
    if not HAVE_FFMPEG:
        print("[skip] 76. ffmpeg not installed")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td).resolve()
        with _StubBillingServer(_quota(98, 58)) as stub:
            result = _run_cli(
                ["--text", "你好。", "--language", "zh", "--out-dir", str(work),
                 "--retry-from", str(work / "missing.json"),
                 "--retry-reason", "r"],
                {}, stub.base_url,
            )
            assert result.returncode != 0
            combined = (result.stdout or "") + (result.stderr or "")
            assert "retry record not found" in combined, combined[-300:]
    print("[ok] 76. a retry reference to a missing record fails in a separate process too")
def test_binding_gate_and_child_share_one_credential():
    """The key the gate authorises must be the key the child receives."""
    import os as _os

    if not HAVE_FFMPEG:
        print("[skip] 77. ffmpeg not installed")
        return

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        report = work / "credential-report.json"
        authorised = "sk-cp-AUTHORISED-KEY"
        ambient = "sk-api-AMBIENT-DIFFERENT"

        previous_env = _os.environ.get("MINIMAX_API_KEY")
        previous_report = _os.environ.get("FAKE_MMX_CREDENTIAL_REPORT")
        _os.environ["MINIMAX_API_KEY"] = ambient
        _os.environ["FAKE_MMX_CREDENTIAL_REPORT"] = str(report)
        try:
            resolved = _resolved(authorised, source="MINIMAX_SUBSCRIPTION_KEY_ENV")
            guard = guard_with(credential=authorised)
            provider = _fixture_provider(work, guard=guard, credential=resolved)
            provider.synthesize_speech(
                SpeechRequest(display_text="你好，这是测试。", language="zh")
            )
        finally:
            for name, value in (
                ("MINIMAX_API_KEY", previous_env),
                ("FAKE_MMX_CREDENTIAL_REPORT", previous_report),
            ):
                if value is None:
                    _os.environ.pop(name, None)
                else:
                    _os.environ[name] = value

        assert report.is_file(), "the fixture must report which credential it resolved"
        observed = json.loads(report.read_text(encoding="utf-8"))
        # The child saw MINIMAX_API_KEY_ENV, never MMX_CONFIG: the authorised
        # key replaced the ambient one instead of being overridden by it.
        assert observed["credential_source"] == "MINIMAX_API_KEY_ENV", observed
        assert observed["credential_class"] == "SUBSCRIPTION", observed
        # The value itself is never written anywhere.
        assert authorised not in report.read_text(encoding="utf-8")
        assert ambient not in report.read_text(encoding="utf-8")
    print("[ok] 77. gate and child transport share one authorised credential")


def test_unbound_provider_refuses_to_generate():
    """No bound credential means no generation, not an ambient fallback."""
    if not HAVE_FFMPEG:
        print("[skip] 78. ffmpeg not installed")
        return
    from contentops.media.credentials import CredentialBindingError
    from contentops.media.minimax_speech import MiniMaxMPlanProvider

    with tempfile.TemporaryDirectory() as td:
        provider = MiniMaxMPlanProvider(
            guard=guard_with(), work_dir=Path(td), cli=FIXTURE_CLI
        )
        try:
            provider.synthesize_speech(
                SpeechRequest(display_text="你好，这是测试。", language="zh")
            )
        except CredentialBindingError as exc:
            assert "Refusing to" in str(exc)
            assert "credential" in str(exc)
            print("[ok] 78. an unbound provider refuses to generate")
            return
        raise AssertionError("an unbound provider generated anyway")


def _recording_cli(work: Path):
    """A CLI that records the fact it was launched, then succeeds."""
    marker = work / "child-was-launched"
    recorder = work / "recorder.py"
    recorder.write_text(
        "import pathlib, sys\n"
        "pathlib.Path(r" + str(marker) + ").write_text('launched')\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    return [sys.executable, str(recorder)], marker


def test_non_subscription_credentials_block_before_child_launch():
    """PAYG, UNKNOWN and ABSENT must stop the run before any child starts."""
    if not HAVE_FFMPEG:
        print("[skip] 79. ffmpeg not installed")
        return
    for key in ("sk-api-PAYG-KEY", "sk-UNKNOWN-KEY", "", "   "):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            cli, marker = _recording_cli(work)
            resolved = _resolved(key, source="MINIMAX_SUBSCRIPTION_KEY_ENV")
            try:
                provider = _fixture_provider(work, credential=resolved, cli=cli)
                provider.synthesize_speech(
                    SpeechRequest(display_text="你好。", language="zh")
                )
            except Exception:
                # BillingBlocked for PAYG/UNKNOWN, CredentialBindingError for
                # ABSENT. Either way the run stops. What matters is below.
                pass
            assert not marker.exists(), (
                f"credential class {resolved.credential_class!r} launched the child"
            )
    print("[ok] 79. PAYG, UNKNOWN and ABSENT never reach the provider child")


def test_absent_credential_fails_closed_even_with_a_permissive_gate():
    """If the gate were bypassed, the binding itself must still stop the child."""
    if not HAVE_FFMPEG:
        print("[skip] 80b. ffmpeg not installed")
        return
    from contentops.media.credentials import CredentialBindingError

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        cli, marker = _recording_cli(work)
        provider = _fixture_provider(
            work, credential=_resolved("", source="NONE"), cli=cli
        )
        # Construction succeeds on purpose, so that --health still runs on an
        # unauthenticated host. The refusal happens when a child environment is
        # actually requested, which is the moment it would matter.
        assert provider._binding.is_bound is False
        try:
            provider._binding.require_env()
        except CredentialBindingError as exc:
            assert "Refusing to" in str(exc)
        else:
            raise AssertionError("an absent credential produced a usable child env")

        # And end to end: whatever the reason, no child is ever launched.
        try:
            provider.synthesize_speech(
                SpeechRequest(display_text="你好。", language="zh")
            )
        except Exception:
            pass
        assert not marker.exists(), "an unbound child was launched"
    print("[ok] 80b. an absent credential cannot produce a working transport")


def test_payg_credential_is_blocked_by_the_gate():
    """A PAYG key is refused by BillingGuard, independently of binding."""
    from contentops.media.billing_guard import BillingGuard as _BG

    guard = _BG(base_url="https://x.invalid", credential="sk-api-PAYG")
    result = guard.evaluate(modality="speech")
    assert result.verdict == BLOCKED_BILLING_SOURCE_UNCERTAIN
    assert any("credential class" in r for r in result.reasons)
    print("[ok] 80. a PAYG credential is refused by the billing gate")


def test_credential_value_never_leaves_the_resolver():
    """repr, str and safe metadata must all omit the secret."""
    sentinel = "sk-cp-SUPERSECRET_TEST_VALUE"
    resolved = _resolved(sentinel, source="MINIMAX_SUBSCRIPTION_KEY_ENV")
    assert sentinel not in repr(resolved)
    assert sentinel not in str(resolved)
    assert sentinel not in json.dumps(resolved.safe_metadata())
    assert resolved.safe_metadata() == {
        "credential_class": "SUBSCRIPTION",
        "credential_source": "MINIMAX_SUBSCRIPTION_KEY_ENV",
    }
    print("[ok] 81. the credential value never appears in repr, str or metadata")


def test_secret_sentinel_absent_from_every_persisted_output():
    """Success, failure, retry, receipt, sidecar, attempts and reuse log."""
    if not HAVE_FFMPEG:
        print("[skip] 82. ffmpeg not installed")
        return
    import os as _os

    from contentops.media.attempts import read_reuse_events

    sentinel = "sk-cp-SUPERSECRET_TEST_VALUE"
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        resolved = _resolved(sentinel, source="MINIMAX_SUBSCRIPTION_KEY_ENV")
        guard = guard_with(credential=sentinel)
        provider = _fixture_provider(work, guard=guard, credential=resolved)
        request = SpeechRequest(display_text="你好，这是测试。", language="zh")

        first = provider.synthesize_speech(request)          # success path
        second = provider.synthesize_speech(request)         # cache reuse path
        serialised = receipt_to_dict(first.receipt)
        rendered = json.dumps(serialised, ensure_ascii=False)

        # failure + retry evidence
        previous = _os.environ.get("FAKE_MMX_FAIL")
        _os.environ["FAKE_MMX_FAIL"] = "1"
        try:
            failing = _fixture_provider(
                work,
                guard=guard_with(credential=sentinel),
                credential=resolved,
            )
            try:
                failing.synthesize_speech(
                    SpeechRequest(display_text="另一句。", language="zh")
                )
            except RuntimeError as exc:
                assert sentinel not in str(exc)
        finally:
            if previous is None:
                _os.environ.pop("FAKE_MMX_FAIL", None)
            else:
                _os.environ["FAKE_MMX_FAIL"] = previous

        surfaces = {
            "receipt": rendered,
            "reuse_events": json.dumps(read_reuse_events(work), ensure_ascii=False),
        }
        for path in work.rglob("*"):
            if path.is_file() and path.suffix in {".json", ".jsonl"}:
                surfaces[path.name] = path.read_text(encoding="utf-8", errors="replace")

        for name, text in surfaces.items():
            assert sentinel not in text, f"the secret leaked into {name}"

        assert first.reused is False and second.reused is True
    print("[ok] 82. the secret sentinel appears in no persisted or serialised output")


def test_fresh_provider_restores_receipt_state_on_cache_hit():
    """A brand new provider that hits the cache must still answer receipt()."""
    if not HAVE_FFMPEG:
        print("[skip] 83. ffmpeg not installed")
        return
    from contentops.media.attempts import find_attempt_records  # noqa: F401

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        request = SpeechRequest(display_text="你好，这是测试。", language="zh")

        provider_a = _fixture_provider(work)
        first = provider_a.synthesize_speech(request)
        sidecar = sidecar_for(Path(first.asset.normalized_path))
        before = sidecar.read_bytes()

        # A completely new provider whose billing transport explodes on contact.
        def exploding(url, credential):
            raise AssertionError(f"billing transport was called: {url}")

        provider_b = _fixture_provider(
            work,
            guard=BillingGuard(
                base_url="https://example.invalid",
                credential="sk-cp-TESTONLY0000000000",
                http_get_json=exploding,
            ),
        )
        assert provider_b._receipts == []

        second = provider_b.synthesize_speech(request)
        assert second.reused is True

        # receipt() must work on the fresh provider, both forms.
        latest = provider_b.receipt()
        by_asset = provider_b.receipt(second.asset)
        assert latest.fingerprint == first.receipt.fingerprint
        assert by_asset.fingerprint == first.receipt.fingerprint
        assert latest.raw_sha256 == first.receipt.raw_sha256
        assert latest.attempt == 1

        # The immutable generation receipt is untouched.
        assert sidecar.read_bytes() == before

        # Repeated reuse must not grow the in-memory list without bound.
        for _ in range(3):
            provider_b.synthesize_speech(request)
        matching = [
            r for r in provider_b._receipts
            if r.fingerprint == first.receipt.fingerprint
        ]
        assert len(matching) == 1, f"duplicate receipts: {len(matching)}"
    print("[ok] 83. a fresh provider restores receipt state from the cache, sidecar unchanged")


def test_fresh_provider_cache_hit_makes_no_billing_or_network_call():
    if not HAVE_FFMPEG:
        print("[skip] 84. ffmpeg not installed")
        return

    def exploding(url, credential):
        raise AssertionError(f"billing transport was called: {url}")

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        request = SpeechRequest(display_text="你好，这是测试。", language="zh")
        _fixture_provider(work).synthesize_speech(request)

        guard = BillingGuard(
            base_url="https://example.invalid",
            credential="sk-cp-TESTONLY0000000000",
            http_get_json=exploding,
        )
        fresh = _fixture_provider(work, guard=guard)
        outcome = fresh.synthesize_speech(request)
        assert outcome.reused is True
        assert guard.call_count == 0
    print("[ok] 84. a fresh-provider cache hit costs zero billing and zero network")


TESTS = [
    test_binding_gate_and_child_share_one_credential,
    test_unbound_provider_refuses_to_generate,
    test_non_subscription_credentials_block_before_child_launch,
    test_absent_credential_fails_closed_even_with_a_permissive_gate,
    test_payg_credential_is_blocked_by_the_gate,
    test_credential_value_never_leaves_the_resolver,
    test_secret_sentinel_absent_from_every_persisted_output,
    test_fresh_provider_restores_receipt_state_on_cache_hit,
    test_fresh_provider_cache_hit_makes_no_billing_or_network_call,
    test_credential_classification,
    test_non_subscription_credential_is_refused,
    test_guard_never_exposes_the_credential,
    test_guard_allows_only_safe_state,
    test_guard_blocks_each_nonzero_paid_field,
    test_guard_fails_closed_on_unreadable_balance,
    test_guard_fails_closed_on_schema_change,
    test_guard_blocks_on_exhausted_or_unreadable_plan_quota,
    test_require_safe_raises_with_verdict,
    test_balance_endpoint_is_declared_undocumented,
    test_balance_endpoint_lives_in_exactly_one_module,
    test_easel_compatibility_recorded_as_incompatible,
    test_pinned_easel_requires_group_id,
    test_lexicon_uses_plain_text_expansion_only,
    test_lexicon_keeps_display_and_spoken_apart,
    test_lexicon_covers_the_regression_vocabulary,
    test_lexicon_version_enters_the_fingerprint,
    test_english_lexicon_is_empty_without_evidence,
    test_fingerprint_changes_with_every_material_input,
    test_fingerprint_is_stable_for_identical_input,
    test_retry_cap_is_two,
    test_second_attempt_requires_a_named_reason,
    test_receipt_records_credential_class_not_value,
    test_asr_is_a_detector_and_never_approves,
    test_asr_detects_missing_and_duplicated_tokens,
    test_fallback_is_explicit_and_never_silent,
    test_duration_policy_prefers_shortest_legal_value,
    test_duration_policy_uses_minimum_when_above_three,
    test_duration_policy_rejects_unsupported_short_request,
    test_duration_policy_demands_justification_above_minimum,
    test_verified_h3_duration_ranges,
    test_duration_policy_does_not_touch_production,
    test_normalisation_moves_level_toward_target,
    test_normalisation_is_not_applied_twice,
    test_technical_qc_rejects_silence_and_accepts_tone,
    test_technical_qc_rejects_missing_file,
    test_measure_audio_reports_format,
    test_provider_module_makes_no_network_call_at_import,
    test_subprocess_policy_covers_the_new_modules,
    test_cli_entrypoint_help_runs,
    test_transport_flattens_newlines_before_calling_the_cli,
    test_transport_never_uses_the_rejected_pause_marker,
    test_verify_output_rejects_missing_stale_and_trivial_files,
    test_lexicon_covers_the_narration_asr_findings,
    test_asr_coverage_is_meaningful_for_chinese,
    test_asr_reconciles_chinese_numerals_with_digits,
    test_loudness_is_measured_not_predicted,
    test_modality_windows_follow_verified_mplan_behaviour,
    test_unknown_modality_is_blocked_not_defaulted,
    test_weekly_only_never_implies_all_modalities_safe,
    test_owed_amount_is_required_and_must_be_zero,
    test_every_required_balance_field_fails_closed_on_schema_change,
    test_receipt_before_any_synthesis_raises,
    test_receipt_is_persisted_and_retrievable_after_synthesis,
    test_reused_asset_carries_truthful_provenance,
    test_cache_is_rejected_when_the_sidecar_disagrees,
    test_cache_reuse_makes_no_billing_or_network_call,
    test_force_bypasses_the_cache,
    test_retry_requires_a_named_reason,
    test_retry_with_identical_fingerprint_is_refused,
    test_retry_with_changed_input_is_accepted,
    test_asr_multiplicity_behaviour,
    test_asr_coverage_is_multiset_recall,
    test_retry_without_a_durable_record_is_refused,
    test_invalid_retry_records_are_refused,
    test_retry_refused_before_any_billing_or_provider_call,
    test_generation_sidecar_is_immutable_on_cache_hit,
    test_reused_receipt_carries_the_original_generation_evidence,
    test_incomplete_sidecar_is_a_cache_miss,
    test_sidecar_completeness_helper_is_strict,
    test_receipt_records_preflight_verdict_not_post_state,
    test_authorize_returns_the_full_verdict,
    test_generation_makes_one_balance_read_not_a_second_authorisation,
    test_previous_fixes_still_hold,
    test_retry_rule_survives_a_process_boundary,
    test_retry_reference_is_validated_inside_a_separate_process,
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
    print(f"All {len(TESTS)} M2 speech regression tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())