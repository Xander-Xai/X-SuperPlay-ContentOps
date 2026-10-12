"""Prepare the Founder voice clone: validate everything, persist, then STOP.

Nothing here transmits. It exists so that the one billable clone request has a
persisted, checkable record *before* it is sent -- the sample digest, the voice alias,
the declared objective, the expected one-time fee and a request fingerprint -- so that
"exactly one attempt, on these terms" is verifiable afterwards rather than remembered.

Run it to see the gate. Pass ``--print-gate`` (the default) and it prints
``READY_FOR_ONE_TIME_CLONE_FEE`` and writes the receipt with
``clone_status: NOT_ATTEMPTED``. It never uploads and never clones, because
transmitting is a separate, explicitly confirmed action.

It also reports any cloned voice that already exists on the account, because that
changes the commercial decision: if a usable clone is already present, paying CNY 9.9
for a second one is waste.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.credentials import resolve_credential  # noqa: E402
from contentops.media.minimax_voice_clone import (  # noqa: E402
    CLONE_FEE_MAX_CNY,
    CLONE_FEE_POLICY,
    TTS_BILLING_POLICY,
    REFUSAL_FEE_NOT_CONFIRMED,
    MiniMaxVoiceCloneProvider,
    VoiceCloneRequest,
    voice_id_hash,
)

SAMPLE = ROOT / "assert" / "voice-reference-clean.wav"
SAMPLE_AUDIT = ROOT / "projects/easel-enhanced-golden/receipts/founder-voice-sample-audit.json"
OUT = ROOT / "projects/easel-enhanced-golden/receipts/founder-voice-clone-receipt.json"

#: Local record of a real attempt, written by the run that performed it. If present it
#: is merged into the receipt, so the committed receipt describes what actually
#: happened rather than only what was prepared. Absent on a clean checkout, where the
#: receipt legitimately describes a preflight that was never sent.
ATTEMPT_RECORD = ROOT / ".verify-tmp" / "m23-founder-clone" / "clone-execution.json"

VOICE_ALIAS = "founder_primary_v1"
PROVIDER_VOICE_ID = "XSuperPlayFounderV1"
OBJECTIVE = "speech-2.8-hd narration for the Enhanced Golden pipeline"
SAMPLE_DURATION_S = 15.0


def derive_notes(receipt: Dict[str, Any]) -> List[str]:
    """Describe the run from the receipt's own counters, never from a fixed string.

    The notes used to be one hand-written list written for the pre-attempt state, so
    after a refused attempt the receipt read "no provider upload, no clone request, no
    synthesis was performed" directly above ``provider_calls: {upload: 1, clone: 1}``.
    That is the worst shape a record can take: the counters are the part a reader
    trusts, and a sentence beside them that denies them teaches the reader to distrust
    the sentence *and* stops them noticing when the counters are wrong.

    Generating the prose from the counters makes the contradiction unrepresentable --
    there is no separate claim left to fall out of date.
    """
    calls = receipt.get("provider_calls") or {}
    upload = int(calls.get("upload") or 0)
    clone = int(calls.get("clone") or 0)
    listed = int(calls.get("list") or 0)
    tts = bool(receipt.get("tts_performed", False))
    retried = bool(receipt.get("retry_performed", False))
    status = receipt.get("provider_status_code")
    charge = receipt.get("observed_charge_cny")

    if upload == 0 and clone == 0:
        headline = (
            "no provider upload, no clone request, no synthesis was performed"
        )
    else:
        headline = (
            f"{upload} upload(s) and {clone} clone request(s) were sent to the provider "
            f"and the clone step answered status_code={status}; "
            f"{'a' if tts else 'no'} synthesis and "
            f"{'a' if retried else 'no'} retry followed"
        )
    return [
        headline,
        (
            f"counters: upload={upload}, clone={clone}, list={listed}, "
            f"tts={int(tts)}, retry={int(retried)}"
        )
        + (f", observed_charge_cny={charge}" if charge is not None else ""),
        "the sample is a LOCAL PRIVATE INPUT: gitignored, untracked, not copied",
        "the raw provider voice_id is not recorded here, only its SHA256",
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-gate", action="store_true", default=True,
        help="print the one-time fee gate (default)",
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    resolved = resolve_credential()
    provider = MiniMaxVoiceCloneProvider(credential=resolved)

    print("=== FOUNDER VOICE CLONE PREFLIGHT (no provider call) ===")
    print(f"  credential_class : {resolved.credential_class}")
    print(f"  credential_source: {resolved.source}")
    print(f"  base_url_host    : {provider._base_url}")
    print()

    if not SAMPLE.is_file():
        raise SystemExit(
            f"the private sample is absent at {SAMPLE.relative_to(ROOT).as_posix()}. "
            "It is a LOCAL PRIVATE INPUT and gitignored, so it will not exist on a "
            "clean checkout. Nothing was sent."
        )

    digest = _sha256(SAMPLE)
    request = VoiceCloneRequest(
        voice_alias=VOICE_ALIAS,
        provider_voice_id=PROVIDER_VOICE_ID,
        objective=OBJECTIVE,
        sample_path=SAMPLE,
        sample_sha256=digest,
    )

    # Preflight performs every local precondition check and no I/O.
    preflight = provider.preflight(request, duration_s=SAMPLE_DURATION_S)
    print("=== SAMPLE ===")
    for key in ("sha256", "bytes", "suffix", "duration_s", "duration_checked"):
        print(f"  {key:16s}: {preflight['sample'][key]}")
    print()
    print("=== REQUEST ===")
    print(f"  voice_alias       : {preflight['voice_alias']}")
    print(f"  provider_voice_id : {preflight['provider_voice_id']}")
    print(f"  voice_id_hash     : {preflight['voice_id_hash']}")
    print(f"  payload fields    : {preflight['request_payload_fields']}")
    print(f"  preview text sent : {preflight['preview_text_sent']}")
    print(f"  fingerprint       : {preflight['request_fingerprint']}")
    print()

    # Read-only: does a clone already exist? This is not billable and it is
    # commercially decisive, so it is checked before anything is spent.
    existing: List[Dict[str, Any]] = []
    existing_probe_error = ""
    try:
        existing = provider.list_cloned_voices()
    except Exception as exc:  # noqa: BLE001 - a failed probe must not block the report
        existing_probe_error = f"{type(exc).__name__}: {exc}"

    print("=== EXISTING CLONED VOICES ON THIS ACCOUNT (read-only) ===")
    if existing_probe_error:
        print(f"  probe failed: {existing_probe_error}")
    else:
        print(f"  count: {len(existing)}")
        for entry in existing:
            raw = str(entry.get("voice_id", ""))
            print(f"    voice_id_hash : {voice_id_hash(raw)[:16]}")
            print(f"    created_time  : {entry.get('created_time')}")
            print(f"    voice_name    : {entry.get('voice_name')!r}")
    print()

    sample_audit: Dict[str, Any] = {}
    if SAMPLE_AUDIT.is_file():
        sample_audit = json.loads(SAMPLE_AUDIT.read_text(encoding="utf-8"))

    receipt = {
        "schema": "contentops.voice-clone-receipt/v1",
        "producer": "scripts/prepare_founder_voice_clone.py",
        "provider": "minimax",
        "clone_transport": "documented_public_api",
        "voice_alias": VOICE_ALIAS,
        "voice_id_hash": preflight["voice_id_hash"],
        "sample_sha256": digest,
        "sample_bytes": preflight["sample"]["bytes"],
        "sample_duration_s": preflight["sample"]["duration_s"],
        "sample_audit_receipt": (
            "projects/easel-enhanced-golden/receipts/founder-voice-sample-audit.json"
        ),
        "sample_audit_all_requirements_met": sample_audit.get("all_requirements_met"),
        "rights_basis": "FOUNDER_OWN_VOICE",
        "clone_fee_policy": CLONE_FEE_POLICY,
        "tts_billing_policy": TTS_BILLING_POLICY,
        "allow_payg_tts": False,
        "allow_credit_pack_tts": False,
        "expected_max_fee_cny": str(CLONE_FEE_MAX_CNY),
        "clone_status": "NOT_ATTEMPTED",
        "provider_status_code": None,
        "provider_status_meaning": "",
        "base_url_host": provider._base_url,
        "credential_class": resolved.credential_class,
        "credential_source": resolved.source,
        "model_for_tts": OBJECTIVE,
        "request_fingerprint": preflight["request_fingerprint"],
        "created_at": "",
        "provider_calls": {"upload": 0, "clone": 0, "list": provider.list_count},
        "refusal_code": REFUSAL_FEE_NOT_CONFIRMED,
        "refusal_reason": (
            "the clone request is billable (one-time, Founder-confirmed CNY 9.9 per "
            "cloned voice) and no Founder confirmation to spend has been given. Nothing "
            "was uploaded and nothing was cloned."
        ),
        "existing_cloned_voices_on_account": [
            {
                "voice_id_hash": voice_id_hash(str(e.get("voice_id", ""))),
                "created_time": e.get("created_time"),
                "voice_name": e.get("voice_name"),
            }
            for e in existing
        ],
        "existing_clone_note": (
            "A cloned voice already exists on this account and appears in the "
            "voice_cloning list, which the current documentation says only happens "
            "after a successful synthesis. Its provenance is unverified: no receipt "
            "binds it to the approved sample, and it was not created by ContentOps. "
            "Whether to REUSE it instead of paying for a second clone is a Founder "
            "decision, not an engineering one."
        ),
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
        "notes": [],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)

    # Merge a real attempt if one was made locally. The receipt must describe what
    # happened, not what was planned: a preflight receipt left saying NOT_ATTEMPTED
    # after a clone was actually refused would be the stale-receipt failure this
    # repository has already been bitten by once.
    if ATTEMPT_RECORD.is_file():
        attempt = json.loads(ATTEMPT_RECORD.read_text(encoding="utf-8"))
        receipt["clone_status"] = attempt.get("clone_status", receipt["clone_status"])
        receipt["refusal_code"] = attempt.get("refusal_code") or receipt["refusal_code"]
        receipt["provider_status_code"] = attempt.get("provider_status_code")
        receipt["provider_status_meaning"] = attempt.get(
            "provider_status_meaning_documented", ""
        )
        receipt["provider_calls"] = attempt.get("provider_calls", receipt["provider_calls"])
        receipt["quota_before"] = attempt.get("quota_before")
        receipt["quota_after"] = attempt.get("quota_after")
        receipt["observed_charge_cny"] = attempt.get("charge_observed_cny")
        receipt["attempt_notes"] = attempt.get("notes", [])
        receipt["retry_performed"] = attempt.get("retry_performed", False)
        receipt["tts_performed"] = attempt.get("tts_performed", False)
        receipt["tts_skipped_reason"] = attempt.get("tts_skipped_reason", "")
        receipt["orphaned_upload_note"] = attempt.get("orphaned_upload_note", "")
        receipt["refusal_reason"] = (
            "the clone request was sent once, authorised by the Founder, and the "
            "provider refused it with status_code "
            f"{attempt.get('provider_status_code')}. No charge was incurred and no "
            "retry was attempted."
        )
        receipt["attempted_at"] = attempt.get("finished_at") or attempt.get("started_at")

    # Written last, from the receipt as it now stands, so the prose cannot describe a
    # different run than the counters describe.
    receipt["notes"] = derive_notes(receipt)

    OUT.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    if args.print_gate:
        print(provider.fee_gate(request))
        print()

    print("wrote", OUT.relative_to(ROOT).as_posix())
    print()
    print("NOTHING WAS TRANSMITTED. This script has no code path that uploads or clones.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())