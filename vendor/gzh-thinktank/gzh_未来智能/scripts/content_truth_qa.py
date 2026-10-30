#!/usr/bin/env python3
"""Deterministic content truth checks for tutorial articles.

This is not a semantic fact checker.  It catches claims that are internally
contradictory or too strong to be published without an explicit source:
step-count drift, missing Python packages in install snippets, unsupported
numeric thresholds, and absolute/superlative promises.  The independent
fact-review receipt remains mandatory for papers, benchmarks and high-risk
claims.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from workflow_security import load_json as strict_load_json  # noqa: E402
from workspace_paths import resolve_article_workspace  # noqa: E402


CONTRACT = "content-truth-qa-v1"
ROOT = Path(__file__).resolve().parents[1]

PACKAGE_MAP = {
    "langchain_text_splitters": "langchain-text-splitters",
    "langchain_openai": "langchain-openai",
    "langchain_chroma": "langchain-chroma",
    "langchain_community": "langchain-community",
    "langchain_core": "langchain-core",
    "chromadb": "chromadb",
    "openai": "openai",
    "langchain": "langchain",
}

ABSOLUTE_PATTERNS = (
    r"最低风险",
    r"最高(?:性价比|可靠|靠谱|效价)",
    r"最靠谱",
    r"根本原因",
    r"绝大多数企业",
    r"\b\d{1,3}%\b",
)


def _json(path: Path) -> dict[str, Any]:
    value = strict_load_json(path, default={})
    return value if isinstance(value, dict) else {}


def _claims(sources: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in sources.get("claims", []) if isinstance(item, dict)] if isinstance(sources.get("claims"), list) else []


def _claim_has_provenance(claim: dict[str, Any]) -> bool:
    claim_id = str(claim.get("id") or "").strip()
    source_ids = claim.get("source_ids")
    locator = claim.get("evidence_locator")
    return bool(
        claim_id
        and isinstance(source_ids, list)
        and any(str(value).strip() for value in source_ids)
        and ((isinstance(locator, list) and locator) or isinstance(locator, dict))
        and str(claim.get("as_of") or "").strip()
    )


def _section_blocks(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.M))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((match.group(1).strip(), text[match.end():end]))
    return blocks


def _step_count_errors(text: str) -> list[str]:
    errors: list[str] = []
    for heading, body in _section_blocks(text):
        m = re.search(r"([一二三四五六七八九十\d]+)\s*个(?:核心)?步骤", heading)
        if not m:
            continue
        title_count_raw = m.group(1)
        try:
            title_count = int(title_count_raw)
        except ValueError:
            title_count = "一二三四五六七八九十".index(title_count_raw) + 1
        numbered = re.findall(r"^\s*\d+[\.、]\s+", body, flags=re.M)
        if numbered and len(numbered) != title_count:
            errors.append(f"步骤数漂移：章节“{heading}”声称 {title_count} 步，正文列出 {len(numbered)} 步")
    return errors


def _package_errors(text: str) -> list[str]:
    installs = set()
    for match in re.finditer(r"(?:pip|python\s+-m\s+pip)\s+install\s+([^\n`]+)", text, flags=re.I):
        for token in re.split(r"\s+", match.group(1).strip()):
            token = token.strip("'\";,()")
            if token and not token.startswith("-"):
                installs.add(re.split(r"[<>=!~]", token, maxsplit=1)[0].lower().replace("_", "-"))
    imported = set()
    for match in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", text, flags=re.M):
        root = match.group(1).split(".", 1)[0]
        if root in PACKAGE_MAP:
            imported.add(PACKAGE_MAP[root])
    if not installs or not imported:
        return []
    missing = sorted(pkg for pkg in imported if pkg not in installs)
    return ["代码依赖未出现在安装命令：" + ", ".join(missing)] if missing else []


def _dependency_pin_errors(text: str) -> list[str]:
    """Runnable snippets must declare a reproducible dependency surface."""
    if not re.search(r"能直接跑|可运行|最小\s*RAG|runnable|运行以下代码", text, flags=re.I):
        return []
    errors: list[str] = []
    for match in re.finditer(r"(?:pip|python\s+-m\s+pip)\s+install\s+([^\n`]+)", text, flags=re.I):
        tokens = [token.strip("'\";,()") for token in re.split(r"\s+", match.group(1).strip()) if token.strip() and not token.startswith("-")]
        unpinned = [re.split(r"[<>=!~]", token, maxsplit=1)[0] for token in tokens if "==" not in token and not token.startswith("git+")]
        if unpinned:
            errors.append("可运行代码的安装命令缺少精确版本锁定：" + ", ".join(unpinned))
    return errors


def _unsupported_numeric_errors(text: str, sources: dict[str, Any]) -> list[str]:
    claims = _claims(sources)
    claim_text = " ".join(str(item.get("statement", "")) for item in claims)
    errors: list[str] = []
    for match in re.finditer(r"(?:Faithfulness|Context Recall|Context Precision|Answer Relevancy)[^。\n]{0,80}(?:≥|>=|>)\s*\d+(?:\.\d+)?", text, flags=re.I):
        phrase = match.group(0)
        number = re.search(r"(?:≥|>=|>)\s*\d+(?:\.\d+)?", phrase)
        matching = [claim for claim in claims if number and number.group(0) in str(claim.get("statement") or "")]
        if number and not matching:
            errors.append(f"未绑定来源的评估阈值：{phrase.strip()}")
        elif matching and not any(_claim_has_provenance(claim) for claim in matching):
            errors.append(f"评估阈值缺少结构化 claim/source/evidence 绑定：{phrase.strip()}")
    return errors


def _absolute_errors(text: str, sources: dict[str, Any]) -> list[str]:
    claims = _claims(sources)
    errors: list[str] = []
    for pattern in ABSOLUTE_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.I):
            value = match.group(0)
            matching = [claim for claim in claims if value in str(claim.get("statement") or "")]
            if not matching:
                errors.append(f"未绑定来源的绝对化/硬承诺：{value}")
            elif not any(_claim_has_provenance(claim) for claim in matching):
                errors.append(f"绝对化/硬承诺缺少结构化 claim/source/evidence 绑定：{value}")
    return sorted(set(errors))


def check(article: Path) -> dict[str, Any]:
    article = article.resolve()
    source = article / "article.md"
    if not source.is_file():
        source = article / "draft.md"
    text = source.read_text(encoding="utf-8", errors="replace") if source.is_file() else ""
    sources = _json(article / "sources.json")
    errors = _step_count_errors(text) + _package_errors(text) + _dependency_pin_errors(text)
    errors += _unsupported_numeric_errors(text, sources)
    errors += _absolute_errors(text, sources)
    # Bind high-risk visible claims to a rendered DOM marker.  A phrase copied
    # into sources.json is not evidence that the reader-facing HTML contains
    # the same claim or that the claim was reviewed in context.
    html_path = article / "article.html"
    html = html_path.read_text(encoding="utf-8", errors="replace") if html_path.is_file() else ""
    if html:
        for claim in _claims(sources):
            statement = str(claim.get("statement") or "")
            claim_id = str(claim.get("id") or "").strip()
            if not claim_id or not _claim_has_provenance(claim):
                continue
            high_risk_terms = [term for term in ABSOLUTE_PATTERNS if re.search(term, statement, flags=re.I)]
            if high_risk_terms and not re.search(rf"data-claim-id\s*=\s*[\"']{re.escape(claim_id)}[\"']", html, flags=re.I):
                errors.append(f"可见 HTML 缺少 claim {claim_id} 的 data-claim-id 绑定；台账不能替代正文主张")
    result = {
        "schema_version": 1,
        "contract": CONTRACT,
        "status": "passed" if not errors else "blocked",
        "source": source.name if source.is_file() else "",
        "errors": errors,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    args = parser.parse_args()
    article = resolve_article_workspace(args.article, allow_test_fixture=True)
    result = check(article)
    (article / "content-truth-qa.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
