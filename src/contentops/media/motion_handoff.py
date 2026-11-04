"""External motion handoff contract: validate a record without granting reuse.

MotionClone is an external tool. ContentOps receives a handoff for one short,
self-owned clip and checks that the record is internally consistent and bounded:
a logical project path, a real MP4 with a matching digest, the pinned runtime
pair, original and rearranged project hashes, a short source window, an internal
rights scope, and the three authority flags false.

A validated handoff is ``ACCEPTED_FOR_REVIEW``. It does **not** enter the M5
manifest automatically, does not authorize public reuse of third-party
derivative material, and does not publish. The caller must still place the asset
on the one active timeline and run the gates.

What is not claimed
-------------------
A record is not a licence. Reading it proves the file and metadata agree; it
does not prove the source clip may be published, nor that the motion is usable.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA = "contentops.motion-handoff/v1"

ACCOUNT_ROLES = ("explorer", "thinktank")
STATUSES = ("RECEIVED",)
RIGHTS_SCOPES = ("OWNED_SELF_MADE", "LICENSED_INTERNAL_REVIEW", "INTERNAL_REVIEW_ONLY")

#: The pinned external pair. Mixing media-use's 0.8.222 runtime into this path is
#: a mismatch, not a variant.
EXPECTED_RUNTIME = {
    "name": "MotionClone",
    "version": "2.0.0",
    "hyperframes_version": "0.8.33",
}

SOURCE_WINDOW_MAX_S = 8.0
OUTPUT_MIN_S = 4.0
OUTPUT_MAX_S = 12.0
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 30.0

_HASH = re.compile(r"^[0-9a-f]{64}$")


class HandoffError(ValueError):
    """A handoff record violates the contract."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise HandoffError(code, detail)


def _hex(value: Any, field: str) -> str:
    text = str(value or "").strip().lower()
    _require(bool(_HASH.match(text)), "HANDOFF_PROJECT_HASH", f"{field} must be a 64-char hex digest")
    return text


def _resolve_output(path: str, project_root: Path) -> Path:
    text = str(path or "").strip()
    if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise HandoffError("HANDOFF_PATH_ABSOLUTE", f"{text!r} is an absolute host path")
    if not text.startswith("project://"):
        raise HandoffError("HANDOFF_PATH_SCHEME", "a motion asset must use project://")
    relative = text[len("project://"):]
    _require(".." not in Path(relative).parts, "HANDOFF_PATH_ESCAPE", f"{text!r} escapes the project")
    root = Path(project_root).resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HandoffError("HANDOFF_PATH_ESCAPE", f"{text!r} escapes the project")
    return candidate


def _check_probe(probe: Dict[str, Any]) -> None:
    _require(not bool(probe.get("has_audio")), "HANDOFF_AUDIO_PRESENT", "a motion handoff must be silent")
    _require(probe.get("width") == TARGET_WIDTH and probe.get("height") == TARGET_HEIGHT,
             "HANDOFF_PROBE", "the probe is not 1080x1920")
    _require(str(probe.get("codec_name") or "").lower() in ("h264", "libx264"),
             "HANDOFF_PROBE", "the probe is not H.264")
    _require(str(probe.get("pix_fmt") or "").lower() == "yuv420p",
             "HANDOFF_PROBE", "the probe is not yuv420p")
    _require(str(probe.get("avg_frame_rate") or "") == "30/1"
             and str(probe.get("r_frame_rate") or "") == "30/1",
             "HANDOFF_PROBE", "the probe is not 30 fps")


