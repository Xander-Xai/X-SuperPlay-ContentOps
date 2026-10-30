#!/usr/bin/env python3
"""Windows-safe content repurposing preflight and manifest generator.

The original shell entrypoint remains available on POSIX systems.  This
wrapper deliberately does not claim that an LLM has generated platform copy;
it creates a reviewable manifest and platform briefs that an Agent or a
configured provider can fill without relying on Bash, jq, iconv, or $HOME.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from media_guard import DERIVATIVE_PLATFORMS, derivative_guard  # noqa: E402


PLATFORM_BRIEFS = {
    "wechat": "保留完整论点、来源和图文结构；输出公众号正文或摘要，不删除事实边界。",
    "xiaohongshu": "提炼可保存清单和视觉卡片文案；避免把长文直接截断。",
    "douyin": "仅输出可选口播脚本与镜头提示；公众号图文仍是主产物，不自动发布。",
    "video": "仅输出可选视频脚本和素材清单；不把视频渲染当作公众号门禁。",
    "newsletter": "拆成可扫描的小节，保留来源、结论和行动号召。",
    "linkedin": "强调方法、证据和案例，减少口语化夸张表达。",
    "twitter": "拆成短帖线程，每条只承载一个事实或判断。",
}


def slugify(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", value).strip("-").lower()
    return value[:60] or "content"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Markdown or text source file")
    parser.add_argument("--platforms", default="wechat", help="comma-separated platform briefs")
    parser.add_argument("--output-dir", default="", help="output directory")
    parser.add_argument(
        "--article-dir",
        type=Path,
        help="公众号定稿目录；生成 video/douyin/audio 派生物时必须提供并已通过 final_reviewed",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印将要生成的产物，不写文件")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    if not source.is_file():
        parser.error(f"source file not found: {source}")
    content = source.read_text(encoding="utf-8", errors="replace")
    platforms = [item.strip().lower() for item in args.platforms.split(",") if item.strip()]
    unknown = [item for item in platforms if item not in PLATFORM_BRIEFS]
    if unknown:
        parser.error("unsupported platforms: " + ", ".join(unknown))

    derivative_platforms = [item for item in platforms if item in DERIVATIVE_PLATFORMS]
    workflow_guard: dict[str, object] = {"status": "not_required"}
    if derivative_platforms:
        if args.article_dir is None:
            print("REPURPOSE BLOCKED: video/douyin/audio 只能作为公众号定稿后的派生附件，请提供 --article-dir", file=sys.stderr)
            return 1
        article_dir = args.article_dir.expanduser()
        if not article_dir.is_absolute():
            article_dir = PROJECT_ROOT / article_dir
        article_dir = article_dir.resolve()
        if source.parent != article_dir or source.name not in {"article.md", "article.html"}:
            print("REPURPOSE BLOCKED: 视频/音频派生必须直接来源于该公众号工作区的 article.md 或 article.html", file=sys.stderr)
            return 1
        guard_errors: list[str] = []
        for platform in derivative_platforms:
            guard_errors.extend(derivative_guard(article_dir, platform))
        if guard_errors:
            print("REPURPOSE BLOCKED: 派生媒体门禁未通过", file=sys.stderr)
            for error in guard_errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        workflow_guard = {
            "status": "passed",
            "required_stage": "final_reviewed",
            "platforms": derivative_platforms,
            "article_dir": article_dir.name,
        }

    root = Path(args.output_dir).expanduser().resolve() if args.output_dir else source.parent / "repurposed"
    final_dir = root / f"{date.today().isoformat()}-{slugify(source.stem)}"
    manifest = {
        "schema_version": 1,
        "status": "brief_ready",
        "source": source.name,
        "source_characters": len(re.sub(r"\s+", "", content)),
        "platforms": platforms,
        "outputs": [f"{platform}.md" for platform in platforms],
        "account_publish": "manual-review-required",
        "delivery": "not_published",
        "workflow_guard": workflow_guard,
    }
    if args.dry_run:
        print(json.dumps({"directory": str(final_dir), "manifest": manifest}, ensure_ascii=False, indent=2))
        return 0

    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "repurpose-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for platform in platforms:
        (final_dir / f"{platform}.md").write_text(
            f"# {platform} 派生简报\n\n"
            f"- 来源：`{source.name}`\n"
            f"- 状态：brief_ready（需 Agent/人工完成改写和审核）\n"
            f"- 约束：{PLATFORM_BRIEFS[platform]}\n\n"
            "## 核心事实与判断\n\n"
            "请从来源正文提取，不得新增未经核验的事实。\n",
            encoding="utf-8",
        )
    print(f"REPURPOSE BRIEFS CREATED: {final_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
