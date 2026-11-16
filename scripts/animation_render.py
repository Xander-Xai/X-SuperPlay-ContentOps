#!/usr/bin/env python3
"""Render one animation clip and stop. Easel still composes the episode.

Stdout is one JSON object. Remotion's own logs stay in the captured child
process, not on this stdout, so M5 can parse the execution receipt.
A missing runtime exits 1 with BLOCKED. It does not call Huashu.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from process_utils import hidden_run  # noqa: E402
from contentops.media.animation_backend import (  # noqa: E402
    REMOTION_VERSION,
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
from contentops.media.generated_clip import register_generated_clip  # noqa: E402
from contentops.paths import resolve_label  # noqa: E402

REMOTION_ROOT = ROOT / "extensions" / "animation-remotion"
CLI = REMOTION_ROOT / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _template_digest() -> str:
    """Hash the composition sources so a template edit invalidates every clip.

    Covers the registration entry, all component sources and the pinned
    dependency manifest. A change to any of them changes the rendered pixels,
    therefore it must change the cache identity.
    """
    sources = sorted(
        [REMOTION_ROOT / "package.json"] + list((REMOTION_ROOT / "src").glob("*.tsx"))
    )
    digest = hashlib.sha256()
    for path in sources:
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(_sha256(path).encode("ascii"))
    return digest.hexdigest()


def _source_digests(spec_file: Path, raw: Dict[str, Any],
                    trusted_recording: Optional[Dict[str, Any]]) -> List[str]:
    """Collect byte identities that must invalidate a cached clip.

    The spec file carries the references; a verified recording carries the
    actual staged bytes; inline SHA-256 values in props bind any registered
    source. Together they ensure a source change cannot replay a stale clip.
    """
    digests = [_sha256(spec_file)]
    if trusted_recording:
        for key in ("validated_sha256", "sha256", "source_document_sha256"):
            value = str(trusted_recording.get(key) or "")
            if len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower()):
                digests.append(value.lower())
    for value in (raw.get("props") or {}).values():
        text = str(value) if not isinstance(value, (dict, list)) else ""
        if len(text) == 64 and all(char in "0123456789abcdef" for char in text.lower()):
            digests.append(text.lower())
    return digests


def _safe_motion_check(checked: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only portable motion-QC facts in receipts; local paths stay local."""
    return {key: value for key, value in checked.items() if key != "path"}


def _which(name: str) -> bool:
    return shutil.which(name) is not None


