"""Capture plan: what the operator must record for each beat, and why.

The 1024 account is built mostly from real screen evidence, but "record the
screen" is not an instruction -- it is the absence of one. A beat that shows a
command needs a terminal surface, a beat that shows a result needs a browser
surface, and a beat that explains a mechanism has nothing to record at all.
When that decision is left to the person holding the recorder, the footage
arrives at the wrong aspect, with the cursor parked over the evidence, or as a
still frame of a screen that was never actually operated.

This module turns each beat into an explicit capture contract: surface, what
must be visible, how the 9:16 crop is taken, whether the cursor is shown, and
whether anything personal has to be redacted. The plan is advisory in tone but
mechanical in shape -- it never acquires media and never claims a capture
happened.

What is not claimed
-------------------
Passing this check does not prove the footage was recorded, is legible, or
supports the claim. It proves the recording brief exists, names a surface, and
does not contradict the account's recording policy. Whether the take is usable
stays a human decision.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

SCHEMA = "contentops.capture-plan/v1"

RECORDING_POLICIES = ("ALLOWED_CROPPED", "FORBIDDEN")

EVIDENCE_NEEDS = ("direct_observation", "explanation", "none")

#: Surfaces that produce footage. A policy of FORBIDDEN forbids every one.
RECORDING_SURFACES = ("browser", "terminal", "task_screen")

SURFACES = RECORDING_SURFACES + ("whiteboard", "owned_demo", "card")

#: The price of admission for a direct observation: you must be able to say
#: what the viewer will see, not just where they will look.
MIN_MUST_SHOW = 2

MODES: Dict[str, Dict[str, Any]] = {
    "browser_evidence": {
        "surface": "browser",
        "capture": "record a real browser window; keep the URL bar, keep the result",
        "source_aspect": "16:9",
        "crop": "focus crop to 9:16 around the region the sentence names",
        "evidence_level": "direct_observation",
        "cursor": "visible",
        "must_show": ["地址栏或页面标题", "关键操作后的结果", "版本号或 URL"],
    },
    "terminal_evidence": {
        "surface": "terminal",
        "capture": "record a terminal session; the command and its output are both in frame",
        "source_aspect": "16:9",
        "crop": "focus crop to 9:16 on the command block, not the whole desktop",
        "evidence_level": "direct_observation",
        "cursor": "hidden",
        "must_show": ["执行的命令", "输出或报错", "版本号"],
    },
    "task_screen": {
        "surface": "task_screen",
        "capture": "record the task surface in use; input, action and outcome in one take",
        "source_aspect": "16:9",
        "crop": "focus crop to 9:16 on the working region",
        "evidence_level": "direct_observation",
        "cursor": "visible",
        "must_show": ["输入条件", "关键动作", "结果"],
    },
    "whiteboard_excalidraw": {
        "surface": "whiteboard",
        "capture": "draw the mechanism on a whiteboard surface; no screen footage",
        "source_aspect": "9:16",
        "crop": "native portrait, no crop",
        "evidence_level": "explanation",
        "cursor": "hidden",
        "must_show": ["机制名称", "因果箭头", "适用边界"],
    },
    "owned_demo": {
        "surface": "owned_demo",
        "capture": "render the demo surface from the composition, not from a desktop",
        "source_aspect": "9:16",
        "crop": "native portrait, no crop",
        "evidence_level": "explanation",
        "cursor": "hidden",
    },
    "card_only": {
        "surface": "card",
        "capture": "no capture; this beat is a card",
        "source_aspect": "9:16",
        "crop": "native portrait, no crop",
        "evidence_level": "explanation",
        "cursor": "hidden",
    },
}

#: Ordered keyword tables. First match wins, so the order is the precedence.
ROUTE_PATTERNS = (
    ("terminal_evidence",
     ("终端", "命令行", "powershell", "bash", "命令", "报错", "安装", "部署", "pip ", "npm ")),
    ("browser_evidence",
     ("浏览器", "官网", "官方页面", "仓库", "github", "url", "页面", "登录", "dashboard")),
    ("task_screen",
     ("工作台", "任务", "流程", "表格", "文档", "办公", "交付", "客户")),
    ("whiteboard_excalidraw",
     ("架构", "机制", "原理", "推导", "公式", "因果", "链路")),
)

ROUTE_ALIASES = {
    "terminal": "terminal_evidence",
    "browser": "browser_evidence",
    "product-ui": "browser_evidence",
    "task": "task_screen",
    "whiteboard": "whiteboard_excalidraw",
    "excalidraw": "whiteboard_excalidraw",
    "demo": "owned_demo",
    "concept-motion": "owned_demo",
    "card": "card_only",
}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def recommend_mode(beat: Dict[str, Any]) -> Dict[str, Any]:
    """Pick one capture mode for a beat and say why.

    An explicit ``route`` wins. Otherwise the spoken text chooses, and the
    reason names the term that decided it, so an operator can disagree with a
    specific word instead of with a black box.
    """
    explicit = ROUTE_ALIASES.get(_text(beat.get("route")).lower())
    if explicit:
        return {"mode": explicit, "reasons": [f"route:{_text(beat.get('route'))}"]}
    haystack = " ".join(
        _text(beat.get(key)).lower()
        for key in ("spoken_text", "viewer_job", "source_strategy", "must_show")
    )
    for mode, terms in ROUTE_PATTERNS:
        hit = next((term for term in terms if term in haystack), "")
        if hit:
            return {"mode": mode, "reasons": [f"text:{hit}"]}
    need = _text(beat.get("evidence_need"))
    if need == "direct_observation":
        return {"mode": "browser_evidence", "reasons": ["evidence-need:direct_observation"]}
    return {"mode": "card_only", "reasons": ["no-capture-term"]}


def _default_must_show(mode: str, beat: Dict[str, Any]) -> List[str]:
    declared = beat.get("must_show")
    if isinstance(declared, list):
        return [_text(item) for item in declared if _text(item)]
    return list(MODES[mode].get("must_show", ()))


def build_capture(beat: Dict[str, Any], policy: str) -> Dict[str, Any]:
    """Fill one beat's capture contract from its own text and the policy."""
    recommendation = recommend_mode(beat)
    mode = recommendation["mode"]
    if policy == "FORBIDDEN" and MODES[mode]["surface"] in RECORDING_SURFACES:
        mode = "card_only"
        recommendation["reasons"].append("recording-policy:FORBIDDEN")
    contract = MODES[mode]
    must_show = _default_must_show(mode, beat)
    return {
        "mode": mode,
        "surface": contract["surface"],
        "capture": contract["capture"],
        "source_aspect": contract["source_aspect"],
        "crop": contract["crop"],
        "evidence_level": contract["evidence_level"],
        "cursor": contract["cursor"],
        "must_show": must_show,
        "redaction": "required" if beat.get("redaction_required") is True else "none",
        "reasons": recommendation["reasons"],
    }


