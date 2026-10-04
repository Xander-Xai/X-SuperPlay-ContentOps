"""MiniMax M Plan speech provider, over the official CLI transport.

Transport decision and why
--------------------------
Measured against the pinned Easel v0.2.1 runtime on 2026-10-04, with a real
Subscription Key in the environment and **no** invented values:

| Check | Result |
|---|---|
| ``voice_clone.py check --provider minimax`` | exit 3, reports ``MINIMAX_GROUP_ID`` missing although ``MINIMAX_API_KEY`` was present |
| ``voice_clone.py clone --provider minimax ...`` | exit 1, blocked by ``require_env("MINIMAX_GROUP_ID")`` before any HTTP request |

Classification: ``EASEL_MPLAN_AUTH_INCOMPATIBLE``.

Three independent reasons, all read from the pinned source:

1. ``MINIMAX_GROUP_ID`` is **mandatory** (``require_env``) and is appended to
   every call as ``?GroupId=``. The current M Plan credential model has no
   GroupId. Inventing one, or borrowing an unrelated account id, is forbidden.
2. Easel's MiniMax path is **clone-only**: ``clone_minimax`` requires a
   ``--voice-id`` produced by ``enroll_minimax``. There is no system-voice TTS
   path, so the capability M2.0 actually verified -- system voices,
   ``speech-2.8-hd``, ``pronunciation_dict`` -- is unreachable through it.
3. Its defaults are legacy: base URL ``https://api.minimax.chat`` and model
   ``speech-01``.

Therefore ContentOps speaks to the **current official CLI** directly. This is a
thin adapter, not a second TTS implementation: it owns the billing gate, the
lexicon, normalisation, QC, idempotency and the receipt, and delegates synthesis
to the vendor CLI.

Easel is not patched, not forked and not modified.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from process_utils import hidden_run  # noqa: E402

from contentops.media.asr_backcheck import backcheck_speech  # noqa: E402
from contentops.media.attempts import (  # noqa: E402
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    AttemptRecordError,
    GenerationAttemptRecord,
    append_reuse_event,
    load_attempt_record,
    sanitise_failure,
)
from contentops.media.audio import (  # noqa: E402
    NORMALISATION_TARGET_LUFS,
    NORMALISATION_TRUE_PEAK_DB,
    normalise_speech,
    technical_qc,
)
from contentops.media.billing_guard import BillingGuard  # noqa: E402
from contentops.media.credentials import (  # noqa: E402
    CREDENTIAL_ABSENT,
    CREDENTIAL_PAYG,
    CREDENTIAL_SUBSCRIPTION,
    CredentialBindingError,
    ResolvedCredential,
    child_env_for,
)
from contentops.media.contract import (  # noqa: E402
    BillingBlocked,
    MediaProvider,
    QuotaSnapshot,
    SpeechAsset,
    SpeechReceipt,
    SpeechRequest,
)
from contentops.media.fingerprint import (  # noqa: E402
    sha256_file,
    sha256_text,
    speech_fingerprint,
)
from contentops.media.lexicon import (  # noqa: E402
    PronunciationLexicon,
    default_en_lexicon,
    default_zh_lexicon,
)

__all__ = [
    "EASEL_COMPATIBILITY",
    "MAX_ATTEMPTS",
    "MiniMaxMPlanProvider",
    "SpeechOutcome",
    "resolve_cli",
]

#: Recorded result of the pinned-Easel compatibility test. Kept as data so the
#: receipt and the docs cannot drift apart from the measured outcome.
EASEL_COMPATIBILITY = "EASEL_MPLAN_AUTH_INCOMPATIBLE"

PROVIDER_NAME = "minimax_m_plan"
PRODUCT = "m_plan"
PLAN = "explore"
BILLING_MODE = "subscription"
ALLOW_PAYG = False
ALLOW_CREDIT_PACK = False

#: Maximum provider generation attempts per asset.
MAX_ATTEMPTS = 2

#: Measured provider-behaviour trap, found 2026-10-04 on the golden narration.
#:
#: ``mmx speech synthesize`` behaves differently when ``--text`` contains a
#: newline. Measured matrix, all with the official CLI v1.0.27:
#:
#: ==========================  ======  ==============================  =========
#: text                       exit    ``--out`` honoured             container
#: ==========================  ======  ==============================  =========
#: single line                0       yes                             WAV
#: single line + normalise    0       yes                             WAV
#: single line + pronunciation 0      yes                             WAV
#: **contains a newline**     **0**   **no**                         **MP3**
#: ==========================  ======  ==============================  =========
#:
#: In the newline case the CLI still exits 0, silently ignores ``--out`` and
#: ``--format``, writes an MP3 into the **current working directory**, and
#: synthesises only the first line. Trusting the exit code would therefore mean
#: believing a truncated narration succeeded and then reading a stale or
#: missing file.
#:
#: Two defences, both required:
#: 1. the text is flattened to a single line before it is sent
#: 2. the output file is verified to exist, be fresh and be non-trivial after
#:    the call, so a future CLI regression fails loudly instead of silently
PAUSE_JOIN = " "
_FORBIDDEN_IN_TEXT = ("\n", "\r")


def flatten_for_cli(text: str) -> str:
    """Collapse a multi-line narration into one CLI-safe line.

    The documented ``<#seconds#>`` pause marker was tried first and **rejected**
    by the CLI with exit 1, so it is not used. A plain space is the only
    transformation applied, and the spoken text is unchanged apart from losing
    the line breaks themselves.
    """
    if not any(token in text for token in _FORBIDDEN_IN_TEXT):
        return text
    parts = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    return PAUSE_JOIN.join(part for part in parts if part)


def verify_output(path: Path, *, not_before: float, min_bytes: int = 1024) -> None:
    """Fail loudly when the CLI did not actually write what was asked for."""
    if not path.is_file():
        raise RuntimeError(
            f"the CLI reported success but {path} does not exist; it most "
            f"likely ignored --out. See the CLI output for the path it used."
        )
    if path.stat().st_mtime < not_before - 1:
        raise RuntimeError(
            f"{path} is stale (older than this request); refusing to treat a "
            f"previous run's output as this run's result"
        )
    if path.stat().st_size < min_bytes:
        raise RuntimeError(
            f"{path} is only {path.stat().st_size} bytes; treating it as a "
            f"failed generation rather than usable narration"
        )


SIDECAR_SUFFIX = ".receipt.json"

#: Fields a cached generation receipt must carry before it may be reused.
#:
#: Every one of these was previously allowed to be blank on a cache hit, which
#: produced a receipt with an empty voice, empty text hashes and
#: ``lexicon_version="unknown"``. Fabricated provenance is worse than no cache:
#: a missing field is a cache miss, never something to fill in.
REQUIRED_SIDECAR_FIELDS: Tuple[str, ...] = (
    "provider",
    "product",
    "plan",
    "model",
    "voice",
    "display_text_sha256",
    "spoken_text_sha256",
    "lexicon_version",
    "fingerprint",
    "raw_sha256",
    "normalized_sha256",
    "technical_qc",
    "semantic_qc",
    "billing_guard_verdict",
    "attempt",
    "human_review",
)

#: Fields whose value must not be an empty string.
NON_BLANK_SIDECAR_FIELDS: Tuple[str, ...] = (
    "provider", "product", "plan", "model", "voice",
    "display_text_sha256", "spoken_text_sha256", "lexicon_version",
    "fingerprint", "raw_sha256", "normalized_sha256",
    "billing_guard_verdict", "human_review",
)


def sidecar_for(asset_path: Path) -> Path:
    """Path of the sanitised receipt that sits next to a generated asset."""
    return asset_path.with_name(asset_path.name + SIDECAR_SUFFIX)


def write_sidecar(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def sidecar_is_complete(payload: Optional[Dict[str, Any]]) -> bool:
    """True when a cached receipt carries every required provenance field.

    Rejects a missing key, a blank string where blank is meaningless, and a field
    of the wrong type for ``attempt``. Anything short of complete is a cache miss.
    """
    if not isinstance(payload, dict):
        return False
    for name in REQUIRED_SIDECAR_FIELDS:
        if name not in payload:
            return False
    for name in NON_BLANK_SIDECAR_FIELDS:
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            return False
    for name in ("technical_qc", "semantic_qc"):
        if not isinstance(payload.get(name), dict):
            return False
    attempt = payload.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool):
        return False
    return True


def load_sidecar(path: Path) -> Optional[Dict[str, Any]]:
    """Load a sidecar, returning ``None`` when it is absent or unusable.

    A corrupt or unreadable sidecar is treated as no cache at all rather than as
    a licence to invent provenance.
    """
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None

DEFAULT_MODEL = "speech-2.8-hd"
DEFAULT_VOICES = {
    "zh": "Chinese (Mandarin)_Reliable_Executive",
    "en": "English_expressive_narrator",
}


#: Environment override for the transport executable. Set to a full command
#: prefix (a path, or a JSON-ish argv list separated by spaces is not supported --
#: use a path) to point at a stand-in during tests. Unset in production, where the
#: official CLI on PATH is used.
CLI_ENV_VAR = "CONTENTOPS_MINIMAX_CLI"


def resolve_cli() -> Any:
    """Absolute path to the official CLI launcher.

    On Windows the npm install produces ``mmx.cmd`` shims that CreateProcess
    cannot resolve from a bare ``mmx``, so resolution happens once here.
    """
    override = os.environ.get(CLI_ENV_VAR, "").strip()
    if override:
        # A JSON array is an argv prefix, which is what a stand-in launcher
        # needs (an interpreter plus a script). A bare value is a path.
        if override.startswith("["):
            try:
                parsed = json.loads(override)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list) and parsed and all(
                isinstance(part, str) for part in parsed
            ):
                return parsed
        return override
    return shutil.which("mmx")


@dataclass
class SpeechOutcome:
    """Result of one ``synthesize_speech`` call."""

    asset: SpeechAsset
    receipt: SpeechReceipt
    reused: bool = False
    fallback: Optional[Dict[str, Any]] = None


class MiniMaxMPlanProvider(MediaProvider):
    """Speech-only provider for the MiniMax M Plan Explore subscription."""

    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        guard: BillingGuard,
        work_dir: Path,
        cli: Any = None,
        model: str = DEFAULT_MODEL,
        transport_credential: Optional[ResolvedCredential] = None,
    ) -> None:
        self._guard = guard
        self._work_dir = Path(work_dir)
        self._cli = cli or resolve_cli()
        self._model = model
        # The credential the billing gate authorised, bound once into the child
        # environment. The provider never re-resolves it, so the gate and the
        # transport cannot drift apart.
        self._credential = transport_credential
        self._child_env: Optional[Dict[str, str]] = None
        if transport_credential is not None:
            self._child_env = child_env_for(transport_credential)
        self._lexicons = {
            "zh": default_zh_lexicon(),
            "en": default_en_lexicon(),
        }
        self._receipts: List[SpeechReceipt] = []
        self._last_attempt_fingerprint: Optional[str] = None

    # -- provider contract -------------------------------------------------

    def capabilities(self) -> Dict[str, Any]:
        return {
            "provider": PROVIDER_NAME,
            "transport": "official_cli",
            "transport_package": "mmx-cli",
            "speech": {
                "supported": True,
                "model": self._model,
                "system_voices": True,
                "pronunciation_dict": True,
                "ssml": False,
                "evidence": "M2.0 receipt, Issue #4",
            },
            "image": {"supported": False, "owner": "Issue #20"},
            "video": {"supported": False, "owner": "Issue #22"},
            "voice_clone": {"supported": False, "owner": "Issue #23"},
            "easel_compatibility": EASEL_COMPATIBILITY,
        }

    def health(self) -> Dict[str, Any]:
        cli = self._cli
        if not cli:
            return {
                "reachable": False,
                "reason": "official MiniMax CLI not on PATH",
                "install": "npm install -g mmx-cli",
            }
        prefix = list(cli) if isinstance(cli, (list, tuple)) else [cli]
        env = self._child_env if self._child_env is not None else None
        result = hidden_run(prefix + ["--version"], env=env, timeout=60)
        guard = self._guard.evaluate()
        return {
            "reachable": result.returncode == 0,
            "transport_version": (result.stdout or "").strip(),
            "credential_class": guard.credential_class,
            "billing_verdict": guard.verdict,
            "billing_reasons": guard.reasons,
        }

    def quota(self) -> QuotaSnapshot:
        snapshot = self._guard.read_quota()
        if snapshot is None:
            raise BillingBlocked(
                "BLOCKED_BILLING_SOURCE_UNCERTAIN",
                ["included plan usage could not be read"],
            )
        return snapshot

    # -- speech ------------------------------------------------------------

    def lexicon_for(self, language: str) -> PronunciationLexicon:
        return self._lexicons.get(language, self._lexicons["en"])

    def receipt(self, asset: Optional[SpeechAsset] = None) -> SpeechReceipt:
        """Return the receipt for a produced asset.

        Raises:
            RuntimeError: if nothing has been produced yet. Returning a
                placeholder receipt would be a fabricated provenance record.
        """
        if asset is not None:
            for candidate in self._receipts:
                if candidate.raw_sha256 == asset.raw_sha256:
                    return candidate
        if self._receipts:
            return self._receipts[-1]
        raise RuntimeError(
            "no receipt available; call synthesize_speech() first"
        )

    def synthesize_speech(
        self,
        request: SpeechRequest,
        *,
        retry_reason: Optional[str] = None,
        attempt: int = 1,
        retry_from: Optional[Path] = None,
    ) -> SpeechOutcome:
        """Produce narration, reuse a valid cached asset, or raise.

        Order matters and is part of the contract:

        1. build the spoken text and the fingerprint
        2. resolve and verify the cache
        3. **only if a provider call is genuinely needed**, run the billing gate

        The cache is checked before the billing gate on purpose. A valid cached
        asset needs no provider request, so it must not consume quota, must not
        need network access, and must work offline.

        Raises:
            BillingBlocked: the pre-flight could not prove included-plan billing.
            CapabilityNotSupported: no official CLI on this host.
            RuntimeError: a retry without a changed input, or a failed generation.
        """
        if not self._cli:
            from contentops.media.contract import CapabilityNotSupported

            raise CapabilityNotSupported(
                "official MiniMax CLI not on PATH; run: npm install -g mmx-cli"
            )

        lexicon = self.lexicon_for(request.language)
        spoken_text = request.spoken_text or lexicon.spoken_text(request.display_text)
        voice = request.voice or DEFAULT_VOICES.get(request.language, DEFAULT_VOICES["en"])
        model = request.model or self._model

        # The fingerprint must describe what the voice actually says, which is
        # the flattened single-line form the CLI will receive.
        cli_text = flatten_for_cli(spoken_text)

        fingerprint = speech_fingerprint(
            provider=PROVIDER_NAME,
            product=PRODUCT,
            plan=PLAN,
            model=model,
            voice=voice,
            spoken_text=cli_text,
            lexicon_component=lexicon.fingerprint_component(),
            speed=request.speed,
            text_normalization=request.text_normalization,
            normalisation_target_lufs=NORMALISATION_TARGET_LUFS,
            normalisation_true_peak_db=NORMALISATION_TRUE_PEAK_DB,
        )

        # A retry must change a generation input, not merely carry a note.
        # Checked before any billing or provider call.
        previous_record = self._validate_attempt(
            attempt, retry_reason, fingerprint, retry_from
        )

        self._work_dir.mkdir(parents=True, exist_ok=True)
        raw_path = (self._work_dir / f"narration-{fingerprint[:16]}-raw.wav").resolve()
        normalized_path = (self._work_dir / f"narration-{fingerprint[:16]}.wav").resolve()
        sidecar_path = sidecar_for(normalized_path)

        if not request.force:
            cached = self._reuse(
                normalized_path=normalized_path,
                raw_path=raw_path,
                sidecar_path=sidecar_path,
                fingerprint=fingerprint,
            )
            if cached is not None:
                return cached

        # Only now, with a provider call actually pending, does billing matter.
        # authorize() keeps the whole verdict: this is the decision that permitted
        # the call, and it is what the receipt must record.
        preflight = self._guard.authorize(modality="speech")
        quota_before = preflight.quota

        import time

        last_error = ""
        for current in range(attempt, MAX_ATTEMPTS + 1):
            if current > attempt:
                # Only reachable if the caller drove multiple attempts in one
                # call; each still has to have changed something real.
                self._validate_attempt(current, retry_reason, fingerprint, retry_from)
            # Remove any previous file so a fresh mtime is meaningful and a
            # stale asset can never be mistaken for this run's output.
            for stale in (raw_path, normalized_path, sidecar_path):
                if stale.exists():
                    stale.unlink()

            # Durable retry evidence, written before the call so a crash still
            # leaves a record. An in-memory attribute cannot do this job: the
            # operator runs attempt 2 as a separate process.
            attempt_record = GenerationAttemptRecord(
                provider=PROVIDER_NAME,
                modality="speech",
                fingerprint=fingerprint,
                attempt_number=current,
            )
            attempt_path = attempt_record.write(self._work_dir)
            started = time.time()
            prefix = (
                list(self._cli) if isinstance(self._cli, (list, tuple)) else [self._cli]
            )
            command: List[str] = prefix + [
                "speech", "synthesize",
                "--model", model,
                "--text", cli_text,
                "--voice", voice,
                "--format", "wav",
                "--out", str(raw_path),
                "--quiet", "--non-interactive",
            ]
            if request.speed is not None:
                command += ["--speed", str(request.speed)]
            if request.text_normalization:
                command += ["--text-normalization"]
            command += lexicon.provider_arguments()

            result = hidden_run(command, env=self._require_child_env(), timeout=600)
            if result.returncode == 0:
                try:
                    verify_output(raw_path, not_before=started)
                except RuntimeError as exc:
                    last_error = (
                        f"{exc} | cli_stdout={(result.stdout or '').strip()[:200]} "
                        f"| cli_stderr={(result.stderr or '').strip()[:200]}"
                    )
                    attempt_record.mark_failed(
                        "unverifiable_output", last_error
                    ).write(self._work_dir)
                    raise RuntimeError(
                        f"speech generation could not be trusted on attempt "
                        f"{current}/{MAX_ATTEMPTS}: {last_error}"
                    ) from exc
                outcome = self._finish(
                    request=request,
                    lexicon=lexicon,
                    spoken_text=spoken_text,
                    cli_text=cli_text,
                    voice=voice,
                    model=model,
                    fingerprint=fingerprint,
                    preflight=preflight,
                    raw_path=raw_path,
                    normalized_path=normalized_path,
                    sidecar_path=sidecar_path,
                    attempt=current,
                    retry_reason=retry_reason,
                )
                attempt_record.mark_succeeded(
                    outcome.receipt.normalized_sha256 or "",
                    str(sidecar_path),
                ).write(self._work_dir)
                return outcome
            last_error = (result.stderr or "")[-400:]
            attempt_record.mark_failed(
                "provider_cli_nonzero_exit", last_error
            ).write(self._work_dir)
            if current == MAX_ATTEMPTS:
                break
            # A second attempt is only ever made by the caller, with a named
            # reason. This loop does not retry on its own; it stops and reports.
            raise RuntimeError(
                f"speech generation failed on attempt {current}/{MAX_ATTEMPTS}: "
                f"{last_error}. A second attempt requires a named failure reason "
                f"and a changed text, lexicon, voice or parameter."
            )

        raise RuntimeError(
            f"speech generation failed after {MAX_ATTEMPTS} attempts: {last_error}"
        )

    def credential_metadata(self) -> Dict[str, str]:
        """Safe credential metadata for receipts. Never the value."""
        if self._credential is None:
            return {"credential_class": CREDENTIAL_ABSENT, "credential_source": "UNBOUND"}
        return self._credential.safe_metadata()

    def _require_child_env(self) -> Dict[str, str]:
        """Return the bound child environment, or refuse to generate.

        Failing closed matters here more than anywhere else in this module: an
        unbound child would quietly discover its own credential, and the gate
        would be authorising a key the provider never uses.
        """
        if self._child_env is None:
            raise CredentialBindingError(
                "no credential is bound to the provider transport. Build the "
                "provider with transport_credential=resolve_credential() so the "
                "billing gate and the child use the same key. Refusing to "
                "generate rather than let the child pick one itself."
            )
        return self._child_env

    # -- internals ---------------------------------------------------------

    def _validate_attempt(
        self,
        attempt: int,
        retry_reason: Optional[str],
        fingerprint: str,
        retry_from: Optional[Path],
    ) -> Optional[GenerationAttemptRecord]:
        """Refuse a retry that is only a note, before any billing or provider call.

        Attempt 2 requires **all three**:

        - a named failure reason
        - a durable attempt record proving attempt 1 actually failed
        - a generation fingerprint that differs from that record's

        The record is mandatory rather than optional. Comparing against an
        in-memory attribute only worked when both attempts ran inside one Python
        process, and the real workflow is two commands, so an identical attempt 2
        used to pass straight through.

        Returns the loaded previous record so the caller can chain from it.
        """
        if attempt <= 1:
            return None
        if attempt > MAX_ATTEMPTS:
            raise RuntimeError(
                f"attempt {attempt} exceeds the maximum of {MAX_ATTEMPTS}"
            )
        if not (retry_reason or "").strip():
            raise RuntimeError(
                f"attempt {attempt} requires a named failure reason "
                f"(retry_reason); refusing to retry blindly"
            )
        if retry_from is None:
            raise RuntimeError(
                "attempt 2 requires --retry-from pointing at the attempt record "
                "of a failed first attempt. A reason alone is not evidence: the "
                "previous fingerprint has to survive the process boundary."
            )

        try:
            record = load_attempt_record(Path(retry_from))
        except AttemptRecordError as exc:
            raise RuntimeError(f"retry record is not usable: {exc}") from exc

        if record.provider != PROVIDER_NAME:
            raise RuntimeError(
                f"retry record provider {record.provider!r} does not match "
                f"{PROVIDER_NAME!r}"
            )
        if record.modality != "speech":
            raise RuntimeError(
                f"retry record modality {record.modality!r} is not 'speech'"
            )
        if record.attempt_number != 1:
            raise RuntimeError(
                f"retry record must describe attempt 1, got "
                f"attempt_number={record.attempt_number}"
            )
        if record.status != STATUS_FAILED:
            raise RuntimeError(
                f"retry record status is {record.status!r}; only a FAILED first "
                f"attempt may be retried"
            )
        if record.fingerprint == fingerprint:
            raise RuntimeError(
                "attempt 2 must change a generation input (spoken text, "
                "lexicon, voice, model or speed). The fingerprint is unchanged "
                f"({fingerprint[:16]}), so this would be an identical retry."
            )
        return record

    def _reuse(
        self,
        *,
        normalized_path: Path,
        raw_path: Path,
        sidecar_path: Path,
        fingerprint: str,
    ) -> Optional[SpeechOutcome]:
        """Reuse a cached asset, but only with truthful provenance.

        The previous implementation returned an asset with a blank voice, blank
        text hashes and the English lexicon version regardless of what was
        actually requested. That is fabricated provenance, so a sidecar receipt
        written next to the asset is now the only source of reuse metadata.

        The cache is rejected unless **all** of these hold:

        - the normalised asset exists and passes technical QC
        - the sidecar exists and parses
        - the sidecar fingerprint matches the current fingerprint
        - the normalised file hash still matches the sidecar
        - the raw file, if present, still matches its recorded hash

        Anything else is a cache miss. A missing, corrupt or mismatched sidecar
        must never be papered over with invented values.
        """
        if not normalized_path.is_file():
            return None
        payload = load_sidecar(sidecar_path)
        if not sidecar_is_complete(payload):
            return None
        assert payload is not None
        if payload.get("fingerprint") != fingerprint:
            return None
        expected_norm = payload.get("normalized_sha256")
        try:
            actual_norm = sha256_file(normalized_path)
        except OSError:
            return None
        if actual_norm != expected_norm:
            return None
        recorded_raw = payload.get("raw_sha256") or ""
        if raw_path.is_file() and recorded_raw:
            try:
                if sha256_file(raw_path) != recorded_raw:
                    return None
            except OSError:
                return None

        from contentops.media.audio import measure_audio

        qc = technical_qc(normalized_path, expected_sample_rate_hz=32000)
        if not qc.get("approved"):
            return None
        measured = measure_audio(normalized_path)

        stored_qc = payload.get("technical_qc") or {}
        stored_sem = payload.get("semantic_qc") or {
            "status": "SKIPPED",
            "reason": "carried from the generating run",
        }

        asset = SpeechAsset(
            raw_path=str(raw_path) if raw_path.is_file() else str(normalized_path),
            normalized_path=str(normalized_path),
            model=payload.get("model") or self._model,
            voice=payload.get("voice") or "",
            display_text_sha256=payload.get("display_text_sha256") or "",
            spoken_text_sha256=payload.get("spoken_text_sha256") or "",
            raw_sha256=recorded_raw,
            normalized_sha256=actual_norm,
            duration_s=measured.duration_s,
            sample_rate_hz=measured.sample_rate_hz,
            channels=measured.channels,
            codec=measured.codec,
            peak_before_db=(payload.get("peak_before_db")),
            peak_after_db=measured.peak_db,
            loudness_before=payload.get("loudness_before"),
            loudness_after=measured.integrated_lufs,
            technical_qc=stored_qc or qc,
            semantic_qc=stored_sem,
            approved=True,
        )
        # The returned receipt is the ORIGINAL generation receipt, restored from
        # the immutable sidecar. Rebuilding it here would overwrite quota_before,
        # quota_after and the original attempt number, destroying the evidence
        # that this asset was actually paid for out of plan entitlement.
        receipt = _receipt_from_payload(
            asset=asset, payload=payload, fingerprint=fingerprint
        )
        # Restore provider state as well as the receipt. Without this a *fresh*
        # provider that happened to hit the cache would still raise
        # "no receipt available" from receipt(), which breaks the contract every
        # caller relies on. _receipt() is deliberately NOT used here: it is the
        # generation path and would rewrite the immutable sidecar.
        self._remember_receipt(receipt)
        # Reuse is audited by an append-only event, never by mutating provenance.
        append_reuse_event(
            self._work_dir,
            {
                "event": "CACHE_REUSE",
                "fingerprint": fingerprint,
                "asset_sha256": actual_norm,
                "provider_call": False,
                "billing_call": False,
            },
        )
        return SpeechOutcome(asset=asset, receipt=receipt, reused=True)

    def _finish(
        self,
        *,
        request: SpeechRequest,
        lexicon: PronunciationLexicon,
        spoken_text: str,
        cli_text: str,
        voice: str,
        model: str,
        fingerprint: str,
        preflight: Any,
        raw_path: Path,
        normalized_path: Path,
        sidecar_path: Path,
        attempt: int,
        retry_reason: Optional[str],
    ) -> SpeechOutcome:
        from contentops.media.audio import measure_audio

        before = measure_audio(raw_path)
        normalisation = normalise_speech(raw_path, normalized_path)
        if not normalisation.get("ok"):
            raise RuntimeError(
                f"loudness normalisation failed: {normalisation.get('reason')}"
            )
        after = measure_audio(normalized_path)

        expected_chars = len(cli_text)
        expected_duration = max(1.0, expected_chars / 6.0)
        technical = technical_qc(
            normalized_path,
            expected_duration_s=expected_duration,
            expected_sample_rate_hz=32000,
        )
        semantic = backcheck_speech(normalized_path, cli_text).as_dict()

        asset = SpeechAsset(
            raw_path=str(raw_path),
            normalized_path=str(normalized_path),
            model=model,
            voice=voice,
            display_text_sha256=sha256_text(request.display_text),
            spoken_text_sha256=sha256_text(spoken_text),
            raw_sha256=sha256_file(raw_path),
            normalized_sha256=sha256_file(normalized_path),
            duration_s=after.duration_s,
            sample_rate_hz=after.sample_rate_hz,
            channels=after.channels,
            codec=after.codec,
            peak_before_db=before.peak_db,
            peak_after_db=after.peak_db,
            loudness_before=before.integrated_lufs,
            loudness_after=after.integrated_lufs,
            technical_qc=technical,
            semantic_qc=semantic,
            approved=bool(technical.get("approved")),
        )

        # Post-generation observation, deliberately separate from the
        # authorisation. A generation may consume the last of a window, and a
        # later balance-read failure must not rewrite that history.
        post_state: Dict[str, Any] = {}
        quota_after: Optional[QuotaSnapshot] = None
        try:
            quota_after = self._guard.read_quota()
            post_state["quota_after"] = {
                "bucket": quota_after.bucket if quota_after else None,
                "interval_remaining_percent": (
                    quota_after.interval_remaining_percent if quota_after else None
                ),
                "weekly_remaining_percent": (
                    quota_after.weekly_remaining_percent if quota_after else None
                ),
            }
        except Exception as exc:  # noqa: BLE001
            post_state["quota_after"] = {"error": type(exc).__name__}

        receipt = self._receipt(
            asset=asset,
            fingerprint=fingerprint,
            spoken_text=spoken_text,
            voice=voice,
            model=model,
            lexicon_version=lexicon.version,
            quota_before=preflight.quota,
            quota_after=quota_after,
            verdict=preflight.verdict,
            reasons=preflight.reasons,
            attempt=attempt,
            retry_reason=retry_reason,
            reused=False,
            post_generation_billing_state=post_state,
        )
        return SpeechOutcome(asset=asset, receipt=receipt)

    def _receipt(
        self,
        *,
        asset: SpeechAsset,
        fingerprint: str,
        spoken_text: str,
        voice: str,
        model: str,
        lexicon_version: str,
        quota_before: Optional[QuotaSnapshot],
        quota_after: Optional[QuotaSnapshot],
        verdict: str,
        reasons: List[str],
        attempt: int,
        retry_reason: Optional[str],
        reused: bool,
        post_generation_billing_state: Optional[Dict[str, Any]] = None,
        persist_sidecar: bool = True,
    ) -> SpeechReceipt:
        # A narration is never production-ready on its own: a human must hear it.
        human_review = "PENDING_FOUNDER_REVIEW"
        production_ready = False
        fallback = {
            "edge_tts_available": bool(shutil.which("edge-tts")),
            "used": False,
            "degraded": False,
            "policy": "explicit only; a silent swap to edge-tts is forbidden",
        }
        # Build the receipt, then record and persist it. Returning directly from
        # the constructor call here is what made receipt() raise "no receipt
        # available" after a successful synthesis.
        receipt = SpeechReceipt(
            provider=PROVIDER_NAME,
            product=PRODUCT,
            plan=PLAN,
            billing_mode=BILLING_MODE,
            payg_allowed=ALLOW_PAYG,
            credit_pack_allowed=ALLOW_CREDIT_PACK,
            transport="official_cli",
            transport_version=self._transport_version(),
            model=model,
            voice=voice,
            display_text_sha256=asset.display_text_sha256,
            spoken_text_sha256=asset.spoken_text_sha256 or sha256_text(spoken_text),
            lexicon_version=lexicon_version,
            fingerprint=fingerprint,
            quota_before=quota_before,
            quota_after=quota_after,
            billing_guard_verdict=verdict,
            billing_guard_reasons=list(reasons),
            post_generation_billing_state=post_generation_billing_state or {},
            technical_qc=asset.technical_qc,
            semantic_qc=asset.semantic_qc,
            raw_sha256=asset.raw_sha256,
            normalized_sha256=asset.normalized_sha256,
            attempt=attempt,
            retry_reason=retry_reason,
            fallback=fallback,
            production_ready=production_ready,
            human_review=human_review,
        )
        self._receipts.append(receipt)

        # Persist sanitised provenance next to the asset. Without this a later
        # cache hit would have to invent the voice, text hashes and lexicon
        # version, which is exactly the fabricated-provenance bug this replaces.
        asset_path = Path(asset.normalized_path or "")
        if persist_sidecar and asset_path.name:
            payload = receipt_to_dict(receipt)
            payload.update({
                "fingerprint": fingerprint,
                "normalized_sha256": asset.normalized_sha256,
                "raw_sha256": asset.raw_sha256,
                "display_text_sha256": asset.display_text_sha256,
                "spoken_text_sha256": asset.spoken_text_sha256,
                "lexicon_version": lexicon_version,
                "voice": voice,
                "model": model,
                "peak_before_db": asset.peak_before_db,
                "loudness_before": asset.loudness_before,
                "provider_call": not reused,
            })
            write_sidecar(sidecar_for(asset_path), payload)
        return receipt

    def _remember_receipt(self, receipt: SpeechReceipt) -> None:
        """Track a receipt in memory, without duplicating it.

        A provider instance that reuses the same asset many times must not grow an
        unbounded list of identical receipts. Persistence is untouched either way:
        this only affects in-memory lookup.
        """
        for existing in self._receipts:
            if existing.fingerprint == receipt.fingerprint:
                return
            if (
                receipt.normalized_sha256
                and existing.normalized_sha256 == receipt.normalized_sha256
            ):
                return
        self._receipts.append(receipt)

    def _transport_version(self) -> str:
        if not self._cli:
            return "UNKNOWN"
        prefix = (
            list(self._cli) if isinstance(self._cli, (list, tuple)) else [self._cli]
        )
        env = self._child_env if self._child_env is not None else None
        result = hidden_run(prefix + ["--version"], env=env, timeout=60)
        return (result.stdout or "").strip() or "UNKNOWN"


def _receipt_from_payload(
    *, asset: SpeechAsset, payload: Dict[str, Any], fingerprint: str
) -> SpeechReceipt:
    """Rebuild the original generation receipt from an immutable sidecar."""

    def snapshot(value: Any) -> Optional[QuotaSnapshot]:
        if not isinstance(value, dict):
            return None
        return QuotaSnapshot(
            bucket=value.get("bucket"),
            interval_remaining_percent=value.get("interval_remaining_percent"),
            weekly_remaining_percent=value.get("weekly_remaining_percent"),
            modality_breakdown=value.get("modality_breakdown") or {},
        )

    post_state = payload.get("post_generation_billing_state") or {}
    return SpeechReceipt(
        provider=payload["provider"],
        product=payload["product"],
        plan=payload["plan"],
        billing_mode=payload.get("billing_mode", BILLING_MODE),
        payg_allowed=bool(payload.get("payg_allowed", ALLOW_PAYG)),
        credit_pack_allowed=bool(payload.get("credit_pack_allowed", ALLOW_CREDIT_PACK)),
        transport=payload.get("transport", "official_cli"),
        transport_version=payload.get("transport_version", "UNKNOWN"),
        model=payload["model"],
        voice=payload["voice"],
        display_text_sha256=payload["display_text_sha256"],
        spoken_text_sha256=payload["spoken_text_sha256"],
        lexicon_version=payload["lexicon_version"],
        fingerprint=fingerprint,
        quota_before=snapshot(payload.get("quota_before")),
        quota_after=snapshot(payload.get("quota_after")),
        billing_guard_verdict=payload["billing_guard_verdict"],
        billing_guard_reasons=list(payload.get("billing_guard_reasons") or []),
        post_generation_billing_state=post_state,
        technical_qc=payload.get("technical_qc") or {},
        semantic_qc=payload.get("semantic_qc") or {},
        raw_sha256=payload["raw_sha256"],
        normalized_sha256=payload["normalized_sha256"],
        attempt=int(payload.get("attempt") or 1),
        retry_reason=payload.get("retry_reason"),
        fallback=payload.get("fallback") or {},
        production_ready=bool(payload.get("production_ready", False)),
        human_review=payload.get("human_review", "PENDING_FOUNDER_REVIEW"),
    )


def receipt_to_dict(receipt: SpeechReceipt) -> Dict[str, Any]:
    """Serialise a receipt, including the frozen quota snapshots."""

    def snapshot(value: Optional[QuotaSnapshot]) -> Optional[Dict[str, Any]]:
        if value is None:
            return None
        return {
            "bucket": value.bucket,
            "interval_remaining_percent": value.interval_remaining_percent,
            "weekly_remaining_percent": value.weekly_remaining_percent,
            "modality_breakdown": value.modality_breakdown,
        }

    return {
        "provider": receipt.provider,
        "product": receipt.product,
        "plan": receipt.plan,
        "billing_mode": receipt.billing_mode,
        "payg_allowed": receipt.payg_allowed,
        "credit_pack_allowed": receipt.credit_pack_allowed,
        "credential_recorded": "credential_class only; never a value",
        "transport": receipt.transport,
        "transport_version": receipt.transport_version,
        "model": receipt.model,
        "voice": receipt.voice,
        "display_text_sha256": receipt.display_text_sha256,
        "spoken_text_sha256": receipt.spoken_text_sha256,
        "lexicon_version": receipt.lexicon_version,
        "fingerprint": receipt.fingerprint,
        "quota_before": snapshot(receipt.quota_before),
        "quota_after": snapshot(receipt.quota_after),
        "billing_guard_verdict": receipt.billing_guard_verdict,
        "billing_guard_reasons": receipt.billing_guard_reasons,
        "post_generation_billing_state": receipt.post_generation_billing_state,
        "technical_qc": receipt.technical_qc,
        "semantic_qc": receipt.semantic_qc,
        "raw_sha256": receipt.raw_sha256,
        "normalized_sha256": receipt.normalized_sha256,
        "attempt": receipt.attempt,
        "retry_reason": receipt.retry_reason,
        "fallback": receipt.fallback,
        "production_ready": receipt.production_ready,
        "human_review": receipt.human_review,
    }