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
sys.path.insert(0, str(ROOT / "src"))

from check_account_dna import (  # noqa: E402
    REQUIRED_PROMPT_FIELDS,
    _catalog_roots,
    check_account,
)
from contentops.media.claim_coverage import (  # noqa: E402
    EVIDENCE_MODES,
    composition_policy_errors,
)

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


CATALOG_ABSENT = "no skill catalog root is present"


def _clone(path: Path) -> dict:
    """A mutable deep copy, for the mutation tests below."""
    return json.loads(json.dumps(_dna(path)))


def test_every_account_declares_the_evidence_mode_that_gates_it():
    """The field both the plan and the QC read; undeclared, each invented one."""
    for path in (EXPLORE, BUILD):
        assert _dna(path)["evidence"]["mode"] in EVIDENCE_MODES, path


def test_the_proof_account_is_gated_by_the_real_source_floor():
    dna = _dna(EXPLORE)
    assert dna["evidence"]["mode"] == "EVIDENCE_LED"
    assert dna["evidence"]["manual_recording"] == "ALLOWED_CROPPED"
    assert "real_source_ratio_min_70" in dna["render"]["qc_checks"]
    problems = composition_policy_errors(
        "EVIDENCE_LED", dna["visual"]["composition"]["segments"])
    assert problems == [], problems


def test_the_explanatory_account_is_gated_by_its_own_composition():
    dna = _dna(BUILD)
    assert dna["evidence"]["mode"] == "EXPLANATORY"
    assert dna["evidence"]["manual_recording"] == "FORBIDDEN"
    assert "real_source_ratio_min_70" not in dna["render"]["qc_checks"]
    assert "composition_ratio" in dna["render"]["qc_checks"]
    # The same mix the proof account above must reach 70% with is legal here,
    # because nothing in an explanatory cut is claimed to be a recording.
    assert composition_policy_errors(
        "EXPLANATORY", dna["visual"]["composition"]["segments"]) == []


def test_an_undeclared_evidence_mode_fails():
    dna = _clone(EXPLORE)
    dna["evidence"].pop("mode")
    failures = check_account(dna, ROOT)
    assert any("evidence.mode" in failure for failure in failures), failures


def test_a_proven_account_may_not_declare_a_mix_it_cannot_reach():
    """The pair that shipped: 70% vector animation under a 70% real-source floor."""
    dna = _clone(EXPLORE)
    dna["visual"]["composition"]["segments"] = [
        {"role": "vector_animation", "pct": 70},
        {"role": "code_snapshot", "pct": 25},
        {"role": "metric_chart", "pct": 5},
    ]
    failures = check_account(dna, ROOT)
    assert any("tops out at 30%" in failure for failure in failures), failures


def test_an_explanatory_account_may_not_keep_the_floor():
    dna = _clone(BUILD)
    dna["render"]["qc_checks"].append("real_source_ratio_min_70")
    failures = check_account(dna, ROOT)
    assert any("still demands it" in failure for failure in failures), failures


def test_an_explanatory_account_may_not_plan_a_recording():
    dna = _clone(BUILD)
    dna["evidence"]["manual_recording"] = "ALLOWED_CROPPED"
    dna["visual"]["composition"]["segments"] = [
        {"role": "screen_recording_evidence", "pct": 60},
        {"role": "vector_animation", "pct": 40},
    ]
    failures = check_account(dna, ROOT)
    assert any("EXPLANATORY plans no recording" in failure for failure in failures), failures
SHARED_STORE_ABSENT = "the shared skill store"

#: Warnings that name a host-local resource this checkout does not have. Both
#: are expected on a CI runner, where the Easel runtime and ~/.agents/skills are
#: absent by design. Anything else in the warning channel is unexpected.
HOST_LOCAL_WARNINGS = (CATALOG_ABSENT, SHARED_STORE_ABSENT)


def test_the_dna_checker_passes_on_the_shipped_accounts():
    for path in (EXPLORE, BUILD):
        warnings: list = []
        failures = check_account(_dna(path), ROOT, warnings)
        assert failures == [], failures
        # A clean checkout has no catalog (both roots are gitignored) and no
        # shared store (it lives in the user's home), so the membership half
        # reports that it could not run. That is the expected state in CI, not
        # a defect in the shipped DNA.
        unexpected = [w for w in warnings
                      if not any(marker in w for marker in HOST_LOCAL_WARNINGS)]
        assert unexpected == [], unexpected


def _mutated(dna: dict, step: str, **changes) -> dict:
    clone = json.loads(json.dumps(dna))
    entry = next(item for item in clone["skill_route"] if item["step"] == step)
    entry.update(changes)
    return clone


