#!/usr/bin/env python3
"""Declarative, machine-checkable stage contracts for the gate pipeline.

RC6 (weak stage contracts): the ``workflow-gates.yaml`` ``required`` field is
prose.  It tells a human what each stage must produce, but nothing in the gate
actually enforces it as data.  This module is the single source of truth for
the *structural* invariants every stage must satisfy, expressed as data so the
gate, the orchestrator, and the demo can all read the same contract.

Design:
- Each stage declares the files it must produce and the keys each file must
  carry.  ``validate_stage_contract`` returns a list of human-readable errors,
  exactly like the existing ``_errors_for_*`` checkers, so it can be merged
  into the gate without rewriting those functions.
- The contracts are intentionally a *subset/complement* of the richer semantic
  checks already in ``workflow_gate.py``.  They are mounted **additively**: the
  gate runs both, and a stage passes only when every layer agrees.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from workflow_security import load_json as strict_load_json, load_yaml as strict_load_yaml  # noqa: E402


@dataclass(frozen=True)
class FileSpec:
    path: str
    min_bytes: int = 1
    kind: str = "any"  # any | yaml | json | markdown
    required_keys: tuple[str, ...] = ()
    # Dotted JSON-path checks (e.g. "status" or "score"); value must be present
    # and, for the listed leaf keys, equal one of the allowed values.
    require_values: dict[str, tuple[str, ...]] = field(default_factory=dict)
    min_sections: int = 0  # markdown only: minimum "## " heading count


@dataclass(frozen=True)
class StageContract:
    stage: str
    label: str
    files: tuple[FileSpec, ...]


CONTRACTS: dict[str, StageContract] = {
    "environment_ready": StageContract(
        stage="environment_ready",
        label="环境与账号就绪",
        files=(
            FileSpec("article.yaml", kind="yaml", required_keys=("account", "title", "author", "content_medium")),
            FileSpec("routing.yaml", kind="yaml", required_keys=("schema_version", "status", "account_route")),
            FileSpec("capability-profile.json", kind="json", required_keys=("contract", "external_image_api_required", "selected_backends"), require_values={"contract": ("capability-profile-v1",)}),
        ),
    ),
    "topic_selected": StageContract(
        stage="topic_selected",
        label="选题确认",
        files=(
            FileSpec("topic-card.md", min_bytes=80, kind="markdown"),
            FileSpec(
                "topic-contract.yaml", kind="yaml",
                required_keys=(
                    "schema_version", "status", "canonical_topic", "topic_thesis",
                    "reader_problem", "scope", "anchor", "series", "drift_rules", "approval",
                ),
            ),
            FileSpec("topic-cluster.md", min_bytes=180, kind="markdown"),
            FileSpec(
                "article.yaml", kind="yaml",
                required_keys=("title", "author", "digest", "account"),
            ),
            FileSpec(
                "content-brief.yaml", kind="yaml",
                required_keys=(
                    "account", "audience", "primary_keyword", "shareable_angle",
                    "primary_claim", "cta", "risk_level", "human_review_required",
                ),
            ),
            FileSpec(
                "seo-report.json", kind="json",
                required_keys=("status", "score", "keywords"),
                require_values={"status": ("passed",)},
            ),
        ),
    ),
    "research_complete": StageContract(
        stage="research_complete",
        label="调研与实测完成",
        files=(
            FileSpec("research.md", min_bytes=180, kind="markdown", min_sections=0),
            FileSpec(
                "sources.json", kind="json",
                required_keys=("sources", "claims"),
            ),
            FileSpec(
                "source-verification.json", kind="json",
                required_keys=("contract", "verified_at", "sources"),
                require_values={"contract": ("source-verification-v1",)},
            ),
        ),
    ),
    "research_reviewed": StageContract(
        stage="research_reviewed",
        label="研究来源审查通过",
        files=(
            FileSpec(
                "source-review.json", kind="json",
                required_keys=("contract", "status", "sources_digest", "topic_fingerprint", "sources"),
                require_values={"contract": ("source-review-v1",), "status": ("passed",)},
            ),
        ),
    ),
    "draft_complete": StageContract(
        stage="draft_complete",
        label="初稿完成",
        files=(
            FileSpec("draft.md", min_bytes=80, kind="markdown", min_sections=3),
            FileSpec("content-revision.json", kind="json"),
        ),
    ),
    "content_reviewed": StageContract(
        stage="content_reviewed",
        label="内容审稿通过",
        files=(
            FileSpec("article.md", min_bytes=1000, kind="markdown"),
            FileSpec("review-report.md", min_bytes=300, kind="markdown"),
            FileSpec("review-checks.json", kind="json", require_values={"status": ("passed",)}),
            FileSpec("review-evidence.json", kind="json", require_values={"status": ("passed",)}),
            FileSpec("claim-verification.json", kind="json", require_values={"contract": ("claim-verification-v1",), "status": ("passed",)}),
            FileSpec("ai-disclosure.yaml", kind="yaml", require_values={"status": ("passed",)}),
            FileSpec("content-revision.json", kind="json", required_keys=("final_digest", "status")),
        ),
    ),
    "formatted": StageContract(
        stage="formatted",
        label="微信排版通过",
        files=(
            FileSpec("article.html", min_bytes=1000, kind="any"),
            FileSpec("format-report.json", kind="json", require_values={"status": ("passed",), "validator": ("passed",)}),
        ),
    ),
    "illustrated": StageContract(
        stage="illustrated",
        label="配图与素材通过",
        files=(
            FileSpec("visual-brief.yaml", kind="yaml"),
            FileSpec("image-generation-plan.json", kind="json"),
            FileSpec("visual-director-plan.json", kind="json"),
            FileSpec("image-sources.json", kind="json"),
            FileSpec("asset-index.json", kind="json", required_keys=("contract", "status", "assets"), require_values={"contract": ("asset-index-v1",), "status": ("passed",)}),
            FileSpec("vision-review.json", kind="json", required_keys=("contract", "status", "reviews"), require_values={"contract": ("vision-review-v1",), "status": ("passed", "deterministic-only")} ),
        ),
    ),
    "final_reviewed": StageContract(
        stage="final_reviewed",
        label="终审通过",
        files=(
            FileSpec("final-review.md", min_bytes=100, kind="markdown"),
            FileSpec("article_预览.html", min_bytes=500, kind="any"),
            FileSpec("preview-capture.json", kind="json", require_values={"status": ("passed",)}),
            FileSpec("preview_screenshot.png", min_bytes=1024, kind="any"),
            FileSpec("preview-fullpage.png", min_bytes=1024, kind="any"),
        ),
    ),
    "draft_submitted": StageContract(
        stage="draft_submitted",
        label="草稿提交并回读",
        files=(
            FileSpec("publish-preflight.json", kind="json", require_values={"status": ("passed",)}),
            FileSpec("publish-attempt.json", kind="json", require_values={"status": ("passed",)}),
            FileSpec("publish-receipt.json", kind="json", required_keys=("status", "mode", "media_id", "readback", "target_kind")),
        ),
    ),
}


def _read_yaml(path: Path) -> dict[str, Any]:
    value = strict_load_yaml(path, default={})
    return value if isinstance(value, dict) else {}


def _read_json(path: Path) -> Any:
    return strict_load_json(path, default=None)


def _section_count(text: str) -> int:
    return len(re.findall(r"^##\s+", text, flags=re.M))


def validate_file(article_dir: Path, spec: FileSpec) -> list[str]:
    errors: list[str] = []
    path = article_dir / spec.path
    if not path.is_file():
        errors.append(f"缺少阶段产物：{spec.path}")
        return errors
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    if size < spec.min_bytes:
        errors.append(f"{spec.path} 字节数 {size} 低于契约最低要求 {spec.min_bytes}")
    text = path.read_text(encoding="utf-8", errors="replace")

    if spec.kind == "markdown" and spec.min_sections > 0:
        if _section_count(text) < spec.min_sections:
            errors.append(
                f"{spec.path} 至少需要 {spec.min_sections} 个二级章节，"
                f"当前 {_section_count(text)} 个"
            )

    data: Any = None
    if spec.kind == "yaml":
        data = _read_yaml(path)
        if spec.required_keys and not isinstance(data, dict):
            errors.append(f"{spec.path} 不是有效的 YAML 对象")
            data = None
    elif spec.kind == "json":
        data = _read_json(path)
        if spec.required_keys and data is None:
            errors.append(f"{spec.path} 不是有效的 JSON 对象")
            data = None

    if isinstance(data, dict):
        for key in spec.required_keys:
            if key not in data or str(data.get(key, "")).strip() == "":
                errors.append(f"{spec.path} 缺少或为空字段：{key}")
        for leaf, allowed in spec.require_values.items():
            value = str(data.get(leaf, "")).strip().lower()
            if value not in {str(item).strip().lower() for item in allowed}:
                errors.append(
                    f"{spec.path} 的 {leaf} 必须是 {('/'.join(allowed))} 之一，当前为 {value!r}"
                )
    return errors


def validate_stage_contract(article_dir: Path, stage: str) -> list[str]:
    """Return structural contract errors for ``stage`` (additive to the gate)."""
    contract = CONTRACTS.get(stage)
    if contract is None:
        return []
    errors: list[str] = []
    for spec in contract.files:
        errors.extend(validate_file(article_dir, spec))
    return errors


def contract_for_stage(stage: str) -> StageContract | None:
    return CONTRACTS.get(stage)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("usage: python stage_contract.py <article_dir> <stage>")
        raise SystemExit(2)
    target = Path(sys.argv[1]).expanduser().resolve()
    issues = validate_stage_contract(target, sys.argv[2])
    if issues:
        print(f"STAGE CONTRACT FAILURES [{sys.argv[2]}]:")
        for issue in issues:
            print(f"- {issue}")
        raise SystemExit(1)
    print(f"STAGE CONTRACT PASSED: {sys.argv[2]}")
