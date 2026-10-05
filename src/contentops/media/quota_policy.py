"""Quota policy and scheduling. Explicit configuration, never inferred economics.

What this is not
----------------
It is not a cost model. The provider exposes **percentages only**: it will say
"58 % of weekly plan usage remains" and will not say what a video clip costs.

M4 measured one real observation: a 4 s / 768P H3 job moved weekly usage by about
**7 percentage points**. That is tempting to turn into a rate. It is not one, and
the temptation is worth naming explicitly:

- it was **one** observation, from **one** clip length, at **one** resolution
- the plan exposes no absolute units, so a percentage cannot be mapped to money
- a longer clip, a different resolution or a different model could move it by a
  different amount

So ``weekly_floor_percent`` below is an **operator policy value**, chosen by a
person, and it is not derived from that observation. The observation lives in
``research/`` as a warning for budgeting, which is the only thing it can honestly
be used for.

Two different jobs, kept apart
------------------------------
:class:`~contentops.media.quota_policy.MediaQuotaPolicy` and
:class:`~contentops.media.billing_guard.BillingGuard` answer different questions
and both are needed:

- the **policy** decides *whether to plan this work at all* — ordering, floors,
  declared budgets, whether paid funds are even permitted
- the **BillingGuard** decides *whether this specific call is safe right now*,
  immediately before the provider request, with live balance and quota reads

A scheduling decision never authorises a provider call. Every provider still runs
its own guard, because quota can be spent by something else between the two
points, and a stale plan is not authorisation.

One snapshot, one decision
--------------------------
All three modalities draw on the **same account plan state**, so fetching quota
per planned action would both waste calls and, worse, produce inconsistent
answers between two actions in the same plan. :class:`QuotaScheduler.schedule`
takes **one** :class:`QuotaSnapshot` and returns one decision per action against
it.

Priority order
--------------
Fixed by policy, in this order, and deliberately not by provider price:

1. anything already reusable
2. mandatory real or captured evidence
3. narration
4. deterministic local assets
5. generated image support
6. generated video support

Video sits last because a ~7pp draw on a shared weekly window is the most
expensive thing ContentOps does, and because a beautiful generated insert must
never starve the narration or the evidence a claim depends on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from contentops.media.billing_guard import MODALITY_WINDOWS
from contentops.media.contract import QuotaSnapshot
from contentops.media.media_envelope import MediaModality

__all__ = [
    "DECISION_ALLOW",
    "DECISION_BLOCKED",
    "DECISION_DEFER",
    "DECISION_MANUAL_REQUIRED",
    "DECISION_REUSE_REQUIRED",
    "DECISIONS",
    "DEFAULT_QUOTA_POLICY",
    "PRIORITY_DETERMINISTIC",
    "PRIORITY_EVIDENCE",
    "PRIORITY_GENERATED_IMAGE",
    "PRIORITY_GENERATED_VIDEO",
    "PRIORITY_REUSE",
    "PRIORITY_SPEECH",
    "MediaQuotaPolicy",
    "PlannedMediaAction",
    "QuotaDecision",
    "QuotaScheduler",
    "SchedulingOutcome",
    "priority_for",
]

DECISION_ALLOW = "ALLOW"
DECISION_REUSE_REQUIRED = "REUSE_REQUIRED"
DECISION_DEFER = "DEFER"
DECISION_MANUAL_REQUIRED = "MANUAL_REQUIRED"
DECISION_BLOCKED = "BLOCKED"

DECISIONS: Tuple[str, ...] = (
    DECISION_ALLOW,
    DECISION_REUSE_REQUIRED,
    DECISION_DEFER,
    DECISION_MANUAL_REQUIRED,
    DECISION_BLOCKED,
)


@dataclass(frozen=True)
class MediaQuotaPolicy:
    """Explicit, human-chosen limits. Every field is a decision, not a derivation.

    Attributes:
        weekly_floor_percent: refuse to start new video work below this much
            weekly usage. Chosen by an operator. **Not** derived from the
            observed ~7pp delta.
        require_interval_for_speech: speech consumes the 5-hour window.
        require_interval_for_image: image consumes the 5-hour window.
        require_interval_for_video: video does **not** consume it, and requiring
            it would be wrong — the field exists so that relationship is stated
            rather than assumed.
        allow_payg: permanently false. Present as a field so a policy object can
            never be constructed while quietly permitting it.
        allow_credit_pack: permanently false, same reason.
        video_requires_declared_budget: a video action must carry a declared
            quota budget before it is scheduled.
        minimum_weekly_percent_to_schedule_video: additional per-action floor, so
            one video does not consume the whole remaining window in a plan with
            several.
    """

    weekly_floor_percent: float = 20.0
    require_interval_for_speech: bool = True
    require_interval_for_image: bool = True
    require_interval_for_video: bool = False
    allow_payg: bool = False
    allow_credit_pack: bool = False
    video_requires_declared_budget: bool = True
    minimum_weekly_percent_to_schedule_video: float = 15.0

    def __post_init__(self) -> None:
        if self.allow_payg:
            raise ValueError(
                "allow_payg cannot be enabled. ContentOps is subscription-only; "
                "a policy that permitted it would be a configuration that "
                "silently authorises cash spend."
            )
        if self.allow_credit_pack:
            raise ValueError(
                "allow_credit_pack cannot be enabled. M Plan falls through to "
                "Credit Packs once included quota is exhausted, and that is not "
                "authorised spend."
            )
        if not 0.0 <= self.weekly_floor_percent <= 100.0:
            raise ValueError(
                f"weekly_floor_percent must be a percentage, got "
                f"{self.weekly_floor_percent!r}"
            )
        if not 0.0 <= self.minimum_weekly_percent_to_schedule_video <= 100.0:
            raise ValueError(
                "minimum_weekly_percent_to_schedule_video must be a percentage, "
                f"got {self.minimum_weekly_percent_to_schedule_video!r}"
            )

    def windows_for(self, modality: str) -> Tuple[str, ...]:
        """Which usage windows this modality's policy consults.

        Reads the modality window table that ``BillingGuard`` already owns rather
        than restating it, so the scheduler and the gate cannot disagree about
        whether video draws the 5-hour window. The ``require_interval_*`` fields
        are then an assertion about that table rather than a second source of
        truth: a mismatch is refused here instead of producing a wrong decision.
        """
        canonical = MediaModality.canonical(modality)
        # ``MODALITY_WINDOWS`` is keyed by the gate's own lowercase modality
        # names. Folding here rather than duplicating the table keeps one source
        # of truth for which windows a modality consumes.
        windows = MODALITY_WINDOWS.get(canonical.lower())
        if windows is None:
            raise ValueError(
                f"modality {canonical!r} has no usage windows defined in "
                f"BillingGuard; refusing to guess"
            )
        declared = {
            "speech": self.require_interval_for_speech,
            "image": self.require_interval_for_image,
            "video": self.require_interval_for_video,
        }[canonical.lower()]
        actual = "interval" in windows
        if declared != actual:
            raise ValueError(
                f"policy says require_interval_for_{canonical}={declared} but "
                f"BillingGuard.MODALITY_WINDOWS says {windows}. Refusing to "
                f"schedule against a window model that disagrees with the gate."
            )
        return windows

    def as_dict(self) -> Dict[str, Any]:
        return {
            "weekly_floor_percent": self.weekly_floor_percent,
            "require_interval_for_speech": self.require_interval_for_speech,
            "require_interval_for_image": self.require_interval_for_image,
            "require_interval_for_video": self.require_interval_for_video,
            "allow_payg": self.allow_payg,
            "allow_credit_pack": self.allow_credit_pack,
            "video_requires_declared_budget": self.video_requires_declared_budget,
            "minimum_weekly_percent_to_schedule_video":
                self.minimum_weekly_percent_to_schedule_video,
            "basis": (
                "explicit operator policy. The weekly floors are chosen values, "
                "not derived from any observed quota delta, and the provider "
                "exposes percentages only."
            ),
        }


DEFAULT_QUOTA_POLICY = MediaQuotaPolicy()


@dataclass
class PlannedMediaAction:
    """One thing the plan wants to make.

    ``reusable`` is the highest-priority fact about an action: something already
    on disk that satisfies it needs no quota, no network and no decision beyond
    confirming it is still valid.
    """

    action_id: str
    modality: str
    #: Lower runs earlier. Set by the caller from the documented policy order.
    priority: int = 50
    #: True when the beat asserts a fact and may only use evidence-capable media.
    requires_evidence: bool = False
    #: True when a valid cached asset already satisfies this action.
    reusable: bool = False
    #: A video action's declared budget, e.g. ``"7pp"``.
    declared_budget: Optional[str] = None
    #: What this action would produce, for a human reading the decision record.
    description: str = ""
    #: Set when a person must do it and no code path can.
    manual_only: bool = False

    def __post_init__(self) -> None:
        MediaModality.canonical(self.modality)

    @property
    def is_generation(self) -> bool:
        return not self.reusable and not self.manual_only


@dataclass
class QuotaDecision:
    """What the scheduler decided for one action, and why."""

    action_id: str
    modality: str
    decision: str
    reasons: List[str] = field(default_factory=list)
    #: The policy values in force when this decision was made. Recorded on every
    #: decision so a later reader can tell what the rules were, not just what
    #: happened.
    policy: Dict[str, Any] = field(default_factory=dict)
    observed: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.decision not in DECISIONS:
            raise ValueError(
                f"unknown scheduling decision {self.decision!r}; expected one of "
                f"{', '.join(DECISIONS)}"
            )

    @property
    def allowed(self) -> bool:
        return self.decision == DECISION_ALLOW

    def as_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "modality": self.modality,
            "decision": self.decision,
            "reasons": list(self.reasons),
            "policy": dict(self.policy),
            "observed": dict(self.observed),
        }


@dataclass
class SchedulingOutcome:
    """Every decision from one pass, in the order they were considered."""

    decisions: List[QuotaDecision] = field(default_factory=list)
    #: Actions sorted into execution order. Ties break on action_id so the order
    #: is reproducible rather than dependent on input order.
    execution_order: List[str] = field(default_factory=list)
    deferred: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)
    manual_required: List[str] = field(default_factory=list)

    def decision_for(self, action_id: str) -> Optional[QuotaDecision]:
        for decision in self.decisions:
            if decision.action_id == action_id:
                return decision
        return None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "decisions": [d.as_dict() for d in self.decisions],
            "execution_order": list(self.execution_order),
            "deferred": list(self.deferred),
            "blocked": list(self.blocked),
            "manual_required": list(self.manual_required),
        }


class QuotaScheduler:
    """Order planned actions and decide which may proceed.

    Stateless with respect to quota: it never calls a provider. It takes one
    snapshot and applies one policy. That is what makes the decision reproducible
    and what keeps it from becoming a second, weaker billing gate.
    """

    def __init__(
        self,
        *,
        policy: Optional[MediaQuotaPolicy] = None,
        balances: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._policy = policy if policy is not None else DEFAULT_QUOTA_POLICY
        #: Paid-balance readings, if the caller has them. Empty means "not
        #: supplied", which is treated as *unknown* and therefore blocks
        #: generation, never as zero.
        self._balances = dict(balances) if balances else {}

    @property
    def policy(self) -> MediaQuotaPolicy:
        return self._policy

    def _paid_balances_safe(self, reasons: List[str]) -> bool:
        """All four paid balances must be present and exactly zero.

        Missing is *not* zero. "I could not check" and "it is zero" are different
        claims and only one of them is safe to bill against.
        """
        required = ("cash_balance", "credit_balance", "voucher_balance", "owed_amount")
        safe = True
        for name in required:
            if name not in self._balances:
                reasons.append(
                    f"{name} was not supplied; an unreadable balance is never "
                    f"treated as zero"
                )
                safe = False
                continue
            try:
                value = float(str(self._balances[name]))
            except (TypeError, ValueError):
                reasons.append(f"{name} is unreadable: {self._balances[name]!r}")
                safe = False
                continue
            if value != 0:
                reasons.append(
                    f"{name} is {value}, so paid funds could be consumed; "
                    f"subscription-only spend requires it to be zero"
                )
                safe = False
        return safe

    def _observed(self, modality: str, snapshot: QuotaSnapshot) -> Dict[str, Any]:
        return {
            "interval_remaining_percent": snapshot.interval_remaining_percent,
            "weekly_remaining_percent": snapshot.weekly_remaining_percent,
            "windows_consulted": list(self._policy.windows_for(modality)),
        }

    def _window_failures(self, modality: str, snapshot: QuotaSnapshot) -> List[str]:
        failures: List[str] = []
        for window in self._policy.windows_for(modality):
            if window == "interval":
                value = snapshot.interval_remaining_percent
                label = "interval_remaining_percent"
            else:
                value = snapshot.weekly_remaining_percent
                label = "weekly_remaining_percent"
            if value is None:
                failures.append(
                    f"{modality} requires the {label} window and it is unknown; an "
                    f"unreadable window is never treated as available"
                )
            elif value <= 0:
                failures.append(
                    f"{modality} requires the {label} window and it is exhausted "
                    f"({value})"
                )
        return failures

    def schedule(
        self,
        actions: Sequence[PlannedMediaAction],
        snapshot: QuotaSnapshot,
    ) -> SchedulingOutcome:
        """Decide every action against one snapshot, in policy order.

        ``snapshot`` is read once and shared by every decision. MiniMax modalities
        share one account plan, so per-action fetches would answer the same
        question inconsistently.
        """
        outcome = SchedulingOutcome()
        policy_record = self._policy.as_dict()

        # Priority first, then action_id so a tie is reproducible rather than
        # dependent on the caller's ordering.
        ordered = sorted(actions, key=lambda a: (a.priority, a.action_id))

        for action in ordered:
            modality = MediaModality.canonical(action.modality)
            reasons: List[str] = []
            observed = self._observed(modality, snapshot)

            if action.manual_only:
                decision = DECISION_MANUAL_REQUIRED
                reasons.append(
                    "this action needs a person; no code path produces it. "
                    "Reported rather than substituted."
                )
            elif action.reusable:
                # Cheapest and safest: no quota, no network, no provider.
                decision = DECISION_REUSE_REQUIRED
                reasons.append(
                    "a valid asset already satisfies this action, so it consumes "
                    "no quota and no provider call"
                )
            elif not self._paid_balances_safe(reasons):
                decision = DECISION_BLOCKED
            else:
                window_failures = self._window_failures(modality, snapshot)
                if window_failures:
                    decision = DECISION_BLOCKED
                    reasons.extend(window_failures)
                elif modality == MediaModality.VIDEO:
                    decision, video_reasons = self._decide_video(
                        action, snapshot, reasons
                    )
                    reasons.extend(video_reasons)
                else:
                    decision = DECISION_ALLOW

            outcome.decisions.append(
                QuotaDecision(
                    action_id=action.action_id,
                    modality=modality,
                    decision=decision,
                    reasons=reasons or ["policy conditions satisfied"],
                    policy=policy_record,
                    observed=observed,
                )
            )
            if decision == DECISION_ALLOW:
                outcome.execution_order.append(action.action_id)
            elif decision == DECISION_DEFER:
                outcome.deferred.append(action.action_id)
            elif decision == DECISION_BLOCKED:
                outcome.blocked.append(action.action_id)
            elif decision == DECISION_MANUAL_REQUIRED:
                outcome.manual_required.append(action.action_id)

        return outcome

    def _decide_video(
        self,
        action: PlannedMediaAction,
        snapshot: QuotaSnapshot,
        reasons: List[str],
    ) -> Tuple[str, List[str]]:
        """Video: the weekly floor and a declared budget, or defer.

        Video is deferred rather than blocked when the floor is not met. The
        distinction is operational, not semantic: a blocked action is wrong, a
        deferred one is merely not now, and video legitimately becomes available
        next week. Neither is ever silently allowed.
        """
        extra: List[str] = []
        weekly = snapshot.weekly_remaining_percent

        if self._policy.video_requires_declared_budget and not (
            action.declared_budget or ""
        ).strip():
            # No budget is a planning omission, not a provider state, so it
            # blocks: proceeding without one would make the spend unattributable.
            extra.append(
                "no declared quota budget; a video task is the most expensive "
                "call ContentOps makes and its spend must be written down first"
            )
            return DECISION_BLOCKED, extra

        if weekly is None:
            extra.append(
                "weekly remaining is unknown, so it cannot be compared with the "
                f"configured floor of {self._policy.weekly_floor_percent}%"
            )
            return DECISION_BLOCKED, extra

        if weekly < self._policy.weekly_floor_percent:
            extra.append(
                f"weekly remaining {weekly}% is below the configured floor of "
                f"{self._policy.weekly_floor_percent}%; deferring video rather "
                f"than starting work that would starve narration and evidence"
            )
            return DECISION_DEFER, extra

        if weekly < self._policy.minimum_weekly_percent_to_schedule_video:
            extra.append(
                f"weekly remaining {weekly}% is below the per-action minimum of "
                f"{self._policy.minimum_weekly_percent_to_schedule_video}% for "
                f"video"
            )
            return DECISION_DEFER, extra

        extra.append(
            f"weekly remaining {weekly}% meets the configured floor of "
            f"{self._policy.weekly_floor_percent}% and the declared budget is "
            f"{action.declared_budget!r}"
        )
        return DECISION_ALLOW, extra


#: The documented policy order. Lower number runs first. Assigned here rather
#: than at each call site so the ordering is one list, and so a test can assert
#: the order rather than infer it.
PRIORITY_REUSE = 10
PRIORITY_EVIDENCE = 20
PRIORITY_SPEECH = 30
PRIORITY_DETERMINISTIC = 40
PRIORITY_GENERATED_IMAGE = 50
PRIORITY_GENERATED_VIDEO = 60


def priority_for(*, modality: str, requires_evidence: bool) -> int:
    """The documented policy priority for one action.

    Evidence outranks narration outranks deterministic local assets outranks
    generated image outranks generated video. A generated shot is the most
    expensive thing to make and the least load-bearing for a truthful video, so
    it goes last.
    """
    canonical = MediaModality.canonical(modality)
    if requires_evidence:
        return PRIORITY_EVIDENCE
    if canonical == MediaModality.SPEECH:
        return PRIORITY_SPEECH
    if canonical == MediaModality.VIDEO:
        return PRIORITY_GENERATED_VIDEO
    return PRIORITY_GENERATED_IMAGE
