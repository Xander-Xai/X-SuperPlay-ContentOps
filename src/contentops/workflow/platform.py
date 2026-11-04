"""Platform constraints: local execution limits, not platform authority.

The registry says which platforms exist; it does not say what a cut may look
like on each one. This module supplies the local, conservative execution limits
a project needs before it is rendered: aspect ratio, a maximum sensible
duration, and a caption ceiling. They are **local policy**, not a claim about
what a platform accepts.

An unknown platform fails closed. A target that contradicts the limits is
refused rather than silently coerced.

What is not claimed
-------------------
A passing check does not mean the platform will accept the upload, and it does
not grant posting authority. Publication remains manual and separately
authorized.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .contract import WorkflowError

SCHEMA = "contentops.platform-constraints/v1"

#: Conservative local defaults. These are chosen limits, not platform facts.
DEFAULT_CONSTRAINTS: Dict[str, Dict[str, Any]] = {
    "douyin": {"aspect_ratio": "9:16", "max_duration_s": 180, "caption_max_chars": 80},
    "xiaohongshu": {"aspect_ratio": "3:4", "max_duration_s": 300, "caption_max_chars": 1000},
    "xiaohongshu_video": {"aspect_ratio": "3:4", "max_duration_s": 300, "caption_max_chars": 1000},
    "xiaohongshu_image": {"aspect_ratio": "3:4", "max_duration_s": 300, "caption_max_chars": 1000},
    "bilibili": {"aspect_ratio": "16:9", "max_duration_s": 600, "caption_max_chars": 200},
    "wechat_channels": {"aspect_ratio": "9:16", "max_duration_s": 180, "caption_max_chars": 80},
    "shipinhao": {"aspect_ratio": "9:16", "max_duration_s": 180, "caption_max_chars": 80},
    "wechat_official_account": {"aspect_ratio": "3:4", "max_duration_s": 600, "caption_max_chars": 2000},
    "wechat_article": {"aspect_ratio": "3:4", "max_duration_s": 600, "caption_max_chars": 2000},
    "zhihu": {"aspect_ratio": "16:9", "max_duration_s": 600, "caption_max_chars": 2000},
    "csdn": {"aspect_ratio": "16:9", "max_duration_s": 600, "caption_max_chars": 2000},
    "youtube": {"aspect_ratio": "16:9", "max_duration_s": 600, "caption_max_chars": 5000},
    "x": {"aspect_ratio": "16:9", "max_duration_s": 140, "caption_max_chars": 280},
}

#: Registry rows use split ids for a platform with two content forms.
REGISTRY_ALIASES = {
    "xiaohongshu": ("xiaohongshu_video", "xiaohongshu_image"),
    "wechat_channels": ("shipinhao",),
    "wechat_official_account": ("wechat_article",),
}

ASPECTS = ("9:16", "3:4", "16:9", "1:1")


def constraints_for(platform: str, registry_path: Optional[Path] = None) -> Dict[str, Any]:
    """Return the local constraints for ``platform``; unknown platforms fail."""
    key = str(platform or "").strip().lower()
    if not key:
        raise WorkflowError("PLATFORM_MISSING", "a target platform is required")
    if key not in DEFAULT_CONSTRAINTS:
        raise WorkflowError("PLATFORM_UNKNOWN", f"{key!r} has no local constraint profile")
    base = dict(DEFAULT_CONSTRAINTS[key])
    # The registry is a presence check only; it never supplies executable limits.
    if registry_path is not None:
        try:
            data = json.loads(Path(registry_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict):
            rows = data.get("platforms") or data.get("entries") or []
            if isinstance(rows, list) and rows:
                ids = {str(row.get("platform_id") or row.get("id") or row.get("platform") or "").lower()
                       for row in rows if isinstance(row, dict)}
                accepted = {key} | set(REGISTRY_ALIASES.get(key, ()))
                if not (accepted & ids):
                    raise WorkflowError("PLATFORM_NOT_REGISTERED", f"{key!r} is absent from the registry")
    return {
        "schema": SCHEMA,
        "platform": key,
        "aspect_ratio": base["aspect_ratio"],
        "max_duration_s": base["max_duration_s"],
        "caption_max_chars": base["caption_max_chars"],
        "authority": "local execution limit only; not platform acceptance or posting authority",
        "production_ready": False,
    }


def validate_target(target: Dict[str, Any], constraints: Dict[str, Any]) -> Dict[str, Any]:
    """Check a project target against the chosen platform constraints."""
    if not isinstance(target, dict):
        raise WorkflowError("PLATFORM_TARGET", "target must be an object")
    aspect = str(target.get("aspect_ratio") or constraints.get("aspect_ratio"))
    if aspect not in ASPECTS:
        raise WorkflowError("PLATFORM_ASPECT", f"aspect {aspect!r} is not supported locally")
    if aspect != constraints.get("aspect_ratio"):
        raise WorkflowError(
            "PLATFORM_ASPECT_MISMATCH",
            f"target {aspect} does not match the {constraints.get('platform')} profile {constraints.get('aspect_ratio')}",
        )
    try:
        duration = float(target.get("duration_target_sec"))
    except (TypeError, ValueError):
        raise WorkflowError("PLATFORM_DURATION", "duration_target_sec must be numeric")
    if duration <= 0 or duration > float(constraints.get("max_duration_s")):
        raise WorkflowError(
            "PLATFORM_DURATION",
            f"{duration}s exceeds the local {constraints.get('max_duration_s')}s limit",
        )
    return {"aspect_ratio": aspect, "duration_target_sec": duration}
