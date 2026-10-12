"""Regression tests for the native-credential rounds. Issue #34.

Everything here runs offline. The provider is a fake transport; every decision
function is pure; no credential is real and nothing is charged.

The invariants that matter most, and why:

- the credential in the ``Authorization`` header is the credential that was
  passed -- the whole failure these rounds correct was a receipt claiming one
  credential while the transport used another;
- the two routes cannot use each other's keys -- a PAYG key must be refused by
  the M Plan gate, and the activation gate must refuse a non-PAYG class;
- this round's single-use flags are independent of the historical ones -- the
  earlier recovery being consumed must not block the new authorisation, and the
  new authorisation must not resurrect the old one;
- the append-only activation history keeps every historical entry.
"""

from __future__ import annotations

import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.cash_activation_recovery import (  # noqa: E402
    ACTIVATION_CHARGE_NOT_BOUNDED,
    EXPOSED_PAYG_KEY_NOT_ROTATED,
    EXPOSED_PAYG_KEY_FINGERPRINTS,
    RECOVERY_ALREADY_USED,
)
from contentops.media.credentials import (  # noqa: E402
    CREDENTIAL_PAYG,
    CREDENTIAL_SUBSCRIPTION,
)
from contentops.media.minimax_native_tts import (  # noqa: E402
    MINIMAX_CN_HOST,
    NativeTtsRefusal,
    REFUSAL_PROVIDER_STATUS,
)
from contentops.media.native_rounds import (  # noqa: E402
    FOUNDER_AUTHORISED_NATIVE_FIRST_ACTIVATION,
    MPLAN_NARRATION_ROUTE,
    NATIVE_FIRST_ACTIVATION_CEILING_CNY,
    PAYG_ACTIVATION_ROUTE,
    append_activation_history,
    build_spoken_request,
    canonical_blob_sha256,
    classify_mplan_only,
    classify_payg_outcome,
    decide_mplan_native,
    decide_payg_native_activation,
    delta_money,
    run_native_activation_once,
)

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


VOICE_HASH = "7271d9c80c88821a6a09ed43328619d0ee08c3f2b2449237fe2c31f6899abeef"
ACTIVATION_TEXT = "这是一段用于首次激活的最短自然中文语音样本。"
TEST_KEY = "sk-api-TEST-KEY-000-AAAAAAAAAAAAAAAA"
SUB_KEY = "sk-cp-TEST-KEY-111-BBBBBBBBBBBBBBBB"


class FakeTransport:
    def __init__(self, responder):
        self.responder = responder
        self.calls = []

    def __call__(self, url, headers, body, timeout_s):
        self.calls.append({"url": url, "headers": dict(headers), "body": json.loads(body)})
        return self.responder(url, headers, body)


def _ok_envelope(audio_hex: str = "00" * 64) -> bytes:
    return json.dumps(
        {
            "data": {"audio": audio_hex, "status": 2},
            "extra_info": {"usage_characters": 44, "audio_format": "wav"},
            "trace_id": "trace-rounds",
            "base_resp": {"status_code": 0, "status_msg": "success"},
        }
    ).encode()


def _balances(cash="10.00", voucher="15.00", credit="0.00", owed="0.00"):
    return {
        "balances": {
            "cash_balance": cash,
            "voucher_balance": voucher,
            "credit_balance": credit,
            "owed_amount": owed,
            "available_amount": str(Decimal(cash) + Decimal(voucher)),
        },
        "verdict": "BLOCKED_BILLING_SOURCE_UNCERTAIN",
        "quota": None,
        "reasons": [],
    }


def _decide_payg(**overrides):
    params = dict(
        payg_key_fingerprint="deadbeef0000",
        payg_key_is_payg_class=True,
        voice_id_hash=VOICE_HASH,
        voice_exists=True,
        voice_window_remaining_s=160 * 3600,
        cash_balance=10.00,
        credit_balance=0.00,
        voucher_balance=15.00,
        owed_amount=0.00,
        billable_character_count=44,
        previous_payg_refusal=True,
        previous_subscription_refusal=True,
        native_round_used=False,
        prior_recovery_used=True,
        exception_granted=False,
        exception_consumed=False,
    )
    params.update(overrides)
    return decide_payg_native_activation(**params)


