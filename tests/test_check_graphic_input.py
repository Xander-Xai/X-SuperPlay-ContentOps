"""Preflight must catch, in one pass, the data faults that make graphic
packaging fail one error at a time: a missing copy review, an image_method that
disagrees with the assets, a corrupted generation receipt, and rights/evidence
date drift. It is read-only and must never write an approval or edit a project.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "check_graphic_input", ROOT / "scripts" / "check_graphic_input.py")
assert _spec and _spec.loader
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)

HEX = "a" * 64
PROMPT = "b" * 64


def _codes(result: dict) -> set[str]:
    return {p["code"] for p in result["problems"]}


def _base_project(tmp: Path, *, method: str = "codex_imagegen",
                  with_generation: bool = True, reviewed_at: str = "2026-11-23") -> Path:
    """A minimal, otherwise-valid GRAPHIC_TEXT project under a projects/ parent."""
    project = tmp / "projects" / "demo-graphic"
    (project / "receipts").mkdir(parents=True)
    (project / "assets").mkdir()
    (project / "draft.md").write_text("# Title\n\nBody.\n", encoding="utf-8")
    # Keep the exact prompt that produced the image, so its hash matches the
    # receipt (PROMPT below). This is the "prompt is traceable" contract.
    prompts_dir = project / "03_images" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "shot-01.md").write_text(PROMPT + "\n", encoding="utf-8")

    # rights evidence file (the source of truth validators compare against)
    rights_record = {
        "schema": "contentops.media-rights-review/v1",
        "license_id": "GENERATED-REMOTE-REVIEWED",
        "source_url": "https://openai.com/policies/terms-of-use/",
        "reviewed_by": "Founder",
        "reviewed_at": reviewed_at,
        "attribution": "generated for this draft",
        "synthetic": True,
        "generation_id": "gen1",
        "asset_sha256": HEX,
        "terms_url": "https://openai.com/policies/terms-of-use/",
        "terms_effective_date": "2024-12-01",
        "permitted_use": "support illustration in this unpublished draft only",
        "review_scope": "this exact image; not publication approval",
    }
    (project / "assets" / "rights.json").write_text(
        json.dumps(rights_record, ensure_ascii=False, indent=2), encoding="utf-8")

    image = {
        "asset_id": "comic",
        "path": "assets/comic.png",
        "alt": "A support illustration.",
        "rights": {
            "license_id": "GENERATED-REMOTE-REVIEWED",
            "source_url": "https://openai.com/policies/terms-of-use/",
            "reviewed_by": "Founder",
            "reviewed_at": reviewed_at,
            "review_evidence": "assets/rights.json",
            "attribution": "generated for this draft",
            "synthetic": True,
        },
    }
    if with_generation:
        image["generation"] = {"generation_id": "gen1", "receipt": "receipts/gen.json"}
        receipt = {
            "schema": "contentops.graphic-image-generation/v1",
            "generation_id": "gen1", "method": "codex_imagegen",
            "provider": "openai-codex", "prompt_sha256": checker.prompt_sha256(PROMPT),
        }
        (project / "receipts" / "gen.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")

    inp = {"schema": "contentops.graphic-input/v1", "title": "Title",
           "platform_id": "wechat_article", "account": "thinktank",
           "image_method": method, "draft": "draft.md", "images": [image]}
    (project / "graphic-input.json").write_text(
        json.dumps(inp, ensure_ascii=False, indent=2), encoding="utf-8")
    return project


def test_flags_missing_copy_review_as_human_step() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = _base_project(Path(tmp))
        result = checker.check(project)
        assert "COPY_REVIEW_NOT_REVIEWED" in _codes(result)
        step = next(p for p in result["problems"] if p["code"] == "COPY_REVIEW_NOT_REVIEWED")
        assert step["level"] == "human"
        assert "copy_review.py" in step["remedy"]
        assert result["ok"] is True  # no *block* problems; review is a human gate, not corruption


def test_flags_generation_method_without_receipt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = _base_project(Path(tmp), method="codex_imagegen", with_generation=False)
        result = checker.check(project)
        assert "GENERATION_RECEIPT_REQUIRED" in _codes(result)
        assert not result["ok"]


def test_flags_corrupted_prompt_digest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = _base_project(Path(tmp))
        gen_path = project / "receipts" / "gen.json"
        gen = json.loads(gen_path.read_text(encoding="utf-8"))
        gen["prompt_sha256"] = "z" * 65  # invalid chars and wrong length
        gen_path.write_text(json.dumps(gen), encoding="utf-8")
        result = checker.check(project)
        assert "PROMPT_DIGEST_INVALID" in _codes(result)
        assert not result["ok"]


def test_flags_rights_date_drift_between_input_and_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = _base_project(Path(tmp), reviewed_at="2026-11-23")
        inp_path = project / "graphic-input.json"
        inp = json.loads(inp_path.read_text(encoding="utf-8"))
        inp["images"][0]["rights"]["reviewed_at"] = "2026-11-25"  # drift from evidence file
        inp_path.write_text(json.dumps(inp, ensure_ascii=False, indent=2), encoding="utf-8")
        result = checker.check(project)
        assert "IMAGE_RIGHTS_INVALID" in _codes(result)
        assert not result["ok"]


def test_flags_prompt_not_archived() -> None:
    """A generated image must have its exact prompt kept in the project.

    Otherwise an image generated from a prompt unrelated to the article could be
    packaged and the reviewer could not tell what the image was actually based on.
    """
    with tempfile.TemporaryDirectory() as tmp:
        project = _base_project(Path(tmp))
        (project / "03_images" / "prompts" / "shot-01.md").unlink()
        result = checker.check(project)
        assert "PROMPT_NOT_ARCHIVED" in _codes(result)
        assert not result["ok"]


def test_reports_handoff_blockers_as_info_not_block() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = _base_project(Path(tmp))
        handoff = {"schema": "contentops.bundle-handoff/v1", "state": "READY_FOR_MANUAL_PACKAGE",
                   "blockers": ["PLATFORM_PLACEHOLDER", "HOST_CAPABILITY_UNVERIFIED"]}
        (project / "receipts" / "bundle-handoff-graphic_text.json").write_text(
            json.dumps(handoff), encoding="utf-8")
        result = checker.check(project)
        info = next(p for p in result["problems"] if p["code"] == "DELIVERY_BLOCKERS_PRESENT")
        assert info["level"] == "info"
        assert result["ok"] is True  # blockers do not block packaging; only delivery
