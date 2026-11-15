#!/usr/bin/env python3
"""Write the per-platform adaptation plan for one project.

One row per platform the account declares: the shape it needs, whether the master cut
satisfies it or a second render is required, and which recording policy governs the
account. The plan is written to ``receipts/platform-adaptation.json``.

Exit codes: 0 planned, 1 blocked, 2 usage error.

Examples
--------
    python scripts/platform_adapt.py plan --project projects/my-video
    python scripts/platform_adapt.py plan --project projects/my-video --platform bilibili
    python scripts/platform_adapt.py plan --project projects/my-video --json --no-write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from contentops.platforms.adaptation import (  # noqa: E402
    PLANNED,
    RECEIPT,
    AdaptationError,
    plan,
    write_receipt,
)


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _print_table(payload: dict) -> None:
    account = payload.get("account") or {}
    master = payload.get("master_canvas") or {}
    shape = f"{master.get('width')}×{master.get('height')}" if master else "未声明"
    print(f"account  {account.get('slug')}  ({account.get('kind') or '?'})")
    print(f"master   {shape}")
    recording = payload.get("recording") or {}
    print(f"录屏策略 {recording.get('manual_recording')}  {recording.get('note')}")
    print("")
    header = f"{'平台':<18}{'状态':<14}{'画幅':<10}{'时长上限':<10}{'需变体':<8}备注"
    print(header)
    print("-" * len(header))
    for row in payload.get("platforms") or []:
        limits = row.get("limits") or {}
        canvas = row.get("canvas") or {}
        aspect = limits.get("aspect_required") or (
            f"{canvas.get('width')}×{canvas.get('height')}" if canvas else "-")
        duration = limits.get("max_duration_s")
        print(f"{row['platform_id']:<18}{row.get('role_status') or '-':<14}{aspect:<10}"
              f"{(str(duration) + 's') if duration else '-':<10}"
              f"{'是' if row.get('requires_variant') else '否':<8}"
              f"{row.get('variant_reason') or ''}")


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan_cmd = sub.add_parser("plan", help="build and write the adaptation plan")
    plan_cmd.add_argument("--project", required=True, help="项目目录")
    plan_cmd.add_argument("--platform", action="append", default=[],
                          help="只看这些平台（可重复）；缺省为账号声明的全部平台")
    plan_cmd.add_argument("--json", action="store_true", help="输出完整计划 JSON")
    plan_cmd.add_argument("--no-write", action="store_true", help="只计算，不写回执")
    args = parser.parse_args(argv)

    project = Path(args.project).expanduser()
    if not project.is_dir():
        print(f"项目目录不存在：{project}", file=sys.stderr)
        return 2
    try:
        payload = plan(project, repo_root=ROOT, platforms=args.platform or None)
    except AdaptationError as exc:
        print(f"请求无效：{exc}", file=sys.stderr)
        return 2

    if not args.no_write:
        write_receipt(project, payload)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_table(payload)
        print("")
        print(f"status: {payload['status']} ({payload['reason_code']})")
        if not args.no_write:
            print(f"receipt: {(project / RECEIPT).as_posix()}")
    return 0 if payload["status"] == PLANNED else 1


if __name__ == "__main__":
    raise SystemExit(main())
