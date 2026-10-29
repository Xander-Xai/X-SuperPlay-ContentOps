#!/usr/bin/env python3
"""Fail-closed semantic checks for the technical_explainer copy route.

This is deliberately a small editorial contract, not a factuality oracle. It
checks that a mechanism explanation contains the beats declared by the
taxonomy and that conditional performance language is not silently presented
as a universal benchmark result.
"""

from __future__ import annotations

import re
from typing import Any

try:
    from console_encoding import configure_utf8_stdio
except ImportError:  # imported as scripts.technical_explainer_qc
    from scripts.console_encoding import configure_utf8_stdio

configure_utf8_stdio()


BEAT_PATTERNS: dict[str, tuple[str, ...]] = {
    "概念问题": ("解决", "问题", "为什么", "主要"),
    "机制": ("机制", "分页", "block", "物理", "逻辑", "按需", "分配", "回收"),
    "关键术语": ("KV Cache", "PagedAttention", "Attention", "block", "Continuous Batching"),
    "对比边界": ("区分", "区别", "而", "调度", "批处理", "分别"),
    "条件性收益": ("条件", "取决于", "有助于", "通常", "可以", "能够", "在", "视", "取舍"),
    "适用场景": ("并发", "请求", "推理", "场景", "适用", "工作负载"),
    "行动": ("还想", "继续", "复现", "测试", "拆解", "下一步", "行动"),
}

# These phrases are not always false. They are unsafe in a conceptual script
# unless the same sentence supplies a workload/measurement condition.
UNQUALIFIED_BENEFITS: tuple[tuple[str, str], ...] = (
    ("核心收益就是", "把收益写成条件性判断，并注明工作负载或测量条件"),
    ("提升推理吞吐", "改为“在相同请求/配置下可能提升吞吐”，或给出本机 benchmark"),
    ("支持更多并发", "改为“有助于容纳更多并发请求”，不要当作无条件保证"),
    ("减少碎片", "限定为分页分配带来的分配浪费/碎片降低，不要泛化为所有显存碎片"),
)


def _has_condition_near(text: str, phrase: str) -> bool:
    """Return whether a condition marker occurs in the sentence containing phrase."""
    index = text.find(phrase)
    if index < 0:
        return False
    start = max(text.rfind("。", 0, index), text.rfind("；", 0, index), text.rfind("\n", 0, index)) + 1
    end_candidates = [value for value in (text.find("。", index), text.find("；", index), text.find("\n", index)) if value >= 0]
    end = min(end_candidates) if end_candidates else len(text)
    sentence = text[start:end]
    return bool(re.search(r"条件|取决于|相同|配置|工作负载|可能|有助于|通常|测量|实测|benchmark", sentence, re.I))


def audit_text(text: str, *, evidence_level: str = "official") -> dict[str, Any]:
    """Audit one technical explanation and return a serialisable receipt."""
    copy_text = str(text or "").strip()
    lowered = copy_text.lower()
    beats: dict[str, bool] = {}
    for beat, patterns in BEAT_PATTERNS.items():
        beats[beat] = any(pattern.lower() in lowered for pattern in patterns)

    issues: list[dict[str, str]] = []
    if not copy_text:
        issues.append({"code": "empty_voiceover", "message": "technical_explainer voiceover 不能为空"})
    for beat, present in beats.items():
        if not present:
            issues.append({"code": "missing_beat", "beat": beat, "message": f"缺少技术解释段落：{beat}"})

    if evidence_level not in {"official", "user_owned", "local_test", "hypothesis"}:
        issues.append({"code": "invalid_evidence_level", "message": "evidence_level 不在当前证据枚举内"})
    if evidence_level in {"official", "hypothesis"} and "实测" not in copy_text and "benchmark" not in lowered:
        # This is a receipt-level note, not a failure: an official conceptual
        # explanation is allowed to have no local benchmark.
        pass
    for phrase, recommendation in UNQUALIFIED_BENEFITS:
        if phrase in copy_text and not _has_condition_near(copy_text, phrase):
            issues.append({"code": "unqualified_benefit", "phrase": phrase, "message": recommendation})

    return {
        "schema_version": 1,
        "content_type": "technical_explainer",
        "evidence_level": evidence_level,
        "status": "passed" if not issues else "blocked",
        "passed": not issues,
        "beats": beats,
        "issues": issues,
        "method": [
            "先判定概念问题，再解释机制和关键术语",
            "明确与相邻能力的边界，避免把内存管理和调度混为一谈",
            "把收益写成有条件的适用判断；没有本机 benchmark 就不写成实测结论",
            "最后保留一个可分类的下一步动作",
        ],
    }


def validate_payload(payload: dict[str, Any]) -> list[str]:
    """Bridge the plain-text audit into the canonical copy-brief validator."""
    if str(payload.get("content_type", "")).strip() != "technical_explainer":
        return []
    receipt = audit_text(str(payload.get("voiceover", "")), evidence_level=str(payload.get("evidence_level", "")))
    return [f"technical_explainer: {item['message']}" for item in receipt["issues"]]
