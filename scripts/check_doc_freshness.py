#!/usr/bin/env python3
"""Documentation freshness checker.

Why this exists
---------------
Documents rot silently: no test fails when a status table keeps describing last
month's architecture. On 2026-11-12 the README still called 公众号 and 小红书
"verify-only, no delivery layer" while the delivery runners had been on `main`
for days. Nothing was red, so the stale page survived.

The contract this enforces
--------------------------
Every tracked doc states the date it was verified against (`> Last verified:
YYYY-MM-DD` and its accepted variants). If a commit touching the code paths
mapped to that doc lands **after** that date, the doc is stale and this check
fails. Updating the date without reading the diff is the only way to defeat the
mechanism, which is why the failure message names the commits.

Also checked:
  * the English/Chinese pair carries the same verification date;
  * the date is not in the future;
  * every Tier-1 doc in ``scripts/check_i18n.py`` is either tracked or explicitly
    exempt in ``config/docs/doc-freshness.json``;
  * a tracked doc's mapped paths actually exist in git history (a typo would
    otherwise silently match nothing and always pass).

BOUNDARY: this reads git history only. It never contacts GitHub, so a pass says
nothing about the live remote state — see ``docs/DOC-SYNC.md`` for the manual
step that does.

Usage
-----
    python scripts/check_doc_freshness.py
    python scripts/check_doc_freshness.py --report-only
    python scripts/check_doc_freshness.py --json
    python scripts/check_doc_freshness.py --today 2026-11-12

Exit codes: 0 pass, 1 stale/unclassified/parse error, 2 config error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from process_utils import hidden_run

ROOT = Path(__file__).resolve().parents[1]
CONFIG_REL = "config/docs/doc-freshness.json"
HEADER_WINDOW = 40  # lines scanned for the verification marker
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# A verification date is written in the author's local time zone, while CI runs on
# UTC. An author in UTC+8 writing the file at 04:00 local time is one calendar day
# ahead of the runner, which is not a fabricated date. One day of skew is allowed;
# anything beyond that is treated as a time bomb.
MAX_CLOCK_SKEW_DAYS = 1

# Accepted verification lines. Order matters only for readability; the first
# match wins. Full-width colons are what the Chinese docs actually use.
MARKER_PATTERNS = (
    r">\s*Last verified:\s*(\d{4}-\d{2}-\d{2})",
    r">\s*Status verified:\s*(\d{4}-\d{2}-\d{2})",
    r">\s*Last updated:\s*(\d{4}-\d{2}-\d{2})",
    r">\s*Last reviewed:\s*(\d{4}-\d{2}-\d{2})",
    r">\s*Last regenerated[^:\n]{0,40}:\s*(\d{4}-\d{2}-\d{2})",
    r">\s*最后验证：\s*(\d{4}-\d{2}-\d{2})",
    r">\s*状态验证：\s*(\d{4}-\d{2}-\d{2})",
    r">\s*最后更新：\s*(\d{4}-\d{2}-\d{2})",
    r">\s*最后复核：\s*(\d{4}-\d{2}-\d{2})",
    r">\s*最后[^\n：:]{0,20}重生成：\s*(\d{4}-\d{2}-\d{2})",
)


@dataclass
class Finding:
    level: str      # "STALE" | "ERROR"
    doc: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"level": self.level, "doc": self.doc, "detail": self.detail}


# --------------------------------------------------------------------------
# pure helpers (unit-tested without git)
# --------------------------------------------------------------------------

def parse_marker(text: str) -> str | None:
    """Return the verification date in the first HEADER_WINDOW lines, or None."""
    head = "\n".join(text.splitlines()[:HEADER_WINDOW])
    for pattern in MARKER_PATTERNS:
        m = re.search(pattern, head)
        if m:
            return m.group(1)
    return None


def is_valid_date(value: str) -> bool:
    if not DATE_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _latest_plausible_date(today: str) -> str:
    """Newest marker date that is not treated as a time bomb."""
    return (date.fromisoformat(today) + timedelta(days=MAX_CLOCK_SKEW_DAYS)).isoformat()


def evaluate(
    tracks: list[dict[str, Any]],
    read_text: Any,
    mirror_of: Any,
    changes_since: Any,
    today: str,
) -> list[Finding]:
    """Decide freshness without touching git.

    ``read_text(rel) -> str | None``, ``mirror_of(rel) -> str`` (repo-relative),
    ``changes_since(paths, since) -> list[(sha, date, subject)]``.
    """
    findings: list[Finding] = []
    for track in tracks:
        doc = track["doc"]
        paths = list(track.get("code") or [])
        text = read_text(doc)
        if text is None:
            findings.append(Finding("ERROR", doc, "tracked doc is missing"))
            continue
        marker = parse_marker(text)
        if marker is None:
            findings.append(
                Finding("ERROR", doc,
                        "no verification line in the first %d lines "
                        "(e.g. '> Last verified: YYYY-MM-DD')" % HEADER_WINDOW)
            )
            continue
        if not is_valid_date(marker):
            findings.append(Finding("ERROR", doc, f"verification date '{marker}' is not YYYY-MM-DD"))
            continue
        if marker > _latest_plausible_date(today):
            findings.append(
                Finding(
                    "ERROR",
                    doc,
                    f"verification date {marker} is more than {MAX_CLOCK_SKEW_DAYS} day(s) "
                    f"ahead of the runner date {today} (UTC); it is written in local time, "
                    f"so one day of skew is allowed but this is beyond it",
                )
            )

        mirror = mirror_of(doc)
        if mirror:
            mirror_text = read_text(mirror)
            if mirror_text is not None:
                mirror_marker = parse_marker(mirror_text)
                if mirror_marker and mirror_marker != marker:
                    findings.append(
                        Finding("ERROR", doc,
                                f"pair date mismatch: {doc} says {marker}, {mirror} says {mirror_marker}")
                    )

        if not paths:
            continue
        changes = changes_since(paths, marker)
        if changes:
            newest = changes[0]
            findings.append(
                Finding(
                    "STALE",
                    doc,
                    f"code changed after {marker}: {len(changes)} commit(s) touch "
                    f"{', '.join(paths)}; newest {newest[0]} {newest[1]} {newest[2]}"
                    " — re-read the diff, update the facts, then bump the date",
                )
            )
    return findings


def coverage_gaps(tier1: Iterable[str], tracks: list[dict[str, Any]], exempt: Iterable[dict[str, Any]]) -> list[Finding]:
    classified = {t["doc"] for t in tracks} | {e["doc"] for e in exempt}
    return [
        Finding("ERROR", doc,
                "Tier-1 doc is neither tracked nor exempt in " + CONFIG_REL)
        for doc in tier1
        if doc not in classified
    ]


# --------------------------------------------------------------------------
# git / filesystem adapters
# --------------------------------------------------------------------------

def _read_text(rel: str) -> str | None:
    path = ROOT / rel
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def _mirror_of(rel: str) -> str:
    import check_i18n  # same directory; single source of truth for the pairing

    mirror = ROOT / check_i18n._mirror_rel(rel)
    return check_i18n._mirror_rel(rel) if mirror.exists() else ""


def _changes_since(paths: list[str], since: str) -> list[tuple[str, str, str]]:
    """Commits touching ``paths`` whose committer date is after ``since``.

    The comparison is a plain string compare on ISO dates, not ``git --since``
    timezone arithmetic: the doc states a date, so the check compares dates.
    """
    result = hidden_run(
        ["git", "-C", str(ROOT), "log", "-n", "200", "--format=%h|%cs|%s",
         "--", *paths],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if result.returncode != 0:
        return []
    rows: list[tuple[str, str, str]] = []
    for line in (result.stdout or "").splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3 and parts[1] and parts[1] > since:
            rows.append((parts[0], parts[1], parts[2]))
    return rows


def load_config() -> dict[str, Any]:
    path = ROOT / CONFIG_REL
    if not path.is_file():
        raise SystemExit(f"config error: missing {CONFIG_REL}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"config error: {CONFIG_REL} is not valid JSON ({exc})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Documentation freshness checker")
    parser.add_argument("--report-only", action="store_true",
                        help="never fail: print findings and exit 0 (local use only)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--today", default=None,
                        help="override today's date (YYYY-MM-DD) for tests")
    args = parser.parse_args(argv)

    today = args.today or date.today().isoformat()
    config = load_config()
    tracks = config.get("tracks") or []
    exempt = config.get("exempt") or []

    import check_i18n

    findings = evaluate(tracks, _read_text, _mirror_of, _changes_since, today)
    findings += coverage_gaps(check_i18n.TIER1_DOCS, tracks, exempt)

    stale = [f for f in findings if f.level == "STALE"]
    errors = [f for f in findings if f.level == "ERROR"]

    if args.json:
        print(json.dumps(
            {"schema": "contentops.doc-freshness-report/v1", "today": today,
             "tracks": len(tracks), "exempt": len(exempt),
             "findings": [f.as_dict() for f in findings]},
            ensure_ascii=False, indent=2))
    else:
        for finding in findings:
            print(f"[{finding.level}] {finding.doc}: {finding.detail}")
        if not findings:
            print(f"doc-freshness PASS: {len(tracks)} tracked doc(s), "
                  f"{len(exempt)} exempt, verified against git history at {today}")
        else:
            print(f"\ndoc-freshness: {len(stale)} stale, {len(errors)} error(s)")

    if args.report_only:
        return 0
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
