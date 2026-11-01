"""Graphic line: a manual package that cannot pretend to be published.

Run: python tests/test_graphic_workflow.py
"""

from __future__ import annotations

import base64
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.graphic import (  # noqa: E402
    GraphicPackageError,
    build_package,
    write_package,
)
from contentops.workflow.contract import (  # noqa: E402
    GRAPHIC_CONTRACT_ID,
    load_workflow,
    new_workflow,
    save_workflow,
)
from contentops.workflow.gate import approve_stage, check_stage  # noqa: E402

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _project(tmp: Path) -> Path:
    (tmp / "assets").mkdir(parents=True)
    (tmp / "assets" / "cover.png").write_bytes(PNG_1X1)
    (tmp / "assets" / "cover.rights.json").write_text(json.dumps({
        "schema": "contentops.media-rights-review/v1",
        "license_id": "OWNED-BY-OPERATOR",
        "source_url": "repo://X-SuperPlay-ContentOps#cover",
        "reviewed_by": "Xander",
        "reviewed_at": "2026-11-02",
        "attribution": "",
        "synthetic": False,
    }), encoding="utf-8")
    (tmp / "draft.md").write_text("# Test\n\nA real draft with a verified claim.\n",
                                  encoding="utf-8")
    return tmp


def _handoff(tmp: Path, platform: str = "wechat_article") -> Path:
    path = tmp / "handoff.json"
    path.write_text(json.dumps({
        "schema": "contentops.bundle-handoff/v1",
        "bundle_id": "CB-20261102-001",
        "bundle_sha256": "a" * 64,
        "content_format": "GRAPHIC_TEXT",
        "platform": {"platform_id": platform},
        "blockers": ["HOST_CAPABILITY_UNVERIFIED"],
        "publish_authorized": False,
        "human_review": "NOT_STARTED",
        "production_ready": False,
    }), encoding="utf-8")
    return path


def _input(tmp: Path, **overrides) -> Path:
    payload = {
        "title": "A verified title",
        "platform_id": "wechat_article",
        "draft": "draft.md",
        "images": [{
            "asset_id": "cover",
            "path": "assets/cover.png",
            "alt": "A one-pixel test cover",
            "rights": {
                "license_id": "OWNED-BY-OPERATOR",
                "review_evidence": "assets/cover.rights.json",
                "source_url": "repo://X-SuperPlay-ContentOps#cover",
                "reviewed_by": "Xander",
                "reviewed_at": "2026-11-02",
                "attribution": "",
                "synthetic": False,
            },
        }],
    }
    payload.update(overrides)
    path = tmp / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _raises(code, fn):
    try:
        fn()
    except GraphicPackageError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"expected GraphicPackageError {code}")


def test_valid_package_stops_for_manual_review():
    with tempfile.TemporaryDirectory() as tmp:
        project = _project(Path(tmp))
        package = build_package(project, _handoff(project), _input(project), ROOT)
        assert package["status"] == "AWAITING_MANUAL_REVIEW"
        assert package["publish_authorized"] is False
        assert package["production_ready"] is False
        assert package["images"][0]["facts"] == {"format": "png", "width": 1, "height": 1}
        assert package["platform"]["status"] == "PLANNED"
        assert "PLATFORM_PLACEHOLDER" in package["blockers"]


def test_package_writes_preview_and_receipt_inside_the_project():
    with tempfile.TemporaryDirectory() as tmp:
        project = _project(Path(tmp))
        package = build_package(project, _handoff(project), _input(project), ROOT)
        paths = write_package(project, package)
        assert paths["package"].parent == project.resolve() / "receipts"
        assert paths["workflow"] == project.resolve() / "workflow.json"
        workflow = json.loads(paths["workflow"].read_text(encoding="utf-8"))
        assert workflow["contract"] == "contentops.copy-to-graphic/v1"
        assert all(stage["status"] == "pending" for stage in workflow["stages"])
        assert (project / "02_draft" / "draft.md").is_file()
        assert (project / "05_quality" / "graphic-qc.json").is_file()
        preview = paths["preview"].read_text(encoding="utf-8")
        assert "A one-pixel test cover" in preview
        assert "publish authorized: **no**" in preview


def test_missing_rights_block_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        project = _project(Path(tmp))
        data = json.loads(_input(project).read_text(encoding="utf-8"))
        del data["images"][0]["rights"]
        bad = project / "bad.json"
        bad.write_text(json.dumps(data), encoding="utf-8")
        _raises("IMAGE_RIGHTS_MISSING", lambda: build_package(
            project, _handoff(project), bad, ROOT))


def test_missing_image_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        project = _project(Path(tmp))
        _raises("FILE_MISSING", lambda: build_package(
            project, _handoff(project),
            _input(project, images=[{
                "asset_id": "cover", "path": "assets/missing.png",
                "alt": "missing", "rights": {}}]), ROOT))


def test_image_path_cannot_escape():
    with tempfile.TemporaryDirectory() as tmp:
        project = _project(Path(tmp))
        _raises("PATH_INVALID", lambda: build_package(
            project, _handoff(project),
            _input(project, images=[{
                "asset_id": "cover", "path": "../outside.png",
                "alt": "outside", "rights": {}}]), ROOT))


