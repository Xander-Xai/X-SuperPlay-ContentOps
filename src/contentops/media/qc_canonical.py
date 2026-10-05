"""The canonical, portable serialization of a QC result.

Why this module exists
----------------------
``qc_video`` is a runtime tool. It reads files with real paths, and its report
legitimately names them: ``final.mp4 not found at D:\\...\\final.mp4`` is an
accurate, useful diagnostic *at the moment it is produced*.

That is a different concern from what a committed artifact should contain. Two QC
reports were tracked side by side:

- ``qc-report-m45.json``  — ``WARN``, graded ``final/m45.mp4`` (the real target)
- ``qc-report-final.json`` — ``FAIL``, graded ``final/final.mp4`` (never produced)

They looked equally current and contradicted each other, and both carried absolute
``D:\\Projects\\...`` paths. So this module is the **boundary**: it takes the runtime
result verbatim, sanitizes it through the logical-path contract, and writes the
tracked receipt. ``qc_video`` internals are untouched — it keeps reporting the truth
about the machine it ran on.

Currency is declared, never inferred
------------------------------------
Every canonical report states ``currency`` and the ``graded_target`` it applies to.
That is what stops the next stale report from being mistaken for truth: a reader can
see *what* was graded and *whether it is current*, instead of having to infer it from
a filename or a modification date.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from contentops.media.media_paths import sanitize_embedded_paths

__all__ = [
    "CURRENCY_CURRENT",
    "CURRENCY_NON_CURRENT_DIAGNOSTIC",
    "QC_CANONICAL_SCHEMA",
    "canonical_qc_report",
    "render_canonical_qc_markdown",
    "write_canonical_qc_receipt",
]

QC_CANONICAL_SCHEMA = "contentops.qc-canonical/v1"

#: This report describes the artifact that exists.
CURRENCY_CURRENT = "CURRENT"
#: Retained for diagnosis only. Must never be cited as the current result.
CURRENCY_NON_CURRENT_DIAGNOSTIC = "NON_CURRENT_DIAGNOSTIC"


def _sanitize(value: Any, *, repo_root: Path, project_root: Optional[Path]) -> Any:
    """Rewrite every string in a nested structure, keys included."""
    if isinstance(value, dict):
        return {
            _sanitize(key, repo_root=repo_root, project_root=project_root): _sanitize(
                item, repo_root=repo_root, project_root=project_root
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _sanitize(item, repo_root=repo_root, project_root=project_root)
            for item in value
        ]
    if isinstance(value, str):
        return sanitize_embedded_paths(
            value, repo_root=repo_root, project_root=project_root
        )
    return value


def canonical_qc_report(
    runtime: Dict[str, Any],
    *,
    repo_root: Path,
    project_root: Path,
    graded_target: Optional[str] = None,
    currency: str = CURRENCY_CURRENT,
    non_current_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Turn a runtime ``qc_video`` result into a portable, self-describing receipt.

    Args:
        runtime: the ``qc_video`` result, verbatim. Its ``overall`` and ``checks``
            are preserved exactly — sanitizing paths must never change a verdict.
        repo_root: where ``repo://`` references resolve.
        project_root: where ``project://`` references resolve.
        graded_target: logical reference for the file actually graded, e.g.
            ``project://final/m45.mp4``. Recorded so a reader can tell which
            artifact a verdict is about without inferring it from a filename.
        currency: :data:`CURRENCY_CURRENT` or
            :data:`CURRENCY_NON_CURRENT_DIAGNOSTIC`.
        non_current_reason: required when ``currency`` is non-current. A stale report
            is acceptable to keep; a stale report with no stated reason is not.

    Raises:
        ValueError: a non-current report was declared without a reason.
    """
    if currency == CURRENCY_NON_CURRENT_DIAGNOSTIC and not non_current_reason:
        raise ValueError(
            "a non-current QC report must state why it is not current; an "
            "unexplained stale result is indistinguishable from a real one"
        )

    sanitized = _sanitize(runtime, repo_root=repo_root, project_root=project_root)
    report: Dict[str, Any] = {
        "schema": QC_CANONICAL_SCHEMA,
        "currency": currency,
        "project": sanitized.get("project", ""),
        "graded_target": graded_target or sanitized.get("video", ""),
        "overall": sanitized.get("overall"),
        "checked_at": sanitized.get("checked_at"),
        "checks": sanitized.get("checks", []),
        "path_policy": "logical references (project://, repo://); no absolute paths",
    }
    if non_current_reason:
        report["non_current_reason"] = non_current_reason
    if runtime.get("video"):
        report["video"] = sanitized.get("video")
    return report


def _detail_fields(check: Dict[str, Any]) -> str:
    """The non-structural fields of a check, joined for the markdown table."""
    reserved = {"id", "ok", "severity"}
    parts = [
        f"{key}={value}"
        for key, value in check.items()
        if key not in reserved and value not in (None, "", [], {})
    ]
    return ", ".join(parts)


def render_canonical_qc_markdown(report: Dict[str, Any], *, project_name: str) -> str:
    """Human-readable view of a canonical report, with no machine paths.

    Generated from the sanitized report rather than from the runtime result, so the
    markdown cannot drift from the JSON or reintroduce a path the JSON does not have.
    """
    checks: Iterable[Dict[str, Any]] = report.get("checks") or []
    lines = [
        f"# QC Report — {project_name}",
        "",
        f"**Currency**: `{report.get('currency')}`",
        f"**Graded target**: `{report.get('graded_target') or '(none)'}`",
        f"**Overall**: `{report.get('overall')}`",
        f"**Checked at**: {report.get('checked_at') or '(not recorded)'}",
    ]
    if report.get("non_current_reason"):
        lines.extend(["", f"**Not current because**: {report['non_current_reason']}"])
    lines.extend(["", f"**Paths**: {report.get('path_policy')}", ""])
    lines.append("| Check | Status | Severity | Detail |")
    lines.append("|---|---|---|---|")
    for check in checks:
        lines.append(
            f"| {check.get('id')} "
            f"| {'OK' if check.get('ok') else 'FAIL'} "
            f"| {check.get('severity', 'PASS')} "
            f"| {_detail_fields(check)} |"
        )
    return "\n".join(lines) + "\n"


def write_canonical_qc_receipt(
    project_root: Path,
    runtime: Dict[str, Any],
    *,
    repo_root: Path,
    name: str,
    graded_target: Optional[str] = None,
    currency: str = CURRENCY_CURRENT,
    non_current_reason: Optional[str] = None,
) -> List[Path]:
    """Write the sanitized ``<name>.json`` and ``<name>.md`` receipts.

    Overwrites whatever ``qc_video`` wrote at the same path. That is deliberate:
    ``qc_video`` writes its raw, machine-local report first, and this rewrites it in
    place, so there is exactly one file per report rather than a raw copy and a
    sanitized copy that can disagree.

    Returns:
        The paths written.
    """
    project_root = Path(project_root)
    report = canonical_qc_report(
        runtime,
        repo_root=repo_root,
        project_root=project_root,
        graded_target=graded_target,
        currency=currency,
        non_current_reason=non_current_reason,
    )
    receipts = project_root / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    json_path = receipts / f"{name}.json"
    md_path = receipts / f"{name}.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    md_path.write_text(
        render_canonical_qc_markdown(report, project_name=project_root.name),
        encoding="utf-8",
    )
    return [json_path, md_path]