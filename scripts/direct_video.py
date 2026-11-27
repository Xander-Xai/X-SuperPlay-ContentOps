#!/usr/bin/env python3
"""Director-grade multi-role video planner & Huashu film compiler CLI (T08).

Usage:
    python scripts/direct_video.py compile --spec director-spec.json --out-dir motion/film
    python scripts/direct_video.py demo --account x-superplay-future-intelligence --aspect 9:16 --out-dir .verify-tmp/fi-9x16
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

from contentops.media.video_director import DirectorError, build_director_plan, compile_huashu_film  # noqa: E402


def _demo_scenes(account: str) -> tuple[str, List[Dict[str, Any]]]:
    """Verified-source Easel v0.2.1/v0.3.0 scenes tailored to FI vs 1024 DNA."""
    if account == "x-superplay-1024":
        return (
            "Easel 实测：CLI 能跑通，但 Web 工作台 6 项没过",
            [
                {
                    "scene_id": "s01",
                    "role": "hook_conflict",
                    "duration_s": 3.5,
                    "kicker": "X超玩·1024 · 实测结论前置",
                    "headline": "doctor 绿了 12 项，但真跑起来有 7 项红灯",
                    "subtext": "我们把 Easel 锁在 v0.2.1，逐文件核对 982 个哈希，直接看实拍结果。",
                    "image_path": "projects/easel-review/sources/screenshots/10-easel-doctor.png",
                    "focus_box": [6, 52, 88, 22],
                    "source_label": "REAL SCREENSHOT · 10-easel-doctor.png",
                },
                {
                    "scene_id": "s02",
                    "role": "real_evidence",
                    "duration_s": 4.0,
                    "kicker": "MEASURED PROOF · 端口错配实拍",
                    "headline": "ping 第 1 步红、第 2 步绿：端口 18789 vs 37289",
                    "subtext": "上游 healthz 探测写死 18789，而 easel profile 网关实际跑在 37289。",
                    "image_path": "projects/easel-review/sources/screenshots/11-easel-ping.png",
                    "focus_box": [2, 37, 96, 17],
                    "source_label": "REAL CAPTURE · easel ping 实测输出",
                },
                {
                    "scene_id": "s03",
                    "role": "failure_boundary",
                    "duration_s": 4.0,
                    "kicker": "COST & LIMITS · 真实失败清单",
                    "headline": "Web 路径 6 项未过，不适合零配置新手",
                    "metrics": [
                        {"label": "核心依赖 OK", "value": "12", "note": "Python / Node / FFmpeg / Playwright", "tone": "success"},
                        {"label": "实测 FAIL", "value": "7", "note": "6 项 Web + 1 项 healthz", "tone": "problem"},
                        {"label": "内置 Skills", "value": "114", "note": "创作层占 52 个（实数）"},
                    ],
                    "dot_matrix": {"label": "DOCTOR 19 项实测分布（红=7失败 / 绿=12通过）", "total": 19, "active": 7},
                    "subtext": "缺 fastapi / uvicorn / 前端构建 / .env Key，Web 工作台当前未验证。",
                    "source_label": "MEASURED RECEIPT · Easel v0.2.1 doctor",
                },
                {
                    "scene_id": "s04",
                    "role": "verdict_cta",
                    "duration_s": 3.5,
                    "kicker": "WHO IT IS FOR · 适用判断",
                    "headline": "不是开箱即用的 SaaS，\n但 CLI 生产引擎今天能调通",
                    "subtext": "适合愿意自己配环境的独立开发者；先跑完 CLI 线，再决定要不要接进业务。",
                    "cta_line": "想看下一条真实成本与边界拆解，评论区报你想测的开源项目。",
                    "source_label": "1024 VERDICT · PRODUCTION_READY=FALSE",
                },
            ],
        )

    return (
        "Easel 工程拆解：为什么生产级 Agent 底座必须冻结版本",
        [
            {
                "scene_id": "s01",
                "role": "hook_conflict",
                "duration_s": 3.5,
                "kicker": "X超玩·未来智能 · AI 工程拆解",
                "headline": "顺手一次 git pull，整条出片链路为什么直接崩了？",
                "subtext": "从 v0.2.1（982 文件 3fe2d99）到 v0.3.0（bb3c8ff），必须逐文件核对哈希防静默漂移。",
                "image_path": "projects/easel-review/sources/screenshots/12-easel-version-evidence.png",
                "focus_box": [2, 35, 96, 30],
                "source_label": "PINNED EVIDENCE · v0.2.1 982-blob 校验实拍",
            },
            {
                "scene_id": "s02",
                "role": "mechanism_flow",
                "duration_s": 4.2,
                "kicker": "ARCHITECTURE CHAIN · 零上游修改策略",
                "headline": "ADAPTER 隔离层：只调引擎，不改上游源码",
                "nodes": [
                    {"label": "Pin 锁文件", "detail": "easel-pins.json 锁定 bb3c8ff 精确提交"},
                    {"label": "逐文件校验", "detail": "1071 个基线 blob + 14 个覆写摘要比对"},
                    {"label": "Adapter 适配", "detail": "assemble_easel.py 接管 Windows 字幕转义"},
                    {"label": "人工终审门", "detail": "QC PASS ≠ 发布许可，保留人类放行权", "status": "failure"},
                ],
                "subtext": "用薄适配器吞掉平台差异，换来可回滚（v0.2.1）和可复现。",
                "source_label": "ARCHITECTURE · docs/UPSTREAM-EASEL.md",
            },
            {
                "scene_id": "s03",
                "role": "code_walkthrough",
                "duration_s": 4.0,
                "kicker": "KEY CODE · 硬门禁不靠 Prompt 祈祷",
                "headline": "把账号红线写进任务契约，冲突直接退出 4",
                "file_path": "src/contentops/workflow/task_harness.py",
                "highlight_lines": [2, 3, 4],
                "code_lines": [
                    "if manual_policy == 'FORBIDDEN' and wants_desktop_recording:",
                    "    conflicts.append({'severity': 'HARD_BLOCK', 'tier': 2,",
                    "        'code': 'ACCOUNT_RECORDING_FORBIDDEN'})",
                    "status = 'CONFLICT_BLOCKED' if hard_blocks else 'READY'",
                ],
                "subtext": "FI 严禁手动录屏与 AI 假证据，进入合成前即被程序拦截。",
                "source_label": "KEY LINES · task_harness.py",
            },
            {
                "scene_id": "s04",
                "role": "verdict_cta",
                "duration_s": 3.5,
                "kicker": "REPRO & NEXT · 复现与边界",
                "headline": "能跑通不等于能上线，\n每一步都留回执才敢交付",
                "subtext": "运行 easel_engine.py verify v0.3.0 与 make_content.py context 即可复现整条校验链。",
                "cta_line": "需要这套 Agent 工程锁版与门禁方案，评论区说你的技术栈。",
                "source_label": "FI ENGINEERING · PRODUCTION_READY=FALSE",
            },
        ],
    )


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Director-grade multi-role video planner & compiler")
    sub = parser.add_subparsers(dest="command", required=True)

    comp = sub.add_parser("compile", help="compile a director-spec JSON into an om.js film directory")
    comp.add_argument("--spec", required=True, type=Path)
    comp.add_argument("--out-dir", required=True, type=Path)

    demo = sub.add_parser("demo", help="compile a verified-source dual-account director film")
    demo.add_argument("--account", required=True, choices=("x-superplay-future-intelligence", "x-superplay-1024"))
    demo.add_argument("--aspect", default="9:16", choices=("9:16", "16:9"))
    demo.add_argument("--out-dir", required=True, type=Path)
    demo.add_argument("--style-override", default=None)

    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            spec = json.loads(args.spec.read_text(encoding="utf-8"))
            plan = build_director_plan(
                root=ROOT,
                account_slug=str(spec["account_slug"]),
                title=str(spec["title"]),
                aspect=str(spec.get("aspect") or "9:16"),
                scenes=spec.get("scenes") or [],
                style_override=spec.get("style_override"),
            )
            result = compile_huashu_film(plan, root=ROOT, out_dir=args.out_dir)
        else:
            title, scenes = _demo_scenes(args.account)
            plan = build_director_plan(
                root=ROOT,
                account_slug=args.account,
                title=title,
                aspect=args.aspect,
                scenes=scenes,
                style_override=args.style_override,
            )
            result = compile_huashu_film(plan, root=ROOT, out_dir=args.out_dir)
    except DirectorError as exc:
        print(json.dumps({"state": "BLOCKED", "code": exc.code, "reason": exc.detail}, ensure_ascii=False, indent=2))
        return 4

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["design_lint"]["ok"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
