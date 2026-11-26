"""Assign a motion backend to every shot, so a film can use several skills.

Why this exists
---------------
A VIDEO account names one motion profile in its DNA, which made every shot use
the same skill. The repository actually ships five render backends

* huashu-art-motion, huashu-motion  (local, non-paid, M5's own adapter path)
* remotion, motion-canvas, manim    (clip renderers via animation_render.py)

plus a compatibility matrix mapping shot kinds to the backends that can draw
them. ``m5_production.stage_motion`` already honours a per-shot ``backend`` and
labels a mixed plan ``hybrid``. What was missing is a planner that reads the
shot semantics and picks a backend per shot from what is actually ready.

Rules, in priority order
------------------------
1. A backend is only chosen when its readiness check says READY. An unready
   backend is never silently substituted -- that is FAIL is FAIL (AGENTS.md 7).
2. Huashu is checked through its own adapter preflight, not animation_render's
   clip preflight; the two paths have different runtime contracts.
3. An explicit per-shot backend is never replaced. A declared fallback is used
   only when the caller listed it and it is ready.
4. Account gates are respected: future-intelligence refuses recording input;
   x-superplay-1024 needs a real recording for production.
5. The plan reports which backends it used. A single backend is not called
   hybrid; several are. Nothing here renders, approves copy or authorizes
   publication.

Run: ``python scripts/plan_motion.py <project> [--json]``
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from contentops.media.animation_backend import (
    ACCOUNT_1024,
    ACCOUNT_FUTURE,
    CLIP_BACKENDS,
    HUASHU_BACKENDS,
    KNOWN_BACKENDS,
    RECORDING_KINDS,
    SHOT_COMPATIBILITY,
    TEMPLATES,
    VIDEO_ACCOUNTS,
    AnimationError,
)

SCHEMA = "contentops.animation-orchestration/v1"
HUASHU_PATH = "M5_HUASHU_ADAPTER"
CLIP_PATH = "ANIMATION_RENDER"


class OrchestrationBlocked(ValueError):
    """A shot cannot be assigned a ready backend without degrading."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def backend_path(backend: str) -> str:
    """Which runtime path actually renders this backend."""
    if backend in HUASHU_BACKENDS:
        return HUASHU_PATH
    if backend in CLIP_BACKENDS:
        return CLIP_PATH
    raise OrchestrationBlocked("UNKNOWN_BACKEND", f"{backend!r}")


def shot_kind(line: Mapping[str, Any]) -> str:
    """Derive a shot kind from the line's declared template/visual role.

    A line may declare ``shot_kind`` or ``animation_type`` directly. Otherwise
    its ``visual_role`` maps to the compatibility vocabulary. Unknown kinds are
    reported, never guessed into a backend that cannot draw them.
    """
    for key in ("shot_kind", "kind"):
        value = str(line.get(key) or "").strip().lower()
        if value in SHOT_COMPATIBILITY:
            return value
    animation_type = str(line.get("animation_type") or "").strip().lower()
    if animation_type in SHOT_COMPATIBILITY:
        return animation_type
    role = str(line.get("visual_role") or "").strip().lower()
    if role in SHOT_COMPATIBILITY:
        return role
    # A script built from a coarser topic derivative has no per-shot grammar;
    # classify from the segment label and the spoken text instead. This is a
    # planning hint only -- it never rewrites the approved narration.
    segment = str(line.get("source_segment_id") or "").upper()
    for token, kind in (
        ("HOOK", "title_card"), ("INTRO", "title_card"), ("CTA", "title_card"),
        ("ROADMAP", "architecture"), ("ARCH", "architecture"),
        ("FLOW", "agent_flow"), ("EVAL", "comparison"),
        ("ACCEPT", "comparison"), ("COMPARE", "comparison"),
        ("MATH", "math"), ("FORMULA", "math"),
        ("CODE", "code_card"),
    ):
        if token in segment:
            return kind
    text = str(line.get("narration") or line.get("caption") or "").lower()
    if any(word in text for word in ("公式", "推导", "math", "equation")):
        return "math"
    if any(word in text for word in ("清单", "几件事", "第一", "第二", "对比", "而不是")):
        return "comparison"
    if any(word in text for word in ("路线", "流程", "架构", "阶段", "步骤")):
        return "architecture"
    return "unclassified"


