#!/usr/bin/env python3
"""Regression tests for the research-source relevance gate."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path

import source_review


def _workspace() -> Path:
    root = Path(tempfile.mkdtemp(prefix="source-review-"))
    sources = {
        "schema_version": 1,
        "sources": [
            {
                "id": "official-a",
                "title": "Official mechanism guide",
                "url": "https://github.com/example/project/blob/main/guide.md",
                "kind": "external",
                "evidence_level": "official-repo",
                "version_scope": "main captured",
            },
            {
                "id": "background-b",
                "title": "Background article",
                "url": "https://docs.anthropic.com/en/docs/example",
                "kind": "external",
                "evidence_level": "official-docs",
                "version_scope": "current docs",
            },
        ],
        "claims": [
            {"id": "claim-a", "statement": "A supported mechanism", "source_ids": ["official-a"]},
        ],
    }
    (root / "sources.json").write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")
    (root / "source-snapshots").mkdir()
    snapshots = {}
    for source_id in ("official-a", "background-b"):
        path = root / "source-snapshots" / f"{source_id}.raw"
        path.write_text("The source directly describes the mechanism, boundary, and limitation relevant to the current topic.\n", encoding="utf-8")
        snapshots[source_id] = {"id": source_id, "snapshot": f"source-snapshots/{source_id}.raw", "snapshot_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (root / "source-verification.json").write_text(json.dumps({"sources": list(snapshots.values())}, ensure_ascii=False), encoding="utf-8")
    plan = {
        "topic_binding": {"topic_fingerprint": "topic-1"},
        "sources": [
            {"source_id": "official-a", "used_in_article": True, "claim_ids": ["claim-a"]},
            {"source_id": "background-b", "used_in_article": False, "claim_ids": []},
        ],
    }
    (root / "evidence-plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return root


def _record(source_id: str, verdict: str, claim_ids: list[str], *, method: str = "fulltext") -> dict:
    excerpt = "The source directly describes the mechanism, boundary, and limitation relevant to the current topic."
    return {
        "source_id": source_id,
        "source_title": source_id,
        "source_type": "official-docs",
        "review_verdict": verdict,
        "topic_match": "direct" if verdict != "excluded" else "none",
        "extraction": {
            "method": method,
            "locator": "guide.md#mechanism",
            "source_path": f"source-snapshots/{source_id}.raw",
            "excerpt": excerpt,
            "excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
            "captured_at": "2026-08-25T00:00:00+00:00",
        },
        "extracted_summary": "The source explains the mechanism and its operating boundary for this topic, with enough detail to map one claim.",
        "support_scope": "Supports the mechanism claim only; it does not establish production safety or universal applicability.",
        "claim_ids": claim_ids,
        "limitations": "The source is scoped to its documented implementation and must not be generalized beyond the stated version or product.",
        "review_rationale": "The extracted passage was compared with the topic contract and claim wording before inclusion.",
        "exclusion_reason": "The source is background-only and does not directly support a claim used in this article.",
    }


def _write_review(root: Path, records: list[dict]) -> None:
    payload = {
        "schema_version": 1,
        "contract": source_review.CONTRACT,
        "status": "passed",
        "review_method": "structured-source-scope-review-v1",
        "reviewer_type": "agent",
        "reviewer": "test-agent",
        "reviewed_at": "2026-08-25T00:00:00+00:00",
        "sources_digest": source_review._sha256(root / "sources.json"),
        "topic_fingerprint": "topic-1",
        "semantic_truth_boundary": "scope only",
        "sources": records,
    }
    (root / "source-review.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_valid_review_passes() -> None:
    root = _workspace()
    _write_review(root, [_record("official-a", "included", ["claim-a"]), _record("background-b", "excluded", [])])
    assert source_review.validate(root) == []


def test_used_source_cannot_be_excluded() -> None:
    root = _workspace()
    _write_review(root, [_record("official-a", "excluded", []), _record("background-b", "excluded", [])])
    errors = source_review.validate(root)
    assert any("正文采用来源 official-a" in error for error in errors)
    assert any("claim claim-a 引用了被来源审查排除" in error for error in errors)


def test_metadata_only_cannot_be_included() -> None:
    root = _workspace()
    _write_review(root, [_record("official-a", "included", ["claim-a"], method="metadata"), _record("background-b", "excluded", [])])
    assert any("只有 metadata" in error for error in source_review.validate(root))


def test_stale_sources_digest_blocks() -> None:
    root = _workspace()
    _write_review(root, [_record("official-a", "included", ["claim-a"]), _record("background-b", "excluded", [])])
    sources = json.loads((root / "sources.json").read_text(encoding="utf-8"))
    sources["sources"][0]["title"] = "changed"
    (root / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    assert any("sources_digest" in error for error in source_review.validate(root))


def test_self_hashed_fabricated_excerpt_blocks() -> None:
    root = _workspace()
    records = [_record("official-a", "included", ["claim-a"]), _record("background-b", "excluded", [])]
    fabricated = "A fabricated summary that was never present in the verified source snapshot."
    records[0]["extraction"]["excerpt"] = fabricated
    records[0]["extraction"]["excerpt_sha256"] = hashlib.sha256(fabricated.encode("utf-8")).hexdigest()
    _write_review(root, records)
    assert any("不是 source-verification 快照原文子串" in error for error in source_review.validate(root))


if __name__ == "__main__":
    test_valid_review_passes()
    test_used_source_cannot_be_excluded()
    test_metadata_only_cannot_be_included()
    test_stale_sources_digest_blocks()
    test_self_hashed_fabricated_excerpt_blocks()
    print("SOURCE REVIEW TESTS PASSED")
