"""Clip-renderer contract. Easel stays the timeline; these backends emit shots.

A clip backend renders one short silent MP4. It does not compose the episode,
does not count as a screen recording, and does not approve publication.
``motion_handoff`` stays MotionClone-only. Do not stamp a Remotion or Manim
file with that runtime to get past its check.

Selection never substitutes an explicit backend. A fallback runs only when the
caller listed it and it is compatible with the shot. A missing runtime is
BLOCKED, not a still image and not a Huashu render in disguise.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

SCHEMA = "contentops.animation-clip-receipt/v1"
PLAN_SCHEMA = "contentops.animation-clip-plan/v1"
CAPABILITY_SCHEMA = "contentops.animation-capability-matrix/v1"

ACCOUNT_1024 = "x-superplay-1024"
ACCOUNT_FUTURE = "x-superplay-future-intelligence"
VIDEO_ACCOUNTS = (ACCOUNT_1024, ACCOUNT_FUTURE)

HUASHU_BACKENDS = ("huashu-art-motion", "huashu-motion")
CLIP_BACKENDS = ("remotion", "motion-canvas", "manim")
KNOWN_BACKENDS = HUASHU_BACKENDS + CLIP_BACKENDS

REMOTION_VERSION = "4.0.543"
REMOTION_SKILL_COMMIT = "7e541aa"
REMOTION_SKILLS = (
    "remotion-best-practices",
    "remotion-captions",
    "remotion-create",
    "remotion-docs",
    "remotion-interactivity",
    "remotion-license",
    "remotion-maps",
    "remotion-markup",
    "remotion-multimedia",
    "remotion-render",
    "remotion-saas",
    "remotion-studio",
    "remotion-upgrade",
)

TEMPLATES = {
    "annotation": {"composition": "AnnotationCard", "backend": "remotion"},
    "comparison": {"composition": "AnnotationCard", "backend": "remotion"},
    "rag_flow": {"composition": "RagFlow", "backend": "remotion"},
    "recording_mark": {"composition": "RecordingMark", "backend": "remotion"},
    "title_card": {"composition": "TitleCard", "backend": "remotion"},
}

SHOT_COMPATIBILITY = {
    "annotation": ("remotion", "huashu-art-motion", "huashu-motion"),
    "comparison": ("remotion", "huashu-art-motion", "huashu-motion"),
    "title_card": ("remotion", "huashu-art-motion"),
    "architecture": ("remotion", "motion-canvas", "huashu-art-motion"),
    "agent_flow": ("remotion", "motion-canvas", "huashu-art-motion"),
    "math": ("manim",),
    "code_card": ("remotion",),
    "recording_mark": ("remotion",),
}

RECORDING_KINDS = {
    "recording", "real_recording", "screen_recording", "screen_capture",
    "manual_recording", "desktop_recording", "terminal_recording",
}

_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/(?!/))")
_HASH = re.compile(r"^[0-9a-f]{64}$")


class AnimationError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _logical(path: str) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text.startswith("project://") or ".." in text.split("/"):
        raise AnimationError("PATH", f"{path!r} must be a project:// path")
    if _ABSOLUTE.match(text[len("project://"):]):
        raise AnimationError("PATH", "a receipt must not carry a host path")
    return text


def normalize_backend(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    aliases = {
        "art-motion": "huashu-art-motion",
        "motion": "huashu-motion",
        "remotion-skills": "remotion",
    }
    return aliases.get(text, text)


def _ready(readiness: Mapping[str, Any], backend: str) -> bool:
    row = readiness.get(backend)
    if isinstance(row, bool):
        return row
    if isinstance(row, Mapping):
        return row.get("ready") is True
    return False


def _blocked(code: str, detail: str, **extra: Any) -> Dict[str, Any]:
    payload = {
        "state": "BLOCKED",
        "code": code,
        "detail": detail,
        "backend": extra.pop("backend", None),
        "substituted": False,
        "generated": True,
        "evidence_capable": False,
        "production_ready": False,
        "publish_authorized": False,
        "execution_authorized": False,
    }
    payload.update(extra)
    return payload


def select_backend(
    *,
    account_id: str,
    shot_type: str,
    explicit: Optional[str] = None,
    readiness: Optional[Mapping[str, Any]] = None,
    declared_fallbacks: Sequence[str] = (),
    purpose: str = "production",
    input_kind: Optional[str] = None,
    has_real_recording: bool = False,
) -> Dict[str, Any]:
    """Choose a clip backend. An explicit name is never replaced silently."""
    account = str(account_id or "").strip()
    if not account:
        return _blocked("ACCOUNT_REQUIRED", "an animation clip needs an account id")
    if account not in VIDEO_ACCOUNTS:
        return _blocked("UNKNOWN_ACCOUNT", f"{account!r} is not a video account")

    kind = str(input_kind or "").strip().lower()
    if account == ACCOUNT_FUTURE and kind in RECORDING_KINDS:
        return _blocked(
            "RECORDING_FORBIDDEN",
            "future-intelligence refuses a desktop or manual recording",
            account_id=account,
        )
    if account == ACCOUNT_1024 and purpose == "production" and not has_real_recording:
        return _blocked(
            "MISSING_REAL_RECORDING",
            "1024 production needs a cropped recording; a generated clip cannot satisfy it",
            account_id=account,
        )

    shot = str(shot_type or "").strip().lower()
    compatible = SHOT_COMPATIBILITY.get(shot)
    if compatible is None:
        return _blocked("UNKNOWN_SHOT", f"shot type {shot!r} has no backend map", account_id=account)

    ready_map = readiness or {}
    requested = normalize_backend(explicit)
    if requested is not None:
        if requested not in KNOWN_BACKENDS:
            return _blocked("UNSUPPORTED_BACKEND", f"unsupported motion backend {requested!r}",
                            account_id=account, requested=requested)
        if requested not in compatible:
            return _blocked(
                "INCOMPATIBLE_BACKEND",
                f"{requested} cannot render shot type {shot}",
                account_id=account, requested=requested,
            )
        if _ready(ready_map, requested):
            return _selected(requested, account, shot, explicit=True, purpose=purpose)
        fallback = _declared_fallback(requested, compatible, declared_fallbacks, ready_map)
        if fallback is None:
            return _blocked(
                "RUNTIME_NOT_READY",
                f"{requested} is not ready and no declared compatible fallback is ready",
                account_id=account, requested=requested,
            )
        return _selected(fallback, account, shot, explicit=False, purpose=purpose,
                         requested=requested, fallback_of=requested)

    for candidate in compatible:
        if _ready(ready_map, candidate):
            return _selected(candidate, account, shot, explicit=False, purpose=purpose)
    return _blocked(
        "RUNTIME_NOT_READY",
        f"no ready backend for shot type {shot}",
        account_id=account,
    )


def _declared_fallback(requested: str, compatible: Sequence[str],
                       declared: Sequence[str], readiness: Mapping[str, Any]) -> Optional[str]:
    for raw in declared:
        name = normalize_backend(raw)
        if not name or name == requested:
            continue
        if name in compatible and _ready(readiness, name):
            return name
    return None


def _selected(backend: str, account: str, shot: str, *, explicit: bool,
              purpose: str, requested: Optional[str] = None,
              fallback_of: Optional[str] = None) -> Dict[str, Any]:
    return {
        "state": "SELECTED",
        "code": "SELECTED",
        "backend": backend,
        "requested": requested or backend,
        "account_id": account,
        "shot_type": shot,
        "explicit": explicit,
        "substituted": fallback_of is not None,
        "fallback_of": fallback_of,
        "purpose": purpose,
        "generated": True,
        "evidence_capable": False,
        "counts_as_real_recording": False,
        "production_ready": False,
        "publish_authorized": False,
        "execution_authorized": False,
        "skills_installation": "SKILL_NOT_INSTALLED",
    }


def production_gate(*, account_id: str, has_real_recording: bool,
                    purpose: str = "production") -> Dict[str, Any]:
    """Whether this clip may enter a production episode. Never a publish grant."""
    account = str(account_id or "").strip()
    if account == ACCOUNT_1024 and purpose == "production" and not has_real_recording:
        return _blocked(
            "MISSING_REAL_RECORDING",
            "1024 production is blocked until a cropped recording is registered",
            account_id=account, purpose=purpose,
        )
    if account == ACCOUNT_FUTURE and purpose == "production":
        return {
            "state": "TECHNICAL_ONLY",
            "code": "EXPLANATORY_CLIP",
            "account_id": account,
            "detail": "vector animation may enter technical QC; it is not system output",
            "generated": True,
            "evidence_capable": False,
            "production_ready": False,
            "publish_authorized": False,
        }
    if purpose == "test":
        return {
            "state": "TEST_ONLY",
            "code": "TEST_PURPOSE",
            "account_id": account,
            "detail": "test render is not an accepted case",
            "generated": True,
            "evidence_capable": False,
            "production_ready": False,
            "publish_authorized": False,
        }
    return {
        "state": "TECHNICAL_ONLY",
        "code": "VISUAL_SUPPORT",
        "account_id": account,
        "generated": True,
        "evidence_capable": False,
        "production_ready": False,
        "publish_authorized": False,
    }


def plan_clip(
    *,
    account_id: str,
    template: str,
    placement_id: str,
    asset_id: str,
    props: Mapping[str, Any],
    duration_s: float = 4.0,
    backend: str = "remotion",
    dna: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if template not in TEMPLATES:
        raise AnimationError("UNKNOWN_TEMPLATE", f"unknown template {template!r}")
    if str(account_id) not in VIDEO_ACCOUNTS:
        raise AnimationError("UNKNOWN_ACCOUNT", str(account_id))
    name = normalize_backend(backend)
    if name not in CLIP_BACKENDS:
        raise AnimationError("UNSUPPORTED_BACKEND", str(backend))
    try:
        duration = float(duration_s)
    except (TypeError, ValueError) as exc:
        raise AnimationError("DURATION", "duration_s must be numeric") from exc
    if not 2.0 <= duration <= 8.0:
        raise AnimationError("DURATION", f"{duration}s is outside 2-8s")
    if not str(placement_id).strip() or not str(asset_id).strip():
        raise AnimationError("PLACEMENT", "placement_id and asset_id are required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", str(asset_id)):
        raise AnimationError("ASSET_ID", "asset_id must be a safe filename")
    cleaned = dict(props)
    if template == "rag_flow":
        nodes = cleaned.get("nodes")
        if not isinstance(nodes, list) or len(nodes) < 2:
            raise AnimationError("PROPS", "rag_flow needs at least two nodes")
        if any(not str(node).strip() for node in nodes):
            raise AnimationError("PROPS", "rag_flow nodes must be non-empty strings")
    if template in ("annotation", "comparison"):
        for key in ("title", "left_label", "right_label", "callout"):
            if not str(cleaned.get(key) or "").strip():
                raise AnimationError("PROPS", f"{template} needs {key}")
    if template == "recording_mark":
        required = ("title", "note")
        missing = [key for key in required if not str(cleaned.get(key) or "").strip()]
        if missing:
            raise AnimationError("PROPS", "recording_mark needs " + ", ".join(missing))
        recording_id = str(cleaned.get("recording_asset_id") or "").strip()
        if not recording_id:
            raise AnimationError("PROPS", "recording_mark needs recording_asset_id")
        box = cleaned.get("box")
        if not isinstance(box, Mapping):
            raise AnimationError("PROPS", "recording_mark needs a normalized box")
        try:
            x, y, w, h = (float(box[key]) for key in ("x", "y", "w", "h"))
        except (KeyError, TypeError, ValueError) as exc:
            raise AnimationError("PROPS", "recording_mark box needs numeric x/y/w/h") from exc
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > 1 or y + h > 1:
            raise AnimationError("PROPS", "recording_mark box must fit in normalized frame coordinates")
        for key in ("plate", "video", "recording_sha256"):
            cleaned.pop(key, None)
    if template == "title_card":
        missing = [key for key in ("conflict", "stakes")
                   if not str(cleaned.get(key) or "").strip()]
        if missing:
            raise AnimationError("PROPS", "title_card needs " + ", ".join(missing))
        # A hook card is an editorial title. It must never carry an evidence
        # claim or a source path; keep only display fields.
        for key in ("claim", "source_ref", "source_refs", "evidence_ref",
                    "recording_asset_id", "plate", "video"):
            cleaned.pop(key, None)
        # Visual parameters are DNA-owned, never shot-owned. Drop any attempt to
        # carry a font size, margin, colour or effect override through props.
        for key in ("font", "font_size", "fontSize", "font_size_px", "margin_v_px",
                    "side_margin_ratio", "max_chars_per_line", "palette_override",
                    "effect", "effects", "forbidden_effects", "color", "colour"):
            cleaned.pop(key, None)
        # Bound the hook text to the DNA line length so it wraps instead of
        # overflowing the 1080px width or the caption safe zone.
        contract = hook_visual_contract(dna or {})
        limit = contract["max_chars_per_line"]
        for key in ("conflict", "stakes"):
            text = str(cleaned.get(key) or "").strip()
            if len(text) > limit * 3:
                raise AnimationError(
                    "DNA_VISUAL",
                    f"title_card {key} has {len(text)} chars; DNA allows at most {limit * 3}",
                )
        cleaned["hook_contract"] = contract
    palette = cleaned.get("palette")
    if not isinstance(palette, Mapping) or not palette.get("bg") or not palette.get("ink"):
        raise AnimationError("PROPS", "props.palette must include bg and ink from account DNA")
    return {
        "schema": PLAN_SCHEMA,
        "account_id": account_id,
        "backend": name,
        "template": template,
        "composition": TEMPLATES[template]["composition"],
        "placement_id": placement_id,
        "asset_id": asset_id,
        "duration_s": duration,
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "props": cleaned,
        "generated": True,
        "evidence_capable": False,
        "counts_as_real_recording": False,
    }


def preflight(backend: str, probe: Mapping[str, Any]) -> Dict[str, Any]:
    """Interpret a caller-supplied environment probe. Does not spawn processes."""
    name = normalize_backend(backend)
    if name not in CLIP_BACKENDS:
        return _blocked("UNSUPPORTED_BACKEND", f"unsupported motion backend {name!r}")
    if not isinstance(probe, Mapping):
        return _blocked("PROBE", "preflight probe must be a mapping", backend=name)
    if probe.get("error"):
        return _blocked(str(probe["error"]), str(probe.get("detail") or "probe failed"), backend=name)
    missing = [item for item in ("node", "ffmpeg") if probe.get(item) is False]
    if name == "remotion":
        if probe.get("browser") is False:
            missing.append("browser")
        pinned = str(probe.get("pinned_version") or "")
        installed = str(probe.get("installed_cli_version") or "")
        core = str(probe.get("installed_core_version") or "")
        if pinned and pinned != REMOTION_VERSION:
            return _blocked(
                "VERSION_MISMATCH",
                f"pinned Remotion {pinned} is not {REMOTION_VERSION}",
                backend=name,
            )
        mismatches = [value for value in (installed, core) if value and value != REMOTION_VERSION]
        if mismatches or (probe.get("node_modules") is True and (not installed or not core)):
            return _blocked(
                "VERSION_MISMATCH",
                f"installed Remotion CLI/core versions {installed or 'unknown'}/{core or 'unknown'} do not match {REMOTION_VERSION}",
                backend=name,
            )
        if probe.get("node_modules") is False:
            missing.append("node_modules")
    if name == "manim" and probe.get("manim") is False:
        missing.append("manim")
    if name == "motion-canvas" and probe.get("headless_export") is False:
        return _blocked(
            "NO_HEADLESS_EXPORT",
            "Motion Canvas exports through the editor websocket, not a headless CLI",
            backend=name,
        )
    if missing:
        return _blocked("RUNTIME_MISSING", "missing " + ", ".join(missing), backend=name)
    return {
        "state": "READY",
        "code": "READY",
        "backend": name,
        "version": probe.get("pinned_version") or probe.get("version"),
        "execution_authorized": False,
        "production_ready": False,
        "publish_authorized": False,
    }


def resolve_skill(skill_id: str, installed: Sequence[str]) -> Dict[str, Any]:
    name = str(skill_id or "").strip()
    if name not in REMOTION_SKILLS:
        return {
            "state": "BLOCKED",
            "code": "UNKNOWN_SKILL",
            "skill_id": name,
            "execution_authorized": False,
        }
    present = name in set(installed)
    return {
        "state": "DISCOVERED" if present else "NOT_INSTALLED",
        "code": "DISCOVERED" if present else "SKILL_NOT_INSTALLED",
        "skill_id": name,
        "installed": present,
        "execution_authorized": False,
        "publish_authorized": False,
        "source_commit": None,
        "version": None,
    }


def build_receipt(
    *,
    project_id: str,
    account_id: str,
    placement_id: str,
    asset_id: str,
    backend: str,
    template: str,
    output_path: str,
    sha256: str,
    probe: Mapping[str, Any],
    purpose: str,
    source_spec: str,
    version: str,
    skill_source: Optional[str] = None,
    technical_qc: str = "PENDING",
) -> Dict[str, Any]:
    digest = str(sha256 or "").strip().lower()
    if not _HASH.match(digest):
        raise AnimationError("HASH", "sha256 must be 64 hex characters")
    logical = _logical(output_path)
    spec = _logical(source_spec)
    return {
        "schema": SCHEMA,
        "project_id": project_id,
        "account_id": account_id,
        "placement_id": placement_id,
        "asset_id": asset_id,
        "backend": normalize_backend(backend),
        "backend_version": version,
        "template": template,
        "skill_source": skill_source,
        "source_spec": spec,
        "output_path": logical,
        "sha256": digest,
        "width": probe.get("width"),
        "height": probe.get("height"),
        "fps": probe.get("fps") or probe.get("avg_frame_rate"),
        "codec": probe.get("codec_name"),
        "pix_fmt": probe.get("pix_fmt"),
        "duration_s": probe.get("duration_s"),
        "has_audio": bool(probe.get("has_audio")),
        "generated": True,
        "evidence_capable": False,
        "evidence_use": "VISUAL_SUPPORT",
        "source_kind": "vector_animation",
        "counts_as_real_recording": False,
        "purpose": purpose,
        "rights": "GENERATED_LOCAL_NO_COMMERCIAL_CLEARANCE",
        "technical_qc": technical_qc,
        "human_review": "PENDING_FOUNDER_REVIEW",
        "production_ready": False,
        "publish_authorized": False,
        "execution_authorized": False,
    }


def hook_visual_contract(dna: Mapping[str, Any]) -> Dict[str, Any]:
    """Derive the 3s hook card's visual rules from the account DNA.

    Every value comes from the account file: caption line length, the subtitle
    safe zone, the display font and the declared forbidden effects. A shot spec
    cannot raise a font size, shrink a safe margin, or re-enable a banned effect
    — there is no prop for any of them, so production cannot bypass the DNA by
    editing parameters.
    """
    visual = dna.get("visual") if isinstance(dna.get("visual"), Mapping) else {}
    caption = visual.get("caption_style") if isinstance(visual, Mapping) else {}
    caption = caption if isinstance(caption, Mapping) else {}
    safe = caption.get("safe_zone") if isinstance(caption, Mapping) else {}
    safe = safe if isinstance(safe, Mapping) else {}
    brand = dna.get("brand") if isinstance(dna.get("brand"), Mapping) else {}
    forbidden = brand.get("forbidden_effects") if isinstance(brand, Mapping) else ()
    forbidden = tuple(str(item) for item in (forbidden or ()))
    try:
        max_chars = int(caption.get("max_chars_per_line") or 18)
    except (TypeError, ValueError):
        max_chars = 18
    try:
        margin_v = int(safe.get("margin_v_px") or 120)
    except (TypeError, ValueError):
        margin_v = 120
    try:
        side_ratio = float(safe.get("side_margin_ratio") or 0.07)
    except (TypeError, ValueError):
        side_ratio = 0.07
    return {
        "font": str(caption.get("font") or "Noto Sans CJK SC"),
        "caption_size_px": int(caption.get("size_px") or 47),
        "max_chars_per_line": max(8, min(40, max_chars)),
        "margin_v_px": max(0, min(400, margin_v)),
        "side_margin_ratio": max(0.0, min(0.25, side_ratio)),
        "forbidden_effects": forbidden,
    }


def props_digest(props: Mapping[str, Any]) -> str:
    import json
    payload = json.dumps(props, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def clip_fingerprint(
    *,
    account_id: str,
    template: str,
    placement_id: str,
    asset_id: str,
    purpose: str,
    duration_s: float,
    props: Mapping[str, Any],
    dna: Mapping[str, Any],
    source_digests: Sequence[str] = (),
    version: str = REMOTION_VERSION,
    backend: str = "remotion",
    template_digest: str = "",
) -> str:
    """Identity of one render job. A cache hit requires an exact match.

    Brand DNA, render parameters, referenced source bytes, backend version and
    purpose all participate. A change to any of them changes the fingerprint,
    so a stale MP4 can never be replayed under a new identity. The filename is
    deliberately not part of the identity.
    """
    import json
    canonical_sources = sorted({str(value).strip().lower() for value in source_digests
                                if str(value).strip()})
    payload = {
        "schema": "contentops.clip-fingerprint/v1",
        "backend": normalize_backend(backend),
        "version": str(version),
        "account_id": str(account_id),
        "template": str(template),
        "placement_id": str(placement_id),
        "asset_id": str(asset_id),
        "purpose": str(purpose),
        "duration_s": round(float(duration_s), 3),
        "props": props_digest(props),
        "dna": props_digest(dna),
        "sources": canonical_sources,
        "template_digest": str(template_digest or "").strip().lower(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def palette_from_dna(dna: Mapping[str, Any]) -> Dict[str, str]:
    """Resolve brand palette first; animation props cannot replace DNA tokens."""
    brand = dna.get("brand") if isinstance(dna.get("brand"), Mapping) else {}
    palette = brand.get("palette") if isinstance(brand, Mapping) else None
    if not isinstance(palette, Mapping):
        visual = dna.get("visual") if isinstance(dna.get("visual"), Mapping) else {}
        motion = visual.get("motion") if isinstance(visual, Mapping) else {}
        profile = {}
        if isinstance(motion, Mapping):
            profile = motion.get("motion_profile") or motion.get("palette") or {}
        palette = profile.get("palette") if isinstance(profile, Mapping) else None
        if not isinstance(palette, Mapping):
            palette = visual.get("palette") if isinstance(visual, Mapping) else None
    if not isinstance(palette, Mapping):
        raise AnimationError("PALETTE", "account DNA has no brand palette")
    strict_brand = isinstance(brand.get("palette"), Mapping)
    keys = {"base": "bg", "muted": "sub"}
    resolved = {keys.get(key, key): str(value) for key, value in palette.items()
                if key in {"base", "bg", "surface", "ink", "muted", "sub", "accent"}}
    if strict_brand:
        resolved["bg"] = str(palette.get("base") or palette.get("bg"))
        resolved["accent"] = str(palette.get("accent"))
    needed = ("bg", "ink", "accent")
    missing = [key for key in needed if not resolved.get(key)]
    if missing:
        raise AnimationError("PALETTE", "palette missing " + ", ".join(missing))
    resolved.setdefault("surface", "#FFFFFF")
    resolved.setdefault("sub", resolved.get("ink", "#FFFFFF"))
    resolved["accent2"] = resolved["accent"]
    return resolved


# --- Unified backend capability matrix (P0.3) -----------------------------
# One executable table, derived from the constants and lock files already in
# this contract. It never grants execution or publication and never upgrades a
# declared capability to VERIFIED from configuration alone. Real render
# verification is supplied by a caller-supplied evidence map keyed by backend,
# so a green matrix cannot be produced by editing documentation.

CAPABILITY_LOCKS = {
    "remotion": "runtime/remotion.lock.json",
    "remotion-three": "runtime/remotion.lock.json",
    "huashu-art-motion": "runtime/huashu-motion.lock.json",
    "huashu-motion": "runtime/huashu-motion.lock.json",
    "manim": "runtime/manim.lock.json",
    "motion-canvas": "runtime/motion-canvas.lock.json",
}

CAPABILITY_TEMPLATES = {
    "remotion": (
        "annotation", "comparison", "rag_flow", "recording_mark", "title_card",
    ),
    "remotion-three": ("technical_3d_explainer",),
    "huashu-art-motion": (
        "architecture_flow", "state_transition", "code_focus",
        "evidence_zoom", "metric_transition", "comparison_reveal",
    ),
    "huashu-motion": (),
    "manim": ("math_formula_reveal", "attention_matrix_flow"),
    "motion-canvas": ("animated_system_graph", "agent_state_machine"),
}

CAPABILITY_SHOT_TYPES = {
    "remotion": tuple(key for key, backends in SHOT_COMPATIBILITY.items() if "remotion" in backends),
    "remotion-three": ("architecture", "agent_flow"),
    "huashu-art-motion": ("architecture", "agent_flow", "annotation", "comparison", "title_card"),
    "huashu-motion": ("architecture", "agent_flow", "annotation", "comparison"),
    "manim": ("math",),
    "motion-canvas": ("architecture", "agent_flow"),
}

CAPABILITY_RENDER_ENTRY = {
    "remotion": "scripts/animation_render.py",
    "remotion-three": "scripts/animation_render.py",  # same render entry; 3D is a composition
    "huashu-art-motion": "scripts/huashu_motion_adapter.py",
    "huashu-motion": "scripts/huashu_motion_adapter.py",
    "manim": "scripts/manim_render.py",
    "motion-canvas": "scripts/motion_canvas_render.py",
}

# Honest default: no backend is render-verified until a receipt-backed evidence
# map is supplied. Declared here only so the matrix is self-describing.
CAPABILITY_DEFAULT_STATE = {
    "remotion": "IMPLEMENTED_NOT_VERIFIED",
    "remotion-three": "MISSING",
    "huashu-art-motion": "IMPLEMENTED_NOT_VERIFIED",
    "huashu-motion": "IMPLEMENTED_NOT_VERIFIED",
    "manim": "MISSING",
    "motion-canvas": "MISSING",
}


def capability_matrix(
    repo_root: Optional[Path | str] = None,
    *,
    render_evidence: Optional[Mapping[str, Any]] = None,
    block_state: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Return the single executable backend capability matrix.

    ``render_evidence`` maps a backend name to a receipt-backed dict containing
    at least ``verified_at``, ``sha256`` and ``receipt``. A backend is promoted
    to ``VERIFIED`` only when that mapping is supplied — never by reading a
    lock file or a document. ``block_state`` maps a backend to its current
    blocking code (for example ``RUNTIME_MISSING``); absent entries stay
    declared rather than silently passing.
    """
    # parents: [0]=media, [1]=contentops, [2]=src, [3]=repo root
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    evidence = render_evidence if isinstance(render_evidence, Mapping) else {}
    blocks = block_state if isinstance(block_state, Mapping) else {}
    rows: Dict[str, Any] = {}
    for backend in KNOWN_BACKENDS + ("remotion-three",):
        lock_rel = CAPABILITY_LOCKS.get(backend)
        lock_path = root / lock_rel if lock_rel else None
        installed_lock = bool(lock_path and lock_path.is_file())
        version = None
        version_source = None
        license_text = None
        if installed_lock:
            try:
                data = json.loads(lock_path.read_text(encoding="utf-8"))
                version = data.get("version") or data.get("installed_version")
                version_source = data.get("version_source") or lock_rel
                license_text = data.get("license") or data.get("license_read")
            except (OSError, ValueError):
                data = {}
        if backend == "remotion" and not version:
            version = REMOTION_VERSION
            version_source = "animation_backend.REMOTION_VERSION"
        proof = evidence.get(backend)
        verified = bool(isinstance(proof, Mapping) and proof.get("verified_at")
                        and proof.get("sha256") and proof.get("receipt"))
        blocking = str(blocks.get(backend) or "") or None
        # A blocking gate outranks a historical receipt: a currently blocked
        # backend is never advertised as VERIFIED, even with past evidence.
        if blocking:
            state = "BLOCKED"
        elif verified:
            state = "VERIFIED"
        else:
            state = CAPABILITY_DEFAULT_STATE.get(backend, "MISSING")
        rows[backend] = {
            "backend": backend,
            "schema": CAPABILITY_SCHEMA,
            "runtime_version": version,
            "version_source": version_source,
            "lock_file": lock_rel,
            "lock_present": installed_lock,
            "install_environment": ("extensions/animation-remotion (npm, gitignored node_modules)"
                                    if backend.startswith("remotion") else "isolated local runtime"),
            "supported_shot_types": list(CAPABILITY_SHOT_TYPES.get(backend, ())),
            "templates": list(CAPABILITY_TEMPLATES.get(backend, ())),
            "render_entry": CAPABILITY_RENDER_ENTRY.get(backend),
            "input_contract": PLAN_SCHEMA,
            "output_contract": SCHEMA,
            "output_spec": {"width": 1080, "height": 1920, "fps": 30, "codec": "h264",
                            "pix_fmt": "yuv420p", "duration_s": [2, 8], "audio": False},
            "render_verified": verified,
            "render_evidence": dict(proof) if isinstance(proof, Mapping) else None,
            "license": license_text,
            "execution_authorized": False,
            "publish_authorized": False,
            "production_ready": False,
            "blocking_status": blocking,
            "state": state,
            "accounts": list(VIDEO_ACCOUNTS),
            "is_compositor": False,
        }
    return {
        "schema": CAPABILITY_SCHEMA,
        "note": ("capability rows are declarations plus lock-file facts. Only a receipt-backed "
                 "render_evidence entry promotes a backend to VERIFIED. No row composes a film."),
        "backends": rows,
    }
