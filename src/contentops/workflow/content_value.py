"""Content Value & Information-Gain Gate (T04).

Empty copy is rarely just a phrasing problem — most often the research input
carries no real findings, no concrete observation, and no creator judgment, so
the writer only has README summaries and filler to work with.

This module provides a structured ``contentops.value-brief/v1`` contract and
honest evaluator that checks:
1. Whether the research answers *why a viewer should care*, *what specific
   problem is solved*, and *what information delta exists beyond README/news*.
2. Whether concrete findings (code paths, commands, measured numbers, real
   errors, trade-offs) are present with source attribution.
3. Whether first-person experience claims ("我用了三天", "我亲测有效",
   "我踩了一个坑") are backed by ``evidence_basis == "first_hand_execution"``
   rather than fabricated from reading docs.

It never fabricates evidence, never approves publication, and never replaces
human editorial judgment.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

SCHEMA = "contentops.value-brief/v1"

EVIDENCE_BASES = (
    "first_hand_execution",
    "source_code_audit",
    "verified_official_docs",
    "literature_synthesis",
)

FIRST_PERSON_EXPERIENCE_PATTERNS = (
    re.compile(r"我(?:亲自|实际|重度|深度|亲自重度)?(?:用了|使用了|测了|跑了|试了|体验了)[^\n。！？]{0,18}[一二三四五六七八九十\d]+[天周月次遍小时]"),
    re.compile(r"我亲测(?:有效|可用|发现|跑通)"),
    re.compile(r"我(?:自己)?踩了(?:一个|不少|很多)?坑"),
    re.compile(r"实测下来我发现"),
)

CONCRETE_EVIDENCE_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:%|ms|s|秒|分钟|小时|GB|MB|KB|px|帧|项|条|个|行|次|元|pp)"
    r"|[A-Za-z0-9_.-]+\.(?:py|js|ts|json|yaml|yml|md|html|mp4|png)"
    r"|:\d+|`[^`]+`|https?://)"
)


def detect_ungrounded_first_person(text: str, *, evidence_basis: str) -> List[str]:
    """Flag fabricated first-person experience phrasing when not backed by execution."""
    if evidence_basis == "first_hand_execution":
        return []
    hits: List[str] = []
    for pat in FIRST_PERSON_EXPERIENCE_PATTERNS:
        for m in pat.finditer(str(text or "")):
            phrase = m.group(0)
            if phrase not in hits:
                hits.append(phrase)
    return hits


def evaluate_value_brief(brief: Dict[str, Any], *, draft_text: str = "") -> Dict[str, Any]:
    """Audit whether a research/content brief carries real information gain."""
    if not isinstance(brief, dict):
        raise ValueError("value brief must be a JSON object")

    basis = str(brief.get("evidence_basis") or "").strip()
    findings = brief.get("real_findings") or []
    if not isinstance(findings, list):
        findings = []

    issues: List[Dict[str, str]] = []
    required_fields = (
        ("viewer_problem", "未明确观众为什么需要看这条内容 / 解决什么具体问题"),
        ("info_delta", "未说明相对已有同类文章或 README 的信息增量"),
        ("creator_judgment", "缺少明确的创作者观点或工程判断"),
        ("applicability_and_limits", "未说明适用条件、限制或失败边界"),
        ("actionable_takeaway", "未说明观众看完能带走什么具体动作或判断"),
    )
    for field, msg in required_fields:
        val = str(brief.get(field) or "").strip()
        if len(val) < 12:
            issues.append({"code": f"MISSING_{field.upper()}", "severity": "BLOCK", "detail": msg})

    if basis not in EVIDENCE_BASES:
        issues.append({
            "code": "INVALID_EVIDENCE_BASIS",
            "severity": "BLOCK",
            "detail": f"evidence_basis must be one of {', '.join(EVIDENCE_BASES)}",
        })

    concrete_findings = 0
    sourced_findings = 0
    for idx, item in enumerate(findings, start=1):
        if isinstance(item, dict):
            obs = str(item.get("observation") or "").strip()
            src = str(item.get("source_ref") or "").strip()
            if CONCRETE_EVIDENCE_RE.search(obs):
                concrete_findings += 1
            if src:
                sourced_findings += 1
        elif isinstance(item, str) and CONCRETE_EVIDENCE_RE.search(item):
            concrete_findings += 1

    if len(findings) < 2:
        issues.append({
            "code": "THIN_FINDINGS",
            "severity": "BLOCK",
            "detail": "至少需要 2 条基于真实源码、实测、数据或错误日志的具体发现（禁止仅改写 README 摘要）",
        })
    elif concrete_findings < 2:
        issues.append({
            "code": "ABSTRACT_FINDINGS",
            "severity": "WARN",
            "detail": f"仅 {concrete_findings}/{len(findings)} 条发现包含具象锚点（数字/路径/命令/报错），信息增量偏弱",
        })

    if findings and sourced_findings < len(findings):
        issues.append({
            "code": "UNSOURCED_FINDING",
            "severity": "WARN",
            "detail": f"{len(findings) - sourced_findings} 条发现未附带 source_ref 出处",
        })

    combined_text = "\n".join([
        str(brief.get("creator_judgment") or ""),
        str(brief.get("info_delta") or ""),
        str(draft_text or ""),
    ])
    fp_hits = detect_ungrounded_first_person(combined_text, evidence_basis=basis or "verified_official_docs")
    if fp_hits:
        issues.append({
            "code": "UNGROUNDED_FIRST_PERSON",
            "severity": "BLOCK",
            "detail": f"evidence_basis={basis!r}（非实际运行实测），禁止伪造第一人称经历：{', '.join(fp_hits)}",
        })

    hard_blocks = [i for i in issues if i["severity"] == "BLOCK"]
    return {
        "schema": SCHEMA,
        "ok": not hard_blocks,
        "evidence_basis": basis,
        "finding_count": len(findings),
        "concrete_finding_count": concrete_findings,
        "sourced_finding_count": sourced_findings,
        "ungrounded_first_person": fp_hits,
        "issues": issues,
        "production_ready": False,
        "publish_authorized": False,
    }
