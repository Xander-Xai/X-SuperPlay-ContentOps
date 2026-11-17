"""Anchor stills must be readable, and must show what the shot is talking about.

Three regressions this suite pins down, all found while wiring the six Huashu
templates to the anchor renderer:

* the schematic painted the dark ``ink`` token onto the dark brand background,
  so every stage label became invisible once ``brand.palette`` replaced the old
  light ``motion_profile`` palette;
* a pinned excerpt window was re-opened on a nearby ``def``, so a shot about
  ``MISSING_REAL_RECORDING`` displayed ``_declared_fallback`` instead;
* the rebuild script drew a three-box schematic for a ``code_focus`` shot, so a
  beat that says "this line of code" showed a diagram.

Everything here is offline: Pillow draws a real PNG into a temp directory, and
no process is spawned.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from contentops.media.source_anchor import (  # noqa: E402
    ANCHOR_HEIGHT,
    ANCHOR_WIDTH,
    _readable_text,
    render_anchor,
    render_flow_anchor,
)

DARK_PALETTE = {
    "bg": "#0F1117", "surface": "#F9FBFA", "ink": "#202B31",
    "sub": "#65747A", "accent": "#38BDF8", "accent2": "#AABDC1",
}
LIGHT_PALETTE = {
    "bg": "#F4F2ED", "surface": "#FFFFFF", "ink": "#18232B",
    "sub": "#5C6970", "accent": "#087FA6", "accent2": "#C4DCE3",
}

SOURCE = "\n".join([
    "import os",
    "",
    "def _declared_fallback(requested, compatible):",
    "    for name in compatible:",
    "        return name",
    "    return None",
    "",
    "def select_backend(*, account_id, shot_type):",
    "    if account_id == 'x-superplay-1024':",
    "        return _blocked('MISSING_REAL_RECORDING', 'a cropped recording is required')",
    "    return None",
])


def _render(tmp: Path, *, palette=DARK_PALETTE, pin_lines=(), name="a.png"):
    return render_anchor(
        source_text=SOURCE, filename="backend.py", title="",
        repository="pinned source", commit="", spdx="",
        palette=palette, queries=["select_backend recording"],
        out_path=tmp / name, pin_lines=pin_lines,
    )


LONG_SOURCE = "\n".join(
    [f"VALUE_{index} = {index}" for index in range(40)]
    + ["def _declared_fallback(requested, compatible):",
       "    for name in compatible:",
       "        return name",
       "    return None"]
    + [f"AUX_{index} = {index}" for index in range(30)]
    + ["def select_backend(*, account_id):",
       "    if account_id == 'x-superplay-1024':",
       "        return _blocked('MISSING_REAL_RECORDING')",
       "    return None"])


def test_pinned_window_opens_on_the_pinned_lines_not_a_distant_definition():
    with tempfile.TemporaryDirectory() as temp:
        rendered = render_anchor(
            source_text=LONG_SOURCE, filename="backend.py", title="",
            repository="pinned source", commit="", spdx="",
            palette=DARK_PALETTE, queries=["MISSING_REAL_RECORDING"],
            out_path=Path(temp) / "pinned.png", pin_lines=[75, 76, 77, 78],
        )
        shown = [row["n"] for row in rendered.lines if row["n"] is not None]
        assert 75 in shown and 78 in shown, shown
        # The old bug re-opened the card on the earlier `def`, 70 lines above.
        assert min(shown) >= 71, shown
        assert set(rendered.focus_lines) == {75, 76, 77, 78}


def test_unpinned_window_still_opens_on_a_definition():
    with tempfile.TemporaryDirectory() as temp:
        rendered = _render(Path(temp), name="free.png")
        assert rendered.source_lines, "an unpinned card must still show source lines"
        texts = [str(row["text"]) for row in rendered.lines]
        assert any(text.strip().startswith("def ") for text in texts), texts[:4]


def test_dark_background_picks_light_text_and_light_picks_ink():
    assert _readable_text("#0F1117", DARK_PALETTE)[0] == "#F9FBFA"
    assert _readable_text("#F4F2ED", LIGHT_PALETTE)[0] == "#18232B"


def test_flow_anchor_labels_are_legible_on_a_dark_brand_card():
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp) / "flow.png"
        render_flow_anchor(title="升级需要批准", steps=["上游新版本", "评估影响", "冻结决定"],
                           palette=DARK_PALETTE, out_path=out,
                           provenance="schematic drawn from the reviewed narration")
        from PIL import Image
        image = Image.open(out).convert("RGB")
        assert image.size == (ANCHOR_WIDTH, ANCHOR_HEIGHT)
        # The box interior must not be painted with the same colour as the text.
        assert _readable_text(DARK_PALETTE["bg"], DARK_PALETTE)[0] != DARK_PALETTE["ink"]


def _write_project(root: Path, account: str, animation: str) -> Path:
    project = root / "case"
    (project / "script").mkdir(parents=True)
    (project / "sources").mkdir(parents=True)
    (project / "project.yaml").write_text(
        f'id: case\ntitle: "t"\naccount_slug: {account}\n', encoding="utf-8")
    (project / "script" / "script.json").write_text(json.dumps({
        "schema": "contentops.m5-script/v1",
        "lines": [{"id": "l1", "narration": "看到这段守卫代码", "caption": "守卫",
                   "claim": None, "asset_id": "a1"}],
        "visual_shots": [{"shot_id": "l1", "segment_id": "l1", "asset_id": "a1",
                          "visual_role": "explain", "duration_weight": 1.0,
                          "visual_focus": "MISSING_REAL_RECORDING",
                          "animation_type": animation,
                          "animation": {"states": ["候选", "比对", "决定"],
                                        "transition": "一致", "success": "复用",
                                        "failure": "重渲"}}],
    }, ensure_ascii=False), encoding="utf-8")
    (project / "sources" / "assets.json").write_text(json.dumps({
        "schema": "contentops.m5-assets/v1",
        "assets": [{"id": "a1", "type": "CODE_SNAPSHOT",
                    "repo_path": "projects/case/assets/anchors/a1.png",
                    "permission": "CREATED_BY_OWNER"}],
    }, ensure_ascii=False), encoding="utf-8")
    return project


def test_vector_account_keeps_a_code_card_for_a_code_focus_shot():
    import rebuild_source_anchors

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        project = _write_project(root, "x-superplay-future-intelligence", "code_focus")
        (project / "sources" / "pinned").mkdir(parents=True, exist_ok=True)
        document = project / "sources" / "pinned" / "backend.py"
        document.write_text(SOURCE, encoding="utf-8")
        manifest = json.loads((project / "sources" / "assets.json").read_text(encoding="utf-8"))
        manifest["assets"][0]["source_document"] = "sources/pinned/backend.py"
        (project / "sources" / "assets.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        # A dry run reports the branch it would take without drawing anything.
        result = rebuild_source_anchors.rebuild(project, dry_run=True)
        rebuilt = {row["id"]: row for row in result["rebuilt"]}
        assert rebuilt["a1"].get("kind") != "concept", rebuilt["a1"]


def test_schematic_uses_the_steps_the_shot_declares():
    import rebuild_source_anchors

    with tempfile.TemporaryDirectory() as temp:
        project = _write_project(Path(temp), "x-superplay-future-intelligence",
                                 "state_transition")
        steps = rebuild_source_anchors._declared_steps(project)
        assert steps == {"a1": ["候选", "比对", "决定"]}


def main() -> int:
    tests = [
        test_pinned_window_opens_on_the_pinned_lines_not_a_distant_definition,
        test_unpinned_window_still_opens_on_a_definition,
        test_dark_background_picks_light_text_and_light_picks_ink,
        test_flow_anchor_labels_are_legible_on_a_dark_brand_card,
        test_vector_account_keeps_a_code_card_for_a_code_focus_shot,
        test_schematic_uses_the_steps_the_shot_declares,
    ]
    for test in tests:
        test()
        print(f"[ok] {test.__name__}")
    print(f"All {len(tests)} source-anchor renderer tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
