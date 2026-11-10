#!/usr/bin/env python3
"""Fetch Bilibili public video metrics into a project receipt.

This is the transport for the ``api_public`` channel this repository declares
for bilibili. It wraps ``Nemo2011/bilibili-api`` (MIT) across a process
boundary: the library is imported lazily, only when ``--execute`` is passed,
and only the *public* video info is read — no login, no creator centre, no
scraping.

    plan      DNA gate + BV resolution + endpoint listing. Offline.
    fetch     resolve BV -> read the public counters -> write the receipt.
              Requires --execute.

What this script will not do
----------------------------
* It will not fetch for an account whose DNA does not list bilibili. One
  account's numbers must never be attributed to another.
* It will not invent a BV. No layer carries one -> blocked, not guessed.
* It will not pretend a network error is an empty metric. A failed fetch
  writes no metrics receipt; the failure goes to stderr with the real code.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.accounts import load_account  # noqa: E402
from contentops.platforms import bilibili_metrics as bm  # noqa: E402


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _load_project(project_dir: Path) -> Dict[str, Any]:
    """Read project.yaml for the BV chain. A missing file is fine: CLI and DNA
    remain sources; a missing file simply is not one."""
    path = project_dir / "project.yaml"
    if not path.is_file():
        return {}
    try:
        import yaml  # PyYAML, already a CI requirement
    except ImportError as exc:  # pragma: no cover - CI installs PyYAML
        raise SystemExit(f"BLOCKED: PyYAML is required to read {path}: {exc}") from None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _receipt_path(project_dir: Path, out: Path | None) -> Path:
    if out is not None:
        return Path(out)
    return project_dir / "receipts" / "metrics-bilibili.json"


def _resolve(args: argparse.Namespace) -> tuple:
    dna_path = Path(args.account)
    if not dna_path.is_file():
        raise SystemExit(f"BLOCKED: account DNA not found {dna_path}")
    dna = load_account(dna_path)
    allowed, allow_reason = bm.dna_allows(dna)
    blockers: list = []
    if not allowed:
        blockers.append(
            f"bilibili metrics refused for {dna.get('slug', dna_path.name)}: {allow_reason}"
        )

    project_dir = Path(args.project) if args.project else None
    project_cfg: Dict[str, Any] = {}
    if project_dir is not None:
        project_cfg = _load_project(project_dir)
    bvid, source, reason, bvid_blockers = bm.resolve_bvid(args.bvid, project_cfg, dna)
    blockers.extend(bvid_blockers)
    return dna, project_dir, bvid, source, reason, blockers


def cmd_plan(args: argparse.Namespace) -> int:
    dna, project_dir, bvid, source, reason, blockers = _resolve(args)
    payload = {
        "state": "PLAN",
        "schema": bm.RECEIPT_SCHEMA,
        "account_slug": dna.get("slug", ""),
        "dna_gate": "PASS",
        "bvid": bvid or None,
        "bvid_source": source,
        "bvid_reason": reason,
        "mode": bm.MODE_TRANSPORT_SMOKE if source == "cli" else bm.MODE_ACCOUNT_DELIVERY,
        "endpoints": {"video_info": "GET bilibili public video info (via bilibili-api, no login)"},
        "receipt_target": str(_receipt_path(project_dir, args.out)) if project_dir or args.out else None,
        "execute_required": True,
    }
    if blockers:
        payload["state"] = "BLOCKED"
        payload["blockers"] = blockers
    _emit(payload)
    return 4 if blockers else 0


def cmd_fetch(args: argparse.Namespace) -> int:
    if not args.execute:
        raise SystemExit("BLOCKED: fetch touches the network; pass --execute")
    dna, project_dir, bvid, source, reason, blockers = _resolve(args)
    if blockers:
        _emit({"state": "BLOCKED", "blockers": blockers})
        return 4
    if project_dir is None and args.out is None:
        raise SystemExit("BLOCKED: --project or --out is required so the receipt lands somewhere real")

    try:
        from bilibili_api import video  # lazy: only under --execute
    except ImportError as exc:
        raise SystemExit(
            "BLOCKED: bilibili-api-python is not installed. "
            f"pip install bilibili-api-python  ({exc})"
        ) from None

    try:
        info = asyncio.run(video.Video(bvid=bvid).get_info())
    except Exception as exc:  # noqa: BLE001 - a real network/API failure is reported as such
        print(f"FETCH_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 6

    stat = info.get("stat") if isinstance(info, dict) else None
    if not isinstance(stat, dict):
        print("FETCH_FAILED: response has no stat object; refusing to invent counters", file=sys.stderr)
        return 6
    metrics, problems = bm.shape_video_stats(stat)
    receipt = bm.build_receipt(
        account_slug=dna.get("slug", ""),
        bvid=bvid,
        bvid_source=source,
        metrics=metrics,
        fetched_at=_stamp(),
        title=str(info.get("title") or ""),
        problems=problems or None,
    )
    target = _receipt_path(project_dir, args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit({"state": "FETCHED", "receipt": str(target), "mode": receipt["mode"], "metrics": metrics})
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("plan", "fetch"))
    parser.add_argument("--account", required=True, help="account DNA JSON path")
    parser.add_argument("--project", default=None, help="project directory (reads project.yaml, writes receipts/)")
    parser.add_argument("--bvid", default=None, help="explicit BV; makes the receipt a TRANSPORT_SMOKE")
    parser.add_argument("--out", default=None, help="receipt path override")
    parser.add_argument("--execute", action="store_true", help="allow the real network call")
    args = parser.parse_args(argv)
    _configure_stdio()
    return cmd_plan(args) if args.command == "plan" else cmd_fetch(args)


if __name__ == "__main__":
    raise SystemExit(main())