# --- A. credential binding -----------------------------------------------------


@test
def test_the_two_routes_send_their_own_credentials_in_their_own_headers():
    """The exact defect this round corrects, pinned as a test.

    If both keys ever end up in the same header -- or if the transport ever
    substitutes one for the other -- these two calls stop disagreeing.
    """
    payload = build_spoken_request(
        display_text=ACTIVATION_TEXT, voice_id="founder_primary_v1", model="speech-2.8-hd"
    ).payload
    from contentops.media.minimax_native_tts import send_t2a_once

    t1 = FakeTransport(lambda *_: (200, _ok_envelope()))
    t2 = FakeTransport(lambda *_: (200, _ok_envelope()))
    send_t2a_once(payload=payload, credential=TEST_KEY, transport=t1)
    send_t2a_once(payload=payload, credential=SUB_KEY, transport=t2)
    assert t1.calls[0]["headers"]["Authorization"] == "Bearer " + TEST_KEY
    assert t2.calls[0]["headers"]["Authorization"] == "Bearer " + SUB_KEY
    assert t1.calls[0]["headers"]["Authorization"] != t2.calls[0]["headers"]["Authorization"]
    print("[ok] 1. each route's request carries exactly its own credential")


@test
def test_both_routes_target_the_same_documented_cn_host_and_path():
    payload = build_spoken_request(
        display_text=ACTIVATION_TEXT, voice_id="founder_primary_v1", model="speech-2.8-hd"
    ).payload
    from contentops.media.minimax_native_tts import send_t2a_once

    for key in (TEST_KEY, SUB_KEY):
        transport = FakeTransport(lambda *_: (200, _ok_envelope()))
        send_t2a_once(payload=payload, credential=key, transport=transport)
        assert transport.calls[0]["url"] == MINIMAX_CN_HOST + "/v1/t2a_v2"
    print("[ok] 2. both routes address the documented CN host and path")


# --- B. PAYG activation gate ---------------------------------------------------


@test
def test_the_new_authorisation_is_independent_of_the_consumed_recovery():
    """prior recovery used must be RECORDED, not blocking.

    The Founder granted a new, independent single-use authorisation. The old
    one being consumed is a historical fact; if it blocked, the new grant could
    never execute, and if the new one silently reused the old flag, the old
    record would be rewritten.
    """
    decision = _decide_payg(
        prior_recovery_used=True,
        native_round_used=False,
        exception_granted=True,
        payg_key_fingerprint=EXPOSED_PAYG_KEY_FINGERPRINTS[0],
    )
    assert decision["authorised"] is True, decision["reasons"]
    assert decision["route"] == PAYG_ACTIVATION_ROUTE
    assert decision["authorisation"] == FOUNDER_AUTHORISED_NATIVE_FIRST_ACTIVATION
    assert decision["prior_recovery_used"] is True
    print("[ok] 3. the consumed historical recovery does not block the new grant")


@test
def test_this_rounds_single_use_flag_blocks_a_replay():
    decision = _decide_payg(
        native_round_used=True,
        exception_granted=True,
        payg_key_fingerprint=EXPOSED_PAYG_KEY_FINGERPRINTS[0],
    )
    assert decision["authorised"] is False
    assert RECOVERY_ALREADY_USED in decision["refusals"], decision["refusals"]
    print("[ok] 4. once used, this round's authorisation refuses replay")


@test
def test_the_exposed_key_is_still_gated_without_the_new_exception():
    decision = _decide_payg(
        payg_key_fingerprint=EXPOSED_PAYG_KEY_FINGERPRINTS[0],
        exception_granted=False,
    )
    assert decision["authorised"] is False
    assert EXPOSED_PAYG_KEY_NOT_ROTATED in decision["refusals"]
    print("[ok] 5. the exposed key stays gated; the new exception is required")


