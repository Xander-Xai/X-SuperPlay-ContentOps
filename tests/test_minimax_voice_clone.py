"""M2.1 voice-clone regression tests. No provider call, no network, no spend.

Every test here runs against a fake transport or a refusal path. The real clone is one
billable call that must happen exactly once, by hand, with explicit Founder
confirmation -- so nothing in CI may reach any provider host.

The tests are grouped by the failure each one exists to prevent:

A. **Privacy.** The raw Founder voice and the raw provider voice_id must not be
   committable or leakable through a receipt.
B. **Spend.** A billable clone must be impossible without an explicit confirmation,
   impossible above the authorised fee ceiling, and impossible with the wrong
   credential class.
C. **One attempt.** No retry, no second voice id, no duplicate clone.
D. **Schema honesty.** A changed provider response must refuse, not be reinterpreted.
E. **The happy path.** A mocked successful clone, and a cloned-voice synthesis request
   that reuses the existing speech machinery rather than reimplementing it.

Three structural rules this file follows, because they were expensive to learn:

1. **Refusals are asserted by code, not by message.** ``CloneRefusal.code`` is the
   contract; message text is prose and may be reworded.
2. **The absence of a call is asserted by counter.** ``upload_count == 0`` is the only
   mechanical proof that a refusal happened *before* the sample left the machine. A
   test that only checks "it raised" would still pass if the upload had already
   happened.
3. **The substitute sample is clearly not a human voice.** Tests that need a sample
   build a synthetic WAV locally. Reusing the Founder's real recording in CI would
   make the suite depend on a private input, and would put a real voice on a build
   runner.
"""

from __future__ import annotations

import json
import math
import os
import struct
import sys
import tempfile
import wave
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.credentials import (  # noqa: E402
    CREDENTIAL_PAYG,
    CREDENTIAL_SUBSCRIPTION,
    ResolvedCredential,
    CredentialBinding,
)
from contentops.media import minimax_voice_clone as vc  # noqa: E402
from process_utils import hidden_run  # noqa: E402

TESTS: List = []


def test(fn):
    TESTS.append(fn)
    return fn


def _skip(number: int, what: str, need: str) -> None:
    print(f"[skip] {number}. {what} (needs {need})")


# --- fixtures ---------------------------------------------------------------


def synthetic_wav(path: Path, seconds: float = 15.0, rate: int = 16000) -> Path:
    """A quiet sine tone. Deliberately not speech, and deliberately not the Founder.

    Tests must never depend on the private recording: it is gitignored, so CI would not
    have it, and shipping a real voice to a build runner to test plumbing is the
    opposite of the privacy rule the plumbing exists to enforce.
    """
    frames = int(seconds * rate)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        data = b"".join(
            struct.pack("<h", int(1200 * math.sin(2 * math.pi * 220 * i / rate)))
            for i in range(frames)
        )
        handle.writeframes(data)
    return path


def subscription_binding() -> CredentialBinding:
    return CredentialBinding(
        ResolvedCredential(
            key="sk-cp-" + "x" * 40,
            credential_class=CREDENTIAL_SUBSCRIPTION,
            source="TEST_FIXTURE",
        )
    )


def payg_binding() -> CredentialBinding:
    return CredentialBinding(
        ResolvedCredential(
            key="sk-api-" + "x" * 40,
            credential_class=CREDENTIAL_PAYG,
            source="TEST_FIXTURE",
        )
    )


