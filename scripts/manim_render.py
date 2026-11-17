#!/usr/bin/env python3
"""Render one short silent Manim shot and stop. Easel still composes the episode.

This is the project-level adapter behind the manifest-declared render entry
(``CAPABILITY_RENDER_ENTRY['manim']``). It follows the same governance as the
Remotion clip entry ``scripts/animation_render.py`` and reuses the SAME shared
contracts — it does not build a second cache, receipt, registry or timeline:

* backend selection / gating : ``contentops.media.animation_backend``
* canonical clip receipt     : ``build_receipt`` (contentops.animation-clip-receipt/v1)
* identity + trusted cache   : ``clip_fingerprint`` + sidecar bytes/QC recheck
* M45 manifest + assets      : ``register_generated_clip`` (one inventory, one timeline)
* media QC                   : ``check_motion_sample`` (2–8 s silent CFR clip)

Manim itself is invoked from an ISOLATED venv located through
``runtime/manim.lock.json`` via the official ``python -m manim render`` path.
The venv is never the system interpreter and is never installed into one.

Stdout is exactly one JSON object so M5 / e2e scripts can parse the execution
receipt. A missing/blocked runtime exits 1 with BLOCKED and never substitutes
another engine. Nothing here authorizes production or publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from process_utils import hidden_run  # noqa: E402
from contentops.media.animation_backend import (  # noqa: E402
    MANIM_VERSION,
    AnimationError,
    build_receipt,
    clip_fingerprint,
    palette_from_dna,
    plan_clip,
    preflight,
    production_gate,
    select_backend,
)
from contentops.media.motion_sample import check_motion_sample  # noqa: E402
from contentops.media.quality_gate import MediaManifest  # noqa: E402
from contentops.media.generated_clip import register_generated_clip  # noqa: E402
from contentops.paths import relative_label  # noqa: E402

LOCK_PATH = ROOT / "runtime" / "manim.lock.json"
SCENE_MODULE = ROOT / "scripts" / "manim_scenes.py"
SCENE_CLASS = {
    "math_formula_reveal": "MathFormulaReveal",
    "attention_matrix_flow": "AttentionMatrixFlow",
}
_CACHE_RECEIPT_SCHEMA = "contentops.animation-clip-receipt/v1"
_FINGERPRINT_ENV = "CONTENTOPS_MANIM_PROPS"


# --- small shared helpers (same style as animation_render.py) ---------------

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json_bytes(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # LF bytes: git normalises *.json to LF; CRLF would change the bytes hashed
    # during render and break the trusted cache on a fresh checkout.
    path.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _emit(payload: Dict[str, Any], code: int) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return code


def _blocked_execution(decision: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "execution": {"state": "BLOCKED", "error": decision.get("detail"), "reused": False},
        "decision": decision,
    }


# --- lock + environment probe ------------------------------------------------

def _load_lock() -> Dict[str, Any]:
    if not LOCK_PATH.is_file():
        raise ValueError("MANIM_LOCK_MISSING: runtime/manim.lock.json not found")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock.get("backend") != "manim":
        raise ValueError("MANIM_LOCK_BACKEND: lock does not declare backend manim")
    return lock


def _venv_python(lock: Mapping[str, Any]) -> Path:
    """Resolve the locked isolated interpreter. Never falls back to sys.executable."""
    raw = str(lock.get("venv_python") or "").strip()
    if not raw:
        raise ValueError("MANIM_VENV_MISSING: lock has no venv_python")
    path = Path(raw)
    if not path.is_file():
        raise ValueError(f"MANIM_VENV_MISSING: {raw}")
    return path


def environment_probe() -> Dict[str, Any]:
    """Probe the locked venv by actually importing manim from it.

    No process spawning policy exception: uses the shared hidden_run. A failed
    import is reported as ``manim: False`` with captured stderr, which preflight
    turns into a BLOCKED verdict — never a silent pass and never a substitute.
    """
    try:
        lock = _load_lock()
        python = _venv_python(lock)
    except (OSError, ValueError) as exc:
        return {"manim": False, "node": True, "ffmpeg": _which("ffmpeg"),
                "error": "MANIM_VENV", "detail": str(exc)}
    proc = hidden_run([str(python), "-c", "import manim; print(manim.__version__)"], timeout=60)
    version = (proc.stdout or "").strip().splitlines()[-1] if proc.returncode == 0 else None
    return {
        "manim": proc.returncode == 0 and version == str(lock.get("version")),
        "manim_import": proc.returncode == 0,
        "version": version,
        "pinned_version": lock.get("version"),
        "venv_python": str(python),
        "node": True,  # manim does not need node; preflight ignores it for manim
        "ffmpeg": _which("ffmpeg"),
        "detail": (proc.stderr or "")[-400:],
    }


def _which(name: str) -> bool:
    import shutil
    return shutil.which(name) is not None


def _scene_template_digest(lock: Mapping[str, Any]) -> str:
    """Hash every local input that can change rendered pixels.

    Covers the scene source and the runtime lock. A scene edit or a runtime
    upgrade changes the digest, so a stale MP4 can never be replayed under the
    new identity.
    """
    digest = hashlib.sha256()
    for path in sorted({SCENE_MODULE, LOCK_PATH}):
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(_sha256(path).encode("ascii"))
    return digest.hexdigest()


def _source_digests(spec_file: Path, raw: Mapping[str, Any]) -> List[str]:
    """Collect SHA-256 strings that must invalidate a cached clip.

    The spec file binds the whole prop structure; every 64-hex digest anywhere in
    props (notably definition_source.sha256) is collected recursively so a source
    hidden in a nested object still invalidates the cache.
    """
    def walk(value: Any):
        if isinstance(value, str):
            text = value.strip().lower()
            if len(text) == 64 and all(c in "0123456789abcdef" for c in text):
                yield text
        elif isinstance(value, dict):
            for item in value.values():
                yield from walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from walk(item)

    digests = [_sha256(spec_file)]
    digests.extend(walk(raw.get("props") or {}))
    return list(dict.fromkeys(digests))


# --- ffprobe, normalize, QC, frames -----------------------------------------

def _ffprobe(path: Path) -> Dict[str, Any]:
    proc = hidden_run([
        "ffprobe", "-v", "error", "-show_frames", "-show_streams", "-show_format",
        "-select_streams", "v:0", "-show_entries",
        "stream=codec_type,codec_name,width,height,pix_fmt,avg_frame_rate,r_frame_rate:"
        "format=duration:frame=best_effort_timestamp_time",
        "-of", "json", str(path),
    ], timeout=180)
    if proc.returncode != 0:
        return {"error": "FFPROBE_FAILED", "detail": (proc.stderr or "")[-400:]}
    try:
        raw = json.loads(proc.stdout or "{}")
    except ValueError:
        return {"error": "FFPROBE_FAILED", "detail": "ffprobe returned invalid JSON"}
    streams = raw.get("streams") or []
    video = next((row for row in streams if row.get("codec_type") == "video"), {})
    return {
        "codec_name": video.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "pix_fmt": video.get("pix_fmt"),
        "avg_frame_rate": video.get("avg_frame_rate"),
        "r_frame_rate": video.get("r_frame_rate"),
        "duration_s": float((raw.get("format") or {}).get("duration") or 0.0),
        "has_audio": any(row.get("codec_type") == "audio" for row in streams),
        "frame_timestamps": [row.get("best_effort_timestamp_time") for row in (raw.get("frames") or [])
                             if row.get("media_type", "video") != "audio"],
        "fps": 30,
    }


def _normalize(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    proc = hidden_run([
        "ffmpeg", "-y", "-i", str(source),
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-color_range", "tv", "-r", "30",
        "-vf", "scale=1080:1920:flags=lanczos,format=yuv420p,setsar=1",
        "-movflags", "+faststart", str(target),
    ], timeout=300)
    if proc.returncode != 0 or not target.is_file():
        raise AnimationError("TRANSCODE", (proc.stderr or "ffmpeg failed")[-500:])


def _extract_frames(video: Path, frames_dir: Path) -> List[Dict[str, Any]]:
    """Extract first / middle / last frame as preview evidence."""
    probe = _ffprobe(video)
    duration = float(probe.get("duration_s") or 0.0)
    times = [0.0, round(duration / 2, 3), max(0.0, round(duration - 0.1, 3))]
    frames_dir.mkdir(parents=True, exist_ok=True)
    extracted: List[Dict[str, Any]] = []
    for index, ts in enumerate(times):
        out = frames_dir / f"frame-{index}.png"
        proc = hidden_run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(ts),
             "-i", str(video), "-frames:v", "1", str(out)], timeout=120,
        )
        if proc.returncode == 0 and out.is_file():
            extracted.append({"position": ("first", "middle", "last")[index],
                              "timestamp_s": ts, "path": relative_label(out)})
    return extracted


# --- trusted cache: identity + bytes + QC, never a filename shortcut --------

def _trusted_cache_hit(sidecar: Path, output: Path, fingerprint: str) -> Optional[Dict[str, Any]]:
    if not sidecar.is_file() or not output.is_file():
        return None
    payload = _read_json(sidecar)
    if payload is None or str(payload.get("fingerprint") or "") != fingerprint:
        return None
    recorded = str((payload.get("output") or {}).get("output_sha256")
                   or payload.get("output_sha256") or "").lower()
    if recorded != _sha256(output):
        return None
    probe = _ffprobe(output)
    checked = check_motion_sample(output, probe=probe)
    if checked.get("state") != "TECHNICALLY_CHECKED":
        return None
    return {"sha256": recorded, "receipt": payload, "probe": probe, "qc": checked}


# --- receipt + registration (reuse shared canonical receipt) ----------------

def _build_sidecar_payload(*, project: Path, asset_id: str, fingerprint: str,
                           template: str, account_id: str, placement_id: str,
                           probe: Mapping[str, Any], sha: str, spec_logical: str,
                           raw: Mapping[str, Any], dna: Mapping[str, Any]) -> Dict[str, Any]:
    """The video-receipt schema the shared M45 validator accepts, plus pin facts."""
    digests = _source_digests(project / spec_logical[len("project://"):], raw) if spec_logical.startswith("project://") else []
    return {
        "schema": "contentops.video-receipt/v1",
        "run_id": f"{project.name}-{asset_id}-{fingerprint[:12]}",
        "engine": "manim",
        "backend": "manim",
        "backend_version": MANIM_VERSION,
        "account_id": account_id,
        "placement_id": placement_id,
        "asset_id": asset_id,
        "template": template,
        "fingerprint": fingerprint,
        "template_digest": _scene_template_digest(_load_lock()),
        "dna_digest": hashlib.sha256(json.dumps(
            dna, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest(),
        "source_digests": digests,
        "source_spec": spec_logical,
        "source_rights": "GENERATED_LOCAL_NO_COMMERCIAL_CLEARANCE",
        "output_sha256": sha,
        "output": {"path": f"project://assets/generated/manim/{asset_id}.mp4",
                   "repo_path": f"projects/{project.name}/assets/generated/manim/{asset_id}.mp4",
                   "output_sha256": sha},
        "generated": True,
        "evidence_capable": False,
        "evidence_use": "VISUAL_SUPPORT",
        "counts_as_real_recording": False,
        "source_kind": "vector_animation",
        "technical_qc": {"approved": True, "reasons": [],
                         "probe": {k: v for k, v in probe.items() if k != "frame_timestamps"}},
        "human_review": "PENDING_FOUNDER_REVIEW",
        "production_ready": False,
        "publish_authorized": False,
        "execution_authorized": False,
    }


def _register(*, project: Path, final: Path, asset_id: str, placement_id: str,
              fingerprint: str, sha: str, template: str, sidecar_name: str) -> Dict[str, Any]:
    return register_generated_clip(
        project=project, repo_root=ROOT, asset_id=asset_id, placement_id=placement_id,
        output=final, sha256=sha, fingerprint=fingerprint, backend="manim",
        receipt_name=sidecar_name,
    )


# --- Easel input validation contract ----------------------------------------

def validate_easel_input(project: Path, asset_id: str) -> Dict[str, Any]:
    """Prove the registered clip is a valid Easel input without composing anything.

    Easel consumes the ONE M45 manifest. This check confirms: the manifest parses
    under MANIFEST_SCHEMA, its timeline resolves to exactly one active asset per
    placement, and the registered asset carries only visual-support governance
    flags. It never grants production or publication and never calls Easel.
    """
    manifest_path = project / "work" / "m45" / "manim-media-manifest.json"
    try:
        manifest = MediaManifest.load(manifest_path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"state": "BLOCKED", "code": "EASEL_MANIFEST_UNREADABLE", "detail": str(exc),
                "accepted_by_easel": False, "production_ready": False, "publish_authorized": False}
    envelope = manifest.envelope_for(asset_id)
    if envelope is None:
        return {"state": "BLOCKED", "code": "EASEL_ASSET_MISSING", "detail": asset_id,
                "accepted_by_easel": False, "production_ready": False, "publish_authorized": False}
    try:
        active = manifest.timeline_assets()
    except Exception as exc:  # TimelineError and any structural problem
        return {"state": "BLOCKED", "code": "EASEL_TIMELINE_INVALID", "detail": str(exc),
                "accepted_by_easel": False, "production_ready": False, "publish_authorized": False}
    active_ids = [row.asset_id for row in active]
    violations: List[str] = []
    if envelope.generated is not True:
        violations.append("generated")
    if envelope.evidence_capable is not False:
        violations.append("evidence_capable")
    if str(envelope.evidence_use or "") != "VISUAL_SUPPORT":
        violations.append("evidence_use")
    if envelope.production_ready is not False:
        violations.append("production_ready")
    if envelope.placement_id is None or not envelope.path.startswith("project://"):
        violations.append("path_or_placement")
    if violations:
        return {"state": "BLOCKED", "code": "EASEL_BOUNDARY", "detail": ", ".join(violations),
                "accepted_by_easel": False, "production_ready": False, "publish_authorized": False}
    return {
        "state": "ACCEPTED_AS_VISUAL_SUPPORT", "code": "EASEL_INPUT_OK",
        "detail": "one manifest, one timeline; generated visual support, no claim",
        "accepted_by_easel": True,
        "timeline_active_asset_ids": active_ids,
        "asset_id": asset_id,
        "placement_id": envelope.placement_id,
        "evidence_capable": False,
        "production_ready": False,
        "publish_authorized": False,
    }


# --- main render flow --------------------------------------------------------

def render(project: Path, spec_path: Path, *, placement_id: str, asset_id: str,
           account_id: str, purpose: str) -> int:
    project = project.resolve()
    spec_file = spec_path if spec_path.is_absolute() else project / spec_path
    try:
        spec_file.resolve().relative_to(project)
    except ValueError:
        return _emit(_blocked_execution({"state": "BLOCKED", "code": "PATH",
                                         "detail": "spec escapes the project"}), 1)
    raw = json.loads(spec_file.read_text(encoding="utf-8"))
    template = str(raw.get("template") or "")
    if template not in SCENE_CLASS:
        return _emit(_blocked_execution({"state": "BLOCKED", "code": "UNKNOWN_TEMPLATE",
                                         "detail": f"{template!r} is not a Manim shot"}), 1)
    backend = "manim"

    # Governor: selector + gate use the same contract as every other backend.
    lock = _load_lock()
    probe = environment_probe()
    decision = select_backend(
        account_id=account_id, shot_type=str(raw.get("shot_type") or "math"),
        explicit=backend,
        readiness={backend: preflight(backend, probe).get("state") == "READY"},
        purpose=purpose,
    )
    if decision.get("state") != "SELECTED":
        return _emit(_blocked_execution(decision), 1)

    dna = json.loads((ROOT / "config" / "accounts" / f"{account_id}.json").read_text(encoding="utf-8"))
    palette = palette_from_dna(dna)
    props = dict(raw.get("props") or {})
    # DNA is authoritative: overwrite whatever palette the props carried.
    props["palette"] = palette
    props["font"] = str((dna.get("visual") or {}).get("caption_style", {}).get("font") or "Noto Sans CJK SC")
    if purpose == "test" and not str(props.get("testBanner") or "").strip():
        props["testBanner"] = "测试用途 · 技术样片"
    elif purpose != "test":
        props.pop("testBanner", None)

    try:
        spec = plan_clip(
            account_id=account_id, template=template, placement_id=placement_id,
            asset_id=asset_id, props=props,
            duration_s=float(raw.get("duration_s") or 4), backend=backend, dna=dna,
        )
    except AnimationError as exc:
        return _emit(_blocked_execution({"state": "BLOCKED", "code": exc.code, "detail": exc.detail}), 1)

    gate = production_gate(account_id=account_id, has_real_recording=False, purpose=purpose)
    fingerprint = clip_fingerprint(
        account_id=account_id, template=template, placement_id=placement_id,
        asset_id=asset_id, purpose=purpose, duration_s=float(spec["duration_s"]),
        props=props, dna=dna, source_digests=_source_digests(spec_file, raw),
        version=MANIM_VERSION, backend=backend,
        template_digest=_scene_template_digest(lock),
    )

    final = project / "assets" / "generated" / "manim" / f"{asset_id}.mp4"
    sidecar = final.with_name(final.name + ".receipt.json")
    logical = f"project://assets/generated/manim/{asset_id}.mp4"
    spec_logical = "project://" + spec_file.resolve().relative_to(project).as_posix()

    # Trusted cache: identity + actual bytes + QC. Any DNA/param/source/version
    # change yields a new fingerprint and falls through to a fresh render.
    cached = _trusted_cache_hit(sidecar, final, fingerprint)
    if cached is not None:
        registration = _register(
            project=project, final=final, asset_id=asset_id, placement_id=placement_id,
            fingerprint=fingerprint, sha=cached["sha256"], template=template,
            sidecar_name=sidecar.name,
        )
        easel = validate_easel_input(project, asset_id)
        return _emit({
            "execution": {"state": "REUSED", "reused": True,
                          "adapter_receipt": "project://receipts/" + f"manim-{asset_id}.json"},
            "receipt": "project://receipts/" + f"manim-{asset_id}.json",
            "decision": {"state": "REUSED", "detail": "fingerprint, bytes and sample QC all match",
                         "production_gate": gate.get("code")},
            "registration": registration, "easel_input": easel,
            "sha256": cached["sha256"], "fingerprint": fingerprint,
        }, 0)

    # Fresh render from the isolated venv through the official Manim CLI.
    work = project / "work" / "animation" / "manim" / asset_id
    work.mkdir(parents=True, exist_ok=True)
    media_dir = work / "media"
    props_path = work / f"{asset_id}.props.json"
    _write_json_bytes(props_path, props)
    raw_mp4_hint = work / f"{asset_id}.raw.mp4"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    env[_FINGERPRINT_ENV] = str(props_path)
    python = _venv_python(lock)
    command = [
        str(python), "-m", "manim", "render", "-q", "l", "--fps", "30",
        "--format", "mp4", "-r", "1080,1920", "--media_dir", str(media_dir),
        "-o", f"{asset_id}.raw", str(SCENE_MODULE), SCENE_CLASS[template],
    ]
    try:
        proc = hidden_run(command, cwd=str(ROOT), timeout=900, env=env)
    except Exception as exc:
        return _emit(_blocked_execution({"state": "BLOCKED", "code": "RENDER_TIMEOUT",
                                         "detail": str(exc)}), 1)
    log_path = work / f"{asset_id}.render.log"
    log_path.write_text((proc.stdout or "") + "\n" + (proc.stderr or ""), encoding="utf-8")

    # Manim places the file under media_dir/videos/<module>/<quality>/<name>.mp4.
    candidates = sorted(media_dir.rglob(f"{asset_id}.raw.mp4"))
    if proc.returncode != 0 or not candidates:
        detail = (proc.stderr or proc.stdout or "manim render failed").strip()
        summary = " | ".join(line.strip() for line in detail.splitlines() if line.strip())[:600]
        return _emit(_blocked_execution({"state": "BLOCKED", "code": "RENDER_FAILED",
                                         "detail": summary or "manim render failed"}), 1)
    try:
        _normalize(candidates[0], final)
    except AnimationError as exc:
        return _emit(_blocked_execution({"state": "BLOCKED", "code": exc.code, "detail": exc.detail}), 1)

    probe = _ffprobe(final)
    checked = check_motion_sample(final, probe=probe)
    if checked.get("state") != "TECHNICALLY_CHECKED":
        return _emit(_blocked_execution({"state": "BLOCKED", "code": "SAMPLE_QC",
                                         "detail": checked.get("reason")}), 1)
    frames = _extract_frames(final, project / "receipts" / "frames" / asset_id)
    sha = _sha256(final)

    receipt = build_receipt(
        project_id=project.name, account_id=account_id, placement_id=placement_id,
        asset_id=asset_id, backend=backend, template=template, output_path=logical,
        sha256=sha, probe={**probe, "fps": 30}, purpose=purpose, source_spec=spec_logical,
        version=MANIM_VERSION, skill_source=None, technical_qc="TECHNICALLY_CHECKED",
    )
    receipt["fingerprint"] = fingerprint
    receipt["production_gate"] = gate
    receipt["template_digest"] = _scene_template_digest(lock)
    receipt["preview_frames"] = frames
    receipt["render_command"] = command
    receipt_path = project / "receipts" / f"manim-{asset_id}.json"
    _write_json_bytes(receipt_path, receipt)

    sidecar_payload = _build_sidecar_payload(
        project=project, asset_id=asset_id, fingerprint=fingerprint, template=template,
        account_id=account_id, placement_id=placement_id, probe=probe, sha=sha,
        spec_logical=spec_logical, raw=raw, dna=dna,
    )
    _write_json_bytes(sidecar, sidecar_payload)

    registration = _register(
        project=project, final=final, asset_id=asset_id, placement_id=placement_id,
        fingerprint=fingerprint, sha=sha, template=template, sidecar_name=sidecar.name,
    )
    receipt["asset_registration"] = registration
    easel = validate_easel_input(project, asset_id)
    receipt["easel_input"] = easel
    _write_json_bytes(receipt_path, receipt)

    # ffprobe + SHA + frame report (portable, no host paths in canonical receipt).
    media_report = {
        "schema": "contentops.manim-media-report/v1",
        "asset_id": asset_id, "template": template, "backend": "manim",
        "output": logical, "sha256": sha, "fingerprint": fingerprint,
        "ffprobe": {k: v for k, v in probe.items() if k != "frame_timestamps"},
        "frame_count": len(probe.get("frame_timestamps") or []),
        "preview_frames": frames,
        "motion_sample": {"state": checked.get("state"), "frame_count": checked.get("frame_count")},
        "governance": {"generated": True, "evidence_capable": False,
                       "production_ready": False, "publish_authorized": False},
    }
    _write_json_bytes(project / "receipts" / f"manim-{asset_id}-media.json", media_report)

    return _emit({
        "execution": {"state": "EXECUTED", "reused": False,
                      "adapter_receipt": "project://receipts/" + receipt_path.name},
        "receipt": "project://receipts/" + receipt_path.name,
        "decision": {"state": "RENDERED", "detail": "technically checked; awaiting review",
                     "production_gate": gate.get("code")},
        "registration": registration, "easel_input": easel,
        "sha256": sha, "fingerprint": fingerprint,
    }, 0)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Render one short silent Manim shot")
    parser.add_argument("project", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--render", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--validate-easel", action="store_true")
    parser.add_argument("--backend", default="manim")
    parser.add_argument("--spec", default="")
    parser.add_argument("--placement-id", default="")
    parser.add_argument("--asset-id", default="")
    parser.add_argument("--account", default="")
    parser.add_argument("--purpose", default="production", choices=("production", "test"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    project = args.project

    if args.preflight:
        try:
            probe = environment_probe()
            decision = preflight("manim", probe)
        except (OSError, ValueError) as exc:
            decision = {"state": "BLOCKED", "code": "MANIM_PROBE", "detail": str(exc)}
        return _emit({"execution": {"state": "READY" if decision.get("state") == "READY" else "BLOCKED"},
                      "decision": decision}, 0 if decision.get("state") == "READY" else 1)
    if args.validate_easel:
        result = validate_easel_input(project, args.asset_id)
        return _emit(result, 0 if result.get("accepted_by_easel") else 1)
    if not (args.spec and args.placement_id and args.asset_id and args.account):
        parser.error("--render requires --spec, --placement-id, --asset-id and --account")
    try:
        return render(project, Path(args.spec), placement_id=args.placement_id,
                      asset_id=args.asset_id, account_id=args.account, purpose=args.purpose)
    except (OSError, ValueError, AnimationError) as exc:
        code = getattr(exc, "code", "RENDER_FAILED")
        return _emit(_blocked_execution({"state": "BLOCKED", "code": code, "detail": str(exc)}), 1)


if __name__ == "__main__":
    raise SystemExit(main())
