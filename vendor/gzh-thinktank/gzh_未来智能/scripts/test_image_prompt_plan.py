#!/usr/bin/env python3
"""Offline regression tests for the evidence-first Agnes prompt contract."""

from __future__ import annotations

import json
import hashlib
import tempfile
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_image_prompt_plan import compile_plan  # noqa: E402
from account_context import ACCOUNT_ID  # noqa: E402


def _fixture(raw: str, account: str = ACCOUNT_ID, body_visuals: list[dict] | None = None, body_words: int = 2000) -> Path:
    article = Path(raw)
    (article / "imgs").mkdir()
    (article / "article.yaml").write_text(
        f"account: {account}\ntitle: Agent 原理拆解\n", encoding="utf-8"
    )
    # Generate a CJK-heavy body deterministically.
    cjk = "人工智能大语言模型注意力机制架构流程图"
    cycles = max(1, body_words // len(cjk))
    (article / "article.md").write_text(
        "# Agent 原理拆解\n\n" + "\n\n".join(
            [f"## {cjk[:4]}"] + [cjk * (i % 3 + 1) for i in range(cycles)]
        ) + "\n",
        encoding="utf-8",
    )
    visuals = body_visuals or [
        {"id": "body-01", "section": "架构", "kind": "architecture", "purpose": "解释组件之间的调用关系", "asset": "imgs/section-01.png"},
    ]
    lines = [
        "schema_version: 1",
        f"account: {account}",
        "title: Agent 原理拆解",
        "art_direction: 纸白、墨蓝、朱砂锚点",
        "cover:\n  asset: imgs/cover.png",
        "body_visuals:",
    ]
    for v in visuals:
        lines.append(f"  - id: {v['id']}")
        for k, val in v.items():
            if k == "id":
                continue
            lines.append(f"    {k}: {val}")
    (article / "visual-brief.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return article


def test_dynamic_quota_longer_allows_more_visuals():
    with tempfile.TemporaryDirectory(prefix="image-plan-") as raw:
        # account body_visual_count clamps: sentinel 4 / thinktank 6 -> cover + body
        expected_body = 4 if ACCOUNT_ID == "sentinel" else 6
        article = _fixture(raw, account=ACCOUNT_ID, body_words=4800, body_visuals=[
            {"id": f"body-{i:02d}", "section": f"章节{i}", "kind": "architecture", "purpose": "说明", "asset": f"imgs/section-{i:02d}.png"}
            for i in range(1, expected_body + 1)
        ])
        plan = compile_plan(article, "agnes", None, None)
        assert len(plan["prompt_files"]) == expected_body + 1


def test_dynamic_quota_gate_fires_when_too_many():
    with tempfile.TemporaryDirectory(prefix="image-plan-") as raw:
        article = _fixture(raw, account=ACCOUNT_ID, body_words=800, body_visuals=[
            {"id": f"body-{i:02d}", "section": f"章节{i}", "kind": "signal-card", "purpose": "提示", "asset": f"imgs/section-{i:02d}.png"}
            for i in range(1, 7)
        ])
        try:
            compile_plan(article, "agnes", None, None)
            raise AssertionError("expected count gate to fail")
        except SystemExit as exc:
            assert "插图数量超限" in str(exc.code) or "动态配额" in str(exc.code)


def test_mermaid_passthrough_to_visual_contract():
    """compile_plan 必须把简报中的 mermaid/diagram 图源透传进 visual-contract.json。

    回归保护：此前 compile_plan 重建合同时丢失 unit.mermaid，导致
    beautiful-mermaid 后端退化为稀疏自动连线图，glyph 密度 <12 阻断 illustrated。
    """
    mermaid_src = "graph TD; A[Self-Attention] --> B[Multi-Head]"
    with tempfile.TemporaryDirectory(prefix="image-plan-") as raw:
        article = _fixture(raw, body_visuals=[
            {"id": "body-01", "section": "架构", "kind": "architecture",
             "purpose": "解释组件之间的调用关系", "asset": "imgs/section-01.png",
             "mermaid": mermaid_src, "diagram": "custom-diagram-src"},
        ])
        plan = compile_plan(article, "agnes", None, None)
        assert len(plan["prompt_files"]) == 2
        record = next(r for r in plan["prompt_files"] if r["id"] == "body-01")
        assert record.get("mermaid") == mermaid_src
        assert record.get("diagram") == "custom-diagram-src"
        contract = json.loads((article / "visual-contract.json").read_text(encoding="utf-8"))
        unit = next(u for u in contract["units"] if u["id"] == "body-01")
        assert unit.get("mermaid") == mermaid_src, "contract unit 必须携带 mermaid 图源"
        assert unit.get("diagram") == "custom-diagram-src"


def test_mermaid_absent_stays_empty_in_contract():
    """未提供 mermaid 时，合同单元 mermaid/diagram 应为空串，渲染器走自动布线。"""
    with tempfile.TemporaryDirectory(prefix="image-plan-") as raw:
        article = _fixture(raw, body_visuals=[
            {"id": "body-01", "section": "架构", "kind": "architecture",
             "purpose": "解释组件之间的调用关系", "asset": "imgs/section-01.png"},
        ])
        compile_plan(article, "agnes", None, None)
        contract = json.loads((article / "visual-contract.json").read_text(encoding="utf-8"))
        unit = next(u for u in contract["units"] if u["id"] == "body-01")
        assert unit.get("mermaid", "") == ""
        assert unit.get("diagram", "") == ""


def test_language_policy_is_english_cover_only():
    """封面英文是强制信息层，正文图不能被错误地全盘英文化。"""
    with tempfile.TemporaryDirectory(prefix="image-plan-") as raw:
        article = _fixture(raw)
        plan = compile_plan(article, "agnes", None, None)
        cover = next(record for record in plan["prompt_files"] if record["id"] == "cover")
        body = next(record for record in plan["prompt_files"] if record["id"] == "body-01")
        assert cover["language_policy"]["display_language"] == "english-required"
        assert body["language_policy"]["display_language"] == "zh-CN-first"
        body_prompt = (article / body["path"]).read_text(encoding="utf-8")
        assert "正文图文字以中文为主" in body_prompt


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="image-plan-") as raw:
        article = _fixture(raw)
        plan = compile_plan(article, "agnes", None, None)
        assert plan["model"] == "agnes-image-2.1-flash"
        assert plan["generation_policy"]["diagrams_prefer_deterministic_renderer"] is True
        assert len(plan["prompt_files"]) == 2
        prompt_path = article / plan["prompt_files"][1]["path"]
        prompt = prompt_path.read_text(encoding="utf-8")
        # RC1: prompt body must describe the picture only.
        assert "Subject:" in prompt
        assert "Negative:" in prompt
        # Operational metadata must stay in frontmatter, never in the body.
        assert "Visual Owner:" not in prompt
        assert "Generation Mode:" not in prompt
        assert "Fallback:" not in prompt
        assert "Evidence Claim IDs:" not in prompt
        saved = json.loads((article / "image-generation-plan.json").read_text(encoding="utf-8"))
        assert saved["prompt_files"][1]["sha256"] == hashlib.sha256(prompt_path.read_bytes()).hexdigest()
        assert saved["prompt_files"][1]["section"] == "架构"
        assert saved["prompt_files"][1]["kind"] == "architecture"

    test_dynamic_quota_longer_allows_more_visuals()
    test_dynamic_quota_gate_fires_when_too_many()
    test_mermaid_passthrough_to_visual_contract()
    test_mermaid_absent_stays_empty_in_contract()
    test_language_policy_is_english_cover_only()
    print("IMAGE PROMPT PLAN TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
