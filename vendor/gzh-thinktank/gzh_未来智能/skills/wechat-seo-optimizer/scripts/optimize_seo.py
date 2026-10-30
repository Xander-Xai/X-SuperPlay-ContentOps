#!/usr/bin/env python3
"""Deterministic WeChat SEO diagnosis with a structured report."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def _yaml_title(file_path: Path) -> str:
    article_yaml = file_path.parent / "article.yaml"
    if article_yaml.is_file():
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(article_yaml.read_text(encoding="utf-8")) or {}
            title = str(data.get("title", "")).strip()
            if title:
                return title
        except Exception:
            pass
    return ""


def analyze_seo(file_path: Path, keywords_str: str) -> dict:
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()
    title = _yaml_title(file_path)
    if not title:
        title_match = next((re.match(r"^#\s+(.+?)\s*$", line) for line in lines), None)
        title = title_match.group(1).strip() if title_match else ""
    score = 100
    title_score = 100
    suggestions: list[str] = []

    title_len = len(title)
    if title_len < 8 or title_len > 28:
        score -= 10
        title_score -= 15
        suggestions.append(f"标题长度建议在 8-28 字之间，当前为 {title_len} 字。")

    kw_in_title = sum(1 for kw in keywords if kw.lower() in title.lower())
    if kw_in_title == 0:
        score -= 20
        title_score -= 20
        suggestions.append("标题中未包含核心关键词，建议自然嵌入主关键词。")

    headings = re.findall(r"^##\s+(.+)$", content, re.MULTILINE)
    if len(headings) < 3:
        score -= 10
        suggestions.append("小标题（H2）数量不足，建议设置至少 3 个清晰的层级标题。")

    total_chars = len(re.sub(r"\s+", "", content))
    densities = {}
    for kw in keywords:
        count = content.lower().count(kw.lower())
        density = (count * len(kw)) / max(total_chars, 1) * 100
        densities[kw] = round(density, 3)
        if density < 0.5:
            suggestions.append(f"关键词 '{kw}' 密度偏低 ({density:.2f}%)，建议在正文中自然增加。")

    score = max(score, 0)
    title_score = max(title_score, 0)
    return {
        "schema_version": 1,
        "status": "passed" if score >= 70 and title_score >= 70 else "needs_revision",
        "score": score,
        "title_score": title_score,
        "title": title,
        "keywords": keywords,
        "keyword_density": densities,
        "heading_count": len(headings),
        "suggestions": suggestions,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="WeChat SEO Optimizer")
    parser.add_argument("file", help="Markdown article file")
    parser.add_argument("--keywords", default="AI,公众号", help="Comma separated target keywords")
    parser.add_argument("--output", help="JSON report path; defaults beside the input as seo-report.json")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    path = Path(args.file).expanduser().resolve()
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 1
    report = analyze_seo(path, args.keywords)
    output = Path(args.output).expanduser().resolve() if args.output else path.parent / "seo-report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n[WeChat Matrix Pipeline] SEO 诊断报告: {path}")
    print(f"综合评分: {report['score']} / 100")
    print(f"标题评分: {report['title_score']} / 100")
    for index, suggestion in enumerate(report["suggestions"], 1):
        print(f"{index}. {suggestion}")
    print(f"结构化回执: {output}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