def _account_guard(account_id: str, *, purpose: str,
                   has_real_recording: bool, input_kind: str) -> None:
    if account_id not in VIDEO_ACCOUNTS:
        raise OrchestrationBlocked("UNKNOWN_ACCOUNT", f"{account_id!r} is not a video account")
    if account_id == ACCOUNT_FUTURE and input_kind in RECORDING_KINDS:
        raise OrchestrationBlocked(
            "RECORDING_FORBIDDEN",
            "future-intelligence refuses a desktop or manual recording")
    if (account_id == ACCOUNT_1024 and purpose == "production"
            and not has_real_recording):
        raise OrchestrationBlocked(
            "MISSING_REAL_RECORDING",
            "x-superplay-1024 production needs a verified real recording")


def plan(
    lines: Sequence[Mapping[str, Any]],
    *,
    account_id: str,
    readiness: Mapping[str, Any],
    purpose: str = "production",
    has_real_recording: bool = False,
    default_backend: Optional[str] = None,
) -> Dict[str, Any]:
    """Return one backend assignment per line, or fail closed.

    ``readiness`` maps backend name to a state string: ``READY`` or anything
    else. The caller owns how readiness is probed; this function only refuses
    to pick an unready backend. ``default_backend`` is a preference, not a
    forced single backend: a shot incompatible with it uses the first ready
    compatible backend instead, and the plan records why.
    """
    _account_guard(account_id, purpose=purpose,
                   has_real_recording=has_real_recording,
                   input_kind=str(lines[0].get("input_kind") or "") if lines else "")
    if not lines:
        raise OrchestrationBlocked("NO_SHOTS", "no shots to plan")

    if default_backend is not None:
        if default_backend not in KNOWN_BACKENDS:
            raise OrchestrationBlocked("UNKNOWN_BACKEND", f"{default_backend!r}")
        if str(readiness.get(default_backend) or "").upper() != "READY":
            raise OrchestrationBlocked(
                "DEFAULT_BACKEND_UNREADY",
                f"default backend {default_backend!r} is not READY")

    assignments: List[Dict[str, Any]] = []
    for line in lines:
        placement = str(line.get("id") or line.get("placement_id") or "").strip()
        if not placement:
            raise OrchestrationBlocked("SHOT_ID_REQUIRED", "every shot needs an id")
        kind = shot_kind(line)
        explicit = str(line.get("motion_backend") or line.get("backend") or "").strip()
        compatible = list(SHOT_COMPATIBILITY.get(kind, ()))
        if not compatible:
            compatible = [b for b in KNOWN_BACKENDS
                          if str(readiness.get(b) or "").upper() == "READY"]
            if not compatible:
                raise OrchestrationBlocked(
                    "NO_READY_BACKEND",
                    f"{placement}: shot kind {kind!r} has no declared compatible backend "
                    "and no ready fallback")
        candidates: List[str] = []
        if explicit:
            if explicit not in KNOWN_BACKENDS:
                raise OrchestrationBlocked("UNKNOWN_BACKEND", f"{placement}: {explicit!r}")
            candidates.append(explicit)
        else:
            if default_backend and default_backend in compatible:
                candidates.append(default_backend)
            candidates.extend(b for b in compatible if b not in candidates)
        chosen = next((b for b in candidates
                       if str(readiness.get(b) or "").upper() == "READY"), None)
        if chosen is None:
            raise OrchestrationBlocked(
                "NO_READY_BACKEND",
                f"{placement}: compatible backends {compatible} are not READY")
        template = next((name for name, row in TEMPLATES.items()
                         if row.get("backend") == chosen and name == kind), None)
        assignments.append({
            "placement_id": placement,
            "shot_kind": kind,
            "backend": chosen,
            "backend_path": backend_path(chosen),
            "template": template,
            "explicit": bool(explicit),
        })

    used = sorted({row["backend"] for row in assignments})
    return {
        "schema": SCHEMA,
        "account_id": account_id,
        "purpose": purpose,
        "hybrid": len(used) > 1,
        "backends": used,
        "assignments": assignments,
        "production_ready": False,
        "publish_authorized": False,
    }
