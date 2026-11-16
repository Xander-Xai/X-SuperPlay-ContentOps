"""Register one generated clip the way M5 already accepts visual support.

This is the shared inventory step. It does not render, does not approve, and
does not treat the file as a screen recording.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from contentops.media.image_contract import AssetKind, AssetRegistry, EvidenceUse
from contentops.media.media_envelope import (
    HUMAN_REVIEW_PENDING,
    TECHNICAL_PASS,
    MediaAssetEnvelope,
    MediaModality,
)
from contentops.media.quality_gate import AssetQualityGate, build_manifest
from contentops.paths import relative_label


def _read(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def register_generated_clip(
    *,
    project: Path,
    repo_root: Path,
    asset_id: str,
    placement_id: str,
    output: Path,
    sha256: str,
    fingerprint: str,
    backend: str,
    receipt_name: str,
) -> Dict[str, Any]:
    """Write the inventory rows a later stage_assets / storyboard can verify."""
    logical = f"project://{output.resolve().relative_to(project.resolve()).as_posix()}"
    repo_path = relative_label(output, repo_root)
    registry = AssetRegistry()
    registry.register(
        asset_id=asset_id,
        kind=AssetKind.GENERATED_VIDEO,
        path=logical,
        evidence_use=EvidenceUse.VISUAL_SUPPORT,
        receipt_ref=receipt_name,
        sha256=sha256,
        notes={"adapter": backend, "placement_id": placement_id},
    )
    registry.assert_evidence_boundary()
    envelope = MediaAssetEnvelope(
        asset_id=asset_id,
        modality=MediaModality.VIDEO,
        path=logical,
        sha256=sha256,
        receipt_ref=receipt_name,
        fingerprint=fingerprint,
        asset_kind=AssetKind.GENERATED_VIDEO,
        generated=True,
        evidence_capable=False,
        evidence_use=EvidenceUse.VISUAL_SUPPORT,
        claim_refs=[],
        technical_status=TECHNICAL_PASS,
        human_review=HUMAN_REVIEW_PENDING,
        production_ready=False,
        placement_id=placement_id,
    )
    gate = AssetQualityGate().evaluate(envelope, repo_root=repo_root, project_root=project)
    if gate.blocked:
        raise ValueError("ASSET_GATE_BLOCKED: " + "; ".join(gate.reasons))
    manifest_path = project / "work" / "m45" / f"{backend}-media-manifest.json"
    build_manifest(
        [envelope], [gate],
        notes={"source": f"{backend} local clip render", "production_ready": False,
               "human_review": HUMAN_REVIEW_PENDING},
    ).write(manifest_path)

    sources_path = project / "sources" / "assets.json"
    sources = _read(sources_path)
    assets = list(sources.get("assets") or [])
    entry = {
        "id": asset_id,
        "type": "GENERATED_VIDEO",
        "repo_path": repo_path,
        "sha256": sha256,
        "permission": "CREATED_BY_OWNER",
        "usage_scope": "VISUAL_SUPPORT only",
        "origin": f"{backend} local code render",
        "generated": True,
        "evidence_capable": False,
        "notes": "Generated visual; not source evidence.",
    }
    replaced = False
    for index, old in enumerate(assets):
        if old.get("id") == asset_id:
            if old.get("repo_path") not in (None, repo_path) and old.get("sha256") not in (None, sha256):
                if old.get("repo_path") != repo_path:
                    raise ValueError(f"ASSET_ID_COLLISION:{asset_id}")
            assets[index] = {**old, **entry}
            replaced = True
            break
    if not replaced:
        assets.append(entry)
    sources["assets"] = assets
    if "schema" not in sources:
        sources["schema"] = "contentops.m5-source-assets/v1"
    _write(sources_path, sources)

    script_path = project / "script" / "assets.json"
    script_assets = _read(script_path)
    mapped = script_assets.get("assets")
    if not isinstance(mapped, dict):
        mapped = {}
    mapped[asset_id] = {
        "path": logical,
        "sha256": sha256,
        "evidence_use": "VISUAL_SUPPORT",
        "generated": True,
    }
    script_assets["assets"] = mapped
    if "schema" not in script_assets:
        script_assets["schema"] = "contentops.m5-script-assets/v1"
    _write(script_path, script_assets)
    return {
        "repo_path": repo_path,
        "logical": logical,
        "gate_state": gate.state,
        "manifest": f"project://{manifest_path.resolve().relative_to(project.resolve()).as_posix()}",
        "generated": True,
        "evidence_capable": False,
    }
