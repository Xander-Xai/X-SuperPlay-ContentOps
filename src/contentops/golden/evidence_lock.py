"""The evidence lock: the thing every variant must agree on.

What this is for
----------------
An A/B/C/D experiment is worthless if the factual material moved between arms. If
B used a re-captured screenshot, "B sounds better" is really "B had a different
picture". So the lock freezes the factual side of the experiment and every variant
is checked against it before it is allowed to become a build.

What this is deliberately **not**
--------------------------------
This is not the #6 Claim Ledger. A Claim Ledger asserts what a video *claims* and
traces each claim to evidence. This records the factual placement/source binding
that exists **today**, honestly, including the fact that ``claim_refs`` is empty
because no ledger exists yet. Inventing claims to fill that field would be the
worst possible outcome here: a lock that asserts provenance nobody verified is worse
than a lock that admits it has none.

The evidence/support split
--------------------------
A factual asset carries a claim or illustrates a verified fact. A support asset is
generated media that makes the video better without asserting anything: a hook, a
transition, an abstract metaphor. They are separate lists with separate rules, and
the distinction is structural rather than a flag on one list — because the failure
this guards against is a generated full-screen image quietly taking the slot of a
doctor screenshot.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

__all__ = [
    "EVIDENCE_LOCK_SCHEMA",
    "EvidenceAsset",
    "EvidenceLock",
    "EvidenceLockError",
    "build_evidence_lock",
    "structural_fingerprint",
]

EVIDENCE_LOCK_SCHEMA = "contentops.evidence-lock/v1"

PathLike = Union[str, Path]


class EvidenceLockError(ValueError):
    """The lock could not be built, or a variant violated it.

    Carries a stable ``code`` so callers and receipts can distinguish
    ``EVIDENCE_SHA_CHANGED`` from ``EVIDENCE_ASSET_REMOVED`` without matching on
    message text.
    """

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def structural_fingerprint(value: Any) -> str:
    """Digest of a structure with volatile fields removed.

    Used for the storyboard so that a lock survives re-ordering of JSON keys while
    still failing when a shot, a caption or a path changes. Timestamps are excluded
    for the same reason the manifest excludes them: they change for no informational
    gain and would make the lock unstable.
    """
    volatile = {"checked_at", "created_at", "recorded_at", "generated_at", "timestamp"}

    def scrub(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                key: scrub(item)
                for key, item in sorted(node.items())
                if key not in volatile
            }
        if isinstance(node, list):
            return [scrub(item) for item in node]
        return node

    canonical = json.dumps(scrub(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class EvidenceAsset:
    """One factual placement, frozen.

    ``claim_refs`` is an empty list by default and is meant to stay empty until the
    #6 Claim Ledger exists. Nothing in this module requires it to be populated, and
    nothing fills it speculatively.
    """

    #: Timeline slot, e.g. ``shot_00``. Renaming a slot is a script change.
    placement_id: str
    #: Portable reference, e.g. ``project://sources/screenshots/10-easel-doctor.png``.
    asset_path: str
    #: Digest of the bytes. This is the value compared across variants.
    asset_sha256: str
    #: Factual material by definition: an evidence lock admits nothing generated.
    asset_kind: str
    evidence_use: str
    #: Empty until a Claim Ledger exists. Recorded, not invented.
    claim_refs: List[str] = field(default_factory=list)
    #: The receipt or document that records where this asset came from, if any.
    source_ref: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "placement_id": self.placement_id,
            "asset_path": self.asset_path,
            "asset_sha256": self.asset_sha256,
            "asset_kind": self.asset_kind,
            "evidence_use": self.evidence_use,
            "claim_refs": list(self.claim_refs),
            "source_ref": self.source_ref,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "EvidenceAsset":
        return cls(
            placement_id=payload["placement_id"],
            asset_path=payload["asset_path"],
            asset_sha256=payload["asset_sha256"],
            asset_kind=payload["asset_kind"],
            evidence_use=payload["evidence_use"],
            claim_refs=list(payload.get("claim_refs") or []),
            source_ref=payload.get("source_ref"),
        )


@dataclass
class EvidenceLock:
    """The frozen factual side of the experiment, plus the context it was cut from.

    ``fixture`` is the load-bearing field for honesty. A lock built from test
    fixtures and a lock built from real baseline sources are structurally identical,
    and the only thing that stops one being reported as the other is this flag
    travelling with the lock into every receipt.
    """

    source_project: str
    master_script_sha256: str
    narration_text_sha256: str
    storyboard_fingerprint: str
    caption_sha256: Optional[str]
    evidence: List[EvidenceAsset]
    #: True when built from fixtures. A production lock requires ``fixture=False``.
    fixture: bool = False
    #: Free-form notes, e.g. which claim-binding fields are not yet available.
    notes: Dict[str, Any] = field(default_factory=dict)

    # -- integrity ---------------------------------------------------------

    def by_placement(self) -> Dict[str, EvidenceAsset]:
        return {asset.placement_id: asset for asset in self.evidence}

    def asset_digest(self) -> str:
        """Digest over the factual assets only.

        Deliberately excludes the script and narration digests so a caller can ask
        the two questions separately: "did the evidence change?" and "did the words
        change?". Collapsing them into one number would make a narration-only
        variant look like an evidence change.
        """
        return structural_fingerprint(
            [asset.as_dict() for asset in sorted(
                self.evidence, key=lambda a: a.placement_id
            )]
        )

    def fingerprint(self) -> str:
        """Digest over everything a variant must reproduce.

        Includes the script, the narration text, the storyboard structure and the
        caption, so one fingerprint answers "is this the same experiment?".
        """
        return structural_fingerprint({
            "master_script_sha256": self.master_script_sha256,
            "narration_text_sha256": self.narration_text_sha256,
            "storyboard_fingerprint": self.storyboard_fingerprint,
            "caption_sha256": self.caption_sha256,
            "evidence": [
                asset.as_dict() for asset in sorted(
                    self.evidence, key=lambda a: a.placement_id
                )
            ],
        })

    def asset_identity(self) -> List[Dict[str, Any]]:
        """The tuple compared across A/B/C/D for every factual placement.

        This is the #25 evidence-identity comparison, precomputed: placement, path,
        digest, kind, evidence role, claim refs and source ref. One mismatch in any
        of these invalidates the experiment.
        """
        return [
            {
                "placement_id": asset.placement_id,
                "asset_path": asset.asset_path,
                "asset_sha256": asset.asset_sha256,
                "asset_kind": asset.asset_kind,
                "evidence_use": asset.evidence_use,
                "claim_refs": list(asset.claim_refs),
                "source_ref": asset.source_ref,
            }
            for asset in sorted(self.evidence, key=lambda a: a.placement_id)
        ]

    # -- serialisation -----------------------------------------------------

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": EVIDENCE_LOCK_SCHEMA,
            "fixture": self.fixture,
            "source_project": self.source_project,
            "master_script_sha256": self.master_script_sha256,
            "narration_text_sha256": self.narration_text_sha256,
            "storyboard_fingerprint": self.storyboard_fingerprint,
            "caption_sha256": self.caption_sha256,
            "asset_digest": self.asset_digest(),
            "fingerprint": self.fingerprint(),
            # asset_identity() already returns plain dicts; calling as_dict() on its
            # output was a bug this suite caught on the first run.
            "evidence": self.asset_identity(),
            "claim_ledger_status": (
                "NOT_AVAILABLE — #6 Claim Ledger does not exist yet. claim_refs are "
                "recorded as empty rather than populated speculatively."
            ),
            "notes": dict(self.notes),
        }

    def write(self, path: PathLike) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "EvidenceLock":
        schema = payload.get("schema")
        if schema != EVIDENCE_LOCK_SCHEMA:
            raise EvidenceLockError(
                "LOCK_SCHEMA_UNKNOWN",
                f"declared schema {schema!r}; this client understands "
                f"{EVIDENCE_LOCK_SCHEMA!r}",
            )
        return cls(
            source_project=payload["source_project"],
            master_script_sha256=payload["master_script_sha256"],
            narration_text_sha256=payload["narration_text_sha256"],
            storyboard_fingerprint=payload["storyboard_fingerprint"],
            caption_sha256=payload.get("caption_sha256"),
            evidence=[
                EvidenceAsset.from_dict(item) for item in payload.get("evidence") or []
            ],
            fixture=bool(payload.get("fixture", False)),
            notes=dict(payload.get("notes") or {}),
        )

    @classmethod
    def load(cls, path: PathLike) -> "EvidenceLock":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def build_evidence_lock(
    *,
    source_project: str,
    master_script_path: PathLike,
    narration_text_path: PathLike,
    storyboard_path: PathLike,
    caption_path: Optional[PathLike] = None,
    asset_paths: Optional[Dict[str, PathLike]] = None,
    resolve_logical: Optional[Any] = None,
    asset_kinds: Optional[Dict[str, str]] = None,
    evidence_uses: Optional[Dict[str, str]] = None,
    claim_refs: Optional[Dict[str, Sequence[str]]] = None,
    source_refs: Optional[Dict[str, str]] = None,
    fixture: bool = False,
    notes: Optional[Dict[str, Any]] = None,
) -> EvidenceLock:
    """Build a lock from files on disk.

    Args:
        source_project: portable reference to the project the assets come from.
        master_script_path: the script. Its digest is frozen.
        narration_text_path: the narration **text**. Its digest is frozen, so a
            variant that re-records different words is caught even if the audio file
            were somehow reused.
        storyboard_path: the storyboard. Only its structural fingerprint is frozen,
            so key ordering and timestamps do not cause false failures.
        caption_path: caption file, when one exists.
        asset_paths: ``placement_id -> local path`` for the factual assets.
        resolve_logical: callable turning a local path into a portable reference.
            Required, so a lock can never embed a machine path.
        asset_kinds: ``placement_id -> AssetKind``. Factual by definition.
        evidence_uses: ``placement_id -> evidence role``.
        claim_refs: ``placement_id -> claim ids``. Omit to record them empty.
        source_refs: ``placement_id -> source receipt or document reference``.
        fixture: mark a lock built from test fixtures. A production lock must not
            set this, and :func:`assert_production_lock` enforces that.
        notes: extra provenance notes.

    Raises:
        EvidenceLockError: ``LOCK_ASSET_MISSING`` when a declared asset is absent.
            A lock that silently drops an absent asset is exactly the failure that
            would let a variant build against a smaller evidence set.
    """
    resolve = resolve_logical
    if resolve is None:
        raise EvidenceLockError(
            "LOGICAL_RESOLVER_MISSING",
            "build_evidence_lock needs a resolve_logical callable; a lock must never "
            "embed a machine path",
        )
    declared = dict(asset_paths or {})
    if not declared:
        raise EvidenceLockError(
            "LOCK_HAS_NO_ASSETS",
            "an evidence lock with no factual assets would lock nothing",
        )

    storyboard = json.loads(Path(storyboard_path).read_text(encoding="utf-8"))
    assets: List[EvidenceAsset] = []
    for placement_id, local in sorted(declared.items()):
        path = Path(local)
        if not path.is_file():
            raise EvidenceLockError(
                "LOCK_ASSET_MISSING",
                f"placement {placement_id!r} declares {path.name}, which does not "
                f"exist. Refusing to build a lock that silently omits evidence.",
            )
        assets.append(EvidenceAsset(
            placement_id=placement_id,
            asset_path=resolve(path),
            asset_sha256=_sha256_file(path),
            asset_kind=(asset_kinds or {}).get(placement_id, "SCREENSHOT"),
            evidence_use=(evidence_uses or {}).get(placement_id, "EVIDENCE"),
            claim_refs=list((claim_refs or {}).get(placement_id, [])),
            source_ref=(source_refs or {}).get(placement_id),
        ))

    return EvidenceLock(
        source_project=source_project,
        master_script_sha256=_sha256_file(Path(master_script_path)),
        narration_text_sha256=_sha256_file(Path(narration_text_path)),
        storyboard_fingerprint=structural_fingerprint(storyboard),
        caption_sha256=(
            _sha256_file(Path(caption_path)) if caption_path else None
        ),
        evidence=assets,
        fixture=fixture,
        notes=dict(notes or {}),
    )


def assert_production_lock(lock: EvidenceLock) -> None:
    """Refuse to treat a fixture lock as a production lock.

    Called before any real provider spend. A fixture lock and a production lock have
    identical shape, so without this the only thing separating a test result from a
    reported experiment is whoever remembered to check.
    """
    if lock.fixture:
        raise EvidenceLockError(
            "FIXTURE_LOCK_IS_NOT_PRODUCTION",
            "this evidence lock was built from test fixtures; it cannot back a real "
            "Golden build or a Founder review",
        )
