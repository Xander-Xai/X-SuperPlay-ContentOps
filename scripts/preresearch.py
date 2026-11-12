#!/usr/bin/env python3
"""CLI for the mandatory pre-copy research gate.

    python scripts/preresearch.py init    --project projects/my-video
    python scripts/preresearch.py intent  --project projects/my-video
    python scripts/preresearch.py check   --project projects/my-video
    python scripts/preresearch.py approve --project projects/my-video \
        --reviewer "Your Name" --opinion "Read the diff and the sources" --confirm

``init`` scaffolds the four written artifacts; it never overwrites existing
files. ``intent`` copies the router's ``ContentIntent`` out of
``00_brief/brief.json`` and is the only supported way to produce the fifth:
the gate consumes the router's intent, it never invents a topic.
A scaffold alone cannot pass: the evidence list starts empty and the reading
notes carry TODO markers. The operator fills them, runs ``check``, then signs
with ``approve``. There is no force switch and no automatic approval.

Exit codes: 0 ok, 2 usage, 4 blocked by the gate, 1 unexpected.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.workflow import preresearch  # noqa: E402

BLOCKED_EXIT = 4

TEMPLATES: Dict[str, str] = {
    "project-reading.md": """# 项目通读记录

> 本文件回答：为了写这期文案，我实际读了本仓库的哪些东西，得到哪些可核查事实。
> 必须在写 `script/master.md` / `02_draft/draft.md` 之前完成并经具名批准。

## 读过的文件

- `docs/RUNBOOK.md` — TODO：记下与本次制作直接相关的真实命令
- `docs/CONTENT-LIFECYCLE-STAGES.md` — TODO：记下双线契约与当前阶段状态
- `scripts/make_content.py` — TODO：记下门禁与产物命名
- TODO：再补充仓库内路径，注明行号

## 得到的事实（逐条带路径与行号）

- TODO：只写能在文件里逐字核对的事实，不凭印象

## 与本期主题的关系

- TODO：说明这次内容要讲什么、不讲什么
""",
    "outline.md": """# 本期内容大纲

> 先出大纲 / 手册，再写文案。此文件是「制作文案前」环节的交付物之一。

## 主题与受众

- TODO：一句话主题 + 面向谁

## 视频线 VIDEO

- TODO：分镜与旁白要点，每条事实后挂来源编号

## 图文线 GRAPHIC_TEXT

- TODO：文章结构与配图清单

## 证据映射

- TODO：claim_id → 落盘的源文档路径

## 不做的事

- TODO：明确本次不渲染、不发布、不付费等边界
""",
    "evidence-list.json": """{
  "schema": "contentops.precopy-research-evidence/v1",
  "note": "每条必须是可打开核实的真实来源；占位不算证据。至少 3 条，且至少一条 kind 为 primary 或 official。",
  "items": []
}
""",
    "boundary.md": """# 边界声明

> 本环节只做研究、核实与大纲，不写最终文案、不渲染、不发布、不联网付费。

- 资料核实不等于产线实跑；本阶段不产出 MP4，不生成平台草稿。
- `production_ready: false`
- `publish_authorized: false`
- 任何「已验证」只指资料与代码核对，不指渲染或发布结果。
- AI 生成的图 / 视频只能作视觉辅助，不承担事实举证。
- 具名批准后若改动任何一份研究产物，批准立即失效（STALE），须重新 check 并 approve。
""",
}


def _project(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def _emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_init(args) -> int:
    project = _project(args.project)
    if not project.is_dir():
        _emit({"state": "BLOCKED", "code": "PROJECT_MISSING", "path": str(project)})
        return BLOCKED_EXIT
    target = project / preresearch.RESEARCH_DIR
    target.mkdir(parents=True, exist_ok=True)
    created, skipped = [], []
    for name, body in TEMPLATES.items():
        path = target / name
        if path.is_file():
            skipped.append(path.relative_to(project).as_posix())
            continue
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
        created.append(path.relative_to(project).as_posix())
    _emit({"state": "SCAFFOLDED", "project": project.name,
           "created": created, "skipped": skipped,
           "next": ("run `preresearch.py intent` to bind the router's intent, "
                    "fill the four written artifacts, then check, then approve"),
           "production_ready": False, "publish_authorized": False})
    return 0


def cmd_intent(args) -> int:
    project = _project(args.project)
    if not project.is_dir():
        _emit({"state": "BLOCKED", "code": "PROJECT_MISSING", "path": str(project)})
        return BLOCKED_EXIT
    try:
        payload = preresearch.bind_intent(project)
    except preresearch.PreresearchError as exc:
        _emit({"state": "BLOCKED", "code": exc.code, "detail": exc.detail,
               "production_ready": False})
        return BLOCKED_EXIT
    _emit(payload)
    return 0


def cmd_check(args) -> int:
    report = preresearch.check(_project(args.project))
    _emit(report)
    return 0 if report["ok"] else BLOCKED_EXIT


def cmd_approve(args) -> int:
    if not args.confirm:
        _emit({"state": "BLOCKED", "code": "CONFIRMATION_REQUIRED",
               "detail": "pass --confirm to record a human decision"})
        return 2
    if not args.reviewer or not args.reviewer.strip():
        _emit({"state": "BLOCKED", "code": "REVIEWER_REQUIRED"})
        return 2
    if not args.opinion or not args.opinion.strip():
        _emit({"state": "BLOCKED", "code": "OPINION_REQUIRED"})
        return 2
    project = _project(args.project)
    try:
        record = preresearch.approve(project, reviewer=args.reviewer, opinion=args.opinion)
    except preresearch.PreresearchError as exc:
        _emit({"state": "BLOCKED", "code": exc.code, "detail": exc.detail,
               "check": exc.report, "production_ready": False})
        return BLOCKED_EXIT
    _emit({"state": "PRECOPY_RESEARCH_APPROVED", "project": project.name,
           "receipt": preresearch.RECEIPT.as_posix(), "record": record})
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--project", required=True)
        p.add_argument("--json", action="store_true", help="reserved for JSON output")

    init = sub.add_parser("init", help="scaffold the four written artifacts")
    common(init)

    intent = sub.add_parser("intent", help="copy the router's intent into the package")
    common(intent)

    for name, help_text in (("check", "report gate state"), ("status", "report gate state")):
        p = sub.add_parser(name, help=help_text)
        common(p)

    approve = sub.add_parser("approve", help="sign the research phase")
    common(approve)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--opinion", required=True)
    approve.add_argument("--confirm", action="store_true")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return cmd_init(args)
        if args.command == "intent":
            return cmd_intent(args)
        if args.command in ("check", "status"):
            return cmd_check(args)
        if args.command == "approve":
            return cmd_approve(args)
    except (OSError, ValueError) as exc:
        _emit({"state": "BLOCKED", "code": "PROJECT_ERROR", "detail": str(exc)})
        return BLOCKED_EXIT
    return 2


if __name__ == "__main__":
    sys.exit(main())
