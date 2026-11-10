#!/usr/bin/env python3
"""Reconcile Strategy's platform claims with ContentOps' runtime facts.

Why this exists
---------------
Strategy's operating matrix may say a platform is ``Active`` while this
repository's registry still has it at ``PLANNED``. Neither side is lying:
``Active`` is a strategic commitment, ``PLANNED`` is a claim about code and
evidence on this branch. The failure mode is not disagreement — it is
*unstated* disagreement, where someone reads the strategy deck and assumes the
executor exists, or reads the registry and forgets the strategy moved on.

This command makes the gap explicit and boring. It compares three things:

1. the mirror in ``config/registry/strategy_platform_status.json`` against the
   Strategy matrix actually on disk (``--strategy-root``), so a Strategy-side
   edit cannot drift past this repository unnoticed;
2. Strategy's status against the runtime ``status`` in
   ``config/registry/platforms.json`` — reported, never resolved: the runtime
   is not wrong for lagging, and Strategy is not wrong for being ahead;
3. mirror coverage: every ``strategy_platform`` named in the runtime registry
   must have a mirror entry, or the mirror is incomplete and ``--strict``
   fails.

It reads two files and prints a report. It edits nothing, in either
repository, ever.

Usage
-----
    python scripts/check_platform_status_sync.py --strategy-root ../X-SuperPlay-Strategy
    python scripts/check_platform_status_sync.py --strategy-root ... --strict --json

Exit codes: 0 consistent (or gaps reported without --strict), 1 ``--strict``
and the mirror disagrees with Strategy or is incomplete, 2 misuse/unreadable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

MATRIX_RELATIVE = Path("03-Execution") / "Platform-Operating-Matrix.md"
MIRROR_RELATIVE = Path("config") / "registry" / "strategy_platform_status.json"
REGISTRY_RELATIVE = Path("config") / "registry" / "platforms.json"

#: Strategy's lifecycle vocabulary for the operating matrix.
STRATEGY_STATUSES = ("Active", "Derived", "Experiment", "Infrastructure")

#: Chinese platform label in the Strategy matrix → strategy_platform id as the
#: runtime registry spells it. A matrix row for a platform missing here fails
#: loudly: silent extra platforms are how coverage rot starts.
MATRIX_LABELS: Dict[str, str] = {
    "抖音": "douyin",
    "小红书": "xiaohongshu",
    "B站": "bilibili",
    "视频号": "shipinhao",
    "公众号": "gzh",
    "知乎": "zhihu",
    "CSDN": "csdn",
    "YouTube": "youtube",
    "X": "x",
    "GitHub": "github",
}

#: The runtime registry names some ``strategy_platform`` values after the
#: platform's product rather than Strategy's matrix label. The alias is the
#: reconciliation, stated once: an unmapped runtime name still fails coverage,
#: it never silently matches.
RUNTIME_ALIASES: Dict[str, str] = {
    "wechat_channels": "shipinhao",
    "wechat_official_account": "gzh",
}


class SyncError(Exception):
    """A refusal with a code. Callers branch on the code, not the prose."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def parse_matrix(text: str) -> Dict[str, str]:
    """Extract {strategy_platform: status} from the matrix's main table.

    The main table is the one whose rows carry a known lifecycle status in the
    status column. Anything else in the document is ignored on purpose.
    """
    statuses: Dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        label, status = cells[0], cells[5]
        if status not in STRATEGY_STATUSES:
            continue
        platform = MATRIX_LABELS.get(label)
        if platform is None:
            raise SyncError(
                "MATRIX_UNKNOWN_PLATFORM",
                f"matrix row {label!r} has no mapping in MATRIX_LABELS; extend the table")
        if platform in statuses and statuses[platform] != status:
            raise SyncError(
                "MATRIX_CONFLICTING_ROWS",
                f"{platform!r} appears twice with {statuses[platform]!r} and {status!r}")
        statuses[platform] = status
    if not statuses:
        raise SyncError("MATRIX_NO_ROWS", "no platform rows recognised in the matrix")
    return statuses


def load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise SyncError("FILE_MISSING", path.as_posix())
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SyncError("FILE_MALFORMED", f"{path.as_posix()}: {exc}")


