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
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from process_utils import hidden_run  # noqa: E402

from contentops.media.asr_backcheck import backcheck_speech  # noqa: E402
from contentops.media.audio import (  # noqa: E402
    NORMALISATION_TARGET_LUFS,
    NORMALISATION_TRUE_PEAK_DB,
    normalise_speech,
    technical_qc,
)
from contentops.media.billing_guard import BillingGuard  # noqa: E402
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

DEFAULT_MODEL = "speech-2.8-hd"
DEFAULT_VOICES = {
    "zh": "Chinese (Mandarin)_Reliable_Executive",
    "en": "English_expressive_narrator",
}


def resolve_cli() -> Optional[str]:
    """Absolute path to the official CLI launcher.

    On Windows the npm install produces ``mmx.cmd`` shims that CreateProcess
    cannot resolve from a bare ``mmx``, so resolution happens once here.
    """
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
        cli: Optional[str] = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._guard = guard
        self._work_dir = Path(work_dir)
        self._cli = cli or resolve_cli()
        self._model = model
        self._lexicons = {
            "zh": default_zh_lexicon(),
            "en": default_en_lexicon(),
        }
        self._receipts: List[SpeechReceipt] = []

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
        result = hidden_run([cli, "--version"], timeout=60)
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
    ) -> SpeechOutcome:
        """Produce narration, or raise.

        Raises:
            BillingBlocked: the pre-flight could not prove included-plan billing.
            CapabilityNotSupported: no official CLI on this host.
            RuntimeError: both permitted attempts failed.
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

        # Fail-closed gate immediately before generation, not once per process.
        quota_before = self._guard.require_safe()

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

        self._work_dir.mkdir(parents=True, exist_ok=True)
        raw_path = (self._work_dir / f"narration-{fingerprint[:16]}-raw.wav").resolve()
        normalized_path = (self._work_dir / f"narration-{fingerprint[:16]}.wav").resolve()

        cached = self._reuse(normalized_path, raw_path, fingerprint)
        if cached is not None and not request.force:
            return cached

        import time

        last_error = ""
        for current in range(attempt, MAX_ATTEMPTS + 1):
            # Remove any previous file so a fresh mtime is meaningful and a
            # stale asset can never be mistaken for this run's output.
            for stale in (raw_path, normalized_path):
                if stale.exists():
                    stale.unlink()

            started = time.time()
            command: List[str] = [
                self._cli, "speech", "synthesize",
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

            result = hidden_run(command, timeout=600)
            if result.returncode == 0:
                try:
                    verify_output(raw_path, not_before=started)
                except RuntimeError as exc:
                    last_error = (
                        f"{exc} | cli_stdout={(result.stdout or '').strip()[:200]} "
                        f"| cli_stderr={(result.stderr or '').strip()[:200]}"
                    )
                    raise RuntimeError(
                        f"speech generation could not be trusted on attempt "
                        f"{current}/{MAX_ATTEMPTS}: {last_error}"
                    ) from exc
                return self._finish(
                    request=request,
                    lexicon=lexicon,
                    spoken_text=spoken_text,
                    cli_text=cli_text,
                    voice=voice,
                    model=model,
                    fingerprint=fingerprint,
                    quota_before=quota_before,
                    raw_path=raw_path,
                    normalized_path=normalized_path,
                    attempt=current,
                    retry_reason=retry_reason,
                )
            last_error = (result.stderr or "")[-400:]
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

    # -- internals ---------------------------------------------------------

    def _reuse(
        self, normalized_path: Path, raw_path: Path, fingerprint: str
    ) -> Optional[SpeechOutcome]:
        """Reuse a valid approved asset for an unchanged fingerprint."""
        if not normalized_path.is_file():
            return None
        qc = technical_qc(normalized_path, expected_sample_rate_hz=32000)
        if not qc.get("approved"):
            return None
        from contentops.media.audio import measure_audio

        measured = measure_audio(normalized_path)
        asset = SpeechAsset(
            raw_path=str(raw_path) if raw_path.is_file() else str(normalized_path),
            normalized_path=str(normalized_path),
            model=self._model,
            voice="",
            display_text_sha256="",
            spoken_text_sha256="",
            raw_sha256=sha256_file(raw_path) if raw_path.is_file() else "",
            normalized_sha256=sha256_file(normalized_path),
            duration_s=measured.duration_s,
            sample_rate_hz=measured.sample_rate_hz,
            channels=measured.channels,
            codec=measured.codec,
            peak_before_db=None,
            peak_after_db=measured.peak_db,
            loudness_before=None,
            loudness_after=measured.integrated_lufs,
            technical_qc=qc,
            semantic_qc={"status": "SKIPPED", "reason": "reused asset"},
            approved=True,
        )
        receipt = self._receipt(
            asset=asset,
            fingerprint=fingerprint,
            spoken_text="",
            voice="",
            model=self._model,
            lexicon_version=self.lexicon_for("en").version,
            quota_before=None,
            quota_after=None,
            verdict="SAFE_INCLUDED_PLAN",
            reasons=["reused cached asset; no provider call was made"],
            attempt=0,
            retry_reason=None,
            reused=True,
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
        quota_before: QuotaSnapshot,
        raw_path: Path,
        normalized_path: Path,
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

        quota_after: Optional[QuotaSnapshot] = None
        try:
            quota_after = self._guard.read_quota()
        except Exception:  # noqa: BLE001
            quota_after = None

        guard_result = self._guard.evaluate()
        receipt = self._receipt(
            asset=asset,
            fingerprint=fingerprint,
            spoken_text=spoken_text,
            voice=voice,
            model=model,
            lexicon_version=lexicon.version,
            quota_before=quota_before,
            quota_after=quota_after,
            verdict=guard_result.verdict,
            reasons=guard_result.reasons,
            attempt=attempt,
            retry_reason=retry_reason,
            reused=False,
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
        return SpeechReceipt(
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
        return receipt

    def _transport_version(self) -> str:
        if not self._cli:
            return "UNKNOWN"
        result = hidden_run([self._cli, "--version"], timeout=60)
        return (result.stdout or "").strip() or "UNKNOWN"


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