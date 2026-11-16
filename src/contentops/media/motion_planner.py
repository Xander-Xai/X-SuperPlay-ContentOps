"""Account-DNA-driven Huashu Art Motion shot plans for M5.

This first compiler is deliberately bounded to the two active video accounts.
It emits parameterized, source-traceable clips for known technical concepts and
fails closed when a line cannot be placed into a meaningful visual grammar.
It does not invent benchmark values or treat generated visuals as evidence.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from contentops.evidence.source_artifact import EVIDENCE_CAPABLE_PERMISSIONS, PERMISSIONS
from contentops.media.animation_backend import palette_from_dna
from contentops.media.source_anchor import pick_rects

# Vertical 1080x1920 films burn subtitles at roughly y=1400..1520. Every
# parameterised grammar respects ``safe`` for its own layout, so the reserved
# band is declared once here instead of nudging each cue by hand.
SUBTITLE_SAFE_BOTTOM = 520


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
    # Model-training / adaptation topics used to fall through to
    # "unsupported" and block the whole automatic shot plan. The visual form
    # of the asset (a verbatim excerpt card, a screenshot, a vector) is not
    # what this classifier reads: it reads the spoken line's semantics.
    if re.search(r"证据|声明|收据|工作流|人工审核|复核|门禁|链路|审批|"
                 r"receipt|workflow|gate", folded):
        return "workflow"
    if re.search(
            r"sft|qlora|lora|微调|量化|低秩|显存|参数|模型|训练|推理|rlhf|"
            r"nf4|4-bit|4bit|transformer|adapter|注意力|梯度|checkpoint|"
            r"蒸馏|对齐|监督|预训练|batch|epoch", folded):
        return "model"
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


def _labelled_steps(kind: str, text: str) -> List[tuple[str, str]]:
    """Process labels a whiteboard shot can draw, derived from the spoken line."""
    if kind == "retrieval":
        lexical = "BM25 召回" if re.search(r"\bbm25\b", text, re.I) else "词项召回"
        semantic = "向量召回" if "向量" in text or "vector" in text.lower() else "语义召回"
        final = "重排候选" if re.search(r"重排|rerank", text, re.I) else "候选汇合"
        return [(lexical, "doc"), (semantic, "target"), (final, "stack")]
    if kind == "agent":
        return [("Agent 状态", "person"), ("调用工具", "screen"), ("结果返回", "check")]
    if kind == "protocol":
        return [("客户端", "screen"), ("协议边界", "network"), ("服务端工具", "gear")]
    if kind == "metric":
        return [("来源指标", "chart"), ("对照口径", "target"), ("结论一条", "check")]
    if kind == "model":
        return [("预训练主干", "gear"), ("低秩适配器", "stack"),
                ("量化与显存", "chart")]
    if kind == "workflow":
        return [("真实来源", "doc"), ("人工复核", "check"), ("收据留痕", "stack")]
    return [("真实代码", "screen"), ("配置入口", "gear"), ("运行结果", "check")]


def _y3_cues(text: str, kind: str, *, duration: float) -> List[Dict[str, Any]]:
    """Whiteboard: draw a thing, then write the line that names it."""
    steps = _labelled_steps(kind, text)
    cues: List[Dict[str, Any]] = []
    cursor = 0.0
    step = max(0.85, min(1.35, (duration - 0.6) / max(1, len(steps))))
    for index, (label, icon) in enumerate(steps):
        if index % 2 == 0:
            cues.append({"at": round(cursor, 3), "kind": "draw", "text": label,
                         "data": {"icon": icon}})
        else:
            cues.append({"at": round(cursor, 3), "kind": "point",
                         "text": _short_label(label if len(label) > 5 else text, 18)})
        cursor += step
    cues.append({"at": round(min(cursor, max(0.4, duration - 0.5)), 3),
                 "kind": "highlight", "data": {"target": "draw", "index": 0}})
    return cues


def _t2_cues(text: str, source_image: str, rects: Sequence[Mapping[str, Any]],
             *, duration: float) -> List[Dict[str, Any]]:
    """Evidence shot: the still is the main picture, the camera finds the line.

    Huashu t2 pushes only when the framed rectangle is narrow enough
    (``zoom = fill / rect_width``, capped at 2.6). The rectangles come from the
    anchor's own line geometry, so each camera move lands on real source lines
    instead of an OCR box spanning the whole column.
    """
    cues: List[Dict[str, Any]] = [{"at": 0.0, "kind": "image", "image": source_image,
                                   "text": _short_label(text, 14)}]
    if not rects:
        return cues
    take = list(rects[:2]) if duration >= 4.4 else list(rects[:1])
    span = max(1.0, (duration - 1.6) / max(1, len(take)))
    for index, region in enumerate(take):
        rect = region.get("rect") if isinstance(region, Mapping) else region
        width = float(rect[2])
        fill = round(min(0.96, max(0.58, 1.55 * width)), 3)
        cues.append({"at": round(1.15 + index * span, 3), "kind": "highlight",
                     "data": {"rect": [round(float(value), 6) for value in rect],
                              "fill": fill}})
    return cues


def _t1_cues(text: str, kind: str) -> List[Dict[str, Any]]:
    """3b1b: one object at a time, each step transforming the previous one."""
    if kind == "retrieval" and re.search(r"\bRRF\b", text, re.I):
        return [
            {"at": 0.0, "kind": "equation", "text": "rankᵢ(d)"},
            {"at": 1.05, "kind": "equation", "text": "1 / (k + rankᵢ(d))"},
            {"at": 2.1, "kind": "equation",
             "text": "score(d) = Σᵢ 1 / (k + rankᵢ(d))"},
            {"at": 3.1, "kind": "point", "text": "按名次累加倒数贡献"},
            {"at": 3.85, "kind": "highlight", "data": {"target": "equation"}},
        ]
    if kind == "retrieval" and re.search(r"原始分|score scale|raw score", text, re.I):
        return [
            {"at": 0.0, "kind": "equation", "text": "BM25 原始分"},
            {"at": 1.05, "kind": "equation", "text": "向量相似度"},
            {"at": 2.1, "kind": "equation",
             "text": "1/(k+rank₁(d)) + 1/(k+rank₂(d))"},
            {"at": 3.1, "kind": "point", "text": "按排名融合，不直接比原始分"},
            {"at": 3.85, "kind": "highlight", "data": {"target": "equation"}},
        ]
    if kind == "retrieval":
        lexical = "BM25" if re.search(r"\bBM25\b", text, re.I) else "词项"
        semantic = "向量" if ("向量" in text or "dense" in text.lower()) else "语义"
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
    # Agent / protocol / code / metric: name each party in the order the line
    # names it, then transform the pair into the relationship. Only labels that
    # occur in the narration are drawn, so the animation cannot assert a state
    # or boundary the source did not name.
    vocabulary = (
        (r"智能体|\bagent\b", "Agent"),
        (r"客户端|\bclient\b", "Client"),
        (r"mcp", "MCP"),
        (r"协议|\bprotocol\b", "协议"),
        (r"状态|\bstate\b", "状态"),
        (r"工具调用|调用工具|工具|\btool", "工具"),
        (r"服务端|\bserver\b", "Server"),
        (r"缓存|\bcache\b", "缓存"),
        (r"护栏|guardrail", "护栏"),
        (r"重排|rerank", "重排"),
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
        cues = [{"at": round(index * 0.95, 2), "kind": "equation",
                 "text": f"{left} → {right}"} for index, (left, right) in enumerate(pairs)]
        cues.append({"at": round(len(pairs) * 0.95, 2), "kind": "highlight",
                     "data": {"target": "equation"}})
        return cues
    return [
        {"at": 0.0, "kind": "equation", "text": terms[0] if terms else "输入"},
        {"at": 1.1, "kind": "point", "text": _short_label(text, 18)},
        {"at": 2.2, "kind": "highlight", "data": {"target": "equation"}},
    ]


def _grammar_for(account_id: str, role: str, kind: str, has_still: bool,
                 allowed: set[str], index: int) -> str:
    """Pick the drawing syntax from what the line does and what the account is for.

    The account DNA decides the bias, the shot decides the exception:

    * ``x-superplay-1024`` is evidence-led: a registered still carries every
      factual or explanatory beat, and only the opening/closing section marker
      is drawn. That keeps ~87% of frames on real source material, above the
      account's 70% floor.
    * ``x-superplay-future-intelligence`` explains in vectors: proof beats
      still show the real excerpt, everything else is drawn, alternating
      between the 3b1b transform grammar and the whiteboard so neighbouring
      shots never share a composition.

    The rule is deliberately not "if a picture exists, use it": that is what
    turned both accounts into the same screenshot-plus-push film.
    """
    evidence_ok = has_still and "t2_keynote_ui" in allowed
    if role in {"proof", "demo"} and evidence_ok:
        return "t2_keynote_ui"
    if account_id == "x-superplay-1024":
        if role == "transition" and "y3_whiteboard" in allowed:
            return "y3_whiteboard"
        if evidence_ok:
            return "t2_keynote_ui"
        if "y3_whiteboard" in allowed:
            return "y3_whiteboard"
        return "t1_3b1b"
    if role == "transition" and "y3_whiteboard" in allowed:
        return "y3_whiteboard"
    if kind in {"retrieval", "agent", "protocol"} and "t1_3b1b" in allowed:
        return "t1_3b1b" if index % 2 == 0 else (
            "y3_whiteboard" if "y3_whiteboard" in allowed else "t1_3b1b")
    if "y3_whiteboard" in allowed:
        return "y3_whiteboard"
    return "t1_3b1b" if "t1_3b1b" in allowed else "t2_keynote_ui"


def _cues(text: str, kind: str, source_image: str | None,
          grammar: str, source_regions: Sequence[Mapping[str, Any]] = (),
          *, duration: float = 3.0) -> List[Dict[str, Any]]:
    """Build the shot's visual beats for the grammar that will actually run.

    Every emitted ``kind`` must be one the chosen grammar draws. Huashu ignores
    unknown kinds without an error, so a whiteboard ``draw`` cue inside a
    ``t2_keynote_ui`` spec used to render nothing at all -- the shot silently
    lost a third of its beats.
    """
    if grammar == "t2_keynote_ui":
        if not source_image:
            raise MotionPlanError(
                "AUTO_MOTION_SOURCE_MISSING: the evidence grammar needs a registered still")
        return _t2_cues(text, source_image, source_regions, duration=duration)
    if grammar == "t1_3b1b":
        return _t1_cues(text, kind)
    if grammar == "y3_whiteboard":
        return _y3_cues(text, kind, duration=duration)
    raise MotionPlanError(f"AUTO_MOTION_GRAMMAR_UNSUPPORTED: {grammar!r}")


ANIMATION_TEMPLATE_GRAMMARS = {
    "architecture_flow": "y3_whiteboard",
    "state_transition": "y3_whiteboard",
    "code_focus": "t2_keynote_ui",
    "evidence_zoom": "t2_keynote_ui",
    "metric_transition": "t3_finance_chart",
    "comparison_reveal": "y3_whiteboard",
}
_TEMPLATE_ICONS = {"person", "network", "doc", "chat", "bulb", "check", "cross",
                   "screen", "stack", "gear", "target", "clock", "chart"}
_TEMPLATE_RECORDING_KINDS = {
    "SCREEN_RECORDING", "REAL_SCREEN_RECORDING", "REAL_RECORDING", "MANUAL_RECORDING",
}
_GENERATED_SOURCE_KINDS = {"GENERATED_IMAGE", "GENERATED_VIDEO", "GENERATED_AUDIO"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _template_source(line: Mapping[str, Any], source_assets: Mapping[str, Mapping[str, Any]],
                     animation_type: str) -> tuple[str, Mapping[str, Any], str, bool]:
    source_id = str(line.get("asset_id") or "").strip()
    source = source_assets.get(source_id)
    if not source_id or not isinstance(source, Mapping):
        raise MotionPlanError(f"AUTO_MOTION_TEMPLATE_SOURCE_MISSING: {animation_type}")
    source_kind = str(source.get("type") or "").upper()
    permission = str(source.get("permission") or "").upper()
    sha256 = str(source.get("sha256") or "").lower()
    if permission not in PERMISSIONS:
        raise MotionPlanError(f"AUTO_MOTION_TEMPLATE_PERMISSION_INVALID: {animation_type}")
    if permission == "NONE":
        raise MotionPlanError(f"AUTO_MOTION_TEMPLATE_RIGHTS_UNCLEARED: {animation_type}")
    if source_kind in _GENERATED_SOURCE_KINDS or not _SHA256_RE.fullmatch(sha256):
        raise MotionPlanError(f"AUTO_MOTION_TEMPLATE_SOURCE_INVALID: {animation_type}")
    claim_ref = str(line.get("claim") or line.get("claim_ref") or "").strip()
    editorial_only = line.get("editorial_only") is True
    if bool(claim_ref) == editorial_only:
        raise MotionPlanError(
            f"AUTO_MOTION_TEMPLATE_CLAIM_OR_EDITORIAL_REQUIRED: {animation_type}")
    refs = line.get("source_refs") or []
    if claim_ref and (permission not in EVIDENCE_CAPABLE_PERMISSIONS or not refs):
        raise MotionPlanError(f"AUTO_MOTION_TEMPLATE_SOURCE_NOT_CLAIM_CAPABLE: {animation_type}")
    if animation_type == "code_focus":
        document_sha = str(source.get("source_document_sha256") or "").lower()
        if source_kind != "CODE_SNAPSHOT" or not _SHA256_RE.fullmatch(document_sha):
            raise MotionPlanError("AUTO_MOTION_CODE_SOURCE_UNBOUND: expected a digest-bound CODE_SNAPSHOT")
    if animation_type == "metric_transition":
        if source_kind not in {"REAL_DOCUMENT", "METRIC_RECORD", "DATASET"}:
            raise MotionPlanError("AUTO_MOTION_METRIC_SOURCE_INVALID: a registered data/document source is required")
        if permission not in EVIDENCE_CAPABLE_PERMISSIONS:
            raise MotionPlanError("AUTO_MOTION_METRIC_SOURCE_NOT_CLAIM_CAPABLE")
    return source_id, source, claim_ref, editorial_only


def _template_labels(value: Any, name: str, minimum: int, maximum: int) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise MotionPlanError(f"AUTO_MOTION_TEMPLATE_INPUT_INVALID: {name} needs {minimum}-{maximum} entries")
    labels = []
    for item in value:
        label = str(item.get("label") or "").strip() if isinstance(item, Mapping) else str(item).strip()
        if not label or len(label) > 48:
            raise MotionPlanError(f"AUTO_MOTION_TEMPLATE_INPUT_INVALID: {name} labels must be 1-48 chars")
        labels.append(label)
    return labels


def _template_rect(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != 4:
        raise MotionPlanError("AUTO_MOTION_FOCUS_RECT_INVALID: expected [x,y,width,height]")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise MotionPlanError("AUTO_MOTION_FOCUS_RECT_INVALID: coordinates must be finite numbers")
    try:
        converted = [float(item) for item in value]
    except (OverflowError, ValueError, TypeError):
        raise MotionPlanError("AUTO_MOTION_FOCUS_RECT_INVALID: coordinates must be finite numbers") from None
    if any(not math.isfinite(item) for item in converted):
        raise MotionPlanError("AUTO_MOTION_FOCUS_RECT_INVALID: coordinates must be finite numbers")
    x, y, width, height = converted
    if (x < 0 or y < 0 or width <= 0 or height <= 0
            or x + width > 1 or y + height > 1):
        raise MotionPlanError("AUTO_MOTION_FOCUS_RECT_INVALID: rectangle must fit the source frame")
    return [round(x, 6), round(y, 6), round(width, 6), round(height, 6)]


def _whiteboard_flow_cues(labels: Sequence[str], duration: float,
                          icons: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    chosen = list(icons or ())
    if chosen and len(chosen) != len(labels):
        raise MotionPlanError("AUTO_MOTION_TEMPLATE_INPUT_INVALID: icon count must match labels")
    cues: List[Dict[str, Any]] = []
    span = max(0.25, (duration - 0.9) / len(labels))
    for index, label in enumerate(labels):
        icon = chosen[index] if chosen else ("check" if index == len(labels) - 1 else "network")
        if icon not in _TEMPLATE_ICONS:
            raise MotionPlanError(f"AUTO_MOTION_TEMPLATE_ICON_UNSUPPORTED: {icon!r}")
        cues.append({"at": round(0.2 + index * span, 3), "kind": "draw",
                     "text": label,
                     "data": {"icon": icon, "arrow": index < len(labels) - 1}})
    cues.append({"at": round(duration - 0.45, 3), "kind": "highlight",
                 "data": {"target": "draw", "index": len(labels) - 1}})
    return cues


def _template_cues(animation_type: str, params: Mapping[str, Any], line: Mapping[str, Any],
                   source: Mapping[str, Any], source_image: Optional[str],
                   source_regions: Sequence[Mapping[str, Any]], duration: float,
                   account_id: str) -> tuple[str, List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Compile a named, parameterized shot through only verified runtime grammars."""
    source_kind = str(source.get("type") or "").upper()
    if animation_type == "architecture_flow":
        labels = _template_labels(params.get("nodes"), "nodes", 2, 6)
        return "y3_whiteboard", _whiteboard_flow_cues(labels, duration), None
    if animation_type == "state_transition":
        labels = _template_labels(params.get("states"), "states", 2, 5)
        transition = str(params.get("transition") or "").strip()
        success = str(params.get("success") or "").strip()
        failure = str(params.get("failure") or "").strip()
        if (not transition or not success or not failure
                or max(len(transition), len(success), len(failure)) > 48):
            raise MotionPlanError(
                "AUTO_MOTION_TEMPLATE_INPUT_INVALID: transition, success and failure labels are required")
        primary_end = duration * 0.55
        step = (primary_end - 0.2) / (len(labels) + 1)
        if step < 0.18:
            raise MotionPlanError("AUTO_MOTION_TEMPLATE_TIMING_INVALID: too many states for this duration")
        cues = [{"at": round(0.2 + index * step, 3), "kind": "draw", "text": label,
                 "data": {"icon": "network", "arrow": True}}
                for index, label in enumerate(labels)]
        cues.extend([
            {"at": round(0.2 + len(labels) * step, 3), "kind": "point", "text": transition},
            {"at": round(duration * 0.62, 3), "kind": "draw", "text": success,
             "data": {"icon": "check", "branch": "success", "arrow": False}},
            {"at": round(duration * 0.76, 3), "kind": "draw", "text": failure,
             "data": {"icon": "cross", "branch": "failure", "arrow": False}},
            {"at": round(duration - 0.45, 3), "kind": "highlight",
             "data": {"target": "draw", "index": len(labels) - 1}},
        ])
        if cues[-2]["at"] >= cues[-1]["at"] or cues[-3]["at"] >= cues[-2]["at"]:
            raise MotionPlanError("AUTO_MOTION_TEMPLATE_TIMING_INVALID: outcome branches overlap")
        return "y3_whiteboard", cues, None
    if animation_type == "comparison_reveal":
        before = str(params.get("before") or "").strip()
        after = str(params.get("after") or "").strip()
        if not before or not after or max(len(before), len(after)) > 48:
            raise MotionPlanError("AUTO_MOTION_TEMPLATE_INPUT_INVALID: before/after labels are required")
        return "y3_whiteboard", _whiteboard_flow_cues(
            [before, after], duration, ["cross", "check"]), None
    if animation_type in {"code_focus", "evidence_zoom"}:
        if not source_image:
            raise MotionPlanError(f"AUTO_MOTION_SOURCE_MISSING: {animation_type} needs a registered image")
        if animation_type == "code_focus":
            if source_kind != "CODE_SNAPSHOT":
                raise MotionPlanError("AUTO_MOTION_CODE_SOURCE_INVALID: code_focus needs CODE_SNAPSHOT")
            if not _SHA256_RE.fullmatch(str(source.get("source_document_sha256") or "").lower()):
                raise MotionPlanError("AUTO_MOTION_CODE_SOURCE_UNBOUND: source document digest is required")
        elif source_kind not in {"REAL_SCREENSHOT", "SCREENSHOT", "SCREEN_RECORDING"}:
            raise MotionPlanError("AUTO_MOTION_EVIDENCE_SOURCE_INVALID: evidence_zoom needs a real capture")
        if account_id == "x-superplay-future-intelligence" and source_kind in _TEMPLATE_RECORDING_KINDS:
            raise MotionPlanError("RECORDING_FORBIDDEN: future-intelligence forbids recording input")
        regions = list(source_regions)
        focus_rect = params.get("focus_rect")
        if focus_rect is not None:
            regions = [{"text": str(params.get("focus_label") or line.get("visual_focus") or "Source focus"),
                        "confidence": 1.0, "rect": _template_rect(focus_rect),
                        "matched_terms": []}]
        if not regions:
            raise MotionPlanError(f"AUTO_MOTION_FOCUS_MISSING: {animation_type} needs a source-bound focus region")
        text = str(line.get("visual_focus") or line.get("narration") or "").strip()
        return "t2_keynote_ui", _t2_cues(text, source_image, regions, duration=duration), None
    if animation_type == "metric_transition":
        if params.get("source_asset_id") != line.get("asset_id"):
            raise MotionPlanError("AUTO_MOTION_METRIC_SOURCE_MISMATCH: chart data must cite the shot source asset")
        if source_kind in _GENERATED_SOURCE_KINDS:
            raise MotionPlanError("AUTO_MOTION_METRIC_SOURCE_INVALID: generated material cannot source metrics")
        title, unit, source_label = (str(params.get(key) or "").strip()
                                     for key in ("title", "unit", "source_label"))
        chart = str(params.get("chart") or "bar").strip().lower()
        if (not title or not unit or not source_label or max(len(title), len(unit)) > 80
                or len(source_label) > 120 or chart not in {"bar", "line"}):
            raise MotionPlanError("AUTO_MOTION_METRIC_INPUT_INVALID: title, unit, source and bar/line chart are required")
        if re.match(r"^(?:[A-Za-z]:[\\/]|\\\\|/)", source_label):
            raise MotionPlanError("AUTO_MOTION_METRIC_SOURCE_INVALID: source label must not expose a host path")
        raw_series = params.get("series")
        if not isinstance(raw_series, list) or not 2 <= len(raw_series) <= 12:
            raise MotionPlanError("AUTO_MOTION_METRIC_INPUT_INVALID: series needs 2-12 sourced values")
        series = []
        for row in raw_series:
            if not isinstance(row, Mapping):
                raise MotionPlanError("AUTO_MOTION_METRIC_INPUT_INVALID: each series row needs label/value")
            label = str(row.get("label") or "").strip()
            value = row.get("value")
            if not label or len(label) > 32 or isinstance(value, bool) \
                    or not isinstance(value, (int, float)):
                raise MotionPlanError("AUTO_MOTION_METRIC_INPUT_INVALID: labels and finite numeric values are required")
            try:
                numeric_value = float(value)
            except (OverflowError, ValueError, TypeError):
                raise MotionPlanError("AUTO_MOTION_METRIC_INPUT_INVALID: labels and finite numeric values are required") from None
            if not math.isfinite(numeric_value):
                raise MotionPlanError("AUTO_MOTION_METRIC_INPUT_INVALID: labels and finite numeric values are required")
            series.append({"label": label, "value": value})
        source_path = source.get("_template_source_path")
        try:
            source_record = json.loads(Path(str(source_path)).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            raise MotionPlanError("AUTO_MOTION_METRIC_SOURCE_UNREADABLE: expected a JSON source record") from None
        if not isinstance(source_record, Mapping):
            raise MotionPlanError("AUTO_MOTION_METRIC_SOURCE_INVALID: source record must be an object")
        registered_series = source_record.get("series")
        if (source_record.get("title") != title or source_record.get("unit") != unit
                or source_record.get("citation") != source_label
                or not isinstance(registered_series, list)
                or registered_series != series):
            raise MotionPlanError(
                "AUTO_MOTION_METRIC_SOURCE_MISMATCH: title, unit, citation and values must match hashed source")
        data = {"title": title, "unit": unit, "source": source_label,
                "chart": chart, "series": series}
        if "highlight_index" in params:
            highlight_value = params["highlight_index"]
            if isinstance(highlight_value, bool) or not isinstance(highlight_value, int):
                raise MotionPlanError("AUTO_MOTION_METRIC_INPUT_INVALID: highlight_index must be an integer")
            highlight = highlight_value
            if not 0 <= highlight < len(series):
                raise MotionPlanError("AUTO_MOTION_METRIC_INPUT_INVALID: highlight_index is outside series")
            data["highlight"] = {"index": highlight, "text": series[highlight]["label"]}
        start = 0.8
        cues = [{"at": 0.0, "kind": "title"}]
        if chart == "bar":
            spacing = min(0.35, max(0.12, (duration - 1.6) / len(series)))
            cues.extend({"at": round(start + index * spacing, 3), "kind": "bar",
                         "dur": 0.7, "data": {"index": index}}
                        for index in range(len(series)))
        else:
            cues.append({"at": start, "kind": "line", "dur": min(1.8, duration - 1.2)})
        if "highlight" in data:
            cues.append({"at": round(duration - 0.5, 3), "kind": "highlight",
                         "text": data["highlight"]["text"],
                         "data": {"index": data["highlight"]["index"]}})
        if max(float(cue["at"]) for cue in cues) >= duration:
            raise MotionPlanError("AUTO_MOTION_METRIC_TIMING_INVALID: cues exceed clip duration")
        return "t3_finance_chart", cues, data
    raise MotionPlanError(f"AUTO_MOTION_TEMPLATE_UNSUPPORTED: {animation_type!r}")


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
    brand = account_dna.get("brand") or {}
    brand_palette = brand.get("palette") if isinstance(brand, Mapping) else None
    refresh = brand.get("refresh") if isinstance(brand, Mapping) else {}
    refresh = refresh if isinstance(refresh, Mapping) else {}
    refresh_target = str(refresh.get("target_palette") or "").strip()
    if refresh_target and refresh_target != "brand.palette":
        raise MotionPlanError(
            f"AUTO_MOTION_PALETTE_TARGET_UNSUPPORTED: {refresh_target!r}")
    style_variants = profile.get("style_variants") or {}
    if isinstance(brand_palette, Mapping):
        try:
            palette = palette_from_dna(account_dna)
        except ValueError as exc:
            raise MotionPlanError(f"AUTO_MOTION_PALETTE_INVALID: {exc}") from None
        # The profile's old variants remain useful historical context, but a
        # declared brand palette is the render input. Never relabel it as an old
        # variant, and never allow a per-shot variant to restore stale colors.
        default_variant = "brand.palette"
        style_variants = {}
    else:
        palette = profile.get("palette") or {}
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
    visual = account_dna.get("visual") or {}
    motion = visual.get("motion") or {}
    identity = {
        "account": account_id,
        "profile": profile,
        "resolved_palette": palette,
        "brand_palette": brand_palette,
        "brand_refresh": refresh,
        "brand_forbidden_effects": brand.get("forbidden_effects", [])
        if isinstance(brand, Mapping) else [],
        "motion_allowed": motion.get("allowed", []),
        "motion_forbidden": motion.get("forbidden", []),
        "caption_style": visual.get("caption_style", {}),
        "render": account_dna.get("render", {}),
        "retention": account_dna.get("retention", {}),
        "script": script,
        "narration": narration,
        "assets": source_assets,
        "planner_sha256": planner_sha256,
    }
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
        requested_variant = str(line.get("style_variant") or "")
        if isinstance(brand_palette, Mapping):
            if requested_variant and requested_variant != "brand.palette":
                raise MotionPlanError(
                    f"AUTO_MOTION_STALE_STYLE_VARIANT: {requested_variant!r} conflicts with brand.palette")
            style_variant = "brand.palette"
        else:
            style_variant = requested_variant or default_variant
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
        requested_animation_type = str(line.get("animation_type") or "").strip()
        if kind == "unsupported" and str((source or {}).get("type") or "").upper() == "CODE_SNAPSHOT":
            kind = "code"
        if kind == "unsupported" and requested_animation_type:
            kind = requested_animation_type
        if kind == "unsupported":
            raise MotionPlanError(f"AUTO_MOTION_UNSUPPORTED: no semantic visual grammar matched {placement}")

        animation_type = requested_animation_type
        template_params = line.get("animation") or {}
        if animation_type:
            if not isinstance(template_params, Mapping):
                raise MotionPlanError("AUTO_MOTION_TEMPLATE_INPUT_INVALID: animation must be an object")
            grammar = ANIMATION_TEMPLATE_GRAMMARS.get(animation_type)
            if not grammar:
                raise MotionPlanError(f"AUTO_MOTION_TEMPLATE_UNSUPPORTED: {animation_type!r}")
            if grammar not in allowed:
                raise MotionPlanError(f"AUTO_MOTION_GRAMMAR_UNAVAILABLE: {grammar} is not allowed")
            source_asset_id, source, claim_ref, editorial_only = _template_source(
                line, source_assets, animation_type)
            source_path = str(source.get("repo_path") or "")
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
            if not absolute.is_file() or _file_sha(absolute) != str(source.get("sha256") or "").lower():
                raise MotionPlanError(f"AUTO_MOTION_TEMPLATE_SOURCE_HASH_MISMATCH: {placement}")
            source = {**source, "_template_source_path": str(absolute)}
            if animation_type == "metric_transition" and absolute.suffix.lower() != ".json":
                raise MotionPlanError("AUTO_MOTION_METRIC_SOURCE_INVALID: metrics need a JSON source record")
            if animation_type == "code_focus" and absolute.suffix.lower() not in IMAGE_SUFFIXES:
                raise MotionPlanError("AUTO_MOTION_CODE_SOURCE_INVALID: code snapshot must have a renderable image")
            if animation_type == "evidence_zoom" and absolute.suffix.lower() not in IMAGE_SUFFIXES:
                raise MotionPlanError("AUTO_MOTION_EVIDENCE_SOURCE_INVALID: evidence zoom needs a still image")
        else:
            grammar = None
            claim_ref = ""
            editorial_only = False

        source_image = None
        source_image_sha256 = None
        code_snapshot = str((source or {}).get("type") or "").upper() == "CODE_SNAPSHOT"
        has_still = bool(source) and Path(str(source.get("repo_path") or "")).suffix.lower() \
            in IMAGE_SUFFIXES
        visual_role_hint = str(line.get("visual_role") or "").strip().lower()
        if not animation_type:
            grammar = _grammar_for(account_id, visual_role_hint, kind, has_still, allowed, index)
        if grammar == "t2_keynote_ui":
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

        # Camera targets come from the anchor's own line geometry when the
        # anchor recorded it: those rectangles are exactly one to three source
        # lines tall, so ``fill / rect_width`` really does push the camera.
        # OCR boxes are the fallback for imported screenshots.
        used_rects = camera_targeted_regions.setdefault(
            str((source or {}).get("sha256") or source_asset_id), set())
        layout = (source or {}).get("text_layout") or {}
        if source_image and layout:
            source_regions = [{"rect": rect, "text": _short_label(text, 20),
                               "confidence": 1.0, "matched_terms": []}
                              for rect in pick_rects(layout, text, exclude=used_rects)]
        elif source_image and source:
            if not source.get("ocr_regions"):
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
            source_regions = _matching_ocr_regions(text, source, used_rects)
        else:
            source_regions = []
        if code_snapshot:
            source_regions = source_regions[:1]
        if grammar == "t2_keynote_ui":
            used_rects.update(json.dumps(list(region["rect"]), separators=(",", ":"))
                              for region in source_regions)
        if animation_type:
            grammar, cues, template_data = _template_cues(
                animation_type, template_params, line, source, source_image,
                source_regions, render_duration, account_id)
        else:
            cues = _cues(text, kind, source_image, grammar, source_regions,
                         duration=render_duration)
            template_data = None
        # Cue timestamps must remain inside this exact measured narration clip.
        latest_cue = max(float(cue["at"]) for cue in cues)
        scale = min(1.0, max(0.0, render_duration - 0.1) / latest_cue) if latest_cue else 1.0
        cues = [{**cue, "at": round(float(cue["at"]) * scale, 3)} for cue in cues]
        visual_role = str(line.get("visual_role") or "").strip().lower()
        if visual_role not in {"proof", "demo", "explain", "context", "transition"}:
            # Generated motion is always supporting material, even when its
            # source is claim-capable; it must never become the proof asset.
            visual_role = "explain" if animation_type else (
                "proof" if source and line.get("claim")
                and str(source.get("type") or "").upper()
                not in {"GENERATED_IMAGE", "GENERATED_VIDEO", "STOCK"}
                else "explain")
        if animation_type and visual_role == "proof":
            raise MotionPlanError("AUTO_MOTION_TEMPLATE_NOT_EVIDENCE: generated motion cannot be a proof shot")
        evidence_ref = line.get("evidence_ref") or (
            (line.get("claim") or source_asset_id) if visual_role == "proof" else None)
        scene_template = str((profile.get("scene_templates") or {}).get(visual_role)
                             or "editorial-diagram")
        spec = {"grammar": grammar, "duration": render_duration, "fps": 30,
                "width": 1080, "height": 1920, "theme": shot_palette,
                "safe": {"top": 0, "bottom": SUBTITLE_SAFE_BOTTOM,
                         "fill": str(shot_palette.get("bg") or "")},
                "cues": cues,
                "contentops_scene": {"segment_id": str(line.get("segment_id") or placement),
                                     "visual_role": visual_role,
                                     "template": scene_template,
                                     "evidence_ref": evidence_ref,
                                     "style_variant": style_variant}}
        if animation_type:
            spec["contentops_scene"].update({
                "animation_type": animation_type,
                "source_asset_id": source_asset_id,
                "claim_ref": claim_ref or None,
                "editorial_only": editorial_only,
            })
        if template_data is not None:
            spec["data"] = template_data
        if hold_padding:
            spec["contentops_timing"] = {
                "narration_duration_s": speech_duration,
                "visual_hold_padding_s": hold_padding,
            }
        if source_image_sha256:
            # The upstream renderer ignores this adapter namespace. Including
            # the file hash in the spec makes the existing per-shot cache miss
            # when the real screenshot changes at the same path.
            spec["contentops_source"] = {
                "asset_id": source_asset_id,
                "sha256": source_image_sha256,
                **({"source_document_sha256": str(source.get("source_document_sha256")).lower()}
                   if source.get("source_document_sha256") else {}),
            }
        elif animation_type:
            # Non-image sources (notably metric records) also participate in
            # per-shot cache identity; a changed source must not reuse a stale clip.
            spec["contentops_source"] = {
                "asset_id": source_asset_id,
                "sha256": str(source.get("sha256") or "").lower(),
            }
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
            # LF only: git normalizes *.json to LF, so writing CRLF here would
            # make a fresh checkout hash differently from the render receipt.
            spec_path.write_bytes(
                (json.dumps(spec, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        shot = {
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
        }
        if animation_type:
            shot.update({"animation_type": animation_type,
                         "claim_ref": claim_ref or None,
                         "editorial_only": editorial_only})
        shots.append(shot)
    plan = {"schema": "contentops.motion-shot-plan/v1", "account_id": account_id,
            "profile_version": account_dna.get("version"), "input_sha256": fingerprint,
            "compiler": "contentops.motion_planner/v6",
            "compiler_sha256": planner_sha256, "shots": shots}
    plan_path = auto_dir / f"shot-plan-{fingerprint[:12]}.json"
    if not plan_path.exists():
        plan_path.write_bytes(
            (json.dumps(plan, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return {"path": plan_path, "plan": plan, "input_sha256": fingerprint}
