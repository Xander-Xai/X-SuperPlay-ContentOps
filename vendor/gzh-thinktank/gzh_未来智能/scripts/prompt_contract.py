#!/usr/bin/env python3
"""Prompt contract for image-generation prompts (RC1 / RC4).

A generation prompt sent to an image model must describe the *picture* only.
Operational metadata (visual owner, generation mode, continuity group, mobile
safe area, fallback, evidence claim ids, render backend ...) belongs in the
prompt file's YAML frontmatter, never in the body the model reads.  Leaking
that metadata into the body pollutes the image and is exactly the "concern
mixing" failure we are removing from the whole pipeline.

This module is the single, reusable contract checker.  It is called:
  * after ``build_image_prompt_plan.py`` compiles prompt files (hard fail),
  * inside ``visual_qa.py check()`` at the ``illustrated`` gate (hard fail),
so the contract is enforced at both generation-plan time and gate time.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# Phrases that must NEVER appear in a prompt body (they are control/audit
# metadata, not picture description).  Matched case-insensitively.
METADATA_LEAK_PATTERNS: tuple[str, ...] = (
    r"visual\s*owner\s*:",
    r"generation\s*mode\s*:",
    r"continuity\s*group\s*:",
    r"mobile\s*safe\s*area\s*:",
    r"fallback\s*:",
    r"evidence\s*claim\s*ids\s*:",
    r"render\s*backend\s*:",
    r"execution\s*backend\s*:",
    r"requested\s*backend\s*:",
    r"request\s*sha",
    r"execution\s*provider",
)

# A compliant prompt must contain these structural anchors.
REQUIRED_PATTERNS: tuple[str, ...] = (
    r"subject\s*:",
    r"style\s*:",
)

# A compliant illustrative/cover prompt must declare what the model must NOT
# put into the picture (no readable text, numbers, code, charts).
NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"negative\s*:",
    r"不要生成|不得出现|禁止|不得包含|不含文字|无文字|不要出现文字",
)


def _read_prompt_file(path: Path) -> tuple[dict[str, Any], str]:
    """Split a prompt file into (frontmatter dict, body string)."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        frontmatter: dict[str, Any] = {}
        body = parts[-1] if len(parts) >= 3 else text
        if len(parts) >= 3:
            try:
                import yaml  # type: ignore

                frontmatter = yaml.safe_load(parts[1]) or {}
            except Exception:
                frontmatter = {}
        return frontmatter, body
    return {}, text


def validate_prompt_body(body: str, *, exact_text: bool = False) -> list[str]:
    """Return a list of contract violations for a prompt body."""
    problems: list[str] = []
    lowered = body.lower()

    for pattern in METADATA_LEAK_PATTERNS:
        if re.search(pattern, lowered):
            problems.append(f"提示词正文泄露运营元数据（匹配 '{pattern}'）")

    for pattern in REQUIRED_PATTERNS:
        if not re.search(pattern, lowered):
            problems.append(f"提示词缺少必要结构（缺少 '{pattern}'）")

    has_negative = any(re.search(p, lowered) for p in NEGATIVE_PATTERNS)
    if exact_text:
        # Deterministic SVG/HTML/KaTeX diagrams are the opposite of an
        # illustrative prompt: exact labels and typed edges are facts, so a
        # blanket "no text" instruction would silently produce a picture that
        # cannot satisfy the visual contract.
        if not re.search(r"精确|exact|可读文字|标签|节点|箭头|关系", lowered):
            problems.append("确定性技术图提示词必须声明 exact text/labels/edges")
        if not has_negative:
            problems.append("提示词缺少负向约束（需禁止水印、伪界面、乱码和无关装饰）")
    elif not has_negative:
        problems.append("提示词缺少负向约束（必须声明画面禁止文字/数字/代码/图表）")

    return problems


def validate_prompt_file(path: Path) -> list[str]:
    if not path.is_file():
        return [f"提示词文件不存在：{path.name}"]
    frontmatter, body = _read_prompt_file(path)
    backend = str(frontmatter.get("execution_backend") or frontmatter.get("render_backend") or "").strip().lower()
    mode = str(frontmatter.get("generation_mode") or "").strip().lower()
    exact_text = mode == "deterministic" or backend in {
        "deterministic-svg", "deterministic-infographic", "beautiful-mermaid",
        "katex-html-composite", "code-block", "formula-code-map", "excalidraw",
    }
    return validate_prompt_body(body, exact_text=exact_text)


def validate_plan(article_dir: Path) -> list[str]:
    """Validate every prompt file referenced by image-generation-plan.json."""
    plan_path = article_dir / "image-generation-plan.json"
    if not plan_path.is_file():
        return []
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    violations: list[str] = []
    for item in plan.get("prompt_files", []) if isinstance(plan.get("prompt_files"), list) else []:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("path", "")).strip()
        if not raw:
            continue
        path = (article_dir / raw).resolve()
        for problem in validate_prompt_file(path):
            violations.append(f"{path.name}: {problem}")
    return violations


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, help="文章目录")
    parser.add_argument("--prompt-file", help="只校验单个提示词文件")
    args = parser.parse_args()

    article = Path(args.article).expanduser()
    if not article.is_absolute():
        article = Path(__file__).resolve().parents[1] / article
    article = article.resolve()

    if args.prompt_file:
        problems = validate_prompt_file(article / args.prompt_file)
    else:
        problems = validate_plan(article)

    if problems:
        print("PROMPT CONTRACT FAILED")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("PROMPT CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
