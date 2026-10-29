"""One report, one verdict.

The repository already learned this the expensive way: two tracked QC reports
sat side by side, one PASS and one FAIL, both looking current. A reader could
not tell which described the cut on disk, so both were treated as equally true.

So a quality report here:

- is deterministic (checks are sorted, no timestamp in the body);
- carries exactly one ``verdict`` for exactly one ``graded_target``;
- never reports ``production_ready`` on its own -- a human review is a separate
  artifact and cannot be synthesized by a passing check.

Severity is per check, and FAIL outranks WARN. A check that did not run is not
a pass; it is simply absent, and :func:`build_report` records the count so the
gap is visible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List

SCHEMA = "contentops.quality-report/v1"
SEVERITIES = ("FAIL", "WARN", "INFO")


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    ok: bool
    severity: str = "FAIL"
    detail: str = ""
    measured: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.check_id or not self.check_id.strip():
            raise ValueError("check_id must be a non-empty string")
        if self.severity not in SEVERITIES:
            raise ValueError(f"severity must be one of {SEVERITIES}, got {self.severity!r}")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "ok": self.ok,
            # Severity describes a failure. On a passing check it would read as
            # "PASS but severity FAIL", so it is null rather than misleading.
            "severity": None if self.ok else self.severity,
            "detail": self.detail,
            "measured": dict(sorted(self.measured.items())),
        }


def verdict(checks: Iterable[CheckResult]) -> str:
    failed = False
    warned = False
    for check in checks:
        if check.ok:
            continue
        if check.severity == "FAIL":
            failed = True
        elif check.severity == "WARN":
            warned = True
    if failed:
        return "FAIL"
    if warned:
        return "WARN"
    return "PASS"


def build_report(graded_target: str,
                 checks: Iterable[CheckResult],
                 currency: str = "CURRENT") -> Dict[str, Any]:
    """Build the canonical report body. Nothing here can mark a cut ready."""
    if not graded_target or not graded_target.strip():
        raise ValueError("graded_target must name the artifact this report grades")
    if currency not in ("CURRENT", "STALE"):
        raise ValueError("currency must be CURRENT or STALE")
    ordered: List[CheckResult] = sorted(checks, key=lambda item: item.check_id)
    return {
        "schema": SCHEMA,
        "graded_target": graded_target,
        "currency": currency,
        "verdict": verdict(ordered),
        "check_count": len(ordered),
        "failed_count": sum(1 for item in ordered if not item.ok and item.severity == "FAIL"),
        "warned_count": sum(1 for item in ordered if not item.ok and item.severity == "WARN"),
        "checks": [item.as_dict() for item in ordered],
        "production_ready": False,
        "human_review": "PENDING",
    }
