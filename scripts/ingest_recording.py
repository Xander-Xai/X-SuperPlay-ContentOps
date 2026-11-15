#!/usr/bin/env python3
"""Admit one hand-made screen recording into a project as evidence material.

Exit codes: 0 accepted, 1 refused/blocked, 2 usage error. The verdict, its reason code and
the receipt path are always printed, because a refusal that says nothing is not auditable.

Examples
--------
    python scripts/ingest_recording.py --project projects/my-video \\
        --file D:/captures/terminal.mp4 --claim C07 --crop 0,120,1080,1200 \\
        --source-ref repo://src/contentops/media

    python scripts/ingest_recording.py --project projects/my-video \\
        --file D:/captures/arch.mp4 --claim C03
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

from contentops.media.recording_intake import (  # noqa: E402
    ACCEPTED,
    RECEIPT,
    RecordingIntakeError,
    RecordingRequest,
    intake,
)


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _crop(text: str) -> dict:
    parts = [part.strip() for part in text.replace(" ", ",").split(",") if part.strip()]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--crop 需要 4 个整数：x,y,width,height")
    try:
        x, y, width, height = (int(part) for part in parts)
    except ValueError:
        raise argparse.ArgumentTypeError("--crop 的四个值都必须是整数") from None
    return {"x": x, "y": y, "width": width, "height": height}


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        description="Admit a manual screen recording as evidence material, per account policy.")
    parser.add_argument("--project", required=True, help="项目目录")
    parser.add_argument("--file", required=True, help="录屏文件（项目外亦可，会被复制进项目）")
    parser.add_argument("--claim", action="append", default=[],
                        help="绑定的 claim_id，可重复")
    parser.add_argument("--crop", type=_crop, default=None,
                        help="裁切矩形 x,y,width,height（ALLOWED_CROPPED 账号必填）")
    parser.add_argument("--in-ms", type=int, default=None, help="可用区间起点（毫秒）")
    parser.add_argument("--out-ms", type=int, default=None, help="可用区间终点（毫秒）")
    parser.add_argument("--source-ref", default="", help="这段画面展示的来源（URL 或 repo:// 路径）")
    parser.add_argument("--notes", default="", help="人工备注，写进回执与素材行")
    parser.add_argument("--dry-run", action="store_true",
                        help="只判定不落盘（不复制文件、不写素材清单，仍写回执）")
    args = parser.parse_args(argv)

    project = Path(args.project).expanduser()
    if not project.is_dir():
        print(f"项目目录不存在：{project}", file=sys.stderr)
        return 2

    request = RecordingRequest(path=Path(args.file), claim_ids=args.claim,
                               crop=args.crop, source_ref=args.source_ref,
                               in_ms=args.in_ms, out_ms=args.out_ms, notes=args.notes)
    try:
        payload = intake(project, request, repo_root=ROOT,
                         apply=not args.dry_run, write=True)
    except RecordingIntakeError as exc:
        print(f"请求无效：{exc}", file=sys.stderr)
        return 2

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nverdict: {payload['verdict']} ({payload['reason_code']})", file=sys.stderr)
    if not args.dry_run:
        print(f"receipt: {(project / RECEIPT).as_posix()}", file=sys.stderr)
    return 0 if payload["verdict"] == ACCEPTED else 1


if __name__ == "__main__":
    raise SystemExit(main())