def plan(beats: Iterable[Dict[str, Any]], *, account: str,
         recording_policy: str) -> Dict[str, Any]:
    """Turn a beat list into a capture plan document."""
    planned = []
    for beat in beats:
        item = dict(beat)
        item["capture"] = build_capture(beat, recording_policy)
        planned.append(item)
    return {
        "schema": SCHEMA,
        "account": account,
        "recording_policy": recording_policy,
        "beats": planned,
    }


def _validate_beat(index: int, beat: Any, policy: str) -> List[str]:
    errors: List[str] = []
    label = f"beats[{index}]"
    if not isinstance(beat, dict):
        return [f"{label} must be an object"]
    beat_id = _text(beat.get("beat_id"))
    if not beat_id:
        errors.append(f"{label}.beat_id must be a non-empty string")
        label = f"beats[{index}]"
    else:
        label = f"beats[{index}] ({beat_id})"
    need = _text(beat.get("evidence_need"))
    if need not in EVIDENCE_NEEDS:
        errors.append(f"{label}.evidence_need must be one of {EVIDENCE_NEEDS}")
    start, end = _number(beat.get("start_ms")), _number(beat.get("end_ms"))
    if start is None or end is None:
        errors.append(f"{label} must declare integer start_ms and end_ms")
    elif start < 0 or end <= start:
        errors.append(f"{label} window is not a positive range: {start}-{end}ms")
    if not isinstance(beat.get("redaction_required"), bool):
        errors.append(f"{label}.redaction_required must be an explicit boolean")
    must_show = beat.get("must_show")
    if must_show is not None:
        if not isinstance(must_show, list) or not all(isinstance(i, str) and i.strip()
                                                      for i in must_show):
            errors.append(f"{label}.must_show must be a list of non-empty strings")
        elif len({item.strip() for item in must_show}) != len(must_show):
            errors.append(f"{label}.must_show repeats an entry")

    capture = beat.get("capture")
    if not isinstance(capture, dict):
        errors.append(f"{label}.capture is missing; run the planner or write one")
        return errors
    surface = _text(capture.get("surface"))
    if surface not in SURFACES:
        errors.append(f"{label}.capture.surface must be one of {SURFACES}")
        return errors
    if policy == "FORBIDDEN" and surface in RECORDING_SURFACES:
        errors.append(f"{label} captures {surface} on an account that forbids recording")
    if need == "direct_observation":
        if surface not in RECORDING_SURFACES:
            errors.append(f"{label} needs a direct observation but its surface is "
                          f"{surface!r}; a card cannot show an operation")
        shown = capture.get("must_show")
        if not isinstance(shown, list) or len([i for i in shown if isinstance(i, str) and i.strip()]) < MIN_MUST_SHOW:
            errors.append(f"{label} must name at least {MIN_MUST_SHOW} things the "
                          f"viewer will see; a capture with nothing named is a screenshot of a screen")
    if beat.get("redaction_required") is True and capture.get("redaction") != "required":
        errors.append(f"{label} declares redaction but its capture does not require it")
    if surface in ("browser", "terminal") and capture.get("redaction") not in ("required", "none"):
        errors.append(f"{label}.capture.redaction must be 'required' or 'none'")
    return errors


