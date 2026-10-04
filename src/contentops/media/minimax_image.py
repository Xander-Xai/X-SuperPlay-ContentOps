"""MiniMax M Plan image generation, with evidence-safe provenance.

What this module is careful about
---------------------------------
Four things, each of which has a specific failure it prevents:

1. **The container is sniffed, never assumed.** M2.0 measured the provider
   returning JPEG bytes from a ``.png`` request. The requested extension and the
   detected container are both recorded, and the canonical file is named for what
   the bytes actually are. See :mod:`contentops.media.image_container`.

2. **The credential is resolved once and bound to the child.** The billing gate
   and the ``mmx`` process must use the same key. See
   :mod:`contentops.media.credentials`.

3. **The cache is checked before the billing gate.** A valid cached image needs
   no provider request, so it must not consume quota, need network access, or
   work only when online.

4. **The receipt is immutable.** The generation sidecar records what was paid
   for. Reuse restores it and never rewrites it; reuse activity goes to an
   append-only event log instead.

Order of operations in :meth:`generate_image`, and why
------------------------------------------------------
::

    validate dimensions      -> free, catches typos before any billing read
    build fingerprint
    validate retry evidence  -> a blind retry is refused before billing
    resolve the cache        -> a hit needs neither billing nor provider
    authorize(modality=image) -> only now, with a provider call genuinely pending
    write STARTED record     -> survives a crash
    run mmx image generate
    verify the output file   -> exit 0 is not semantic success
    sniff container, QC, receipt

Dimension validation deliberately precedes the billing gate. The official CLI
also validates them, but only in the second position: an operator typo would
already have cost a billing read by then.

Transport
---------
The official CLI, verified present on the host:

- ``mmx image generate --prompt <text>``
- ``--model`` is implicit; ``image-01`` is the default
- ``--width`` / ``--height``: range [512, 2048], multiples of 8, ``image-01`` only
- ``--seed <n>`` for reproducibility
- ``--out <path>`` for an exact path, single image only
- ``--output json`` for structured output

``--api-key`` is deliberately **never** used: argv is visible to anything on the
host, and the child environment already carries the authorised key.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# The transport layer lives in scripts/ and must be imported through the one
# sanctioned path, so that no provider can spawn a process directly and no
# console window can appear on Windows.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from process_utils import hidden_run  # noqa: E402

from contentops.media.attempts import (  # noqa: E402
    STATUS_FAILED,
    AttemptRecordError,
    GenerationAttemptRecord,
    append_reuse_event,
    load_attempt_record,
)
from contentops.media.billing_guard import BillingGuard  # noqa: E402
from contentops.media.credentials import CredentialBinding, ResolvedCredential  # noqa: E402
from contentops.media.image_contract import (
    ImageAsset,
    ImageOutcome,
    ImageProvider,
    ImageReceipt,
    ImageRequest,
)
from contentops.media.image_container import (
    CANONICAL_EXTENSIONS,
    ImageContainerError,
    canonical_extension_for,
    sniff_image_file,
)
from contentops.media.image_fingerprint import image_fingerprint, validate_dimensions
from contentops.media.mplan_identity import (
    ALLOW_CREDIT_PACK,
    ALLOW_PAYG,
    BILLING_MODE,
    MAX_ATTEMPTS,
    PLAN,
    PRODUCT,
    PROVIDER_NAME,
)
from contentops.media.text_contamination import assess_text_contamination
from contentops.media.transport import (
    load_sidecar,
    resolve_cli,
    sidecar_for,
    verify_output,
    write_sidecar,
)

__all__ = [
    "DEFAULT_IMAGE_MODEL",
    "PRIMARY_PORTRAIT_HEIGHT",
    "PRIMARY_PORTRAIT_WIDTH",
    "REQUIRED_IMAGE_SIDECAR_FIELDS",
    "MiniMaxMPlanImageProvider",
    "image_receipt_to_dict",
    "receipt_to_dict",
]

DEFAULT_IMAGE_MODEL = "image-01"

#: Primary ContentOps use case is portrait short-form video, so the default
#: request is 9:16. Both values are within [512, 2048] and multiples of 8.
PRIMARY_PORTRAIT_WIDTH = 768
PRIMARY_PORTRAIT_HEIGHT = 1360

#: 9:16. Compared with a tolerance, never exactly: a provider may return nearby
#: dimensions and that is still a usable video frame.
PORTRAIT_ASPECT = 9 / 16

#: Extension ContentOps asks the CLI to write. It is a *request*, recorded for
#: comparison with reality, not a claim about the bytes.
REQUESTED_EXTENSION = ".png"

TRANSPORT = "official_cli"
TRANSPORT_PACKAGE = "mmx-cli"

#: Smallest plausible generated image. Anything smaller is a truncated response
#: or an error page, not a render.
MIN_OUTPUT_BYTES = 1024

#: Fields a cached image receipt must carry before it may be reused.
#:
#: ``requested_*`` and ``detected_*`` are both required, because the whole point
#: is that a mismatch between them stays visible. A cache hit that filled a blank
#: field with a default would be fabricated provenance.
REQUIRED_IMAGE_SIDECAR_FIELDS: Tuple[str, ...] = (
    "provider",
    "product",
    "plan",
    "model",
    "prompt_sha256",
    "fingerprint",
    "detected_container",
    "canonical_path",
    "canonical_extension",
    "requested_extension",
    "output_sha256",
    "width",
    "height",
    "technical_qc",
    "billing_guard_verdict",
    "transport",
    "transport_version",
    "billing_mode",
)

#: Fields whose value must be a non-empty string.
NON_BLANK_IMAGE_SIDECAR_FIELDS: Tuple[str, ...] = (
    "provider", "product", "plan", "model", "prompt_sha256", "fingerprint",
    "detected_container", "canonical_extension", "requested_extension",
    "output_sha256", "billing_guard_verdict", "transport", "transport_version",
    "billing_mode",
)

#: Fields that must carry an exact integer.
INTEGER_IMAGE_SIDECAR_FIELDS: Tuple[str, ...] = ("width", "height", "attempt")


def image_sidecar_is_complete(payload: Optional[Dict[str, Any]]) -> bool:
    """True when a cached image receipt carries every required field."""
    if not isinstance(payload, dict):
        return False
    for name in REQUIRED_IMAGE_SIDECAR_FIELDS:
        if name not in payload:
            return False
    for name in NON_BLANK_IMAGE_SIDECAR_FIELDS:
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            return False
    for name in INTEGER_IMAGE_SIDECAR_FIELDS:
        value = payload.get(name)
        if not isinstance(value, int) or isinstance(value, bool):
            return False
    if not isinstance(payload.get("technical_qc"), dict):
        return False
    # The governance fields are not optional and are not free-form: a generated
    # image that claims to be evidence would defeat the point of generating it.
    if payload.get("generated") is not True:
        return False
    if payload.get("evidence_capable") is not False:
        return False
    return True


class MiniMaxMPlanImageProvider(ImageProvider):
    """Image-only provider for the MiniMax M Plan Explore subscription."""

    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        guard: BillingGuard,
        work_dir: Path,
        cli: Any = None,
        model: str = DEFAULT_IMAGE_MODEL,
        transport_credential: Optional[ResolvedCredential] = None,
    ) -> None:
        self._guard = guard
        self._work_dir = Path(work_dir)
        self._cli = cli or resolve_cli()
        self._model = model
        # One resolved credential, bound once. The provider has no resolver of
        # its own, so the gate and the child cannot disagree about the key.
        self._binding = CredentialBinding(transport_credential)
        self._receipts: List[ImageReceipt] = []
        self._transport_version: Optional[str] = None

    # -- provider contract -------------------------------------------------

    def capabilities(self) -> Dict[str, Any]:
        return {
            "provider": PROVIDER_NAME,
            "transport": TRANSPORT,
            "transport_package": TRANSPORT_PACKAGE,
            "image": {
                "supported": True,
                "model": self._model,
                "models_documented": ["image-01", "image-01-live"],
                "width_range": [512, 2048],
                "dimension_multiple": 8,
                "custom_dimensions_model": "image-01",
                "seeded": True,
                "exact_output_path": True,
                "containers_observed": ["PNG", "JPEG"],
                "evidence": "M3.0 receipt, Issue #20",
            },
            "speech": {"supported": False, "owner": "Issue #19"},
            "video": {"supported": False, "owner": "Issue #22"},
            "evidence_capable": False,
        }

    def health(self) -> Dict[str, Any]:
        if not self._cli:
            return {
                "reachable": False,
                "reason": "official MiniMax CLI not on PATH",
                "install": "npm install -g mmx-cli",
            }
        prefix = list(self._cli) if isinstance(self._cli, (list, tuple)) else [self._cli]
        env = self._binding.require_env() if self._binding.is_bound else None
        result = hidden_run(prefix + ["--version"], env=env, timeout=60)
        verdict = self._guard.evaluate(modality="image")
        return {
            "reachable": result.returncode == 0,
            "transport_version": (result.stdout or "").strip(),
            "credential_class": verdict.credential_class,
            "billing_verdict": verdict.verdict,
            "billing_reasons": verdict.reasons,
        }

    def quota(self):
        snapshot = self._guard.read_quota()
        if snapshot is None:
            from contentops.media.contract import BillingBlocked

            raise BillingBlocked(
                "BLOCKED_BILLING_SOURCE_UNCERTAIN",
                ["included plan usage could not be read"],
            )
        return snapshot

    def receipt(self, asset: Optional[ImageAsset] = None) -> ImageReceipt:
        """Return the receipt for a produced image.

        Raises:
            RuntimeError: if nothing has been produced yet. Returning a
                placeholder receipt would be a fabricated provenance record.
        """
        if asset is not None:
            for candidate in self._receipts:
                if candidate.output_sha256 == asset.sha256:
                    return candidate
        if self._receipts:
            return self._receipts[-1]
        raise RuntimeError("no receipt available; call generate_image() first")

    def credential_metadata(self) -> Dict[str, str]:
        """Safe credential metadata for receipts. Never the value."""
        return self._binding.safe_metadata()

    # -- image -------------------------------------------------------------

    def generate_image(
        self,
        request: ImageRequest,
        *,
        retry_reason: Optional[str] = None,
        attempt: int = 1,
        retry_from: Optional[Path] = None,
    ) -> ImageOutcome:
        """Produce an image, reuse a valid cached one, or raise.

        Raises:
            CapabilityNotSupported: no official CLI on this host.
            DimensionRejected: the requested dimensions are invalid. Raised
                before any billing read, so a typo costs nothing.
            BillingBlocked: the pre-flight could not prove included-plan billing.
            RuntimeError: a retry without changed inputs, or a failed generation.
        """
        if not self._cli:
            from contentops.media.contract import CapabilityNotSupported

            raise CapabilityNotSupported(
                "official MiniMax CLI not on PATH; run: npm install -g mmx-cli"
            )

        model = request.model or self._model

        # Free validation first. The CLI would also reject these, but only after
        # a billing read, and the error could not name the ContentOps field.
        validate_dimensions(request.width, request.height, model=model)

        prompt = (request.prompt or "").strip()
        if not prompt:
            raise ValueError("prompt must not be empty")

        fingerprint = image_fingerprint(
            provider=PROVIDER_NAME,
            product=PRODUCT,
            plan=PLAN,
            model=model,
            prompt=prompt,
            width=request.width,
            height=request.height,
            seed=request.seed,
        )

        # A retry must change a real generation input, not merely carry a note.
        # Checked before any billing or provider call.
        self._validate_attempt(attempt, retry_reason, fingerprint, retry_from)

        self._work_dir.mkdir(parents=True, exist_ok=True)
        requested_path = self._work_dir / f"image-{fingerprint[:16]}{REQUESTED_EXTENSION}"

        if not request.force:
            cached = self._reuse(fingerprint=fingerprint, model=model, seed=request.seed)
            if cached is not None:
                return cached

        # Only now, with a provider call genuinely pending, does billing matter.
        # authorize() keeps the whole verdict: this is the decision that permitted
        # the call, and it is what the receipt must record.
        preflight = self._guard.authorize(modality="image")
        quota_before = preflight.quota

        # Remove anything left from a previous run so a fresh mtime is meaningful
        # and a stale image can never be mistaken for this run's output.
        self._purge(fingerprint)

        attempt_record = GenerationAttemptRecord(
            provider=PROVIDER_NAME,
            modality="image",
            fingerprint=fingerprint,
            attempt_number=attempt,
        )
        attempt_record.write(self._work_dir)

        prefix = list(self._cli) if isinstance(self._cli, (list, tuple)) else [self._cli]
        command: List[str] = prefix + [
            "image", "generate",
            "--prompt", prompt,
            "--model", model,
            "--width", str(request.width),
            "--height", str(request.height),
            "--n", "1",
            "--out", str(requested_path),
            "--quiet", "--non-interactive",
        ]
        if request.seed is not None:
            command += ["--seed", str(request.seed)]

        started = time.time()
        result = hidden_run(command, env=self._binding.require_env(), timeout=600)

        if result.returncode != 0:
            reason = (
                f"cli_stdout={(result.stdout or '').strip()[-300:]} "
                f"cli_stderr={(result.stderr or '').strip()[-300:]}"
            )
            attempt_record.mark_failed("provider_cli_nonzero_exit", reason).write(self._work_dir)
            raise RuntimeError(
                f"image generation failed on attempt {attempt}/{MAX_ATTEMPTS}: "
                f"{(result.stderr or '').strip()[-300:]}. A second attempt requires "
                f"a named failure reason and a changed prompt, seed, dimensions or model."
            )

        # Exit 0 is not semantic success. Verify the file, then verify the bytes.
        try:
            verify_output(
                requested_path, not_before=started, min_bytes=MIN_OUTPUT_BYTES
            )
            container = sniff_image_file(requested_path)
        except (RuntimeError, ImageContainerError) as exc:
            reason = (
                f"{exc} | cli_stdout={(result.stdout or '').strip()[:300]} "
                f"| cli_stderr={(result.stderr or '').strip()[:300]}"
            )
            attempt_record.mark_failed("unverifiable_output", reason).write(self._work_dir)
            raise RuntimeError(
                f"image generation could not be trusted on attempt "
                f"{attempt}/{MAX_ATTEMPTS}: {reason}"
            ) from exc

        # Preserve provider bytes. The only change is the *name*, so the file's
        # extension finally agrees with its contents. No transcode ever happens:
        # re-encoding would alter pixels and destroy the output hash relationship.
        canonical_extension = canonical_extension_for(container)
        canonical_path = self._work_dir / f"image-{fingerprint[:16]}{canonical_extension}"
        if requested_path != canonical_path:
            if canonical_path.exists():
                canonical_path.unlink()
            os.replace(requested_path, canonical_path)

        outcome = self._finish(
            request=request,
            prompt=prompt,
            model=model,
            fingerprint=fingerprint,
            preflight=preflight,
            canonical_path=canonical_path,
            requested_path=requested_path,
            container=container,
            attempt=attempt,
            retry_reason=retry_reason,
        )
        attempt_record.mark_succeeded(
            outcome.asset.sha256, str(sidecar_for(canonical_path))
        ).write(self._work_dir)
        return outcome

    # -- internals ---------------------------------------------------------

    def _validate_attempt(
        self,
        attempt: int,
        retry_reason: Optional[str],
        fingerprint: str,
        retry_from: Optional[Path],
    ) -> Optional[GenerationAttemptRecord]:
        """Refuse a retry that is only a note, before any billing or provider call.

        Attempt 2 requires **all three**: a named failure reason, a durable
        record proving attempt 1 actually failed, and a fingerprint that differs
        from that record's. The record is mandatory because the real workflow is
        two commands; an in-memory comparison only worked inside one process.
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
        if record.modality != "image":
            raise RuntimeError(
                f"retry record modality {record.modality!r} is not 'image'"
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
                "attempt 2 must change a generation input (prompt, seed, "
                f"dimensions or model). The fingerprint is unchanged "
                f"({fingerprint[:16]}), so this would be an identical retry."
            )
        return record

    def _candidate_paths(self, fingerprint: str) -> List[Tuple[Path, Path, str]]:
        """Every place a canonical image for this fingerprint could live."""
        found: List[Tuple[Path, Path, str]] = []
        for extension in sorted(set(CANONICAL_EXTENSIONS.values()) | {REQUESTED_EXTENSION}):
            candidate = self._work_dir / f"image-{fingerprint[:16]}{extension}"
            found.append((candidate, sidecar_for(candidate), extension))
        return found

    def _purge(self, fingerprint: str) -> None:
        for candidate, sidecar, _ in self._candidate_paths(fingerprint):
            for stale in (candidate, sidecar):
                if stale.exists():
                    stale.unlink()

    def _reuse(
        self,
        *,
        fingerprint: str,
        model: str,
        seed: Optional[int],
    ) -> Optional[ImageOutcome]:
        """Reuse a cached image, but only with truthful provenance.

        A cache hit requires **all** of:

        - the asset exists, and the sidecar parses and is schema-complete
        - the fingerprint matches
        - the file's SHA-256 matches ``output_sha256``
        - the sniffed container matches ``detected_container``
        - the decoded width and height match the receipt
        - ``model`` and ``seed`` match
        - ``generated`` is ``True`` and ``evidence_capable`` is ``False``

        Any mismatch is a cache miss. Nothing is filled in with a default: a
        missing field means the receipt cannot vouch for the asset, and
        inventing the value would be fabricated provenance.
        """
        from contentops.media.fingerprint import sha256_file
        from contentops.media.image_qc import technical_image_qc

        for candidate, sidecar_path, extension in self._candidate_paths(fingerprint):
            if not candidate.is_file():
                continue
            payload = load_sidecar(sidecar_path)
            if not image_sidecar_is_complete(payload):
                continue
            assert payload is not None

            if payload.get("fingerprint") != fingerprint:
                continue
            if payload.get("model") != model:
                continue
            if payload.get("seed") != seed:
                continue

            # A JPEG requested as .png is normal; a receipt that disagrees with
            # the bytes on disk is not.
            if payload.get("canonical_extension") != extension:
                continue

            try:
                actual_sha = sha256_file(candidate)
            except OSError:
                continue
            if actual_sha != payload.get("output_sha256"):
                continue

            try:
                detected = sniff_image_file(candidate)
            except ImageContainerError:
                continue
            if detected != payload.get("detected_container"):
                continue
            if canonical_extension_for(detected) != extension:
                continue

            qc = technical_image_qc(
                candidate,
                expected_width=payload.get("width"),
                expected_height=payload.get("height"),
                expected_aspect=PORTRAIT_ASPECT,
                require_container=detected,
            )
            if not qc.approved:
                continue
            if qc.width != payload.get("width") or qc.height != payload.get("height"):
                continue

            stored_signal = (payload.get("technical_qc") or {}).get(
                "text_contamination_suspected"
            )
            signal = stored_signal

            asset = ImageAsset(
                canonical_path=str(candidate),
                container=detected,
                width=int(payload["width"]),
                height=int(payload["height"]),
                sha256=actual_sha,
                technical_qc=qc.as_dict(),
                evidence_capable=False,
                generated=True,
            )
            receipt = self._receipt_from_payload(asset=asset, payload=payload)
            # Restore provider state as well as the receipt, so a *fresh* provider
            # that hit the cache can still answer receipt(). The generation path
            # _receipt() is deliberately not used: it would rewrite the
            # immutable sidecar.
            self._remember_receipt(receipt)
            append_reuse_event(
                self._work_dir,
                {
                    "event": "CACHE_REUSE",
                    "modality": "image",
                    "fingerprint": fingerprint,
                    "asset_sha256": actual_sha,
                    "container": detected,
                    "provider_call": False,
                    "billing_call": False,
                    "text_contamination_suspected": signal,
                },
            )
            return ImageOutcome(asset=asset, receipt=receipt, reused=True)
        return None

    def _finish(
        self,
        *,
        request: ImageRequest,
        prompt: str,
        model: str,
        fingerprint: str,
        preflight: Any,
        canonical_path: Path,
        requested_path: Path,
        container: str,
        attempt: int,
        retry_reason: Optional[str],
    ) -> ImageOutcome:
        from contentops.media.fingerprint import sha256_file, sha256_text
        from contentops.media.image_qc import technical_image_qc

        # Technical QC measures; it never approves on taste. `approved` here means
        # "technically sound", not "publishable".
        qc = technical_image_qc(
            canonical_path,
            expected_width=request.width,
            expected_height=request.height,
            expected_aspect=PORTRAIT_ASPECT,
            require_container=container,
        )
        if not qc.approved:
            raise RuntimeError(
                "the generated image failed technical QC and will not be "
                f"recorded as usable: {'; '.join(qc.reasons)}"
            )

        signal = assess_text_contamination(canonical_path)
        qc_dict = qc.as_dict()
        qc_dict["text_contamination_suspected"] = signal.suspected
        qc_dict["text_contamination_detail"] = signal.as_dict()

        output_sha = sha256_file(canonical_path)
        asset = ImageAsset(
            canonical_path=str(canonical_path),
            container=container,
            width=qc.width or request.width,
            height=qc.height or request.height,
            sha256=output_sha,
            technical_qc=qc_dict,
            evidence_capable=False,
            generated=True,
        )

        # Post-generation observation, deliberately separate from the
        # authorisation. A generation may consume the last of a window, and a
        # later balance-read failure must not rewrite that history.
        post_state: Dict[str, Any] = {}
        quota_after = None
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
            prompt_sha256=sha256_text(prompt),
            model=model,
            seed=request.seed,
            requested_width=request.width,
            requested_height=request.height,
            requested_path=str(requested_path),
            quota_before=preflight.quota,
            quota_after=quota_after,
            verdict=preflight.verdict,
            reasons=preflight.reasons,
            attempt=attempt,
            retry_reason=retry_reason,
        )
        write_sidecar(sidecar_for(canonical_path), receipt_to_dict(receipt))
        self._remember_receipt(receipt)
        return ImageOutcome(asset=asset, receipt=receipt, reused=False)

    def _receipt(
        self,
        *,
        asset: ImageAsset,
        fingerprint: str,
        prompt_sha256: str,
        model: str,
        seed: Optional[int],
        requested_width: int,
        requested_height: int,
        requested_path: str,
        quota_before: Any,
        quota_after: Any,
        verdict: str,
        reasons: List[str],
        attempt: int,
        retry_reason: Optional[str],
    ) -> ImageReceipt:
        return ImageReceipt(
            provider=PROVIDER_NAME,
            product=PRODUCT,
            plan=PLAN,
            billing_mode=BILLING_MODE,
            payg_allowed=ALLOW_PAYG,
            credit_pack_allowed=ALLOW_CREDIT_PACK,
            transport=TRANSPORT,
            transport_version=self._version(),
            model=model,
            prompt_sha256=prompt_sha256,
            seed=seed,
            requested_width=requested_width,
            requested_height=requested_height,
            width=asset.width,
            height=asset.height,
            requested_path=requested_path,
            requested_extension=REQUESTED_EXTENSION,
            detected_container=asset.container,
            canonical_path=asset.canonical_path,
            canonical_extension=canonical_extension_for(asset.container),
            output_sha256=asset.sha256,
            fingerprint=fingerprint,
            quota_before=quota_before,
            quota_after=quota_after,
            billing_guard_verdict=verdict,
            billing_guard_reasons=list(reasons),
            credential_class=self._binding.safe_metadata()["credential_class"],
            credential_source=self._binding.safe_metadata()["credential_source"],
            technical_qc=dict(asset.technical_qc),
            text_contamination_suspected=asset.technical_qc.get(
                "text_contamination_suspected"
            ),
            attempt=attempt,
            retry_reason=retry_reason,
            fallback={},
            # Technical QC passing is not production readiness. A Founder has to
            # look at it before it can carry a claim.
            production_ready=False,
            human_review="PENDING_FOUNDER_REVIEW",
            generated=True,
            evidence_capable=False,
            post_generation_billing_state={},
        )

    def _receipt_from_payload(
        self, *, asset: ImageAsset, payload: Dict[str, Any]
    ) -> ImageReceipt:
        """Rebuild the ORIGINAL generation receipt from the immutable sidecar.

        Rebuilding the *receipt* is correct; rebuilding it by re-running the
        generation is not. ``quota_before``, ``quota_after`` and the original
        attempt number must survive, or the evidence that this image came out of
        plan entitlement disappears on the first reuse.
        """
        def snapshot(value: Any):
            from contentops.media.contract import QuotaSnapshot

            if not isinstance(value, dict):
                return None
            return QuotaSnapshot(
                bucket=value.get("bucket"),
                interval_remaining_percent=value.get("interval_remaining_percent"),
                weekly_remaining_percent=value.get("weekly_remaining_percent"),
                modality_breakdown=value.get("modality_breakdown") or {},
            )

        return ImageReceipt(
            provider=str(payload["provider"]),
            product=str(payload["product"]),
            plan=str(payload["plan"]),
            billing_mode=str(payload["billing_mode"]),
            payg_allowed=bool(payload.get("payg_allowed", ALLOW_PAYG)),
            credit_pack_allowed=bool(payload.get("credit_pack_allowed", ALLOW_CREDIT_PACK)),
            transport=str(payload["transport"]),
            transport_version=str(payload["transport_version"]),
            model=str(payload["model"]),
            prompt_sha256=str(payload["prompt_sha256"]),
            seed=payload.get("seed"),
            requested_width=int(payload.get("requested_width") or asset.width),
            requested_height=int(payload.get("requested_height") or asset.height),
            width=asset.width,
            height=asset.height,
            requested_path=str(payload.get("requested_path") or ""),
            requested_extension=str(payload["requested_extension"]),
            detected_container=str(payload["detected_container"]),
            canonical_path=asset.canonical_path,
            canonical_extension=str(payload["canonical_extension"]),
            output_sha256=asset.sha256,
            fingerprint=str(payload["fingerprint"]),
            quota_before=snapshot(payload.get("quota_before")),
            quota_after=snapshot(payload.get("quota_after")),
            billing_guard_verdict=str(payload["billing_guard_verdict"]),
            billing_guard_reasons=list(payload.get("billing_guard_reasons") or []),
            credential_class=str(payload.get("credential_class") or "UNKNOWN"),
            credential_source=str(payload.get("credential_source") or "UNBOUND"),
            technical_qc=dict(payload.get("technical_qc") or {}),
            text_contamination_suspected=(payload.get("technical_qc") or {}).get(
                "text_contamination_suspected"
            ),
            attempt=int(payload["attempt"]),
            retry_reason=payload.get("retry_reason"),
            fallback=dict(payload.get("fallback") or {}),
            # Reuse does not upgrade readiness. The asset is the same asset, with
            # the same pending human review.
            production_ready=bool(payload.get("production_ready", False)),
            human_review=str(payload.get("human_review") or "PENDING_FOUNDER_REVIEW"),
            generated=True,
            evidence_capable=False,
            post_generation_billing_state=dict(payload.get("post_generation_billing_state") or {}),
        )

    def _remember_receipt(self, receipt: ImageReceipt) -> None:
        """Track a receipt in memory, without duplicating it."""
        for existing in self._receipts:
            if existing.fingerprint == receipt.fingerprint:
                return
            if existing.output_sha256 and existing.output_sha256 == receipt.output_sha256:
                return
        self._receipts.append(receipt)

    def _version(self) -> str:
        if self._transport_version:
            return self._transport_version
        prefix = list(self._cli) if isinstance(self._cli, (list, tuple)) else [self._cli]
        env = self._binding.require_env() if self._binding.is_bound else None
        result = hidden_run(prefix + ["--version"], env=env, timeout=60)
        self._transport_version = (result.stdout or "").strip() or "unknown"
        return self._transport_version


