"""Manual post-publication metrics: import, refuse, look, and stop.

What this module will not do
----------------------------
It does not log in anywhere, does not scrape a creator centre, and does not
estimate a number that was not exported. Official figures come from the creator's
own export — YouTube exposes impressions, CTR, watch time, average view duration
and audience retention; Douyin's creator centre exposes作品, completion and traffic
source data. Anything else is a fiction with a decimal point.

A report that is missing a field is **rejected**, not defaulted. A missing metric
stays missing. That is the whole discipline: the moment a pipeline fills gaps with
plausible numbers, the numbers stop meaning anything.

Why metrics never flow back
---------------------------
This module reads. It returns observations and one variable worth testing next
round. It cannot touch the script, the QC verdict or ``production_ready`` — the
review receipt states those as `false` and a test asserts no such key is ever
produced. Post-publication evidence informs a human's next decision; it does not
edit the artefact that produced it.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

__all__ = [
    "MetricsRejected",
    "Report",
    "SCHEMA_REPORT",
    "SCHEMA_REVIEW",
    "load_report",
    "load_reports",
    "review",
    "write_review",
]

SCHEMA_REPORT = "contentops.manual-metrics/v1"
SCHEMA_REVIEW = "contentops.metrics-review/v1"

REQUIRED_REPORT_FIELDS = (
    "schema",
    "platform",
    "work_url",
    "export_date",
    "source_file",
    "source_sha256",
    "metrics",
)


class MetricsRejected(ValueError):
    """The export is not usable. Carries every reason, not the first one."""

    def __init__(self, reasons: Iterable[str]) -> None:
        self.reasons = list(reasons)
        super().__init__("; ".join(self.reasons))


@dataclass(frozen=True)
class Report:
    platform: str
    work_url: str
    export_date: str
    source_file: str
    source_sha256: str
    metrics: Dict[str, float] = field(default_factory=dict)

    def observation_lines(self) -> List[str]:
        return [
            f"{self.platform} {self.export_date} {self.work_url}: {name}={value:g}"
            for name, value in sorted(self.metrics.items())
        ]


def _valid_url(value: str) -> bool:
    """Syntax only. A matching URL is not proof of publication or ownership."""
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme in {"http", "https"} and bool(parts.netloc) and not parts.username


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_report(path: Path, *, export_dir: Path) -> Report:
    """Read and validate one export. Raises :class:`MetricsRejected` on any doubt."""
    path = Path(path)
    export_dir = Path(export_dir).resolve()
    resolved = path.resolve()
    reasons: List[str] = []

    if not resolved.is_file():
        raise MetricsRejected([f"export does not exist: {path.name}"])
    if export_dir not in resolved.parents and resolved != export_dir:
        raise MetricsRejected([
            f"export must live under {export_dir.name}/, not outside it"])

    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MetricsRejected([f"export is not readable JSON: {exc}"]) from None
    if not isinstance(payload, dict):
        raise MetricsRejected(["export must be a JSON object"])

    for name in REQUIRED_REPORT_FIELDS:
        if name not in payload:
            reasons.append(f"missing required field: {name}")
    if reasons:
        raise MetricsRejected(reasons)

    if payload.get("schema") != SCHEMA_REPORT:
        reasons.append(f"schema must be {SCHEMA_REPORT!r}, got {payload.get('schema')!r}")

    platform = payload.get("platform")
    if not isinstance(platform, str) or not platform.strip():
        reasons.append("platform must be a non-empty string")

    work_url = payload.get("work_url")
    if not isinstance(work_url, str) or not _valid_url(work_url):
        reasons.append("work_url must be an http(s) URL with a host")

    export_date = payload.get("export_date")
    try:
        date.fromisoformat(str(export_date))
    except (TypeError, ValueError):
        reasons.append("export_date must be ISO YYYY-MM-DD")

    source_file = payload.get("source_file")
    if not isinstance(source_file, str) or not source_file.strip():
        reasons.append("source_file must name the exported file")
    else:
        candidate = (export_dir / source_file).resolve()
        if export_dir not in candidate.parents:
            reasons.append("source_file must stay inside the export directory")
        elif not candidate.is_file():
            reasons.append(f"source_file is not present under {export_dir.name}/")

    metrics = payload.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        reasons.append("metrics must be a non-empty object of name -> number")
    else:
        for name, value in metrics.items():
            if not isinstance(name, str) or not name.strip():
                reasons.append("metric names must be non-empty strings")
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                reasons.append(f"metric {name!r} must be a number, got {type(value).__name__}")
                continue
            if not math.isfinite(float(value)):
                reasons.append(f"metric {name!r} must be finite")

    if reasons:
        raise MetricsRejected(reasons)

    declared_sha = str(payload.get("source_sha256") or "").strip().lower()
    actual_path = (export_dir / str(source_file)).resolve()
    actual_sha = _sha256(actual_path)
    if declared_sha != actual_sha:
        raise MetricsRejected([
            "source_sha256 does not match the exported file; the export changed "
            "after the report was written"])

    return Report(
        platform=str(platform),
        work_url=str(work_url),
        export_date=str(export_date),
        source_file=str(source_file),
        source_sha256=actual_sha,
        metrics={str(k): float(v) for k, v in metrics.items()},
    )


def load_reports(export_dir: Path) -> Tuple[List[Report], List[Dict[str, Any]]]:
    """Load every export in a directory. One rejection does not hide the others."""
    export_dir = Path(export_dir)
    if not export_dir.is_dir():
        return [], [{"file": None, "reasons": [f"no export directory at {export_dir.name}/"]}]

    reports: List[Report] = []
    rejected: List[Dict[str, Any]] = []
    for path in sorted(export_dir.glob("*.json")):
        try:
            reports.append(load_report(path, export_dir=export_dir))
        except MetricsRejected as exc:
            rejected.append({"file": path.name, "reasons": exc.reasons})
    return reports, rejected


def _next_variable(reports: List[Report]) -> Optional[Dict[str, Any]]:
    """Pick one variable worth testing next round — deterministically.

    Preference order, so the answer is reproducible rather than editorial:

    1. a metric that appears in some exports but not all — the reporting gap is
       the first thing that makes later comparisons unreliable;
    2. otherwise the metric with the widest coefficient of variation across
       exports — the one behaving least predictably;
    3. otherwise the first metric of the only export.

    This names a *variable to observe*. It deliberately does not say what to change
    in the video.
    """
    if not reports:
        return None

    names = {name for report in reports for name in report.metrics}
    coverage = {name: sum(1 for r in reports if name in r.metrics) for name in names}
    incomplete = sorted(n for n, count in coverage.items() if count < len(reports))
    if incomplete:
        name = incomplete[0]
        return {
            "name": name,
            "basis": f"reported in {coverage[name]} of {len(reports)} exports",
            "note": "names a variable to report consistently; prescribes no edit",
        }

    if len(reports) > 1:
        best_name, best_cv = None, -1.0
        for name in sorted(names):
            values = [r.metrics[name] for r in reports]
            mean = statistics.fmean(values)
            if mean == 0:
                continue
            cv = statistics.pstdev(values) / abs(mean)
            if cv > best_cv:
                best_name, best_cv = name, cv
        if best_name is not None:
            return {
                "name": best_name,
                "basis": f"widest spread across exports (coefficient of variation {best_cv:.2f})",
                "note": "names a variable to watch; prescribes no edit",
            }

    first = sorted(reports[0].metrics)[0]
    return {
        "name": first,
        "basis": "only one export is available, so no comparison is possible yet",
        "note": "names a variable to keep reporting; prescribes no edit",
    }


def review(reports: List[Report], rejected: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Produce the review receipt. Observations are facts; the variable is a question."""
    rejected = list(rejected or [])
    observations: List[str] = []
    for report in reports:
        observations.extend(report.observation_lines())

    return {
        "schema": SCHEMA_REVIEW,
        "network_used": False,
        "external_action": "none",
        "imported": [
            {"platform": r.platform, "work_url": r.work_url, "export_date": r.export_date,
             "source_file": r.source_file, "source_sha256": r.source_sha256,
             "metrics": dict(sorted(r.metrics.items()))}
            for r in reports
        ],
        "rejected": rejected,
        "observations": observations,
        "next_variable": _next_variable(reports),
        "constraints": {
            "modifies_script": False,
            "modifies_qc": False,
            "modifies_production_ready": False,
            "note": "metrics inform a human decision; they never edit the artefact",
        },
        "production_ready": False,
        "publish_authorized": False,
    }


def write_review(project: Path, *, export_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Import `<project>/metrics/exports/` and write `receipts/metrics-review.json`."""
    project = Path(project)
    export_dir = Path(export_dir) if export_dir else project / "metrics" / "exports"
    reports, rejected = load_reports(export_dir)
    payload = review(reports, rejected)
    receipts = project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / "metrics-review.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
