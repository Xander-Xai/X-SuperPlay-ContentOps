#!/usr/bin/env python3
"""Render the full huashu eras film from the project's measured motion timeline."""

from __future__ import annotations

import argparse
import base64
import functools
import json
import sys
import threading
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingTCPServer

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))

from process_utils import hidden_run  # noqa: E402


class LocalServer(ThreadingTCPServer):
    daemon_threads = True
    request_queue_size = 128


class RouteHandler(SimpleHTTPRequestHandler):
    project: Path
    engine: Path

    def log_message(self, *_: object) -> None:
        return

    def translate_path(self, path: str) -> str:
        relative = path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        route, _, tail = relative.partition("/")
        root = self.engine if route == "engine" else self.project if route == "project" else None
        if root is None:
            return str(self.project / "__not_found__")
        candidate = (root / tail).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            return str(self.project / "__not_found__")
        return str(candidate)


def _timeline(project: Path) -> list[dict[str, object]]:
    segments = json.loads((project / "motion" / "timeline.json").read_text(encoding="utf-8"))["segments"]
    # This is the eras renderer, so a segment declared for another variant
    # (the baseline) is not part of this film.
    return [segment for segment in segments if segment.get("variant", "eras") == "eras"]


def _source(project: Path, clip: str) -> Path:
    """Prefer an eras-only re-render; the baseline clip stays byte-identical."""
    override = project / "work" / "eras" / "clips" / f"{clip}.mp4"
    if override.is_file():
        return override
    return project / "work" / "clips" / f"{clip}.mp4"


def _pad_tail_frames(destination: Path, count: int) -> None:
    missing = [index for index in range(1, count + 1)
               if not (destination / f"{index:04d}.jpg").is_file()]
    if not missing:
        return
    first_missing = missing[0]
    if missing != list(range(first_missing, count + 1)) or first_missing == 1:
        return
    tail = (destination / f"{first_missing - 1:04d}.jpg").read_bytes()
    for index in missing:
        (destination / f"{index:04d}.jpg").write_bytes(tail)


def _extract_frames(project: Path, segments: list[dict[str, object]], fps: int) -> None:
    root = project / "work" / "film-frames"
    for segment in segments:
        clip = str(segment["clip"])
        duration = float(segment["duration"])
        count = round(duration * fps)
        source = _source(project, clip)
        if not source.is_file():
            raise SystemExit(f"missing timeline clip: {source}")
        destination = root / clip
        destination.mkdir(parents=True, exist_ok=True)
        result = hidden_run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-t", str(duration),
            "-vf", f"fps={fps}", "-frames:v", str(count), "-q:v", "3",
            str(destination / "%04d.jpg"),
        ], timeout=300)
        if result.returncode != 0:
            raise SystemExit(f"frame extraction failed for {clip}: {(result.stderr or '')[-500:]}")
        _pad_tail_frames(destination, count)
        missing = [destination / f"{index:04d}.jpg" for index in range(1, count + 1)
                   if not (destination / f"{index:04d}.jpg").is_file()]
        if missing:
            raise SystemExit(f"frame extraction was incomplete for {clip}: {missing[0]}")


def _render(project: Path, engine: Path, out: Path, fps: int) -> float:
    from playwright.sync_api import sync_playwright

    film = project / "motion" / "film" / "index.html"
    if not film.is_file():
        raise SystemExit(f"missing film entrypoint: {film}")
    RouteHandler.project = project
    RouteHandler.engine = engine
    server = LocalServer(("127.0.0.1", 0), RouteHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    frames = project / "work" / "film-render-frames"
    frames.mkdir(parents=True, exist_ok=True)
    port = server.server_address[1]
    try:
        with sync_playwright() as playwright:
            browser = None
            last_error: Exception | None = None
            for options in ({}, {"channel": "chrome"}, {"channel": "msedge"}):
                try:
                    browser = playwright.chromium.launch(
                        args=["--disable-web-security", "--enable-gpu-rasterization", "--ignore-gpu-blocklist"],
                        **options,
                    )
                    break
                except Exception as error:  # noqa: BLE001
                    last_error = error
            if browser is None:
                raise SystemExit(f"no usable Chromium for huashu film render: {last_error}")
            page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
            errors: list[str] = []
            failed: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("requestfailed",
                    lambda request: failed.append(f"{request.url} -> {request.failure}"))
            page.goto(f"http://127.0.0.1:{port}/project/motion/film/index.html?render=1&w=1080&h=1920")
            try:
                page.wait_for_function(
                    "window.__ready === true || !!window.__bootFailed", timeout=120000
                )
            except Exception as error:  # noqa: BLE001
                raise SystemExit(
                    "huashu film never booted: "
                    + ((page.evaluate("window.__bootFailed || null"))
                       or " | ".join(errors + failed) or str(error))
                )
            blocked = page.evaluate("window.__bootFailed || null")
            if blocked:
                boot_errors = page.evaluate("window.__bootErrors || []")
                detail = [str(blocked), *[str(item) for item in boot_errors],
                          *[f"failed: {item}" for item in failed[:5]], *errors[:5]]
                raise SystemExit("huashu film boot failed: " + " | ".join(detail))
            duration = float(page.evaluate("window.__total"))
            for frame in range(round(duration * fps)):
                png = page.evaluate(
                    "async (t) => { await window.prepare(t); window.renderFrame(t); return window.__canvas.toDataURL('image/png').split(',')[1]; }",
                    frame / fps,
                )
                (frames / f"{frame:06d}.png").write_bytes(base64.b64decode(png))
            browser.close()
            if errors:
                raise SystemExit("huashu film page errors: " + " | ".join(errors))
    finally:
        server.shutdown()
        server.server_close()

    out.parent.mkdir(parents=True, exist_ok=True)
    encoded = hidden_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(fps),
        "-i", str(frames / "%06d.png"), "-c:v", "libx264", "-preset", "slow",
        "-crf", "14", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
    ], timeout=600)
    if encoded.returncode != 0 or not out.is_file():
        raise SystemExit(f"huashu film encoding failed: {(encoded.stderr or '')[-500:]}")
    return duration


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("work/huashu-eras.mp4"))
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()

    project = args.project.resolve()
    engine = args.engine.resolve()
    out = args.out if args.out.is_absolute() else project / args.out
    if not (engine / "engine.js").is_file():
        raise SystemExit(f"not a huashu engine directory: {engine}")
    segments = _timeline(project)
    _extract_frames(project, segments, args.fps)
    duration = _render(project, engine, out, args.fps)
    print(json.dumps({"status": "OK", "out": str(out), "duration_s": duration, "fps": args.fps}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