def test_duplicate_image_ids_are_refused():
    with tempfile.TemporaryDirectory() as tmp:
        project = _project(Path(tmp))
        image = {
            "asset_id": "cover", "path": "assets/cover.png", "alt": "cover",
            "rights": {
                "license_id": "OWNED-BY-OPERATOR",
                "review_evidence": "assets/cover.rights.json",
                "source_url": "repo://X-SuperPlay-ContentOps#cover",
                "reviewed_by": "Xander", "reviewed_at": "2026-11-02",
                "attribution": "", "synthetic": False,
            },
        }
        _raises("IMAGE_ID_INVALID", lambda: build_package(
            project, _handoff(project), _input(project, images=[image, image]), ROOT))


def test_platform_mismatch_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        project = _project(Path(tmp))
        _raises("PLATFORM_MISMATCH", lambda: build_package(
            project, _handoff(project, "x"), _input(project), ROOT))


def test_handoff_cannot_claim_publish_authorization():
    with tempfile.TemporaryDirectory() as tmp:
        project = _project(Path(tmp))
        handoff = _handoff(project)
        payload = json.loads(handoff.read_text(encoding="utf-8"))
        payload["publish_authorized"] = True
        handoff.write_text(json.dumps(payload), encoding="utf-8")
        _raises("HANDOFF_PUBLISH_FLAG_INVALID", lambda: build_package(
            project, handoff, _input(project), ROOT))


def test_graphic_workflow_has_its_own_stages_and_cannot_borrow_video_names():
    document = new_workflow("article", "explorer", GRAPHIC_CONTRACT_ID)
    assert [stage["id"] for stage in document["stages"]] == [
        "brief", "outline", "draft", "images", "layout", "quality", "delivery"]
    assert "audio" not in [stage["id"] for stage in document["stages"]]


def test_graphic_gate_approves_in_order_and_invalidates_downstream_after_edit():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        document = new_workflow("article", "explorer", GRAPHIC_CONTRACT_ID)
        artifacts = {
            "brief": '{"topic": "test"}',
            "outline": '{"sections": ["one"]}',
            "draft": "# Draft\n\nBody.\n",
            "images": '{"images": []}',
            "layout": '{"preview": "preview.md"}',
            "quality": '{"overall": "PASS"}',
            "delivery": '{"state": "AWAITING_MANUAL_REVIEW"}',
        }
        for stage_id, text in artifacts.items():
            path = project / next(
                item["artifact"] for item in document["stages"] if item["id"] == stage_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            result = check_stage(project, document, stage_id)
            assert result["ok"], result
            approve_stage(project, document, stage_id, "Xander", confirm=True)
        save_workflow(project / "workflow.json", document)

        (project / "02_draft" / "draft.md").write_text("# Changed\n", encoding="utf-8")
        loaded = load_workflow(project / "workflow.json")
        result = check_stage(project, loaded, "images")
        assert not result["ok"]
        assert any("draft" in error for error in result["errors"])


def test_repo_owned_image_is_recorded_logically():
    with tempfile.TemporaryDirectory() as tmp:
        project = _project(Path(tmp))
        rights = project / "assets" / "repo.rights.json"
        rights.write_text(json.dumps({
            "schema": "contentops.media-rights-review/v1",
            "license_id": "OWNED-BY-OPERATOR",
            "source_url": "repo://X-SuperPlay-ContentOps#screenshot",
            "reviewed_by": "Xander",
            "reviewed_at": "2026-11-02",
            "attribution": "",
            "synthetic": False,
        }), encoding="utf-8")
        data = {
            "title": "Repo evidence",
            "platform_id": "wechat_article",
            "draft": "draft.md",
            "images": [{
                "asset_id": "version_evidence",
                "path": "repo://projects/easel-review/sources/screenshots/12-easel-version-evidence.png",
                "alt": "Pinned Easel version evidence",
                "rights": {
                    "license_id": "OWNED-BY-OPERATOR",
                    "review_evidence": "assets/repo.rights.json",
                    "source_url": "repo://X-SuperPlay-ContentOps#screenshot",
                    "reviewed_by": "Xander",
                    "reviewed_at": "2026-11-02",
                    "attribution": "",
                    "synthetic": False,
                },
            }],
        }
        input_path = project / "repo-input.json"
        input_path.write_text(json.dumps(data), encoding="utf-8")
        package = build_package(project, _handoff(project), input_path, ROOT, ROOT)
        assert package["images"][0]["path"].startswith("repo://projects/easel-review/")
        assert package["images"][0]["scope"] == "repo"


def test_repo_path_cannot_escape_the_repository():
    with tempfile.TemporaryDirectory() as tmp:
        project = _project(Path(tmp))
        _raises("PATH_INVALID", lambda: build_package(
            project, _handoff(project),
            _input(project, images=[{
                "asset_id": "escape", "path": "repo://../outside.png",
                "alt": "escape", "rights": {}}]), ROOT, ROOT))


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {test.__name__}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