@test
def test_a_consumed_exception_blocks_and_a_wrong_scope_blocks():
    consumed = _decide_payg(
        payg_key_fingerprint=EXPOSED_PAYG_KEY_FINGERPRINTS[0],
        exception_granted=True,
        exception_consumed=True,
    )
    assert consumed["authorised"] is False
    other_voice = _decide_payg(
        payg_key_fingerprint=EXPOSED_PAYG_KEY_FINGERPRINTS[0],
        exception_granted=True,
        voice_id_hash="0" * 64,
    )
    assert other_voice["authorised"] is False
    print("[ok] 6. a consumed exception and a foreign voice both refuse")


@test
def test_a_subscription_class_or_a_large_text_or_a_dry_account_all_refuse():
    wrong_class = _decide_payg(payg_key_is_payg_class=False)
    assert wrong_class["authorised"] is False
    too_long = _decide_payg(billable_character_count=100000)
    assert too_long["authorised"] is False
    assert ACTIVATION_CHARGE_NOT_BOUNDED in too_long["refusals"]
    no_cash = _decide_payg(cash_balance=1.00)
    assert no_cash["authorised"] is False
    credit_pack = _decide_payg(credit_balance=5.0)
    assert credit_pack["authorised"] is False
    print("[ok] 7. wrong key class, oversized text, thin cash and a Credit Pack all refuse")


@test
def test_the_projection_is_9_9154_under_the_10_00_ceiling():
    decision = _decide_payg()
    assert decision["projected_total_cny"] == "9.9154", decision["projected_total_cny"]
    assert decision["ceiling_cny"] == "10.00"
    assert Decimal(decision["projected_total_cny"]) <= NATIVE_FIRST_ACTIVATION_CEILING_CNY
    print("[ok] 8. the projected total is CNY 9.9154 against the CNY 10.00 ceiling")


# --- C. M Plan gate ------------------------------------------------------------


@test
def test_the_mplan_gate_refuses_a_payg_key_and_unproven_billing():
    payg = decide_mplan_native(
        credential_class=CREDENTIAL_PAYG,
        credential_source="MINIMAX_CLONE_KEY_ENV",
        guard_verdict="BLOCKED_BILLING_SOURCE_UNCERTAIN",
        guard_reasons=["credential class is PAYG"],
        quota={"interval_remaining_percent": 15, "weekly_remaining_percent": 51},
    )
    assert payg["authorised"] is False
    assert "MPLAN_REQUIRES_SUBSCRIPTION_KEY" in payg["refusals"]
    print("[ok] 9. the M Plan gate can never be satisfied by a PAYG credential")


@test
def test_the_mplan_gate_passes_only_with_safe_plan_billing_and_live_quota():
    good = decide_mplan_native(
        credential_class=CREDENTIAL_SUBSCRIPTION,
        credential_source="MMX_CONFIG",
        guard_verdict="SAFE_INCLUDED_PLAN",
        quota={"interval_remaining_percent": 15, "weekly_remaining_percent": 51},
    )
    assert good["authorised"] is True, good["reasons"]
    assert good["route"] == MPLAN_NARRATION_ROUTE
    exhausted = decide_mplan_native(
        credential_class=CREDENTIAL_SUBSCRIPTION,
        credential_source="MMX_CONFIG",
        guard_verdict="SAFE_INCLUDED_PLAN",
        quota={"interval_remaining_percent": 0, "weekly_remaining_percent": 51},
    )
    assert exhausted["authorised"] is False
    unreadable = decide_mplan_native(
        credential_class=CREDENTIAL_SUBSCRIPTION,
        credential_source="MMX_CONFIG",
        guard_verdict="SAFE_INCLUDED_PLAN",
        quota=None,
    )
    assert unreadable["authorised"] is False
    print("[ok] 10. the M Plan gate needs safe billing and live quota")


# --- D. classification ---------------------------------------------------------


def _delta(before, after):
    return delta_money(before, after)


