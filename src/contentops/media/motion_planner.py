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
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


class MotionPlanError(ValueError):
    """The account or narration cannot be rendered without guessing visuals."""


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
    if re.search(r"源码|代码|code|仓库|github|实现|函数|配置", folded):
        return "code"
    if re.search(r"数据|指标|数值|增长|性能|延迟|吞吐|metric", folded):
        return "metric"
    return "unsupported"


def _short_label(text: str, limit: int = 12) -> str:
    value = " ".join(str(text or "").split()).strip("。！？!?；;，,")
    return value[:limit] if value else "机制步骤"


def _cues(text: str, kind: str, source_image: str | None,
          grammar: str) -> List[Dict[str, Any]]:
    """Build two or three semantic beats from the script line, not a title card."""
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
    if not isinstance(profile, dict) or profile.get("backend") != "huashu-art-motion":
        raise MotionPlanError("AUTO_MOTION_PROFILE_MISSING: account DNA has no Huashu profile")
    palette = profile.get("palette") or {}
    required_colors = ("bg", "surface", "ink", "sub", "accent", "accent2")
    if any(not re.fullmatch(r"#[0-9a-fA-F]{6}", str(palette.get(key) or ""))
           for key in required_colors):
        raise MotionPlanError("AUTO_MOTION_PALETTE_INVALID: expected all six hex colors")
    allowed = set(profile.get("grammars") or [])
    if "y3_whiteboard" not in allowed:
        raise MotionPlanError("AUTO_MOTION_GRAMMAR_UNAVAILABLE: y3_whiteboard is not allowed")

    lines = script.get("lines") or []
    timings = narration.get("lines") or []
    if not lines or len(lines) != len(timings):
        raise MotionPlanError("AUTO_MOTION_TIMELINE_MISMATCH: narration timing must cover each line")
    planner_sha256 = _file_sha(Path(__file__).resolve())
    identity = {"account": account_id, "profile": profile, "script": script,
                "narration": narration, "assets": source_assets,
                "planner_sha256": planner_sha256}
    fingerprint = _sha(identity)
    auto_dir = project / "motion" / "auto"
    specs_dir = auto_dir / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    shots = []
    for line, timing in zip(lines, timings):
        placement = str(line.get("id") or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,50}", placement):
            raise MotionPlanError(f"AUTO_MOTION_PLACEMENT_INVALID: {placement!r}")
        source_asset_id = str(line.get("asset_id") or "")
        text = str(line.get("narration") or line.get("caption") or "").strip()
        duration = float(timing.get("duration") or 0)
        source = source_assets.get(source_asset_id)
        if not placement or not source_asset_id or not text:
            raise MotionPlanError("AUTO_MOTION_LINE_INVALID: each line needs id, source asset and narration")
        if not 0.0 < duration <= 8.0:
            raise MotionPlanError(
                f"AUTO_MOTION_DURATION_UNSUPPORTED: {placement} is {duration:.2f}s; "
                "a narrated shot must be positive and no longer than 8 seconds")
        render_duration = max(2.0, duration)
        hold_padding = round(render_duration - duration, 3)
        kind = _topic_kind(text)
        if kind == "unsupported" and str((source or {}).get("type") or "").upper() == "CODE_SNAPSHOT":
            kind = "code"
        if kind == "unsupported":
            raise MotionPlanError(f"AUTO_MOTION_UNSUPPORTED: no semantic visual grammar matched {placement}")

        source_image = None
        source_image_sha256 = None
        if account_id == "x-superplay-1024":
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

        # Keep the 1024 account evidence-led with its screenshot plus annotated
        # whiteboard flow. Future Intelligence uses progressive derivations for
        # retrieval, agent-flow and protocol-boundary explanations when allowed.
        grammar = ("t1_3b1b" if account_id == "x-superplay-future-intelligence"
                   and kind in {"retrieval", "agent", "protocol"}
                   and "t1_3b1b" in allowed
                   else "y3_whiteboard")
        cues = _cues(text, kind, source_image, grammar)
        # Cue timestamps must remain inside this exact measured narration clip.
        latest_cue = max(float(cue["at"]) for cue in cues)
        scale = min(1.0, max(0.0, render_duration - 0.1) / latest_cue) if latest_cue else 1.0
        cues = [{**cue, "at": round(float(cue["at"]) * scale, 3)} for cue in cues]
        spec = {"grammar": grammar, "duration": render_duration, "fps": 30,
                "width": 1080, "height": 1920, "theme": palette, "cues": cues}
        if hold_padding:
            spec["contentops_timing"] = {
                "narration_duration_s": duration,
                "visual_hold_padding_s": hold_padding,
            }
        if source_image_sha256:
            # The upstream renderer ignores this adapter namespace. Including
            # the file hash in the spec makes the existing per-shot cache miss
            # when the real screenshot changes at the same path.
            spec["contentops_source"] = {"asset_id": source_asset_id,
                                         "sha256": source_image_sha256}
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
            "source_asset_id": source_asset_id,
            "content_point": text,
            "semantic_class": kind,
            "motion_syntax": grammar,
            "backend": "huashu-art-motion",
            "spec": spec_path.relative_to(project).as_posix(),
            "duration_s": duration,
            "source_refs": [str(ref) for ref in line.get("source_refs", [])],
            "visual_match": "PENDING_FRAME_REVIEW",
        })
    plan = {"schema": "contentops.motion-shot-plan/v1", "account_id": account_id,
            "profile_version": account_dna.get("version"), "input_sha256": fingerprint,
            "compiler": "contentops.motion_planner/v3",
            "compiler_sha256": planner_sha256, "shots": shots}
    plan_path = auto_dir / f"shot-plan-{fingerprint[:12]}.json"
    if not plan_path.exists():
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return {"path": plan_path, "plan": plan, "input_sha256": fingerprint}
