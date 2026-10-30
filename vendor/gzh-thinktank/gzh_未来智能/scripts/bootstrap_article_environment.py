#!/usr/bin/env python3
"""Bootstrap the ignored local article environment without touching secrets.

The repository keeps configuration and credentials outside version control, but
the article writer still needs a predictable preset directory.  This command
creates the directories and copies only public seed presets.  It never creates
or edits ``aws.env``.

Usage:
    python scripts/bootstrap_article_environment.py
    python scripts/bootstrap_article_environment.py --check
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from check_runtime_dependencies import check as check_runtime_dependencies


ROOT = Path(__file__).resolve().parents[1]
AWS_ROOT = ROOT / ".aws-article"
PRESET_DIRS = (
    "structures",
    "closing-blocks",
    "title-styles",
    "formatting",
    "cover-styles",
    "image-styles",
    "sticker-styles",
)
SEEDS = {
    "structures/AI 项目问题驱动教程结构.md": ROOT
    / "skills"
    / "gzh-article-orchestrator"
    / "references"
    / "presets"
    / "structures"
    / "AI 项目问题驱动教程结构.md",
    "closing-blocks/公众号关注引导.md": ROOT
    / "skills"
    / "gzh-article-orchestrator"
    / "references"
    / "presets"
    / "closing-blocks"
    / "simple.example.md",
}


def ensure_article_environment(*, check_only: bool = False) -> list[str]:
    missing: list[str] = []
    if not AWS_ROOT.is_dir():
        missing.append(".aws-article")
    for name in PRESET_DIRS:
        path = AWS_ROOT / "presets" / name
        if not path.is_dir():
            missing.append(str(path.relative_to(ROOT)))
            if not check_only:
                path.mkdir(parents=True, exist_ok=True)
    tmp = AWS_ROOT / "tmp"
    if not tmp.is_dir():
        missing.append(str(tmp.relative_to(ROOT)))
        if not check_only:
            tmp.mkdir(parents=True, exist_ok=True)

    for relative, source in SEEDS.items():
        target = AWS_ROOT / "presets" / relative
        if target.is_file():
            continue
        if not source.is_file():
            missing.append(f"seed:{source.relative_to(ROOT)}")
            continue
        missing.append(str(target.relative_to(ROOT)))
        if not check_only:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只检查，不创建目录或文件")
    parser.add_argument("--check-dependencies", action="store_true", help="同时检查 PyYAML/Pillow 与浏览器渲染依赖")
    args = parser.parse_args()
    if args.check_dependencies:
        dependency_errors = check_runtime_dependencies(require_chrome=True)
        if dependency_errors:
            print("ARTICLE ENVIRONMENT DEPENDENCIES BLOCKED")
            for item in dependency_errors:
                print(f"- {item}")
            return 1
        print("ARTICLE ENVIRONMENT DEPENDENCIES READY")
    missing = ensure_article_environment(check_only=args.check)
    if missing and args.check:
        print("ARTICLE ENVIRONMENT MISSING")
        for item in missing:
            print(f"- {item}")
        return 1
    if missing:
        print("ARTICLE ENVIRONMENT READY")
        for item in missing:
            print(f"- created: {item}")
    else:
        print("ARTICLE ENVIRONMENT ALREADY READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
