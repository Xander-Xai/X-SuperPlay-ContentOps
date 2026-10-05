"""The A/B/C/D variant model, the builder, and the guards that keep it honest.

The experiment
--------------
Four arms, nested so each step adds exactly one variable:

======  ====================  ==============  ===========  =========================
Arm     Narration             Support image   H3 insert    Isolates
======  ====================  ==============  ===========  =========================
A       baseline voice        none            none         the pinned Easel baseline
B       MiniMax narration     none            none         voice alone
C       same as B              1 image         none         + support visual
D       same as B and C        same 1 image    max 2        + generated video
======  ====================  ==============  ===========  =========================

A is allowed to win. So is NONE. Nothing here ranks the arms.

Evidence versus support
-----------------------
The one structural rule that matters most: **a generated asset may never occupy a
factual placement.** The baseline is six real screenshots, each of which is the
picture a sentence points at. Implementing C or D by substituting a generated image
for a screenshot would produce a video that looks fine and asserts things nobody
verified, which is the exact failure the whole evidence boundary exists to prevent.

So the timeline has two independent layers:

- the **evidence timeline**, frozen by :class:`~contentops.golden.evidence_lock.EvidenceLock`
- the **support enhancement layer**, a set of declared insertions that render
  alongside or between evidence placements

A support insertion is identified by the placement it accompanies or precedes. It
is never given an ``evidence_use`` and never enters the evidence timeline.

Declared changes are checked against actual changes
---------------------------------------------------
A receipt that only echoes what the author *said* they changed proves nothing. The
builder recomputes the real differences between two arms and refuses to build when
the actual differences contain anything undeclared. That is what makes the nesting
claim checkable rather than aspirational.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from contentops.golden.evidence_lock import (
    EvidenceLock,
    EvidenceLockError,
    assert_production_lock,
)

__all__ = [
    "SUPPORT_LAYER_ROLE",
    "VARIANT_IDS",
    "DirtyExperimentError",
    "EnhancedGoldenBuilder",
    "SupportInsertion",
    "VariantPlan",
    "VariantReceipt",
    "VariantSpec",
    "VARIANT_SPECS",
    "compute_variant_diff",
]

PathLike = Union[str, Path]

#: Every arm in the experiment, in order.
VARIANT_IDS: Tuple[str, ...] = ("A", "B", "C", "D")

#: Support media is never evidence. Stated as a constant so a receipt carries the
#: policy rather than relying on a reader remembering it.
SUPPORT_LAYER_ROLE = "NON_CLAIM_SUPPORT"

#: Arm D may add at most this many H3 inserts. One is the default and is what the
#: plan expects to be sufficient; two exists so a reviewer can see the ceiling is
#: real rather than assumed.
MAX_H3_INSERTS = 2


class DirtyExperimentError(RuntimeError):
    """The experiment is not clean, so no build may proceed.

    Separate from :class:`EvidenceLockError` because these are about the *variant
    relationship*, not about the lock being unreadable. Carries a stable ``code``
    so receipts and tests assert on the code, never on wording.
    """

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


# --- the variant specification ----------------------------------------------


@dataclass(frozen=True)
class VariantSpec:
    """What one arm is declared to change relative to the arm below it.

    ``base`` is the arm this one nests onto, which is what makes the experiment
    single-variable. D is declared against C, C against B, B against A, and A
    against nothing.
    """

    variant_id: str
    base: Optional[str]
    #: ``baseline`` or ``minimax``.
    narration: str
    #: Number of generated support images. Never a factual replacement.
    generated_images: int = 0
    #: Number of H3 support inserts. Capped by :data:`MAX_H3_INSERTS`.
    h3_inserts: int = 0
    #: Human-readable statement of the single variable this arm changes.
    isolates: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "base": self.base,
            "narration": self.narration,
            "generated_images": self.generated_images,
            "h3_inserts": self.h3_inserts,
            "isolates": self.isolates,
        }


#: The four arms, nested. A is the baseline and changes nothing.
VARIANT_SPECS: Dict[str, VariantSpec] = {
    "A": VariantSpec(
        variant_id="A", base=None, narration="baseline",
        isolates="the pinned Easel baseline, unchanged",
    ),
    "B": VariantSpec(
        variant_id="B", base="A", narration="minimax",
        isolates="narration alone; no generated image, no H3",
    ),
    "C": VariantSpec(
        variant_id="C", base="B", narration="minimax", generated_images=1,
        isolates="one generated support image, narration unchanged from B",
    ),
    "D": VariantSpec(
        variant_id="D", base="C", narration="minimax", generated_images=1,
        h3_inserts=1,
        isolates="one H3 support insert, narration and image unchanged from C",
    ),
}


@dataclass
class SupportInsertion:
    """One generated asset in the support layer.

    Carries the placement it accompanies so the two layers stay visibly separate.
    ``evidence_use`` is fixed to the support role and cannot be set to anything
    claim-bearing: a generated asset that claimed to be evidence would be exactly
    the substitution this design forbids.
    """

    #: Where it sits: ``precedes:<placement>``, ``follows:<placement>`` or
    #: ``overlay:<placement>``. Never a bare factual placement id, because that
    #: would read as a replacement.
    anchor: str
    asset_path: str
    asset_sha256: str
    #: ``image`` or ``video``.
    modality: str
    #: Why this support asset earns its place. Required: an unexplained insert is
    #: indistinguishable from decoration added to make an arm look richer.
    purpose: str
    evidence_use: str = SUPPORT_LAYER_ROLE
    audio_policy: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "anchor": self.anchor,
            "asset_path": self.asset_path,
            "asset_sha256": self.asset_sha256,
            "modality": self.modality,
            "purpose": self.purpose,
            "evidence_use": self.evidence_use,
            "audio_policy": self.audio_policy,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "SupportInsertion":
        return cls(
            anchor=payload["anchor"],
            asset_path=payload["asset_path"],
            asset_sha256=payload["asset_sha256"],
            modality=payload["modality"],
            purpose=payload["purpose"],
            evidence_use=payload.get("evidence_use", SUPPORT_LAYER_ROLE),
            audio_policy=payload.get("audio_policy"),
        )


@dataclass
class VariantPlan:
    """A fully resolved arm: a spec, its evidence, and its support insertions.

    Built by :meth:`EnhancedGoldenBuilder.plan`. Holding the evidence lock on the
    plan means a guard cannot accidentally compare against a different lock than the
    one that was enforced.
    """

    spec: VariantSpec
    lock: EvidenceLock
    #: Narration asset for this arm. C, B and D must share one digest.
    narration_path: str
    narration_sha256: str
    support: List[SupportInsertion] = field(default_factory=list)
    #: True when narration and support assets are test fixtures rather than real
    #: provider output. Travels with the plan so no receipt can omit it.
    fixture: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.spec.variant_id,
            "base": self.spec.base,
            "narration": self.spec.narration,
            "narration_path": self.narration_path,
            "narration_sha256": self.narration_sha256,
            "support": [item.as_dict() for item in self.support],
            "support_count": len(self.support),
            "fixture": self.fixture,
        }

    def identity(self) -> Dict[str, Any]:
        """Everything a variant receipt must record, for the difference engine."""
        return {
            "variant_id": self.spec.variant_id,
            "narration_sha256": self.narration_sha256,
            "support": sorted(
                (item.anchor, item.asset_sha256, item.modality) for item in self.support
            ),
            "evidence": [
                (asset["placement_id"], asset["asset_sha256"])
                for asset in self.lock.asset_identity()
            ],
        }


# --- the difference engine ---------------------------------------------------


def compute_variant_diff(current: VariantPlan, base: VariantPlan) -> Dict[str, Any]:
    """Recompute what actually differs between two arms.

    Declared differences are recorded alongside, never instead of, the computed
    ones. The gap between the two is the interesting part: a declared change that
    did not happen, or an actual change nobody declared.
    """
    cur, ref = current.identity(), base.identity()
    spec_cur = VARIANT_SPECS[cur["variant_id"]]
    spec_ref = VARIANT_SPECS[ref["variant_id"]]

    declared = {
        "narration_changed": spec_cur.narration != spec_ref.narration,
        "support_images_added": (
            spec_cur.generated_images - spec_ref.generated_images
        ),
        "h3_inserts_added": spec_cur.h3_inserts - spec_ref.h3_inserts,
    }

    actual: Dict[str, Any] = {
        "narration": {
            "changed": cur["narration_sha256"] != ref["narration_sha256"],
            "from": ref["narration_sha256"],
            "to": cur["narration_sha256"],
        },
        "support_assets": {
            "added": sorted(set(cur["support"]) - set(ref["support"])),
            "removed": sorted(set(ref["support"]) - set(cur["support"])),
        },
        "evidence": {
            "changed": cur["evidence"] != ref["evidence"],
            "placements_changed": sorted(
                {p for p, s in cur["evidence"]} | {p for p, s in ref["evidence"]}
            ) if cur["evidence"] != ref["evidence"] else [],
        },
        "script": {"changed": False},
        "timeline": {
            "changed": cur["support"] != ref["support"],
            "note": (
                "the evidence timeline is identical by construction here; a true "
                "change would mean the evidence lock itself was not enforced"
            ),
        },
    }

    # Count actual additions by modality, so a declared "one image" cannot quietly
    # turn into two images and one H3.
    added = actual["support_assets"]["added"]
    actual["support_assets"]["images_added"] = sorted(
        a for a in added if a[2] == "image"
    )
    actual["support_assets"]["h3_added"] = sorted(
        a for a in added if a[2] == "video"
    )
    return {
        "variant": cur["variant_id"],
        "base": ref["variant_id"],
        "declared_changes": declared,
        "actual_asset_changes": actual["support_assets"],
        "actual_narration_changes": actual["narration"],
        "actual_evidence_changes": actual["evidence"],
        "actual_script_changes": actual["script"],
        "actual_timeline_changes": actual["timeline"],
    }


# --- the builder -------------------------------------------------------------


@dataclass
class VariantReceipt:
    """Per-arm record. Every field here is something a reviewer would otherwise
    have to take on trust."""

    variant_id: str
    schema_version: str
    base_experiment_fingerprint: str
    evidence_lock_fingerprint: str
    evidence_asset_digest: str
    master_script_sha256: str
    narration_text_sha256: str
    storyboard_fingerprint: str
    factual_assets: List[Dict[str, Any]]
    narration_sha256: str
    narration_asset_logical_path: str
    generated_image_shas: List[str]
    h3_shas: List[str]
    declared_changes: Dict[str, Any]
    actual_changes: Dict[str, Any]
    manifest_fingerprint: Optional[str] = None
    compose: Dict[str, Any] = field(default_factory=dict)
    qc: Dict[str, Any] = field(default_factory=dict)
    provider_calls: Dict[str, int] = field(
        default_factory=lambda: {"speech": 0, "image": 0, "video": 0}
    )
    quota_before: Dict[str, Any] = field(default_factory=dict)
    quota_after: Dict[str, Any] = field(default_factory=dict)
    #: Never true before a human has watched. No code path sets it otherwise.
    production_ready: bool = False
    human_review: str = "PENDING_FOUNDER_REVIEW"
    fixture: bool = False
    notes: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema_version,
            "variant_id": self.variant_id,
            "base_experiment_fingerprint": self.base_experiment_fingerprint,
            "evidence_lock_fingerprint": self.evidence_lock_fingerprint,
            "evidence_asset_digest": self.evidence_asset_digest,
            "master_script_sha256": self.master_script_sha256,
            "narration_text_sha256": self.narration_text_sha256,
            "storyboard_fingerprint": self.storyboard_fingerprint,
            "factual_assets": self.factual_assets,
            "narration_sha256": self.narration_sha256,
            "narration_asset_logical_path": self.narration_asset_logical_path,
            "generated_image_shas": self.generated_image_shas,
            "h3_shas": self.h3_shas,
            "declared_changes": self.declared_changes,
            "actual_changes": self.actual_changes,
            "manifest_fingerprint": self.manifest_fingerprint,
            "compose": self.compose,
            "qc": self.qc,
            "provider_calls": self.provider_calls,
            "quota_before": self.quota_before,
            "quota_after": self.quota_after,
            "production_ready": self.production_ready,
            "human_review": self.human_review,
            "fixture": self.fixture,
            "notes": self.notes,
        }


class EnhancedGoldenBuilder:
    """Builds A/B/C/D while refusing every experiment that is not actually clean.

    The builder holds the evidence lock and the narration assets. It does not
    generate media: asset acquisition is a separate, explicit step, so a build can
    never quietly spend quota. Composition is injected as a callable, which is what
    keeps this testable without ffmpeg and keeps provider-free CI possible.
    """

    def __init__(
        self,
        *,
        lock: EvidenceLock,
        narration_assets: Dict[str, str],
        support_assets: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        compose: Optional[Any] = None,
        experiment_fingerprint: Optional[str] = None,
    ) -> None:
        self.lock = lock
        #: ``variant_id -> logical narration path``.
        self.narration_assets = dict(narration_assets)
        #: ``variant_id -> [support insertion dicts]``.
        self.support_assets = {
            key: list(value) for key, value in (support_assets or {}).items()
        }
        self._compose = compose
        self.experiment_fingerprint = experiment_fingerprint or lock.fingerprint()
        self._plans: Dict[str, VariantPlan] = {}

    # -- planning ----------------------------------------------------------

    def plan(self, variant_id: str) -> VariantPlan:
        """Resolve one arm, enforcing the reuse and cap rules."""
        spec = self._resolve_spec(variant_id)
        narration_path = self._require_narration(spec)

        support: List[SupportInsertion] = []
        for payload in self.support_assets.get(variant_id, []):
            support.append(SupportInsertion.from_dict(payload))

        if len([s for s in support if s.modality == "video"]) > MAX_H3_INSERTS:
            raise DirtyExperimentError(
                "TOO_MANY_H3_INSERTS",
                f"variant {variant_id} declares {len(support)} video inserts; the cap "
                f"is {MAX_H3_INSERTS}. More inserts cost real quota and test nothing "
                f"the first insert did not already test.",
            )
        for item in support:
            if item.evidence_use != SUPPORT_LAYER_ROLE:
                raise DirtyExperimentError(
                    "GENERATED_REPLACED_EVIDENCE",
                    f"support asset at {item.anchor!r} declares evidence_use "
                    f"{item.evidence_use!r}. Generated media is never "
                    f"claim-bearing; it lives in the support layer.",
                )
            self._require_anchor_form(item, spec.variant_id)

        plan = VariantPlan(
            spec=spec,
            lock=self.lock,
            narration_path=narration_path,
            narration_sha256=self._digest_of(narration_path),
            support=support,
            fixture=self.lock.fixture,
        )
        self._check_reuse(spec, plan)
        self._plans[spec.variant_id] = plan
        return plan

    def _resolve_spec(self, variant_id: str) -> VariantSpec:
        spec = VARIANT_SPECS.get(variant_id)
        if spec is None:
            raise DirtyExperimentError(
                "UNKNOWN_VARIANT",
                f"{variant_id!r} is not one of {', '.join(VARIANT_IDS)}",
            )
        return spec

    def _require_narration(self, spec: VariantSpec) -> str:
        narration = self.narration_assets.get(spec.variant_id)
        if not narration:
            raise DirtyExperimentError(
                "NARRATION_ASSET_MISSING",
                f"variant {spec.variant_id} has no narration asset. The arms share "
                f"assets deliberately; each one is declared, not regenerated.",
            )
        return narration

    def _require_anchor_form(self, item: SupportInsertion, variant_id: str) -> None:
        """A support insert must name its relationship to a factual placement.

        A bare placement id is refused because it reads as "this generated asset *is*
        that slot", which is the substitution the design forbids. The form makes the
        relationship explicit: it sits before, after, or over an evidence shot.
        """
        if ":" not in item.anchor:
            raise DirtyExperimentError(
                "SUPPORT_ANCHOR_MUST_BE_RELATIONAL",
                f"variant {variant_id} support asset at {item.anchor!r} must be "
                f"anchored as 'precedes:', 'follows:' or 'overlay:' a factual "
                f"placement. A bare placement id would read as replacing it.",
            )
        relation, _, placement = item.anchor.partition(":")
        if relation not in ("precedes", "follows", "overlay"):
            raise DirtyExperimentError(
                "SUPPORT_ANCHOR_RELATION_UNKNOWN",
                f"{relation!r} is not a known support relation; use precedes, "
                f"follows or overlay",
            )
        if placement not in self.lock.by_placement():
            raise DirtyExperimentError(
                "SUPPORT_ANCHOR_UNKNOWN_PLACEMENT",
                f"support asset is anchored to {placement!r}, which is not a locked "
                f"factual placement",
            )

    def _digest_of(self, logical_path: str) -> str:
        """Digest a logical reference's bytes.

        The builder is given logical references, so it resolves them through the same
        path contract the manifest uses rather than guessing a root. Resolution is
        injected so this stays testable and so a variant cannot record a digest for a
        file it did not actually read.
        """
        resolver = getattr(self, "_resolve", None)
        if resolver is None:
            raise DirtyExperimentError(
                "RESOLVER_NOT_CONFIGURED",
                "the builder needs a resolve callback to read asset bytes",
            )
        local = resolver(logical_path)
        path = Path(local)
        if not path.is_file():
            raise DirtyExperimentError(
                "NARRATION_ASSET_MISSING",
                f"{logical_path} does not resolve to a file",
            )
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def set_resolver(self, resolve) -> None:
        self._resolve = resolve

    def _check_reuse(self, spec: VariantSpec, plan: VariantPlan) -> None:
        """Enforce the shared-asset rules that make the nesting meaningful.

        Without this, "B, C and D use the same narration" would be a claim in a
        document rather than a property of the build, and a reviewer would have no
        way to tell a one-variable experiment from four unrelated videos.
        """
        if spec.variant_id in ("C", "D") and spec.base == "B":
            base_plan = self._plans.get("B")
            if base_plan is None:
                base_plan = self.plan("B")
            if plan.narration_sha256 != base_plan.narration_sha256:
                raise DirtyExperimentError(
                    "B_C_D_NARRATION_MISMATCH",
                    f"variant {spec.variant_id} narration {plan.narration_sha256[:12]} "
                    f"differs from B's {base_plan.narration_sha256[:12]}. B/C/D must "
                    f"share one narration asset so the comparison isolates visuals.",
                )
        if spec.variant_id == "D" and spec.base == "C":
            base_plan = self._plans.get("C") or self.plan("C")
            base_images = {s.asset_sha256 for s in base_plan.support if s.modality == "image"}
            own_images = {s.asset_sha256 for s in plan.support if s.modality == "image"}
            if base_images != own_images:
                raise DirtyExperimentError(
                    "C_D_IMAGE_MISMATCH",
                    f"variant D's generated image {sorted(own_images)} differs from "
                    f"C's {sorted(base_images)}. D must reuse C's exact image; "
                    f"regenerating it would confound the H3 variable.",
                )

    # -- building ----------------------------------------------------------

    def build(self, variant_id: str) -> VariantReceipt:
        """Validate, difference-check, then compose.

        Order matters: the guards run before composition, so a dirty experiment
        costs no render time and cannot leave a half-built artifact behind.
        """
        plan = self.plan(variant_id)
        spec = plan.spec

        if not plan.fixture:
            # A real build must not be standing on a fixture lock.
            try:
                assert_production_lock(self.lock)
            except EvidenceLockError as exc:
                raise DirtyExperimentError(exc.code, exc.detail) from exc

        diff: Dict[str, Any] = {
            "declared_changes": {}, "actual_asset_changes": {},
            "actual_narration_changes": {}, "actual_evidence_changes": {},
            "actual_script_changes": {}, "actual_timeline_changes": {},
        }
        if spec.base is not None:
            base_plan = self._plans.get(spec.base) or self.plan(spec.base)
            diff = compute_variant_diff(plan, base_plan)
            self._enforce_clean(spec, plan, base_plan, diff)

        compose_result: Dict[str, Any] = {"status": "NOT_COMPOSED", "reason": (
            "no compose callable was supplied; this build validated the experiment "
            "and did not render"
        )}
        if self._compose is not None:
            compose_result = self._compose(plan)

        return VariantReceipt(
            variant_id=variant_id,
            schema_version="contentops.golden-variant-receipt/v1",
            base_experiment_fingerprint=self.experiment_fingerprint,
            evidence_lock_fingerprint=self.lock.fingerprint(),
            evidence_asset_digest=self.lock.asset_digest(),
            master_script_sha256=self.lock.master_script_sha256,
            narration_text_sha256=self.lock.narration_text_sha256,
            storyboard_fingerprint=self.lock.storyboard_fingerprint,
            factual_assets=self.lock.asset_identity(),
            narration_sha256=plan.narration_sha256,
            narration_asset_logical_path=plan.narration_path,
            generated_image_shas=sorted(
                s.asset_sha256 for s in plan.support if s.modality == "image"
            ),
            h3_shas=sorted(s.asset_sha256 for s in plan.support if s.modality == "video"),
            declared_changes=diff["declared_changes"],
            actual_changes=diff,
            compose=compose_result,
            # Every arm is unapproved. There is no code path that sets this True.
            production_ready=False,
            human_review="PENDING_FOUNDER_REVIEW",
            fixture=plan.fixture,
        )

    def _enforce_clean(
        self,
        spec: VariantSpec,
        plan: VariantPlan,
        base_plan: VariantPlan,
        diff: Dict[str, Any],
    ) -> None:
        """Refuse any build whose actual differences exceed its declared ones.

        This is the check that makes the experiment mean something. Declaring "one
        generated image" and shipping two is not a documentation slip; it means the
        reported result measures something other than what it claims to.
        """
        declared = diff["declared_changes"]
        actual = diff["actual_asset_changes"]

        if diff["actual_evidence_changes"]["changed"]:
            raise DirtyExperimentError(
                "EVIDENCE_SHA_CHANGED",
                f"variant {spec.variant_id} changed factual evidence relative to "
                f"{base_plan.spec.variant_id}. The comparison would measure the "
                f"evidence, not the enhancement.",
            )
        if diff["actual_script_changes"]["changed"]:
            raise DirtyExperimentError(
                "SCRIPT_CHANGED",
                f"variant {spec.variant_id} changed the master script",
            )
        if diff["actual_narration_changes"]["changed"] != declared.get("narration_changed"):
            raise DirtyExperimentError(
                "UNDECLARED_TIMELINE_CHANGE",
                f"variant {spec.variant_id} narration changed="
                f"{diff['actual_narration_changes']['changed']} but declared="
                f"{declared.get('narration_changed')}",
            )

        added_images = len(actual.get("images_added", []))
        added_h3 = len(actual.get("h3_added", []))
        if added_images != declared.get("support_images_added", 0):
            raise DirtyExperimentError(
                "UNDECLARED_ASSET_DIFFERENCE",
                f"variant {spec.variant_id} added {added_images} generated image(s) "
                f"but declared {declared.get('support_images_added', 0)}",
            )
        if added_h3 != declared.get("h3_inserts_added", 0):
            raise DirtyExperimentError(
                "UNDECLARED_ASSET_DIFFERENCE",
                f"variant {spec.variant_id} added {added_h3} H3 insert(s) but "
                f"declared {declared.get('h3_inserts_added', 0)}",
            )
        if actual.get("removed"):
            raise DirtyExperimentError(
                "UNDECLARED_ASSET_DIFFERENCE",
                f"variant {spec.variant_id} removed support assets present in "
                f"{base_plan.spec.variant_id}: {actual['removed']}",
            )
        if added_h3 > MAX_H3_INSERTS:
            raise DirtyExperimentError(
                "TOO_MANY_H3_INSERTS",
                f"variant {spec.variant_id} added {added_h3} H3 inserts; cap is "
                f"{MAX_H3_INSERTS}",
            )
