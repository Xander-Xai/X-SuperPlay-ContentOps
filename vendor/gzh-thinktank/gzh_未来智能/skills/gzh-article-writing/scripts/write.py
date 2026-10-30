#!/usr/bin/env python3
"""Agent-only 公众号写作辅助工具。

写稿由当前 Agent 在本地完成；本脚本不连接外部写作服务，也不读取写作模型
凭证。它保留两个安全的辅助能力：生成统一约束提示词，以及在审稿阶段剥离
资料路径标注。这样可以继续被旧版编排器调用，同时从代码层面移除外部写稿依赖。

用法：
    python write.py prompt draft <topic-card.md>
    python write.py prompt rewrite <article.md> --instruction "改成口语化"
    python write.py strip-citations <draft.md> -o <article.md>

draft/rewrite/continue 子命令保留为兼容入口，但会明确提示由 Agent 直接写稿，
并以退出码 2 结束；不会尝试网络请求或读取任何模型密钥。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml


for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def _err(message: str, code: int = 1) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(code)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        _err(f"无法读取文件 {path}: {exc}")


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = yaml.safe_load(_read_text(path))
    except yaml.YAMLError as exc:
        _err(f"YAML 解析失败 {path}: {exc}")
    return value if isinstance(value, dict) else {}


def _article_dir(input_path: Path) -> Path:
    return input_path if input_path.is_dir() else input_path.parent


def _merged_context(input_path: Path) -> dict:
    """读取公开写作约束，不读取任何凭证字段。"""
    root = Path.cwd()
    context = _load_yaml(root / ".aws-article" / "config.yaml")
    context.update(_load_yaml(_article_dir(input_path) / "article.yaml"))
    for key in ("image_model",):
        context.pop(key, None)
    return context


def _reference_texts(paths: list[str] | None) -> str:
    chunks: list[str] = []
    for raw in (paths or [])[:5]:
        path = Path(raw)
        if not path.is_file():
            _err(f"参考资料不存在: {path}")
        chunks.append(f"\n--- 参考资料: {path.name} ---\n{_read_text(path)}")
    return "".join(chunks)


def _build_prompt(mode: str, input_path: Path, instruction: str = "", references: list[str] | None = None) -> dict:
    source = _read_text(input_path)
    context = _merged_context(input_path)
    system = (
        "你是公众号内容编辑。请严格依据输入材料和公开账号约束写作，"
        "不得虚构事实；需要引用时保留可审计的资料路径标注；"
        "正文使用简体中文，结构清晰，适合移动端图文阅读。"
    )
    user = [
        f"任务模式：{mode}",
        f"公开账号约束（仅用于写作，不含凭证）：{json.dumps(context, ensure_ascii=False, indent=2)}",
        "输入材料：",
        source,
    ]
    if instruction.strip():
        user.extend(["\n补充要求：", instruction.strip()])
    refs = _reference_texts(references)
    if refs:
        user.extend(["\n参考资料（只可据此核验事实）：", refs])
    return {
        "mode": mode,
        "system_prompt": system,
        "user_prompt": "\n".join(user),
        "writing_provider": "agent-local",
    }


def _strip_citations(text: str) -> str:
    patterns = [
        r"\s*[（(]\s*资料路径\s*[:：]\s*[^）)]*[）)]",
        r"\s*[（(]\s*来源\s*[:：]\s*[^）)]*[）)]",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text)
    return text


def _add_input_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", type=Path, help="选题卡片或文章 Markdown 路径")
    parser.add_argument("-o", "--output", type=Path, help="输出路径")
    parser.add_argument("--instruction", default="", help="补充写作要求")
    parser.add_argument("--reference", action="append", default=[], help="公开参考资料，可重复，最多 5 个")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent-only 公众号写作辅助工具")
    sub = parser.add_subparsers(dest="command", required=True)

    prompt = sub.add_parser("prompt", help="生成供当前 Agent 使用的约束提示词")
    prompt.add_argument("mode", choices=("draft", "rewrite", "continue"))
    _add_input_args(prompt)

    for mode in ("draft", "rewrite", "continue"):
        compat = sub.add_parser(mode, help="兼容入口：写稿由当前 Agent 完成")
        _add_input_args(compat)

    strip = sub.add_parser("strip-citations", help="剥离资料路径标注")
    strip.add_argument("input", type=Path)
    strip.add_argument("-o", "--output", type=Path)

    args = parser.parse_args(argv)
    if args.command == "strip-citations":
        text = _strip_citations(_read_text(args.input))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0

    if args.command == "prompt":
        if not args.input.is_file():
            _err(f"输入文件不存在: {args.input}")
        payload = _build_prompt(args.mode, args.input, args.instruction, args.reference)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
        return 0

    _err("写稿入口已改为 Agent 本地执行；请使用 prompt 子命令获取约束后由当前 Agent 产出正文。", 2)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
