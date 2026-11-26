"""TOPIC copy derivative -> M5 script projection.

One test per defect found during the AgentGuide video run:

- splitting never loses or rewrites reviewed copy;
- narration equals caption and each segment's claims are fully covered;
- adjacent shots never reuse the same authored card;
- every line asks for the camera-push grammar with a valid focus rectangle;
- a projection that reuses a card or drifts from the derivative fails closed;
- the CLI writes only script.json and blocks without authored cards.

Run: python tests/test_topic_m5.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.script.topic_m5 import (  # noqa: E402
    DERIVATIVE_SCHEMA,
    FOCUS_RECTS,
    PUSH_GRAMMAR,
    SCRIPT_SCHEMA,
    TopicM5Error,
    build_script,
    validate_script,
)
import topic_to_m5  # noqa: E402


def derivative(segments=None):
    return {
        "schema": DERIVATIVE_SCHEMA,
        "format": "VIDEO",
        "copy_id": "COPY-TEST-01",
        "copy_sha256": "a" * 64,
        "segments": segments or [
            {"source_segment_id": "S01", "text": "第一句话。第二句话，第三句话？",
             "claim_refs": ["C1", "C2"]},
            {"source_segment_id": "S02", "text": "另外一段很长的话需要被切成多个镜头才不会超过时长上限。",
             "claim_refs": ["C2"]},
        ],
    }


CARDS = ["card-a", "card-b", "card-c"]


def test_projection_preserves_copy_and_claims():
    d = derivative()
    s = build_script(d, asset_ids=CARDS)
    assert s["schema"] == SCRIPT_SCHEMA
    joined = {}
    claims_by_seg = {}
    for line in s["lines"]:
        seg = line["source_segment_id"]
        joined[seg] = joined.get(seg, "") + line["narration"]
        claims_by_seg.setdefault(seg, set()).update(line["claims"])
        assert line["caption"] == line["narration"]
        assert line["claim"] in line["claims"]
    for seg in d["segments"]:
        assert joined[seg["source_segment_id"]] == seg["text"]
        assert claims_by_seg[seg["source_segment_id"]] == set(seg["claim_refs"])
    assert validate_script(s, d) == []


def test_long_segment_is_split_within_char_budget():
    d = derivative()
    s = build_script(d, asset_ids=CARDS, max_chars=12)
    assert len([l for l in s["lines"] if l["source_segment_id"] == "S02"]) >= 3
    assert all(len(l["narration"]) <= 12 for l in s["lines"])
    assert validate_script(s, d) == []


def test_adjacent_shots_rotate_card_and_focus():
    d = derivative()
    s = build_script(d, asset_ids=CARDS, max_chars=8)
    for prev, cur in zip(s["lines"], s["lines"][1:]):
        assert prev["asset_id"] != cur["asset_id"], "adjacent reuse fails visual QC"
        prev_rect = prev["animation"]["focus_rect"]
        cur_rect = cur["animation"]["focus_rect"]
        assert prev_rect != cur_rect
        assert cur_rect in [list(r) for r in FOCUS_RECTS]


def test_every_line_has_push_grammar_and_valid_focus_rect():
    d = derivative()
    s = build_script(d, asset_ids=CARDS)
    for line in s["lines"]:
        assert line["animation_type"] == PUSH_GRAMMAR
        rect = line["animation"]["focus_rect"]
        assert isinstance(rect, list) and len(rect) == 4
        assert all(isinstance(value, (int, float)) for value in rect)
        assert rect in [list(r) for r in FOCUS_RECTS]


def test_reused_card_in_existing_script_fails_check():
    d = derivative()
    s = build_script(d, asset_ids=CARDS, max_chars=8)
    for line in s["lines"]:
        line["asset_id"] = "same-card"
    problems = validate_script(s, d)
    assert any("reuses card" in p for p in problems)


def test_whiteboard_grammar_fails_check():
    d = derivative()
    s = build_script(d, asset_ids=CARDS)
    s["lines"][0]["animation_type"] = "architecture_flow"
    problems = validate_script(s, d)
    assert any("camera motion" in p for p in problems)


def test_copy_drift_fails_check():
    d = derivative()
    s = build_script(d, asset_ids=CARDS)
    s["lines"][0]["narration"] += "多出来的字"
    problems = validate_script(s, d)
    assert any("does not reproduce reviewed text" in p for p in problems)


def test_derivative_without_claims_is_blocked():
    d = derivative([{"source_segment_id": "S01", "text": "一句话。", "claim_refs": []}])
    try:
        build_script(d, asset_ids=CARDS)
    except TopicM5Error as exc:
        assert exc.code == "SEGMENT_NO_CLAIMS"
    else:
        raise AssertionError("expected SEGMENT_NO_CLAIMS")


def test_no_cards_is_blocked():
    try:
        build_script(derivative(), asset_ids=[])
    except TopicM5Error as exc:
        assert exc.code == "NO_VISUAL_CARDS"
    else:
        raise AssertionError("expected NO_VISUAL_CARDS")


def test_cli_writes_only_script_and_blocks_without_cards():
    d = derivative()
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        (project / "00_brief").mkdir()
        (project / "script").mkdir()
        (project / "sources").mkdir()
        (project / "00_brief" / "copy-derivative.json").write_text(
            json.dumps(d, ensure_ascii=False), encoding="utf-8")
        (project / "sources" / "assets.json").write_text(
            json.dumps({"schema": "contentops.m5-assets/v1", "assets": [
                {"id": c, "type": "REAL_SCREENSHOT", "permission": "CREATED_BY_OWNER",
                 "sha256": "a" * 64, "repo_path": "assets/x.png"}
                for c in CARDS
            ]}, ensure_ascii=False), encoding="utf-8")

        assert topic_to_m5.main([str(project), "--json"]) == 0
        script_path = project / "script" / "script.json"
        assert script_path.is_file()
        assert not (project / "receipts").exists()

        assert topic_to_m5.main([str(project), "--check", "--json"]) == 0
        assert topic_to_m5.main([str(project), "--dry-run", "--json"]) == 0

        (project / "sources" / "assets.json").write_text(
            json.dumps({"schema": "contentops.m5-assets/v1", "assets": []}), encoding="utf-8")
        assert topic_to_m5.main([str(project), "--json"]) == 4


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} tests passed")
