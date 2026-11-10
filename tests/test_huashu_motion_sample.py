"""The prepared motion sample is a design, and it says so.

Run: python tests/test_huashu_motion_sample.py

Nothing here renders. The suite checks the sample's design files against the
contracts they will have to satisfy the moment a render is authorized: the
storyboard's rhythm, the Art Motion spec shape, the unified visual spec, the
M4.5 asset mapping, and the Huashu Motion project draft. It also checks the
things that must stay true no matter what: the sample is marked unrendered, it
uses no real screenshot, and generated visuals may be supplementary only when factual claims are independently supported.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media import huashu_motion  # noqa: E402

PROJECT = ROOT / "projects" / "huashu-motion-sample"
SAMPLE_MIN_S = 15.0
SAMPLE_MAX_S = 25.0
CJK = re.compile(r"[㐀-鿿]")


def _json(relative: str):
    return json.loads((PROJECT / relative).read_text(encoding="utf-8"))


def _storyboard():
    return _json("script/storyboard.json")


def test_the_sample_is_declared_unrendered_everywhere():
    board = _storyboard()
    assert board["render_status"] == "RENDER_NOT_VERIFIED"
    status = _json("receipts/render-status.json")
    assert status["status"] == "RENDER_NOT_VERIFIED"
    assert status["rendered"] is False
    assert status["clips"] == []
    assert status["production_ready"] is False
    assert status["publish_authorized"] is False
    assert _json("motion/asset-mapping.json")["render_status"] == "RENDER_NOT_VERIFIED"
    assert _json("motion/visual-spec.json")["render_status"] == "RENDER_NOT_VERIFIED"
    assert _json("huashu-motion/project.json")["render_status"] == "RENDER_NOT_VERIFIED"


def test_the_storyboard_lasts_between_fifteen_and_twenty_five_seconds():
    board = _storyboard()
    total = board["total_duration_s"]
    assert SAMPLE_MIN_S <= total <= SAMPLE_MAX_S, total
    shots = board["shots"]
    assert sum(shot["duration_s"] for shot in shots) == total
    assert shots[0]["duration_s"] == 4.0, "the first motion-sample candidate must satisfy the unchanged 4–8 s gate"
    cursor = 0.0
    for shot in shots:
        assert abs(shot["time_in_s"] - cursor) < 0.001, shot["placement_id"]
        assert abs(shot["time_out_s"] - round(cursor + shot["duration_s"], 3)) < 0.001, shot["placement_id"]
        cursor += shot["duration_s"]


def test_every_shot_fits_the_eight_second_clip_contract():
    for shot in _storyboard()["shots"]:
        assert 0.0 < shot["duration_s"] <= huashu_motion.MAX_CLIP_S, shot["placement_id"]


def test_no_camera_treatment_repeats_three_times_in_a_row():
    cameras = [shot["camera"] for shot in _storyboard()["shots"]]
    for index in range(len(cameras) - 2):
        window = cameras[index:index + 3]
        assert not (window[0] == window[1] == window[2]), window


def test_the_fast_camera_appears_once_and_only_on_the_emphasis_shot():
    shots = _storyboard()["shots"]
    fast = [shot["placement_id"] for shot in shots if shot["camera"] == "快推"]
    assert fast == ["p04"], fast


def test_every_shot_names_a_subject_and_an_action():
    for shot in _storyboard()["shots"]:
        assert shot["subject"].strip(), shot["placement_id"]
        assert shot["action"].strip(), shot["placement_id"]
        assert len(shot["screen_text"]) <= 8, shot["placement_id"]


def test_the_sample_uses_no_real_screenshot_and_no_third_party_material():
    board = _storyboard()
    assert board["evidence_policy"]["real_assets_used"] is False
    assert board["evidence_policy"]["evidence_capable"] is False
    sources = list((PROJECT / "sources").glob("*"))
    assert sources, "the design note is part of the sample"
    for source in sources:
        assert source.suffix in {".md", ".txt"}, source
    for spec_path in sorted((PROJECT / "motion" / "specs").glob("*.json")):
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        for cue in spec["cues"]:
            for key in ("image", "frames"):
                ref = cue.get(key)
                for item in (ref if isinstance(ref, list) else [ref]):
                    if isinstance(item, str):
                        assert item.startswith("assets/motion/"), item


def test_every_art_motion_spec_satisfies_the_pinned_clip_contract():
    board = _storyboard()
    grammars = set()
    themes = set()
    for shot in board["shots"]:
        spec_path = PROJECT / shot["art_motion"]["spec"]
        assert spec_path.is_file(), spec_path
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        assert spec["grammar"] in {
            "t1_3b1b", "t2_keynote_ui", "t3_finance_chart", "y1_kurzgesagt",
            "y2_vox", "y3_whiteboard", "y4_storytime", "y5_kinetic_type"}, spec
        assert spec["theme"] in {
            "paper", "poster", "ink", "navy", "bauhaus", "snow", "wood", "chalk"}, spec
        assert spec["fps"] == 30 and spec["width"] == 1080 and spec["height"] == 1920
        assert 0.0 < spec["duration"] <= huashu_motion.MAX_CLIP_S
        assert spec["duration"] == shot["duration_s"], shot["placement_id"]
        assert spec["cues"], shot["placement_id"]
        for cue in spec["cues"]:
            assert 0 <= cue["at"] < spec["duration"], (shot["placement_id"], cue)
        grammars.add(spec["grammar"])
        themes.add(spec["theme"])
    assert len(grammars) <= 2, grammars
    assert themes == {"ink"}, themes


def test_every_spec_primary_copy_matches_the_storyboard():
    board = _storyboard()
    for shot in board["shots"]:
        spec = json.loads((PROJECT / shot["art_motion"]["spec"]).read_text(encoding="utf-8"))
        primary = [cue["text"] for cue in spec["cues"] if cue.get("text")]
        assert primary == [shot["screen_text"]], (shot["placement_id"], primary)


def test_the_chinese_copy_binds_the_pinned_cjk_font_review():
    board = _storyboard()
    for shot in board["shots"]:
        spec = json.loads((PROJECT / shot["art_motion"]["spec"]).read_text(encoding="utf-8"))
        has_cjk = any(CJK.search(cue.get("text") or "") or CJK.search(cue.get("sub") or "")
                      for cue in spec["cues"])
        assert has_cjk, shot["placement_id"]
    visual = _json("motion/visual-spec.json")
    assert visual["typography"]["cjk_family"] == "Noto Serif JP"
    assert visual["typography"]["font_review_status"] == "CJK_GLYPH_VISUAL_REVIEW_REQUIRED"


def test_the_visual_spec_is_one_style_with_a_non_blue_purple_palette():
    visual = _json("motion/visual-spec.json")
    assert visual["theme"] == "ink"
    palette = visual["palette"]
    for name, value in palette.items():
        if name == "rules":
            continue
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", value), (name, value)
    for name, value in palette.items():
        if name == "rules":
            continue
        red = int(value[1:3], 16)
        blue = int(value[5:7], 16)
        assert not (blue - red > 40), (name, value)


def test_the_asset_mapping_gives_every_placement_exactly_one_active_producer():
    board = _storyboard()
    mapping = _json("motion/asset-mapping.json")
    entries = mapping["entries"]
    placements = [entry["placement_id"] for entry in entries]
    assert placements == [shot["placement_id"] for shot in board["shots"]]
    assert len(placements) == len(set(placements))
    for entry in entries:
        assert entry["audio_policy"] == "REPLACE"
        assert entry["generated"] is True
        assert entry["evidence_capable"] is False
        assert entry["rights"] == "UNRESOLVED"
        assert entry["review_status"] == "PENDING_FOUNDER_REVIEW"
        assert entry["active_producer"] in {huashu_motion.ENGINE_MOTION,
                                            huashu_motion.ENGINE_ART_MOTION}
        assert entry["alternate_producer"]["engine"] != entry["active_producer"]
        assert entry["alternate_producer"]["status"] == "NOT_RENDERED"
        assert "re-activated" in entry["alternate_producer"]["activation_rule"]
        assert (PROJECT / entry["spec_path"]).is_file(), entry["spec_path"]


def test_the_mapping_never_names_a_rendered_clip():
    mapping = _json("motion/asset-mapping.json")
    for entry in mapping["entries"]:
        assert not (PROJECT / entry["clip_path"]).exists(), entry["clip_path"]
        assert not (PROJECT / entry["derived_clip_path"]).exists(), entry["derived_clip_path"]


def test_the_huashu_motion_draft_is_explicitly_non_compatible_until_rewritten():
    draft = (PROJECT / "huashu-motion" / "index.html").read_text(encoding="utf-8")
    project = _json("huashu-motion/project.json")
    assert project["compatibility_status"] == "NOT_COMPATIBLE"
    findings = " ".join(project["compatibility_findings"])
    assert "data-composition-id" in findings
    assert "window.__timelines" in findings
    assert "scene:" in findings
    assert "CSS" in findings
    assert "NOT_HUASHU_MOTION_COMPATIBLE" in draft
    assert "RENDER_NOT_VERIFIED" in draft


def test_the_huashu_motion_project_records_the_pinned_contract_and_blockers():
    project = _json("huashu-motion/project.json")
    assert project["engine"] == "huashu-motion"
    assert project["version"] == "0.3.1"
    assert project["commit"] == "52467f99c602b76ba86d511d37acdfe93fa1e16e"
    assert "skills/huashu-motion/references/contract.md" in project["contract_source"]
    assert project["contract_status"] == "READ_STATIC_CONTRACT"
    for path in project["integration_paths"]:
        assert path["status"] == "BLOCKED"
        assert path["note"]


def test_the_draft_commands_are_the_upstream_ones():
    project = _json("huashu-motion/project.json")
    commands = project["upstream_commands_verbatim"]
    for operation in ("check", "still", "render", "qa"):
        assert commands[operation].startswith(f"om {operation}")
        assert commands[operation] == huashu_motion.OPERATIONS[operation]["command"]


def test_the_draft_covers_every_storyboard_scene():
    draft = (PROJECT / "huashu-motion" / "index.html").read_text(encoding="utf-8")
    for shot in _storyboard()["shots"]:
        assert f'data-om-id="{shot["huashu_motion"]["scene"]}"' in draft, shot["placement_id"]


def test_a_generated_sample_visual_can_supplement_a_separately_supported_claim():
    """The visual is not evidence; the independently verified ledger is."""
    import tempfile

    import m5_production

    board = _storyboard()
    placement = board["shots"][0]["placement_id"]
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "script").mkdir(parents=True)
        (project / "sources").mkdir()
        (project / "work" / "clips").mkdir(parents=True)
        clip = project / "work" / "clips" / "p01.mp4"
        clip.write_bytes(b"generated visual fixture")
        (project / "script" / "script.json").write_text(json.dumps({
            "schema": m5_production.SCRIPT_SCHEMA, "lines": [{
                "id": "line-a", "claim": "C1", "narration": "fact narration",
                "caption": "fact", "placement_id": placement,
            }],
        }), encoding="utf-8")
        result = m5_production.stage_script(
            project, _ledger(), {}, manifest_assets_by_line={"line-a": {
                "asset_id": "p01-motion", "repo_path": str(clip),
                "placement_id": placement, "generated": True,
                "evidence_capable": False, "evidence_use": "VISUAL_SUPPORT",
                "claim_refs": [],
            }})
        assert result["lines"] == 1
        assert "C1" in (project / "script" / "master.md").read_text(encoding="utf-8")


def test_a_generated_sample_visual_cannot_claim_evidence_itself():
    import tempfile

    import m5_production

    board = _storyboard()
    placement = board["shots"][0]["placement_id"]
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "script").mkdir(parents=True)
        (project / "sources").mkdir()
        clip = project / "generated.mp4"
        clip.write_bytes(b"generated visual fixture")
        (project / "script" / "script.json").write_text(json.dumps({
            "schema": m5_production.SCRIPT_SCHEMA, "lines": [{
                "id": "line-a", "claim": "C1", "narration": "fact narration",
                "caption": "fact", "placement_id": placement,
            }],
        }), encoding="utf-8")
        try:
            m5_production.stage_script(
                project, _ledger(), {}, manifest_assets_by_line={"line-a": {
                    "asset_id": "p01-motion", "repo_path": str(clip),
                    "placement_id": placement, "generated": True,
                    "evidence_capable": False, "evidence_use": "EVIDENCE",
                    "claim_refs": ["C1"],
                }})
        except m5_production.M5Blocked as exc:
            assert "generated visual cannot carry claim evidence" in str(exc)
        else:
            raise AssertionError("a generated visual must not claim evidence capability")


def _ledger():
    from contentops.evidence import CLAIM_SCHEMA, ClaimLedger

    return ClaimLedger.from_payload({"schema": CLAIM_SCHEMA, "claims": [{
        "id": "C1", "text": "the fact", "artifacts": ["source"], "quotes": ["the fact"],
    }]})


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - a runner reports, it does not hide
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    total = len(TESTS)
    print(f"{total - failures}/{total} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