def _snapshot_to_dict(snapshot: Any) -> Optional[Dict[str, Any]]:
    if snapshot is None:
        return None
    return {
        "bucket": snapshot.bucket,
        "interval_remaining_percent": snapshot.interval_remaining_percent,
        "weekly_remaining_percent": snapshot.weekly_remaining_percent,
        "modality_breakdown": snapshot.modality_breakdown,
    }


def receipt_to_dict(receipt: ImageReceipt) -> Dict[str, Any]:
    """Serialise an image receipt. No credential value ever appears here."""
    return {
        "schema": "contentops.image-receipt/v1",
        "provider": receipt.provider,
        "product": receipt.product,
        "plan": receipt.plan,
        "billing_mode": receipt.billing_mode,
        "payg_allowed": receipt.payg_allowed,
        "credit_pack_allowed": receipt.credit_pack_allowed,
        "credential_class": receipt.credential_class,
        "credential_source": receipt.credential_source,
        "transport": receipt.transport,
        "transport_version": receipt.transport_version,
        "model": receipt.model,
        "prompt_sha256": receipt.prompt_sha256,
        "seed": receipt.seed,
        "requested_width": receipt.requested_width,
        "requested_height": receipt.requested_height,
        "width": receipt.width,
        "height": receipt.height,
        "requested_path": receipt.requested_path,
        "requested_extension": receipt.requested_extension,
        "detected_container": receipt.detected_container,
        "canonical_path": receipt.canonical_path,
        "canonical_extension": receipt.canonical_extension,
        "output_sha256": receipt.output_sha256,
        "fingerprint": receipt.fingerprint,
        "quota_before": _snapshot_to_dict(receipt.quota_before),
        "quota_after": _snapshot_to_dict(receipt.quota_after),
        "billing_guard_verdict": receipt.billing_guard_verdict,
        "billing_guard_reasons": list(receipt.billing_guard_reasons),
        "technical_qc": dict(receipt.technical_qc),
        "text_contamination_suspected": receipt.text_contamination_suspected,
        "attempt": receipt.attempt,
        "retry_reason": receipt.retry_reason,
        "fallback": dict(receipt.fallback),
        "production_ready": receipt.production_ready,
        "human_review": receipt.human_review,
        "generated": receipt.generated,
        "evidence_capable": receipt.evidence_capable,
        "post_generation_billing_state": dict(receipt.post_generation_billing_state),
    }


image_receipt_to_dict = receipt_to_dict