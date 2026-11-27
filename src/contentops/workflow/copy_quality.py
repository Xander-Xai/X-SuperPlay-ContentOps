"""Copy quality signals for a finished script: structure, not taste.

The problem
-----------
A technically correct script can still be a bad piece of content. The common
failure modes are structural and machine-visible:

* the opening is a programme announcement ("这一期讲…") instead of a hook, so a
  viewer scrolls in the first three seconds;
* the ending states a conclusion but never asks the viewer to do anything, so a
  finished film produces no follow;
* the whole narration speaks in the third person about a subject, never to the
  person watching, which reads as a document read aloud;
* it is all abstraction — "三类镜头", "六种模板" — with no number, named thing or
  concrete case to hold onto;
* it is padded with filler ("众所周知", "需要注意的是") that carries no information.

None of that is caught today: ``copy_review`` records a human decision, and the
MD/QC gates check facts, lengths and geometry, not whether the writing works.

What this module is
-------------------
A read-only measurement. Given the narration lines of a script, in order, it
reports where the opening, the ending and the body stand, with the exact lines
that triggered each signal and a concrete, non-generic suggestion. It never
rewrites the copy, never edits a file, never touches the claim ledger, and never
gates production — a low score is advice to the human editor, not a verdict.

What it is not
--------------
It cannot judge whether the idea is interesting, whether the facts are right, or
whether the audience will watch. It measures structure and wording only, and it
says so in every report. A high score is not a promise of reach; a low score is
not a block.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

SCHEMA = "contentops.copy-quality/v1"

#: Openings that announce the programme instead of hooking the viewer.
TEMPLATE_OPENINGS = (
    "这一期讲", "本期", "这期视频", "今天我们来", "大家好", "欢迎来到",
    "这期节目", "接下来我们", "在今天的视频里",
)

#: Markers of an opening that earns the next few seconds.
HOOK_MARKERS = (
    "别", "其实", "真相", "错在", "误区", "反常识", "为什么", "怎么",
    "是不是", "你有没有", "你以为", "大部分人", "很多人", "90%", "80%",
    "？", "?",
)

#: Wording that asks the viewer to act.
CTA_MARKERS = (
    "关注", "点赞", "收藏", "评论", "转发", "分享", "下期", "下一条",
    "下集", "系列", "订阅", "追更", "留言", "告诉我",
)

#: A closing that only points at sources is compliance, not a call to action.
COMPLIANCE_MARKERS = ("来源", "核对", "版权", "文末", "参考文献", "出处")

#: An article *can* end on a concrete action ("留下一件能检查的东西") rather than
#: "关注/下一条". A video cannot: without an explicit ask it produces no follow.
ARTICLE_CTA_MARKERS = (
    "留下", "试试", "去做", "行动", "第一步", "不妨", "可以试", "建议你",
    "检查", "动手", "打开", "跑一遍",
)

#: Filler that adds words but no information.
FILLER_PHRASES = (
    "众所周知", "需要注意的是", "总的来说", "综上所述", "不得不说的是",
    "毫无疑问", "显而易见", "换句话说", "简单来说", "事实上", "大家都知道",
    "让我们来看看", "可以看到", "值得一提的是",
)

#: AI-slop throat-clearing, hollow elevation, and translationese (Humanizer-zh / zh-writing-humanizer).
AI_SLOP_PHRASES = (
    "在人工智能飞速发展的今天", "随着AI技术的飞速发展", "随着技术的不断进步", "在当今快节奏的时代",
    "不可否认的是", "正如硬币都有两面", "这不仅是一次技术创新",
    "为行业带来无限可能", "打造全新的智能生态", "开启全新篇章",
    "值得我们深入思考", "从而实现真正的价值闭环", "深度赋能", "全面赋能",
    "重塑行业格局", "让我们拭目以待", "未来可期",
    "在很大程度上", "发挥了重要作用", "总而言之", "毋庸置疑",
    "质的飞跃", "降本增效", "行云流水", "稳如磐石", "新纪元", "极具潜力", "深刻改变", "独特魅力",
)

MECHANICAL_SYMMETRY_RE = re.compile(r"(?:不仅[^。！？\n]{2,20}更|不是[^。！？\n]{2,20}而是|一方面[^。！？\n]{2,25}另一方面)")

#: A concrete line names a number, a path, a named tool, an English term or a URL.
CONCRETE_PATTERNS = (
    re.compile(r"\d"),                       # any digit
    re.compile(r"[A-Za-z][A-Za-z0-9_.\-]{2,}"),  # latin token / path / term
    re.compile(r"https?://"),
    re.compile(r"[A-Z][a-z]+[A-Z]"),         # CamelCase product name
)

_SENTENCE_SPLIT = re.compile(r"[。！？!?；;\n]+")
_TRAILING = "，。！？、；：,.!?;: "


def _norm(text: str) -> str:
    return str(text or "").strip().strip(_TRAILING)


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(str(text or "")) if s.strip()]


def _is_template_opening(text: str) -> bool:
    head = _norm(text)
    return any(head.startswith(marker) or marker in head[:12] for marker in TEMPLATE_OPENINGS)


def _has_hook(text: str) -> bool:
    return any(marker in text for marker in HOOK_MARKERS)


def _has_cta(text: str) -> bool:
    return any(marker in text for marker in CTA_MARKERS)


def _is_compliance_only(text: str) -> bool:
    return any(marker in text for marker in COMPLIANCE_MARKERS) and not _has_cta(text)


def _is_concrete(text: str) -> bool:
    return any(pattern.search(text) for pattern in CONCRETE_PATTERNS)


def _norm_lines(lines: Iterable[Any]) -> List[str]:
    """Accept either plain strings or script line dicts with a narration field."""
    out: List[str] = []
    for line in lines:
        if isinstance(line, str):
            out.append(line)
            continue
        if isinstance(line, dict):
            text = line.get("narration") or line.get("text") or line.get("caption") or ""
            out.append(str(text))
            continue
        raise TypeError("copy lines must be strings or dicts with narration/text/caption")
    return [t for t in out if _norm(t)]


FORMATS = ("video", "article", "text")


def diagnose(lines: Sequence[Any], format: str = "video") -> Dict[str, Any]:
    """Measure a narration script and return structure signals plus advice.

    ``lines`` is the spoken lines in playback order. The first non-empty line is
    the opening and the last is the ending; the body is everything between (or
    everything, for very short scripts).

    ``format`` tunes the ending check: a video needs an explicit ask
    ("关注/下一条"), while a long article may close on a concrete action
    ("留下一件能检查的东西") and still count as a call to action.
    """
    if format not in FORMATS:
        raise ValueError(f"unknown format {format!r}")
    texts = _norm_lines(lines)
    if not texts:
        raise ValueError("no narration lines to diagnose")
    if len(texts) == 1:
        texts = [texts[0], texts[0]]  # opening == ending for a one-liner

    opening, ending = texts[0], texts[-1]
    body = texts[1:-1] if len(texts) > 2 else texts[:]

    # --- opening -----------------------------------------------------------
    template = _is_template_opening(opening)
    hooked = _has_hook(opening)
    if template and not hooked:
        opening_status, opening_note = "TEMPLATE", "开头是节目介绍句，不是钩子；观众前三秒会划走。"
    elif hooked:
        opening_status, opening_note = "HOOKED", "开头含钩子要素（痛点/疑问/反常识/数字）。"
    else:
        opening_status, opening_note = "NEUTRAL", "开头是中性陈述，缺少让观众停下的理由。"
    if not _has_person(opening):
        opening_note += " 开头没有出现“你”。"

    # --- ending ------------------------------------------------------------
    has_cta = _has_cta(ending)
    if format == "article":
        has_cta = has_cta or any(marker in ending for marker in ARTICLE_CTA_MARKERS)
    if has_cta:
        ending_status, ending_note = "CTA", "结尾有明确的行动号召。"
    elif _is_compliance_only(ending):
        ending_status, ending_note = "WEAK_CTA", "结尾只是合规说明（来源/核对），没有引导关注或系列。"
    else:
        ending_status, ending_note = "NO_CTA", "结尾没有行动号召。"

    # --- body --------------------------------------------------------------
    body_sentences = [s for text in body for s in _sentences(text)] or _sentences("。".join(texts))
    person_hits = sum(1 for s in body_sentences if _has_person(s))
    concrete_hits = sum(1 for s in body_sentences if _is_concrete(s))
    filler_hits = [ph for ph in FILLER_PHRASES if ph in " ".join(texts)]
    filler_lines = [i + 1 for i, t in enumerate(texts) if any(ph in t for ph in FILLER_PHRASES)]
    total = max(1, len(body_sentences))
    person_ratio = round(person_hits / total, 3)
    concrete_ratio = round(concrete_hits / total, 3)

    # --- score (structure completeness only) -------------------------------
    score = 0
    score += 30 if opening_status == "HOOKED" else 10 if opening_status == "NEUTRAL" else 0
    score += 25 if ending_status == "CTA" else 5 if ending_status == "WEAK_CTA" else 0
    score += round(min(person_ratio, 0.5) / 0.5 * 20)      # up to 20
    score += round(min(concrete_ratio, 0.6) / 0.6 * 25)    # up to 25
    score -= min(len(filler_hits) * 5, 20)
    score = max(0, min(100, score))

    suggestions: List[str] = []
    if opening_status == "TEMPLATE":
        suggestions.append("把开头从“这一期讲…”改成具体痛点或反常识：例如“你花了三天做的片子，为什么 30 秒就没人看？”")
    elif opening_status == "NEUTRAL":
        suggestions.append("在开头加一个具体钩子：一个数字、一个常见误区，或一句直接对“你”说的话。")
    if ending_status != "CTA":
        suggestions.append("结尾加一句行动号召：关注、收藏，或指向同系列的下一条具体主题。")
    if person_ratio < 0.1:
        suggestions.append("正文几乎没有“你”：把至少一两句改成直接对观众说话，减少“文档朗读感”。")
    if concrete_ratio < 0.3:
        suggestions.append("正文偏抽象：每 2–3 句至少补一个数字、命名工具或具体案例，让观点有落点。")
    if filler_hits:
        suggestions.append("删除空洞套话：" + "、".join(sorted(set(filler_hits))) + "。")

    joined_all = "\n".join(texts)
    compact_all = re.sub(r"\s+", "", joined_all)
    ai_slop_hits = sorted({ph for ph in AI_SLOP_PHRASES if ph in compact_all})
    symmetry_count = len(MECHANICAL_SYMMETRY_RE.findall(joined_all))
    long_spoken_lines = [
        i + 1 for i, t in enumerate(texts)
        if format == "video" and len(_norm(t)) > 48
    ]
    if ai_slop_hits:
        suggestions.append("删去 AI 套话与空洞拔高：" + "、".join(ai_slop_hits) + "，改成具体对象、数据或边界。")
    if symmetry_count >= 3:
        suggestions.append(f"检测到 {symmetry_count} 处机械对称句式（不仅…更…/不是…而是…），建议打破重复结构。")
    if long_spoken_lines:
        suggestions.append(f"视频口播第 {long_spoken_lines[:4]} 行超过 48 字，朗读容易一口气喘不过来，建议拆短留气口。")

    return {
        "schema": SCHEMA,
        "line_count": len(texts),
        "score": score,
        "opening": {"status": opening_status, "text": opening, "note": opening_note},
        "ending": {"status": ending_status, "text": ending, "note": ending_note},
        "body": {
            "sentence_count": total,
            "person_ratio": person_ratio,
            "concrete_ratio": concrete_ratio,
            "filler_hits": sorted(set(filler_hits)),
            "filler_lines": filler_lines,
        },
        "editorial_audit": {
            "ai_slop_hits": ai_slop_hits,
            "mechanical_symmetry_count": symmetry_count,
            "long_spoken_lines": long_spoken_lines,
            "oral_rhythm_ok": not long_spoken_lines,
        },
        "suggestions": suggestions,
        "format": format,
        "disclaimer": (
            f"结构完整性信号（{format} 口径），不是内容价值或播放量预测；不自动改写文案，"
            "不阻塞生产，人工编辑拥有最终判断。"
        ),
    }


def _has_person(text: str) -> bool:
    return "你" in text or "您" in text


__all__ = ["SCHEMA", "diagnose", "TEMPLATE_OPENINGS", "HOOK_MARKERS", "CTA_MARKERS"]
