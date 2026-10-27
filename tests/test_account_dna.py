"""Account DNA policy tests.

Two accounts, one brand base. The DNA is what the pipeline reads and what the
one-click prompt is written from, so a drift between the two is a silent
production defect rather than a typo. These tests fail loudly.

Run: python tests/test_account_dna.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_account_dna import REQUIRED_PROMPT_FIELDS, check_account  # noqa: E402

ACCOUNTS = ROOT / "config" / "accounts"
EXPLORE = ACCOUNTS / "x-superplay-1024.json"
BUILD = ACCOUNTS / "x-superplay-future-intelligence.json"

BRAND_BASE = "#0f1117"
BRAND_ACCENT = "#38bdf8"


def _dna(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_both_accounts_declare_the_v2_schema():
    for path in (EXPLORE, BUILD):
        assert _dna(path)["schema"] == "contentops.account-dna/v2", path


def test_one_brand_base_serves_both_accounts():
    for path in (EXPLORE, BUILD):
        palette = _dna(path)["brand"]["palette"]
        assert palette["base"].lower() == BRAND_BASE, path
        assert palette["accent"].lower() == BRAND_ACCENT, path


def test_the_accent_has_exactly_one_owner():
    for path in (EXPLORE, BUILD):
        dna = _dna(path)
        assert dna["visual"]["accent"].lower() == dna["brand"]["palette"]["accent"].lower(), path


def test_composition_sums_to_one_hundred():
    for path in (EXPLORE, BUILD):
        segments = _dna(path)["visual"]["composition"]["segments"]
        assert sum(segment["pct"] for segment in segments) == 100, path


def test_explore_allows_only_cropped_evidence():
    dna = _dna(EXPLORE)
    assert dna["evidence"]["manual_recording"] == "ALLOWED_CROPPED"
    roles = {segment["role"] for segment in dna["visual"]["composition"]["segments"]}
    assert "screen_recording_evidence" in roles
    assert dna["evidence"]["required_evidence_class"] == "EXECUTED"


def test_future_intelligence_forbids_manual_recording():
    dna = _dna(BUILD)
    assert dna["evidence"]["manual_recording"] == "FORBIDDEN"
    roles = {segment["role"] for segment in dna["visual"]["composition"]["segments"]}
    assert "screen_recording_evidence" not in roles
    assert "screen_recording_evidence" in dna["evidence"]["forbidden"] or \
        "手动桌面录屏" in dna["evidence"]["forbidden"]


def test_captions_are_borderless_and_shadowless():
    for path in (EXPLORE, BUILD):
        caption = _dna(path)["visual"]["caption_style"]
        assert caption["outline"] == "none", path
        assert caption["shadow"] == "none", path
        assert "Outline=0" in caption["burn_style"], path
        assert "Shadow=0" in caption["burn_style"], path
        assert caption["highlight"].lower() == BRAND_ACCENT, path


def test_covers_keep_the_whitespace_floor_and_one_title_line():
    for path in (EXPLORE, BUILD):
        cover = _dna(path)["visual"]["cover"]
        assert cover["whitespace_min_ratio"] >= 0.3, path
        assert cover["title_lines"] == 1, path


def test_bgm_sits_at_least_18_db_under_the_voice():
    for path in (EXPLORE, BUILD):
        bgm = _dna(path)["audio"]["bgm"]
        assert bgm["max_db_below_voice"] >= 18, path


def test_both_accounts_name_the_decision_they_answer():
    explore = _dna(EXPLORE)
    build = _dna(BUILD)
    assert "值不值得用" in explore["decision_question"]
    assert "怎么才能跑起来" in build["decision_question"]


def test_explore_separates_reach_audience_from_core_audience():
    dna = _dna(EXPLORE)
    assert dna["core_audience"] == ["独立开发者", "小微企业经营者", "产品决策者"]
    assert len(dna["audience"]) > len(dna["core_audience"]), \
        "the reach list must stay wider than the core list"
    assert dna["audience_layers"]["core"], "the layers must say which one the writing targets"


def test_promise_is_the_strategy_statement_and_tagline_is_the_public_hook():
    explore = _dna(EXPLORE)
    assert explore["promise"].startswith("亲自测试 AI 新能力"), explore["promise"]
    assert "翻车和成本" in explore["tagline"]
    assert explore["promise"] != explore["tagline"]


def test_content_pillars_carry_weights_that_sum_to_one_hundred():
    pillars = _dna(EXPLORE)["content_pillars"]
    assert [p["name"] for p in pillars] == ["AI 新物种", "AI 挑战100个职业", "AI 生意实验室"]
    assert sum(p["weight_pct"] for p in pillars) == 100
    for pillar in pillars:
        assert pillar["structure"], pillar["name"]


def test_every_active_platform_has_a_declared_role():
    for path in (EXPLORE, BUILD):
        dna = _dna(path)
        roles = dna["platform_roles"]
        for platform in dna["platforms"] + dna.get("derived_platforms", []):
            assert platform in roles, (path, platform)
            assert roles[platform]["role"], (path, platform)


def test_evidence_ladder_refuses_to_jump_rungs():
    for path in (EXPLORE, BUILD):
        ladder = _dna(path)["evidence_ladder"]
        assert ladder["order"] == ["view", "like_or_collect", "comment_or_question",
                                   "dm_or_consult", "paid"]
        assert "never proves a higher one" in ladder["rule"]


def test_non_negotiable_keeps_the_publishing_and_evidence_rules():
    for path in (EXPLORE, BUILD):
        rules = _dna(path)["non_negotiable"]
        joined = "".join(rules)
        for must in ("不伪造实验", "AI 生成画面", "人工批准", "真实 URL", "付费需求"):
            assert must in joined, (path, must)


def test_business_stage_is_not_movable_by_content():
    for path in (EXPLORE, BUILD):
        business = _dna(path)["business"]
        assert business["source_of_truth"].endswith("X-SuperPlay-OPC-Blueprint")
        assert "Stage 0" in business["stage"]
        assert "may not move the OPC stage" in business["rule"]


def test_explore_declares_which_template_beat_it_defers():
    coverage = _dna(EXPLORE)["narrative"]["template_coverage"]
    assert coverage["deferred"] == ["COST_AND_LIMITS"]
    assert coverage["deferred_reason"], "a deferred beat needs a stated reason"
    template = set(_dna(EXPLORE)["narrative"]["template"])
    assert set(coverage["covered"]) | set(coverage["deferred"]) == template


def test_text_platforms_are_not_video_platforms():
    build = _dna(BUILD)
    assert set(build["platforms"]) == {"bilibili", "douyin"}, build["platforms"]
    assert set(build["text_platforms"]["platforms"]) == {"zhihu", "csdn"}
    assert not set(build["platforms"]) & set(build["text_platforms"]["platforms"])
    assert build["text_platforms"]["format"] == "TEXT_REWRITE"


def test_the_render_block_declares_a_vertical_9_by_16_canvas():
    for path in (EXPLORE, BUILD):
        render = _dna(path)["render"]
        canvas = render["canvas"]
        assert render["engine"] == "easel", path
        assert canvas["orientation"] == "vertical", path
        assert canvas["width"] * 16 == canvas["height"] * 9, path
        assert render["qc_checks"], path
        assert render["audio"]["voice_provider"], path
        assert render["fonts"]["primary"], path


def test_the_prompt_files_exist_and_name_every_output_field():
    for path in (EXPLORE, BUILD):
        dna = _dna(path)
        prompt = ROOT / dna["prompt"]
        assert prompt.is_file(), prompt
        text = prompt.read_text(encoding="utf-8")
        for field in REQUIRED_PROMPT_FIELDS:
            assert field in text, (prompt, field)
        assert dna["account"] in text, prompt
        assert BRAND_BASE.lower() in text.lower(), prompt
        assert BRAND_ACCENT.lower() in text.lower(), prompt


def test_the_prompt_carries_the_account_own_narrative_template():
    explore = (ROOT / _dna(EXPLORE)["prompt"]).read_text(encoding="utf-8")
    build = (ROOT / _dna(BUILD)["prompt"]).read_text(encoding="utf-8")
    assert "裁切" in explore and "录屏" in explore
    assert "不出现任何手动桌面录屏" in build


def test_the_dna_checker_passes_on_the_shipped_accounts():
    for path in (EXPLORE, BUILD):
        failures = check_account(_dna(path), ROOT)
        assert failures == [], failures


def test_the_variant_pipeline_reads_the_caption_style_from_the_dna():
    from build_account_variants import load_specs

    specs = load_specs()
    for slug, spec in specs.items():
        style = spec["caption_style"]
        assert style["outline"] == "none", slug
        assert "Outline=0" in style["burn_style"], slug
        assert style["highlight"].lower() == BRAND_ACCENT, slug


def main() -> int:
    failures = []
    tests = (
        test_both_accounts_declare_the_v2_schema,
        test_one_brand_base_serves_both_accounts,
        test_the_accent_has_exactly_one_owner,
        test_composition_sums_to_one_hundred,
        test_explore_allows_only_cropped_evidence,
        test_future_intelligence_forbids_manual_recording,
        test_captions_are_borderless_and_shadowless,
        test_covers_keep_the_whitespace_floor_and_one_title_line,
        test_bgm_sits_at_least_18_db_under_the_voice,
        test_both_accounts_name_the_decision_they_answer,
        test_explore_separates_reach_audience_from_core_audience,
        test_promise_is_the_strategy_statement_and_tagline_is_the_public_hook,
        test_content_pillars_carry_weights_that_sum_to_one_hundred,
        test_every_active_platform_has_a_declared_role,
        test_evidence_ladder_refuses_to_jump_rungs,
        test_non_negotiable_keeps_the_publishing_and_evidence_rules,
        test_business_stage_is_not_movable_by_content,
        test_explore_declares_which_template_beat_it_defers,
        test_text_platforms_are_not_video_platforms,
        test_the_render_block_declares_a_vertical_9_by_16_canvas,
        test_the_prompt_files_exist_and_name_every_output_field,
        test_the_prompt_carries_the_account_own_narrative_template,
        test_the_dna_checker_passes_on_the_shipped_accounts,
        test_the_variant_pipeline_reads_the_caption_style_from_the_dna,
    )
    for fn in tests:
        try:
            fn()
            print(f"[ok] {fn.__name__}")
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print("\nAll account DNA tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