def _browser() -> Optional[str]:
    override = os.environ.get("CONTENTOPS_REMOTION_BROWSER")
    candidates = [override] if override else []
    candidates.extend([
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def environment_probe(backend: str) -> Dict[str, Any]:
    lock = REMOTION_ROOT / "package-lock.json"
    pinned = None
    if lock.is_file():
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
            pinned = ((data.get("packages") or {}).get("node_modules/remotion") or {}).get("version")
        except (OSError, ValueError):
            pinned = None
    cli_version = None
    if CLI.is_file():
        proc = hidden_run(["node", "-e", "console.log(require('./node_modules/@remotion/cli/package.json').version)"],
                          cwd=str(REMOTION_ROOT), timeout=20)
        if proc.returncode == 0:
            cli_version = (proc.stdout or "").strip()
    core_version = None
    core_package = REMOTION_ROOT / "node_modules" / "remotion" / "package.json"
    if core_package.is_file():
        try:
            core_version = json.loads(core_package.read_text(encoding="utf-8")).get("version")
        except (OSError, ValueError):
            core_version = None
    if backend == "manim":
        proc = hidden_run([sys.executable, "-c", "import manim"], timeout=30)
        return {"manim": proc.returncode == 0, "node": _which("node"), "ffmpeg": _which("ffmpeg"),
                "detail": (proc.stderr or proc.stdout or "")[-400:]}
    if backend == "motion-canvas":
        return {
            "node": _which("node"),
            "ffmpeg": _which("ffmpeg"),
            "headless_export": False,
            "detail": "Motion Canvas video export is an editor websocket capture, not a headless CLI",
        }
    return {
        "node": _which("node"),
        "ffmpeg": _which("ffmpeg"),
        "browser": _browser() is not None,
        "node_modules": CLI.is_file(),
        "pinned_version": pinned or REMOTION_VERSION,
        "installed_cli_version": cli_version,
        "installed_core_version": core_version,
    }


def skill_readiness() -> bool:
    probe = environment_probe("remotion")
    result = preflight("remotion", probe)
    return result.get("state") == "READY"


def _ffprobe(path: Path) -> Dict[str, Any]:
    proc = hidden_run([
        "ffprobe", "-v", "error", "-show_frames", "-show_streams", "-show_format",
        "-show_entries",
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
        "frame_timestamps": [row.get("best_effort_timestamp_time") for row in raw.get("frames") or []
                             if row.get("media_type", "video") != "audio"],
        "fps": 30,
    }


def _load_dna(account_id: str) -> Dict[str, Any]:
    path = ROOT / "config" / "accounts" / f"{account_id}.json"
    if not path.is_file():
        raise AnimationError("UNKNOWN_ACCOUNT", account_id)
    return json.loads(path.read_text(encoding="utf-8"))


def _composition_props(spec: Dict[str, Any], purpose: str, palette: Dict[str, str], *,
                      video: Optional[str] = None, source_in_seconds: float = 0.0) -> Dict[str, Any]:
    props = dict(spec.get("props") or {})
    if spec["template"] == "rag_flow":
        return {
            "title": props["title"],
            "nodes": list(props["nodes"]),
            "caption": props.get("caption") or "原理示意，不是系统输出",
            "durationSeconds": spec["duration_s"],
            "palette": palette,
        }
    if spec["template"] == "recording_mark":
        banner = props.get("test_banner") or ""
        if purpose == "test" and not banner:
            banner = "测试用途 · 非真实录屏案例"
        return {
            "title": props["title"],
            "note": props["note"],
            "durationSeconds": spec["duration_s"],
            "testBanner": banner,
            "video": video or "",
            "sourceInSeconds": source_in_seconds,
            "box": props["box"],
            "palette": palette,
        }
    if spec["template"] == "title_card":
        banner = props.get("test_banner") or ""
        if purpose == "test" and not banner:
            banner = "测试用途 · 技术样片"
        # All colours, including "problem", are resolved from the DNA palette
        # by the caller. A shot spec cannot inject or override a brand colour.
        return {
            "conflict": props["conflict"],
            "stakes": props["stakes"],
            "kicker": props.get("kicker") or "",
            "durationSeconds": spec["duration_s"],
            "testBanner": banner,
            "palette": dict(palette),
        }
    banner = props.get("test_banner") or ""
    if purpose == "test" and not banner:
        banner = "测试用途 · 不是真实录屏证据"
    return {
        "title": props["title"],
        "leftLabel": props["left_label"],
        "rightLabel": props["right_label"],
        "callout": props["callout"],
        "durationSeconds": spec["duration_s"],
        "testBanner": banner,
        "palette": palette,
    }


def _stage_recording_public(project: Path, source: Path, expected_sha256: str, *,
                            crop: Optional[Dict[str, Any]] = None):
    """Stage one verified, project-contained recording in a unique Remotion public dir.

    Only this selected file is exposed to the renderer. The caller must clean up
    the returned TemporaryDirectory after the Remotion process exits.
    """
    root = project.resolve()
    source = Path(source)
    if source.is_symlink():
        raise ValueError("recording source must not be a symlink")
    source = source.resolve(strict=True)
    try:
        source.relative_to(root)
    except ValueError as exc:
        raise ValueError("recording source escapes the authorized project") from exc
    if not source.is_file():
        raise ValueError("recording source is not a regular file")
    digest = str(expected_sha256 or "").lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("recording SHA-256 is invalid")
    if _sha256(source) != digest:
        raise ValueError("recording hash does not match its registration")

    parent = root / "work" / "animation"
    try:
        parent.resolve().relative_to(root)
    except ValueError as exc:
        raise ValueError("Remotion public directory parent escapes the project") from exc
    parent.mkdir(parents=True, exist_ok=True)
    resolved_parent = parent.resolve()
    try:
        resolved_parent.relative_to(root)
    except ValueError as exc:
        raise ValueError("Remotion public directory parent escapes the project") from exc
    temporary = tempfile.TemporaryDirectory(prefix="remotion-public-", dir=str(resolved_parent))
    public_dir = Path(temporary.name).resolve()
    try:
        public_dir.relative_to(resolved_parent)
        suffix = ".mp4" if crop is not None else source.suffix.lower()
        if suffix not in {".mp4", ".mov", ".webm", ".mkv"}:
            raise ValueError("recording container is not supported for public staging")
        relative = f"recordings/{digest}{suffix}"
        destination = public_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if crop is None:
            shutil.copyfile(source, destination)
        else:
            if not isinstance(crop, dict):
                raise ValueError("recording crop must be a verified rectangle")
            values = [crop.get(key) for key in ("x", "y", "width", "height")]
            if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
                raise ValueError("recording crop coordinates must be integers")
            x, y, width, height = values
            if min(x, y) < 0 or min(width, height) <= 0:
                raise ValueError("recording crop rectangle is invalid")
            video_filter = (
                f"crop={width}:{height}:{x}:{y},"
                "scale=1080:1920:force_original_aspect_ratio=decrease,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
            )
            proc = hidden_run([
                "ffmpeg", "-y", "-i", str(source), "-map", "0:v:0", "-an",
                "-vf", video_filter, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(destination),
            ], timeout=300)
            if proc.returncode != 0 or not destination.is_file():
                raise ValueError("failed to create the cropped private recording copy")
        staged_digest = _sha256(destination)
        if crop is None and staged_digest != digest:
            raise ValueError("staged recording hash changed during copy")
        if crop is not None and staged_digest == digest:
            raise ValueError("crop transform produced a byte-identical input copy")
        if not destination.is_file() or destination.stat().st_size == 0:
            raise ValueError("staged recording is missing or empty")
        return temporary, public_dir, relative
    except Exception:
        temporary.cleanup()
        raise


def _registered_recording(project: Path, asset_id: str) -> Optional[Dict[str, Any]]:
    manifest = json.loads((project / "sources" / "assets.json").read_text(encoding="utf-8"))
    asset = next((row for row in manifest.get("assets", []) if row.get("id") == asset_id), None)
    if not asset or str(asset.get("type", "")).lower() != "recording":
        return None
    if asset.get("evidence_capable") is not True or asset.get("origin") != "SELF_CAPTURED":
        return None
    if asset.get("permission") != "SELF_CAPTURED_CROPPED" or not isinstance(asset.get("crop"), dict):
        return None
    source_ref = str(asset.get("source_ref") or "")
    if not source_ref or source_ref.startswith("project://"):
        return None
    refs_path = project / "sources" / "source-refs.json"
    if not refs_path.is_file():
        return None
    refs = json.loads(refs_path.read_text(encoding="utf-8"))
    ref = next((row for row in refs.get("refs", []) if str(row.get("id")) == source_ref), None)
    if not ref or str(ref.get("permission") or "").upper() not in {
        "OWNED", "CREATED_BY_OWNER", "USER_PROVIDED_LOCAL",
    }:
        return None
    return asset


def _trusted_recording(project: Path, asset_id: str) -> Optional[Dict[str, Any]]:
    asset = _registered_recording(project, asset_id)
    if not asset:
        return None
    from contentops.paths import resolve_label
    from contentops.media.recording_intake import RecordingRequest, intake

    path_value = str(asset.get("repo_path") or "")
    path = resolve_label(path_value, ROOT)
    if not path.is_file():
        return None
    digest = _sha256(path)
    if digest != str(asset.get("sha256") or "").lower():
        return None
    try:
        path.resolve().relative_to(project.resolve())
    except ValueError:
        return None
    result = intake(
        project,
        RecordingRequest(
            path=path,
            source_ref=str(asset.get("source_ref")),
            crop=asset.get("crop"),
            claim_ids=tuple(str(value) for value in asset.get("claim_ids") or []),
        ),
        repo_root=ROOT,
        apply=False,
        write=False,
    )
    registered_hash = str(asset.get("sha256") or "").lower()
    files = result.get("files") or []
    if (result.get("verdict") != "ACCEPTED" or
            (result.get("account") or {}).get("slug") != "x-superplay-1024" or
            not registered_hash or not any(row.get("sha256") == registered_hash for row in files)):
        return None
    return {**asset, "resolved_path": str(path), "validated_sha256": registered_hash}


def _has_other_recording(project: Path, exclude: str) -> bool:
    try:
        manifest = json.loads((project / "sources" / "assets.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    for row in manifest.get("assets", []):
        if row.get("id") == exclude or str(row.get("type", "")).lower() != "recording":
            continue
        if _trusted_recording(project, str(row.get("id") or "")):
            return True
    return False


def _has_test_plate(project: Path, exclude: str) -> bool:
    try:
        manifest = json.loads((project / "sources" / "assets.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    for row in manifest.get("assets", []):
        if row.get("id") != exclude:
            continue
        if row.get("test_only") is not True or row.get("evidence_capable") is not False:
            continue
        if str(row.get("type") or "").lower() not in {"recording", "video", "generated_video"}:
            continue
        path = resolve_label(str(row.get("repo_path") or ""), ROOT)
        if path.is_file() and _sha256(path) == str(row.get("sha256") or "").lower():
            return True
    return False


def _normalize(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    proc = hidden_run([
        "ffmpeg", "-y", "-i", str(source),
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-color_range", "tv",
        "-r", "30", "-vf", "scale=1080:1920:flags=lanczos,format=yuv420p,setsar=1",
        "-movflags", "+faststart",
        str(target),
    ], timeout=300)
    if proc.returncode != 0 or not target.is_file():
        raise AnimationError("TRANSCODE", (proc.stderr or "ffmpeg failed")[-500:])


def _emit(payload: Dict[str, Any], code: int) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return code


def _blocked_execution(decision: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "execution": {"state": "BLOCKED", "error": decision.get("detail"), "reused": False},
        "decision": decision,
    }


def _trusted_cache_hit(sidecar: Path, output: Path, fingerprint: str,
                       asset_id: str) -> Optional[Dict[str, Any]]:
    """Return reusable receipt data only if identity, bytes and QC all still hold.

    Checks, in order: sidecar parses; fingerprint matches the current job;
    the sidecar's recorded output hash matches the file's actual bytes; the
    output is a regular file; and the sample still passes the motion gate.
    Any failure means MISS and the caller renders normally. No filename-based
    shortcut is permitted.
    """
    if not sidecar.is_file() or not output.is_file():
        return None
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if str(payload.get("fingerprint") or "") != fingerprint:
        return None
    recorded = str(payload.get("output_sha256") or "").lower()
    recorded_hash = str((payload.get("output") or {}).get("output_sha256") or recorded).lower()
    actual = _sha256(output)
    if recorded_hash != actual:
        return None
    try:
        probe = _ffprobe(output)
        checked = check_motion_sample(output, probe=probe)
    except (OSError, ValueError):
        return None
    if checked.get("state") != "TECHNICALLY_CHECKED":
        return None
    return {
        "sha256": actual,
        "receipt_name": f"animation-{asset_id}.json",
        "receipt": payload,
    }


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
    backend = str(raw.get("backend") or "remotion")
    dna = _load_dna(account_id)
    palette = palette_from_dna(dna)
    # The conflict colour is a declared DNA brand token, never a per-shot prop.
    # Copy it from brand.palette into the resolved palette so the composition
    # receives only DNA-authoritative colours.
    brand_palette = (dna.get("brand") or {}).get("palette") or {}
    problem = str(brand_palette.get("problem") or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", problem):
        palette["problem"] = problem
    template = str(raw.get("template") or "")
    trusted_recording = None
    recording_id = str((raw.get("props") or {}).get("recording_asset_id") or "")
    if template == "recording_mark":
        if account_id != "x-superplay-1024":
            return _emit(_blocked_execution({"state": "BLOCKED", "code": "ACCOUNT_TEMPLATE_FORBIDDEN",
                                             "detail": "recording_mark is only available to x-superplay-1024"}), 1)
        if purpose == "production":
            trusted_recording = _trusted_recording(project, recording_id)
        elif purpose == "test":
            manifest = json.loads((project / "sources" / "assets.json").read_text(encoding="utf-8"))
            asset = next((row for row in manifest.get("assets", []) if row.get("id") == recording_id), None)
            if asset and asset.get("test_only") is True and asset.get("evidence_capable") is False:
                path = resolve_label(str(asset.get("repo_path") or ""), ROOT)
                if path.is_file() and _sha256(path) == str(asset.get("sha256") or "").lower():
                    trusted_recording = {**asset, "test_plate": True, "resolved_path": str(path)}
        if not trusted_recording:
            code = "TEST_PLATE_NOT_REGISTERED" if purpose == "test" else "RECORDING_NOT_VERIFIED"
            return _emit(_blocked_execution({"state": "BLOCKED", "code": code,
                                             "detail": "recording_mark needs a verified recording or explicitly registered TEST_ONLY plate"}), 1)
    source_asset_id = recording_id
    has_real_recording = _has_other_recording(project, source_asset_id) or trusted_recording is not None
    props = dict(raw.get("props") or {})
    props["palette"] = palette
    if template == "recording_mark" and trusted_recording and trusted_recording.get("test_plate"):
        props["test_banner"] = "测试用途 · 非真实录屏案例"
    if template in ("recording_mark", "annotation", "comparison") and purpose == "production" and not has_real_recording:
        return _emit(_blocked_execution({"state": "BLOCKED", "code": "MISSING_REAL_RECORDING",
                                         "detail": "1024 production needs an intake-verified cropped recording and source evidence"}), 1)
    spec = plan_clip(
        account_id=account_id,
        template=template,
        placement_id=placement_id,
        asset_id=asset_id,
        props={**props, "palette": palette},
        duration_s=float(raw.get("duration_s") or 4),
        backend=backend,
    )
    shot_type = str(raw.get("shot_type") or {
        "rag_flow": "architecture",
        "annotation": "annotation",
        "comparison": "comparison",
        "recording_mark": "recording_mark",
        "title_card": "title_card",
    }.get(str(raw.get("template") or ""), str(raw.get("template") or "")))
    readiness = environment_probe(backend)
    decision = select_backend(
        account_id=account_id,
        shot_type=shot_type,
        explicit=backend,
        readiness={backend: preflight(backend, readiness).get("state") == "READY"},
        purpose=purpose,
        input_kind=raw.get("input_kind"),
        has_real_recording=has_real_recording,
    )
    if decision.get("state") != "SELECTED":
        return _emit(_blocked_execution(decision), 1)
    if backend == "remotion" and not skill_readiness():
        return _emit(_blocked_execution({
            "state": "BLOCKED", "code": "RUNTIME_NOT_READY",
            "detail": "installed Remotion runtime version does not match its lock",
        }), 1)
    gate = production_gate(account_id=account_id, has_real_recording=has_real_recording,
                           purpose=purpose)
    if purpose == "production" and gate.get("state") == "BLOCKED":
        return _emit(_blocked_execution(gate), 1)
    if backend != "remotion":
        blocked = preflight(backend, environment_probe(backend))
        return _emit(_blocked_execution(blocked), 1)

    browser = _browser()
    work = project / "work" / "animation"
    work.mkdir(parents=True, exist_ok=True)
    props_path = work / f"{asset_id}.props.json"
    raw_mp4 = work / f"{asset_id}.raw.mp4"
    final = project / "assets" / "generated" / "remotion" / f"{asset_id}.mp4"
    sidecar = final.with_name(final.name + ".receipt.json")
    fingerprint = clip_fingerprint(
        account_id=account_id,
        template=template,
        placement_id=placement_id,
        asset_id=asset_id,
        purpose=purpose,
        duration_s=float(spec["duration_s"]),
        props={**props, "palette": palette},
        dna=dna,
        source_digests=_source_digests(spec_file, raw, trusted_recording),
        version=REMOTION_VERSION,
        backend=backend,
        template_digest=_template_digest(),
    )
    # Trusted cache: replay only when the full identity matches AND the bytes
    # on disk still hash to the recorded value AND the sample still passes QC.
    # A filename match alone is never enough; any DNA/params/source/version
    # change produces a different fingerprint and falls through to a render.
    cached = _trusted_cache_hit(sidecar, final, fingerprint, asset_id)
    if cached is not None:
        return _emit({
            "execution": {
                "state": "REUSED",
                "reused": True,
                "adapter_receipt": "project://receipts/" + cached["receipt_name"],
            },
            "receipt": "project://receipts/" + cached["receipt_name"],
            "decision": {"state": "REUSED", "detail": "fingerprint, bytes and sample QC match",
                         "production_gate": gate.get("code")},
            "sha256": cached["sha256"],
            "fingerprint": fingerprint,
        }, 0)
    public_temp = None
    public_dir = None
    public_video = None
    source_in_seconds = float(raw.get("source_in_seconds") or 0.0)
    if template == "recording_mark" and trusted_recording:
        try:
            public_temp, public_dir, public_video = _stage_recording_public(
                project, Path(trusted_recording["resolved_path"]),
                str(trusted_recording.get("sha256") or ""),
                crop=None if trusted_recording.get("test_plate") else trusted_recording.get("crop"),
            )
        except (OSError, ValueError) as exc:
            return _emit(_blocked_execution({"state": "BLOCKED", "code": "RECORDING_PATH",
                                             "detail": str(exc)}), 1)
    prop_payload = _composition_props(
        spec, purpose, palette, video=public_video, source_in_seconds=source_in_seconds,
    )
    props_path.write_text(json.dumps(prop_payload, ensure_ascii=False), encoding="utf-8")
    command = [
        "node", str(CLI), "render", "src/index.tsx", spec["composition"], str(raw_mp4),
        "--props", str(props_path),
        "--codec", "h264",
        "--pixel-format", "yuv420p",
        "--muted",
        "--overwrite",
    ]
    if public_dir is not None:
        command.extend(["--public-dir", str(public_dir)])
    if browser:
        command.extend(["--browser-executable", browser, "--gl", "angle"])
    try:
        proc = hidden_run(command, cwd=str(REMOTION_ROOT), timeout=600)
    finally:
        if public_temp is not None:
            public_temp.cleanup()
    log_path = work / f"{asset_id}.render.log"
    log_path.write_text((proc.stdout or "") + "\n" + (proc.stderr or ""), encoding="utf-8")
    if proc.returncode != 0 or not raw_mp4.is_file():
        detail = (proc.stderr or proc.stdout or "remotion render failed")
        head = detail.strip().splitlines()
        summary = " | ".join(line.strip() for line in head if line.strip())[:500]
        return _emit(_blocked_execution({
            "state": "BLOCKED",
            "code": "RENDER_FAILED",
            "detail": summary or "remotion render failed",
        }), 1)
    _normalize(raw_mp4, final)
    probe = _ffprobe(final)
    checked = check_motion_sample(final, probe=probe)
    if checked.get("state") != "TECHNICALLY_CHECKED":
        return _emit(_blocked_execution({
            "state": "BLOCKED",
            "code": "SAMPLE_QC",
            "detail": checked.get("reason"),
        }), 1)
    logical = f"project://assets/generated/remotion/{asset_id}.mp4"
    spec_logical = "project://" + spec_file.resolve().relative_to(project).as_posix()
    receipt = build_receipt(
        project_id=project.name,
        account_id=account_id,
        placement_id=placement_id,
        asset_id=asset_id,
        backend="remotion",
        template=spec["template"],
        output_path=logical,
        sha256=_sha256(final),
        probe={**probe, "fps": 30},
        purpose=purpose,
        source_spec=spec_logical,
        version=REMOTION_VERSION,
        skill_source=None,
        technical_qc="TECHNICALLY_CHECKED",
    )
    receipt["production_gate"] = gate
    receipt_path = project / "receipts" / f"animation-{asset_id}.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source_digests = _source_digests(spec_file, raw, trusted_recording)
    sidecar_payload = {
        "schema": "contentops.video-receipt/v1",
        "run_id": f"{project.name}-{asset_id}-{fingerprint[:12]}",
        "engine": "remotion",
        "backend_version": REMOTION_VERSION,
        "account_id": account_id,
        "placement_id": placement_id,
        "asset_id": asset_id,
        "template": template,
        "fingerprint": fingerprint,
        "template_digest": _template_digest(),
        "dna_digest": hashlib.sha256(json.dumps(dna, ensure_ascii=False, sort_keys=True,
                                                separators=(",", ":")).encode("utf-8")).hexdigest(),
        "source_digests": source_digests,
        "source_rights": "GENERATED_LOCAL_NO_COMMERCIAL_CLEARANCE",
        "output_sha256": receipt["sha256"],
        "output": {"path": logical, "repo_path": final.relative_to(project).as_posix(),
                   "output_sha256": receipt["sha256"]},
        "generated": True,
        "evidence_capable": False,
        "technical_qc": {"approved": True, "reasons": [], "motion_sample": _safe_motion_check(checked),
                          "probe": {key: value for key, value in probe.items()
                                    if key != "frame_timestamps"}},
        "human_review": "PENDING_FOUNDER_REVIEW",
        "production_ready": False,
        "publish_authorized": False,
    }
    sidecar.write_text(json.dumps(sidecar_payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    registration = register_generated_clip(
        project=project,
        repo_root=ROOT,
        asset_id=asset_id,
        placement_id=placement_id,
        output=final,
        sha256=receipt["sha256"],
        fingerprint=fingerprint,
        backend="remotion",
        receipt_name=sidecar.name,
    )
    receipt["asset_registration"] = registration
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _emit({
        "execution": {
            "state": "EXECUTED",
            "reused": False,
            "adapter_receipt": "project://receipts/" + receipt_path.name,
        },
        "receipt": "project://receipts/" + receipt_path.name,
        "decision": {"state": "RENDERED", "detail": checked.get("reason") or "technically checked",
                     "production_gate": gate.get("code")},
        "sha256": receipt["sha256"],
        "fingerprint": fingerprint,
    }, 0)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Render one animation clip")
    parser.add_argument("project", type=Path)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--backend", default="remotion")
    parser.add_argument("--spec", default="")
    parser.add_argument("--placement-id", default="")
    parser.add_argument("--asset-id", default="")
    parser.add_argument("--account", default="")
    parser.add_argument("--purpose", default="production", choices=("production", "test"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.preflight or not args.render:
        decision = preflight(args.backend, environment_probe(args.backend))
        return _emit({"execution": {"state": "READY" if decision.get("state") == "READY" else "BLOCKED",
                                    "error": decision.get("detail")},
                      "decision": decision}, 0 if decision.get("state") == "READY" else 1)
    try:
        return render(
            args.project, Path(args.spec),
            placement_id=args.placement_id, asset_id=args.asset_id,
            account_id=args.account, purpose=args.purpose,
        )
    except (OSError, ValueError, AnimationError) as exc:
        code = getattr(exc, "code", "RENDER_FAILED")
        return _emit(_blocked_execution({"state": "BLOCKED", "code": code, "detail": str(exc)}), 1)


if __name__ == "__main__":
    raise SystemExit(main())
