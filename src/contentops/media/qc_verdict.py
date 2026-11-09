"""One adjudication for one canonical QC receipt.

The defect this replaces
------------------------
``m5_production.stage_qc`` used to compute
``"PASS" if report.get("overall") != "FAIL" and has_audio else "FAIL"`` and store it
as ``overall_after_m5``. ``produce_video`` then required
``report["overall"] == "PASS"``. A ``WARN`` render was therefore released inside M5
and blocked at the outer entry point: the same receipt, two opposite answers,
depending on which door you came through.

The rule that fixes it
----------------------
``qc_video``'s ``overall`` is preserved verbatim — a sanitizer or an orchestrator
must never rewrite a verdict, because then no receipt can be cited. This module
does not touch it. It answers a different, separate question: *may this artifact
proceed?* and records why.

``WARN`` is the interesting case, and it is not a single rule:

* an **account-bound** project blocks on WARN. A warning on a render that will be
  published under a real account is a decision, not noise.
* a **historical, unbound** sample may proceed, because the alternative is
  retroactively invalidating committed samples that were never claimed to be
  publishable. The tolerance is recorded as ``legacy_warn_tolerated`` so it is
  visible in the receipt rather than implied.

Everything unknown fails closed. An absent or unrecognised ``overall`` is not a
pass; it is an unreadable verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

__all__ = [
    "BLOCK",
    "PROCEED",
    "QcVerdict",
    "adjudicate",
    "KNOWN_OVERALL",
]

PROCEED = "PROCEED"
BLOCK = "BLOCK"

#: The only values ``qc_video`` may emit. Anything else is treated as unreadable.
KNOWN_OVERALL = ("PASS", "WARN", "FAIL")


@dataclass(frozen=True)
class QcVerdict:
    """The answer to "may this render proceed" plus the reasoning behind it."""

    overall: Optional[str]
    decision: str
    account_bound: bool
    audio_present: bool
    reasons: Tuple[str, ...] = field(default_factory=tuple)
    legacy_warn_tolerated: bool = False

    @property
    def blocked(self) -> bool:
        return self.decision == BLOCK

    def as_dict(self) -> Dict[str, Any]:
        return {
            "overall": self.overall,
            "decision": self.decision,
            "account_bound": self.account_bound,
            "audio_present": self.audio_present,
            "reasons": list(self.reasons),
            "legacy_warn_tolerated": self.legacy_warn_tolerated,
        }


def adjudicate(
    report: Dict[str, Any],
    *,
    account_bound: bool,
    audio_present: bool,
) -> QcVerdict:
    """Decide whether a canonical QC receipt lets a render proceed.

    Args:
        report: the canonical receipt. ``overall`` is read, never written.
        account_bound: the project declares an ``account_slug``.
        audio_present: the graded file actually carries an audio stream. A silent
            video is not a warning here — the whole product is narration.
    """
    overall = report.get("overall")
    reasons = []

    if overall not in KNOWN_OVERALL:
        return QcVerdict(
            overall=overall,
            decision=BLOCK,
            account_bound=account_bound,
            audio_present=audio_present,
            reasons=(f"unreadable overall {overall!r}; expected one of {KNOWN_OVERALL}",),
        )

    if not audio_present:
        reasons.append("the graded render has no audio stream")

    if overall == "FAIL":
        reasons.append("qc_video reported FAIL")

    if reasons:
        return QcVerdict(overall=overall, decision=BLOCK, account_bound=account_bound,
                         audio_present=audio_present, reasons=tuple(reasons))

    if overall == "WARN":
        if account_bound:
            return QcVerdict(
                overall=overall, decision=BLOCK, account_bound=True,
                audio_present=audio_present,
                reasons=("qc_video reported WARN on an account-bound project",),
            )
        return QcVerdict(
            overall=overall, decision=PROCEED, account_bound=False,
            audio_present=audio_present,
            reasons=("qc_video reported WARN; tolerated for an unbound historical sample",),
            legacy_warn_tolerated=True,
        )

    return QcVerdict(overall=overall, decision=PROCEED, account_bound=account_bound,
                     audio_present=audio_present, reasons=())