@test
def test_plan_only_verification_accepts_a_quota_delta_or_a_clean_exclusion_chain():
    before = _balances(cash="0.10")
    after_same = _balances(cash="0.10")
    quota_delta = classify_mplan_only(
        quota_before={"interval_remaining_percent": 15, "weekly_remaining_percent": 51},
        quota_after={"interval_remaining_percent": 14, "weekly_remaining_percent": 51},
        deltas=_delta(before, after_same),
    )
    assert quota_delta["verified"] is True
    assert quota_delta["basis"] == "QUOTA_DELTA"

    flat_quota = classify_mplan_only(
        quota_before={"interval_remaining_percent": 15, "weekly_remaining_percent": 51},
        quota_after={"interval_remaining_percent": 15, "weekly_remaining_percent": 51},
        deltas=_delta(before, after_same),
    )
    assert flat_quota["verified"] is True, "flat quota plus a clean chain is not failure"
    assert flat_quota["basis"] == "EXCLUSION_CHAIN"
    print("[ok] 11. quota delta and the exclusion chain both verify plan-only usage")


@test
def test_any_paid_fund_movement_refuses_plan_only_verification():
    before = _balances(cash="0.10")
    after = _balances(cash="0.09")
    moved = classify_mplan_only(
        quota_before={"interval_remaining_percent": 15, "weekly_remaining_percent": 51},
        quota_after={"interval_remaining_percent": 14, "weekly_remaining_percent": 51},
        deltas=_delta(before, after),
    )
    assert moved["verified"] is False
    assert moved["status"] == "MPLAN_CHARGED_PAID_FUNDS"
    credit = _balances(cash="0.10", credit="0.005")
    credit_moved = classify_mplan_only(
        quota_before=None,
        quota_after=None,
        deltas=_delta(before, credit),
    )
    assert credit_moved["verified"] is False
    print("[ok] 12. any cash, voucher, credit or debt movement refuses plan-only")


@test
def test_inconclusive_conditions_leave_the_verification_pending():
    # Unreadable credit + no quota delta + no movement: cannot prove, must not claim.
    d = _delta(_balances(cash="0.10"), _balances(cash="0.10"))
    d["credit_balance"] = {"delta": None, "error": "field unreadable"}
    pending = classify_mplan_only(
        quota_before={"interval_remaining_percent": 15, "weekly_remaining_percent": 51},
        quota_after={"interval_remaining_percent": 15, "weekly_remaining_percent": 51},
        deltas=d,
    )
    assert pending["verified"] is False
    assert pending["status"] == "M_PLAN_ONLY_VERIFICATION_PENDING"
    print("[ok] 13. an unprovable case stays PENDING instead of claiming success")


@test
def test_payg_outcome_semantics():
    assert classify_payg_outcome(
        audio_ok=True, cash_debit=Decimal("9.9154"), anomalies=[]
    ) == "SUCCESS_ACTIVATED_CASH"
    assert classify_payg_outcome(
        audio_ok=True, cash_debit=None, anomalies=[]
    ) == "TTS_SUCCESS_BILLING_UNVERIFIED"
    assert classify_payg_outcome(
        audio_ok=False, cash_debit=None, anomalies=[]
    ) == "ACTIVATION_FAILED"
    assert classify_payg_outcome(
        audio_ok=True, cash_debit=Decimal("9.9154"), anomalies=["cash_debit_over_ceiling"]
    ) == "SEVERE_ANOMALY"
    print("[ok] 14. audio without a measured cash debit is never called activation")


# --- E. runner + history + repo state ------------------------------------------


