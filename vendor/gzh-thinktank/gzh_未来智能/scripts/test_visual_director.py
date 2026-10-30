#!/usr/bin/env python3
"""Regression tests for the evidence-first visual director contract."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_image_prompt_plan import compile_plan  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="visual-director-") as raw:
        article = Path(raw)
        (article / "imgs").mkdir()
        (article / "article.yaml").write_text("account: thinktank\ntitle: 视觉导演测试\n", encoding="utf-8")
        (article / "article.md").write_text("# 视觉导演测试\n\n## 机制\n", encoding="utf-8")
        (article / "sources.json").write_text(json.dumps({
            "claims": [{"id": "claim-1", "statement": "一个可复核主张"}],
        }, ensure_ascii=False), encoding="utf-8")
        (article / "visual-brief.yaml").write_text(
            "schema_version: 1\naccount: thinktank\ntitle: 视觉导演测试\n"
            "image_theme: thinktank-atlas\nart_direction: 纸白、墨蓝、朱砂\n"
            "approval:\n  cover_selection: pending\n"
            "cover:\n  asset: imgs/cover.png\n  ratio: 2.35:1\n"
            "body_visuals:\n"
            "  - id: body-01\n    section: 机制\n    kind: concept-architecture\n"
            "    purpose: 解释机制如何从输入走向可复核结果\n    claim_ids: [claim-1]\n",
            encoding="utf-8",
        )
        plan = compile_plan(article, "agnes", None, None)
        assert plan["schema_version"] == 2
        assert plan["generation_contract"] == "prompt-v2"
        assert plan["prompt_files"][1]["generation_mode"] == "agnes"
        assert plan["prompt_files"][1]["ratio"] == "4:3"
        assert (article / "visual-director-plan.json").is_file()
        director = json.loads((article / "visual-director-plan.json").read_text(encoding="utf-8"))
        assert director["contract"] == "visual-director-v1"
        assert director["records"][1]["viewer_job"]
        prompt = (article / "imgs/prompts/01-body-01.md").read_text(encoding="utf-8")
        for field in ("generation_mode:", "continuity_group:", "safe_area:", "claim_ids:", "fallback:"):
            assert field in prompt
    print("VISUAL DIRECTOR TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

