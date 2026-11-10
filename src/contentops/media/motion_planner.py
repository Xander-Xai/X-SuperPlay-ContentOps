"""Account-DNA-driven Huashu Art Motion shot plans for M5.

This first compiler is deliberately bounded to the two active video accounts.
It emits parameterized, source-traceable clips for known technical concepts and
fails closed when a line cannot be placed into a meaningful visual grammar.
It does not invent benchmark values or treat generated visuals as evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


class MotionPlanError(ValueError):
    """The account or narration cannot be rendered without guessing visuals."""


@lru_cache(maxsize=16)
def _read_local_ocr(path: str, modified_ns: int, size: int) -> tuple[dict, ...]:
    """OCR a local source image once per exact file version."""
    del modified_ns, size  # cache-key inputs invalidate stale OCR after edits
    try:
        from PIL import Image
        from rapidocr_onnxruntime import RapidOCR
        image_path = Path(path)
        width, height = Image.open(image_path).size
        result, _elapsed = RapidOCR()(str(image_path))
    except Exception:  # noqa: BLE001 - unavailable OCR keeps source shot unsupported
        return ()
    if width <= 0 or height <= 0:
        return ()
    regions = []
    for row in result or []:
        if len(row) < 3 or not str(row[1]).strip():
            continue
        try:
            points = [(float(point[0]), float(point[1])) for point in row[0]]
            confidence = float(row[2])
        except (TypeError, ValueError, IndexError):
            continue
        if not points:
            continue
        left = max(0.0, min(x for x, _ in points) / width)
        top = max(0.0, min(y for _, y in points) / height)
        right = min(1.0, max(x for x, _ in points) / width)
        bottom = min(1.0, max(y for _, y in points) / height)
        if right <= left or bottom <= top:
            continue
        regions.append({"text": str(row[1]).strip(),
                        "confidence": round(max(0.0, min(1.0, confidence)), 4),
                        "rect": [round(left, 6), round(top, 6),
                                 round(right - left, 6), round(bottom - top, 6)]})
    return tuple(regions)


VIDEO_ACCOUNTS = {"x-superplay-1024", "x-superplay-future-intelligence"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
ICON_BY_TOPIC = (
    (re.compile(r"rag|检索|召回|retriev|rank|排序|融合|rrf", re.I), "network"),
    (re.compile(r"agent|智能体|状态|工具调用|tool call", re.I), "person"),
    (re.compile(r"mcp|协议|接口|api|服务端|client|server", re.I), "screen"),
    (re.compile(r"源码|代码|code|仓库|github|实现|函数|配置", re.I), "screen"),
    (re.compile(r"数据|指标|数值|增长|性能|延迟|吞吐|metric", re.I), "chart"),
)


def _sha(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _topic_kind(text: str) -> str:
    folded = str(text or "").casefold()
    if re.search(r"rag|检索|召回|retriev|rank|排序|融合|rrf", folded):
        return "retrieval"
    if re.search(r"agent|智能体|状态|工具调用|tool call", folded):
        return "agent"
    if re.search(r"mcp|协议|接口|api|服务端|client|server", folded):
        return "protocol"
    if re.search(r"源码|代码|code|仓库|github|实现|函数|配置|easel|runtime|release|version|pinned|verified|checkout", folded):
        return "code"
    if re.search(r"数据|指标|数值|增长|性能|延迟|吞吐|metric", folded):
        return "metric"
    return "unsupported"


def _short_label(text: str, limit: int = 12) -> str:
    value = " ".join(str(text or "").split()).strip("。！？!?；;，,")
    return value[:limit] if value else "机制步骤"


def _motion_terms(text: str) -> set[str]:
    terms = {token.casefold() for token in re.findall(r"[a-z0-9]+", text, re.I)}
    terms.difference_update({"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"})
    for phrase in re.findall(r"[\u3400-\u9fff]+", text):
        terms.update(phrase[index:index + 2] for index in range(len(phrase) - 1))
    return terms


def _matching_ocr_regions(text: str, source: Mapping[str, Any],
                          excluded_rects: set[str] | None = None) -> List[Dict[str, Any]]:
    narration_terms = _motion_terms(text)
    ranked = []
    excluded_rects = excluded_rects or set()
    for region in source.get("ocr_regions") or []:
        if not isinstance(region, dict):
            continue
        region_text = str(region.get("text") or "").strip()
        rect = region.get("rect")
        if not region_text or not isinstance(rect, list) or len(rect) != 4:
            continue
        try:
            left, top, width, height = [float(value) for value in rect]
            confidence = float(region.get("confidence") or 0)
        except (TypeError, ValueError):
            continue
        if (confidence < 0.5 or left < 0 or top < 0 or width <= 0 or height <= 0
                or left + width > 1.000001 or top + height > 1.000001):
            continue
        rect_key = json.dumps([round(left, 6), round(top, 6), round(width, 6),
                               round(height, 6)], separators=(",", ":"))
        if rect_key in excluded_rects:
            continue
        overlap = narration_terms & _motion_terms(region_text)
        ranked.append(({**region, "rect": [round(left, 6), round(top, 6),
                                             round(width, 6), round(height, 6)],
                        "matched_terms": sorted(overlap)},
                       len(overlap), confidence))
    ranked.sort(key=lambda item: (-item[1], -item[2], item[0]["text"]))
    # Require two content terms before targeting a screenshot region. A
    # one-word match is too broad for code and UI text and can overuse push-ins.
    ranked = [item for item in ranked if item[1] >= 2]
    return [item[0] for item in ranked[:2]]


def _cues(text: str, kind: str, source_image: str | None,
          grammar: str, source_regions: Sequence[Mapping[str, Any]] = ()) -> List[Dict[str, Any]]:
    """Build two or three semantic beats from the script line, not a title card."""
    if grammar == "t2_keynote_ui" and source_image and source_regions:
        cues: List[Dict[str, Any]] = [
            {"at": 0.0, "kind": "image", "image": source_image},
        ]
        for index, region in enumerate(source_regions):
            cues.append({
                "at": 0.8 + index * 1.0,
                "kind": "highlight",
                "data": {"rect": list(region["rect"])},
            })
        return cues
    if source_image:
        icon_name = next((value for pattern, value in ICON_BY_TOPIC if pattern.search(text)), None)
        cues: List[Dict[str, Any]] = [
            {"at": 0.0, "kind": "image", "image": source_image},
            {"at": 0.65, "kind": "draw", "text": _short_label(text),
             "data": {"icon": icon_name or "screen"}},
        ]
        if kind == "retrieval":
            cues.extend([
                {"at": 1.45, "kind": "draw", "text": "语义召回",
                 "data": {"icon": "target"}},
                {"at": 2.25, "kind": "draw", "text": "候选汇合",
                 "data": {"icon": "stack"}},
            ])
        else:
            cues.append({"at": 1.7, "kind": "point", "text": _short_label(text, 18)})
        return cues

    if grammar == "t1_3b1b" and kind in {"agent", "protocol"}:
        # Draw the relationships named in this line as a progressive derivation.
        # Do not add a generic architecture diagram: each node below must occur
        # in the narration, so an illustrative animation cannot quietly assert
        # a tool, state, or protocol boundary the source did not name.
        vocabulary = (
            (r"智能体|\bagent\b", "Agent"),
            (r"客户端|\bclient\b", "Client"),
            (r"mcp", "MCP"),
            (r"协议", "协议"),
            (r"状态|\bstate\b", "状态"),
            (r"工具调用|调用工具|工具|\btool(?:\s+call)?\b", "工具"),
            (r"服务端|\bserver\b", "Server"),
            (r"结果|\bresult\b", "结果"),
            (r"恢复|\bresume\b", "恢复"),
        )
        found = []
        for pattern, label in vocabulary:
            match = re.search(pattern, text, re.I)
            if match:
                found.append((match.start(), label))
        found.sort()
        terms = list(dict.fromkeys(label for _, label in found))
        if len(terms) >= 2:
            pairs = list(zip(terms, terms[1:]))
            cues = [{"at": round(index * 1.0, 2), "kind": "equation",
                     "text": f"{left} → {right}"}
                    for index, (left, right) in enumerate(pairs)]
            cues.append({"at": round(len(pairs) * 1.0, 2), "kind": "highlight",
                         "data": {"target": "equation"}})
            return cues

    if grammar == "t1_3b1b" and kind == "retrieval" and re.search(r"\bRRF\b", text, re.I):
        # RRF has a specific, sourced mathematical mechanism. Make the rank
        # contribution itself transform into the sum instead of reusing the
        # generic two-retriever sequence and leaving the key idea implicit.
        return [
            {"at": 0.0, "kind": "equation", "text": "rankᵢ(d)"},
            {"at": 1.05, "kind": "equation", "text": "1 / (k + rankᵢ(d))"},
            {"at": 2.1, "kind": "equation",
             "text": "score(d) = Σᵢ 1 / (k + rankᵢ(d))"},
            {"at": 3.1, "kind": "point", "text": "按名次累加倒数贡献"},
            {"at": 3.85, "kind": "highlight", "data": {"target": "equation"}},
        ]

    if (grammar == "t1_3b1b" and kind == "retrieval"
            and re.search(r"原始分|score scale|raw score", text, re.I)):
        # This line explains why rank fusion is used. Show that the method
        # transforms incomparable source scores into per-list ranks before
        # calculating one fused score; do not draw a neural-network icon.
        return [
            {"at": 0.0, "kind": "equation", "text": "BM25 原始分"},
            {"at": 1.05, "kind": "equation", "text": "向量相似度"},
            {"at": 2.1, "kind": "equation",
             "text": "1/(k+rank₁(d)) + 1/(k+rank₂(d))"},
            {"at": 3.1, "kind": "point", "text": "按排名融合，不直接比原始分"},
            {"at": 3.85, "kind": "highlight", "data": {"target": "equation"}},
        ]

    if grammar == "t1_3b1b" and kind == "retrieval":
        # Start with the retrieval object, then transform it through the two
        # branches and their merge. Do not open with a title or a bullet list.
        # The labels are generic process stages, not a claim that a particular
        # ranking formula, score or benchmark was used.
        lexical = "BM25" if re.search(r"\bBM25\b", text, re.I) else "词项"
        semantic = "向量" if "向量" in text else "语义"
        final_text = "候选进入重排" if re.search(r"重排|rerank", text, re.I) \
            else "两路候选完成融合"
        return [
            {"at": 0.0, "kind": "equation", "text": f"Query → {lexical}"},
            {"at": 1.05, "kind": "equation", "text": f"Query → {semantic} 候选"},
            {"at": 2.1, "kind": "equation",
             "text": f"{lexical} + {semantic} → 融合候选"},
            {"at": 3.1, "kind": "point", "text": final_text},
            {"at": 3.85, "kind": "highlight", "data": {"target": "equation"}},
        ]

    if kind == "retrieval":
        return [
            {"at": 0.0, "kind": "draw", "text": "词项召回", "data": {"icon": "doc"}},
            {"at": 0.7, "kind": "draw", "text": "语义召回", "data": {"icon": "target"}},
            {"at": 1.55, "kind": "draw", "text": "候选汇合", "data": {"icon": "stack"}},
        ]
    if kind == "agent":
        return [
            {"at": 0.0, "kind": "draw", "text": "Agent 状态", "data": {"icon": "person"}},
            {"at": 0.7, "kind": "draw", "text": "调用工具", "data": {"icon": "screen"}},
            {"at": 1.55, "kind": "draw", "text": "结果返回", "data": {"icon": "check"}},
        ]
    if kind == "protocol":
        return [
            {"at": 0.0, "kind": "draw", "text": "客户端", "data": {"icon": "screen"}},
            {"at": 0.7, "kind": "draw", "text": "协议边界", "data": {"icon": "network"}},
            {"at": 1.55, "kind": "draw", "text": "服务端工具", "data": {"icon": "gear"}},
        ]
    if kind == "code":
        return [
            {"at": 0.0, "kind": "draw", "text": "真实代码", "data": {"icon": "screen"}},
            {"at": 0.75, "kind": "point", "text": _short_label(text, 18)},
        ]
    if kind == "metric":
        return [
            {"at": 0.0, "kind": "draw", "text": "来源指标", "data": {"icon": "chart"}},
            {"at": 0.75, "kind": "point", "text": _short_label(text, 18)},
        ]
    raise MotionPlanError("AUTO_MOTION_UNSUPPORTED: no semantic visual grammar matched "
                          f"script line {text!r}; add a reviewed shot plan")


def build_auto_plan(*, project: Path, account_id: str,
                    account_dna: Mapping[str, Any], script: Mapping[str, Any],
                    narration: Mapping[str, Any],
                    source_assets: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Write deterministic per-placement specs under ``motion/auto``.

    Each output clip is bounded to 2–8 seconds, uses the account's exact six
    color values, and records its content and source anchor in the plan.
    1024 requires an actual registered still for every placement; the clip then
    reveals that evidence image and adds only explanatory marks.
    """
    if account_id not in VIDEO_ACCOUNTS:
        raise MotionPlanError(f"AUTO_MOTION_ACCOUNT_UNSUPPORTED: {account_id!r}")
    if str(account_dna.get("slug") or "") != account_id:
        raise MotionPlanError("AUTO_MOTION_DNA_MISMATCH: profile slug does not match project")
    visual = account_dna.get("visual") or {}
    profile = visual.get("motion", {}).get("motion_profile") or visual.get("motion_profile")
    if (not isinstance(profile, dict)
            or profile.get("backend") not in {"huashu-art-motion", "huashu-motion"}):
        raise MotionPlanError("AUTO_MOTION_PROFILE_MISSING: account DNA has no Huashu profile")
    profile_backend = str(profile.get("backend"))
    palette = profile.get("palette") or {}
    style_variants = profile.get("style_variants") or {}
    default_variant = str(profile.get("recommended_variant") or "")
    if default_variant and default_variant in style_variants:
        palette = style_variants[default_variant]
    required_colors = ("bg", "surface", "ink", "sub", "accent", "accent2")
    if any(not re.fullmatch(r"#[0-9a-fA-F]{6}", str(palette.get(key) or ""))
           for key in required_colors):
        raise MotionPlanError("AUTO_MOTION_PALETTE_INVALID: expected all six hex colors")
    allowed = set(profile.get("grammars") or [])
    if profile_backend == "huashu-art-motion" and "y3_whiteboard" not in allowed:
        raise MotionPlanError("AUTO_MOTION_GRAMMAR_UNAVAILABLE: y3_whiteboard is not allowed")

    semantic_lines = script.get("lines") or []
    semantic_timings = narration.get("lines") or []
    if not semantic_lines or len(semantic_lines) != len(semantic_timings):
        raise MotionPlanError("AUTO_MOTION_TIMELINE_MISMATCH: narration timing must cover each line")
    lines: List[Dict[str, Any]] = []
    timings: List[Dict[str, Any]] = []
    explicit_visuals = script.get("visual_shots")
    if explicit_visuals is None:
        lines = [dict(line) for line in semantic_lines]
        timings = [dict(row) for row in semantic_timings]
    else:
        by_segment: Dict[str, List[Dict[str, Any]]] = {}
        for row in explicit_visuals:
            if not isinstance(row, dict):
                raise MotionPlanError("AUTO_MOTION_VISUAL_SHOT_INVALID: each shot must be an object")
            segment_id = str(row.get("segment_id") or "").strip()
            if not segment_id:
                raise MotionPlanError("AUTO_MOTION_VISUAL_SHOT_INVALID: segment_id is required")
            by_segment.setdefault(segment_id, []).append(row)
        line_ids = [str(line.get("id") or "") for line in semantic_lines]
        if set(by_segment) != set(line_ids):
            raise MotionPlanError(
                "AUTO_MOTION_VISUAL_SHOT_MISMATCH: every semantic line needs a visual plan")
        for index, (semantic, timing) in enumerate(zip(semantic_lines, semantic_timings)):
            segment_id = line_ids[index]
            rows = by_segment[segment_id]
            start = float(timing.get("start") or 0.0)
            if index + 1 < len(semantic_timings):
                end = float(semantic_timings[index + 1].get("start") or 0.0)
            else:
                end = start + float(timing.get("duration") or 0.0)
            span = end - start
            if span <= 0:
                raise MotionPlanError(
                    f"AUTO_MOTION_TIMELINE_MISMATCH: segment {segment_id} has no positive span")
            weights = []
            for row in rows:
                try:
                    weight = float(row.get("duration_weight", 1.0))
                except (TypeError, ValueError):
                    weight = 0.0
                if weight <= 0:
                    raise MotionPlanError(
                        f"AUTO_MOTION_VISUAL_SHOT_INVALID: {row.get('shot_id')!r} has no positive weight")
                weights.append(weight)
            cursor = start
            for row_index, (row, weight) in enumerate(zip(rows, weights)):
                placement = str(row.get("shot_id") or row.get("placement_id") or "").strip()
                asset_id = str(row.get("asset_id") or semantic.get("asset_id") or "").strip()
                visual_role = str(row.get("visual_role") or "explain").strip().lower()
                if visual_role not in {"proof", "demo", "explain", "context", "transition"}:
                    raise MotionPlanError(
                        f"AUTO_MOTION_VISUAL_SHOT_INVALID: {placement!r} has invalid visual_role")
                if visual_role == "proof" and not row.get("evidence_ref"):
                    raise MotionPlanError(
                        f"AUTO_MOTION_VISUAL_SHOT_INVALID: proof shot {placement!r} needs evidence_ref")
                if not placement or not asset_id:
                    raise MotionPlanError(
                        "AUTO_MOTION_VISUAL_SHOT_INVALID: shot_id and asset_id are required")
                shot_end = end if row_index == len(rows) - 1 else cursor + span * weight / sum(weights)
                lines.append({**semantic, **row, "id": placement, "asset_id": asset_id,
                              "segment_id": segment_id, "visual_role": visual_role})
                timings.append({"line_id": placement, "start": cursor,
                                "duration": shot_end - cursor})
                cursor = shot_end
    planner_sha256 = _file_sha(Path(__file__).resolve())
    identity = {"account": account_id, "profile": profile, "script": script,
                "narration": narration, "assets": source_assets,
                "planner_sha256": planner_sha256}
    fingerprint = _sha(identity)
    auto_dir = project / "motion" / "auto"
    specs_dir = auto_dir / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    shots = []
    camera_targeted_regions: Dict[str, set[str]] = {}
    for index, (line, timing) in enumerate(zip(lines, timings)):
        placement = str(line.get("id") or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,50}", placement):
            raise MotionPlanError(f"AUTO_MOTION_PLACEMENT_INVALID: {placement!r}")
        source_asset_id = str(line.get("asset_id") or "")
        text = str(line.get("visual_focus") or line.get("narration")
                   or line.get("caption") or "").strip()
        style_variant = str(line.get("style_variant") or default_variant)
        shot_palette = style_variants.get(style_variant, palette)
        if any(not re.fullmatch(r"#[0-9a-fA-F]{6}", str(shot_palette.get(key) or ""))
               for key in required_colors):
            raise MotionPlanError(
                f"AUTO_MOTION_PALETTE_INVALID: style variant {style_variant!r} is incomplete")
        speech_duration = float(timing.get("duration") or 0)
        start = float(timing.get("start") or 0)
        if index + 1 < len(timings):
            next_start = float(timings[index + 1].get("start") or 0)
            duration = next_start - start
        else:
            duration = speech_duration
        source = source_assets.get(source_asset_id)
        if not placement or not source_asset_id or not text:
            raise MotionPlanError("AUTO_MOTION_LINE_INVALID: each line needs id, source asset and narration")
        if not 0.0 < duration <= 8.0:
            raise MotionPlanError(
                f"AUTO_MOTION_DURATION_UNSUPPORTED: {placement} is {duration:.2f}s; "
                "a narrated shot must be positive and no longer than 8 seconds")
        render_duration = max(2.0, duration)
        hold_padding = round(render_duration - speech_duration, 3)
        kind = _topic_kind(text)
        if kind == "unsupported" and str((source or {}).get("type") or "").upper() == "CODE_SNAPSHOT":
            kind = "code"
        if kind == "unsupported":
            raise MotionPlanError(f"AUTO_MOTION_UNSUPPORTED: no semantic visual grammar matched {placement}")

        source_image = None
        source_image_sha256 = None
        code_snapshot = str((source or {}).get("type") or "").upper() == "CODE_SNAPSHOT"
        if account_id == "x-superplay-1024" or code_snapshot:
            if not source:
                raise MotionPlanError(f"AUTO_MOTION_SOURCE_MISSING: {placement} has no registered evidence asset")
            source_path = str(source.get("repo_path") or "")
            suffix = Path(source_path).suffix.lower()
            if suffix not in IMAGE_SUFFIXES:
                raise MotionPlanError(
                    f"AUTO_MOTION_SOURCE_NOT_STILL: {placement} needs an actual screenshot/image "
                    "to carry through the motion shot")
            absolute = Path(source_path)
            repo_root = project.resolve().parents[1]
            if not absolute.is_absolute():
                absolute = repo_root / absolute
            absolute = absolute.resolve()
            try:
                absolute.relative_to(repo_root.resolve())
            except ValueError:
                raise MotionPlanError(
                    f"AUTO_MOTION_SOURCE_PATH_INVALID: {placement} source escapes the repository") from None
            if not absolute.is_file():
                raise MotionPlanError(f"AUTO_MOTION_SOURCE_MISSING: {placement} image is not on disk")
            spec_probe = specs_dir / f"{placement}.json"
            source_image = Path(os.path.relpath(absolute, spec_probe.parent)).as_posix()
            source_image_sha256 = _file_sha(absolute)

        # A real screenshot is the main picture whenever one exists. OCR is
        # used to focus on the spoken detail; without a match, keep the full
        # source visible and add only a small semantic annotation. Whiteboard
        # and 3b1b grammars are for explanations that have no source image.
        if source_image and source and not source.get("ocr_regions"):
            image_path = Path(source_path)
            if not image_path.is_absolute():
                image_path = project.resolve().parents[1] / image_path
            try:
                stat = image_path.stat()
                ocr_regions = _read_local_ocr(str(image_path.resolve()),
                                              stat.st_mtime_ns, stat.st_size)
                source = {**source, "ocr_regions": list(ocr_regions)}
            except OSError:
                pass
        used_rects = camera_targeted_regions.setdefault(source_asset_id, set())
        source_regions = (_matching_ocr_regions(text, source, used_rects)
                          if source_image and source else [])
        if code_snapshot:
            source_regions = source_regions[:1]
        # Source snapshots must stay visible even when OCR cannot map a line
        # to a precise highlight. Use t2 only for OCR-backed camera targets;
        # a target rectangle is used once per source image. Otherwise use the
        # image-capable whiteboard grammar for progressive explanation.
        grammar = ("t2_keynote_ui" if source_image
                   and "t2_keynote_ui" in allowed
                   else "y3_whiteboard" if code_snapshot
                   and "y3_whiteboard" in allowed
                   else "t1_3b1b" if account_id == "x-superplay-future-intelligence"
                   and kind in {"retrieval", "agent", "protocol"}
                   and "t1_3b1b" in allowed
                   else "y3_whiteboard")
        if grammar == "t2_keynote_ui":
            used_rects.update(json.dumps(region["rect"], separators=(",", ":"))
                              for region in source_regions)
        cues = _cues(text, kind, source_image, grammar, source_regions)
        # Cue timestamps must remain inside this exact measured narration clip.
        latest_cue = max(float(cue["at"]) for cue in cues)
        scale = min(1.0, max(0.0, render_duration - 0.1) / latest_cue) if latest_cue else 1.0
        cues = [{**cue, "at": round(float(cue["at"]) * scale, 3)} for cue in cues]
        visual_role = str(line.get("visual_role") or "").strip().lower()
        if visual_role not in {"proof", "demo", "explain", "context", "transition"}:
            # Source-backed factual lines are visibly marked as proof of the
            # source artifact. Generated illustrations stay explanatory and
            # are never upgraded to execution evidence.
            visual_role = ("proof" if source and line.get("claim")
                           and str(source.get("type") or "").upper()
                           not in {"GENERATED_IMAGE", "GENERATED_VIDEO", "STOCK"}
                           else "explain")
        evidence_ref = line.get("evidence_ref") or (
            (line.get("claim") or source_asset_id) if visual_role == "proof" else None)
        scene_template = str((profile.get("scene_templates") or {}).get(visual_role)
                             or "editorial-diagram")
        spec = {"grammar": grammar, "duration": render_duration, "fps": 30,
                "width": 1080, "height": 1920, "theme": shot_palette,
                "cues": cues,
                "contentops_scene": {"segment_id": str(line.get("segment_id") or placement),
                                     "visual_role": visual_role,
                                     "template": scene_template,
                                     "evidence_ref": evidence_ref,
                                     "style_variant": style_variant}}
        if hold_padding:
            spec["contentops_timing"] = {
                "narration_duration_s": speech_duration,
                "visual_hold_padding_s": hold_padding,
            }
        if source_image_sha256:
            # The upstream renderer ignores this adapter namespace. Including
            # the file hash in the spec makes the existing per-shot cache miss
            # when the real screenshot changes at the same path.
            spec["contentops_source"] = {"asset_id": source_asset_id,
                                         "sha256": source_image_sha256}
        repeated_source = sum(1 for previous in shots
                              if previous.get("source_asset_id") == source_asset_id) > 0
        reuse_reason = None
        if repeated_source:
            reuse_reason = ("same source with a distinct OCR focus region"
                            if source_regions else
                            "same source reused without a distinct focus; visual review required")
        spec_path = specs_dir / f"{placement}-{_sha(spec)[:12]}.json"
        if spec_path.exists():
            try:
                old = json.loads(spec_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise MotionPlanError(f"AUTO_MOTION_STALE_SPEC: {spec_path.name} is unreadable") from None
            if old != spec:
                raise MotionPlanError(
                    f"AUTO_MOTION_STALE_SPEC: {spec_path.relative_to(project).as_posix()} "
                    "exists with different inputs; review before replacing it")
        else:
            spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        shots.append({
            "placement_id": placement,
            "asset_id": f"huashu-{placement}",
            "segment_id": str(line.get("segment_id") or placement),
            "source_asset_id": source_asset_id,
            "visual_role": visual_role,
            "evidence_ref": evidence_ref,
            "scene_template": scene_template,
            "style_variant": style_variant,
            "reuse_reason": reuse_reason,
            "content_point": text,
            "semantic_class": kind,
            "motion_syntax": grammar,
            "backend": profile_backend,
            "spec": spec_path.relative_to(project).as_posix(),
            "duration_s": duration,
            "source_refs": [str(ref) for ref in line.get("source_refs", [])],
            "ocr_targets": source_regions,
            "visual_match": "PENDING_FRAME_REVIEW",
        })
    plan = {"schema": "contentops.motion-shot-plan/v1", "account_id": account_id,
            "profile_version": account_dna.get("version"), "input_sha256": fingerprint,
            "compiler": "contentops.motion_planner/v5",
            "compiler_sha256": planner_sha256, "shots": shots}
    plan_path = auto_dir / f"shot-plan-{fingerprint[:12]}.json"
    if not plan_path.exists():
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return {"path": plan_path, "plan": plan, "input_sha256": fingerprint}
