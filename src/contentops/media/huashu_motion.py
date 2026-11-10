"""Fail-closed adapters and the one shared asset contract for the Huashu engines.

Two engines, one vocabulary
---------------------------
``huashu-motion`` (upstream ``alchaincyf/huashu-motion``) and ``huashu-art-motion``
(upstream ``alchaincyf/huashu-art-motion``) are different programs with different
runtimes, but the material they produce enters the M4.5 pipeline through one
record schema: :data:`RECORD_SCHEMA`. A consumer does not branch on the engine to
read a duration or a digest.

What this module never does
----------------------------
It never starts the upstream CLI, never installs a runtime, and never converts a
trusted runtime into execution authority. The upstream project is a *producer* of
motion clips; the pinned Easel adapter remains the only compositor.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional

#: The shared record every Huashu motion asset is described by.
RECORD_SCHEMA = "contentops.huashu-motion-asset/v1"

ENGINE_MOTION = "huashu-motion"
ENGINE_ART_MOTION = "huashu-art-motion"

#: Engine identities. Each is pinned to one upstream repository and commit.
ENGINES: Dict[str, Dict[str, str]] = {
    ENGINE_MOTION: {
        "repository": "https://github.com/alchaincyf/huashu-motion",
        "version": "0.3.1",
        "commit": "52467f99c602b76ba86d511d37acdfe93fa1e16e",
        # The skill's CLI wrapper; it calls the repository's own command line.
        "entrypoint": "skills/huashu-motion/bin/om",
        # The dispatcher the wrapper reaches. Both are checked: a checkout with
        # one of the two missing is not a usable runtime.
        "dispatcher": "cli/om.js",
        "runtime_root": "D:/Toolchains/huashu-motion/0.3.1",
        "lock": "runtime/huashu-motion.lock.json",
        "role": "MOTION_CLIP_PRODUCER_NOT_FINAL_COMPOSITOR",
    },
    ENGINE_ART_MOTION: {
        "repository": "https://github.com/alchaincyf/huashu-art-motion",
        "version": "1.2.0",
        "commit": "8f0a349a18b4bdf802b8d58715a2259c3e1ce709",
        "entrypoint": "scripts/engine/render.py",
        "runtime_root": "D:/Toolchains/huashu-art-motion/1.2.0",
        "lock": "runtime/huashu-art-motion-baseline.json",
        "role": "MOTION_CLIP_PRODUCER_NOT_FINAL_COMPOSITOR",
    },
}

#: The upstream clip contract caps one parameterized segment at eight seconds.
MAX_CLIP_S = 8.0

#: Upstream ``om`` operations this adapter can describe. The syntax is the
#: upstream's own, read from ``cli/om.js`` at the pinned commit; nothing here
#: is invented, and nothing here is a command this repository may run.
OPERATIONS = {
    "check": {
        "command": "om check [dir] [--samples n] [--source] [--json]",
        "purpose": "Upstream pre-render checks: structure, scripts, files, motion "
                   "rules, then sampled frames.",
        "output": "findings (JSON with --json) or a report; the process exits 1 "
                  "when any finding is error-level.",
    },
    "still": {
        "command": "om still <page.html|dir> [--at 0,2.5] [--out file]",
        "purpose": "Capture a PNG of any page at the given times.",
        "output": "PNG; the caller binds it to a scene and a timestamp.",
    },
    "render": {
        "command": "om render [dir] [--format mp4|mov|webm|gif] [--fps 30] "
                   "[--out file] [--workers n] [--video extract|seek] "
                   "[--frames jpg|png] [--blur n] [--silent] [--transparent]",
        "purpose": "Render the upstream project into a media file.",
        "output": "a media file under <dir>/out/; this adapter never performs "
                  "the render.",
    },
    "qa": {
        "command": "om qa [dir|video] [--loop]",
        "purpose": "Upstream post-render QA of the newest render, or of a given "
                   "video file.",
        "output": "a QA report (single-frame pops, dead time, hard cuts, motion "
                  "curve, loop seam); it does not grant human approval.",
    },
}

#: Operations that read or write project files rather than producing media.
#: The managed gate keeps them apart because their blast radius is a project,
#: not a clip.
NON_MEDIA_OPERATIONS = ("check", "still", "qa")

#: Facts about the upstream render that the ContentOps side has to plan for.
#: Read from README.md at the pinned commit.
OUTPUT_NOTES = (
    "a render of 4 s or longer carries an upstream 'Made with huashu-motion' "
    "credit line in the last 1.2 s unless the film opts out",
    "om render warns about a missing soundtrack unless om sound was run or "
    "--silent was passed; the ContentOps motion gate requires a silent clip",
    "om voice narration uses macOS system voices; on Windows a narration track "
    "must be supplied with --audio <file>",
)

REPOSITORY = ENGINES[ENGINE_MOTION]["repository"]
VERSION = ENGINES[ENGINE_MOTION]["version"]
COMMIT = ENGINES[ENGINE_MOTION]["commit"]
ENTRYPOINT = ENGINES[ENGINE_MOTION]["entrypoint"]
DEFAULT_RUNTIME = Path(ENGINES[ENGINE_MOTION]["runtime_root"])
LOCK_PATH = Path(__file__).resolve().parents[3] / ENGINES[ENGINE_MOTION]["lock"]


class HuashuMotionError(ValueError):
    """Invalid runtime, operation, or output contract."""


def _fps(value: Any) -> Optional[float]:
    try:
        if isinstance(value, str) and "/" in value:
            numerator, denominator = value.split("/", 1)
            return float(numerator) / float(denominator)
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None


def _normalized_repository(value: str) -> str:
    value = (value or "").strip().removesuffix(".git").rstrip("/").lower()
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.split(":", 1)[1].removesuffix(".git")
    elif value.startswith("ssh://git@github.com/"):
        value = "https://github.com/" + value.split("github.com/", 1)[1].removesuffix(".git")
    return value


def engine_identity(engine: str) -> Dict[str, str]:
    """Return the pinned identity of one engine, or refuse an unknown name."""
    identity = ENGINES.get(str(engine or ""))
    if identity is None:
        raise HuashuMotionError(
            f"unknown Huashu engine {engine!r}; expected one of {', '.join(sorted(ENGINES))}"
        )
    return dict(identity)


def verify_runtime(runtime_root: Path, *, lock: Optional[dict] = None,
                   git_probe: Optional[Callable[..., tuple[int, str]]] = None) -> dict:
    """Compare a local huashu-motion checkout with the committed pin.

    Proves bytes' provenance only. It is not execution authority, and it is not
    a statement about the licence of anything the engine renders.
    """
    if lock is None:
        try:
            lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return {"status": "BLOCKED", "reason": "LOCK_UNAVAILABLE", "detail": str(exc)}
    identity = ENGINES[ENGINE_MOTION]
    expected = {
        "schema": "contentops.huashu-motion-lock/v1",
        "capability": ENGINE_MOTION,
        "repository": identity["repository"],
        "version": identity["version"],
        "commit": identity["commit"],
        "entrypoint": identity["entrypoint"],
        "dispatcher": identity["dispatcher"],
    }
    if not isinstance(lock, dict) or any(lock.get(key) != value for key, value in expected.items()):
        return {"status": "BLOCKED", "reason": "LOCK_MISMATCH"}

    root = Path(runtime_root).resolve()
    if not root.is_dir():
        return {"status": "BLOCKED", "reason": "RUNTIME_ROOT_MISSING", "runtime_root": root}
    for key, reason in (("entrypoint", "ENTRYPOINT"), ("dispatcher", "DISPATCHER")):
        candidate = (root / identity[key]).resolve()
        if not candidate.is_relative_to(root):
            return {"status": "BLOCKED", "reason": f"{reason}_ESCAPED_RUNTIME_ROOT",
                    "runtime_root": root, "path": candidate}
        if not candidate.is_file():
            return {"status": "BLOCKED", "reason": f"{reason}_MISSING",
                    "runtime_root": root, "path": candidate}
    entry = (root / identity["entrypoint"]).resolve()
    license_path = (root / "LICENSE").resolve()
    if not license_path.is_relative_to(root):
        return {"status": "BLOCKED", "reason": "LICENSE_ESCAPED_RUNTIME_ROOT", "license": license_path}
    if not license_path.is_file():
        return {"status": "BLOCKED", "reason": "LICENSE_MISSING", "license": license_path}
    if git_probe is None:
        return {"status": "BLOCKED", "reason": "GIT_PROBE_REQUIRED"}

    checks = (
        (("rev-parse", "HEAD"), identity["commit"], "COMMIT_MISMATCH"),
        (("remote", "get-url", "origin"), identity["repository"], "UPSTREAM_MISMATCH"),
        (("status", "--porcelain", "--untracked-files=all"), "", "DIRTY_RUNTIME"),
    )
    for args, expected_value, reason in checks:
        try:
            code, actual = git_probe(root, *args)
        except Exception as exc:
            return {"status": "BLOCKED", "reason": "GIT_VERIFICATION_FAILED", "detail": str(exc)}
        if code != 0:
            return {"status": "BLOCKED", "reason": "GIT_VERIFICATION_FAILED", "operation": args[0]}
        if args[0] == "remote":
            matches = _normalized_repository(actual) == _normalized_repository(expected_value)
        else:
            matches = (actual or "").strip() == expected_value
        if not matches:
            return {"status": "BLOCKED", "reason": reason, "runtime_root": root}

    return {"status": "TRUSTED_RUNTIME", "runtime_root": root, "entrypoint": entry,
            "version": identity["version"], "commit": identity["commit"],
            "engine": ENGINE_MOTION,
            "execution_authorized": False}


def describe_operation(operation: str) -> dict:
    """Return a human-readable operation plan, not a shell command to execute."""
    name = str(operation or "").strip().lower()
    if name not in OPERATIONS:
        raise HuashuMotionError(f"unknown Huashu Motion operation: {operation!r}")
    return {
        "schema": "contentops.huashu-motion-operation-plan/v1",
        "operation": name,
        **OPERATIONS[name],
        "state": "BLOCKED",
        "execution_status": "NOT_EXECUTED",
        "execution_authorized": False,
        "reason": "MANAGED_EXECUTION_AUTHORIZATION_REQUIRED",
    }


def request_operation(operation: str, *, runtime: dict,
                      runner: Optional[Callable[..., Any]] = None) -> dict:
    """Return a refusal until a real scoped managed-execution adapter exists.

    ``runner`` is an injected test spy. It is intentionally never called by this
    implementation, including when a runtime is trusted: runtime integrity is not
    execution authority.
    """
    plan = describe_operation(operation)
    receipt = {
        "schema": "contentops.huashu-motion-operation/v1",
        "engine": ENGINE_MOTION,
        "version": VERSION,
        "commit": COMMIT,
        "operation": plan["operation"],
        "runtime_status": runtime.get("status") if isinstance(runtime, dict) else "UNKNOWN",
        "status": "BLOCKED",
        "execution_status": "NOT_EXECUTED",
        "execution_authorized": False,
        "runner_invoked": False,
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
        "publish_authorized": False,
    }
    receipt["reason"] = (
        runtime.get("reason", "RUNTIME_BLOCKED")
        if not isinstance(runtime, dict) or runtime.get("status") != "TRUSTED_RUNTIME"
        else "MANAGED_EXECUTION_AUTHORIZATION_REQUIRED"
    )
    return receipt


def write_operation_receipt(project_root: Path, receipt: dict) -> Path:
    """Persist a blocked/not-executed operation receipt without calling the engine."""
    root = Path(project_root).resolve()
    if not root.is_dir() or receipt.get("schema") != "contentops.huashu-motion-operation/v1":
        raise HuashuMotionError("a project directory and Huashu Motion operation receipt are required")
    operation = receipt.get("operation")
    if operation not in OPERATIONS or receipt.get("execution_status") != "NOT_EXECUTED":
        raise HuashuMotionError("only a named, non-executed operation receipt can be written")
    path = root / "receipts" / f"huashu-motion-{operation}.json"
    if not path.resolve().is_relative_to(root) or path.exists():
        raise HuashuMotionError("receipt path escapes the project or already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_output_record(*, engine: str, spec_sha256: str, clip_path: str,
                         clip_sha256: str, duration: float, resolution: str,
                         fps: float, audio_policy: str,
                         input_asset_hashes: Optional[dict] = None,
                         rights: str = "UNRESOLVED",
                         technical_status: str = "TECHNICALLY_CHECKED",
                         extra: Optional[dict] = None) -> Dict[str, Any]:
    """Build the one shared record both engines emit for a checked clip."""
    identity = engine_identity(engine)
    if technical_status != "TECHNICALLY_CHECKED":
        raise HuashuMotionError("only a technically checked clip can produce a record")
    if not re.fullmatch(r"[0-9a-f]{64}", str(spec_sha256 or "")):
        raise HuashuMotionError("spec_sha256 must be a lowercase SHA-256 digest")
    if not re.fullmatch(r"[0-9a-f]{64}", str(clip_sha256 or "")):
        raise HuashuMotionError("clip_sha256 must be a lowercase SHA-256 digest")
    if not re.fullmatch(r"[0-9]{4}x[0-9]{4}", str(resolution or "")):
        raise HuashuMotionError("resolution must be WIDTHxHEIGHT")
    if not math.isfinite(float(duration)) or not (0.0 < float(duration) <= MAX_CLIP_S):
        raise HuashuMotionError(f"duration must be within 0-{MAX_CLIP_S:g}s")
    if not math.isfinite(float(fps)) or float(fps) <= 0:
        raise HuashuMotionError("fps must be a positive finite number")
    policy = str(audio_policy or "").upper()
    if policy not in {"MUTE", "REPLACE"}:
        raise HuashuMotionError("a motion clip enters M4.5 under an explicit MUTE or REPLACE policy")
    hashes = input_asset_hashes or {}
    if (not isinstance(hashes, dict)
            or any(not isinstance(name, str) or not name
                   or not re.fullmatch(r"[0-9a-f]{64}", str(digest))
                   for name, digest in hashes.items())):
        raise HuashuMotionError("input_asset_hashes must map names to lowercase SHA-256 digests")
    record = {
        "schema": RECORD_SCHEMA,
        "engine": engine,
        "version": identity["version"],
        "commit": identity["commit"],
        "spec_sha256": spec_sha256,
        "asset_hashes": dict(hashes),
        "clip_path": clip_path,
        "clip_sha256": clip_sha256,
        "duration": round(float(duration), 3),
        "resolution": resolution,
        "fps": float(fps),
        "audio_policy": policy,
        "rights": rights,
        "technical_status": technical_status,
        "review_status": "PENDING_FOUNDER_REVIEW",
        "generated": True,
        "evidence_capable": False,
        "production_ready": False,
        "publish_authorized": False,
    }
    if extra:
        record.update(dict(extra))
    return record


def validate_output(path: Path, *, project_root: Path, expected_sha256: str,
                    spec_sha256: str, probe: dict, audio_policy: str,
                    input_asset_hashes: Optional[dict] = None,
                    engine: str = ENGINE_MOTION) -> Dict[str, Any]:
    """Validate one silent motion clip and return the shared record."""
    from contentops.media.motion_sample import check_motion_clip

    root = Path(project_root).resolve()
    output = Path(path).resolve()
    if not output.is_relative_to(root) or not output.is_file():
        raise HuashuMotionError("output file is missing or escapes the project root")
    if not re.fullmatch(r"[0-9a-f]{64}", str(spec_sha256 or "")):
        raise HuashuMotionError("spec_sha256 must be a lowercase SHA-256 digest")
    if not re.fullmatch(r"[0-9a-f]{64}", str(expected_sha256 or "")):
        raise HuashuMotionError("expected_sha256 must be a lowercase SHA-256 digest")
    policy = str(audio_policy or "").upper()
    if policy not in {"MUTE", "REPLACE"}:
        raise HuashuMotionError("the canonical motion gate requires MUTE or REPLACE audio policy")
    if not isinstance(probe, dict) or type(probe.get("has_audio")) is not bool:
        raise HuashuMotionError("probe must explicitly declare has_audio")
    if probe["has_audio"] is not False:
        raise HuashuMotionError(f"{policy} requires an audio-free clip")
    try:
        duration = float(probe["duration_s"])
        average_fps = _fps(probe["avg_frame_rate"])
        real_fps = _fps(probe["r_frame_rate"])
        timestamps = probe["frame_timestamps"]
        if (not math.isfinite(duration) or average_fps is None or not math.isfinite(average_fps)
                or real_fps is None or not math.isfinite(real_fps)
                or not isinstance(timestamps, list)
                or any(not math.isfinite(float(value)) for value in timestamps)):
            raise ValueError("probe facts must be finite and complete")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise HuashuMotionError(f"probe facts are incomplete or invalid: {exc}") from exc

    result = check_motion_clip(
        output, probe=probe, expected_sha256=expected_sha256,
        min_duration_s=0.0, max_duration_s=MAX_CLIP_S, reason_prefix="CLIP",
    )
    if result.get("state") != "TECHNICALLY_CHECKED":
        raise HuashuMotionError(result.get("reason", "motion clip check failed"))
    return build_output_record(
        engine=engine,
        spec_sha256=spec_sha256,
        clip_path="project://" + output.relative_to(root).as_posix(),
        clip_sha256=result["sha256"],
        duration=result["duration_s"],
        resolution=f"{result['width']}x{result['height']}",
        fps=result["fps"],
        audio_policy=policy,
        input_asset_hashes=input_asset_hashes,
    )


def make_envelope(record: dict, *, asset_id: str, placement_id: str,
                  receipt_ref: str, derived_from: str,
                  transform_receipt_ref: str):
    """Map a checked clip into the existing shared media index."""
    from contentops.media.media_envelope import MediaAssetEnvelope

    if record.get("schema") != RECORD_SCHEMA:
        raise HuashuMotionError("only a shared Huashu motion record can enter M4.5")
    if record.get("technical_status") != "TECHNICALLY_CHECKED":
        raise HuashuMotionError("only a technically checked record can enter M4.5")
    identity = engine_identity(str(record.get("engine") or ""))
    if (record.get("version") != identity["version"]
            or record.get("commit") != identity["commit"]):
        raise HuashuMotionError("motion record does not match the pinned engine runtime")
    if record.get("generated") is not True or record.get("evidence_capable") is not False:
        raise HuashuMotionError("generated motion must remain support-only and evidence-incapable")
    if record.get("audio_policy") not in {"MUTE", "REPLACE"}:
        raise HuashuMotionError("M4.5 motion assets require an explicit MUTE or REPLACE transform")
    if not derived_from or not transform_receipt_ref:
        raise HuashuMotionError("MUTE/REPLACE must bind the transformed source and transform receipt")
    envelope = MediaAssetEnvelope(
        asset_id=asset_id,
        modality="VIDEO",
        path=record["clip_path"],
        sha256=record["clip_sha256"],
        receipt_ref=receipt_ref,
        fingerprint=record["spec_sha256"],
        asset_kind="GENERATED_VIDEO",
        generated=True,
        evidence_capable=False,
        evidence_use="VISUAL_SUPPORT",
        technical_status="PASS_TECHNICAL",
        human_review="PENDING_FOUNDER_REVIEW",
        production_ready=False,
        audio_policy=record["audio_policy"],
        derived_from=derived_from,
        transform_receipt_ref=transform_receipt_ref,
        placement_id=placement_id,
    )
    envelope.validate_shape()
    return envelope
