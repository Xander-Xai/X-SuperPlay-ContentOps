"""The 剪映 handoff writes one draft from the accepted timeline, and stops.

What is pinned
--------------
1. A draft is produced from ``receipts/media-manifest.json`` + the subtitle cues,
   inside the project directory, with a receipt naming the library version, the
   draft path and every written file's sha256.
2. The asset **inventory** is not walked. A manifest may list assets nobody placed
   on the timeline; the draft must ignore them. One of those extra assets points at
   a file that does not exist, so walking the inventory would fail loudly.
3. The picture count must equal the cue count. The handoff pairs one still per
   cue; when the numbers disagree it refuses instead of distributing shots by
   proportion.
4. Nothing is rendered, exported, clicked or opened. The upstream batch-export path
   is documented as JianYing 6 and below only, so it is structurally absent here:
   no ``JianyingController``, no export call, and the receipt says so.
5. ``production_ready`` and ``publish_authorized`` are false in every receipt.

The library is real, at the pinned version. This is a fixture *project*, not a
stubbed library: the point is that JianYing can open what comes out. JianYing
itself is never launched.
"""

from __future__ import annotations

import ast
import json
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.media.jianying_handoff import (  # noqa: E402
    HandoffError,
    PINNED_VERSION,
    build_handoff,
    parse_srt,
)

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
)

SRT_TWO_CUES = """1
00:00:00,000 --> 00:00:02,500
第一句

2
00:00:02,500 --> 00:00:05,000
第二句
"""


