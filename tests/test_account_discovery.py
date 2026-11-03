"""Discovery block tests: the account's own words become its search terms.

The rule these tests defend is narrow and important: **a search term may
only exist if it can be traced to text the account owner wrote.** The
discovery block in the account DNA declares the terms a collector uses, and
each one names the DNA field it came from. If that citation does not
resolve, the term is a fabrication and the DNA fails.

So a test that passes a hand-written keyword into the same validator and
watches it be refused is worth more than any amount of prose about it.

Run: python tests/test_account_discovery.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from check_account_dna import _check_discovery  # noqa: E402
from contentops.hotspots.source_registry import SOURCES  # noqa: E402
from contentops.routing.account_profile import (  # noqa: E402
    Keyword,
    load_profile,
    verify_origin,
)

ACCOUNTS = ROOT / "config" / "accounts"
EXPLORE = ACCOUNTS / "x-superplay-1024.json"
BUILD = ACCOUNTS / "x-superplay-future-intelligence.json"

DNA_FILES = (EXPLORE, BUILD)


def _dna(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_both_accounts_declare_a_discovery_block():
    for path in DNA_FILES:
        dna = _dna(path)
        assert isinstance(dna.get("discovery"), dict), path.name
        assert dna["discovery"]["schema"] == "contentops.account-discovery/v1"


def test_every_keyword_resolves_to_a_field_of_its_own_dna():
    for path in DNA_FILES:
        dna = _dna(path)
        discovery = dna["discovery"]
        for key in ("keywords_positive", "keywords_negative"):
            for item in discovery[key]:
                keyword = Keyword(term=item["term"], language=item["language"],
                                  origin=item["origin"])
                failures = verify_origin(dna, keyword)
                assert failures == [], f"{path.name} {key}: {failures}"


def test_a_keyword_that_no_field_supports_is_refused():
    dna = _dna(EXPLORE)
    invented = Keyword(term="区块链 元宇宙 量子计算", language="zh",
                        origin={"kind": "pillar_scope", "pillar": "AI 新物种"})
    failures = verify_origin(dna, invented)
    assert failures
    assert "does not appear in the DNA text it cites" in failures[0]


def test_a_keyword_citing_a_pillar_that_does_not_exist_is_refused():
    dna = _dna(EXPLORE)
    invented = Keyword(term="新模型", language="zh",
                       origin={"kind": "pillar_scope", "pillar": "不存在的支柱"})
    failures = verify_origin(dna, invented)
    assert failures
    assert "resolves to nothing" in failures[0]


def test_a_keyword_citing_an_out_of_range_audience_index_is_refused():
    dna = _dna(EXPLORE)
    invented = Keyword(term="开发者", language="zh",
                       origin={"kind": "audience", "index": 99})
    failures = verify_origin(dna, invented)
    assert failures
    assert "resolves to nothing" in failures[0]


def test_a_translation_must_translate_a_term_that_exists():
    dna = _dna(EXPLORE)
    invented = Keyword(term="blockchain", language="en",
                       origin={"kind": "translation", "origin_kind": "pillar_scope",
                               "pillar": "AI 新物种", "origin_term": "区块链",
                               "origin_language": "zh"})
    failures = verify_origin(dna, invented)
    assert failures
    assert "does not appear in the cited DNA text" in failures[0]


def test_a_translation_must_change_language():
    dna = _dna(EXPLORE)
    same_language = Keyword(term="open source", language="en",
                            origin={"kind": "translation",
                                    "origin_kind": "pillar_scope",
                                    "pillar": "AI 新物种",
                                    "origin_term": "新 GitHub 项目",
                                    "origin_language": "en"})
    failures = verify_origin(dna, same_language)
    assert failures
    assert "has to change language" in failures[0]


def test_a_translation_must_declare_its_origin_language():
    dna = _dna(EXPLORE)
    undeclared = Keyword(term="open source", language="en",
                         origin={"kind": "translation",
                                 "origin_kind": "pillar_scope",
                                 "pillar": "AI 新物种",
                                 "origin_term": "新 GitHub 项目"})
    failures = verify_origin(dna, undeclared)
    assert failures
    assert "declares no origin_language" in failures[0]


def test_a_translation_may_render_an_english_term_into_chinese():
    """The founder wrote "Workflow"; a Chinese source writes "工作流"."""
    dna = _dna(EXPLORE)
    rendered = Keyword(term="工作流", language="zh",
                       origin={"kind": "translation",
                               "origin_kind": "pillar_scope",
                               "pillar": "AI 挑战100个职业",
                               "origin_term": "Workflow",
                               "origin_language": "en"})
    assert verify_origin(dna, rendered) == []


def test_an_unknown_origin_kind_is_refused():
    dna = _dna(EXPLORE)
    invented = Keyword(term="新模型", language="zh", origin={"kind": "vibes"})
    failures = verify_origin(dna, invented)
    assert failures
    assert "expected one of" in failures[0]


def test_the_dna_check_accepts_both_accounts():
    for path in DNA_FILES:
        warnings: list = []
        failures = _check_discovery(_dna(path), warnings)
        assert failures == [], f"{path.name}: {failures}"


def test_the_dna_check_fails_a_discovery_block_with_an_invented_keyword():
    dna = _dna(EXPLORE)
    dna["discovery"]["keywords_positive"].append({
        "term": "区块链",
        "language": "zh",
        "origin": {"kind": "pillar_scope", "pillar": "AI 新物种"},
    })
    failures = _check_discovery(dna, [])
    assert failures
    assert any("区块链" in failure for failure in failures)


def test_the_dna_check_fails_a_source_that_is_not_in_the_registry():
    dna = _dna(EXPLORE)
    dna["discovery"]["source_allowlist"].append({
        "source_id": "not-a-real-source", "why": "because"})
    failures = _check_discovery(dna, [])
    assert failures
    assert any("not a source in the registry" in failure for failure in failures)


def test_the_dna_check_fails_a_source_with_no_reason():
    dna = _dna(EXPLORE)
    dna["discovery"]["source_allowlist"].append({
        "source_id": "github-search", "why": ""})
    failures = _check_discovery(dna, [])
    assert failures
    assert any("gives no reason" in failure for failure in failures)


def test_the_dna_check_fails_an_account_that_exempts_itself():
    dna = _dna(EXPLORE)
    dna["discovery"]["approval_policy"]["brief_approval_required"] = False
    failures = _check_discovery(dna, [])
    assert failures
    assert any("cannot exempt itself" in failure for failure in failures)


def test_the_dna_check_fails_weights_that_do_not_sum_to_a_hundred():
    dna = _dna(EXPLORE)
    dna["discovery"]["match_weights"]["profile_relevance"] = 90
    failures = _check_discovery(dna, [])
    assert failures
    assert any("summing to 100" in failure for failure in failures)


def test_an_account_with_no_discovery_block_is_warned_about_not_failed():
    dna = _dna(EXPLORE)
    del dna["discovery"]
    warnings: list = []
    failures = _check_discovery(dna, warnings)
    assert failures == []
    assert warnings
    assert "ACCOUNT_DNA_MISSING" in warnings[0]


def test_the_two_accounts_search_for_different_things():
    explore = load_profile(ROOT, "x-superplay-1024")
    build = load_profile(ROOT, "x-superplay-future-intelligence")
    assert set(explore.positive_terms) != set(build.positive_terms)
    assert set(explore.source_allowlist) != set(build.source_allowlist)
    assert set(explore.negative_terms) != set(build.negative_terms)


def test_the_two_accounts_block_different_sources():
    explore = load_profile(ROOT, "x-superplay-1024")
    build = load_profile(ROOT, "x-superplay-future-intelligence")
    assert set(explore.source_blocklist) != set(build.source_blocklist)
    # Both block the general-interest lists.
    assert "baidu-hot" in explore.source_blocklist
    assert "baidu-hot" in build.source_blocklist


def test_every_allowed_source_exists_in_the_registry():
    for path in DNA_FILES:
        dna = _dna(path)
        for entry in dna["discovery"]["source_allowlist"]:
            assert entry["source_id"] in SOURCES, (path.name, entry["source_id"])


def test_the_excluded_topics_come_from_the_accounts_own_not_doing():
    explore = load_profile(ROOT, "x-superplay-1024")
    assert "纯新闻搬运" in explore.topics_exclude
    assert "AI 暴富叙事" in explore.topics_exclude
    build = load_profile(ROOT, "x-superplay-future-intelligence")
    assert any("只追新闻" in topic for topic in build.topics_exclude)


def test_the_include_topics_come_from_the_accounts_own_pillars():
    explore = load_profile(ROOT, "x-superplay-1024")
    assert any("AI 新物种" in topic for topic in explore.topics_include)
    build = load_profile(ROOT, "x-superplay-future-intelligence")
    assert any("LangGraph" in topic for topic in build.topics_include)


def test_each_account_declares_the_platforms_it_publishes_video_on():
    explore = load_profile(ROOT, "x-superplay-1024")
    build = load_profile(ROOT, "x-superplay-future-intelligence")
    assert "douyin" in explore.platforms
    assert "bilibili" in build.platforms
    # A derived or text platform is not a video target.
    assert "zhihu" not in build.platforms
    assert "gzh" not in explore.platforms


def main() -> int:
    tests = tuple(value for name, value in sorted(globals().items())
                  if name.startswith("test_") and callable(value))
    failures = []
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
    print(f"\nAll {len(tests)} account discovery tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
