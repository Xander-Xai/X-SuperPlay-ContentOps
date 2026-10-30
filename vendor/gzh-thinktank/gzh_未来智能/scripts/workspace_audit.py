#!/usr/bin/env python3
"""Audit the external article-workspace boundary and lifecycle registry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from workspace_paths import (
    LIFECYCLE_DIRS,
    WORKSPACE_DIRS,
    WORKSPACE_ID_RE,
    WORKSPACE_SCHEMA,
    artifact_root,
)


ROOT_ARTIFACT_NAMES = {
    "workspace-manifest.json", "article.yaml", "matrix-state.json", "routing.yaml",
    "topic-card.md", "topic-contract.yaml", "topic-cluster.md", "content-calendar.md",
    "topic-integrity.json", "content-brief.yaml", "cta-contract.json", "seo-report.json",
    "research.md", "sources.json", "source-verification.json", "source-review.json", "source-evidence.json",
    "evidence-plan.json", "evidence-provenance.json", "evidence-lineage.json",
    "topic-evidence-isolation.json", "draft.md", "content-revision.json", "review-report.md",
    "review-evidence.json", "review-checks.json", "content-truth-qa.json", "claim-verification.json",
    "fact-review.json", "ai-disclosure.yaml", "article.md", "article.html", "format-report.json",
    "visual-brief.yaml", "visual-routing.json", "skill-evaluation.json", "image-plan.md",
    "visual-director-plan.json", "visual-director-plan.md", "image-generation-plan.json",
    "img_analysis.md", "image-sources.json", "asset-index.json", "visual-semantic-review.json",
    "visual-content-qa.json", "visual-depth-review.json", "visual-reader-test.json", "vision-review.json",
    "visual-aesthetic-review.json", "visual-contract-audit.json", "visual-route-consistency.json",
    "visual-run-manifest.jsonl", "visual-taste-review.json", "workflow-status.json",
    "checkpoint-manifest.json", "formula-manifest.json", "closing.md", "handoff-card.md",
    "final-review.md", "preview-capture.json", "publish-preflight.json",
    "publish-attempt.json", "publish-receipt.json", "publish-result.json", "metrics.json",
    "approval-events.json", "capability-profile.json", "art-direction.yaml", "visual-contract.json",
    "article_预览.html", "preview_screenshot.png", "preview-fullpage.png", ".matrix-state.lock",
}
ROOT_ARTIFACT_PREFIXES = ("README",)
ROOT_ARTIFACT_DIRS = {"work", "exports", "snapshots", "evidence", "source-snapshots", "imgs", "preview-slices", "formula-src", ".tmp-formulas"}


def audit(root: Path | None = None) -> list[str]:
    root = (root or artifact_root(create=False)).resolve()
    errors: list[str] = []
    if not root.exists():
        return [f"artifact root missing: {root}"]
    for name in (*LIFECYCLE_DIRS, "registry", "inbox", "tmp"):
        if not (root / name).is_dir():
            errors.append(f"artifact root missing directory: {name}")
    registry_path = root / "registry" / "workspace-index.json"
    if not registry_path.is_file():
        errors.append("missing registry/workspace-index.json")
        return errors
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"invalid workspace registry: {exc}"]
    if registry.get("contract") != "workspace-index-v1":
        errors.append("workspace registry contract mismatch")
    registered: set[Path] = set()
    for entry in registry.get("workspaces", []):
        if not isinstance(entry, dict):
            errors.append("workspace registry contains non-object entry")
            continue
        workspace_id = str(entry.get("workspace_id", ""))
        if not WORKSPACE_ID_RE.fullmatch(workspace_id):
            errors.append(f"invalid workspace id: {workspace_id}")
        relative = str(entry.get("relative_path", ""))
        path = (root / relative).resolve()
        registered.add(path)
        try:
            path.relative_to(root)
        except ValueError:
            errors.append(f"workspace escapes artifact root: {workspace_id}")
            continue
        if not path.is_dir():
            errors.append(f"registered workspace missing: {workspace_id}")
            continue
        for required_dir in WORKSPACE_DIRS:
            if not (path / required_dir).is_dir():
                errors.append(f"workspace missing standard directory: {workspace_id}/{required_dir}")
        manifest_path = path / "workspace-manifest.json"
        if not manifest_path.is_file():
            errors.append(f"workspace missing manifest: {workspace_id}")
        else:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                manifest = {}
            if manifest.get("contract") != WORKSPACE_SCHEMA or manifest.get("workspace_id") != workspace_id:
                errors.append(f"workspace manifest mismatch: {workspace_id}")
        if str(entry.get("lifecycle", "active")) not in LIFECYCLE_DIRS:
            errors.append(f"invalid lifecycle value: {workspace_id}")
        if path.parent.name in LIFECYCLE_DIRS and path.parent.name != str(entry.get("lifecycle", "active")):
            errors.append(f"workspace lifecycle path mismatch: {workspace_id}")
        if manifest_path.is_file() and isinstance(manifest, dict):
            if str(manifest.get("relative_path", "")) != relative:
                errors.append(f"workspace manifest relative_path mismatch: {workspace_id}")
            if str(manifest.get("lifecycle", "active")) != str(entry.get("lifecycle", "active")):
                errors.append(f"workspace manifest lifecycle mismatch: {workspace_id}")
        for child in path.iterdir():
            if child.is_dir() and child.name in ROOT_ARTIFACT_DIRS:
                continue
            if child.is_file() and (child.name in ROOT_ARTIFACT_NAMES or child.name.startswith(ROOT_ARTIFACT_PREFIXES)):
                continue
            if child.name == "workspace-manifest.json":
                continue
            errors.append(f"unclassified workspace root output: {path.name}/{child.name}")
    for lifecycle in LIFECYCLE_DIRS:
        parent = root / lifecycle
        if not parent.is_dir():
            continue
        for candidate in parent.iterdir():
            if candidate.is_dir() and candidate.name.startswith("THK-") and candidate.resolve() not in registered:
                errors.append(f"unregistered workspace directory: {lifecycle}/{candidate.name}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="显式执行审计（默认行为，便于统一门禁命令）")
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args()
    errors = audit(args.root)
    if errors:
        print("WORKSPACE AUDIT BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    root = (args.root or artifact_root(create=False)).resolve()
    print(f"WORKSPACE AUDIT PASSED: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