def reconcile(strategy_root: Optional[Path], repo_root: Path) -> Dict[str, Any]:
    mirror_doc = load_json(repo_root / MIRROR_RELATIVE)
    mirror = {str(key): str(value.get("strategy_status") or "")
              for key, value in (mirror_doc.get("statuses") or {}).items()}

    matrix: Dict[str, str] = {}
    matrix_path: Optional[Path] = None
    if strategy_root is not None:
        matrix_path = Path(strategy_root) / MATRIX_RELATIVE
        if not matrix_path.is_file():
            raise SyncError("STRATEGY_MATRIX_MISSING", matrix_path.as_posix())
        matrix = parse_matrix(matrix_path.read_text(encoding="utf-8"))

    registry_doc = load_json(repo_root / REGISTRY_RELATIVE)
    runtime: Dict[str, str] = {}
    for entry in registry_doc.get("platforms") or []:
        name = str(entry.get("strategy_platform") or "")
        if not name:
            continue
        runtime[RUNTIME_ALIASES.get(name, name)] = str(entry.get("status") or "")

    mirror_drift = []
    if matrix_path is not None:
        for platform in sorted(set(mirror) | set(matrix)):
            mine, theirs = mirror.get(platform), matrix.get(platform)
            if mine != theirs:
                mirror_drift.append({
                    "platform": platform,
                    "mirror": mine,
                    "strategy": theirs,
                })

    coverage_gaps = sorted(set(runtime) - set(mirror) - {""})

    strategy_vs_runtime = []
    for platform in sorted(set(mirror) & set(runtime)):
        strategy_status, runtime_status = mirror[platform], runtime[platform]
        if strategy_status == "Active" and runtime_status != "PRODUCTION_ACCEPTED":
            strategy_vs_runtime.append({
                "platform": platform,
                "strategy_status": strategy_status,
                "runtime_status": runtime_status,
                "reading": "strategy commitment; runtime not accepted for production",
            })

    return {
        "schema": "contentops.platform-status-sync/v1",
        "strategy_matrix": str(matrix_path) if matrix_path else None,
        "mirror_matches_strategy": matrix_path is None or not mirror_drift,
        "mirror_drift": mirror_drift,
        "mirror_coverage_gaps": coverage_gaps,
        "strategy_vs_runtime": strategy_vs_runtime,
        "runtime_status_counts": {
            status: sum(1 for value in runtime.values() if value == status)
            for status in sorted(set(runtime.values()))
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Report the gap between Strategy platform claims and ContentOps facts.")
    parser.add_argument("--strategy-root",
                        help="checkout of X-SuperPlay-Strategy (enables mirror drift check)")
    parser.add_argument("--repo-root", default=str(ROOT),
                        help="ContentOps checkout to audit (default: this repository)")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 on mirror drift or mirror coverage gaps")
    parser.add_argument("--json", action="store_true", help="full JSON report")
    args = parser.parse_args(argv)

    try:
        report = reconcile(args.strategy_root, Path(args.repo_root).resolve())
    except SyncError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"mirror matches Strategy: {report['mirror_matches_strategy']}")
        if report["mirror_drift"]:
            for row in report["mirror_drift"]:
                print(f"  DRIFT {row['platform']}: mirror={row['mirror']} "
                      f"strategy={row['strategy']}")
        if report["mirror_coverage_gaps"]:
            print(f"  mirror missing entries for: "
                  f"{', '.join(report['mirror_coverage_gaps'])}")
        print("strategy commitment vs runtime capability (report only, never resolved):")
        if report["strategy_vs_runtime"]:
            for row in report["strategy_vs_runtime"]:
                print(f"  {row['platform']}: strategy={row['strategy_status']} "
                      f"runtime={row['runtime_status']}")
        else:
            print("  (no Active-strategy platforms lagging in runtime)")
        print(json.dumps(report["runtime_status_counts"], ensure_ascii=False))

    if args.strict and (report["mirror_drift"] or report["mirror_coverage_gaps"]):
        print("STRICT: mirror is stale or incomplete — re-read the Strategy matrix "
              "and update strategy_platform_status.json from a verified read",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
