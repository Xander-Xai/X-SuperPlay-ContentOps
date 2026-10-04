"""Test-only video duration policy.

This module governs **development, research, smoke and regression video
requests only**. It has no authority over production shot duration.

Why the rule exists
-------------------
Video is the most expensive modality in the M Plan Explore subscription. One
4 s 768P H3 job consumed **7 weekly percentage points** of the weekly window, and
video is subject only to that weekly window. A careless 10 s "quick check"
therefore costs more than the shortest legal check would.

The rule
--------
Preferred test duration is **1-3 s**, but only where the provider actually
supports it. If the provider minimum is greater than 3 s, use the provider
minimum. Never send an unsupported 1 s / 2 s / 3 s request just because it is
cheaper: an invalid request wastes a round trip and proves nothing.

Any test longer than the provider minimum must be justified in the receipt with
``test_objective``, ``why_minimum_is_insufficient`` and an explicit
``quota_budget``.

Current verified provider minima
--------------------------------
Re-verified 2026-10-04 against the current public API schema, the official CLI
help, and the real M2.0 receipt:

| Model | Output duration | Source |
|---|---|---|
| ``MiniMax-H3`` | integer enum, **4-15** | current v2 create-task API schema; CLI help "4 to 15"; M2.0 requested 4 and succeeded |
| ``MiniMax-H3-Max`` | integer enum, **5-15** | same schema; CLI does not expose the model |

So for H3 the effective test duration is **4 s** today, and for H3 Max it would
be 5 s. Both are provider minima, not preferences.

Reference input clips are a different thing: each reference video or audio clip
is 2-15 s with a 15 s total. That constraint is about inputs and does not change
the output duration rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

__all__ = [
    "PREFERRED_TEST_DURATION_RANGE",
    "ProviderDurationSpec",
    "TestDurationDecision",
    "H3_DURATION_SPEC",
    "H3_MAX_DURATION_SPEC",
    "decide_test_duration",
]

#: The preferred window for a cheap test, in seconds.
PREFERRED_TEST_DURATION_RANGE = (1, 3)


@dataclass(frozen=True)
class ProviderDurationSpec:
    """What one model actually accepts, as currently documented."""

    model: str
    minimum_s: int
    maximum_s: int
    allowed: Sequence[int]
    value_kind: str = "integer_enum"
    checked_at: str = "2026-10-04"
    source: str = "current v2 create-task API schema + official CLI help + M2.0 receipt"

    def supports(self, seconds: int) -> bool:
        return seconds in self.allowed


@dataclass(frozen=True)
class TestDurationDecision:
    duration_s: int
    is_provider_minimum: bool
    preferred_applied: bool
    requires_justification: bool
    justification_fields: List[str]
    reason: str
    spec: ProviderDurationSpec

    def as_dict(self) -> Dict[str, object]:
        return {
            "model": self.spec.model,
            "duration_s": self.duration_s,
            "is_provider_minimum": self.is_provider_minimum,
            "preferred_applied": self.preferred_applied,
            "requires_justification": self.requires_justification,
            "justification_fields": list(self.justification_fields),
            "reason": self.reason,
            "provider_range_s": [self.spec.minimum_s, self.spec.maximum_s],
            "provider_value_kind": self.spec.value_kind,
            "checked_at": self.spec.checked_at,
            "source": self.spec.source,
        }


#: ``MiniMax-H3``: integer enum 4-15, verified.
H3_DURATION_SPEC = ProviderDurationSpec(
    model="MiniMax-H3",
    minimum_s=4,
    maximum_s=15,
    allowed=tuple(range(4, 16)),
)

#: ``MiniMax-H3-Max``: integer enum 5-15, verified; 4 s is not supported.
H3_MAX_DURATION_SPEC = ProviderDurationSpec(
    model="MiniMax-H3-Max",
    minimum_s=5,
    maximum_s=15,
    allowed=tuple(range(5, 16)),
)


def decide_test_duration(
    spec: ProviderDurationSpec,
    *,
    objective: Optional[str] = None,
    why_minimum_is_insufficient: Optional[str] = None,
    quota_budget: Optional[str] = None,
    requested_s: Optional[int] = None,
) -> TestDurationDecision:
    """Choose the shortest legal test duration for ``spec``.

    ``requested_s`` is honoured only when it is both legal and not longer than
    the provider minimum plus a stated justification. The point of the function
    is that "I typed 10" cannot quietly become the test duration.
    """
    low, high = PREFERRED_TEST_DURATION_RANGE
    minimum = spec.minimum_s

    if minimum <= high:
        chosen = max(minimum, low)
        preferred_applied = True
        reason = (
            f"provider minimum {minimum}s is inside the preferred "
            f"{low}-{high}s window, so the preferred minimum is used"
        )
    else:
        chosen = minimum
        preferred_applied = False
        reason = (
            f"provider minimum {minimum}s exceeds the preferred {low}-{high}s "
            f"window, so the provider minimum is used; sending a shorter "
            f"unsupported value would waste a request and prove nothing"
        )

    if requested_s is not None and requested_s != chosen:
        if not spec.supports(requested_s):
            raise ValueError(
                f"{spec.model} does not support {requested_s}s; "
                f"allowed values are {spec.minimum_s}-{spec.maximum_s}"
            )
        if requested_s > minimum:
            # A longer request is allowed, but never silently.
            chosen = requested_s
            preferred_applied = False
            reason = (
                f"explicitly requested {requested_s}s, longer than the provider "
                f"minimum {minimum}s, so a justification is mandatory"
            )

    needs_justification = chosen > minimum
    fields: List[str] = []
    if needs_justification:
        if not objective:
            fields.append("test_objective")
        if not why_minimum_is_insufficient:
            fields.append("why_minimum_is_insufficient")
        if not quota_budget:
            fields.append("quota_budget")

    return TestDurationDecision(
        duration_s=chosen,
        is_provider_minimum=chosen == minimum,
        preferred_applied=preferred_applied,
        requires_justification=needs_justification,
        justification_fields=fields,
        reason=reason,
        spec=spec,
    )