def _project(base: Path, *, cues: int = 2, extra_inventory: bool = True,
             missing_shot: bool = False) -> Path:
    project = base / "demo-project"
    (project / "sources").mkdir(parents=True)
    (project / "receipts").mkdir()
    (project / "assets" / "captions").mkdir(parents=True)
    for name in ("shot-01.png", "shot-02.png"):
        payload = b"" if missing_shot and name == "shot-01.png" else PNG_1X1
        (project / "sources" / name).write_bytes(payload)
    if missing_shot:
        (project / "sources" / "shot-01.png").unlink()

    assets = [
        {"asset_id": "a-01", "modality": "IMAGE", "placement_id": "beat-01",
         "path": "project://sources/shot-01.png", "sha256": None},
        {"asset_id": "a-02", "modality": "IMAGE", "placement_id": "beat-02",
         "path": "project://sources/shot-02.png", "sha256": None},
    ]
    gate_states = {"a-01": "PENDING_HUMAN_REVIEW", "a-02": "PENDING_HUMAN_REVIEW"}
    if extra_inventory:
        # Claims the same slot as a-01 and lost. It is in the inventory, and its
        # file does not exist: walking the inventory would hit it.
        assets.append(
            {"asset_id": "a-01-replaced", "modality": "IMAGE",
             "placement_id": "beat-01", "path": "project://sources/nope.png",
             "sha256": None, "derived_from": "a-01"})
        gate_states["a-01-replaced"] = "PENDING_HUMAN_REVIEW"

    manifest = {
        "schema": "contentops.media-manifest/v1",
        "narration": {},
        "scheduling": {},
        "notes": {"fixture": True},
        "counts": {"by_gate_state": gate_states},
        "timeline": [
            {"placement_id": "beat-01", "active_asset_id": "a-01",
             "selection_reason": "only gate-admissible asset claiming this placement",
             "superseded_asset_ids": ["a-01-replaced"] if extra_inventory else []},
            {"placement_id": "beat-02", "active_asset_id": "a-02",
             "selection_reason": "only gate-admissible asset claiming this placement",
             "superseded_asset_ids": []},
        ],
        "assets": assets,
    }
    (project / "receipts" / "media-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    srt = SRT_TWO_CUES if cues == 2 else SRT_TWO_CUES + """
3
00:00:05,000 --> 00:00:07,000
第三句
"""
    (project / "assets" / "captions" / "default.srt").write_text(srt, encoding="utf-8")
    (project / "receipts" / "subtitles.json").write_text(json.dumps({
        "schema": "contentops.m5-subtitles/v1",
        "path": "assets/captions/default.srt",
        "cues": cues,
    }), encoding="utf-8")
    return project


@test
def test_a_draft_is_written_from_the_accepted_timeline():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        receipt = build_handoff(project, draft_name="demo-handoff")

        assert receipt["state"] == "DRAFT_WRITTEN", receipt
        assert receipt["library"] == {
            "package": "pyJianYingDraft", "version": PINNED_VERSION,
            "license": "Apache-2.0",
            "source": "https://github.com/GuanYixuan/pyJianYingDraft",
            "vendored": False,
        }, receipt["library"]
        draft_dir = project / "work" / "jianying" / "drafts" / "demo-handoff"
        assert draft_dir.is_dir(), f"{draft_dir} was not written"
        assert (draft_dir / "draft_content.json").is_file()
        assert receipt["draft"]["path"] == "project://work/jianying/drafts/demo-handoff"
        assert receipt["draft"]["width"] == 1080 and receipt["draft"]["height"] == 1920
        assert set(receipt["draft"]["files_sha256"]) >= {"draft_content.json"}
        assert receipt["inputs"]["cues"] == 2 and receipt["inputs"]["duration_s"] == 5.0
        assert [item["placement_id"] for item in receipt["inputs"]["placements"]] == [
            "beat-01", "beat-02"]

        # The draft itself, not just our claim about it: two picture clips, two
        # subtitle clips, 1080x1920, and a 5 s timeline in microseconds.
        content = json.loads((draft_dir / "draft_content.json").read_text(encoding="utf-8"))
        tracks = {track["type"]: track.get("segments", []) for track in content["tracks"]}
        assert len(tracks["video"]) == 2, tracks
        assert len(tracks["text"]) == 2, tracks
        assert len(content["materials"]["videos"]) == 2, content["materials"]["videos"]
        assert len(content["materials"]["texts"]) == 2, content["materials"]["texts"]
        assert content["canvas_config"]["width"] == 1080
        assert content["canvas_config"]["height"] == 1920
        assert content["duration"] == 5000000, content["duration"]
        print("[ok] 1. a two-shot draft is written inside the project, with hashes")


@test
def test_the_inventory_is_not_walked():
    with tempfile.TemporaryDirectory() as temp:
        # The manifest lists a-01-replaced, whose file does not exist, claiming the
        # same slot as the winner. Only the timeline may be read.
        project = _project(Path(temp), extra_inventory=True)
        receipt = build_handoff(project, draft_name="timeline-only")
        placed = [item["asset_id"] for item in receipt["inputs"]["placements"]]
        assert placed == ["a-01", "a-02"], placed
        assert "a-01-replaced" not in json.dumps(receipt["inputs"]), (
            "a superseded inventory asset reached the draft")
        print("[ok] 2. a superseded inventory-only asset never reaches the draft")


@test
def test_one_picture_per_cue_is_required():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp), cues=3)
        try:
            build_handoff(project, draft_name="mismatch")
        except HandoffError as exc:
            assert exc.code == "TIMELINE_CUE_MISMATCH", exc.code
        else:
            raise AssertionError("2 placements and 3 cues were silently paired")
        assert not (project / "work" / "jianying").exists(), (
            "a refused handoff left a drafts folder behind")
    print("[ok] 3. a placement/cue mismatch is refused instead of distributed")


@test
def test_a_missing_shot_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp), missing_shot=True)
        try:
            build_handoff(project, draft_name="missing")
        except HandoffError as exc:
            assert exc.code == "ASSET_MISSING", exc.code
        else:
            raise AssertionError("a draft was written for a shot that does not exist")
    print("[ok] 4. a placement whose file is missing is refused")


@test
def test_a_path_outside_the_project_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        outside = Path(temp) / "outside.png"
        outside.write_bytes(PNG_1X1)
        manifest_path = project / "receipts" / "media-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["assets"][0]["path"] = "project://../outside.png"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        try:
            build_handoff(project, draft_name="escape")
        except HandoffError as exc:
            assert exc.code == "ASSET_PATH_OUTSIDE_PROJECT", exc.code
        else:
            raise AssertionError("a draft pointed at a file outside the project")
    print("[ok] 5. a path escaping the project is refused")


@test
def test_the_drafts_folder_stays_with_the_project():
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        project = _project(base)
        try:
            build_handoff(project, drafts_dir=base / "elsewhere", draft_name="outside")
        except HandoffError as exc:
            assert exc.code == "DRAFTS_OUTSIDE_PROJECT", exc.code
        else:
            raise AssertionError("the draft was written outside its project")
    print("[ok] 6. a drafts folder outside the project is refused")


@test
def test_existing_draft_needs_an_explicit_replace():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        build_handoff(project, draft_name="twice")
        try:
            build_handoff(project, draft_name="twice")
        except HandoffError as exc:
            assert exc.code == "DRAFT_EXISTS", exc.code
        else:
            raise AssertionError("a second run overwrote a draft a human may be editing")
        again = build_handoff(project, draft_name="twice", replace=True)
        assert again["state"] == "DRAFT_WRITTEN"
    print("[ok] 7. an existing draft is only replaced when asked")


@test
def test_the_handoff_never_exports_or_opens_jianying():
    # Semantic, not textual: the module docstring is allowed to *explain* that
    # export is out of scope. What must not exist is a code path that reaches it.
    source = ROOT / "src" / "contentops" / "media" / "jianying_handoff.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "JianyingController":
            offenders.append("JianyingController")
        elif isinstance(node, ast.Attribute) and node.attr in {
                "export_draft", "JianyingController"}:
            offenders.append(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = ([alias.name for alias in node.names]
                     if isinstance(node, ast.Import) else [node.module or ""])
            offenders.extend(name for name in names
                             if name.split(".")[0] == "uiautomation")
    assert not offenders, f"export machinery is reachable: {sorted(set(offenders))}"

    with tempfile.TemporaryDirectory() as temp:
        receipt = build_handoff(_project(Path(temp)), draft_name="no-export")
    assert receipt["export_performed"] is False
    assert receipt["manual_export_required"] is True
    assert receipt["production_ready"] is False
    assert receipt["publish_authorized"] is False
    assert receipt["human_review"] == "PENDING_FOUNDER_REVIEW"
    print("[ok] 8. no export path exists, and the receipt cannot claim authority")


@test
def test_a_different_library_version_is_refused():
    import importlib.metadata

    from contentops.media import jianying_handoff

    original = importlib.metadata.version
    importlib.metadata.version = lambda name: "0.0.0"
    try:
        with tempfile.TemporaryDirectory() as temp:
            try:
                build_handoff(_project(Path(temp)), draft_name="wrong-version")
            except HandoffError as exc:
                assert exc.code == "LIBRARY_VERSION_MISMATCH", exc.code
            else:
                raise AssertionError("an unpinned library version was accepted")
    finally:
        importlib.metadata.version = original
        assert jianying_handoff.PINNED_VERSION == PINNED_VERSION
    print("[ok] 9. an unpinned library version is refused")


@test
def test_the_srt_parser_refuses_a_cue_without_timing():
    try:
        parse_srt("1\nnot a time range\n文本\n")
    except HandoffError as exc:
        assert exc.code == "SUBTITLES_UNREADABLE", exc.code
    else:
        raise AssertionError("a cue with no timing was accepted")
    cues = parse_srt(SRT_TWO_CUES)
    assert [(c["start"], c["end"]) for c in cues] == [(0.0, 2.5), (2.5, 5.0)], cues
    print("[ok] 10. the cue parser refuses untimed text and keeps the real times")


def main() -> int:
    failures = []
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(TESTS)} 剪映 handoff tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
