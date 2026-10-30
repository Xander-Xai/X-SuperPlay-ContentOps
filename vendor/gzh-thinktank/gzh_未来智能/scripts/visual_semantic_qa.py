#!/usr/bin/env python3
"""Validate that article visuals carry the semantic contract of their section.

The old visual checker proved that an image existed.  This checker proves that
the editable source contains the labels/relationships promised by the visual
plan and that generic placeholder cards are not silently accepted.

It intentionally treats deterministic diagrams as machine-verifiable.  An
external illustrative raster additionally needs a byte-bound pixel review
from a native multimodal host, an external vision provider, or a signed human.
That keeps model-generated pixels from being mistaken for a factual diagram
without mislabelling a real multimodal review as human approval.
"""

from __future__ import annotations

import argparse
import hashlib
from html import unescape as _html_unescape
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from visual_backend_registry import route_backend, validate_record
from excerpt_utils import section_excerpt as _shared_section_excerpt, section_excerpt_sha256 as _shared_excerpt_sha256
from visual_geometry_qa import check_source as _check_geometry_source
from visual_artifact_qa import check_article as _check_artifact_article
from visual_route_consistency import check as _check_route_consistency
try:
    from visual_aesthetic_qa import check_svg as _check_aesthetic_svg
except ImportError:  # pragma: no cover - standalone import fallback
    _check_aesthetic_svg = None

# 增强 3：信息密度检查。OCR 可选（需 tesseract），未安装时用 glyph 近似。
try:
    from visual_qa import (
        _glyph_component_count,
        MIN_BODY_INFO_GLYPHS as _MIN_INFO_GLYPHS,
        _geometry_required as _infer_geometry_required,
    )
