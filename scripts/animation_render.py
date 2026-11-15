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
import shutil
import sys
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
    palette_from_dna,
    plan_clip,
    preflight,
    production_gate,
    select_backend,
)
from contentops.media.motion_sample import check_motion_sample  # noqa: E402

REMOTION_ROOT = ROOT / "extensions" / "animation-remotion"
CLI = REMOTION_ROOT / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


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
    }


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


def _composition_props(spec: Dict[str, Any], purpose: str) -> Dict[str, Any]:
    props = dict(spec.get("props") or {})
    palette = props.get("palette") or {}
    if spec["template"] == "rag_flow":
        return {
            "title": props["title"],
            "nodes": list(props["nodes"]),
            "caption": props.get("caption") or "原理示意，不是系统输出",
            "durationSeconds": spec["duration_s"],
            "palette": palette,
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


def render(project: Path, spec_path: Path, *, placement_id: str, asset_id: str,
           account_id: str, purpose: str, has_real_recording: bool) -> int:
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
    props = dict(raw.get("props") or {})
    props.setdefault("palette", palette)
    spec = plan_clip(
        account_id=account_id,
        template=str(raw.get("template") or ""),
        placement_id=placement_id,
        asset_id=asset_id,
        props=props,
        duration_s=float(raw.get("duration_s") or 4),
        backend=backend,
    )
    shot_type = str(raw.get("shot_type") or {
        "rag_flow": "architecture",
        "annotation": "annotation",
        "comparison": "comparison",
    }.get(str(raw.get("template") or ""), str(raw.get("template") or "")))
    decision = select_backend(
        account_id=account_id,
        shot_type=shot_type,
        explicit=backend,
        readiness={backend: preflight(backend, environment_probe(backend)).get("state") == "READY"},
        purpose=purpose,
        input_kind=raw.get("input_kind"),
        has_real_recording=has_real_recording,
    )
    if decision.get("state") != "SELECTED":
        return _emit(_blocked_execution(decision), 1)
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
    props_path.write_text(json.dumps(_composition_props(spec, purpose), ensure_ascii=False),
                          encoding="utf-8")
    command = [
        "node", str(CLI), "render", "src/index.tsx", spec["composition"], str(raw_mp4),
        "--props", str(props_path),
        "--codec", "h264",
        "--pixel-format", "yuv420p",
        "--muted",
        "--overwrite",
    ]
    if browser:
        command.extend(["--browser-executable", browser, "--gl", "angle"])
    proc = hidden_run(command, cwd=str(REMOTION_ROOT), timeout=600)
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
        skill_source="remotion-dev/skills@7e541aa",
        technical_qc="TECHNICALLY_CHECKED",
    )
    receipt["production_gate"] = gate
    receipt_path = project / "receipts" / f"animation-{asset_id}.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
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
    parser.add_argument("--has-real-recording", action="store_true")
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
            has_real_recording=args.has_real_recording,
        )
    except (OSError, ValueError, AnimationError) as exc:
        code = getattr(exc, "code", "RENDER_FAILED")
        return _emit(_blocked_execution({"state": "BLOCKED", "code": code, "detail": str(exc)}), 1)


if __name__ == "__main__":
    raise SystemExit(main())
