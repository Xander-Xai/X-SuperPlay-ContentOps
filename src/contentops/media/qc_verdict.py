"""One technical-QC release rule for every video entry.

``qc_video`` owns the verdict. This module decides whether that verdict may
continue. It never rewrites ``WARN`` or ``FAIL`` into ``PASS``, and it never
grants production or publication authority.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

__all__ = ["judge_technical_qc", "project_is_account_bound"]


def project_is_account_bound(project: Path) -> bool:
    """True when the project names an account, or its config cannot be read.

    An unreadable ``project.yaml`` cannot prove the project is a historical
    sample, so it fails closed. A missing file is the historical case.
    """
    path = project / "project.yaml"
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return True
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not (line.startswith("account_slug:") or line.startswith("account_id:")):
            continue
        value = line.split(":", 1)[1].strip().strip("'\"")
        if value and value not in {"null", "None", "~"}:
            return True
    return False


def judge_technical_qc(
    report: Dict[str, Any],
    *,
    has_audio: bool,
    account_bound: bool,
    graded_target: str,
) -> Dict[str, Any]:
    """Decide whether one canonical QC receipt may continue.

    The returned ``overall`` is the receipt's overall, unchanged. ``blocked``
    is the only release switch. Approval flags are always false.
    """
    overall = report.get("overall")
    decision: Dict[str, Any] = {
        "overall": overall,
        "blocked": True,
        "reason": "QC_NOT_PASS",
        "historical_exception": False,
        "production_ready": False,
        "publish_authorized": False,
    }
    if report.get("graded_target") != graded_target:
        decision["reason"] = "REPORT_TARGET_MISMATCH"
        return decision
    if not has_audio:
        decision["reason"] = "MISSING_AUDIO"
        return decision
    if overall == "FAIL":
        decision["reason"] = "QC_FAIL"
        return decision
    if overall == "WARN" and account_bound:
        decision["reason"] = "QC_WARN_ACCOUNT_BOUND"
        return decision
    if overall == "WARN":
        decision["blocked"] = False
        decision["reason"] = "HISTORICAL_WARN"
        decision["historical_exception"] = True
        return decision
    if overall == "PASS":
        decision["blocked"] = False
        decision["reason"] = None
        return decision
    return decision
