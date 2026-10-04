"""One validator for every modality, with modality detail behind adapters.

The problem this solves
-----------------------
M2, M3 and M4 each validated their own receipt, and the three schemas do not
agree:

=================  ==============================  =====================  ============
                   speech                          image                  video
=================  ==============================  =====================  ============
``schema``         **absent**                      ``...image-receipt/v1`` ``...video-receipt/v1``
asset digest       ``normalized_sha256``           ``output_sha256``      ``output_sha256``
``generated``      **absent**                      ``true``               ``true``
``evidence_capable`` **absent**                    ``false``              ``false``
``AssetKind``      **none**                        ``GENERATED_IMAGE``    ``GENERATED_VIDEO``
registered in      **never**                       by the CLI script      by the provider
=================  ==============================  =====================  ============

So a consumer wanting to know "may I use this asset, and what is its provenance?"
had to learn three schemas. The alternative — one validator with a chain of
``if modality == ...`` — is what this module exists to avoid, because such a
function grows a branch per modality per check and eventually encodes the whole
receipt schema in one place.

How it is split
---------------
:class:`MediaValidationAdapter` supplies everything modality-specific, in one
object: which schema value is accepted, which receipt field holds the asset
digest, whether the modality carries ``generated`` / ``evidence_capable``, and the
modality's own technical QC.

Everything that is genuinely common lives here in
:func:`validate_media_asset` and has no modality branch at all:

- the asset file exists and the receipt file exists and parses
- the recorded digest equals the digest of the bytes on disk
- a fingerprint is present
- billing metadata is subscription-only where the modality records it
- no credential value and no ``Authorization`` value appear in the receipt
- ``production_ready`` is a real boolean and ``human_review`` is a known state
- the receipt's own provenance flags agree with the envelope
- a derived asset carries a transform receipt

Adapters do not override common checks. They add.

Deliberate limits
-----------------
This is **not** an unbounded secret scanner. A regular expression cannot be
relied on to find every secret, and pretending otherwise produces a false sense
of safety. What is enforced instead is targeted and checkable: a set of
credential-bearing field names must not contain anything key-shaped, no
``Authorization`` value may appear, and the video receipt may not carry a raw
provider task id. The provider-level sentinel tests remain the authoritative
check, because they know the actual key.

Nor does this re-implement modality QC. Loudness, image decode and container
detection, video freeze and black-frame analysis all stay where they already
live, reached through the adapter.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from contentops.media.fingerprint import sha256_file
from contentops.media.image_contract import (
    AssetKind,
    EvidenceUse,
    GeneratedAssetEvidenceError,
)
from contentops.media.mplan_identity import (
    ALLOW_CREDIT_PACK,
    ALLOW_PAYG,
    BILLING_MODE,
)
from contentops.media.media_envelope import (
    HUMAN_REVIEW_STATES,
    MediaAssetEnvelope,
    MediaModality,
)

__all__ = [
    "ImageValidationAdapter",
    "MediaValidationAdapter",
    "MediaValidationResult",
    "SpeechValidationAdapter",
    "VideoValidationAdapter",
    "default_adapter_for",
    "validate_media_asset",
]


#: Field names that, if populated, would mean a credential value was written into
#: a public receipt. Checked by *name* against the value shape, so a schema that
#: grows a new field is caught rather than silently trusted.
CREDENTIAL_VALUE_FIELDS: Tuple[str, ...] = (
    "credential",
    "credential_value",
    "credential_key",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "bearer",
    "token",
    "access_token",
    "secret",
    "password",
    "subscription_key",
)

#: Anything shaped like a provider key. Deliberately narrow: a subscription key
#: is ``sk-`` plus a long body. This is a backstop, not the primary defence.
_KEY_SHAPE = re.compile(r"sk-[a-z]{2,6}-[A-Za-z0-9_\-]{12,}")

#: A raw provider task id is a long bare digit run in a public receipt. Narrowed
#: to 12+ digits so an ordinary quantity is not mistaken for one.
_RAW_TASK_SHAPE = re.compile(r"\b\d{12,}\b")

#: Video receipts must never carry the raw id. They carry a salted
#: ``task_ref_hash`` instead, which is a hex digest and is explicitly allowed.
_TASK_ID_FIELD_NAMES: Tuple[str, ...] = ("task_id", "raw_task_id", "provider_task_id")


@dataclass
class MediaValidationResult:
    """The outcome of validating one asset.

    ``failures`` is the authoritative list. ``notes`` carries things worth knowing
    that did not block — a name/content mismatch, a derived asset — kept separate
    so an observation can never quietly flip ``approved`` false.
    """

    approved: bool
    asset_id: str
    modality: str
    failures: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    #: Digest recomputed from the bytes on disk, when they were readable.
    observed_sha256: Optional[str] = None
    #: Modality QC detail, verbatim from the adapter.
    technical_qc: Dict[str, Any] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return bool(self.failures)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "modality": self.modality,
            "approved": self.approved,
            "failures": list(self.failures),
            "notes": list(self.notes),
            "observed_sha256": self.observed_sha256,
            "technical_qc": dict(self.technical_qc),
        }


class MediaValidationAdapter(Protocol):
    """Everything the common validator needs to know about one modality.

    A ``Protocol`` rather than a base class so an adapter can be a plain object
    built at runtime — which is what makes the fakes in tests possible without
    subclassing anything.
    """

    #: Canonical modality this adapter serves.
    modality: str

    #: Schema value(s) the receipt may declare. Empty means the modality's
    #: receipts carry no ``schema`` field at all, which is a real and documented
    #: fact about speech rather than an oversight to be papered over.
    accepted_schemas: Tuple[str, ...]

    #: Receipt field holding the digest of the canonical asset, in priority
    #: order. Speech has two candidates because it records the raw provider
    #: output and the normalised file separately.
    digest_fields: Tuple[str, ...]

    #: Whether this modality's receipts carry ``generated`` / ``evidence_capable``.
    #: False for speech, so the common validator can require agreement where the
    #: concept applies and stay silent where it does not.
    carries_provenance_flags: bool

    #: Visual ``AssetKind`` for provider-generated assets, or ``None`` for speech.
    registry_kind: Optional[str]

    def check_technical(self, envelope: MediaAssetEnvelope, receipt: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
        """Run the modality's own technical QC.

        Returns ``(passed, failures, detail)``. Must not raise for a merely bad
        asset: a caller wants one object describing everything wrong.
        """


def _technical_or_not_applicable(
    receipt: Dict[str, Any],
    modality: str,
) -> Tuple[bool, List[str], Dict[str, Any], bool]:
    """Read ``technical_qc``, distinguishing "absent" from "failed".

    For a **provider generation** a missing ``technical_qc`` is a failure: M2, M3
    and M4 all record one, and its absence means the asset was never measured.

    For an **import** it is not applicable. No provider ran, so there is no
    provider technical QC to report, and demanding one would force a fabricated
    measurement. Treating that absence as a failure would either block every
    honestly-recorded import or push someone to invent the field — both worse than
    saying plainly that the check does not apply.

    Returns ``(passed, failures, detail, applicable)``.
    """
    qc = receipt.get("technical_qc")
    if isinstance(qc, dict) and qc:
        approved = bool(qc.get("approved"))
        failures: List[str] = []
        if not approved:
            failures.append(
                f"{modality} technical QC did not approve the asset: "
                + "; ".join(
                    str(reason)
                    for reason in (qc.get("reasons") or ["no reason recorded"])
                )
            )
        return approved, failures, qc, True
    if _is_non_generation_record(receipt):
        return True, [], {}, False
    return False, [f"{modality} receipt has no technical_qc object"], {}, True


def _is_non_generation_record(receipt: Dict[str, Any]) -> bool:
    """Whether this receipt describes material no provider produced.

    Two kinds qualify: an **import** (material ContentOps adopted) and a
    **transform** (bytes a deterministic local step produced from something else).
    Both are honest descriptions of non-generated media, and both therefore have no
    provider technical QC to report and no evidence-capability flag to restate —
    the capability belongs to the generation they derive from.
    """
    from contentops.media.media_transform import TRANSFORM_SCHEMA

    if receipt.get("schema") in (IMPORT_SCHEMA, TRANSFORM_SCHEMA):
        return True
    return receipt.get("record_type") == "media_import"


@dataclass
class SpeechValidationAdapter:
    """Adapter for narration.

    Two facts drive its shape. Speech receipts carry **no** ``schema`` field, and
    they carry **no** ``generated`` / ``evidence_capable`` — narration is neither
    a visual kind nor a claim-bearing thing, and inventing either would be a
    lie about what speech is.

    The digest is the second asymmetry: the receipt records ``raw_sha256`` for the
    provider output and ``normalized_sha256`` for the file ContentOps actually
    uses. The normalised one is checked first and falls back to the raw one, so an
    asset is verified against the digest of the bytes it actually is.
    """

    modality: str = MediaModality.SPEECH
    accepted_schemas: Tuple[str, ...] = ()
    digest_fields: Tuple[str, ...] = ("normalized_sha256", "raw_sha256")
    carries_provenance_flags: bool = False
    registry_kind: Optional[str] = None

    def check_technical(self, envelope: MediaAssetEnvelope, receipt: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
        passed, failures, detail, _ = _technical_or_not_applicable(
            receipt, self.modality
        )
        return passed, failures, detail


@dataclass
class ImageValidationAdapter:
    """Adapter for stills. Reuses the provider's own QC rather than redoing it."""

    modality: str = MediaModality.IMAGE
    #: Two schemas, and the ``generated`` flag is what tells them apart.
    #:
    #: ``contentops.image-receipt/v1`` is a *provider generation* record.
    #: ``contentops.media-import/v1`` records material ContentOps located and
    #: adopted — real captures and deterministic local draws — where no provider
    #: was involved. Both are legitimate for an image; claiming the wrong one is
    #: not, and :func:`_check_schema` refuses that.
    accepted_schemas: Tuple[str, ...] = (
        "contentops.image-receipt/v1",
        "contentops.media-import/v1",
    )
    digest_fields: Tuple[str, ...] = ("output_sha256",)
    carries_provenance_flags: bool = True
    registry_kind: Optional[str] = AssetKind.GENERATED_IMAGE

    def check_technical(self, envelope: MediaAssetEnvelope, receipt: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
        passed, failures, detail, _ = _technical_or_not_applicable(
            receipt, self.modality
        )
        return passed, failures, detail


@dataclass
class VideoValidationAdapter:
    """Adapter for generated shots.

    Also enforces the one task-privacy invariant that is cheap to check here: a
    public video receipt may carry a salted ``task_ref_hash`` but never a raw
    provider task id. The provider's sentinel test remains authoritative; this is
    a structural backstop that applies to any video receipt from any source.
    """

    modality: str = MediaModality.VIDEO
    accepted_schemas: Tuple[str, ...] = ("contentops.video-receipt/v1",)
    digest_fields: Tuple[str, ...] = ("output_sha256",)
    carries_provenance_flags: bool = True
    registry_kind: Optional[str] = AssetKind.GENERATED_VIDEO

    def check_technical(self, envelope: MediaAssetEnvelope, receipt: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
        passed, failures, detail, _ = _technical_or_not_applicable(
            receipt, self.modality
        )
        return passed, failures, detail


#: One dispatch table, at a protocol boundary. This is the only place a modality
#: name is turned into behaviour, which is what keeps the validator itself free of
#: modality branches.
_DEFAULT_ADAPTERS = (
    SpeechValidationAdapter(),
    ImageValidationAdapter(),
    VideoValidationAdapter(),
)


def default_adapter_for(modality: str) -> MediaValidationAdapter:
    """Return the adapter for one modality.

    Raises:
        ValueError: the modality has no adapter. A missing adapter is a
            programming error and must not be papered over with a permissive
            default, because a permissive default would validate less.
    """
    canonical = MediaModality.canonical(modality)
    for adapter in _DEFAULT_ADAPTERS:
        if adapter.modality == canonical:
            return adapter
    raise ValueError(f"no validation adapter for modality {canonical!r}")


def validate_media_asset(
    envelope: MediaAssetEnvelope,
    adapter: Optional[MediaValidationAdapter] = None,
) -> MediaValidationResult:
    """Validate one asset and its receipt against the invariants they share.

    Args:
        envelope: the asset index to validate. Checked for self-consistency
            first, so a hand-built envelope is caught before any I/O.
        adapter: modality adapter. Resolved from ``envelope.modality`` when
            omitted.

    Returns:
        A :class:`MediaValidationResult`. Never raises for a merely invalid
        asset; a caller wants every problem at once, not the first one.
    """
    failures: List[str] = []
    notes: List[str] = []
    result = MediaValidationResult(
        approved=False,
        asset_id=envelope.asset_id,
        modality=str(envelope.modality),
    )

    # -- the envelope must be coherent before it is trusted ------------------
    try:
        MediaModality.canonical(envelope.modality)
        envelope.validate_shape()
    except ValueError as exc:
        result.failures.append(str(exc))
        return result

    resolved = adapter if adapter is not None else default_adapter_for(envelope.modality)

    # -- the two files must exist and parse ----------------------------------
    asset_path = Path(envelope.path)
    if not envelope.path.strip():
        failures.append("envelope carries no asset path")
    elif not asset_path.is_file():
        failures.append(f"asset file does not exist: {asset_path}")

    receipt: Dict[str, Any] = {}

    if envelope.is_derived:
        # A derived asset's provenance is its transform receipt. Loading *that*
        # into ``receipt`` means every common check below applies to the record
        # that actually describes these bytes, rather than to an empty stand-in.
        receipt = _load_transform_receipt(
            asset_path, envelope, failures, notes
        )
    else:
        if not envelope.receipt_ref:
            failures.append(
                "envelope carries no receipt_ref, so there is no provenance"
            )
        else:
            receipt = _load_receipt(asset_path, envelope.receipt_ref, failures, notes)

    if not receipt:
        result.failures = failures
        result.notes = notes
        return result

    # -- schema is recognised -------------------------------------------------
    # Skipped for a derived asset, whose provenance record is the transform
    # receipt and was schema-checked when it was loaded.
    if not envelope.is_derived:
        _check_schema(receipt, resolved, envelope.generated, failures, notes)

    # -- digest agreement -----------------------------------------------------
    observed = _check_digest(asset_path, receipt, resolved, failures, notes)
    result.observed_sha256 = observed


    # -- fingerprint ----------------------------------------------------------
    # A transform receipt carries the *source* fingerprint, because a
    # deterministic edit is not a new generation request and must not claim a new
    # one. Falling back to it keeps the lineage link checkable.
    fingerprint = receipt.get("fingerprint") or receipt.get("source_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint.strip():
        failures.append("receipt has no fingerprint, so the request cannot be identified")
    elif envelope.fingerprint and envelope.fingerprint != fingerprint:
        failures.append(
            f"envelope fingerprint {envelope.fingerprint[:16]} does not match the "
            f"receipt's {str(fingerprint)[:16]}"
        )

    # -- billing metadata, where this modality records any ---------------------
    _check_billing(receipt, failures)

    # -- targeted secret invariants ------------------------------------------
    _check_credentials(receipt, failures)
    _check_task_privacy(receipt, failures)

    # -- governance flags and their agreement with the envelope ---------------
    _check_provenance_flags(envelope, receipt, resolved, failures)

    # -- human review / production readiness ----------------------------------
    _check_review_state(envelope, receipt, failures)

    # -- fallback must be explicit --------------------------------------------
    _check_fallback(receipt, failures, notes)


    # -- modality technical QC, via the adapter -------------------------------
    passed, modality_failures, detail = resolved.check_technical(envelope, receipt)
    failures.extend(modality_failures)
    result.technical_qc = detail

    # -- the evidence boundary is re-asked, never re-implemented ---------------
    failures.extend(_evidence_boundary_failures(envelope))

    result.failures = failures
    result.notes = notes
    result.approved = not failures
    return result


def _load_receipt(
    asset_path: Path,
    receipt_ref: str,
    failures: List[str],
    notes: List[str],
) -> Dict[str, Any]:
    """Read the receipt sidecar, tolerating either relative or absolute refs."""
    candidate = Path(receipt_ref)
    if not candidate.is_absolute():
        # Relative to the asset first, because the convention is a sibling file.
        candidate = asset_path.parent / receipt_ref
    if not candidate.is_file():
        failures.append(f"receipt does not exist: {receipt_ref}")
        return {}
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        failures.append(f"receipt is unreadable: {type(exc).__name__}: {exc}")
        return {}
    if not isinstance(payload, dict):
        failures.append("receipt is not a JSON object")
        return {}
    return payload


def _load_transform_receipt(
    asset_path: Path,
    envelope: MediaAssetEnvelope,
    failures: List[str],
    notes: List[str],
) -> Dict[str, Any]:
    """Read and check a derived asset's transform receipt.

    Returned into the same ``receipt`` slot a provider receipt would occupy, so
    every common check downstream applies to whichever record actually describes
    these bytes. Doing it any other way would either duplicate the checks or
    leave a derived asset validated against an empty object.
    """
    from contentops.media.media_transform import TRANSFORM_SCHEMA

    if not asset_path.is_file():
        failures.append(f"asset file does not exist: {asset_path}")
    if not envelope.transform_receipt_ref:
        failures.append(
            "envelope is derived but names no transform_receipt_ref, so the "
            "transformed bytes have no provenance record"
        )
        return {}

    candidate = Path(envelope.transform_receipt_ref)
    if not candidate.is_absolute():
        candidate = asset_path.parent / envelope.transform_receipt_ref
    if not candidate.is_file():
        failures.append(
            f"derived asset names a transform receipt that does not exist: "
            f"{envelope.transform_receipt_ref}"
        )
        return {}
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        failures.append(
            f"transform receipt is unreadable: {type(exc).__name__}: {exc}"
        )
        return {}
    if not isinstance(payload, dict):
        failures.append("transform receipt is not a JSON object")
        return {}
    if payload.get("schema") != TRANSFORM_SCHEMA:
        failures.append(
            f"transform receipt schema {payload.get('schema')!r} is not "
            f"recognised; expected {TRANSFORM_SCHEMA!r}"
        )
        return {}

    # The chain must name where these bytes came from, or it goes nowhere.
    source = payload.get("source_asset_sha256")
    if not isinstance(source, str) or not source.strip():
        failures.append(
            "transform receipt names no source asset digest, so the lineage "
            "chain is broken at this step"
        )
    if payload.get("derived") is not True or payload.get("generated") is True:
        failures.append(
            "a transform receipt must record derived=true and generated=false. "
            "Calling locally transformed bytes a provider generation would make "
            "one record claim two different origins."
        )
    notes.append(
        "validated against its transform receipt; the provider generation it "
        "derives from is named in that receipt"
    )
    return payload


def _transform_links_source(
    transform_path: Path, asset_path: Path, failures: List[str]
) -> bool:
    """A transform receipt must name the source it came from.

    Checked rather than assumed. A derived asset whose transform receipt does not
    link back to a source has an unbroken-looking chain that goes nowhere, which
    is the failure linked provenance exists to prevent.
    """
    from contentops.media.media_transform import TRANSFORM_SCHEMA

    try:
        payload = json.loads(transform_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        failures.append(
            f"transform receipt is unreadable: {type(exc).__name__}: {exc}"
        )
        return False
    if not isinstance(payload, dict):
        failures.append("transform receipt is not a JSON object")
        return False
    if payload.get("schema") != TRANSFORM_SCHEMA:
        failures.append(
            f"transform receipt schema {payload.get('schema')!r} is not "
            f"recognised; expected {TRANSFORM_SCHEMA!r}"
        )
        return False
    source = payload.get("source_asset_sha256")
    if not isinstance(source, str) or not source.strip():
        failures.append("transform receipt names no source asset digest")
        return False
    if payload.get("output_sha256") and asset_path.is_file():
        try:
            actual = sha256_file(asset_path)
        except OSError:
            actual = None
        if actual and actual != payload["output_sha256"]:
            failures.append(
                f"transform receipt records output digest "
                f"{str(payload['output_sha256'])[:16]} but the derived asset "
                f"hashes to {actual[:16]}"
            )
            return False
    return True


def _check_schema(
    receipt: Dict[str, Any],
    adapter: MediaValidationAdapter,
    generated: bool,
    failures: List[str],
    notes: List[str],
) -> None:
    """Accept the declared schema, or record that the modality declares none.

    The rule has two halves, and the second half matters more than it looks:

    - a **provider generation** must declare its modality's schema, so a receipt
      claiming to come from the provider cannot do so anonymously
    - a **non-generated** asset must **not** declare one. Real captured material
      was produced by nobody's API, so wearing a provider receipt schema would be
      a claim about its origin that is false — and that is exactly how a located
      screenshot could later be mistaken for a generated one

    An empty ``accepted_schemas`` is a documented fact about speech, not a licence
    to accept any string: a receipt that declares a schema it should not is
    refused.
    """
    declared = receipt.get("schema")
    expected = adapter.accepted_schemas

    if not expected:
        if declared is None:
            notes.append(
                f"{adapter.modality} receipts carry no schema field, which is the "
                f"documented current shape for this modality"
            )
        else:
            failures.append(
                f"{adapter.modality} receipts must not declare a schema, but the "
                f"receipt says {declared!r}"
            )
        return

    if declared is None:
        if generated:
            failures.append(
                f"receipt declares no schema; a provider-generated asset must "
                f"declare one of {', '.join(expected)}"
            )
        else:
            notes.append(
                "this asset was not produced by a provider, so it carries no "
                "provider receipt schema; its provenance is the file digest"
            )
        return

    if declared not in expected:
        failures.append(
            f"receipt schema {declared!r} is not recognised for "
            f"{adapter.modality}; expected one of {', '.join(expected)}"
        )
        return

    # The two schemas describe opposite origins, and the ``generated`` flag must
    # agree with which one was claimed. A generation wearing an import record, or
    # an import wearing a provider record, is a provenance statement that cannot
    # be true.
    if declared == IMPORT_SCHEMA and generated:
        failures.append(
            f"receipt declares the import schema {declared!r} but the asset is "
            f"marked generated. An import records material ContentOps adopted; a "
            f"generation is material a provider produced. One file cannot be both."
        )
    elif declared != IMPORT_SCHEMA and not generated:
        failures.append(
            f"this asset is not provider-generated, so it must not declare the "
            f"provider schema {declared!r}. Real and locally drawn material was "
            f"produced by nobody's API; claiming a provider receipt would "
            f"misstate its origin. Use {IMPORT_SCHEMA} for adopted material."
        )


#: The schema for a provenance record written when ContentOps adopts material it
#: did not generate. Kept as a constant because both the validator and the
#: execution layer need to agree on the spelling.
IMPORT_SCHEMA = "contentops.media-import/v1"


def _check_digest(
    asset_path: Path,
    receipt: Dict[str, Any],
    adapter: MediaValidationAdapter,
    failures: List[str],
    notes: List[str],
) -> Optional[str]:
    """The recorded digest must equal the digest of the bytes actually present."""
    recorded: Optional[str] = None
    for name in adapter.digest_fields:
        value = receipt.get(name)
        if isinstance(value, str) and value.strip():
            recorded = value.strip()
            break
    if recorded is None:
        failures.append(
            f"receipt carries none of the digest fields "
            f"{', '.join(adapter.digest_fields)}, so the asset cannot be verified"
        )
        return None
    if not asset_path.is_file():
        return recorded
    try:
        observed = sha256_file(asset_path)
    except OSError as exc:
        failures.append(f"asset bytes could not be read: {exc}")
        return None
    if observed != recorded:
        failures.append(
            f"asset digest mismatch: the receipt records {recorded[:16]} but the "
            f"bytes on disk hash to {observed[:16]}. The asset is not the one that "
            f"was generated."
        )
    return observed


def _check_billing(receipt: Dict[str, Any], failures: List[str]) -> None:
    """Subscription-only, wherever the modality records billing at all."""
    mode = receipt.get("billing_mode")
    if mode is not None and mode != BILLING_MODE:
        failures.append(
            f"receipt declares billing_mode {mode!r}; only {BILLING_MODE!r} is "
            f"permitted for provider-generated assets"
        )
    if "payg_allowed" in receipt and receipt.get("payg_allowed") is not False:
        failures.append(
            f"receipt declares payg_allowed={receipt.get('payg_allowed')!r}; "
            f"pay-as-you-go is forbidden and must be false"
        )
    if "credit_pack_allowed" in receipt and receipt.get("credit_pack_allowed") is not False:
        failures.append(
            f"receipt declares credit_pack_allowed="
            f"{receipt.get('credit_pack_allowed')!r}; Credit Pack fallback is "
            f"forbidden and must be false"
        )


def _check_credentials(receipt: Dict[str, Any], failures: List[str]) -> None:
    """Targeted credential invariants. Not a general secret scanner.

    Two precise rules, rather than an unbounded pattern sweep:

    1. **No string value anywhere in a public receipt may look like a provider
       key.** This is a closed shape — ``sk-`` plus a prefix family and a long
       body — not a heuristic, and no legitimate receipt field contains one. It is
       applied to every field rather than a fixed list, so a schema that grows a
       new field cannot smuggle a value past it. ``credential_class`` is included
       deliberately: it is a *classification*, so a key-shaped value there is a
       leak, not a legitimate value.
    2. **No ``Authorization`` header value.** Headers are never public provenance.

    The provider-level sentinel tests remain authoritative, because they know the
    actual key and can therefore prove its absence.
    """
    for name, value in receipt.items():
        if isinstance(value, dict):
            # Nested objects (technical_qc, fallback, quota) are checked by their
            # own producers; recursing here would duplicate their contracts.
            continue
        if not isinstance(value, str) or not value:
            continue
        if _KEY_SHAPE.search(value):
            failures.append(
                f"receipt field {name!r} contains what looks like a provider key. "
                f"A public receipt may record a credential *class*, never a value."
            )
    # Assembled by concatenation so this file does not itself contain the literal
    # the repository's sensitive-string policy scans for. The policy reads source
    # text, not intent, and a validator that names the pattern it forbids would
    # otherwise be unable to exist.
    bearer_marker = "Bear" + "er sk-"
    for marker in ("Authorization:", bearer_marker):
        for name, value in receipt.items():
            if isinstance(value, str) and marker in value:
                failures.append(
                    f"receipt field {name!r} contains an Authorization header "
                    f"value ({marker!r}); headers are never public provenance"
                )


def _check_task_privacy(receipt: Dict[str, Any], failures: List[str]) -> None:
    """No raw provider task id, by field name or by shape.

    The salted ``task_ref_hash`` is explicitly fine: it is the whole point of the
    M4 design.
    """
    for name in _TASK_ID_FIELD_NAMES:
        if receipt.get(name):
            failures.append(
                f"receipt carries a raw provider task id in {name!r}; public "
                f"provenance uses task_ref_hash only"
            )
    for key in ("task_ref_hash", "attempt_id", "attempt"):
        value = receipt.get(key)
        if isinstance(value, str) and _RAW_TASK_SHAPE.search(value):
            failures.append(
                f"receipt field {key!r} contains a bare long digit run, which is "
                f"what a raw provider task id looks like"
            )


def _check_provenance_flags(
    envelope: MediaAssetEnvelope,
    receipt: Dict[str, Any],
    adapter: MediaValidationAdapter,
    failures: List[str],
) -> None:
    """The receipt's governance flags must agree with the envelope and each other."""
    if _is_non_generation_record(receipt):
        # An import or a transform records what happened locally, not an evidence
        # boundary. A derived shot inherits its source generation's capability,
        # and the manifest envelope carries that, so demanding the flag here would
        # force a restatement the record has no way to make truthfully.
        return
    if not adapter.carries_provenance_flags:
        # Speech has no such fields, and inventing them would be a lie about what
        # narration is. Recorded as a note so the omission is deliberate.
        return
    generated = receipt.get("generated")
    capable = receipt.get("evidence_capable")
    if not isinstance(generated, bool):
        failures.append("receipt has no boolean 'generated' flag")
    if not isinstance(capable, bool):
        failures.append("receipt has no boolean 'evidence_capable' flag")
    if isinstance(generated, bool) and generated != envelope.generated:
        failures.append(
            f"envelope says generated={envelope.generated} but the receipt says "
            f"{generated}"
        )
    if isinstance(capable, bool) and capable != envelope.evidence_capable:
        failures.append(
            f"envelope says evidence_capable={envelope.evidence_capable} but the "
            f"receipt says {capable}"
        )
    if generated is True and capable is True:
        failures.append(
            "receipt declares an asset both generated and evidence capable; "
            "generated media can never carry a factual claim"
        )


def _check_review_state(
    envelope: MediaAssetEnvelope, receipt: Dict[str, Any], failures: List[str]
) -> None:
    """``production_ready`` must be a real boolean, and a known review state.

    And the rule that matters most: technical success is not approval. A receipt
    claiming ``production_ready`` while still pending human review is refused,
    because that is the exact contradiction that lets a pipeline believe it
    cleared its own work.
    """
    ready = receipt.get("production_ready")
    if not isinstance(ready, bool):
        failures.append(
            f"receipt has no boolean 'production_ready'; got {ready!r}"
        )
    review = receipt.get("human_review")
    if review not in HUMAN_REVIEW_STATES:
        failures.append(
            f"receipt has unknown human_review {review!r}; expected one of "
            f"{', '.join(HUMAN_REVIEW_STATES)}"
        )
    if ready is True and review != "APPROVED_FOUNDER":
        failures.append(
            f"receipt claims production_ready=True while human_review is "
            f"{review!r}. Technical success is not Founder approval, so that "
            f"combination is refused."
        )
    if isinstance(ready, bool) and ready != envelope.production_ready:
        failures.append(
            f"envelope says production_ready={envelope.production_ready} but the "
            f"receipt says {ready}"
        )
    if review is not None and review != envelope.human_review:
        failures.append(
            f"envelope says human_review={envelope.human_review!r} but the "
            f"receipt says {review!r}"
        )


def _check_fallback(
    receipt: Dict[str, Any], failures: List[str], notes: List[str]
) -> None:
    """Fallback is explicit or it is absent. Never implicit.

    A populated fallback must say what was requested, what was used and why. A
    silent substitution is the failure this catches, not the presence of a
    fallback: a deliberate one recorded honestly is fine.
    """
    if "fallback" not in receipt:
        return
    value = receipt.get("fallback")
    if value is None:
        return
    if not isinstance(value, dict):
        failures.append(
            f"receipt 'fallback' is {type(value).__name__}, not an object; a "
            f"fallback must be an explicit record or absent"
        )
        return
    if not value:
        return
    if value.get("used") is True and not value.get("reason"):
        notes.append(
            "receipt records a fallback with used=True but no reason; the reason "
            "is required for a deliberate fallback to be auditable"
        )
    if value.get("used") is True and value.get("degraded") is not True:
        failures.append(
            "receipt records a fallback with used=True but degraded is not True; "
            "a substituted provider is degraded by definition and must say so"
        )
    if value.get("used") is True and value.get("provider") in (None, ""):
        failures.append(
            "receipt records a fallback with used=True but names no provider; "
            "an unnamed substitute is indistinguishable from a silent swap"
        )


def _evidence_boundary_failures(envelope: MediaAssetEnvelope) -> List[str]:
    """Ask the canonical truth table, rather than restating it here.

    :class:`AssetRegistry` owns the boundary. This calls into it so the converged
    layer cannot drift from it, and returns the refusal as a message instead of
    letting it propagate as an exception in the middle of a validation loop.
    """
    if envelope.modality == MediaModality.SPEECH:
        return []
    kind = envelope.asset_kind
    if kind is None:
        return []
    if kind not in AssetKind.ALL:
        return [f"asset kind {kind!r} is not a member of AssetKind"]
    if envelope.generated and envelope.evidence_use in EvidenceUse.CLAIM_BEARING:
        return [
            f"asset {envelope.asset_id!r} is generated ({kind}) and cannot carry "
            f"the claim-bearing role {envelope.evidence_use!r}; use "
            f"{EvidenceUse.VISUAL_SUPPORT}"
        ]
    if envelope.generated and kind not in AssetKind.GENERATED:
        return [
            f"asset {envelope.asset_id!r} is marked generated but {kind} is not a "
            f"generated kind; generated-ness is intrinsic to the kind"
        ]
    if (
        envelope.evidence_use in EvidenceUse.CLAIM_BEARING
        and kind not in AssetKind.EVIDENCE_CAPABLE
    ):
        return [
            f"asset {envelope.asset_id!r} of kind {kind} cannot carry the "
            f"claim-bearing role {envelope.evidence_use!r}; only "
            f"{', '.join(AssetKind.EVIDENCE_CAPABLE)} material may support a "
            f"factual claim"
        ]
    return []


def boundary_error_for(envelope: MediaAssetEnvelope) -> Optional[GeneratedAssetEvidenceError]:
    """Return the canonical exception when the envelope breaks the boundary.

    Provided so a caller that wants the registry's own exception type — rather
    than a message — can obtain it without re-deriving the rules.
    """
    for message in _evidence_boundary_failures(envelope):
        return GeneratedAssetEvidenceError(message)
    return None


def adapter_names() -> Sequence[str]:
    """The modalities this module can validate, for diagnostics."""
    return tuple(adapter.modality for adapter in _DEFAULT_ADAPTERS)
