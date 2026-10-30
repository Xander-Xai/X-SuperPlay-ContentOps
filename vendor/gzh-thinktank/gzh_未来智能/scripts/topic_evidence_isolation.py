#!/usr/bin/env python3
"""Bind a hybrid-evidence plan to the article's current topic.

The normal source ledger answers ``where did this claim come from?``.  This
contract answers the equally important workflow question ``does that source
belong to this article?``.  A new article gets a deterministic topic binding;
changing the topic later without rebuilding the evidence plan therefore fails
the research gate instead of silently carrying LangGraph evidence into a vLLM
article (or vice versa).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from topic_integrity import _load_yaml, load_contract


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "topic-evidence-isolation-v1"
BINDING_CONTRACT = "topic-evidence-binding-v1"
VERSION = "1.0.0"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _article_title(article: Path) -> str:
    for name in ("article.yaml", "content-brief.yaml"):
        value = _load_yaml(article / name)
        title = str(value.get("title", "")).strip()
        if title:
            return title
    text = (article / "article.md").read_text(encoding="utf-8", errors="replace") if (article / "article.md").is_file() else ""
    match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
    return match.group(1).strip() if match else ""


def _topic_payload(article: Path) -> dict[str, Any]:
    contract = load_contract(article)
    scope = contract.get("scope") if isinstance(contract.get("scope"), dict) else {}
    anchor = contract.get("anchor") if isinstance(contract.get("anchor"), dict) else {}
    series = contract.get("series") if isinstance(contract.get("series"), dict) else {}
    brief = _load_yaml(article / "content-brief.yaml")
    return {
        "canonical_topic": str(contract.get("canonical_topic", "")).strip(),
        "topic_thesis": str(contract.get("topic_thesis", "")).strip(),
        "reader_problem": str(contract.get("reader_problem", "")).strip(),
        "scope_in": _items(scope.get("in_scope")),
        "scope_out": _items(scope.get("out_of_scope")),
        "required_terms": _items(anchor.get("required_terms")),
        "aliases": _items(anchor.get("aliases")),
        "series_mode": str(series.get("mode", "")).strip(),
        "title": _article_title(article),
        "primary_keyword": str(brief.get("primary_keyword", "")).strip(),
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def build_topic_binding(article: Path) -> dict[str, Any]:
    payload = _topic_payload(article)
    terms: list[str] = []
    for value in (
        payload.get("canonical_topic"),
        payload.get("title"),
        payload.get("primary_keyword"),
        *payload.get("required_terms", []),
        *payload.get("aliases", []),
    ):
        text = str(value or "").strip()
        if text and _norm(text) not in {_norm(item) for item in terms}:
            terms.append(text)
    topic_contract_sha256 = _sha(payload)
    fingerprint = _sha({"canonical_topic": payload.get("canonical_topic", ""), "terms": terms})
    return {
        "contract": BINDING_CONTRACT,
        "topic_contract_sha256": topic_contract_sha256,
        "topic_fingerprint": fingerprint,
        "canonical_topic": payload.get("canonical_topic", ""),
        "topic_terms": terms,
        "bound_at": now(),
    }


def _source_map(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id", "")).strip(): item
        for item in document.get("sources", [])
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }


def _source_text(source: dict[str, Any]) -> str:
    values = [
        source.get("id", ""), source.get("title", ""), source.get("url", ""),
        source.get("official_source", ""), source.get("note", ""),
        source.get("version_scope", ""), source.get("kind", ""),
    ]
    return " ".join(str(value or "") for value in values)


def _evidence_paths(article: Path, plan: dict[str, Any]) -> tuple[set[str], list[str]]:
    referenced: set[str] = set()
    errors: list[str] = []
    for row in plan.get("sources", []) if isinstance(plan.get("sources"), list) else []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("source_id", "")).strip()
        for unit in row.get("evidence", []) if isinstance(row.get("evidence"), list) else []:
            if not isinstance(unit, dict):
                continue
            raw = str(unit.get("path", "")).strip().replace("\\", "/")
            if not raw:
                continue
            candidate = (article / raw).resolve()
            try:
                candidate.relative_to(article.resolve())
            except ValueError:
                errors.append(f"来源 {sid} 的证据路径越界：{raw}")
                continue
            if not candidate.is_file():
                errors.append(f"来源 {sid} 的证据文件不存在：{raw}")
            referenced.add(raw)
    evidence_root = article / "evidence"
    if evidence_root.is_dir():
        for path in evidence_root.rglob("*"):
            if not path.is_file() or ".chrome-profile" in path.parts:
                continue
            rel = path.relative_to(article).as_posix()
            if rel not in referenced:
                errors.append(f"证据目录存在未登记文件（疑似旧主题残留）：{rel}")
    return referenced, errors


def validate(article: Path, plan: dict[str, Any] | None = None) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    topic_contract_path = article / "topic-contract.yaml"
    contract = load_contract(article)
    if not topic_contract_path.is_file() or not contract:
        errors.append("缺少有效 topic-contract.yaml；证据不能在无主题合同的情况下复用")
    current = build_topic_binding(article)
    if plan is None:
        plan = _json(article / "evidence-plan.json")
    if not isinstance(plan, dict):
        errors.append("缺少 evidence-plan.json；无法校验主题绑定")
        plan = {}
    binding = plan.get("topic_binding")
    if not isinstance(binding, dict):
        errors.append("evidence-plan.json 缺少 topic_binding；请运行 source_evidence.py bind")
        binding = {}
    for key in ("contract", "topic_contract_sha256", "topic_fingerprint", "canonical_topic"):
        if str(binding.get(key, "")).strip() != str(current.get(key, "")).strip():
            errors.append(f"主题绑定 {key} 与当前 topic-contract 不一致；必须重新初始化证据计划")
    bound_terms = {_norm(item) for item in binding.get("topic_terms", []) if str(item).strip()} if isinstance(binding.get("topic_terms"), list) else set()
    current_terms = {_norm(item) for item in current.get("topic_terms", []) if str(item).strip()}
    if bound_terms != current_terms:
        errors.append("主题绑定 topic_terms 与当前主题锚点不一致；禁止沿用旧主题证据")

    sources_doc = _json(article / "sources.json")
    source_map = _source_map(sources_doc) if isinstance(sources_doc, dict) else {}
    rows = plan.get("sources") if isinstance(plan.get("sources"), list) else []
    plan_ids = {str(row.get("source_id", "")).strip() for row in rows if isinstance(row, dict) and str(row.get("source_id", "")).strip()}
    source_ids = set(source_map)
    if plan_ids != source_ids:
        missing = sorted(source_ids - plan_ids)
        unknown = sorted(plan_ids - source_ids)
        if missing:
            errors.append(f"evidence-plan.json 漏记 sources.json 来源：{', '.join(missing)}")
        if unknown:
            errors.append(f"evidence-plan.json 含不存在来源：{', '.join(unknown)}")

    matched: list[str] = []
    used: list[str] = []
    payload = _topic_payload(article)
    strong_terms = [
        str(payload.get("canonical_topic", "")).strip(),
        str(payload.get("primary_keyword", "")).strip(),
        *_items(payload.get("required_terms")),
    ]
    for row in rows:
        if not isinstance(row, dict) or not row.get("used_in_article"):
            continue
        sid = str(row.get("source_id", "")).strip()
        source = source_map.get(sid)
        if not source:
            continue
        used.append(sid)
        haystack = _norm(_source_text(source))
        # Title/alias words such as “Agent” or “部署” are too broad to prove
        # topic ownership.  A direct source must hit the canonical topic,
        # primary keyword, or a required anchor term; aliases remain useful
        # for human context but cannot alone rescue a copied evidence pack.
        hits = [term for term in strong_terms if _norm(term) and _norm(term) in haystack]
        if hits:
            matched.append(sid)
            continue
        relevance = str(row.get("topic_relevance", "")).strip().lower()
        reason = str(row.get("topic_relevance_reason", "")).strip()
        if relevance != "generic-support" or not reason:
            errors.append(f"正文来源 {sid} 未命中当前主题锚点；若确属通用支撑，必须声明 topic_relevance=generic-support 及理由")

    if not used:
        errors.append("证据计划没有正文使用的来源")
    if used and not matched:
        errors.append("正文来源没有任何一个命中当前主题锚点；疑似复制了其他主题的证据包")

    _, evidence_errors = _evidence_paths(article, plan)
    errors.extend(evidence_errors)
    snapshots = article / "source-snapshots"
    if snapshots.is_dir():
        for path in snapshots.glob("*.raw"):
            snapshot_id = path.stem.strip()
            if snapshot_id not in source_ids:
                errors.append(f"source-snapshots/ 存在未登记来源快照（疑似旧主题残留）：{path.name}")
    data = {
        "schema_version": 1,
        "contract": CONTRACT,
        "verifier": "topic_evidence_isolation.py",
        "verifier_version": VERSION,
        "status": "passed" if not errors else "blocked",
        "audited_at": now(),
        "topic_binding": current,
        "plan_topic_binding": binding,
        "source_ids": sorted(source_ids),
        "used_source_ids": sorted(used),
        "matched_source_ids": sorted(matched),
        "errors": errors,
    }
    return errors, data


def audit(article: Path) -> int:
    errors, receipt = validate(article)
    _write_json(article / "topic-evidence-isolation.json", receipt)
    if errors:
        print("TOPIC EVIDENCE ISOLATION BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"TOPIC EVIDENCE ISOLATION PASSED: {len(receipt['matched_source_ids'])} topic-matched sources")
    return 0


def bind(article: Path) -> int:
    path = article / "evidence-plan.json"
    plan = _json(path)
    if not isinstance(plan, dict):
        print("TOPIC EVIDENCE BIND BLOCKED: 缺少 evidence-plan.json")
        return 1
    plan["topic_binding"] = build_topic_binding(article)
    plan["status"] = "draft"
    _write_json(path, plan)
    print(f"TOPIC EVIDENCE BOUND: {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("audit", "bind"):
        item = sub.add_parser(command)
        item.add_argument("--article", required=True, type=Path)
    args = parser.parse_args()
    article = args.article.expanduser()
    if not article.is_absolute():
        article = ROOT / article
    article = article.resolve()
    return audit(article) if args.command == "audit" else bind(article)


if __name__ == "__main__":
    raise SystemExit(main())
