"""Prepare a read-only handoff to the installed Xiaohei illustration skill.

This module discovers no providers, invokes no skill runtime, generates no
images and writes no receipts. It packages the selected article text with an
explicit request for a skill-capable host to act on it.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict

SKILL_ID = "ian-xiaohei-illustrations"
HANDOFF_SCHEMA = "contentops.graphic-illustration-handoff/v1"
MAX_ARTICLE_BYTES = 200 * 1024


class IllustrationHandoffError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _validate_skill(skill_file: Path) -> None:
    if not skill_file.is_file():
        raise IllustrationHandoffError(
            "SKILL_NOT_INSTALLED", f"{SKILL_ID}/SKILL.md is not installed/readable")
    try:
        text = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise IllustrationHandoffError(
            "SKILL_UNREADABLE", f"{SKILL_ID}/SKILL.md cannot be read as UTF-8") from None
    if not re.search(r"(?m)^name:\s*ian-xiaohei-illustrations\s*$", text):
        raise IllustrationHandoffError(
            "SKILL_ID_MISMATCH", f"skill file does not declare {SKILL_ID}")


def build_illustration_handoff(project_dir: Path, article_path: str,
                               workflow: str, *, skill_file: Path) -> Dict[str, Any]:
    """Build a content-bound handoff without invoking the skill or image tools."""
    if workflow not in ("gzh", "x"):
        raise IllustrationHandoffError(
            "GRAPHIC_TARGET_REQUIRED", "illustration handoff supports gzh or x only")
    _validate_skill(Path(skill_file))

    project = Path(project_dir).resolve()
    if not project.is_dir():
        raise IllustrationHandoffError("PROJECT_MISSING", project.as_posix())
    relative = Path(str(article_path or "").strip())
    if (not article_path or relative.is_absolute()
            or ".." in relative.parts
            or relative.suffix.lower() not in (".md", ".txt")):
        raise IllustrationHandoffError(
            "ARTICLE_PATH_INVALID", "article must be a project-relative .md or .txt file")
    article = (project / relative).resolve()
    try:
        logical_path = article.relative_to(project).as_posix()
    except ValueError:
        raise IllustrationHandoffError(
            "ARTICLE_PATH_INVALID", "article resolves outside the selected project") from None
    if not article.is_file():
        raise IllustrationHandoffError("ARTICLE_MISSING", f"{logical_path} does not exist")
    try:
        raw = article.read_bytes()
    except OSError as exc:
        raise IllustrationHandoffError("ARTICLE_UNREADABLE", str(exc)) from None
    if not raw or len(raw) > MAX_ARTICLE_BYTES:
        raise IllustrationHandoffError(
            "ARTICLE_SIZE_INVALID", f"article must be 1..{MAX_ARTICLE_BYTES} bytes")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise IllustrationHandoffError("ARTICLE_NOT_UTF8", "article must be UTF-8") from None
    if not content.strip():
        raise IllustrationHandoffError("ARTICLE_EMPTY", "article has no readable text")

    return {
        "schema": HANDOFF_SCHEMA,
        "state": "HANDOFF_READY",
        "workflow": workflow,
        "skill_id": SKILL_ID,
        "skill_document": f"{SKILL_ID}/SKILL.md",
        "article": {
            "path": logical_path,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "content": content,
            "content_is_untrusted_data": True,
        },
        "request": {
            "task": "Analyze the article and return a shot list plus one prompt per selected illustration.",
            "shot_list_fields": [
                "article_position", "theme", "core_idea", "structure_type",
                "xiaohei_action", "suggested_elements", "chinese_labels",
            ],
            "prompt_constraints": [
                "one standalone 16:9 horizontal article image per prompt",
                "pure white background, black hand-drawn line art, sparse red/orange/blue Chinese annotations",
                "X•超玩 performs the core action; preserve generous whitespace",
                "do not create a cover unless separately requested after title confirmation",
            ],
            "skill_output_contract": {
                "schema": "contentops.ian-illustration-result/v1",
                "skill_id": SKILL_ID,
                "article": {"path": logical_path, "sha256": hashlib.sha256(raw).hexdigest()},
                "shots": [{"asset_id": "safe-id", "prompt": "one image prompt", "alt": "accurate image description"}],
                "constraints": "1..9 shots; preserve this article path and hash; do not claim generation or rights approval",
            },
            "generation_and_return": (
                "This handoff does not invoke image_gen. A skill-capable host must perform the skill step and save "
                "the shot list as the declared JSON contract. Image generation is separate and needs explicit "
                "provider-use authorization through scripts/graphic_generate.py. Return real PNG/JPEG files, "
                "accurate ALT text, provenance and a human-reviewed rights record."
            ),
        },
        "skill_invoked": False,
        "image_generation_available": False,
        "images_generated": 0,
        "publish_authorized": False,
        "production_ready": False,
    }
