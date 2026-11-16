#!/usr/bin/env python3
"""Account-scoped adapter for Motion Canvas visual-support clips.

Motion Canvas has NO official headless video CLI. Its FFmpeg exporter receives
frames from the editor over a websocket, so a real MP4 can only be produced by
opening the editor, selecting *Video (FFmpeg)* and clicking Render. This adapter
never pretends otherwise:

* ``--preflight`` / ``--prepare`` write an accurate ``EDITOR_EXPORT_REQUIRED``
  receipt with the exact commands and the raw official evidence;
* ``--import-editor-export`` accepts only a real, human-exported MP4 inside the
  project, normalises it, applies the existing technical gate, and registers it
  through the shared receipt / cache / M45 manifest / QC / asset-registry chain.

Compiling the Vite project proves only that the templates build. It is recorded
as COMPILE_EVIDENCE, never as a render or as ``VERIFIED_HEADLESS``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from process_utils import hidden_run  # noqa: E402
from contentops.media.animation_backend import (  # noqa: E402
    MOTION_CANVAS_VERSION,
    AnimationError,
    build_receipt,
    clip_fingerprint,
    palette_from_dna,
    plan_clip,
    preflight,
    production_gate,
)
from contentops.media.generated_clip import register_generated_clip  # noqa: E402
from contentops.media.motion_sample import check_motion_sample  # noqa: E402
from contentops.paths import resolve_project, trusted_project_root  # noqa: E402

BACKEND = "motion-canvas"
SCHEMA = "contentops.motion-canvas-receipt/v1"
ACCOUNTS = ("x-superplay-1024", "x-superplay-future-intelligence")
TEMPLATES = ("animated_system_graph", "agent_state_machine")
ASSET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
EXTENSION = ROOT / "extensions" / "motion-canvas"
LOCK = ROOT / "runtime" / "motion-canvas.lock.json"

# Raw, checkable evidence gathered 2026-11-16. No claim is made beyond it.
OFFICIAL_EVIDENCE = {
    "verified_at": "2026-11-16",
    "upstream": "https://github.com/motion-canvas/motion-canvas",
    "video_export_docs": "https://motion-canvas.io/docs/rendering/video/",
    "exporters_repo": "https://github.com/motion-canvas/exporters",
    "facts": [
        "@motion-canvas/ffmpeg 3.17.2 is MIT and has no `bin` field in its "
        "package.json: it is a Vite server plugin plus an editor client plugin, "
        "not a CLI.",
        "The official guide says to pick the exporter in the Video Settings "
        "tab; rendering is started from the browser editor websocket.",
        "npm dist-tags.latest for @motion-canvas/core, 2d, ui, vite-plugin and "
        "ffmpeg is 3.17.2 (published 2024-12-14); alpha 3.18.0-alpha.0 is not "
        "pinned.",
        "Third-party pages that show `npx mc render` are not official "
        "documentation and were not treated as a supported command.",
    ],
}
REMEDIATION = [
    "Open the pinned editor with the prepared spec: set MOTION_CANVAS_SPEC_PATH "
    "to the prepared spec path, then `npm --prefix extensions/motion-canvas run dev`.",
    "Open http://localhost:9000, confirm 1080x1920 / 30 FPS / sRGB and the "
    "Video (FFmpeg) exporter in Video Settings (already declared in "
    "extensions/motion-canvas/src/project.meta). Click Render.",
    "Save the exported MP4 inside the project and run "
    "`python scripts/motion_canvas_adapter.py <project> --import-editor-export "
    "--asset-id <id> --exported-mp4 <project-relative path>`.",
    "Only that imported, technically checked MP4 can supply render_evidence to "
    "capability_matrix(); a compile log can never do so.",
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # LF bytes: git normalises *.json to LF, so CRLF would change the bytes
    # hashed by a fresh checkout and break the receipt/MP4 identity.
    path.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("INVALID_JSON_OBJECT:" + str(path))
    return payload


def _project_path(value: str) -> Path:
    project = resolve_project(value)
    root = trusted_project_root(project, ROOT)
    if root is None:
        raise ValueError("PROJECT_OUTSIDE_REPO: expected projects/<slug>") from None
    relative = project.relative_to(root)
    if len(relative.parts) != 1:
        raise ValueError("PROJECT_INVALID: expected one project directory under projects/")
    if not project.is_dir():
        raise ValueError("PROJECT_MISSING: project directory does not exist")
    return project


def _project_account(project: Path) -> str:
    config = project / "project.yaml"
    if not config.is_file():
        raise ValueError("ACCOUNT_SLUG_MISSING: project.yaml is missing")
    match = re.search(r"^account_slug:\s*[\"']?([A-Za-z0-9_-]+)",
                      config.read_text(encoding="utf-8"), re.M)
    if not match:
        raise ValueError("ACCOUNT_SLUG_MISSING: project.yaml declares no account_slug")
    account = match.group(1)
    if account not in ACCOUNTS:
        raise ValueError(f"ACCOUNT_OUT_OF_SCOPE: {account} is not in {', '.join(ACCOUNTS)}")
    return account


def _load_dna(account_id: str) -> Dict[str, Any]:
    path = ROOT / "config" / "accounts" / f"{account_id}.json"
    if not path.is_file():
        raise ValueError(f"UNKNOWN_ACCOUNT: {account_id}")
    return _read_json(path)


def _template_digest() -> str:
    """Hash every local input that can change rendered pixels.

    The spec is deliberately excluded: it is the per-clip parameter and is
    hashed separately into clip_fingerprint(). Dependencies, config and every
    scene source are included so a patch cannot silently replay a stale MP4.
    """
    sources = {
        EXTENSION / "package.json",
        EXTENSION / "package-lock.json",
        EXTENSION / "tsconfig.json",
        EXTENSION / "vite.config.ts",
        EXTENSION / "src" / "project.meta",
    }
    src = EXTENSION / "src"
    if src.is_dir():
        for pattern in ("*.ts", "*.tsx", "*.d.ts"):
            sources.update(src.rglob(pattern))
    digest = hashlib.sha256()
    for path in sorted(sources):
        if path.is_file():
            digest.update(path.relative_to(EXTENSION).as_posix().encode("utf-8"))
            digest.update(_sha(path).encode("ascii"))
    return digest.hexdigest()


def _runtime() -> Dict[str, Any]:
    if not LOCK.is_file():
        raise ValueError("RUNTIME_MISSING: runtime/motion-canvas.lock.json")
    lock = _read_json(LOCK)
    package_lock = EXTENSION / "package-lock.json"
    if not package_lock.is_file():
        raise ValueError("RUNTIME_MISSING: extensions/motion-canvas/package-lock.json")
    resolved = ((_read_json(package_lock).get("packages") or {})
                .get("node_modules/@motion-canvas/core") or {}).get("version")
    if resolved != MOTION_CANVAS_VERSION or lock.get("version") != MOTION_CANVAS_VERSION:
        raise ValueError(
            f"VERSION_MISMATCH: lock={lock.get('version')} "
            f"package-lock={resolved} expected={MOTION_CANVAS_VERSION}")
    modules = EXTENSION / "node_modules" / "@motion-canvas"
    installed: Dict[str, Optional[str]] = {}
    for name in ("core", "2d", "ui", "vite-plugin", "ffmpeg"):
        package_json = modules / name / "package.json"
        installed[name] = (json.loads(package_json.read_text(encoding="utf-8")).get("version")
                           if package_json.is_file() else None)
    return {
        "backend": BACKEND,
        "version": MOTION_CANVAS_VERSION,
        "version_source": lock.get("version_source"),
        "lock_sha256": _sha(LOCK),
        "package_lock_sha256": _sha(package_lock),
        "installed_packages": installed,
        "installed": all(value == MOTION_CANVAS_VERSION for value in installed.values()),
        "export_mode": "EDITOR_EXPORT_REQUIRED",
        "template_digest": _template_digest(),
        "license": lock.get("license"),
    }


def environment_probe() -> Dict[str, Any]:
    """Explicit probe: compile capability is kept separate from render proof."""
    runtime = _runtime()
    return {
        "node": shutil.which("node") is not None,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "node_modules": runtime["installed"],
        "headless_export": False,
        "export_mode": "EDITOR_EXPORT_REQUIRED",
        "pinned_version": MOTION_CANVAS_VERSION,
        "installed_core_version": runtime["installed_packages"].get("core"),
        "compile_capable": runtime["installed"] and shutil.which("node") is not None,
        "render_verified": False,
        "detail": ("Motion Canvas video export is an editor websocket capture; "
                   "there is no official headless CLI"),
    }


def _validate_spec(project: Path, value: str) -> tuple[Path, Dict[str, Any]]:
    candidate = (project / value).resolve()
    try:
        candidate.relative_to(project.resolve())
    except ValueError:
        raise ValueError("SPEC_PATH_ESCAPE: spec must stay inside the project") from None
    if not candidate.is_file():
        raise ValueError(f"SPEC_MISSING:{candidate.relative_to(project).as_posix()}")
    spec = _read_json(candidate)
    template = str(spec.get("template") or "")
    if template not in TEMPLATES:
        raise ValueError(f"SPEC_TEMPLATE: unknown template {template!r}")
    if not (2.0 <= float(spec.get("duration_s") or 0.0) <= 8.0):
        raise ValueError("SPEC_DURATION: motion clips must be 2-8 seconds")
    if (spec.get("width"), spec.get("height"), spec.get("fps")) != (1080, 1920, 30):
        raise ValueError("SPEC_FORMAT: expected 1080x1920 at 30 fps")
    if not str(spec.get("title") or "").strip():
        raise ValueError("SPEC_TITLE: a title is required")
    return candidate, spec


def _fingerprint(project: Path, spec_path: Path, spec: Dict[str, Any], dna: Mapping[str, Any],
                 palette: Mapping[str, str], placement_id: str, asset_id: str,
                 purpose: str, runtime: Mapping[str, Any]) -> str:
    prepared = project / "work" / "motion-canvas" / f"{asset_id}.spec.json"
    return clip_fingerprint(
        account_id=str(dna.get("slug") or ""),
        template=str(spec["template"]),
        placement_id=placement_id,
        asset_id=asset_id,
        purpose=purpose,
        duration_s=float(spec["duration_s"]),
        props={**(spec.get("props") or {}), "palette": palette},
        dna=dna,
        source_digests=[_sha(spec_path), _sha(prepared)] if prepared.is_file() else [_sha(spec_path)],
        version=MOTION_CANVAS_VERSION,
        backend=BACKEND,
        template_digest=str(runtime.get("template_digest") or ""),
    )


def _prepare(project: Path, account: str, spec_arg: str, placement_id: str,
             asset_id: str, purpose: str) -> Dict[str, Any]:
    if not ASSET_ID_RE.fullmatch(asset_id):
        raise ValueError("ASSET_ID_INVALID: use a short filename-safe asset id")
    spec_path, spec = _validate_spec(project, spec_arg)
    dna = _load_dna(account)
    palette = palette_from_dna(dna)
    # `problem` is a literal DNA token; the scene may use it only for a live
    # failure state, never as a decorative brand colour.
    brand_palette = (dna.get("brand") or {}).get("palette") or {}
    problem = str(brand_palette.get("problem") or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", problem):
        palette["problem"] = problem
    props = {**(spec.get("props") or {}), "palette": palette}
    plan = plan_clip(
        account_id=account,
        template=str(spec["template"]),
        placement_id=placement_id,
        asset_id=asset_id,
        props=props,
        duration_s=float(spec["duration_s"]),
        backend=BACKEND,
        dna=dna,
    )
    runtime = _runtime()
    probe = environment_probe()
    decision = preflight(BACKEND, probe)
    if decision.get("state") != "BLOCKED" or decision.get("code") != "NO_HEADLESS_EXPORT":
        raise ValueError("PREFLIGHT_INCONSISTENT: editor export must block a headless render")
    fingerprint = _fingerprint(project, spec_path, spec, dna, palette,
                               placement_id, asset_id, purpose, runtime)
    prepared = project / "work" / "motion-canvas" / f"{asset_id}.spec.json"
    payload = {
        "template": spec["template"],
        "duration_s": float(spec["duration_s"]),
        "width": 1080, "height": 1920, "fps": 30,
        "title": str(props.get("title") or ""),
        "caption": str(props.get("caption") or ""),
        "palette": palette,
        "nodes": props.get("nodes") or [],
        "edges": props.get("edges") or [],
        "steps": props.get("steps") or [],
        "states": props.get("states") or [],
        "transitions": props.get("transitions") or [],
        "state_steps": props.get("state_steps") or [],
    }
    _write_json(prepared, payload)
    output = project / "assets" / "generated" / "motion-canvas" / f"{asset_id}.mp4"
    gate = production_gate(account_id=account, has_real_recording=False, purpose=purpose)
    receipt = {
        "schema": SCHEMA,
        "project": project.relative_to(ROOT).as_posix(),
        "created_at": _now(),
        "state": "BLOCKED",
        "code": "EDITOR_EXPORT_REQUIRED",
        "backend": BACKEND,
        "backend_version": MOTION_CANVAS_VERSION,
        "template": spec["template"],
        "account_id": account,
        "placement_id": placement_id,
        "asset_id": asset_id,
        "purpose": purpose,
        "fingerprint": fingerprint,
        "prepared_spec": f"project://{prepared.relative_to(project).as_posix()}",
        "prepared_spec_sha256": _sha(prepared),
        "expected_output": f"project://{output.relative_to(project).as_posix()}",
        "runtime": runtime,
        "environment_probe": probe,
        "headless_preflight": decision,
        "production_gate": gate,
        "compile_capable": probe["compile_capable"],
        "render_verified": False,
        "official_evidence": OFFICIAL_EVIDENCE,
        "remediation": REMEDIATION,
        "impact": (
            "No real MP4 exists for this prepared job. Do not register a clip, "
            "do not supply render_evidence to the capability matrix, and do not "
            "claim a headless or verified render until an editor-exported MP4 "
            "is imported and technically checked."),
        "generated": True,
        "evidence_capable": False,
        "counts_as_real_recording": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
        "production_ready": False,
        "publish_authorized": False,
        "execution_authorized": False,
    }
    block_path = project / "receipts" / f"motion-canvas-{asset_id}-editor-export-required.json"
    _write_json(block_path, receipt)
    return receipt


def _ffprobe(path: Path) -> Dict[str, Any]:
    proc = hidden_run([
        "ffprobe", "-v", "error", "-show_frames", "-show_streams", "-show_format",
        "-select_streams", "v:0", "-show_entries",
        "stream=codec_type,codec_name,width,height,pix_fmt,avg_frame_rate,r_frame_rate:"
        "format=duration:frame=best_effort_timestamp_time",
        "-of", "json", str(path),
    ], timeout=180)
    if proc.returncode != 0:
        return {"error": "FFPROBE_FAILED", "detail": (proc.stderr or "ffprobe failed")[-400:]}
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
        "frame_timestamps": [row.get("best_effort_timestamp_time")
                             for row in raw.get("frames") or []
                             if row.get("media_type", "video") != "audio"],
    }


def _normalize(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    proc = hidden_run([
        "ffmpeg", "-y", "-i", str(source), "-map", "0:v:0", "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-color_range", "tv",
        "-r", "30", "-vf", "scale=1080:1920:flags=lanczos,format=yuv420p,setsar=1",
        "-movflags", "+faststart", str(target),
    ], timeout=600)
    if proc.returncode != 0 or not target.is_file():
        raise ValueError("NORMALIZE_FAILED: " + (proc.stderr or "ffmpeg failed")[-500:])


def _technical_check(path: Path) -> Dict[str, Any]:
    probe = _ffprobe(path)
    checked = check_motion_sample(path, probe=probe)
    if checked.get("state") != "TECHNICALLY_CHECKED":
        raise ValueError("MOTION_SAMPLE_BLOCKED: " + str(checked.get("reason")))
    decode = hidden_run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
                        timeout=600)
    if decode.returncode != 0 or (decode.stderr or "").strip():
        raise ValueError("FULL_DECODE_FAILED: " + (decode.stderr or "")[-600:])
    black = hidden_run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf",
                        "blackdetect=d=0.033:pix_th=0.04", "-an", "-f", "null", "-"],
                       timeout=600)
    segments = [line.strip() for line in (black.stderr or "").splitlines()
                if "black_start:" in line]
    if black.returncode != 0 or segments:
        raise ValueError("BLACK_FRAME_CHECK_FAILED: " + "; ".join(segments[:6]))
    return {"sample_check": {k: v for k, v in checked.items() if k != "path"},
            "probe": {k: v for k, v in probe.items() if k != "frame_timestamps"},
            "frame_timestamps": probe.get("frame_timestamps") or [],
            "full_decode": "PASS", "black_frame_segments": []}


def _import_editor_export(project: Path, account: str, spec_arg: str, placement_id: str,
                          asset_id: str, purpose: str, exported: str) -> Dict[str, Any]:
    spec_path, spec = _validate_spec(project, spec_arg)
    dna = _load_dna(account)
    palette = palette_from_dna(dna)
    props = {**(spec.get("props") or {}), "palette": palette}
    plan_clip(account_id=account, template=str(spec["template"]),
              placement_id=placement_id, asset_id=asset_id, props=props,
              duration_s=float(spec["duration_s"]), backend=BACKEND, dna=dna)
    runtime = _runtime()
    fingerprint = _fingerprint(project, spec_path, spec, dna, palette,
                               placement_id, asset_id, purpose, runtime)
    source = (project / exported).resolve()
    try:
        source.relative_to(project.resolve())
    except ValueError:
        raise ValueError("EXPORT_PATH_ESCAPE: the MP4 must be inside the project") from None
    if not source.is_file() or source.suffix.lower() != ".mp4":
        raise ValueError("EXPORT_MISSING: expected a project-contained .mp4")
    final = project / "assets" / "generated" / "motion-canvas" / f"{asset_id}.mp4"
    sidecar = final.with_name(final.name + ".receipt.json")
    if (sidecar.is_file() and final.is_file()
            and str(((_read_json(sidecar).get("output") or {}).get("output_sha256")
                     or _read_json(sidecar).get("output_sha256") or "")).lower()
            == _sha(final)
            and str(_read_json(sidecar).get("fingerprint") or "") == fingerprint):
        technical = _technical_check(final)
        registration = register_generated_clip(
            project=project, repo_root=ROOT, asset_id=asset_id,
            placement_id=placement_id, output=final, sha256=_sha(final),
            fingerprint=fingerprint, backend=BACKEND, receipt_name=sidecar.name)
        return {"state": "REUSED", "fingerprint": fingerprint,
                "output_sha256": _sha(final), "technical_qc": technical,
                "registration": registration, "render_verified": True}

    _normalize(source, final)
    technical = _technical_check(final)
    probe = {**technical["probe"], "fps": 30}
    logical = f"project://{final.relative_to(project).as_posix()}"
    source_spec = f"project://{spec_path.relative_to(project).as_posix()}"
    receipt = build_receipt(
        project_id=project.name, account_id=account, placement_id=placement_id,
        asset_id=asset_id, backend=BACKEND, template=str(spec["template"]),
        output_path=logical, sha256=_sha(final), probe=probe, purpose=purpose,
        source_spec=source_spec, version=MOTION_CANVAS_VERSION,
        skill_source=None, technical_qc="TECHNICALLY_CHECKED",
    )
    receipt["fingerprint"] = fingerprint
    receipt["export_mode"] = "EDITOR_EXPORT_REQUIRED"
    receipt["editor_export"] = {
        "path": f"project://{source.relative_to(project).as_posix()}",
        "sha256": _sha(source),
        "note": "human-exported from the Motion Canvas editor websocket",
    }
    receipt["runtime"] = runtime
    receipt["production_gate"] = production_gate(
        account_id=account, has_real_recording=False, purpose=purpose)
    receipt["technical_qc_detail"] = technical
    receipt["export_evidence"] = {
        "verified_at": _now(), "sha256": _sha(final),
        "receipt": f"project://receipts/motion-canvas-{asset_id}.json",
    }
    receipt_path = project / "receipts" / f"motion-canvas-{asset_id}.json"
    _write_json(receipt_path, receipt)
    sidecar_payload = {
        "schema": "contentops.video-receipt/v1",
        "engine": BACKEND, "backend_version": MOTION_CANVAS_VERSION,
        "fingerprint": fingerprint, "template_digest": runtime["template_digest"],
        "output_sha256": _sha(final), "output": {
            "path": logical, "repo_path": final.relative_to(project).as_posix(),
            "output_sha256": _sha(final)},
        "editor_export": receipt["editor_export"],
        "technical_qc": technical["sample_check"],
        "render_verified": True,
        "human_review": "PENDING_FOUNDER_REVIEW",
        "production_ready": False, "publish_authorized": False,
    }
    _write_json(sidecar, sidecar_payload)
    registration = register_generated_clip(
        project=project, repo_root=ROOT, asset_id=asset_id,
        placement_id=placement_id, output=final, sha256=_sha(final),
        fingerprint=fingerprint, backend=BACKEND, receipt_name=sidecar.name)
    receipt["asset_registration"] = registration
    _write_json(receipt_path, receipt)
    return {"state": "EXECUTED", "fingerprint": fingerprint,
            "output_sha256": _sha(final), "technical_qc": technical,
            "registration": registration, "render_verified": True,
            "receipt": f"project://receipts/motion-canvas-{asset_id}.json"}


def render_evidence(project: Path, asset_id: str) -> Optional[Dict[str, Any]]:
    """Capability-matrix evidence: only a real, hash-matching receipt counts."""
    receipt = project / "receipts" / f"motion-canvas-{asset_id}.json"
    if not receipt.is_file():
        return None
    payload = _read_json(receipt)
    output = project / str(payload.get("output_path") or "").removeprefix("project://")
    digest = str(payload.get("sha256") or "").lower()
    if not output.is_file() or not re.fullmatch(r"[0-9a-f]{64}", digest) or _sha(output) != digest:
        return None
    if payload.get("technical_qc") != "TECHNICALLY_CHECKED":
        return None
    return {"verified_at": str(payload.get("created_at") or ""),
            "sha256": digest,
            "receipt": f"project://receipts/motion-canvas-{asset_id}.json"}


def _project_label(project: Optional[Path]) -> Optional[str]:
    if project is None:
        return None
    try:
        return project.relative_to(ROOT).as_posix()
    except ValueError:
        return project.name


def _block_payload(project: Path, exc: Exception, *, asset_id: Optional[str]) -> Dict[str, Any]:
    detail = str(exc)
    code = exc.code if isinstance(exc, AnimationError) else ""
    if not code:
        # Our validation errors carry a stable `CODE: detail` prefix. Keep that
        # code machine-readable instead of collapsing every failure into one.
        head = detail.split(":", 1)[0].strip()
        code = head if re.fullmatch(r"[A-Z][A-Z0-9_]{2,40}", head) else "ADAPTER_BLOCKED"
    payload = {
        "schema": SCHEMA,
        "project": _project_label(project),
        "created_at": _now(),
        "state": "BLOCKED",
        "code": code,
        "detail": detail,
        "asset_id": asset_id,
        "render_verified": False,
        "generated": True,
        "evidence_capable": False,
        "counts_as_real_recording": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
        "production_ready": False,
        "publish_authorized": False,
        "execution_authorized": False,
    }
    return payload


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", help="project directory under projects/<slug>")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true",
                      help="probe the runtime and write the EDITOR_EXPORT_REQUIRED receipt")
    mode.add_argument("--prepare", action="store_true",
                      help="validate a spec and prepare an editor-export job")
    mode.add_argument("--import-editor-export", action="store_true",
                      help="accept a real MP4 exported from the editor")
    mode.add_argument("--probe", action="store_true", help="print the environment probe only")
    parser.add_argument("--spec", help="project-relative JSON clip spec")
    parser.add_argument("--placement-id")
    parser.add_argument("--asset-id")
    parser.add_argument("--exported-mp4", help="project-relative path of the editor-exported MP4")
    parser.add_argument("--purpose", choices=("production", "test"), default="production")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        project = _project_path(args.project)
        if args.probe:
            print(json.dumps(environment_probe(), ensure_ascii=False, indent=2))
            return 0
        if args.preflight:
            account = _project_account(project)
            runtime = _runtime()
            probe = environment_probe()
            decision = preflight(BACKEND, probe)
            payload = {
                "schema": SCHEMA, "project": project.relative_to(ROOT).as_posix(),
                "created_at": _now(), "account_id": account,
                "state": "BLOCKED", "code": "EDITOR_EXPORT_REQUIRED",
                "headless_preflight": decision, "runtime": runtime,
                "environment_probe": probe,
                "compile_capable": probe["compile_capable"],
                "render_verified": False,
                "official_evidence": OFFICIAL_EVIDENCE,
                "remediation": REMEDIATION,
                "generated": True, "evidence_capable": False,
                "production_ready": False, "publish_authorized": False,
                "execution_authorized": False,
            }
            _write_json(project / "receipts" / "motion-canvas-preflight.json", payload)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        if not (args.spec and args.placement_id and args.asset_id):
            parser.error("--prepare/--import-editor-export require --spec, "
                         "--placement-id and --asset-id")
        account = _project_account(project)
        if args.prepare:
            receipt = _prepare(project, account, args.spec, args.placement_id,
                               args.asset_id, args.purpose)
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
            return 1  # an accurate block, never a success exit
        if not args.exported_mp4:
            parser.error("--import-editor-export requires --exported-mp4")
        result = _import_editor_export(project, account, args.spec, args.placement_id,
                                       args.asset_id, args.purpose, args.exported_mp4)
        print(json.dumps({"schema": SCHEMA, "project": project.relative_to(ROOT).as_posix(),
                          "account_id": account, **result,
                          "production_ready": False, "publish_authorized": False},
                         ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, AnimationError) as exc:
        payload = _block_payload(
            (Path(args.project) if args.project else None), exc,
            asset_id=getattr(args, "asset_id", None))
        try:
            project = _project_path(args.project)
            _write_json(project / "receipts" / f"motion-canvas-{args.asset_id or 'adapter'}-block.json",
                        payload)
        except (OSError, ValueError):
            pass
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
