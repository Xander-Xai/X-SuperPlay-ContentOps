#!/usr/bin/env python3
"""Validate a topic contract and detect topic drift in article content.

The topic contract is intentionally separate from the prose brief.  The brief
answers *who/why/CTA*; this contract answers *what the article is about, what it
is not about, and how every supporting concept must return to the topic*.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from workflow_security import load_yaml as strict_load_yaml  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILE = "topic-contract.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = strict_load_yaml(path, default={})
    return payload if isinstance(payload, dict) else {}


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _hits(text: str, terms: list[str]) -> list[str]:
    folded = text.casefold()
    return [term for term in terms if term.casefold() in folded]


def _hit_count(text: str, terms: list[str]) -> int:
    """Count occurrences, not just distinct terms, to measure real anchoring."""
    folded = text.casefold()
    return sum(folded.count(term.casefold()) for term in terms if term)


def _sections(text: str) -> list[tuple[str, str]]:
    """Return H2 sections; fall back to the whole article for short drafts."""
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", text))
    if not matches:
        return [("全文", text)] if text.strip() else []
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((match.group(1).strip(), text[match.start():end]))
    return sections


def _first_heading(text: str) -> str:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
    return match.group(1).strip() if match else ""


def _lead_body(text: str) -> str:
    """Return the opening prose after the H1, excluding the title itself."""
    match = re.search(r"(?m)^#\s+.+?$", text)
    if not match:
        return text[:1200]
    return text[match.end(): match.end() + 1200]


def _section_body(section_text: str) -> str:
    """Remove the H2 line so a heading cannot fake a topic return."""
    return section_text.split("\n", 1)[1] if "\n" in section_text else ""


def _visible_text(text: str) -> str:
    """Remove non-reader-facing comments/hidden blocks before anchor counts."""

    value = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    value = re.sub(r"<script\b.*?</script\s*>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style\s*>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    # Keep line boundaries: title/lead/section extraction uses Markdown line
    # structure, while comments/tags are already removed above.
    return re.sub(r"[ \t]+", " ", value).strip()


def _contract_path(article_dir: Path) -> Path:
    return article_dir / CONTRACT_FILE


def load_contract(article_dir: Path) -> dict[str, Any]:
    return _load_yaml(_contract_path(article_dir))


def validate_contract(article_dir: Path) -> list[str]:
    """Validate the machine-readable topic boundary and series map."""
    path = _contract_path(article_dir)
    errors: list[str] = []
    if not path.is_file():
        return [f"缺少 {CONTRACT_FILE}；必须先锁定主题边界合同"]
    contract = load_contract(article_dir)
    if not contract:
        return [f"{CONTRACT_FILE} 为空或不是有效 YAML 对象"]

    try:
        schema_version = int(contract.get("schema_version", 0) or 0)
    except (TypeError, ValueError):
        schema_version = 0
    if schema_version != 1:
        errors.append(f"{CONTRACT_FILE} 的 schema_version 必须是 1")
    if str(contract.get("status", "")).strip().lower() != "approved":
        errors.append(f"{CONTRACT_FILE} 的 status 必须是 approved，不能用 draft/pending 进入选题门禁")
    canonical = str(contract.get("canonical_topic", "")).strip()
    thesis = str(contract.get("topic_thesis", "")).strip()
    reader_problem = str(contract.get("reader_problem", "")).strip()
    for label, value in (("canonical_topic", canonical), ("topic_thesis", thesis), ("reader_problem", reader_problem)):
        if not value:
            errors.append(f"{CONTRACT_FILE} 缺少 {label}")

    scope = contract.get("scope")
    if not isinstance(scope, dict):
        errors.append(f"{CONTRACT_FILE} 缺少 scope 对象")
        scope = {}
    in_scope = _list(scope.get("in_scope"))
    out_scope = _list(scope.get("out_of_scope"))
    if len(in_scope) < 2:
        errors.append(f"{CONTRACT_FILE}.scope.in_scope 至少需要 2 项")
    if not out_scope:
        errors.append(f"{CONTRACT_FILE}.scope.out_of_scope 不能为空；必须明确不展开什么")

    anchor = contract.get("anchor")
    if not isinstance(anchor, dict):
        errors.append(f"{CONTRACT_FILE} 缺少 anchor 对象")
        anchor = {}
    terms = _list(anchor.get("required_terms"))
    aliases = _list(anchor.get("aliases"))
    if len(terms) < 2:
        errors.append(f"{CONTRACT_FILE}.anchor.required_terms 至少需要 2 个主题锚点词")
    try:
        min_total_hits = int(anchor.get("minimum_total_hits", 3))
        if min_total_hits < 1:
            raise ValueError
    except (TypeError, ValueError):
        errors.append(f"{CONTRACT_FILE}.anchor.minimum_total_hits 必须是正整数")

    series = contract.get("series")
    if not isinstance(series, dict):
        errors.append(f"{CONTRACT_FILE} 缺少 series 对象")
        series = {}
    mode = str(series.get("mode", "")).strip().lower()
    if mode not in {"single", "cluster"}:
        errors.append(f"{CONTRACT_FILE}.series.mode 必须是 single 或 cluster")
    subtopics = series.get("subtopics")
    if not isinstance(subtopics, list):
        subtopics = []
        errors.append(f"{CONTRACT_FILE}.series.subtopics 必须是列表")
    if mode == "cluster" and len(subtopics) < 3:
        errors.append(f"cluster 模式至少需要 3 个后续子题，避免写作时临时漂移")
    seen_ids: set[str] = set()
    for index, item in enumerate(subtopics, 1):
        if not isinstance(item, dict):
            errors.append(f"series.subtopics 第 {index} 项必须是对象")
            continue
        item_id = str(item.get("id", "")).strip()
        title = str(item.get("title", "")).strip()
        relation = str(item.get("relation", "")).strip().lower()
        rationale = str(item.get("why_it_belongs", "")).strip()
        return_to_topic = str(item.get("return_to_topic", "")).strip()
        if not item_id or item_id in seen_ids:
            errors.append(f"series.subtopics 第 {index} 项 id 缺失或重复")
        seen_ids.add(item_id)
        if not title:
            errors.append(f"series.subtopics 第 {index} 项缺少 title")
        if relation not in {"core", "supporting", "adjacent"}:
            errors.append(f"series.subtopics 第 {index} 项 relation 必须是 core/supporting/adjacent")
        if not rationale:
            errors.append(f"series.subtopics 第 {index} 项缺少 why_it_belongs")
        if not return_to_topic:
            errors.append(f"series.subtopics 第 {index} 项缺少 return_to_topic；必须写明如何回到主主题")

    drift = contract.get("drift_rules")
    if not isinstance(drift, dict):
        errors.append(f"{CONTRACT_FILE} 缺少 drift_rules 对象")
        drift = {}
    try:
        coverage = float(drift.get("min_anchor_coverage", 0.6))
        if not 0 < coverage <= 1:
            raise ValueError
    except (TypeError, ValueError):
        errors.append(f"{CONTRACT_FILE}.drift_rules.min_anchor_coverage 必须在 0 和 1 之间")
    try:
        max_anchorless = int(drift.get("max_anchorless_sections", 1))
        if max_anchorless < 0:
            raise ValueError
    except (TypeError, ValueError):
        errors.append(f"{CONTRACT_FILE}.drift_rules.max_anchorless_sections 必须是非负整数")
    for key in ("require_anchor_in_title", "require_anchor_in_lead", "require_section_return"):
        if not isinstance(drift.get(key), bool):
            errors.append(f"{CONTRACT_FILE}.drift_rules.{key} 必须是布尔值")

    approval = contract.get("approval")
    if not isinstance(approval, dict):
        errors.append(f"{CONTRACT_FILE} 缺少 approval 对象")
    else:
        if str(approval.get("reviewer", "")).strip() == "":
            errors.append(f"{CONTRACT_FILE}.approval.reviewer 不能为空")
        if str(approval.get("approved_at", "")).strip() == "":
            errors.append(f"{CONTRACT_FILE}.approval.approved_at 不能为空")

    # The contract must actually describe the article's selected topic.
    metadata = _load_yaml(article_dir / "article.yaml")
    brief = _load_yaml(article_dir / "content-brief.yaml")
    title = str(metadata.get("title", "")).strip() or str(brief.get("title", "")).strip()
    selected_keyword = str(brief.get("primary_keyword", "")).strip()
    title_terms = terms + aliases + ([canonical] if canonical else [])
    if title and title_terms and not _hits(title, title_terms):
        errors.append(f"文章标题没有命中主题锚点：{canonical}")
    if selected_keyword and canonical and _norm(canonical) not in _norm(selected_keyword) and _norm(selected_keyword) not in _norm(canonical):
        if not _hits(selected_keyword, terms + aliases):
            errors.append("content-brief.yaml 的 primary_keyword 与主题锚点无交集")

    cluster_path = article_dir / "topic-cluster.md"
    if not cluster_path.is_file():
        errors.append("缺少 topic-cluster.md；必须记录主题母题、子题关系和内容缺口")
    elif canonical and not _hits(_text(cluster_path), [canonical] + terms + aliases):
        errors.append("topic-cluster.md 没有回链 canonical_topic 或主题锚点词")
    return errors


def check_alignment(article_dir: Path, content_path: str = "article.md") -> list[str]:
    """Check title/lead/section continuity against the approved contract."""
    errors = validate_contract(article_dir)
    if errors:
        return [f"主题合同：{error}" for error in errors]
    contract = load_contract(article_dir)
    text = _text(article_dir / content_path)
    if not text.strip():
        return [f"主题一致性：缺少 {content_path}，无法检查是否跑题"]
    visible = _visible_text(text)
    anchor = contract.get("anchor") or {}
    terms = _list(anchor.get("required_terms"))
    aliases = _list(anchor.get("aliases"))
    canonical = str(contract.get("canonical_topic", "")).strip()
    all_terms = list(dict.fromkeys([canonical, *terms, *aliases]))
    drift = contract.get("drift_rules") or {}
    if bool(drift.get("require_anchor_in_title", True)) and not _hits(_first_heading(visible), all_terms):
        errors.append(f"主题一致性：一级标题必须包含主题锚点（{canonical}）")
    if bool(drift.get("require_anchor_in_lead", True)) and not _hits(_lead_body(visible), all_terms):
        errors.append(f"主题一致性：首屏/导语 1200 字内没有主题锚点（{canonical}）")
    total_hits = _hit_count(visible, all_terms)
    try:
        min_hits = int(anchor.get("minimum_total_hits", 3))
    except (TypeError, ValueError):
        min_hits = 3
    if total_hits < min_hits:
        errors.append(f"主题一致性：全文主题锚点命中 {total_hits} 次，低于最低要求 {min_hits} 次")

    sections = _sections(text)
    if sections:
        anchored = 0
        anchorless: list[str] = []
        for heading, section_text in sections:
            body = _visible_text(_section_body(section_text))
            if _hits(body, all_terms):
                anchored += 1
            else:
                anchorless.append(heading)
        coverage = anchored / len(sections)
        try:
            min_coverage = float(drift.get("min_anchor_coverage", 0.6))
        except (TypeError, ValueError):
            min_coverage = 0.6
        try:
            max_anchorless = int(drift.get("max_anchorless_sections", 1))
        except (TypeError, ValueError):
            max_anchorless = 1
        if coverage < min_coverage:
            errors.append(f"主题一致性：章节回链覆盖率 {coverage:.0%}，低于要求 {min_coverage:.0%}")
        if len(anchorless) > max_anchorless:
            errors.append("主题一致性：无主题回链章节超过上限：" + "、".join(anchorless[:8]))

        # If a declared child topic is discussed, its section must still return
        # to the parent topic. This is the specific guard that prevents a
        # supporting concept (for example KV Cache) from replacing the series
        # topic (for example vLLM).
        series = contract.get("series") or {}
        child_titles = [
            str(item.get("title", "")).strip()
            for item in (series.get("subtopics") or [])
            if isinstance(item, dict) and str(item.get("title", "")).strip()
        ]
        for heading, section_text in sections:
            body = _section_body(section_text)
            child_hits = _hits(body, child_titles)
            if child_hits and not _hits(body, all_terms):
                errors.append(f"主题一致性：章节“{heading}”只讲子题 {child_hits[0]}，没有回到主主题 {canonical}")
    return errors


def _write_report(article_dir: Path, content_path: str) -> None:
    errors = check_alignment(article_dir, content_path)
    report = {
        "schema_version": 1,
        "contract": CONTRACT_FILE,
        "content": content_path,
        "status": "passed" if not errors else "blocked",
        "errors": errors,
    }
    (article_dir / "topic-integrity.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, help="文章工作区目录")
    parser.add_argument("--content", default="article.md", help="待检查正文，默认 article.md")
    parser.add_argument("--contract-only", action="store_true", help="只检查主题合同，不检查正文")
    parser.add_argument("--write-report", action="store_true", help="写入 topic-integrity.json 审计回执")
    args = parser.parse_args()
    article_dir = Path(args.article).expanduser()
    if not article_dir.is_absolute():
        article_dir = (ROOT / article_dir).resolve()
    errors = validate_contract(article_dir) if args.contract_only else check_alignment(article_dir, args.content)
    if args.write_report:
        _write_report(article_dir, args.content)
    if errors:
        print("TOPIC INTEGRITY BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("TOPIC INTEGRITY PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
