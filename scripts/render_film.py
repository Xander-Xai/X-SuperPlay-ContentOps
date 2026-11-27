#!/usr/bin/env python3
"""Render a Huashu Motion film to a continuous H.264 MP4 (formal) or stills animatic.

Two honest render tiers (T09):
- ``--mode formal`` (default): runs ``om check`` then ``om render --workers 1``
  through the pinned local Huashu Motion CLI (Chrome CDP continuous frame-by-frame
  rendering). Using ``--workers 1`` avoids the multi-Chrome Windows CDP pipe
  exhaustion that broke default multi-worker renders in PR #231. Optionally muxes
  narration audio (``--audio``) and writes a verifiable ``render-receipt.json``
  tagged ``CONTINUOUS_VIDEO_CANDIDATE``.
- ``--mode animatic``: stitches ``om still`` PNG snapshots via FFmpeg on their
  true timeline durations. Honestly tagged ``ANIMATIC_PREVIEW_ONLY`` — never
  presented as a formal continuous render.

Both modes always keep ``production_ready: false`` and ``publish_authorized: false``.

Usage:
    python scripts/render_film.py --film <film-dir> --out out.mp4 [--mode formal|animatic] [--fps 24]
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_run  # noqa: E402

DEFAULT_WIDTH, DEFAULT_HEIGHT = 1080, 1920


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_om_cli() -> Optional[Path]:
    env = os.environ.get("CONTENTOPS_HUASHU_MOTION_RUNTIME") or os.environ.get("HUASHU_MOTION_RUNTIME")
    candidates = [Path(env) / "cli" / "om.js"] if env else []
    candidates.extend([
        ROOT / ".runtime" / "huashu-motion" / "cli" / "om.js",
        ROOT.parent / ".runtime" / "huashu-motion" / "cli" / "om.js",
        Path("D:/Projects/X-SuperPlay-ContentOps/.runtime/huashu-motion/cli/om.js"),
    ])
    return next((p.resolve() for p in candidates if p.is_file()), None)


def _probe_video(path: Path) -> Dict[str, Any]:
    proc = hidden_run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path),
    ], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path.name}: {(proc.stderr or '')[-300:]}")
    info = json.loads(proc.stdout or "{}")
    vstream = next((s for s in info.get("streams") or [] if s.get("codec_type") == "video"), None)
    if not vstream:
        raise RuntimeError(f"no video stream in {path.name}")
    astream = next((s for s in info.get("streams") or [] if s.get("codec_type") == "audio"), None)
    return {
        "codec": vstream.get("codec_name"),
        "width": int(vstream.get("width") or 0),
        "height": int(vstream.get("height") or 0),
        "fps": vstream.get("avg_frame_rate"),
        "nb_frames": int(vstream.get("nb_frames") or 0),
        "duration_s": round(float((info.get("format") or {}).get("duration") or 0.0), 3),
        "has_audio": astream is not None,
        "bytes": path.stat().st_size,
    }


def _film_dimensions(film: Path) -> tuple[int, int]:
    text = (film / "index.html").read_text(encoding="utf-8", errors="replace")
    wm = re.search(r'data-width\s*=\s*["\']?(\d+)', text)
    hm = re.search(r'data-height\s*=\s*["\']?(\d+)', text)
    return (int(wm.group(1)) if wm else DEFAULT_WIDTH, int(hm.group(1)) if hm else DEFAULT_HEIGHT)


def _collect(film: Path) -> List[tuple[float, Path]]:
    frames = []
    for path in glob.glob(str(film / "index-*s.png")):
        m = re.search(r"index-([0-9.]+)s\.png", os.path.basename(path))
        if m:
            frames.append((float(m.group(1)), Path(path)))
    frames.sort(key=lambda item: item[0])
    return frames


def _build_animatic(frames: List[tuple[float, Path]], out: Path, fps: int, width: int, height: int) -> None:
    if len(frames) < 2:
        raise SystemExit("need at least two stills; run `om still <film> --at ...` first")
    times = [t for t, _ in frames]
    lines: List[str] = []
    for i, (t, path) in enumerate(frames):
        dur = (times[i + 1] - t) if i + 1 < len(times) else 0.5
        lines.append(f"file '{path.as_posix()}'")
        lines.append(f"duration {dur:.2f}")
    lines.append(f"file '{frames[-1][1].as_posix()}'")
    lst = out.with_suffix(".concat.txt")
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
        "-vf", f"scale={width}:{height}:flags=lanczos,fps={fps},format=yuv420p",
        "-c:v", "libx264", "-crf", "20", "-movflags", "+faststart", str(out),
    ]
    proc = hidden_run(cmd, timeout=300)
    lst.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise SystemExit("ffmpeg failed:\n" + (proc.stderr or "")[-600:])


def _mux_audio(video_path: Path, audio_path: Path, out_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
        "-movflags", "+faststart", str(out_path),
    ]
    proc = hidden_run(cmd, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError("audio mux failed: " + (proc.stderr or "")[-400:])


def render_formal(film: Path, out: Path, *, fps: int = 24, workers: int = 1, audio: Optional[Path] = None) -> Dict[str, Any]:
    om_cli = _find_om_cli()
    if om_cli is None:
        raise RuntimeError("HUASHU_OM_CLI_MISSING: set CONTENTOPS_HUASHU_MOTION_RUNTIME")

    t0 = time.monotonic()
    chk = hidden_run(["node", str(om_cli), "check", str(film), "--json"], cwd=str(om_cli.parents[1]), timeout=300)
    check_ok = chk.returncode == 0

    proc = hidden_run([
        "node", str(om_cli), "render", str(film),
        "--format", "mp4", "--fps", str(fps), "--workers", str(workers), "--silent",
    ], cwd=str(om_cli.parents[1]), timeout=1800)
    elapsed = round(time.monotonic() - t0, 2)
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(f"om render failed (exit {proc.returncode}): {combined[-800:].strip()}")

    matches = re.findall(r"(?:[A-Za-z]:[\\/]|/)[^\r\n]*?\.mp4", proc.stdout or "", re.IGNORECASE)
    rendered = Path(matches[-1].strip().strip('"')) if matches else None
    if rendered is None or not rendered.is_file():
        out_candidates = sorted((film / "out").glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        rendered = out_candidates[0] if out_candidates else None
    if rendered is None or not rendered.is_file():
        raise RuntimeError("om render exited 0 but no MP4 output was found")

    out.parent.mkdir(parents=True, exist_ok=True)
    if audio and audio.is_file():
        _mux_audio(rendered, audio, out)
    else:
        shutil.copy2(rendered, out)

    probe = _probe_video(out)
    return {
        "schema": "contentops.film-render/v1",
        "rendered_at": _now(),
        "mode": "formal",
        "render_tier": "CONTINUOUS_VIDEO_CANDIDATE",
        "engine": "huashu-motion-om-render",
        "workers": workers,
        "om_check_passed": check_ok,
        "elapsed_s": elapsed,
        "output": str(out.name),
        "output_sha256": _sha256(out),
        "technical": probe,
        "production_ready": False,
        "publish_authorized": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Render Huashu film to continuous MP4 or animatic preview")
    parser.add_argument("--film", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--mode", choices=("formal", "animatic"), default="animatic")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--audio", type=Path, default=None)
    parser.add_argument("--receipt", type=Path, default=None)
    args = parser.parse_args(argv)

    film = args.film.resolve()
    if not (film / "index.html").exists():
        raise SystemExit(f"not a film dir (no index.html): {film}")

    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.mode == "formal":
        try:
            receipt = render_formal(film, out, fps=args.fps, workers=args.workers, audio=args.audio)
        except Exception as exc:
            print(json.dumps({"state": "BLOCKED", "mode": "formal", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
    else:
        frames = _collect(film)
        if not frames:
            raise SystemExit(
                f"no index-<t>s.png stills in {film}; sample them first:\n"
                f"  om still {film} --at 0,2,5,8,11"
            )
        w, h = _film_dimensions(film)
        _build_animatic(frames, out, args.fps, w, h)
        probe = _probe_video(out)
        receipt = {
            "schema": "contentops.film-render/v1",
            "rendered_at": _now(),
            "mode": "animatic",
            "render_tier": "ANIMATIC_PREVIEW_ONLY",
            "engine": "om-still-ffmpeg-concat",
            "still_count": len(frames),
            "output": str(out.name),
            "output_sha256": _sha256(out),
            "technical": probe,
            "production_ready": False,
            "publish_authorized": False,
            "note": "Animatic from sampled stills, not a frame-accurate continuous render.",
        }

    receipt_path = args.receipt or out.with_suffix(".render-receipt.json")
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