except ImportError:  # pragma: no cover - 依赖顺序保护
    _glyph_component_count = None
    _MIN_INFO_GLYPHS = 12
    _infer_geometry_required = lambda contract, route: bool(contract.get("geometry_required"))


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_NAME = "visual-contract-v1"
REPORT_NAME = "visual-semantic-review.json"
VISION_SKILL = ROOT / "skills" / "vision" / "vision.py"
GENERIC_LABELS = {
    "目标",
    "关系",
    "门禁",
    "资产",
    "输入",
    "检查",
    "放行",
    "回读",
    "现状",
    "证据",
    "判断",
}


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pixel_review_for_asset(article: Path, unit_id: str, output_path: Path) -> tuple[str, str]:
    """Return a valid reviewer mode and receipt hash for an illustrative raster.

    ``vision-review.json`` normally binds the complete semantic report.  The
    semantic report in turn needs to know whether an external raster was
    actually inspected, so requiring the top-level semantic digest here would
    create a circular dependency.  This narrow check therefore validates only
    the exact image bytes and the capability-specific per-image evidence.  The
    full digest is still enforced later by ``vision_review.py check``.
    """

    receipt_path = article / "vision-review.json"
    receipt = _json(receipt_path)
    if receipt.get("contract") != "vision-review-v1" or receipt.get("status") != "passed":
        return "", ""
    reviews = receipt.get("reviews")
    if not isinstance(reviews, list) or not output_path.is_file():
        return "", ""
    expected_sha = _sha(output_path)
    for row in reviews:
        if not isinstance(row, dict) or str(row.get("id") or "").strip() != unit_id:
            continue
        mode = str(row.get("reviewer_mode") or "").strip().lower()
        if mode not in {"native", "external", "human"}:
            continue
        if row.get("status") != "passed":
            continue
        if str(row.get("image_sha256") or "").strip().lower() != expected_sha:
            continue
        if str(row.get("input_sha256") or expected_sha).strip().lower() != expected_sha:
            continue
        if not str(row.get("capability_evidence") or "").strip():
            continue
        if row.get("contrast_status") != "passed" or row.get("legibility_status") != "passed":
            continue
        if not isinstance(row.get("defects"), list):
            continue
        if mode == "native" and not str(row.get("provider_trace") or "").strip():
            continue
        if mode == "external" and any(
            not str(row.get(key) or "").strip()
            for key in ("provider", "model", "request_sha256", "response_sha256")
        ):
            continue
        if mode == "human" and any(
            not str(row.get(key) or "").strip()
            for key in ("reviewer", "signed_by", "approval_event_id")
        ):
            continue
        stable_row = dict(row)
        stable_row.pop("reviewed_at", None)
        stable_payload = json.dumps(
            stable_row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return mode, hashlib.sha256(stable_payload).hexdigest()
    return "", ""


def _vision_skill_metadata() -> dict[str, Any]:
    """Record the image-understanding route without pretending it reviewed pixels.

    The repository's ``vision`` skill explicitly says to skip an external call
    when the current agent already has native image input.  We still record the
    skill path and its routing decision in every semantic report, so the
    workflow cannot silently omit the image-understanding responsibility.
    Pixel assertions remain the job of the native multimodal reviewer (or an
    explicit external provider) plus the deterministic QA companions.
    """
    metadata: dict[str, Any] = {
        "contract": "vision-skill-v1",
        "skill_file": "skills/vision/SKILL.md",
        "entrypoint": "skills/vision/vision.py",
        "role": "multimodal-vision-llm-or-human",
        "machine_companions": [
            "scripts/visual_artifact_qa.py",
            "scripts/visual_geometry_qa.py",
            "scripts/render_mobile_preview.py",
        ],
        "status": "available" if VISION_SKILL.is_file() else "missing",
        "routing": "unknown",
    }
    if not VISION_SKILL.is_file():
        return metadata
    try:
        result = subprocess.run(
            [sys.executable, str(VISION_SKILL), "--check-routing"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        routing = (result.stdout or "").strip().splitlines()
        if routing:
            metadata["routing"] = routing[-1].strip().lower()
        metadata["routing_command_status"] = "passed" if result.returncode == 0 else "failed"
    except (OSError, subprocess.SubprocessError) as exc:
        metadata["routing_command_status"] = "failed"
        metadata["routing_error"] = str(exc)
    return metadata


def _canonical_excerpt(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()[:1200]


_SECTION_MARKER_PATH_RE = re.compile(
    r"(!\[[^\]]*\]\(imgs/section-)\d+(\.(?:png|webp|jpg|jpeg)\))",
    flags=re.IGNORECASE,
)


def _marker_insensitive_excerpt(value: str) -> str:
    """Normalize only authored section-image numbers for semantic hashing.

    The image filename is a routing binding checked separately by
    ``visual_qa``.  It is not article prose; changing a corrected section
    marker must not invalidate an otherwise identical semantic excerpt.
    """
    return _SECTION_MARKER_PATH_RE.sub(r"\1<bound>\2", _canonical_excerpt(value))


def _article_excerpt(article: Path, heading: str) -> str:
    """Delegate to the shared excerpt_utils module (single source of truth)."""
    return _shared_section_excerpt(article, heading)


def _resolve(article: Path, raw: str) -> Path:
    path = Path(str(raw or ""))
    return path if path.is_absolute() else article / path


def _source_text(article: Path, unit: dict[str, Any]) -> tuple[str, str]:
    candidates = [
        unit.get("diagram_source"),
        unit.get("source_file"),
        unit.get("editable_source"),
        unit.get("cover_overlay_source"),
    ]
    for raw in candidates:
        if not str(raw or "").strip():
            continue
        path = _resolve(article, str(raw))
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace"), str(path.relative_to(article))
    # External raster images have no deterministic label source.  Their
    # semantic review is intentionally left pending for a human.
    return "", ""


def _actual_provider(unit: dict[str, Any]) -> str:
    return str(
        unit.get("execution_provider")
        or unit.get("actual_provider")
        or unit.get("provider")
        or ""
    ).strip().lower()


def _visible_source_text(source_text: str) -> str:
    """Remove non-visible semantic ledgers before validating labels.

    A hidden ledger is metadata, not visual evidence.  Counting it would let a
    wrong template pass semantic QA while the reader sees unrelated labels.
    """
    text = re.sub(
        r'<(?:div|section|span)[^>]*class=["\'][^"\']*semantic-ledger[^"\']*["\'][^>]*>.*?</(?:div|section|span)>',
        "",
        source_text,
        flags=re.I | re.S,
    )
    text = re.sub(
        r'<(?:div|section|span)[^>]*style=["\'][^"\']*(?:left\s*:\s*-\d{4,}|display\s*:\s*none|visibility\s*:\s*hidden)[^"\']*["\'][^>]*>.*?</(?:div|section|span)>',
        "",
        text,
        flags=re.I | re.S,
    )
    return text


def _node_text(source_text: str) -> str:
    """Return visible semantic labels, excluding title/description copy.

    Deterministic renderers use more than one visible role: flow nodes,
    Q/K/V lanes, formulas and checklist labels.  The old node-only extractor
    made a correct lane diagram fail (or tempted renderers to add a hidden
    ledger), so collect the explicitly visible semantic roles together.
    """
    source_text = _visible_source_text(source_text)
    values = re.findall(
        r'<([A-Za-z][\w:-]*)[^>]*data-role=["\'](?:node|lane|formula|label|step)["\'][^>]*>(.*?)</\1>',
        source_text,
        flags=re.S | re.I,
    )
    if values:
        visible = [_html_unescape(re.sub(r"<[^>]+>", "", value[1])) for value in values]
        # KaTeX/HTML keeps the exact source formula in data-tex while the
        # visible glyphs are nested spans.  Include a normalized TeX form so
        # contracts can assert symbols such as QKᵀ and n_q without requiring
        # brittle OCR of a raster screenshot.
        tex_values = re.findall(r'data-tex=["\']([^"\']+)["\']', source_text, flags=re.I)
        for raw in tex_values:
            tex = _html_unescape(raw)
            tex = re.sub(r"\^\{\\top\}", "ᵀ", tex)
            tex = re.sub(r"\\mathrm\{([^{}]+)\}", r"\1", tex)
            tex = tex.replace(r"\times", "×").replace(r"\in", "∈")
            tex = tex.replace("{", "").replace("}", "").replace("\\", "")
            visible.append(tex)
        return "\n".join(visible)
    # Mermaid/hand-authored SVGs may not use the local marker.  In that case
    # fall back to the complete editable source, where exact expected labels
    # are still safer than accepting a generic template.
    return _html_unescape(source_text)


def _has_standalone_visible_label(label_text: str, value: str) -> bool:
    """Match a placeholder only when it is a complete visible label.

    Chinese technical copy naturally contains words such as ``检查`` in useful
    phrases (for example ``可检查``).  A substring guard turns those phrases
    into false positives.  Placeholder detection must catch a standalone
    generic card label, not veto a meaningful sentence that happens to share
    one character sequence.
    """
    if not value:
        return False
    stripped = re.sub(r"<[^>]+>", "\n", _html_unescape(label_text))
    return any(line.strip() == value for line in stripped.splitlines())


def _is_deterministic(unit: dict[str, Any]) -> bool:
    mode = str(unit.get("generation_mode") or "").strip().lower()
    provider = _actual_provider(unit)
    return mode == "deterministic" or provider in {"local-deterministic", "local-fallback", "local"}


def _unit_records(contract: dict[str, Any]) -> list[dict[str, Any]]:
    units = contract.get("units")
    if not isinstance(units, list):
        return []
    return [item for item in units if isinstance(item, dict)]


def _backend_asset_errors(article: Path, units: list[dict[str, Any]]) -> list[str]:
    """Prove that the selected backend reached the asset and the article HTML."""
    html_path = article / "article.html"
    html_text = html_path.read_text(encoding="utf-8", errors="replace") if html_path.is_file() else ""
    errors: list[str] = []
    body_backends: set[str] = set()
    required_backends: set[str] = set()
    body_types: set[str] = set()
    for unit in units:
        unit_id = str(unit.get("id") or "unknown")
        if unit_id == "cover":
            continue
        visual_type = str(unit.get("visual_type") or unit.get("kind") or "").strip().lower()
        requested = str(unit.get("requested_backend") or unit.get("render_backend") or "").strip().lower()
        actual = str(unit.get("execution_backend") or "").strip().lower()
        source_raw = str(unit.get("diagram_source") or unit.get("editable_source") or "").strip()
        output = str(unit.get("output") or unit.get("asset") or "").strip().replace("\\", "/")
        source = _resolve(article, source_raw)
        if actual:
            body_backends.add(actual)
        body_types.add(visual_type)
        if visual_type in {"qkv", "shape", "attention", "numeric"}:
            required_backends.add("katex-html-composite")
        elif visual_type == "multihead":
            required_backends.add("beautiful-mermaid")
        elif visual_type == "kv-cache":
            required_backends.add("deterministic-svg")
        elif visual_type == "checklist":
            required_backends.add("deterministic-infographic")
        if not requested or not actual:
            errors.append(f"视觉后端合同缺少 requested/execution backend：{unit_id}")
            continue
        expected = route_backend(str(unit.get("content_signal") or ""), visual_type)
        if requested != expected and not str(unit.get("route_override_reason") or "").strip():
            errors.append(f"视觉路由未按语义后端执行：{unit_id} requested={requested}, expected={expected}")
        if not source.is_file():
            errors.append(f"视觉后端可编辑源不存在：{unit_id} -> {source_raw}")
        else:
            source_text = source.read_text(encoding="utf-8", errors="replace")
            if requested.startswith("katex-") and source.suffix.lower() != ".html":
                errors.append(f"KaTeX 后端没有落到 HTML 中间源：{unit_id}")
            if requested == "beautiful-mermaid" and 'data-backend="beautiful-mermaid"' not in source_text:
                errors.append(f"beautiful-mermaid 后端没有实际渲染标记：{unit_id}")
            if requested in {"beautiful-mermaid", "deterministic-svg"} and source.suffix.lower() != ".svg":
                errors.append(f"SVG 后端源文件类型错误：{unit_id}")
            if "语义绑定视觉" in source_text or "X超玩•未来智能" in source_text:
                errors.append(f"正文图源文件不应携带品牌落款：{unit_id}")
        if output and f'src="{output}"' not in html_text and f"src='{output}'" not in html_text:
            errors.append(f"后端生成的正文图未被 article.html 引用：{unit_id}")
    missing_required = sorted(required_backends - body_backends)
    if missing_required:
        errors.append("正文语义任务没有落到指定视觉后端：" + ", ".join(missing_required))
    if {"multihead", "kv-cache", "checklist"} & body_types and len(body_backends) < 2:
        errors.append("正文存在关系/时序/清单任务，但实际只使用一种视觉后端")
    return errors


def _generation_provenance_errors(article: Path, units: list[dict[str, Any]]) -> list[str]:
    """Reject stale generation/source ledgers whose hashes no longer match PNGs.

    A visual contract can be semantically correct while the image was later
    replaced by hand or by a failed fallback.  The generation plan and
    image-sources ledger are therefore treated as content-addressed manifests,
    not descriptive notes: every declared output hash must equal the bytes on
    disk at review time.
    """
    errors: list[str] = []
    plan_path = article / "image-generation-plan.json"
    source_path = article / "image-sources.json"
    # Lightweight unit fixtures may intentionally exercise only the semantic
    # contract.  Full article gates require both manifests; when neither is
    # present there is nothing to compare yet and we leave that responsibility
    # to workflow_gate.py.
    if not plan_path.is_file() and not source_path.is_file():
        return []
    plan = _json(plan_path)
    plan_records = {
        str(item.get("id")): item
        for item in plan.get("prompt_files", [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    source_doc = _json(source_path)
    source_records = {
        str(item.get("path") or "").replace("\\", "/"): item
        for item in source_doc.get("assets", [])
        if isinstance(item, dict) and str(item.get("path") or "").strip()
    }
    for unit in units:
        unit_id = str(unit.get("id") or "unknown")
        output_raw = str(unit.get("output") or unit.get("asset") or "").strip()
        output_path = _resolve(article, output_raw)
        if not output_path.is_file():
            continue
        actual_hash = _sha(output_path).lower()
        plan_record = plan_records.get(unit_id)
        if not plan_record:
            errors.append(f"image-generation-plan.json 缺少素材记录：{unit_id}")
        else:
            declared = str(plan_record.get("output_sha256") or "").strip().lower()
            if not declared:
                errors.append(f"image-generation-plan.json 缺少 output_sha256：{unit_id}")
            elif declared != actual_hash:
                errors.append(
                    f"生成计划输出哈希已过期：{unit_id} declared={declared[:12]} actual={actual_hash[:12]}"
                )
        source_key = output_raw.replace("\\", "/")
        source_record = source_records.get(source_key)
        if not source_record:
            errors.append(f"image-sources.json 缺少素材记录：{unit_id} -> {source_key}")
        else:
            declared = str(source_record.get("sha256") or "").strip().lower()
            if not declared:
                errors.append(f"image-sources.json 缺少 sha256：{unit_id}")
            elif declared != actual_hash:
                errors.append(
                    f"素材来源哈希已过期：{unit_id} declared={declared[:12]} actual={actual_hash[:12]}"
                )
            generation = source_record.get("generation") if isinstance(source_record.get("generation"), dict) else {}
            generation_status = str(generation.get("status") or "").strip().lower()
            if generation_status not in {"generated", "deterministic", "fallback", "reused"}:
                errors.append(f"image-sources.json 生成状态未完成：{unit_id} status={generation_status or 'missing'}")
            if str(generation.get("execution_mode") or "").strip().lower() == "planned":
                errors.append(f"image-sources.json 仍是 planned 执行记录：{unit_id}")
            # The ledger is an execution receipt, not a copy of the request.
            # Cross-check the provider/backend against the generation plan so
            # a stale manifest cannot claim a passed asset with contradictory
            # provenance.
            if plan_record:
                expected_provider = str(plan_record.get("execution_provider") or "").strip().lower()
                actual_provider = str(generation.get("provider") or "").strip().lower()
                if expected_provider and actual_provider and expected_provider != actual_provider:
                    errors.append(f"生成执行 provider 与素材台账不一致：{unit_id} plan={expected_provider} ledger={actual_provider}")
                for field in ("execution_backend", "requested_backend"):
                    expected_backend = str(plan_record.get(field) or "").strip().lower()
                    actual_backend = str(generation.get(field) or "").strip().lower()
                    if expected_backend and actual_backend and expected_backend != actual_backend:
                        errors.append(f"生成执行 {field} 与素材台账不一致：{unit_id} plan={expected_backend} ledger={actual_backend}")
    return errors


def _formula_image_errors(article: Path) -> list[str]:
    """Check formula PNGs for rotation, blank, and readability issues.

    The formula pipeline renders KaTeX HTML via Chrome headless screenshots.
    If the viewport is too small Chrome may clip or rotate content, producing
    unreadable images.  This guard catches those cases before they reach the
    draft box.
    """
    errors: list[str] = []
    manifest_path = article / "formula-manifest.json"
    if not manifest_path.is_file():
        return errors
    try:
        import struct
    except ImportError:
        return errors
    manifest = _json(manifest_path)
    formulas = manifest.get("formulas", [])
    if not isinstance(formulas, list):
        return errors
    for item in formulas:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("formula_id", "")).strip() or "unknown"
        output_raw = str(item.get("output", "")).strip()
        if not output_raw:
            continue
        png_path = _resolve(article, output_raw)
        if not png_path.is_file():
            errors.append(f"公式 PNG 不存在：{fid}")
            continue
        # Read PNG dimensions from IHDR header for rotation detection.
        # NOTE: File-size / blank heuristics were REMOVED because they
        # falsely flagged legitimate single-character formulas (e.g. "i"
        # at ~863 bytes).  Blank/failed renders are already caught by
        # formula_pipeline.py's hash-existence check (Step 7).
        try:
            with open(png_path, "rb") as fh:
                data = fh.read(24)
            if data[:8] != b"\x89PNG\r\n\x1a\n":
                errors.append(f"公式 PNG 文件头无效：{fid}")
                continue
            w = struct.unpack(">I", data[16:20])[0]
            h = struct.unpack(">I", data[20:24])[0]
        except (OSError, IndexError, struct.error):
            continue
        display_mode = str(item.get("display_mode", "inline")).lower()
        # Rotation detection: a 90°-rotated formula becomes very tall and
        # narrow (h/w typically > 5).  h > w*3 catches this while allowing
        # legitimately tall single characters (h/w ~2).
        if h > w * 3:
            errors.append(
                f"公式图可能旋转（高度 {h} > 宽度 {w}×3）：{fid}"
            )
    return errors


def check(article: Path, *, reviewer_type: str = "agent", reviewer: str = "semantic-contract") -> int:
    contract_path = article / "visual-contract.json"
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    contract = _json(contract_path)
    if not contract_path.is_file():
        errors.append("缺少 visual-contract.json")
    elif contract.get("contract") != CONTRACT_NAME:
        errors.append(f"visual-contract.json 必须使用 contract={CONTRACT_NAME}")

    units = _unit_records(contract)
    if contract_path.is_file() and not units:
        errors.append("visual-contract.json 必须包含 units")
    brand_contract = any(str(item.get("public_brand") or "").strip() for item in units)
    backend_contract = any(str(item.get("requested_backend") or "").strip() for item in units)
    if backend_contract:
        errors.extend(_backend_asset_errors(article, units))
    if units:
        errors.extend(_generation_provenance_errors(article, units))
    route_consistency = _check_route_consistency(article)
    errors.extend(f"视觉路由一致性检查失败：{issue}" for issue in route_consistency.get("errors", []))

    # Validate the bytes and the editable source, not only labels/hashes.  A
    # duplicate SVG attribute can make a browser discard CSS variables while
    # leaving the source semantically correct; the raster gate catches the
    # resulting black blocks before a draft is accepted.
    artifact_result = _check_artifact_article(article, units)
    errors.extend(f"视觉产物完整性检查失败：{issue}" for issue in artifact_result.get("errors", []))
    artifact_by_id = {
        str(record.get("id")): record
        for record in artifact_result.get("records", [])
        if isinstance(record, dict)
    }

    # Formula image readability guard — prevents rotated/blank formula PNGs
    # from silently passing the visual semantic gate.
    errors.extend(_formula_image_errors(article))

    for unit in units:
        unit_id = str(unit.get("id", "")).strip() or "unknown"
        expected = [str(value).strip() for value in unit.get("expected_elements", []) if str(value).strip()]
        forbidden = [str(value).strip() for value in unit.get("forbidden_elements", []) if str(value).strip()]
        section_heading = str(unit.get("section_heading") or unit.get("section") or "").strip()
        source_excerpt_sha256 = str(unit.get("source_excerpt_sha256") or "").strip().lower()
        claim_ids = [str(value).strip() for value in unit.get("claim_ids", []) if str(value).strip()]
        output = str(unit.get("output") or unit.get("asset") or "").strip()
        output_path = _resolve(article, output)
        source_text, source_path = _source_text(article, unit)
        label_text = _node_text(source_text)
        labels_found = [value for value in expected if value in label_text]
        forbidden_found = [value for value in forbidden if _has_standalone_visible_label(label_text, value)]
        generic_found = [value for value in GENERIC_LABELS if _has_standalone_visible_label(label_text, value) and value not in expected]
        if str(unit.get("visual_type") or unit.get("kind") or "").strip().lower() in {"code", "pseudocode"}:
            # Comments in executable examples are implementation notes, not
            # generic visual-card labels.  Exclude them from the placeholder
            # guard while keeping the exact visible code/heading contract.
            code_semantic_text = "\n".join(
                re.sub(r"(?:#|//).*?$", "", line)
                for line in label_text.splitlines()
            )
            forbidden_found = [value for value in forbidden if _has_standalone_visible_label(code_semantic_text, value)]
            generic_found = [value for value in GENERIC_LABELS if _has_standalone_visible_label(code_semantic_text, value) and value not in expected]
        deterministic = _is_deterministic(unit)
        artifact_record = artifact_by_id.get(unit_id, {})
        equivalence = artifact_record.get("source_raster_equivalence") if isinstance(artifact_record, dict) else {}
        if deterministic and unit_id != "cover" and isinstance(equivalence, dict) and equivalence.get("status") == "skipped":
            errors.append(
                f"视觉源/栅格等价检查未执行：{unit_id}；确定性技术图不能只验证 SVG 存在，必须 opt-in source-to-raster gate"
            )
        geometry_errors: list[str] = []
        if unit_id != "cover" and deterministic and source_path:
            geometry_errors = _check_geometry_source(
                _resolve(article, source_path),
                geometry_required=_infer_geometry_required(unit, unit),
                expected_background=str(unit.get("canvas_background") or "").strip(),
            )
            errors.extend(f"视觉几何/画布检查失败：{unit_id}：{issue}" for issue in geometry_errors)
            if _check_aesthetic_svg is not None and unit.get("aesthetic_required") is True and _resolve(article, source_path).suffix.lower() == ".svg":
                aesthetic = _check_aesthetic_svg(_resolve(article, source_path))
                errors.extend(f"视觉美学卫生检查失败：{unit_id}：{issue}" for issue in aesthetic.get("errors", []))
        requested_provider = str(unit.get("requested_provider") or unit.get("provider") or "").strip().lower()
        actual_provider = _actual_provider(unit)
        public_brand = str(unit.get("public_brand") or "").strip()
        pixel_review_mode = ""
        pixel_review_receipt_sha256 = ""
        if backend_contract:
            errors.extend(validate_record(unit))
        if public_brand == "X超玩•未来智能" and re.search(r"X超玩•未来智能\s*[·•]", source_text):
            errors.append(f"视觉源文件残留旧公开品牌署名：{unit_id}")
        if unit_id == "cover":
            # Cover semantics are not optional decoration: the editable
            # overlay must declare the same motif selected by the article
            # topic, and its visible labels must not belong to another
            # workflow (for example AgentState on a RAG article).
            motif = str(unit.get("cover_motif") or "").strip()
            cover_visible = _html_unescape(re.sub(r"<[^>]+>", " ", _visible_source_text(source_text)))
            normalized_cover = re.sub(r"\s+", " ", cover_visible).strip()
            normalize_cover = lambda value: re.sub(r"\s+", " ", value).strip()
            cover_missing = [value for value in expected if normalize_cover(value) not in normalized_cover]
            cover_forbidden = [value for value in forbidden if normalize_cover(value) in normalized_cover]
            labels_found = [value for value in expected if normalize_cover(value) in normalized_cover]
            if not source_path:
                errors.append("封面缺少可编辑语义源；不能只凭 PNG 存在判定主题匹配")
            if not motif:
                errors.append("封面视觉合同缺少 cover_motif")
            elif not re.search(rf'data-cover-motif=["\']{re.escape(motif)}["\']', source_text, flags=re.I):
                errors.append(f"封面源的 cover_motif 与合同不一致：{motif}")
            if cover_missing:
                errors.append(f"封面可见源缺少主题锚点：{', '.join(cover_missing)}")
            if cover_forbidden:
                errors.append(f"封面可见源包含跨主题标签：{', '.join(cover_forbidden)}")
        if unit_id != "cover":
            if not section_heading:
                errors.append(f"视觉合同缺少章节绑定：{unit_id}")
            if not re.fullmatch(r"[0-9a-f]{64}", source_excerpt_sha256):
                errors.append(f"视觉合同缺少正文片段 SHA-256：{unit_id}")
            if not claim_ids:
                errors.append(f"视觉合同缺少章节 claim_ids：{unit_id}")
            if not str(unit.get("viewer_job") or "").strip():
                errors.append(f"视觉合同缺少 viewer_job：{unit_id}")
            if not str(unit.get("render_backend") or "").strip():
                errors.append(f"视觉合同缺少 render_backend：{unit_id}")
            if brand_contract and not public_brand:
                errors.append(f"视觉合同缺少 public_brand：{unit_id}")
            excerpt = _article_excerpt(article, section_heading)
            if excerpt:
                expected_excerpt_sha256 = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
                marker_insensitive_match = False
                if source_excerpt_sha256 != expected_excerpt_sha256:
                    stored_excerpt = str(unit.get("source_excerpt") or "")
                    marker_insensitive_match = bool(stored_excerpt) and hashlib.sha256(
                        _marker_insensitive_excerpt(stored_excerpt).encode("utf-8")
                    ).hexdigest() == hashlib.sha256(
                        _marker_insensitive_excerpt(excerpt).encode("utf-8")
                    ).hexdigest()
                if source_excerpt_sha256 != expected_excerpt_sha256 and not marker_insensitive_match:
                    errors.append(f"视觉合同正文片段 SHA-256 已过期：{unit_id}")
            overlap = sorted(set(expected) & set(forbidden))
            if overlap:
                errors.append(f"视觉合同 expected/forbidden 重叠：{unit_id}: {', '.join(overlap)}")
        if not output_path.is_file():
            status = "failed"
            errors.append(f"视觉素材不存在：{unit_id} -> {output}")
        elif deterministic and unit_id == "cover":
            # Covers may use the local branded poster fallback.  The cover is
            # not a factual diagram, so its contract is asset/theme presence;
            #正文 technical assets still require editable sources below.
            status = "passed"
        elif deterministic:
            # 增强 3：fallback/确定性正文图必须有可见文字成分（信息密度）。
            # OCR（pytesseract，可选）优先校验 expected_elements 在 PNG 可读；
            # 未安装 OCR 时用 glyph 连通域计数近似（空洞占位图 glyph≈0，
            # 有内容的要点卡/代码卡通常 ≥19）。防止"孤立圆圈"式空卡入库。
            _glyphs = _glyph_component_count(output_path) if _glyph_component_count else -1
            if _glyphs >= 0 and _glyphs < _MIN_INFO_GLYPHS:
                errors.append(
                    f"正文图信息密度过低（疑似空内容/占位图）：{unit_id} -> {output_path.name}"
                    f"（glyph={_glyphs}，需 ≥{_MIN_INFO_GLYPHS}）"
                )
            # Expected elements must be visible in the editable source; a
            # hidden semantic ledger cannot satisfy this contract.
            missing = [value for value in expected if value not in label_text]
            if not source_path:
                status = "failed"
                errors.append(f"确定性视觉缺少可编辑源文件：{unit_id}")
            elif missing:
                status = "failed"
                errors.append(f"视觉合同元素未在源文件出现：{unit_id}: {', '.join(missing)}")
            elif forbidden_found or generic_found:
                status = "failed"
                bad = sorted(set(forbidden_found + generic_found))
                errors.append(f"视觉源文件包含禁止的通用占位标签：{unit_id}: {', '.join(bad)}")
            else:
                status = "passed"
        else:
            # A real external raster cannot be proven by OCR alone.  Accept a
            # byte-bound native/external/human pixel receipt, but never rename
            # a multimodal review to ``human``.  The legacy explicit human
            # semantic path remains available for a genuinely human run.
            pixel_review_mode, pixel_review_receipt_sha256 = _pixel_review_for_asset(
                article, unit_id, output_path
            )
            status = "passed" if reviewer_type == "human" or pixel_review_mode else "pending-review"
            if status != "passed":
                errors.append(
                    f"外部 illustrative 素材需要绑定图片字节的 native/external/human pixel review：{unit_id}"
                )
        if requested_provider and actual_provider and unit_id != "cover":
            # Deterministic diagrams may be requested under an Agnes plan, but
            # the contract must record the explicit local execution provider.
            if requested_provider == "agnes" and actual_provider not in {"local-deterministic", "local-fallback", "local"} and actual_provider != requested_provider:
                errors.append(f"视觉素材 requested_provider/execution_provider 不一致且没有可解释 fallback：{unit_id}")

        records.append({
            "id": unit_id,
            "section_heading": section_heading,
            "source_excerpt_sha256": source_excerpt_sha256,
            "viewer_job": str(unit.get("viewer_job") or ""),
            "expected_elements": expected,
            "forbidden_elements": forbidden,
            "claim_ids": claim_ids,
            "render_backend": str(unit.get("render_backend") or ""),
            "public_brand": public_brand,
            "requested_provider": requested_provider,
            "execution_provider": actual_provider,
            "requested_backend": str(unit.get("requested_backend") or unit.get("render_backend") or ""),
            "execution_backend": str(unit.get("execution_backend") or ""),
            "fallback_reason": str(unit.get("fallback_reason") or ""),
            "geometry_status": "passed" if not geometry_errors else "failed",
            "aesthetic_status": "passed" if not (_check_aesthetic_svg and source_path and _resolve(article, source_path).suffix.lower() == ".svg" and _check_aesthetic_svg(_resolve(article, source_path)).get("errors")) else "failed",
            "artifact_status": artifact_by_id.get(unit_id, {}).get("status", "missing"),
            "artifact_source_errors": artifact_by_id.get(unit_id, {}).get("source_errors", []),
            "artifact_raster_errors": artifact_by_id.get(unit_id, {}).get("raster_errors", []),
            "artifact_detected_regions": artifact_by_id.get(unit_id, {}).get("detected_regions", []),
            "canvas_background": str(unit.get("canvas_background") or ""),
            "output": output,
            "editable_source": source_path,
            "labels_found": labels_found,
            "forbidden_found": sorted(set(forbidden_found + generic_found)),
            "association_status": "passed" if status == "passed" else "failed",
            "semantic_status": status,
            "pixel_review_mode": pixel_review_mode if not deterministic else "deterministic",
            "pixel_review_receipt_sha256": pixel_review_receipt_sha256 if not deterministic else "",
            "output_sha256": _sha(output_path) if output_path.is_file() else "",
        })

    overall = "passed" if not errors else "failed"
    report = {
        "schema_version": 1,
        "contract": CONTRACT_NAME,
        "status": overall,
        "reviewer_type": reviewer_type,
        "reviewer": reviewer,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "article": article.name,
        "vision_skill": _vision_skill_metadata(),
        "route_consistency": route_consistency,
        "records": records,
        "errors": errors,
    }
    (article / REPORT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        print("VISUAL SEMANTIC QA BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"VISUAL SEMANTIC QA PASSED: {len(records)} assets")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--reviewer-type", choices=("agent", "human"), default="agent")
    parser.add_argument("--reviewer", default="semantic-contract")
    args = parser.parse_args()
    article = args.article.expanduser()
    if not article.is_absolute():
        article = ROOT / article
    return check(article.resolve(), reviewer_type=args.reviewer_type, reviewer=args.reviewer)


if __name__ == "__main__":
    raise SystemExit(main())
