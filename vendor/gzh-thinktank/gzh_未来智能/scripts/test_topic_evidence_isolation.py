#!/usr/bin/env python3
"""Network-free regression tests for topic/evidence isolation."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from topic_evidence_isolation import build_topic_binding, validate


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fixture(root: Path) -> None:
    (root / "evidence" / "excerpts").mkdir(parents=True)
    (root / "topic-contract.yaml").write_text(
        """schema_version: 1
status: approved
canonical_topic: vLLM 推理服务
topic_thesis: vLLM 的连续批处理与 KV Cache 优化让大模型推理更高效
reader_problem: 不知道如何把 vLLM 部署成稳定的推理服务
scope:
  in_scope: [vLLM, 推理服务]
  out_of_scope: [LangGraph]
anchor:
  required_terms: [vLLM, KV Cache]
  aliases: [推理服务]
series:
  mode: single
""",
        encoding="utf-8",
    )
    (root / "content-brief.yaml").write_text("title: vLLM 推理服务实战\nprimary_keyword: vLLM\n", encoding="utf-8")
    sources = []
    rows = []
    for index, host in enumerate(("docs.vllm.ai", "github.com", "docs.nvidia.com"), 1):
        sid = f"vllm-source-{index}"
        evidence_path = root / "evidence" / "excerpts" / f"{sid}.md"
        evidence_path.write_text(f"vLLM evidence excerpt {index}", encoding="utf-8")
        sources.append({
            "id": sid,
            "title": f"vLLM official source {index}",
            "url": f"https://{host}/vllm/{index}",
            "official_source": "official vLLM authority",
            "evidence_level": "official-docs",
            "note": "vLLM KV Cache inference serving",
        })
        rows.append({
            "source_id": sid,
            "used_in_article": True,
            "claim_ids": [f"c{index}"],
            "evidence": [{
                "kind": "excerpt",
                "path": f"evidence/excerpts/{sid}.md",
                "source_locator": f"https://{host}/vllm/{index}#excerpt",
                "sha256": _digest(evidence_path),
                "license_status": "short quotation with attribution",
            }],
        })
    (root / "sources.json").write_text(json.dumps({"sources": sources}, ensure_ascii=False), encoding="utf-8")
    plan = {
        "schema_version": 1,
        "contract": "hybrid-evidence-plan-v1",
        "topic_binding": build_topic_binding(root),
        "sources": rows,
    }
    (root / "evidence-plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="topic-evidence-isolation-") as raw:
        root = Path(raw)
        _write_fixture(root)
        errors, receipt = validate(root)
        assert not errors, errors
        assert receipt["matched_source_ids"] == sorted(receipt["used_source_ids"])

        # Simulate opening the old LangGraph evidence plan under a new vLLM
        # article: the binding and source-topic checks must both fail.
        (root / "topic-contract.yaml").write_text(
            (root / "topic-contract.yaml").read_text(encoding="utf-8").replace("vLLM 推理服务", "LangGraph Agent 编排框架").replace("vLLM 的连续批处理与 KV Cache 优化让大模型推理更高效", "LangGraph 用 StateGraph 管理 Agent 状态").replace("vLLM 部署成稳定的推理服务", "不知道如何设计可恢复的 Agent 状态").replace("[vLLM, 推理服务]", "[LangGraph, StateGraph]").replace("[vLLM, KV Cache]", "[LangGraph, StateGraph]").replace("[推理服务]", "[Agent 编排]"),
            encoding="utf-8",
        )
        (root / "content-brief.yaml").write_text("title: LangGraph Agent 编排实战\nprimary_keyword: LangGraph\n", encoding="utf-8")
        errors, _ = validate(root)
        assert any("topic_contract_sha256" in error for error in errors), errors
        assert any("未命中当前主题锚点" in error for error in errors), errors
    print("TOPIC EVIDENCE ISOLATION TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