def validate_capture_plan(document: Any) -> List[str]:
    """Return hard failures for a capture plan. Empty means it can brief a capture."""
    if not isinstance(document, dict):
        return ["capture plan must be a JSON object"]
    errors: List[str] = []
    if document.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}")
    if not _text(document.get("account")):
        errors.append("account must be a non-empty string")
    policy = _text(document.get("recording_policy"))
    if policy not in RECORDING_POLICIES:
        errors.append(f"recording_policy must be one of {RECORDING_POLICIES}")

    beats = document.get("beats")
    if not isinstance(beats, list) or not beats:
        errors.append("beats must be a non-empty array")
        return errors

    seen: Dict[str, int] = {}
    previous_end: Optional[int] = None
    for index, beat in enumerate(beats):
        errors.extend(_validate_beat(index, beat, policy))
        if not isinstance(beat, dict):
            continue
        beat_id = _text(beat.get("beat_id"))
        if beat_id:
            if beat_id in seen:
                errors.append(f"duplicate beat_id {beat_id!r}")
            seen[beat_id] = index
        start, end = _number(beat.get("start_ms")), _number(beat.get("end_ms"))
        if start is None or end is None:
            continue
        if previous_end is not None and start < previous_end:
            errors.append(f"beats[{index}] starts at {start}ms, before the previous "
                          f"beat ends at {previous_end}ms")
        previous_end = max(previous_end, end) if previous_end is not None else end
    return errors
