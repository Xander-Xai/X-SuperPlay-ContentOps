#!/usr/bin/env python3
"""Create a deterministic, warning-first visual taste review receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_art_direction import canonical_visual_brief_sha


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "profiles" / "visual-taste-policy.yaml"


def _yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception:
        return {}
    if not path.is_file():
        return {}
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def _image_size(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except Exception:
        try:
            raw = path.read_bytes()
            if raw.startswith(b"\x89PNG") and len(raw) >= 24:
                return int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")
        except Exception:
            pass
    return None


def _unit_path(article_dir: Path, raw: str) -> Path:
    return (article_dir / str(raw or "").replace("\\", "/")).resolve()


def _score_axes(*, layout_count: int, backend_count: int, role_count: int, dimensions_ok: bool, art: dict[str, Any]) -> dict[str, int]:
    material = art.get("material_language") if isinstance(art.get("material_language"), list) else []
    return {
        "focal_hierarchy": 3 if layout_count >= 2 else 2,
        "composition_tension": 3 if layout_count >= 2 else 1,
        "material_depth": min(4, max(1, len(material))),
        "metaphor_isomorphism": 3 if role_count >= 2 else 2,
        "mobile_legibility": 3 if dimensions_ok else 1,
        "template_repetition": 4 if layout_count >= 2 and backend_count >= 2 else 2,
    }


def build_review(article_dir: Path, *, write: bool = True, human_approved: bool = False, human_reviewer: str = "") -> dict[str, Any]:
    article_dir = article_dir.resolve()
    policy = _yaml(POLICY_PATH)
    brief = _yaml(article_dir / "visual-brief.yaml")
    contract_path = article_dir / "visual-contract.json"
    contract: dict[str, Any] = {}
    if contract_path.is_file():
        try:
            value = json.loads(contract_path.read_text(encoding="utf-8"))
            contract = value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            contract = {}
    art_path = article_dir / "art-direction.yaml"
    art = _yaml(art_path)
    aesthetic_path = article_dir / "visual-aesthetic-review.json"
    aesthetic: dict[str, Any] = {}
    if aesthetic_path.is_file():
        try:
            value = json.loads(aesthetic_path.read_text(encoding="utf-8"))
            aesthetic = value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            aesthetic = {}
    units = [u for u in contract.get("units", []) if isinstance(u, dict) and str(u.get("id")) != "cover"]
    if not units and isinstance(brief.get("body_visuals"), list):
        units = [u for u in brief["body_visuals"] if isinstance(u, dict)]

    backends = [str(u.get("execution_backend") or u.get("render_backend") or "").strip() for u in units]
    layouts = [str(u.get("layout_archetype") or u.get("diagram_data", {}).get("layout_archetype") or u.get("visual_type") or "").strip() for u in units]
    roles = [str(u.get("cognitive_role") or "").strip() for u in units]
    sizes: list[dict[str, Any]] = []
    missing: list[str] = []
    for unit in units:
        raw = str(unit.get("asset") or unit.get("output") or "")
        path = _unit_path(article_dir, raw)
        size = _image_size(path) if path.is_file() else None
        if not path.is_file():
            missing.append(raw)
        sizes.append({"id": str(unit.get("id") or ""), "asset": raw, "exists": path.is_file(), "size": list(size) if size else None, "sha256": _sha256(path) if path.is_file() else ""})

    unique_backends = sorted({b for b in backends if b})
    unique_layouts = sorted({l for l in layouts if l})
    unique_roles = sorted({r for r in roles if r})
    dimensions = [tuple(item["size"]) for item in sizes if item.get("size")]
    dimensions_ok = bool(dimensions) and all(width >= 600 and height >= 300 for width, height in dimensions)
    warnings: list[str] = []
    errors: list[str] = list(f"素材不存在：{raw}" for raw in missing if raw)
    min_layouts = int(policy.get("min_layout_families") or 2)
    min_backends = int(policy.get("min_backend_families") or 2)
    min_roles = int(policy.get("min_cognitive_roles") or 2)
    if len(units) >= 3 and len(unique_layouts) < min_layouts:
        warnings.append(f"正文图只有 {len(unique_layouts)} 种构图族，目标至少 {min_layouts} 种")
    if len(units) >= 3 and len(unique_backends) < min_backends:
        warnings.append(f"正文图只有 {len(unique_backends)} 种实际后端，目标至少 {min_backends} 种")
    if len(units) >= 3 and len(unique_roles) < min_roles:
        warnings.append(f"正文图只有 {len(unique_roles)} 种认知角色，建议至少 {min_roles} 种")
    if not art_path.is_file():
        warnings.append("缺少 art-direction.yaml；新文章应先生成视觉论点旁路合同")
    elif art.get("contract") != "art-direction-v1":
        errors.append("art-direction.yaml contract 无效")
    elif str(art.get("source_visual_brief_sha256") or "") != canonical_visual_brief_sha(article_dir):
        warnings.append("art-direction.yaml 与 visual-brief.yaml 的 source hash 不一致")
    if not dimensions_ok and sizes:
        warnings.append("至少一张正文图无法证明满足 600x300 最小尺寸")
    if not aesthetic_path.is_file():
        warnings.append("缺少 visual-aesthetic-review.json；结构审查不能代替图面卫生审查")
    elif aesthetic.get("status") != "passed":
        errors.extend(f"客观美学卫生失败：{issue}" for issue in aesthetic.get("errors", []) if str(issue).strip())

    axes = _score_axes(layout_count=len(unique_layouts), backend_count=len(unique_backends), role_count=len(unique_roles), dimensions_ok=dimensions_ok, art=art)
    human_status = "passed" if human_approved else "pending-human"
    if errors:
        overall_status = "blocked"
    elif warnings and human_status != "passed":
        overall_status = "warning"
    elif human_status != "passed":
        overall_status = "pending-human"
    else:
        overall_status = "passed"
    result = {
        "schema_version": 1,
        "contract": "visual-taste-review-v1",
        "status": overall_status,
        "review_mode": str(policy.get("review_mode") or "warning"),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "article": str(article_dir),
        "policy": "profiles/visual-taste-policy.yaml",
        "policy_sha256": _sha256(POLICY_PATH),
        "art_direction": {"path": "art-direction.yaml", "sha256": _sha256(art_path), "status": str(art.get("status") or "missing")},
        "aesthetic_review": {"path": "visual-aesthetic-review.json", "sha256": _sha256(aesthetic_path), "status": str(aesthetic.get("status") or "missing")},
        "metrics": {
            "body_visual_count": len(units),
            "unique_execution_backends": unique_backends,
            "unique_layout_families": unique_layouts,
            "unique_cognitive_roles": unique_roles,
            "backend_diversity": round(len(unique_backends) / max(1, min(len(units), min_backends)), 3),
            "layout_diversity": round(len(unique_layouts) / max(1, min(len(units), min_layouts)), 3),
        },
        "scores": axes,
        "rubric": {
            "version": str(policy.get("rubric_version") or "visual-taste-rubric-v1"),
            "anchors": policy.get("score_anchors") if isinstance(policy.get("score_anchors"), dict) else {},
            "reviewer_id": "automated-heuristic",
            "calibration_status": "not_calibrated",
            "human_review_status": human_status,
            "human_reviewer": human_reviewer if human_approved else "",
        },
        "assets": sizes,
        "warnings": warnings,
        "errors": errors,
        "human_review_required": not human_approved,
        "note": "结构启发式只能发现硬缺陷；未有真人确认时状态为 pending-human，不得当作人眼观感通过。",
    }
    if write:
        (article_dir / "visual-taste-review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--approve-human", action="store_true", help="仅在真人完成逐图审美检查后使用")
    parser.add_argument("--reviewer-id", default="", help="真人审美复核者标识")
    args = parser.parse_args()
    if args.approve_human and not args.reviewer_id.strip():
        raise SystemExit("--approve-human 必须同时提供 --reviewer-id")
    result = build_review(args.article, write=not args.no_write, human_approved=args.approve_human, human_reviewer=args.reviewer_id)
    print(json.dumps({"status": result["status"], "warnings": result["warnings"], "errors": result["errors"]}, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
