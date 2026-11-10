"""Which metric snapshots are owed, which arrived, and which are merely absent.

Growth decisions fail quietly when ``0`` and "nobody ever recorded a number"
look identical in a CSV. A zero can mean the content genuinely got no
impressions; a missing row means the loop broke — nobody exported, nobody
typed, nobody looked. Strategy's ``EXPLORE → EXPLOIT → RETIRE`` calls need to
know which one happened.

This module audits one published piece of content against the three decision
windows the 30-day plan names: T+24H, T+72H and T+7D. Given the publication
time and the metric snapshot rows already consumed by
:mod:`contentops.x_growth_metrics` (same CSV columns), it answers per window:

- ``NOT_DUE``      — the window has not closed yet; nothing is owed.
- ``DUE_MISSING``  — the window closed and no snapshot was ever recorded.
                     This is a broken data loop, not a zero.
- ``OBSERVED``     — at least one snapshot at or after the window close
                     exists. Snapshots are cumulative, so the earliest such
                     snapshot is the window's value. ``impressions`` carries
                     the observed number, or ``None`` with
                     ``impressions_missing=True`` when the row simply has no
                     value — that is missing data inside an observed snapshot,
                     which is its own defect and its own reason string.

No value here is ever estimated, imputed or scraped. If the snapshot does not
exist, the window says so and stops.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: Window name → hours after publication when it closes.
WINDOWS: Tuple[Tuple[str, int], ...] = (
    ("T+24H", 24),
    ("T+72H", 72),
    ("T+7D", 24 * 7),
)

NOT_DUE = "NOT_DUE"
DUE_MISSING = "DUE_MISSING"
OBSERVED = "OBSERVED"

SNAPSHOT_FIELDS = (
    "content_id", "observed_at", "metric_source", "age_window",
    "impressions", "engagements", "qualified_signal_count",
)


class WindowAuditError(Exception):
    """A refusal with a code. Callers branch on the code, not the prose."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def parse_timestamp(value: Any) -> datetime:
    """Public ISO-8601 parser for CLIs; naive values are read as UTC."""
    return _parse_time(value)


def _parse_time(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise WindowAuditError("TIME_MISSING", "an ISO-8601 timestamp is required")
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise WindowAuditError("TIME_INVALID", f"{value!r} is not an ISO-8601 timestamp")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _observations(rows: List[Dict[str, Any]], content_id: str) -> List[Dict[str, Any]]:
    """Snapshot rows for one content id, chronological, with honest values."""
    observations: List[Dict[str, Any]] = []
    for row in rows:
        if str(row.get("content_id") or "").strip() != content_id:
            continue
        observed_at = _parse_time(row.get("observed_at"))
        impressions_raw = str(row.get("impressions") or "").strip()
        value: Optional[int] = None
        missing = True
        if impressions_raw:
            try:
                value = int(float(impressions_raw))
                missing = False
            except ValueError:
                missing = True
        observations.append({
            "observed_at": observed_at,
            "metric_source": str(row.get("metric_source") or "").strip(),
            "age_window": str(row.get("age_window") or "").strip(),
            "impressions": value,
            "impressions_missing": missing,
        })
    observations.sort(key=lambda item: item["observed_at"])
    return observations


def audit_content(content_id: str, published_at: Any,
                  snapshot_rows: List[Dict[str, Any]], *,
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """Audit one content id against every window. Never invents a value."""
    content_id = str(content_id or "").strip()
    if not content_id:
        raise WindowAuditError("CONTENT_ID_REQUIRED", "a window audit needs a content id")
    published = _parse_time(published_at)
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    observations = _observations(snapshot_rows, content_id)

    windows: Dict[str, Dict[str, Any]] = {}
    for name, hours in WINDOWS:
        due_at = published + timedelta(hours=hours)
        entry: Dict[str, Any] = {
            "due_at": due_at.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
                "+00:00", "Z"),
            "status": None,
            "observations": 0,
            "impressions": None,
            "impressions_missing": None,
            "observed_at": None,
            "metric_source": None,
        }
        # Snapshots are cumulative: the earliest observation at or after the
        # window close is the window's value. Later rows supersede it in the
        # weekly report; this audit only asks whether the window was covered.
        covering = [item for item in observations if item["observed_at"] >= due_at]
        if covering:
            first = covering[0]
            entry["status"] = OBSERVED
            entry["observations"] = len(observations)
            entry["impressions"] = first["impressions"]
            entry["impressions_missing"] = first["impressions_missing"]
            entry["observed_at"] = first["observed_at"].astimezone(timezone.utc).replace(
                microsecond=0).isoformat().replace("+00:00", "Z")
            entry["metric_source"] = first["metric_source"]
        elif moment >= due_at:
            entry["status"] = DUE_MISSING
        else:
            entry["status"] = NOT_DUE
        windows[name] = entry

    return {
        "content_id": content_id,
        "published_at": published.astimezone(timezone.utc).replace(
            microsecond=0).isoformat().replace("+00:00", "Z"),
        "audited_at": moment.astimezone(timezone.utc).replace(
            microsecond=0).isoformat().replace("+00:00", "Z"),
        "windows": windows,
        "total_observations": len(observations),
    }


def read_snapshots_csv(path: Path) -> List[Dict[str, Any]]:
    """Read the same ``metric_snapshots.csv`` the weekly report consumes."""
    path = Path(path)
    if not path.is_file():
        raise WindowAuditError("SNAPSHOTS_CSV_MISSING", path.as_posix())
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        absent = [field for field in SNAPSHOT_FIELDS if field not in fieldnames]
        if absent:
            raise WindowAuditError(
                "SNAPSHOTS_CSV_COLUMNS",
                f"{path.as_posix()} lacks columns: {', '.join(absent)}")
        rows = list(reader)
    return rows


def summarize(audits: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll content audits up into the counts a weekly review can act on."""
    counts = {name: {NOT_DUE: 0, DUE_MISSING: 0, OBSERVED: 0} for name, _ in WINDOWS}
    for audit in audits:
        for name, _ in WINDOWS:
            status = (audit.get("windows") or {}).get(name, {}).get("status")
            if status in counts[name]:
                counts[name][status] += 1
    return {
        "content_audited": len(audits),
        "windows": {name: counts[name] for name, _ in WINDOWS},
        "due_missing_total": sum(counts[name][DUE_MISSING] for name, _ in WINDOWS),
    }
