#!/usr/bin/env python3
"""Render reusable graphic templates to PNG + native platform articles + browsable Gallery (T07).

Uses the local Chrome/Huashu ``om still`` renderer (non-paid, zero new deps) to
rasterize each HTML template into pixel-exact PNGs, runs the deterministic
anti-slop design linter, and generates a browsable ``gallery.html`` plus a
receipt with ``production_ready: false`` and ``publish_authorized: false``.

Usage:
    python scripts/render_graphic_templates.py catalog
    python scripts/render_graphic_templates.py gallery --out-dir .verify-tmp/graphic-gallery
    python scripts/render_graphic_templates.py render --account x-superplay-future-intelligence \
        --input spec.json --out-dir out/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.graphic.design_system import account_tokens  # noqa: E402
from contentops.graphic.templates import (  # noqa: E402
    TEMPLATE_CATALOG,
    render_native_article_pack,
    render_template_html,
)
from process_utils import hidden_run  # noqa: E402


def _find_om_cli() -> Optional[Path]:
    env = os.environ.get("CONTENTOPS_HUASHU_MOTION_RUNTIME") or os.environ.get("HUASHU_MOTION_RUNTIME")
    candidates = [Path(env) / "cli" / "om.js"] if env else []
    candidates.extend([
        ROOT / ".runtime" / "huashu-motion" / "cli" / "om.js",
        ROOT.parent / ".runtime" / "huashu-motion" / "cli" / "om.js",
        Path("D:/Projects/X-SuperPlay-ContentOps/.runtime/huashu-motion/cli/om.js"),
    ])
    return next((p.resolve() for p in candidates if p.is_file()), None)


def _rasterize_html(html_path: Path, png_path: Path) -> Dict[str, Any]:
    om_cli = _find_om_cli()
    if om_cli is None:
        return {"rendered": False, "reason": "HUASHU_OM_CLI_MISSING"}
    proc = hidden_run(["node", str(om_cli), "still", str(html_path), "--out", str(png_path)], timeout=120)
    if proc.returncode != 0 or not png_path.is_file():
        return {"rendered": False, "reason": ((proc.stderr or proc.stdout or "")[-400:]).strip()}
    digest = hashlib.sha256(png_path.read_bytes()).hexdigest()
    return {"rendered": True, "bytes": png_path.stat().st_size, "sha256": digest}


def _default_gallery_specs() -> List[Dict[str, Any]]:
    """Real Easel v0.2.1/v0.3.0 verified-source showcase across both accounts & all templates."""
    return [
        {
            "id": "fi-01-cover-wide",
            "account": "x-superplay-future-intelligence",
            "template_id": "tech_cover",
            "width": 1600,
            "height": 900,
            "data": {
                "kicker": "AI ENGINEERING TEARDOWN · FI",
                "title": "开源 Agent 底座：为什么必须锁死版本？",
                "subtitle": "从 runtime/easel-pins.json 的 bb3c8ff 冻结策略，拆解生产级内容流水线的确定性边界。",
                "conflict_tag": "1071 个基线文件 + 14 个覆写文件逐一哈希校验，拒绝静默漂移",
                "wireframe_labels": ["PIN.JSON", "HASH GATE", "ADAPTER", "REVIEW"],
                "source_note": "SOURCE: runtime/easel-pins.json · commit bb3c8ff",
            },
        },
        {
            "id": "fi-02-architecture",
            "account": "x-superplay-future-intelligence",
            "template_id": "mechanism_architecture",
            "width": 1600,
            "height": 900,
            "data": {
                "kicker": "SYSTEM ARCHITECTURE · FI",
                "title": "一条可追溯内容产线的 4 道硬边界",
                "nodes": [
                    {"label": "真实来源入场", "detail": "源码/回执/实拍先算 SHA-256，无许可来源直接拒收", "artifact": "source-refs.json"},
                    {"label": "任务契约与冲突检查", "detail": "6 级规则优先级拦截跨账号录屏与 AI 冒充证据", "artifact": "task-contract.json"},
                    {"label": "镜头与模板编译", "detail": "按账号 DNA 浅色令牌渲染视频分镜与原生图文", "artifact": "director-plan.json"},
                    {"label": "独立审稿与人工放行", "detail": "技术 QC 通过≠可发布，发布权始终留在人类手里", "artifact": "human-review.json", "status": "failure"},
                ],
                "boundary_note": "任意阶段改动上游来源或文案，指纹自动失效（STALE），不允许带旧审批进入合成。",
                "source_note": "EXPLANATORY ARCHITECTURE · ContentOps src/contentops/workflow/",
            },
        },
        {
            "id": "fi-03-code-annotated",
            "account": "x-superplay-future-intelligence",
            "template_id": "code_annotated",
            "width": 1600,
            "height": 900,
            "data": {
                "kicker": "KEY CODE EXCERPT · FI",
                "title": "为什么跨账号录屏请求在合成前就被直接拦住？",
                "file_path": "src/contentops/workflow/task_harness.py",
                "start_line": 176,
                "highlight_lines": [179, 180, 181],
                "code_lines": [
                    "if manual_policy == 'FORBIDDEN' and flags.get('wants_desktop_recording'):",
                    "    conflicts.append({",
                    "        'severity': 'HARD_BLOCK',",
                    "        'tier': 2,",
                    "        'code': 'ACCOUNT_RECORDING_FORBIDDEN',",
                    "        'rule': f'{account_slug} forbids manual desktop recording',",
                    "    })",
                    "hard_blocks = [c for c in conflicts if c['severity'] == 'HARD_BLOCK']",
                    "status = 'CONFLICT_BLOCKED' if hard_blocks else 'READY_FOR_WORKFLOW'",
                ],
                "callouts": [
                    {"line_ref": "L176-181", "title": "程序硬拦截，不靠 Prompt 祈祷", "detail": "规则冲突直接返回 CONFLICT_BLOCKED 与退出码 4，避免 Agent 静默妥协。"},
                    {"line_ref": "L183", "title": "区分硬红线与允许覆盖", "detail": "单镜头配色微调（Tier 4）允许放行；FI 录屏与 AI 假证据（Tier 1-2）强制阻断。", "kind": "problem"},
                ],
                "source_note": "VERBATIM SOURCE · src/contentops/workflow/task_harness.py",
            },
        },
        {
            "id": "1024-04-measured-comparison",
            "account": "x-superplay-1024",
            "template_id": "measured_comparison",
            "width": 1600,
            "height": 900,
            "data": {
                "kicker": "MEASURED TEARDOWN · X超玩·1024",
                "title": "Easel v0.2.1 实测：能跑，但 7 项检查没过",
                "metrics": [
                    {"label": "DOCTOR OK", "value": "12 项", "note": "Python/Node/FFmpeg/Playwright", "tone": "success"},
                    {"label": "DOCTOR FAIL", "value": "7 项", "note": "6 项 Web 依赖 + 1 项网关端口", "tone": "problem"},
                    {"label": "BUILT-IN SKILLS", "value": "114 个", "note": "创作层占 52 个（实数统计）"},
                    {"label": "HASH VERIFIED", "value": "982/982", "note": "逐文件比对上游 commit 3fe2d99", "tone": "success"},
                ],
                "columns": ["实测环节", "实际观测结果", "状态", "适用边界与坑"],
                "rows": [
                    {"item": "CLI + Skill 往返", "measured": "easel ping Step 2 通，video-script 返回完整稿", "status": "PASS", "boundary": "需走 easel profile 37289 端口"},
                    {"item": "healthz 探测", "measured": "ping Step 1 报错红灯", "status": "FAIL", "boundary": "上游写死 127.0.0.1:18789"},
                    {"item": "Web 工作台", "measured": "缺 fastapi/uvicorn/前端构建/.env Key", "status": "FAIL", "boundary": "6 项未就绪，Web UI 未验"},
                    {"item": "assemble.py 合成", "measured": "纯标准库独立可用", "status": "PASS", "boundary": "Windows 字幕路径需经 adapter 转义"},
                ],
                "verdict": "结论：不是开箱即用的 SaaS，但 CLI 与 Skill 生产底座今天能调通——适合有工程能力的独立开发者，不适合零配置新手。",
                "source_note": "SOURCE: projects/easel-review/script/master.md (REAL LOCAL RUN)",
            },
        },
        {
            "id": "1024-05-playbook-steps",
            "account": "x-superplay-1024",
            "template_id": "step_workflow_timeline",
            "width": 1080,
            "height": 1440,
            "data": {
                "kicker": "PRACTICAL PLAYBOOK · X超玩·1024",
                "title": "接手开源 Agent 工具前，先跑完这 4 步体检",
                "steps": [
                    {"title": "锁死版本并逐文件验哈希", "detail": "别直接追 main 分支；先核对固定 commit 与所有文件摘要。", "command": "python scripts/easel_engine.py verify v0.3.0"},
                    {"title": "用任务契约检查冲突与上下文", "detail": "一条命令加载账号 DNA、浅色令牌、适用 Skills 和红线检查。", "command": "python scripts/make_content.py context --request \"...\""},
                    {"title": "只拿真实运行日志与裁切录屏举证", "detail": "1024 实测片先过录屏入场门，禁止拿 AI 图冒充测试结果。", "command": "python scripts/ingest_recording.py --project <slug> --crop ..."},
                    {"title": "本地连续动画渲染并留存回执", "detail": "区分 animatic 预演与连续帧候选成片，最终由人审片放行。", "command": "python scripts/render_film.py --film <dir> --out out.mp4 --mode formal"},
                ],
                "pitfall": "看到 doctor 绿了 12 项别急着宣称「全通」——把那 7 项 FAIL 和端口写死坑当面讲清，才是有信息增量的实测。",
                "source_note": "SOURCE: ContentOps RUNBOOK & projects/easel-review",
            },
        },
        {
            "id": "gzh-06-cover-235",
            "account": "x-superplay-future-intelligence",
            "template_id": "tech_cover",
            "width": 900,
            "height": 383,
            "data": {
                "kicker": "WECHAT 2.35:1 · FI",
                "title": "Easel 工程拆解：982 文件校验与 7 项失败复盘",
                "subtitle": "为什么我们把开源引擎锁在固定提交，并把 CLI 与 Web 路径拆开验证",
                "wireframe_labels": ["LOCK", "VERIFY", "CLI OK", "WEB FAIL"],
                "source_note": "900×383 NATIVE GZH COVER",
            },
        },
    ]


def render_batch(specs: List[Dict[str, Any]], out_dir: Path, *, render_png: bool = True) -> Dict[str, Any]:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    items: List[Dict[str, Any]] = []
    for spec in specs:
        item_id = str(spec["id"])
        res = render_template_html(
            ROOT,
            template_id=str(spec["template_id"]),
            account_slug=str(spec["account"]),
            data=spec.get("data") or {},
            width=spec.get("width"),
            height=spec.get("height"),
        )
        html_path = out_dir / f"{item_id}.html"
        html_path.write_text(res["html"], encoding="utf-8")
        png_path = out_dir / f"{item_id}.png"
        raster = _rasterize_html(html_path, png_path) if render_png else {"rendered": False, "reason": "SKIPPED_BY_FLAG"}
        items.append({
            "id": item_id,
            "account": res["account_slug"],
            "template_id": res["template_id"],
            "width": res["width"],
            "height": res["height"],
            "html": html_path.name,
            "png": png_path.name if raster.get("rendered") else None,
            "raster": raster,
            "design_lint": res["design_lint"],
        })

    # Build browsable gallery HTML
    cards_markup = []
    for it in items:
        img_tag = f'<img src="{it["png"]}" alt="{it["id"]}">' if it["png"] else f'<iframe src="{it["html"]}"></iframe>'
        lint_ok = "PASS" if it["design_lint"]["ok"] else "FAIL"
        cards_markup.append(
            '<article class="g-item">'
            f'  <div class="g-meta"><b>{it["id"]}</b> · <span>{it["template_id"]}</span> · '
            f'<span>{it["account"]}</span> · <span>{it["width"]}×{it["height"]}</span> · '
            f'<span class="lint-{lint_ok.lower()}">LINT {lint_ok}</span></div>'
            f'  <div class="g-preview">{img_tag}</div>'
            '</article>'
        )
    gallery_html = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>ContentOps Graphic Template Gallery</title>'
        '<style>body{margin:0;padding:40px;background:#EEF1F2;color:#18232B;font-family:"Noto Sans SC","Microsoft YaHei",sans-serif}'
        'h1{margin:0 0 8px;font-size:32px}p.sub{margin:0 0 28px;color:#5C6970}'
        '.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:28px}'
        '.g-item{background:#FFF;border:1px solid #CFD9DC;border-radius:12px;padding:18px;display:flex;flex-direction:column;gap:12px}'
        '.g-meta{font:600 13px/1.4 ui-monospace,monospace;color:#5C6970}.g-meta b{color:#18232B}'
        '.lint-pass{color:#1F7A5A}.lint-fail{color:#BD5149}'
        '.g-preview img{width:100%;height:auto;border-radius:8px;border:1px solid #E2E8EA;display:block}'
        '</style></head><body>'
        '<h1>X-SuperPlay ContentOps · Reusable Graphic Template Gallery</h1>'
        '<p class="sub">Account-DNA light design system (FI soft-engineering #E9EDEF + 1024 warm-editorial #F4F2ED). Review preview only (production_ready: false).</p>'
        f'<div class="grid">{"".join(cards_markup)}</div></body></html>\n'
    )
    (out_dir / "gallery.html").write_text(gallery_html, encoding="utf-8")
    receipt = {
        "schema": "contentops.graphic-template-render/v1",
        "gallery": "gallery.html",
        "count": len(items),
        "all_design_lint_passed": all(it["design_lint"]["ok"] for it in items),
        "all_png_rendered": all(bool(it["png"]) for it in items),
        "items": items,
        "production_ready": False,
        "publish_authorized": False,
    }
    (out_dir / "render-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Render reusable graphic templates and native platform articles")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("catalog", help="list all registered graphic templates")

    gal = sub.add_parser("gallery", help="render all 6 showcase templates into a browsable gallery")
    gal.add_argument("--out-dir", required=True, type=Path)
    gal.add_argument("--html-only", action="store_true")

    rnd = sub.add_parser("render", help="render custom template spec JSON (cards + optional native articles)")
    rnd.add_argument("--account", required=True)
    rnd.add_argument("--input", required=True, type=Path)
    rnd.add_argument("--out-dir", required=True, type=Path)
    rnd.add_argument("--html-only", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "catalog":
        print(json.dumps({"templates": list(TEMPLATE_CATALOG)}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "gallery":
        receipt = render_batch(_default_gallery_specs(), args.out_dir, render_png=not args.html_only)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0 if receipt["all_design_lint_passed"] else 4
    if args.command == "render":
        spec = json.loads(args.input.read_text(encoding="utf-8"))
        cards = spec.get("cards") or []
        for card in cards:
            card.setdefault("account", args.account)
        receipt = render_batch(cards, args.out_dir, render_png=not args.html_only) if cards else {"items": [], "all_design_lint_passed": True}
        if spec.get("article"):
            tokens = account_tokens(ROOT, args.account)
            plats = spec.get("platforms") or ["wechat_article", "zhihu", "csdn", "x"]
            native = render_native_article_pack(tokens, spec["article"], platforms=plats)
            args.out_dir.mkdir(parents=True, exist_ok=True)
            ext_map = {"wechat_article": "article-gzh.html", "zhihu": "article-zhihu.md", "csdn": "article-csdn.md", "x": "post-x.md"}
            written_articles = {}
            for plat, content in native.items():
                target = args.out_dir / ext_map[plat]
                target.write_text(content, encoding="utf-8")
                written_articles[plat] = target.name
            receipt["native_articles"] = written_articles
            (args.out_dir / "render-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0 if receipt.get("all_design_lint_passed", True) else 4
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
