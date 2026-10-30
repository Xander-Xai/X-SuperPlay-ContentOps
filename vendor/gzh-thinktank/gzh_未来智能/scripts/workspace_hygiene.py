#!/usr/bin/env python3
"""Clean-room workspace and split-manifest integrity checks.

The workflow must not silently consume ignored files, stale temporary recipes,
or a manifest whose hashes describe an older revision.  This module is shared
by the static validator and the explicit refresh command so the policy has one
implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from workflow_security import load_json as strict_load_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "split-manifest.json"
OLD_TOPIC_MARKERS = (
    "20260809-混合专家模型-moe-原理-训练与部署全解",
    "drafts/20260809-混合专家模型-moe-原理-训练与部署全解",
)
ROOT_ALLOWED = {
    ".aws-article", "inbox", "integrations",
    "opc-doc", "docs", "profiles", "reports", "scripts", "skills", ".superpowers", "AGENTS.md",
    "README.md", "THIRD_PARTY_NOTICES.md", "workflow-identity.yaml", "requirements-workflow.txt", "tests", "topics",
    "split-manifest.json", "workspace-contract.yaml", ".gitignore",
}
EXCLUDED_PARTS = {".git", "node_modules", "__pycache__", "drafts", "reports", "skills/_archive"}
SKILL_MANIFEST_PREFIXES = tuple(
    f"skills/{name}/" for name in (
        "ai-thinktank-workflow", "gzh-article-orchestrator", "gzh-topic-research",
        "gzh-title-seo", "wechat-seo-optimizer", "gzh-article-writing",
        "gzh-editorial-review", "gzh-article-format", "gzh-visual-assets",
        "gzh-visual-director", "gzh-draft-publisher", "gzh-article-assets",
        "gzh-design-skill", "vision", "formula-rendering", "beautiful-mermaid",
        "excalidraw-diagram", "content-strategy", "opc-conversion-loop",
        "wechat-svg-interactive", "agnes-image-21-flash", "source-evidence-layer",
    )
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_manifest_payload(doc: dict[str, Any]) -> bytes:
    payload = dict(doc)
    payload.pop("manifest_sha256", None)
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _manifest_rows(doc: dict[str, Any]) -> list[dict[str, Any]]:
    rows = doc.get("files")
    return [row for row in rows if isinstance(row, dict) and str(row.get("path", "")).strip()] if isinstance(rows, list) else []


def _normalise_rel(raw: str) -> str:
    value = str(raw or "").replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def manifest_errors(root: Path = ROOT) -> list[str]:
    path = root / "split-manifest.json"
    if not path.is_file():
        return ["缺少 split-manifest.json"]
    doc = strict_load_json(path, default=None)
    if not isinstance(doc, dict):
        return ["split-manifest.json 无法解析或包含重复键"]
    errors: list[str] = []
    recorded_manifest_hash = str(doc.get("manifest_sha256", "")).strip().lower()
    actual_manifest_hash = sha256_bytes(canonical_manifest_payload(doc))
    if recorded_manifest_hash != actual_manifest_hash:
        errors.append("split-manifest.json 的 manifest_sha256 与内容不一致")
    rows = _manifest_rows(doc)
    if not rows:
        errors.append("split-manifest.json 没有 files allowlist")
    seen: set[str] = set()
    for row in rows:
        rel = _normalise_rel(row.get("path", ""))
        if rel in seen:
            errors.append(f"split-manifest.json 存在重复路径：{rel}")
            continue
        seen.add(rel)
        target = root / rel
        if not target.is_file():
            errors.append(f"manifest allowlist 文件不存在：{rel}")
            continue
        try:
            actual_size = target.stat().st_size
            actual_hash = sha256_file(target)
        except OSError as exc:
            errors.append(f"无法读取 manifest 文件 {rel}：{exc}")
            continue
        if int(row.get("size", -1)) != actual_size or str(row.get("sha256", "")).lower() != actual_hash:
            errors.append(f"manifest hash drift：{rel}")
    return errors


def manifest_signature_errors(root: Path = ROOT, *, required: bool = False) -> list[str]:
    """Verify an optional external HMAC signature over the manifest payload.

    The signature is an integrity boundary only; it is not a human identity
    proof.  Public publishing can require it when the workspace has no Git
    history or other immutable source anchor.
    """

    signature_raw = os.environ.get("WORKFLOW_MANIFEST_SIGNATURE_PATH", "").strip()
    key_raw = os.environ.get("WORKFLOW_MANIFEST_SIGNATURE_KEY_PATH", "").strip()
    if not signature_raw and not key_raw and not required:
        return []
    if not signature_raw or not key_raw:
        return ["缺少 WORKFLOW_MANIFEST_SIGNATURE_PATH/WORKFLOW_MANIFEST_SIGNATURE_KEY_PATH"]
    signature_path = Path(signature_raw).expanduser().resolve()
    key_path = Path(key_raw).expanduser().resolve()
    for candidate, label in ((signature_path, "manifest signature"), (key_path, "manifest key")):
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            pass
        else:
            return [f"{label} 必须位于仓库外"]
        if not candidate.is_file():
            return [f"{label} 文件不存在"]
    signature = strict_load_json(signature_path, default=None)
    if not isinstance(signature, dict) or signature.get("contract") != "split-manifest-signature-v1":
        return ["manifest signature contract 无效或包含重复键"]
    doc = strict_load_json(root / "split-manifest.json", default=None)
    if not isinstance(doc, dict):
        return ["无法为 manifest signature 读取 split-manifest.json"]
    manifest_hash = str(doc.get("manifest_sha256") or "").lower()
    if str(signature.get("manifest_sha256") or "").lower() != manifest_hash:
        return ["manifest signature 绑定的 manifest_sha256 不一致"]
    try:
        key = key_path.read_bytes()
        expected = hmac.new(key, canonical_manifest_payload(doc), hashlib.sha256).hexdigest()
    except OSError:
        return ["manifest signature key 无法读取"]
    if not hmac.compare_digest(str(signature.get("signature") or ""), expected):
        return ["manifest signature HMAC 不匹配"]
    return []


def _iter_scan_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = set(path.relative_to(root).parts)
        if ".git" in rel_parts or "node_modules" in rel_parts or "__pycache__" in rel_parts:
            continue
        if "drafts" in rel_parts or "reports" in rel_parts or "_archive" in rel_parts or path.name == "workspace_hygiene.py" or path.name.startswith("test_"):
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith("skills/") and not rel.startswith(SKILL_MANIFEST_PREFIXES):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".ttf", ".woff", ".woff2", ".mp4"}:
            continue
        yield path


def workspace_errors(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for child in root.iterdir():
        if child.name not in ROOT_ALLOWED:
            errors.append(f"根目录存在未登记文件或目录：{child.name}")
    legacy_drafts = root / "drafts"
    if legacy_drafts.exists():
        try:
            legacy_items = list(legacy_drafts.iterdir())
        except OSError:
            legacy_items = [legacy_drafts]
        if legacy_items:
            errors.append(
                "仓库根 drafts/ 含有作品或过程文件；必须迁移到外部 "
                "GZH_ARTIFACT_ROOT/active，禁止继续写入"
            )
        else:
            errors.append("仓库根 drafts/ 目录是遗留入口；请删除并使用外部 artifact root")
    for path in _iter_scan_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(marker in text for marker in OLD_TOPIC_MARKERS):
            errors.append(f"工作流文件残留旧主题硬编码：{path.relative_to(root)}")
    return errors


def external_workspace_errors() -> list[str]:
    """Include the external registry audit when an artifact root exists."""
    try:
        from workspace_audit import audit
        from workspace_paths import artifact_root
        base = artifact_root(create=False)
        if not base.exists():
            return []
        return [f"external workspace: {item}" for item in audit(base)]
    except (ImportError, OSError, ValueError):
        return []


def _candidate_paths(root: Path, existing: list[dict[str, Any]]) -> list[Path]:
    paths: dict[str, Path] = {}
    for row in existing:
        rel = _normalise_rel(row.get("path", ""))
        if rel == "split-manifest.json":
            continue
        if rel.startswith("asset-library/"):
            continue
        if rel.startswith("skills/") and not rel.startswith(SKILL_MANIFEST_PREFIXES):
            continue
        target = root / rel
        if target.is_file():
            paths[rel] = target
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == "split-manifest.json":
            continue
        if rel.startswith("asset-library/"):
            continue
        parts = set(path.relative_to(root).parts)
        if ".git" in parts or "node_modules" in parts or "__pycache__" in parts:
            continue
        if "drafts" in parts or "reports" in parts or "_archive" in parts:
            continue
        if rel.startswith("skills/") and not rel.startswith(SKILL_MANIFEST_PREFIXES):
            continue
        # The split manifest is an execution contract, not a dump of every
        # third-party skill dependency.  Expand only first-party workflow
        # surfaces; the skill catalog is checked separately by registry and
        # required-file contracts.
        if len(parts) > 1 and not (parts & {"scripts", "profiles", "integrations", ".aws-article", "opc-doc"}):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".ttf", ".woff", ".woff2", ".mp4", ".env"}:
            continue
        paths[rel] = path
    return [paths[key] for key in sorted(paths)]


def refresh_manifest(root: Path = ROOT) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    if (root / "split-manifest.json").is_file():
        try:
            existing = json.loads((root / "split-manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    rows = []
    for path in _candidate_paths(root, _manifest_rows(existing)):
        rel = path.relative_to(root).as_posix()
        rows.append({"path": rel, "size": path.stat().st_size, "sha256": sha256_file(path)})
    doc: dict[str, Any] = {
        "schema_version": 3,
        "workflow": "thinktank",
        "target_id": "gzh-thinktank",
        "source_id": "gzh-source-snapshot",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "build_mode": "post-approval-hardening",
        "workflow_revision": sha256_bytes(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")),
        "excluded": ["absolute source/target paths", "aws.env", ".env", "__pycache__", "*.pyc", "node_modules", ".venv", "nested .git", "drafts", "reports"],
        "files": rows,
    }
    doc["manifest_sha256"] = sha256_bytes(canonical_manifest_payload(doc))
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="检查 manifest 与 workspace，不写文件")
    parser.add_argument("--write", action="store_true", help="重建 split-manifest.json")
    parser.add_argument("--require-external-signature", action="store_true", help="要求仓库外 manifest HMAC 签名")
    args = parser.parse_args()
    if args.write:
        doc = refresh_manifest(ROOT)
        MANIFEST.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"MANIFEST REFRESHED: {len(doc['files'])} files")
    errors = manifest_errors(ROOT) + workspace_errors(ROOT) + external_workspace_errors() + manifest_signature_errors(ROOT, required=args.require_external_signature)
    if errors:
        print("WORKSPACE HYGIENE BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("WORKSPACE HYGIENE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
