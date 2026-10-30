#!/usr/bin/env python3
"""Focused regressions for authored visual contracts and render provenance."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import generate_article_images
import visual_content_qa
import visual_qa
from render_code_block import render_html


def test_authored_contract_fields_survive_replan() -> None:
    with tempfile.TemporaryDirectory(prefix="visual-authored-") as raw:
        article = Path(raw)
        body = "正文保持不变，并绑定作者确认的主张。"
        (article / "article.yaml").write_text("title: 作者视觉合同\naccount: thinktank\n", encoding="utf-8")
        (article / "article.md").write_text(f"# 标题\n\n## 显式许可\n\n{body}\n", encoding="utf-8")
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        (article / "visual-contract.json").write_text(json.dumps({
            "contract": "visual-contract-v1",
            "units": [{
                "id": "body-01", "section_heading": "显式许可",
                "source_excerpt_sha256": digest,
                "expected_elements": ["allowed_tools", "require_approval"],
                "claim_ids": ["claim-permission"],
                "code": "def decide():\n    return 'require_approval'",
                "language": "python", "code_style": "production",
            }],
        }, ensure_ascii=False), encoding="utf-8")
        brief = visual_qa._make_brief(article)
        unit = brief["body_visuals"][0]
        assert unit["expected_elements"] == ["allowed_tools", "require_approval"]
        assert unit["claim_ids"] == ["claim-permission"]
        assert unit["code"].startswith("def decide")


def test_code_card_has_real_structure() -> None:
    html = render_html("def decide():\n    return True", "thinktank", "显式许可", "code", "python")
    assert 'data-role="code"' in html
    assert visual_content_qa._has_code_structure(html)
    css_only = '<style>.fake{font-family:"Consolas",monospace}</style><div>显式许可</div>'
    assert not visual_content_qa._has_code_structure(css_only)


def test_taste_receipt_accepts_nested_human_status() -> None:
    # visual_taste_review.py stores human_review_status under rubric; the
    # machine QA summary must not report a false pending state.
    assert visual_qa._taste_review_passed({
        "status": "passed",
        "rubric": {"human_review_status": "passed"},
    })
    assert not visual_qa._taste_review_passed({
        "status": "passed",
        "rubric": {"human_review_status": "pending"},
    })


def test_cover_overlay_is_not_flagged_as_agnes_pseudotext() -> None:
    assert visual_qa._intentional_cover_overlay(
        "imgs/cover.png",
        {"cover_overlay_source": "imgs/diagram-sources/cover-overlay.svg", "method": "agnes-text-to-image + deterministic-English-overlay-chrome"},
    )
    assert not visual_qa._intentional_cover_overlay(
        "imgs/section-01.png",
        {"cover_overlay_source": "imgs/diagram-sources/cover-overlay.svg", "method": "agnes-text-to-image"},
    )


def test_authored_asset_mapping_rejects_cross_section_swap() -> None:
    with tempfile.TemporaryDirectory(prefix="visual-mapping-") as raw:
        article = Path(raw)
        (article / "article.md").write_text(
            "# 标题\n\n## 五、实践\n\n![图](imgs/section-05.png)\n\n## 七、结语\n\n![图](imgs/section-04.png)\n",
            encoding="utf-8",
        )
        errors = visual_qa._authored_asset_mapping_errors(article, [
            {"section_heading": "五、实践", "asset": "imgs/section-04.png"},
            {"section_heading": "七、结语", "asset": "imgs/section-05.png"},
        ])
        assert len(errors) == 2


def test_generation_writes_visual_manifest() -> None:
    with tempfile.TemporaryDirectory(prefix="visual-manifest-") as raw:
        article = Path(raw)
        (article / "imgs" / "diagram-sources").mkdir(parents=True)
        for relative, content in {
            "visual-brief.yaml": "status: approved\n",
            "visual-contract.json": "{}\n",
            "image-generation-plan.json": "{}\n",
            "imgs/prompts/01.md": "prompt\n",
            "imgs/section-01.png": "png-bytes",
            "imgs/diagram-sources/body-01.svg": "<svg/>\n",
        }.items():
            path = article / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        generate_article_images.write_visual_run_manifest(article, [{
            "path": "imgs/prompts/01.md",
            "output": "imgs/section-01.png",
            "diagram_source": "imgs/diagram-sources/body-01.svg",
        }])
        entries = [json.loads(line) for line in (article / "visual-run-manifest.jsonl").read_text(encoding="utf-8").splitlines()]
        assert entries[-1]["stage"] == "visual-render"
        assert entries[-1]["status"] == "passed"
        assert all(item["exists"] and item["sha256"] for item in entries[-1]["outputs"])


def main() -> int:
    test_authored_contract_fields_survive_replan()
    test_code_card_has_real_structure()
    test_taste_receipt_accepts_nested_human_status()
    test_cover_overlay_is_not_flagged_as_agnes_pseudotext()
    test_authored_asset_mapping_rejects_cross_section_swap()
    test_generation_writes_visual_manifest()
    print("VISUAL WORKFLOW REGRESSION TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
