"""``MPLAN_NARRATION_ROUTE`` stage 2: the Golden narration. Issue #34.

One complete narration of the **locked** Golden text, with the cloned voice
``founder_primary_v1``, on the M Plan Subscription Key, through the native CN
HTTP adapter -- one provider request, no retry, no fallback.

It only runs when the cross-key verification receipt records success. The lock
on the text is checked, not trusted: the narration source's canonical Git blob
digest must equal the digest the evidence lock records, or this refuses.

Pipeline, all recorded in an immutable receipt:

- ``PronunciationLexicon`` (plain-text expansion; the M2.0 audited rules)
- two-pass loudness normalisation to the house target
- ASR backcheck (a detector, never a quality judge)
- technical QC gate
- SHA256 of the raw and the normalised audio
- a sidecar receipt next to the asset and a tracked receipt in ``projects/``

The audio itself stays in a gitignored directory: a real person's voice is not
committed, cloned or not.

Dry run by default. ``--execute`` sends the one request.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.clone_route import billable_characters  # noqa: E402
from contentops.media.credentials import (  # noqa: E402
    CREDENTIAL_SUBSCRIPTION,
    load_local_env_file,
    resolve_credential,
)
from contentops.media.minimax_native_tts import (  # noqa: E402
    MINIMAX_CN_HOST,
    NativeTtsRefusal,
    send_t2a_once,
)
from contentops.media.native_rounds import (  # noqa: E402
    MPLAN_NARRATION_ROUTE,
    build_spoken_request,
    canonical_blob_sha256,
    classify_mplan_only,
    decide_mplan_native,
    delta_money,
    read_money,
    write_private_provider_response,
)

VOICE_ID = "founder_primary_v1"
VOICE_ID_HASH = "7271d9c80c88821a6a09ed43328619d0ee08c3f2b2449237fe2c31f6899abeef"
MODEL = "speech-2.8-hd"

NARRATION_SOURCE = ROOT / "projects/easel-review/script/narration.txt"
EVIDENCE_LOCK = ROOT / "projects/easel-enhanced-golden/evidence/evidence-lock.json"
#: The canonical narration digest the evidence lock pins.
LOCKED_NARRATION_SHA256 = (
    "f2de808c9e723f8430acdc44dc374c5791b249250d8bc585a172360a88b9542a"
)

VERIFY_RECEIPT = (
    ROOT
    / "projects/easel-enhanced-golden/receipts"
    / "founder-voice-mplan-crosskey-receipt.json"
)
RECEIPT = (
    ROOT
    / "projects/easel-enhanced-golden/receipts"
    / "founder-voice-golden-narration-receipt.json"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(receipt: Dict[str, Any]) -> None:
    receipt["finished_at"] = _now()
    blob = json.dumps(receipt, ensure_ascii=False)
    for banned in ("Authorization", "Bearer ", "sk-cp-", "sk-api-"):
        if banned in blob:
            raise SystemExit(f"refusing to write a receipt containing {banned!r}")
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {RECEIPT.relative_to(ROOT).as_posix()}")


def _cross_key_verified() -> Optional[Dict[str, Any]]:
    if not VERIFY_RECEIPT.is_file():
        return None
    try:
        payload = json.loads(VERIFY_RECEIPT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not payload.get("m_plan_only_verified"):
        return None
    return {
        "attempt_id": payload.get("attempt_id"),
        "outcome": payload.get("outcome"),
        "basis": (payload.get("verification") or {}).get("basis"),
    }


def _locked_text() -> Dict[str, Any]:
    """The locked Golden narration, verified against the evidence lock."""
    if not NARRATION_SOURCE.is_file():
        raise SystemExit(f"locked narration source missing: {NARRATION_SOURCE}")
    display_text = NARRATION_SOURCE.read_text(encoding="utf-8").strip()
    blob_digest = canonical_blob_sha256(NARRATION_SOURCE)
    lock_digest = None
    if EVIDENCE_LOCK.is_file():
        try:
            lock_digest = json.loads(
                EVIDENCE_LOCK.read_text(encoding="utf-8")
            ).get("narration_text_sha256")
        except (OSError, json.JSONDecodeError):
            lock_digest = None
    if blob_digest is None or blob_digest != LOCKED_NARRATION_SHA256:
        raise SystemExit(
            "refusing: the narration source's canonical digest does not match the "
            f"locked digest (got {blob_digest!r})"
        )
    if lock_digest is not None and lock_digest != blob_digest:
        raise SystemExit(
            "refusing: the evidence lock records a different narration digest than "
            f"the repository holds ({lock_digest!r} vs {blob_digest!r})"
        )
    return {
        "path": str(NARRATION_SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "canonical_blob_sha256": blob_digest,
        "evidence_lock_sha256": lock_digest,
        "display_text": display_text,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="send the one narration request. Without this, "
                             "nothing is transmitted.")
    parser.add_argument("--out-dir", default="outputs/founder-golden",
                        help="gitignored directory for the raw and normalised audio")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    load_local_env_file(ROOT / ".env")
    attempt_id = f"golden-{uuid.uuid4().hex[:12]}"
    sub = resolve_credential()

    verification = _cross_key_verified()
    if verification is None:
        print("REFUSED: the cross-key verification receipt is absent or does not "
              "record m_plan_only_verified=true. Run scripts/verify_mplan_native.py "
              "--execute first. Nothing was sent.")
        return 1

    locked = _locked_text()
    receipt: Dict[str, Any] = {
        "schema": "contentops.golden-narration/v1",
        "stage": "GOLDEN_NARRATION",
        "route": MPLAN_NARRATION_ROUTE,
        "attempt_id": attempt_id,
        "issue": "#34",
        "started_at": _now(),
        "executed": bool(args.execute),
        "voice_id": VOICE_ID,
        "voice_id_hash": VOICE_ID_HASH,
        "model": MODEL,
        "locked_source": {
            "path": locked["path"],
            "canonical_blob_sha256": locked["canonical_blob_sha256"],
            "evidence_lock_sha256": locked["evidence_lock_sha256"],
        },
        "credential_class": sub.credential_class,
        "credential_source": sub.source,
        "payg_key_used_for_this_request": False,
        "host": MINIMAX_CN_HOST,
        "transport": "native_http_cn",
        "cross_key_verification": verification,
        "provider_call_budget": {
            "subscription_tts": 1,
            "asr_transcribe": 1,
            "upload": 0,
            "clone": 0,
            "automatic_retry": 0,
        },
        "notes": [],
    }

    if sub.credential_class != CREDENTIAL_SUBSCRIPTION:
        receipt["outcome"] = "REFUSED_CREDENTIAL_CLASS"
        _write(receipt)
        print(f"REFUSED: the resolved credential is {sub.credential_class}, not a "
              f"Subscription Key. Nothing was sent.")
        return 1

    guard_money = read_money(MINIMAX_CN_HOST, sub.key)
    decision = decide_mplan_native(
        credential_class=sub.credential_class,
        credential_source=sub.source,
        guard_verdict=guard_money["verdict"],
        guard_reasons=guard_money.get("reasons"),
        quota=guard_money["quota"],
    )
    receipt["preflight"] = {
        "billing_verdict": guard_money["verdict"],
        "quota": guard_money["quota"],
        "balances": guard_money["balances"],
        "decision": decision,
    }

    from contentops.media.lexicon import default_zh_lexicon

    lexicon = default_zh_lexicon()
    spec = build_spoken_request(
        display_text=locked["display_text"],
        voice_id=VOICE_ID,
        model=MODEL,
        lexicon=lexicon,
    )
    receipt["narration"] = {
        "display_chars": len(locked["display_text"]),
        "billable_characters": billable_characters(locked["display_text"]),
        "spoken_text_sha256": hashlib.sha256(spec.cli_text.encode()).hexdigest(),
        "lexicon_version": lexicon.version,
        "pronunciation_rule_count": spec.pronunciation_rule_count,
    }

    print(f"=== GOLDEN_NARRATION ({MPLAN_NARRATION_ROUTE}) ===")
    print(f"  attempt_id        : {attempt_id}")
    print(f"  voice / model     : {VOICE_ID} / {MODEL}")
    print(f"  locked text       : {locked['path']} "
          f"(sha256 {locked['canonical_blob_sha256'][:16]}...)")
    print(f"  display chars     : {receipt['narration']['display_chars']} "
          f"({receipt['narration']['billable_characters']} billable)")
    print(f"  subscription key  : {sub.credential_class} ({sub.source})")
    print(f"  transport         : native_http_cn -> {MINIMAX_CN_HOST}/v1/t2a_v2")
    print(f"  BillingGuard      : {guard_money['verdict']}")
    print(f"  M Plan quota      : {guard_money['quota']}")

    if not decision["authorised"]:
        receipt["outcome"] = "REFUSED_PRECHECK"
        _write(receipt)
        print("NOTHING WAS SENT.")
        for reason in decision["reasons"]:
            print(f"  - {reason}")
        return 1

    if not args.execute:
        _write(receipt)
        print("=== DRY RUN. NOTHING WAS SENT. ===")
        return 0

    # --- the one request ------------------------------------------------------
    out_dir = (ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"golden-raw-{attempt_id}.wav"
    normalized_path = out_dir / "golden-narration-founder_primary_v1.wav"

    receipt["request_started_at"] = _now()
    receipt["request_transmitted"] = False
    print("=== ONE REAL GOLDEN NARRATION SYNTHESIS (Subscription Key) ===")
    try:
        result = send_t2a_once(
            payload=spec.payload,
            credential=sub.key,
            base_url=MINIMAX_CN_HOST,
            timeout_s=600,
        )
    except NativeTtsRefusal as refusal:
        receipt["request_transmitted"] = True
        write_private_provider_response(
            ROOT / ".private" / "diagnostics",
            attempt_id,
            host=MINIMAX_CN_HOST,
            route=MPLAN_NARRATION_ROUTE,
            refusal=refusal,
        )
        status = {
            **refusal.structured(),
            "transmitted": True,
            "status_meaning": "provider refused",
        }
        receipt["provider_status"] = status
        receipt["error_taxonomy"] = {
            "http_status": refusal.http_status,
            "provider_status_code": refusal.provider_status_code,
            "provider_status_msg": refusal.provider_status_msg,
            "trace_id": refusal.trace_id,
            "cli_exit_code": None,
            "transport": "native_http_cn",
        }
        receipt["outcome"] = (
            "CROSS_KEY_ACCESS_DENIED"
            if refusal.provider_status_code == 2042
            else "GOLDEN_NARRATION_REFUSED"
        )
        receipt["notes"].append(
            "the provider refused the narration request; no retry, no fallback, "
            "no other Key is substituted"
        )
        _write(receipt)
        print(f"REFUSED: HTTP {refusal.http_status} / provider status "
              f"{refusal.provider_status_code}: {refusal.provider_status_msg}")
        return 1

    receipt["request_transmitted"] = True
    write_private_provider_response(
        ROOT / ".private" / "diagnostics",
        attempt_id,
        host=MINIMAX_CN_HOST,
        route=MPLAN_NARRATION_ROUTE,
        result=result,
    )
    raw_path.write_bytes(result.audio_bytes)

    from contentops.media.asr_backcheck import backcheck_speech
    from contentops.media.audio import (
        NORMALISATION_TARGET_LUFS,
        NORMALISATION_TRUE_PEAK_DB,
        measure_audio,
        normalise_speech,
        technical_qc,
    )
    from contentops.media.fingerprint import sha256_file, speech_fingerprint
    from contentops.media.mplan_identity import PLAN, PRODUCT, PROVIDER_NAME
    from contentops.media.transport import sidecar_for, write_sidecar

    normalisation = normalise_speech(raw_path, normalized_path)
    if not normalisation.get("ok"):
        receipt["outcome"] = "NORMALISATION_FAILED"
        receipt["normalisation"] = normalisation
        _write(receipt)
        print(f"FAILED: loudness normalisation: {normalisation.get('reason')}")
        return 1

    measured = measure_audio(normalized_path)
    expected_duration = max(1.0, len(spec.cli_text) / 6.0)
    technical = technical_qc(
        normalized_path,
        expected_duration_s=expected_duration,
        expected_sample_rate_hz=32000,
    )
    semantic = backcheck_speech(normalized_path, spec.cli_text).as_dict()
    raw_sha = sha256_file(raw_path)
    normalized_sha = sha256_file(normalized_path)
    fingerprint = speech_fingerprint(
        provider=PROVIDER_NAME,
        product=PRODUCT,
        plan=PLAN,
        model=MODEL,
        voice=VOICE_ID,
        spoken_text=spec.cli_text,
        lexicon_component=lexicon.fingerprint_component(),
        speed=None,
        text_normalization=False,
        normalisation_target_lufs=NORMALISATION_TARGET_LUFS,
        normalisation_true_peak_db=NORMALISATION_TRUE_PEAK_DB,
    )

    sidecar_payload = {
        "provider": PROVIDER_NAME,
        "product": PRODUCT,
        "plan": PLAN,
        "billing_mode": "subscription",
        "transport": "native_http_cn",
        "model": MODEL,
        "voice": VOICE_ID,
        "display_text_sha256": hashlib.sha256(
            locked["display_text"].encode()
        ).hexdigest(),
        "spoken_text_sha256": hashlib.sha256(spec.cli_text.encode()).hexdigest(),
        "lexicon_version": lexicon.version,
        "fingerprint": fingerprint,
        "raw_sha256": raw_sha,
        "normalized_sha256": normalized_sha,
        "technical_qc": technical,
        "semantic_qc": semantic,
        "billing_guard_verdict": guard_money["verdict"],
        "attempt": 1,
        "human_review": "PENDING_FOUNDER_REVIEW",
        "production_ready": False,
        "provider_call": True,
        "route": MPLAN_NARRATION_ROUTE,
        "credential_class": sub.credential_class,
        "credential_source": "recorded in the tracked receipt; class only here",
        "trace_id": result.trace_id,
        "usage_characters": result.usage_characters,
        "usage_voice_count": result.usage_voice_count,
        "loudnorm_target": f"I={NORMALISATION_TARGET_LUFS}:TP={NORMALISATION_TRUE_PEAK_DB}",
        "normalisation": {
            "loudness_delta_lu": normalisation.get("loudness_delta_lu"),
            "peak_ceiling_met": normalisation.get("peak_ceiling_met"),
        },
        "narration_locked_source": receipt["locked_source"],
    }
    write_sidecar(sidecar_for(normalized_path), sidecar_payload)

    guard_after = read_money(MINIMAX_CN_HOST, sub.key)
    deltas = delta_money(guard_money, guard_after)
    classification = classify_mplan_only(
        quota_before=guard_money["quota"],
        quota_after=guard_after["quota"],
        deltas=deltas,
    )

    receipt.update(
        {
            "request_finished_at": _now(),
            "provider_status": {
                "status_code": result.status_code,
                "status_meaning": "success",
                "http_status": result.http_status,
                "trace_id": result.trace_id,
                "usage_characters": result.usage_characters,
                "usage_voice_count": result.usage_voice_count,
            },
            "error_taxonomy": {
                "http_status": result.http_status,
                "provider_status_code": result.status_code,
                "provider_status_msg": result.status_msg,
                "trace_id": result.trace_id,
                "cli_exit_code": None,
                "transport": "native_http_cn",
            },
            "audio": {
                "raw_path": str(raw_path),
                "normalized_path": str(normalized_path),
                "raw_sha256": raw_sha,
                "normalized_sha256": normalized_sha,
                "duration_s": measured.duration_s,
                "sample_rate_hz": measured.sample_rate_hz,
                "channels": measured.channels,
                "codec": measured.codec,
                "integrated_lufs": measured.integrated_lufs,
                "true_peak_db": measured.true_peak_db,
            },
            "fingerprint": fingerprint,
            "normalisation": {
                "ok": normalisation.get("ok"),
                "loudness_target_met": normalisation.get("loudness_target_met"),
                "loudness_delta_lu": normalisation.get("loudness_delta_lu"),
                "peak_ceiling_met": normalisation.get("peak_ceiling_met"),
            },
            "technical_qc": technical,
            "asr_backcheck": semantic,
            "second_clone_fee_check": {
                "usage_voice_count": result.usage_voice_count,
                "second_clone_fee_charged": bool(result.usage_voice_count),
            },
            "quota_after": guard_after["quota"],
            "balances_after": guard_after["balances"],
            "deltas": deltas,
            "verification": classification,
            "sidecar_path": str(sidecar_for(normalized_path)),
        }
    )
    receipt["outcome"] = (
        "GOLDEN_NARRATION_READY_FOR_FOUNDER_REVIEW"
        if technical.get("approved")
        else "GOLDEN_NARRATION_TECHNICAL_QC_FAILED"
    )
    if semantic.get("status") == "DETECTED_PROBLEM":
        receipt["notes"].append(
            "ASR backcheck detected a problem; the detector never blocks by itself, "
            "but the Founder should read it before publishing"
        )
    if not classification["verified"]:
        receipt["notes"].append(
            f"plan-only verification at narration time: {classification['status']}"
        )
    if result.usage_voice_count:
        receipt["notes"].append(
            "SEVERE: usage_voice_count is present on a narration request, so a "
            "voice fee may have been charged a second time"
        )

    print()
    print(f"  normalized audio  : {normalized_path}")
    print(f"  sha256            : {normalized_sha}")
    print(f"  duration_s        : {measured.duration_s}")
    print(f"  integrated_lufs   : {measured.integrated_lufs}")
    print(f"  technical QC      : {technical.get('approved')}")
    print(f"  ASR backcheck     : {semantic.get('status')} "
          f"(coverage {semantic.get('coverage')})")
    print(f"  plan-only         : {classification['status']} "
          f"(basis {classification['basis']})")
    print(f"  trace_id          : {result.trace_id}")
    print(f"=== OUTCOME: {receipt['outcome']} ===")
    print("=== STOP: Founder listening and review are pending. ===")

    _write(receipt)
    return 0 if technical.get("approved") else 1


if __name__ == "__main__":
    raise SystemExit(main())