@test
def test_the_runner_preserves_a_provider_refusal_as_separate_fields():
    payload_spec = build_spoken_request(
        display_text=ACTIVATION_TEXT, voice_id="founder_primary_v1", model="speech-2.8-hd"
    )
    responder = lambda *_: (  # noqa: E731
        200,
        json.dumps(
            {
                "trace_id": "trace-refusal",
                "base_resp": {"status_code": 1008, "status_msg": "insufficient balance"},
            }
        ).encode(),
    )
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        receipt: dict = {"attempt_id": "test-attempt"}
        try:
            run_native_activation_once(
                spec=payload_spec,
                credential=TEST_KEY,
                credential_class=CREDENTIAL_PAYG,
                credential_source="TEST",
                base_url=MINIMAX_CN_HOST,
                attempt_id="test-attempt",
                work_dir=tmp / "work",
                diagnostics_dir=tmp / "diag",
                receipt=receipt,
                transport=FakeTransport(responder),
            )
        except NativeTtsRefusal as exc:
            assert exc.code == REFUSAL_PROVIDER_STATUS
            assert exc.provider_status_code == 1008
            assert exc.trace_id == "trace-refusal"
        else:
            raise AssertionError("a 1008 must raise")
        assert receipt["request_transmitted"] is True
        diag = tmp / "diag" / "tts-test-attempt.json"
        assert diag.is_file(), "the raw provider response must be preserved privately"
        blob = diag.read_text(encoding="utf-8")
        assert "insufficient balance" in blob
        assert "trace-refusal" in blob
        assert "Bearer" not in blob and TEST_KEY not in blob
    print("[ok] 15. a refusal keeps its code, message and trace id; raw JSON is private")


@test
def test_history_append_preserves_every_existing_entry_and_refuses_secrets():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "history.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "contentops.voice-activation-history/v1",
                    "attempts": [{"attempt_id": "old-attempt", "outcome": "ACTIVATION_FAILED"}],
                }
            ),
            encoding="utf-8",
        )
        append_activation_history(path, "new-attempt", {"outcome": "REFUSED_PRECHECK"})
        payload = json.loads(path.read_text(encoding="utf-8"))
        ids = [a["attempt_id"] for a in payload["attempts"]]
        assert ids == ["old-attempt", "new-attempt"], ids
        try:
            # Built by concatenation so this test file itself never trips the
            # repository's own secret scanner (check_docs.py runs on tracked
            # files, and a literal credential-shaped string here would fail CI
            # for the exact pattern this assertion exists to defend).
            append_activation_history(
                path,
                "bad-attempt",
                {"note": "Bear" + "er " + "sk-cp-" + "REAL-LOOKING-SECRET"},
            )
        except SystemExit:
            pass
        else:
            raise AssertionError("history must refuse credential-shaped content")
    print("[ok] 16. history is append-only and refuses credential-shaped values")


@test
def test_the_tracked_history_still_contains_every_historical_attempt():
    """The three historical attempts must survive this round unmodified."""
    history = ROOT / "projects/easel-enhanced-golden/receipts/founder-voice-activation-history.json"
    payload = json.loads(history.read_text(encoding="utf-8"))
    ids = {a["attempt_id"] for a in payload["attempts"]}
    for historical in (
        "cashact-c1a3a6506bd8",
        "cashact-d0a52a674c78",
        "cashact-d1684414c30b",
        "cashact-d6546f464ce9",
        "cashact-842acaa45a5c",
    ):
        assert historical in ids, f"{historical} disappeared from the append-only history"
    print("[ok] 17. every historical attempt is still recorded")


@test
def test_the_new_scripts_do_not_reintroduce_the_cli_credential_path():
    """Static guard: no CLI, no env-injected credential, in any new script."""
    for name in (
        "execute_payg_first_activation.py",
        "verify_mplan_native.py",
        "generate_golden_native.py",
    ):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        for forbidden in ("child_env_for", "resolve_cli", "MINIMAX_API_KEY", "subprocess"):
            assert forbidden not in source, f"{name} references {forbidden}"
    print("[ok] 18. no new script can fall back to the CLI credential path")


@test
def test_the_locked_narration_digest_matches_the_evidence_lock():
    source = ROOT / "projects/easel-review/script/narration.txt"
    digest = canonical_blob_sha256(source)
    assert digest == "f2de808c9e723f8430acdc44dc374c5791b249250d8bc585a172360a88b9542a", digest
    lock = json.loads(
        (ROOT / "projects/easel-enhanced-golden/evidence/evidence-lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert lock["narration_text_sha256"] == digest
    print("[ok] 19. the Golden narration text still matches the evidence lock")


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
    print(f"\nAll {total} native-rounds regression tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
