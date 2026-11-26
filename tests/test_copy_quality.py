#!/usr/bin/env python3
"""Offline tests for the read-only copy-structure diagnosis.

Run: python tests/test_copy_quality.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow import copy_quality  # noqa: E402


def test_template_opening_is_flagged() -> None:
    r = copy_quality.diagnose([
        "这一期讲你提的问题：Easel 冻结。",
        "版本写在 pin 文件里。",
        "以上内容都能在文末的来源里逐条核对。",
    ])
    assert r["opening"]["status"] == "TEMPLATE", r["opening"]


def test_hooked_opening_is_recognised() -> None:
    r = copy_quality.diagnose([
        "你花三天做的片子，为什么 30 秒就没人看？",
        "问题常常不在内容，而在开头。",
        "关注我，下一条拆分镜。",
    ])
    assert r["opening"]["status"] == "HOOKED", r["opening"]


def test_strong_cta_ending() -> None:
    r = copy_quality.diagnose([
        "别再用看完多少课记进度。",
        "每一阶段留下一件能跑的东西。",
        "如果你想看具体清单，关注我，下一条讲评测集怎么写。",
    ])
    assert r["ending"]["status"] == "CTA", r["ending"]


def test_compliance_only_ending_is_weak() -> None:
    r = copy_quality.diagnose([
        "别把目标数字写成实绩。",
        "项目验收才说明能力落到了手上。",
        "以上内容都能在文末的来源里逐条核对。",
    ])
    assert r["ending"]["status"] == "WEAK_CTA", r["ending"]


def test_no_ending_action() -> None:
    r = copy_quality.diagnose([
        "别把热度当需求。",
        "先看有没有人真的在问。",
        "剩下的交给时间。",
    ])
    assert r["ending"]["status"] == "NO_CTA", r["ending"]


def test_person_and_concreteness_ratios() -> None:
    r = copy_quality.diagnose([
        "别急着看播放量。",
        "你可以先看这条脚本。",
        "runtime/easel-pins.json 里写了 bb3c8ff。",
        "关注我，下一条继续。",
    ])
    body = r["body"]
    assert body["person_ratio"] > 0, body
    assert body["concrete_ratio"] > 0, body


def test_filler_is_detected_with_line_numbers() -> None:
    r = copy_quality.diagnose([
        "别用套话开头。",
        "众所周知，内容为王。",
        "需要注意的是，标题也重要。",
        "关注我。",
    ])
    assert "众所周知" in r["body"]["filler_hits"]
    assert 2 in r["body"]["filler_lines"]


def test_score_is_bounded_and_low_for_template() -> None:
    weak = copy_quality.diagnose([
        "这一期讲某个话题。",
        "总的来说内容很重要。",
        "以上内容都能在文末核对。",
    ])
    assert 0 <= weak["score"] <= 100
    assert weak["score"] < 70, weak


def test_accepts_script_line_dicts() -> None:
    r = copy_quality.diagnose([
        {"narration": "你为什么总是写不出钩子？", "caption": "钩子"},
        {"narration": "因为你一开口就在做节目介绍。"},
        {"narration": "关注我，下一条给你模板。"},
    ])
    assert r["opening"]["status"] == "HOOKED"
    assert r["ending"]["status"] == "CTA"


def test_empty_input_fails_closed() -> None:
    try:
        copy_quality.diagnose([])
    except ValueError:
        return
    raise AssertionError("empty input must raise")


def test_single_line_is_tolerated() -> None:
    r = copy_quality.diagnose(["你为什么总在开头劝退观众？关注我。"])
    assert r["line_count"] == 2  # opening duplicated to keep opening/ending
    assert r["opening"]["status"] == "HOOKED"


def test_report_states_it_is_not_a_verdict() -> None:
    r = copy_quality.diagnose(["别急着改片。", "先看结构。", "关注我。"])
    assert "不是" in r["disclaimer"] and "播放量" in r["disclaimer"]


TESTS: List[Tuple[str, Callable[[], None]]] = [
    (name, obj) for name, obj in sorted(globals().items())
    if name.startswith("test_") and callable(obj)
]


def main() -> int:
    failures: List[Tuple[str, str]] = []
    for name, fn in TESTS:
        try:
            fn()
            print(f"[ OK ] {name}")
        except Exception as exc:  # noqa: BLE001
            failures.append((name, repr(exc)))
            print(f"[FAIL] {name}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(TESTS)} copy-quality tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