def test_a_route_entry_naming_an_unknown_skill_fails():
    """The gap this closes: the DNA read as sound while pointing at nothing."""
    if not _catalog_roots():
        print("catalog absent on this checkout; skipping membership assertion")
        return
    dna = _mutated(_dna(EXPLORE), "script", skill="video-script-that-does-not-exist")
    warnings: list = []
    failures = check_account(dna, ROOT, warnings)
    assert len(failures) == 1, failures
    assert "'script'" in failures[0], failures[0]
    assert "video-script-that-does-not-exist" in failures[0], failures[0]
    assert "not present under any catalog root" in failures[0], failures[0]
    assert any("could not be determined" in w for w in warnings), warnings
    assert all(w.startswith("[x-superplay-1024]") for w in warnings), \
        "a warning must name the account it belongs to"


def test_a_repo_relative_script_must_exist():
    dna = _mutated(_dna(EXPLORE), "qc", script="scripts/no_such_script.py")
    failures = check_account(dna, ROOT)
    assert len(failures) == 1, failures
    assert "scripts/no_such_script.py" in failures[0], failures[0]
    assert "repository root" in failures[0], failures[0]


def test_an_undeclared_path_base_is_not_silently_assumed():
    """Dropping qc's path_base must fail loudly instead of falling back."""
    if not _catalog_roots():
        # With no catalog every entry skips membership, so the undeclared base
        # has nothing left to be resolved against and cannot be demonstrated.
        print("catalog absent on this checkout; skipping base-resolution assertion")
        return
    dna = _mutated(_dna(EXPLORE), "qc")
    entry = next(item for item in dna["skill_route"] if item["step"] == "qc")
    entry.pop("path_base")
    warnings: list = []
    failures = check_account(dna, ROOT, warnings)
    assert failures, "an undeclared repo entry must not pass as catalog-relative"
    assert any("could not be determined" in w for w in warnings), warnings


def test_the_route_declares_repo_only_where_it_must():
    # Steps whose owner is a repository script, not a catalog skill. ``captions``
    # belongs here because the actual burn lives in scripts/assemble_easel.py;
    # the upstream auto-subtitle skill is never called by this pipeline.
    repo_expected = {"captions", "qc"}
    shared_expected = {
        EXPLORE: {"copy_orchestration", "visual_direction", "broll_plan", "shot_vocabulary",
                  "source_research", "broll_finder"},
        BUILD: {"copy_orchestration", "visual_direction", "broll_plan", "illustration",
                "scene_illustration", "html_demo", "shot_vocabulary", "source_research"},
    }
    for path in (EXPLORE, BUILD):
        route = _dna(path)["skill_route"]
        repo = [item["step"] for item in route if item.get("path_base", "catalog") == "repo"]
        assert repo == ["captions", "qc"], (path, repo)
        shared = {item["step"] for item in route if item.get("path_base") == "shared"}
        assert shared == shared_expected[path], (path, shared)
        for item in route:
            if item["step"] not in repo_expected and item["step"] not in shared:
                assert "path_base" not in item, (path, item["step"], item.get("path_base"))


def test_a_shared_route_naming_an_unknown_skill_fails():
    from check_account_dna import SHARED_SKILL_ROOT
    if not SHARED_SKILL_ROOT.is_dir():
        print("shared store absent on this checkout; skipping the unknown-skill check")
        return
    dna = _mutated(_dna(EXPLORE), "visual_direction", skill="no-such-shared-skill")
    failures = check_account(dna, ROOT)
    assert len(failures) == 1, failures
    assert "shared skill store" in failures[0], failures[0]


def test_an_absent_shared_store_is_a_warning_not_a_failure():
    """A CI runner has no ~/.agents/skills; that is unverified, not invalid."""
    from unittest import mock

    import check_account_dna

    dna = _dna(EXPLORE)
    with mock.patch.object(check_account_dna, "SHARED_SKILL_ROOT",
                           ROOT / "no-such-store"), \
         mock.patch.object(check_account_dna, "shared_skill", lambda name: None):
        failures = check_account_dna.check_account(dna, ROOT)
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
        test_every_account_declares_the_evidence_mode_that_gates_it,
        test_the_proof_account_is_gated_by_the_real_source_floor,
        test_the_explanatory_account_is_gated_by_its_own_composition,
        test_an_undeclared_evidence_mode_fails,
        test_a_proven_account_may_not_declare_a_mix_it_cannot_reach,
        test_an_explanatory_account_may_not_keep_the_floor,
        test_an_explanatory_account_may_not_plan_a_recording,
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
        test_a_route_entry_naming_an_unknown_skill_fails,
        test_a_repo_relative_script_must_exist,
        test_an_undeclared_path_base_is_not_silently_assumed,
        test_the_route_declares_repo_only_where_it_must,
        test_a_shared_route_naming_an_unknown_skill_fails,
        test_an_absent_shared_store_is_a_warning_not_a_failure,
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
