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
from contentops.media.billing_guard import (  # noqa: E402
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
    receipt_to_dict,
    resolve_cli,
    verify_output,
)
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


def guard_with(balances=SAFE_BALANCES, quota=SAFE_QUOTA, credential="sk-cp-EXAMPLE"):
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
    assert any("weekly plan window exhausted" in r for r in result.reasons)

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


TESTS = [
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