class FakeTransport:
    """Records every call it is asked to make. Never touches the network.

    The call log is the evidence: several tests assert that a *later* step never
    happened, which is only checkable if the transport remembers what was asked.
    """

    def __init__(
        self,
        *,
        upload_status: int = 0,
        clone_status: int = 0,
        list_status: int = 0,
        list_entries: Optional[List[Dict[str, Any]]] = None,
        clone_payload: Optional[Dict[str, Any]] = None,
        upload_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.upload_status = upload_status
        self.clone_status = clone_status
        self.list_status = list_status
        self.list_entries = list_entries if list_entries is not None else []
        self.clone_payload = clone_payload
        self.upload_payload = upload_payload
        self.calls: List[str] = []
        self.clone_bodies: List[Dict[str, Any]] = []
        self.upload_paths: List[Path] = []

    def upload(self, path: Path, facts: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append("upload")
        self.upload_paths.append(path)
        if self.upload_payload is not None:
            return self.upload_payload
        return {
            "file": {"file_id": 123456789012345680, "bytes": facts["bytes"],
                     "filename": path.name, "purpose": "voice_clone"},
            "base_resp": {"status_code": self.upload_status, "status_msg": "ok"},
        }

    def clone(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append("clone")
        self.clone_bodies.append(dict(payload))
        if self.clone_payload is not None:
            return self.clone_payload
        return {
            "voice_id": payload["voice_id"],
            "base_resp": {"status_code": self.clone_status, "status_msg": "ok"},
        }

    def list_voices(self) -> Dict[str, Any]:
        self.calls.append("list")
        return {
            "voice_cloning": list(self.list_entries),
            "base_resp": {"status_code": self.list_status, "status_msg": "ok"},
        }


#: A host that can never resolve. Tests must not name a real provider endpoint: the
#: literal is policy-excluded from tracked source, and a test that addressed a real host
#: would be one env change away from touching the network.
TEST_BASE_URL = "https://example.invalid/v1"


def make_provider(transport: Optional[FakeTransport] = None,
                  binding: Optional[CredentialBinding] = None, **kwargs):
    kwargs.setdefault("base_url", TEST_BASE_URL)
    return vc.MiniMaxVoiceCloneProvider(
        binding or subscription_binding(), transport=transport, **kwargs
    )


def make_request(sample: Optional[Path], **overrides) -> vc.VoiceCloneRequest:
    base = dict(
        voice_alias="founder_primary_v1",
        provider_voice_id="XSuperPlayFounderV1",
        objective="M2.1 founder cloned voice for Enhanced Golden narration",
        sample_sha256="",
    )
    base.update(overrides)
    # Only compute the digest when the caller has not deliberately declared a different
    # one: the mismatch test needs its override to survive.
    if sample is not None and "sample_sha256" not in overrides:
        import hashlib
        base["sample_sha256"] = hashlib.sha256(sample.read_bytes()).hexdigest()
    return vc.VoiceCloneRequest(sample_path=sample, **base)


# --- A. privacy --------------------------------------------------------------


@test
def test_one_voice_id_is_accepted_and_sanitized():
    """The alias is public; the provider id is not."""
    vc.validate_voice_id("XSuperPlayFounderV1")
    h = vc.voice_id_hash("XSuperPlayFounderV1")
    assert h == vc.sanitize_voice_id("XSuperPlayFounderV1")
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
    assert "XSuperPlayFounderV1" not in h
    print("[ok] 1. voice_id validates and sanitizes to a stable digest")


@test
def test_invalid_voice_ids_are_refused_before_any_call():
    """Documented rules: [8,256], starts with a letter, letters/digits/-/_ , no - or _ end."""
    bad = [
        "short",              # too short
        "1StartsWithDigit",   # must start with a letter
        "endsWith-",          # may not end with '-'
        "endsWith_",          # may not end with '_'
        "has space",
        "has.dot",
        "has/slash",
        "emoji\U0001F600id",
        "x" * 257,            # too long
    ]
    transport = FakeTransport()
    provider = make_provider(transport)
    for candidate in bad:
        try:
            vc.validate_voice_id(candidate)
            raise AssertionError(f"{candidate!r} should have been refused")
        except vc.CloneRefusal as refusal:
            assert refusal.code == vc.REFUSAL_VOICE_ID_INVALID, (
                f"{candidate!r} refused with {refusal.code}, expected "
                f"{vc.REFUSAL_VOICE_ID_INVALID}"
            )
    assert transport.calls == [], "a bad voice_id must be refused before any provider call"
    assert provider.clone_count == 0
    print(f"[ok] 2. all {len(bad)} invalid voice_ids refused with no provider call")


@test
def test_the_clone_payload_carries_only_file_id_and_voice_id():
    """No preview text. Preview TTS is a second generation event and a first-use charge."""
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        transport = FakeTransport()
        provider = make_provider(transport)
        outcome = provider.clone(
            make_request(sample), confirm_fee=True, duration_s=15.0
        )
        assert outcome.ok, outcome.receipt.notes
        assert len(transport.clone_bodies) == 1
        body = transport.clone_bodies[0]
        assert set(body) == {"file_id", "voice_id"}, (
            f"the clone payload must be minimal, got keys {sorted(body)}. "
            "An optional 'text' preview is a separate generation event."
        )
        assert "text" not in body and "clone_prompt" not in body
        print("[ok] 3. the clone payload is exactly {file_id, voice_id}, no preview text")


@test
def test_the_receipt_contains_no_raw_voice_id_sample_or_credential():
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        transport = FakeTransport()
        provider = make_provider(transport)
        outcome = provider.clone(
            make_request(sample), confirm_fee=True, duration_s=15.0
        )
        blob = json.dumps(outcome.receipt.as_dict(), ensure_ascii=False)

        assert "XSuperPlayFounderV1" not in blob, "raw voice_id leaked into the receipt"
        assert "sk-cp-" not in blob and "sk-api-" not in blob
        assert "Bearer" not in blob and "Authorization" not in blob
        assert str(sample) not in blob, "sample path leaked into the receipt"
        assert sample.name not in blob, "sample filename leaked into the receipt"
        assert outcome.raw_voice_id == "XSuperPlayFounderV1", (
            "the raw id must still be returned in memory so TTS can use it"
        )
        # And the receipt proves it carries only the hash.
        assert outcome.receipt.voice_id_hash == vc.voice_id_hash("XSuperPlayFounderV1")
        print("[ok] 4. the receipt carries the hash, never the raw voice_id or sample")


@test
def test_the_receipt_refuses_to_serialise_a_credential_or_bare_alias():
    """The invariant is enforced at serialisation, not trusted to callers."""
    receipt = vc.VoiceCloneReceipt(voice_alias="founder_primary_v1", voice_id_hash="")
    try:
        receipt.as_dict()
        raise AssertionError("a named alias with no hash must not serialise")
    except vc.CloneRefusal as refusal:
        assert refusal.code == vc.REFUSAL_TRANSPORT

    leaky = vc.VoiceCloneReceipt(voice_alias="a", voice_id_hash="b")
    leaky.notes.append("Authorization: Bearer <redacted>")
    try:
        leaky.as_dict()
        raise AssertionError("a receipt containing a credential-shaped string must not serialise")
    except vc.CloneRefusal:
        pass
    print("[ok] 5. receipt serialisation refuses a bare alias and a credential-shaped string")


@test
def test_a_tracked_sample_is_refused_as_a_privacy_violation():
    """Uploading a committed raw voice would mean the breach already happened.

    The check is done against the real Git index on a real (synthetic) file, because a
    stub for "is tracked" would not prove the index is actually consulted.
    """
    rel = "projects/easel-enhanced-golden/receipts/.clone-test-tracked.wav"
    tracked = ROOT / rel
    transport = FakeTransport()
    provider = make_provider(transport)
    try:
        synthetic_wav(tracked, seconds=11.0)
        add = hidden_run(
            ["git", "add", "-f", "--", rel], cwd=str(ROOT), timeout=120
        )
        if add.returncode != 0:
            _skip(6, "tracked sample refused",
                  "a writable git index")
            return
        try:
            provider.validate_sample(tracked, duration_s=11.0)
            raise AssertionError("a tracked sample must be refused")
        except vc.CloneRefusal as refusal:
            assert refusal.code == vc.REFUSAL_SAMPLE_TRACKED, refusal.code
        assert transport.calls == [], "nothing may be uploaded before the privacy check"
        assert provider.upload_count == 0
        print("[ok] 6. a Git-tracked sample is refused with no upload attempted")
    finally:
        hidden_run(["git", "rm", "--cached", "-q", "--force", "--", rel],
                   cwd=str(ROOT), timeout=120)
        if tracked.exists():
            tracked.unlink()


@test
def test_the_private_voice_registry_is_gitignored():
    """The raw id may live in .private/, and .private/ must not be committable."""
    checks = [
        ".private/founder-voice.json",
        ".private/anything.json",
    ]
    for rel in checks:
        proc = hidden_run(
            ["git", "check-ignore", "-q", "--no-index", "--", rel],
            cwd=str(ROOT), timeout=60,
        )
        assert proc.returncode == 0, f"{rel} is not ignored; the raw voice id could be committed"
    print(f"[ok] 7. all {len(checks)} private registry paths are gitignored")


@test
def test_the_founder_sample_is_not_tracked_and_any_tracking_is_a_violation():
    """The real sample may be absent (CI); if present it must not be tracked."""
    sample = ROOT / "assert" / "voice-reference-clean.wav"
    rel = "assert/voice-reference-clean.wav"
    tracked = hidden_run(
        ["git", "ls-files", "--error-unmatch", "--", rel],
        cwd=str(ROOT), timeout=60,
    )
    assert tracked.returncode != 0, (
        "FOUNDER_VOICE_PRIVACY_VIOLATION: the raw sample is tracked by Git"
    )
    ignored = hidden_run(
        ["git", "check-ignore", "-q", "--no-index", "--", rel],
        cwd=str(ROOT), timeout=60,
    )
    assert ignored.returncode == 0, "the raw sample is not ignored"
    present = sample.is_file()
    print(f"[ok] 8. raw sample untracked and ignored (present locally: {present})")


# --- B. spend ----------------------------------------------------------------


@test
def test_the_billable_clone_refuses_without_explicit_confirmation():
    """The default argument is the gate. Forgetting it must not cost CNY 9.9."""
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        transport = FakeTransport()
        provider = make_provider(transport)
        outcome = provider.clone(make_request(sample), duration_s=15.0)
        assert outcome.status == "REFUSED"
        assert outcome.refusal_code == vc.REFUSAL_FEE_NOT_CONFIRMED
        assert transport.calls == [], (
            f"nothing may be transmitted before confirmation; got {transport.calls}"
        )
        assert provider.upload_count == 0, (
            "the sample must not be uploaded before the fee is confirmed: uploading is "
            "an irreversible disclosure to a third party"
        )
        assert provider.clone_count == 0
        print("[ok] 9. no confirmation -> refused with 0 uploads and 0 clone calls")


@test
def test_the_fee_gate_text_carries_the_required_fields():
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        provider = make_provider(FakeTransport())
        request = make_request(sample)
        text = provider.fee_gate(request)
        assert "READY_FOR_ONE_TIME_CLONE_FEE" in text
        assert f"expected_max_fee_cny={vc.CLONE_FEE_MAX_CNY}" in text
        assert "additional_payg_allowed=false" in text
        assert "credit_pack_fallback_allowed=false" in text
        assert request.fingerprint() in text
        print("[ok] 10. the fee gate prints the required fields, including the fingerprint")


@test
def test_a_declared_fee_above_the_authorised_maximum_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        transport = FakeTransport()
        provider = make_provider(transport)
        outcome = provider.clone(
            make_request(sample, expected_fee_cny=Decimal("9.91")),
            confirm_fee=True,
            duration_s=15.0,
        )
        assert outcome.refusal_code == vc.REFUSAL_FEE_ABOVE_MAX, outcome.refusal_code
        assert transport.calls == []
        print("[ok] 11. a declared fee above CNY 9.9 is refused before any call")


@test
def test_exactly_the_authorised_fee_is_allowed_through():
    """The boundary is inclusive: 9.9 is authorised, and the test proves it is not >9.9 only."""
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        transport = FakeTransport()
        provider = make_provider(transport)
        outcome = provider.clone(
            make_request(sample, expected_fee_cny=Decimal("9.9")),
            confirm_fee=True,
            duration_s=15.0,
        )
        assert outcome.ok, outcome.receipt.notes
        print("[ok] 12. the authorised ceiling itself (CNY 9.9) is accepted")


@test
def test_a_payg_credential_is_refused_for_cloning():
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        transport = FakeTransport()
        provider = make_provider(transport, binding=payg_binding())
        outcome = provider.clone(
            make_request(sample), confirm_fee=True, duration_s=15.0
        )
        assert outcome.refusal_code == vc.REFUSAL_CREDENTIAL_CLASS
        assert transport.calls == []
        assert provider.clone_count == 0
        print("[ok] 13. a PAYG credential is refused; only SUBSCRIPTION may clone")


@test
def test_a_payg_credential_cannot_even_upload():
    """The class check is a precondition of the upload too, not just the clone."""
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        provider = make_provider(FakeTransport(), binding=payg_binding())
        try:
            provider.upload_sample(sample)
            raise AssertionError("a PAYG credential must not upload")
        except vc.CloneRefusal as refusal:
            assert refusal.code == vc.REFUSAL_CREDENTIAL_CLASS
        assert provider.upload_count == 0
        print("[ok] 14. a PAYG credential cannot upload the sample either")


@test
def test_an_absent_credential_is_refused_rather_than_discovered():
    provider = make_provider(FakeTransport(), binding=CredentialBinding(None))
    try:
        provider._require_subscription_credential()
        raise AssertionError("an unbound credential must be refused")
    except vc.CloneRefusal as refusal:
        assert refusal.code == vc.REFUSAL_CREDENTIAL_CLASS
    print("[ok] 15. an unbound credential is refused, never resolved ambiently")


@test
def test_insufficient_balance_is_classified_as_a_spend_refusal():
    """1008 means the request would have been paid outside the subscription."""
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        transport = FakeTransport(clone_status=vc.STATUS_INSUFFICIENT_BALANCE)
        provider = make_provider(transport)
        outcome = provider.clone(
            make_request(sample), confirm_fee=True, duration_s=15.0
        )
        assert outcome.refusal_code == vc.REFUSAL_FEE_ABOVE_MAX, outcome.refusal_code
        assert provider.clone_count == 1, "exactly one attempt, no retry"
        print("[ok] 16. status 1008 is refused and never retried")


# --- C. one attempt ----------------------------------------------------------


@test
def test_a_second_clone_attempt_is_refused_and_never_retried():
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        transport = FakeTransport()
        provider = make_provider(transport)
        first = provider.clone(make_request(sample), confirm_fee=True, duration_s=15.0)
        assert first.ok
        second = provider.clone(make_request(sample), confirm_fee=True, duration_s=15.0)
        assert second.refusal_code == vc.REFUSAL_CLONE_ALREADY_ATTEMPTED, (
            second.refusal_code
        )
        assert provider.clone_count == 1, "a billable call must never repeat"
        assert transport.calls.count("clone") == 1, transport.calls
        print("[ok] 17. a second clone attempt is refused after exactly one call")


@test
def test_the_outcome_records_one_upload_and_one_clone():
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        provider = make_provider(FakeTransport())
        outcome = provider.clone(make_request(sample), confirm_fee=True, duration_s=15.0)
        assert outcome.receipt.provider_calls == {"upload": 1, "clone": 1, "list": 0}
        print("[ok] 18. the receipt records exactly one upload and one clone")


@test
def test_a_duplicate_voice_id_reply_is_classified_and_not_retried():
    """The provider errors when the voice_id already exists. That is not a retry cue."""
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        transport = FakeTransport(
            clone_payload={"base_resp": {"status_code": 2013, "status_msg": "exists"}}
        )
        provider = make_provider(transport)
        outcome = provider.clone(
            make_request(sample), confirm_fee=True, duration_s=15.0
        )
        assert outcome.refusal_code == vc.REFUSAL_SCHEMA_CHANGED, outcome.refusal_code
        assert provider.clone_count == 1
        assert transport.calls.count("clone") == 1
        print("[ok] 19. a duplicate voice_id reply is classified with no second attempt")


# --- D. schema honesty -------------------------------------------------------


@test
def test_a_missing_base_resp_is_a_schema_change_not_a_success():
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        transport = FakeTransport(
            clone_payload={"voice_id": "XSuperPlayFounderV1"}  # no base_resp at all
        )
        provider = make_provider(transport)
        outcome = provider.clone(
            make_request(sample), confirm_fee=True, duration_s=15.0
        )
        assert outcome.refusal_code == vc.REFUSAL_SCHEMA_CHANGED, outcome.refusal_code
        print("[ok] 20. a response without base_resp is refused as a schema change")


@test
def test_account_verification_2038_is_classified_explicitly():
    """The entitlement error the repository already recorded. Not a generic failure."""
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        transport = FakeTransport(
            clone_payload={"base_resp": {"status_code": 2038, "status_msg": "no perm"}}
        )
        provider = make_provider(transport)
        outcome = provider.clone(
            make_request(sample), confirm_fee=True, duration_s=15.0
        )
        assert outcome.refusal_code == vc.REFUSAL_ACCOUNT_VERIFICATION, outcome.refusal_code
        assert "2038" in " ".join(outcome.receipt.notes)
        assert provider.clone_count == 1, "no automatic retry after an entitlement error"
        print("[ok] 21. status 2038 is classified NEEDS_ACCOUNT_VERIFICATION, no retry")


@test
def test_an_unrecognised_status_code_is_not_treated_as_success():
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        transport = FakeTransport(
            clone_payload={"base_resp": {"status_code": 9999, "status_msg": "???"}}
        )
        provider = make_provider(transport)
        outcome = provider.clone(
            make_request(sample), confirm_fee=True, duration_s=15.0
        )
        assert outcome.status == "REFUSED"
        assert outcome.refusal_code, "an unknown code must produce a refusal code"
        print("[ok] 22. an unrecognised status code refuses rather than passing")


@test
def test_a_get_voice_response_without_the_array_is_a_schema_change():
    transport = FakeTransport(list_entries=[])
    provider = make_provider(transport)
    transport.list_voices = lambda: {"base_resp": {"status_code": 0}}  # type: ignore
    try:
        provider.list_cloned_voices()
        raise AssertionError("a get_voice response missing voice_cloning must refuse")
    except vc.CloneRefusal as refusal:
        assert refusal.code == vc.REFUSAL_SCHEMA_CHANGED
    print("[ok] 23. get_voice without a voice_cloning array is refused")


# --- E. sample validation ----------------------------------------------------


@test
def test_an_invalid_duration_is_refused_before_upload():
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "short.wav", seconds=9.5)
        provider = make_provider(FakeTransport())
        try:
            provider.validate_sample(sample, duration_s=9.5)
            raise AssertionError("a 9.5s sample must be refused")
        except vc.CloneRefusal as refusal:
            assert refusal.code == vc.REFUSAL_SAMPLE_INVALID
        assert provider.upload_count == 0
    print("[ok] 24. a sub-minimum duration is refused before any upload")


@test
def test_an_oversized_sample_is_refused_before_upload():
    limit = vc.SAMPLE_MAX_BYTES
    provider = make_provider(FakeTransport())
    with tempfile.TemporaryDirectory() as tmp:
        big = Path(tmp) / "big.wav"
        big.write_bytes(b"RIFF" + b"\0" * (limit + 1))
        try:
            provider.validate_sample(big)
            raise AssertionError("an oversized sample must be refused")
        except vc.CloneRefusal as refusal:
            assert refusal.code == vc.REFUSAL_SAMPLE_INVALID
        assert provider.upload_count == 0
    print(f"[ok] 25. a sample above {limit} bytes is refused before any upload")


@test
def test_an_unsupported_format_is_refused():
    provider = make_provider(FakeTransport())
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "sample.flac"
        bad.write_bytes(b"fLaC" + b"\0" * 2048)
        try:
            provider.validate_sample(bad)
            raise AssertionError("a .flac sample must be refused")
        except vc.CloneRefusal as refusal:
            assert refusal.code == vc.REFUSAL_SAMPLE_INVALID
    print("[ok] 26. an unsupported container is refused")


@test
def test_a_declared_sample_digest_that_disagrees_with_disk_is_refused():
    """Cloning one sample while recording another would make provenance a fiction."""
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        transport = FakeTransport()
        provider = make_provider(transport)
        request = make_request(sample, sample_sha256="0" * 64)
        outcome = provider.clone(request, confirm_fee=True, duration_s=15.0)
        assert outcome.refusal_code == vc.REFUSAL_SAMPLE_INVALID, outcome.refusal_code
        assert transport.calls == []
        print("[ok] 27. a digest mismatch between request and disk is refused")


@test
def test_a_missing_sample_is_refused():
    provider = make_provider(FakeTransport())
    request = make_request(None, sample_sha256="0" * 64)
    outcome = provider.clone(request, confirm_fee=True)
    assert outcome.refusal_code in (vc.REFUSAL_SAMPLE_INVALID,), outcome.refusal_code
    assert provider.clone_count == 0
    print("[ok] 28. a missing sample refuses rather than cloning nothing")


# --- F. happy path and TTS integration --------------------------------------


@test
def test_a_mocked_clone_succeeds_and_records_the_agreed_facts():
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        transport = FakeTransport()
        provider = make_provider(transport)
        outcome = provider.clone(
            make_request(sample), confirm_fee=True, duration_s=15.0
        )
        assert outcome.ok, outcome.receipt.notes
        receipt = outcome.receipt.as_dict()
        assert receipt["provider"] == "minimax"
        assert receipt["clone_transport"] == "documented_public_api"
        assert receipt["voice_alias"] == "founder_primary_v1"
        assert receipt["voice_id_hash"] == vc.voice_id_hash("XSuperPlayFounderV1")
        assert receipt["rights_basis"] == "FOUNDER_OWN_VOICE"
        assert receipt["clone_fee_policy"] == vc.CLONE_FEE_POLICY
        assert receipt["tts_billing_policy"] == vc.TTS_BILLING_POLICY
        assert receipt["allow_payg_tts"] is False
        assert receipt["allow_credit_pack_tts"] is False
        assert receipt["clone_status"] == "CLONED"
        assert receipt["provider_status_code"] == 0
        assert receipt["production_ready"] is False
        assert receipt["human_review"] == "PENDING_FOUNDER_REVIEW"
        print("[ok] 29. a mocked clone succeeds and records every agreed fact")


@test
def test_the_receipt_records_the_host_that_was_actually_used():
    """A credential authorised against one regional host is not evidence about the other."""
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        provider = make_provider(FakeTransport(), base_url="https://example.invalid/v1")
        outcome = provider.clone(make_request(sample), confirm_fee=True, duration_s=15.0)
        assert outcome.receipt.base_url_host == "https://example.invalid/v1"
        assert outcome.receipt.credential_class == CREDENTIAL_SUBSCRIPTION
        print("[ok] 30. the receipt records the exact host addressed")


@test
def test_the_preflight_fingerprint_changes_when_the_terms_change():
    """The fingerprint has to mean something: same terms, same value; new fee, new value."""
    with tempfile.TemporaryDirectory() as tmp:
        sample = synthetic_wav(Path(tmp) / "sample.wav")
        base = make_request(sample)
        same = make_request(sample)
        assert base.fingerprint() == same.fingerprint()

        changed_fee = make_request(sample, expected_fee_cny=Decimal("1.0"))
        assert changed_fee.fingerprint() != base.fingerprint()

        changed_id = make_request(sample, provider_voice_id="XSuperPlayFounderV2")
        assert changed_id.fingerprint() != base.fingerprint()

        changed_objective = make_request(sample, objective="something else")
        assert changed_objective.fingerprint() != base.fingerprint()
        print("[ok] 31. the request fingerprint tracks every term that decides the request")


@test
def test_get_voice_verification_reports_an_empty_list_without_failing():
    """Documented: voice_cloning entries appear only after a successful synthesis.

    So immediately after a clone, an empty list is the expected state, not a failure --
    and the code must not treat it as one, or a correct clone would be reported broken.
    """
    transport = FakeTransport(list_entries=[])
    provider = make_provider(transport)
    assert provider.list_cloned_voices() == []
    assert provider.list_count == 1

    transport2 = FakeTransport(
        list_entries=[{"voice_id": "XSuperPlayFounderV1", "voice_name": "founder"}]
    )
    provider2 = make_provider(transport2)
    entries = provider2.list_cloned_voices()
    assert len(entries) == 1 and entries[0]["voice_id"] == "XSuperPlayFounderV1"
    print("[ok] 32. get_voice verification handles both empty and populated listings")


@test
def test_a_cloned_voice_flows_into_the_existing_speech_request():
    """The clone exists so narration can use it. That path must not be re-implemented.

    SpeechRequest.voice is the documented single point where a voice is chosen, so the
    cloned id belongs there and the existing lexicon, QC, loudness and receipt
    machinery applies unchanged.
    """
    from contentops.media.contract import SpeechRequest

    request = SpeechRequest(
        display_text="hello",
        voice="XSuperPlayFounderV1",
        model="speech-2.8-hd",
    )
    assert request.voice == "XSuperPlayFounderV1"
    assert request.model == "speech-2.8-hd"

    # The speech provider must accept a custom voice without it being in DEFAULT_VOICES.
    from contentops.media import minimax_speech

    assert "XSuperPlayFounderV1" not in minimax_speech.DEFAULT_VOICES.values(), (
        "a cloned voice must not be smuggled in as a default; it is passed explicitly"
    )
    assert minimax_speech.DEFAULT_MODEL == "speech-2.8-hd"
    print("[ok] 33. the cloned voice flows through SpeechRequest unchanged")


@test
def test_the_clone_provider_declares_that_it_does_not_synthesize():
    provider = make_provider(FakeTransport())
    caps = provider.capabilities()
    assert caps["synthesizes"] is False, (
        "clone lifecycle must not absorb synthesis; that is the speech provider's job"
    )
    assert not hasattr(provider, "synthesize_speech"), (
        "the clone provider must not expose synthesize_speech, or clone billing and TTS "
        "billing become one argument-shaped decision"
    )
    assert caps["fee_max_cny"] == str(vc.CLONE_FEE_MAX_CNY)
    assert caps["allow_payg_tts"] is False
    assert caps["allow_credit_pack_tts"] is False
    assert caps["evidence_status"].startswith("DOCUMENTED_BUT_NOT_TESTED")
    print("[ok] 34. the clone provider declares no synthesis capability")


@test
def test_health_never_leaks_the_credential():
    provider = make_provider(FakeTransport())
    blob = json.dumps(provider.health(), ensure_ascii=False)
    assert "sk-cp-" not in blob and "x" * 40 not in blob
    assert provider.health()["credential"]["credential_class"] == CREDENTIAL_SUBSCRIPTION
    print("[ok] 35. health() reports the credential class and never the value")


@test
def test_no_test_here_made_a_real_network_call():
    """Guard the guard: the default provider must have no transport at all.

    If a test ever accidentally constructs a provider without a fake transport and then
    reaches the clone step, this proves the seam exists rather than being theoretical.
    """
    provider = vc.MiniMaxVoiceCloneProvider(
        subscription_binding(), base_url=TEST_BASE_URL
    )
    assert provider._transport is None
    assert provider.upload_count == 0 and provider.clone_count == 0 and provider.list_count == 0
    print("[ok] 36. the network seam is explicit and no counter moved without it")


@test
def test_no_configured_host_is_refused_rather_than_guessed():
    """Fail closed on a missing endpoint.

    A guessed default is worse than no default. The wrong regional host answers with an
    invalid-api-key status, which reads as a broken credential and sends the operator
    looking in the wrong place. Endpoints are also policy-excluded from tracked source,
    so the host has to be supplied at runtime.
    """
    saved = {name: os.environ.pop(name, None) for name in vc.BASE_URL_ENV_VARS}
    try:
        try:
            vc.MiniMaxVoiceCloneProvider(subscription_binding())
            raise AssertionError("a provider with no host must refuse to construct")
        except vc.CloneRefusal as refusal:
            assert refusal.code == vc.REFUSAL_TRANSPORT, refusal.code
            assert "no provider host is configured" in refusal.detail
    finally:
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value
    print("[ok] 37. an unconfigured host refuses instead of guessing a default")


@test
def test_the_host_can_come_from_the_environment():
    """The documented resolution order, and the same variable BillingGuard reads."""
    for name in vc.BASE_URL_ENV_VARS:
        saved = os.environ.pop(name, None)
        os.environ[name] = TEST_BASE_URL
        try:
            provider = vc.MiniMaxVoiceCloneProvider(subscription_binding())
            assert provider._base_url == TEST_BASE_URL, name
        finally:
            os.environ.pop(name, None)
            if saved is not None:
                os.environ[name] = saved

    # The clone-specific variable wins over the shared one when both are set.
    saved = {n: os.environ.get(n) for n in vc.BASE_URL_ENV_VARS}
    try:
        os.environ[vc.BASE_URL_ENV_VARS[1]] = "https://shared.invalid/v1"
        os.environ[vc.BASE_URL_ENV_VARS[0]] = TEST_BASE_URL
        provider = vc.MiniMaxVoiceCloneProvider(subscription_binding())
        assert provider._base_url == TEST_BASE_URL
    finally:
        for name, value in saved.items():
            os.environ.pop(name, None)
            if value is not None:
                os.environ[name] = value
    print(f"[ok] 38. all {len(vc.BASE_URL_ENV_VARS)} host variables resolve, clone-specific first")


def main() -> int:
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
    print(f"\nAll {total} voice-clone regression tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())