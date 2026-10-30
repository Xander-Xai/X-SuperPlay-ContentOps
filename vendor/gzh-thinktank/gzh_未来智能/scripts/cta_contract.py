#!/usr/bin/env python3
"""Build and validate a topic-bound CTA contract for a thinktank article.

The split workflow already validates CTA text in ``workflow_gate.py``.  This
small contract makes the source of the CTA explicit and replayable: a profile
may provide examples, but the article must carry a non-empty, topic-bound
reply keyword and lead magnet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from workspace_paths import resolve_article_workspace  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def _yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return value if isinstance(value, dict) else {}
    except (ImportError, OSError, ValueError):
        return {}


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _topic(article_dir: Path) -> str:
    contract = _yaml(article_dir / "topic-contract.yaml")
    topic = str(contract.get("canonical_topic") or "").strip()
    if topic:
        return topic
    article = _yaml(article_dir / "article.yaml")
    return str(article.get("title") or article_dir.name).strip()


def _fingerprint(topic: str) -> str:
    normalized = re.sub(r"\s+", " ", topic.strip()).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build(article_dir: Path) -> dict[str, Any]:
    brief = _yaml(article_dir / "content-brief.yaml")
    topic = _topic(article_dir)
    return {
        "schema_version": 1,
        "contract": "cta-contract-v1",
        "mode": "topic_bound",
        "account": str(brief.get("account") or "thinktank").strip().lower(),
        "topic": topic,
        "topic_fingerprint": _fingerprint(topic),
        "reply_keyword": str(brief.get("reply_keyword") or "").strip(),
        "lead_magnet": str(brief.get("lead_magnet") or "").strip(),
        "primary_cta": str(brief.get("primary_cta") or brief.get("cta") or "").strip(),
        "secondary_cta": str(brief.get("secondary_cta") or "").strip(),
        "rules": {
            "reply_keyword_required": True,
            "lead_magnet_required": True,
            "primary_cta_exactly_once": True,
            "primary_cta_topic_bound": True,
        },
    }


def validate(article_dir: Path) -> list[str]:
    path = article_dir / "cta-contract.json"
    if not path.is_file():
        return []  # Backward-compatible for pre-contract workspaces.
    contract = _json(path)
    errors: list[str] = []
    if contract.get("contract") != "cta-contract-v1":
        errors.append("cta-contract.json contract 必须是 cta-contract-v1")
    if str(contract.get("mode") or "").strip() != "topic_bound":
        errors.append("cta-contract.json mode 必须是 topic_bound")
    expected = build(article_dir)
    for key in ("reply_keyword", "lead_magnet", "primary_cta", "secondary_cta"):
        if str(contract.get(key) or "").strip() != str(expected.get(key) or "").strip():
            errors.append(f"cta-contract.json 的 {key} 与 content-brief.yaml 不一致")
    if not str(expected.get("reply_keyword") or "").strip():
        errors.append("CTA 合同要求 reply_keyword 非空")
    if not str(expected.get("lead_magnet") or "").strip():
        errors.append("CTA 合同要求 lead_magnet 非空")
    if str(contract.get("topic_fingerprint") or "").strip() != str(expected.get("topic_fingerprint") or "").strip():
        errors.append("cta-contract.json topic_fingerprint 与当前主题不一致")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="write cta-contract.json")
    mode.add_argument("--check", action="store_true", help="validate cta-contract.json")
    args = parser.parse_args()
    article = resolve_article_workspace(args.article, allow_test_fixture=True)
    if not article.is_dir():
        print(f"CTA CONTRACT BLOCKED: article directory not found: {article}")
        return 1
    if args.write:
        (article / "cta-contract.json").write_text(
            json.dumps(build(article), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"CTA CONTRACT WRITTEN: {article / 'cta-contract.json'}")
    errors = validate(article)
    if errors:
        print("CTA CONTRACT BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("CTA CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