def validate_handoff(payload: Dict[str, Any], *, project_root: Path,
                     probe: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Validate one handoff record; return a review-bound result.

    ``probe`` is optional: when supplied, the file's real media facts are checked
    as well as the record fields.
    """
    _require(isinstance(payload, dict) and payload.get("schema") == SCHEMA,
             "HANDOFF_SCHEMA", f"expected schema {SCHEMA}")
    _require(bool(str(payload.get("asset_id") or "").strip()), "HANDOFF_ASSET_ID", "asset_id is required")
    _require(payload.get("account_role") in ACCOUNT_ROLES,
             "HANDOFF_ACCOUNT_ROLE", f"account_role must be one of {', '.join(ACCOUNT_ROLES)}")
    _require(payload.get("status") in STATUSES,
             "HANDOFF_STATUS", f"status {payload.get('status')!r} is not an accepted handoff state")

    runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
    for key, expected in EXPECTED_RUNTIME.items():
        _require(str(runtime.get(key) or "") == expected,
                 "HANDOFF_RUNTIME_MISMATCH",
                 f"runtime {key}={runtime.get(key)!r}; expected {expected!r}")

    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    original = _hex(project.get("original_sha256"), "original_sha256")
    rearranged = _hex(project.get("rearranged_sha256"), "rearranged_sha256")

    output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
    resolved = _resolve_output(str(output.get("path") or ""), Path(project_root))
    _require(resolved.is_file(), "HANDOFF_FILE_MISSING", str(resolved))
    actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
    expected_hash = str(output.get("sha256") or "").lower()
    _require(bool(_HASH.match(expected_hash)), "HANDOFF_HASH_MISMATCH", "output.sha256 is not a hex digest")
    _require(actual == expected_hash, "HANDOFF_HASH_MISMATCH", "the file digest does not match the record")

    try:
        duration = float(output.get("duration_s"))
    except (TypeError, ValueError):
        raise HandoffError("HANDOFF_OUTPUT", "output.duration_s must be numeric")
    _require(OUTPUT_MIN_S <= duration <= OUTPUT_MAX_S,
             "HANDOFF_OUTPUT", f"{duration:.3f}s is outside {OUTPUT_MIN_S:.0f}-{OUTPUT_MAX_S:.0f}s")
    _require(output.get("width") == TARGET_WIDTH and output.get("height") == TARGET_HEIGHT,
             "HANDOFF_OUTPUT", "the record is not 1080x1920")
    _require(str(output.get("codec") or "").lower() in ("h264", "libx264"),
             "HANDOFF_OUTPUT", "the record is not H.264")
    _require(str(output.get("pix_fmt") or "").lower() == "yuv420p",
             "HANDOFF_OUTPUT", "the record is not yuv420p")
    _require(output.get("silent") is True, "HANDOFF_AUDIO_PRESENT", "the record must be silent")
    try:
        fps = float(output.get("fps"))
    except (TypeError, ValueError):
        raise HandoffError("HANDOFF_OUTPUT", "output.fps must be numeric")
    _require(abs(fps - TARGET_FPS) <= 0.001, "HANDOFF_OUTPUT", "the record is not 30 fps")

    window = payload.get("source_window") if isinstance(payload.get("source_window"), dict) else {}
    try:
        start = float(window.get("start_s"))
        end = float(window.get("end_s"))
    except (TypeError, ValueError):
        raise HandoffError("HANDOFF_SOURCE_WINDOW", "source_window needs numeric start_s and end_s")
    _require(0 <= start < end, "HANDOFF_SOURCE_WINDOW", "source_window must satisfy 0 <= start < end")
    _require(end - start <= SOURCE_WINDOW_MAX_S,
             "HANDOFF_SOURCE_WINDOW",
             f"source window {end - start:.3f}s exceeds {SOURCE_WINDOW_MAX_S:.0f}s")

    rights = payload.get("rights") if isinstance(payload.get("rights"), dict) else {}
    _require(rights.get("scope") in RIGHTS_SCOPES,
             "HANDOFF_RIGHTS_SCOPE",
             f"scope must be internal-only: {', '.join(RIGHTS_SCOPES)}")
    for field in ("reviewed_by", "reviewed_at", "evidence"):
        _require(bool(str(rights.get(field) or "").strip()),
                 "HANDOFF_RIGHTS_SCOPE", f"rights.{field} is required")

    _require(payload.get("generated") is True, "HANDOFF_FLAGS", "generated must be true")
    _require(payload.get("evidence_capable") is False, "HANDOFF_FLAGS", "evidence_capable must be false")
    _require(payload.get("publish_authorized") is False, "HANDOFF_FLAGS", "publish_authorized must be false")

    if probe is not None:
        _require(isinstance(probe, dict), "HANDOFF_PROBE", "probe must be a mapping")
        _check_probe(probe)

    return {
        "schema": "contentops.motion-handoff-result/v1",
        "state": "ACCEPTED_FOR_REVIEW",
        "asset_id": str(payload["asset_id"]),
        "account_role": payload["account_role"],
        "path": f"project://{resolved.relative_to(Path(project_root).resolve()).as_posix()}",
        "sha256": actual,
        "duration_s": round(duration, 3),
        "source_window": {"start_s": start, "end_s": end},
        "original_sha256": original,
        "rearranged_sha256": rearranged,
        "rights": {
            "scope": rights["scope"],
            "reviewed_by": rights["reviewed_by"],
            "reviewed_at": rights["reviewed_at"],
            "evidence": rights["evidence"],
            # A record never upgrades an internal review into public reuse.
            "public_reuse_authorized": False,
        },
        "generated": True,
        "evidence_capable": False,
        "production_ready": False,
        "publish_authorized": False,
        "note": "validated record only; it does not enter the M5 timeline by itself",
    }
