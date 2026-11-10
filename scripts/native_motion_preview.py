#!/usr/bin/env python3
"""Render original, silent X-SuperPlay motion support without GSAP.

This is a project-owned local clip producer, not a Huashu runtime and not a
compositor. Its output is generated visual support, never evidence or a claim
that an operation ran. Rendering is limited to the two explicitly named project
slugs and their account profiles.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import DEVNULL, PIPE, hidden_popen, hidden_run, python_executable  # noqa: E402
import skill_route  # noqa: E402

SCHEMA = "contentops.native-motion-preview/v1"
CAPABILITY_ID = "contentops-native-motion"
VERSION = "0.1.0"
WIDTH, HEIGHT, FPS = 1080, 1920, 30
PALETTE = {
    "base": "#0F1117",
    "accent": "#38BDF8",
    "ink": "#F5F7FA",
    "muted": "#8B95A5",
    "surface": "#161A22",
    "line": "#344151",
    "warn": "#F07167",
    "ok": "#58D6A0",
}

PROJECT_PROFILES: Dict[str, Dict[str, Any]] = {
    "x-superplay-future-intelligence-motion-20261107": {
        "account": "x-superplay-future-intelligence",
        "duration_s": 8.0,
        "role": "EXPLANATORY_SUPPORT_NOT_EVIDENCE",
        "claims_current_result": False,
        "story_beats": [
            "found_but_not_authorized",
            "request_grant_gate_runner",
            "blocked_vs_theoretical_authorized_executed",
        ],
        "visual_purpose": "Mechanism illustration for this repository's Huashu adapter; no execution result is depicted.",
    },
    "x-superplay-1024-motion-20261107": {
        "account": "x-superplay-1024",
        "duration_s": 6.0,
        "role": "AUXILIARY_EXPLANATION_NOT_REAL_CAPTURE",
        "claims_current_result": False,
        "claims_current_resolver_result": False,
        "story_beats": [
            "pinned_local_source",
            "offline_resolver_boundary",
            "upstream_byte_compare_not_run",
        ],
        "visual_purpose": "Auxiliary process illustration only; no terminal output, current resolver status or real product capture is synthesized.",
    },
}


class PreviewError(RuntimeError):
    """An unsafe profile, unsupported dependency, or failed local render."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def profile_for_project(project_slug: str) -> Dict[str, Any]:
    """Return an allowlisted project profile after verifying its account DNA key."""
    if project_slug not in PROJECT_PROFILES:
        raise PreviewError(f"unsupported project slug: {project_slug!r}")
    profile = dict(PROJECT_PROFILES[project_slug])
    project_root = ROOT / "projects" / project_slug
    project_yaml = project_root / "project.yaml"
    if not project_yaml.is_file():
        raise PreviewError(f"project metadata is missing: {project_yaml}")
    match = re.search(r"(?m)^account_slug:\s*['\"]?([a-z0-9-]+)['\"]?\s*$",
                      project_yaml.read_text(encoding="utf-8"))
    if not match or match.group(1) != profile["account"]:
        raise PreviewError("project account_slug does not match its allowlisted profile")
    profile["project"] = project_slug
    return profile


def resolve_project_route(project_slug: str) -> Dict[str, Any]:
    """Resolve the actual registry entry; resolution is never an execution grant."""
    profile = profile_for_project(project_slug)
    verdict = skill_route.resolve_capability(
        CAPABILITY_ID,
        account=profile["account"],
        pipeline="M5",
        stage="motion",
    )
    return {
        "capability_id": CAPABILITY_ID,
        "verdict": verdict.get("verdict"),
        "reason": verdict.get("reason"),
        "detail": verdict.get("detail"),
        "execution_authorized": False,
        "contentops_grant_present": False,
        "user_task_scope_authorized": True,
        "authorization_basis": "P6 user work order: free local original animation and internal preview only",
        "account": profile["account"],
        "project": project_slug,
        "pipeline": "M5",
        "stage": "motion",
        "capability": verdict.get("capability"),
        "runtime_dependencies": (verdict.get("capability") or {}).get("source", {}).get("dependencies", []),
        "discovery": verdict.get("discovery"),
        "runtime": verdict.get("runtime"),
    }


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path(r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold
             else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    )
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def _center(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
            font: ImageFont.ImageFont, fill: str) -> None:
    draw.text(xy, text, font=font, fill=fill, anchor="mm")


def _card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], *,
          outline: str = PALETTE["line"], fill: str = PALETTE["surface"],
          radius: int = 24, width: int = 3) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _future_frame(draw: ImageDraw.ImageDraw, t: float, duration: float) -> None:
    # One tall continuous diagram: the highlighted token progresses from tool
    # discovery, through the gate chain, to three explicitly labelled states.
    _center(draw, (WIDTH // 2, 78), "运行时可信，为什么 Agent 仍然不能执行？",
            _font(43, bold=True), PALETTE["ink"])
    _center(draw, (WIDTH // 2, 145), "机制示意 · 非执行记录 · 适用范围：本仓库 Huashu 适配器",
            _font(24), PALETTE["accent"])

    draw.line((64, 196, WIDTH - 64, 196), fill=PALETTE["line"], width=2)
    _center(draw, (WIDTH // 2, 244), "01  找到工具 ≠ 获得执行权",
            _font(29, bold=True), PALETTE["ink"])
    y1, y2 = 315, 495
    _card(draw, (72, y1, 330, y2), outline=PALETTE["accent"])
    _center(draw, (201, 370), "Agent", _font(35, bold=True), PALETTE["ink"])
    _center(draw, (201, 430), "发起查找", _font(24), PALETTE["muted"])
    _card(draw, (412, y1, 668, y2), outline=PALETTE["accent"])
    _center(draw, (540, 370), "Tool", _font(35, bold=True), PALETTE["ink"])
    _center(draw, (540, 430), "已定位", _font(24), PALETTE["accent"])
    _card(draw, (750, y1, 1008, y2), outline=PALETTE["warn"])
    _center(draw, (879, 370), "Grant Gate", _font(31, bold=True), PALETTE["ink"])
    _center(draw, (879, 430), "授权未通过", _font(23), PALETTE["warn"])
    draw.line((330, 405, 750, 405), fill=PALETTE["line"], width=5)
    progress = max(0.0, min(1.0, t / 2.25))
    dot_x = int(330 + 330 * progress)  # deliberately stops before the gate
    draw.ellipse((dot_x - 12, 393, dot_x + 12, 417), fill=PALETTE["accent"])
    draw.line((736, 387, 760, 405, 736, 423), fill=PALETTE["warn"], width=5)

    _center(draw, (WIDTH // 2, 580), "02  Request → Grant → Gate → Runner",
            _font(29, bold=True), PALETTE["ink"])
    labels = ["Request", "Grant", "Gate", "Runner · 示意"]
    node_top, node_gap, node_height = 625, 104, 76
    flow_p = max(0.0, min(1.0, (t - 2.05) / 3.35))
    for index, label in enumerate(labels):
        top = node_top + index * node_gap
        active = flow_p >= index / 4.0 and flow_p < (index + 1) / 4.0 + 0.25
        color = PALETTE["accent"] if active else PALETTE["line"]
        _card(draw, (270, top, 810, top + node_height), outline=color, width=4 if active else 2)
        _center(draw, (540, top + node_height // 2), label,
                _font(27, bold=active), PALETTE["ink"] if active else PALETTE["muted"])
        if index < len(labels) - 1:
            cx = 540
            draw.line((cx, top + node_height, cx, top + node_gap), fill=PALETTE["line"], width=4)
            draw.polygon(((cx - 9, top + node_gap - 14),
                          (cx + 9, top + node_gap - 14),
                          (cx, top + node_gap - 2)), fill=PALETTE["muted"])
    token_y = node_top + int(flow_p * 3) * node_gap + int((flow_p * 3 % 1) * node_gap)
    draw.ellipse((520, token_y - 10, 540, token_y + 10), fill=PALETTE["accent"])
    _center(draw, (WIDTH // 2, 1055), "运行顺序的解释图；不是本项目的成功调用",
            _font(22), PALETTE["muted"])

    _center(draw, (WIDTH // 2, 1150), "03  状态对照 · 后两项为理论示意",
            _font(29, bold=True), PALETTE["ink"])
    cards = [
        (55, 1210, 365, 1450, "BLOCKED", "当前观察态示例", PALETTE["warn"]),
        (385, 1210, 695, 1450, "AUTHORIZED", "理论示意 · 非本次授权", PALETTE["accent"]),
        (715, 1210, 1025, 1450, "EXECUTED", "理论示意 · 未发生", PALETTE["ok"]),
    ]
    state_p = max(0.0, min(1.0, (t - 4.75) / 2.8))
    for index, (left, top, right, bottom, title, caption, color) in enumerate(cards):
        active = (index == min(2, int(state_p * 3)))
        _card(draw, (left, top, right, bottom), outline=color if active else PALETTE["line"],
              width=5 if active else 2)
        _center(draw, ((left + right) // 2, top + 84), title,
                _font(25, bold=True), color if active else PALETTE["muted"])
        _center(draw, ((left + right) // 2, top + 158), caption,
                _font(18), PALETTE["muted"])
    draw.line((64, 1512, WIDTH - 64, 1512), fill=PALETTE["line"], width=2)
    _center(draw, (WIDTH // 2, 1580), "generated explanatory visual · evidence_capable = false",
            _font(21), PALETTE["accent"])
    _center(draw, (WIDTH // 2, 1640), "本预览没有调用 Runner，也没有生成执行回执",
            _font(22), PALETTE["muted"])
    _center(draw, (WIDTH // 2, 1785), f"原创动画 · {t:04.1f}s / {duration:04.1f}s",
            _font(20), PALETTE["muted"])


def _1024_frame(draw: ImageDraw.ImageDraw, t: float, duration: float) -> None:
    _center(draw, (WIDTH // 2, 82), "Easel 显示 OK，就证明工具链没问题了吗？",
            _font(43, bold=True), PALETTE["ink"])
    _center(draw, (WIDTH // 2, 150), "机制示意 · 非本期实测画面 · Owner 录制待提供",
            _font(25), PALETTE["accent"])
    draw.line((64, 204, WIDTH - 64, 204), fill=PALETTE["line"], width=2)

    cards = [
        (72, 360, 1008, 620, "本地 pin / HEAD", "版本与路径线索", PALETTE["accent"]),
        (72, 795, 1008, 1055, "离线 resolver", "当前输出待 Owner 原始录制", PALETTE["ink"]),
        (72, 1230, 1008, 1490, "上游 blob 比对", "本示意不运行 · 当前结果未知", PALETTE["muted"]),
    ]
    for index, (left, top, right, bottom, title, subtitle, color) in enumerate(cards):
        active = min(2, int(max(0, t) / duration * 3)) == index
        _card(draw, (left, top, right, bottom), outline=color if active else PALETTE["line"],
              width=5 if active else 2)
        _center(draw, (WIDTH // 2, top + 92), title,
                _font(32, bold=True), color if active else PALETTE["ink"])
        _center(draw, (WIDTH // 2, top + 175), subtitle,
                _font(22), PALETTE["muted"])
        if index < 2:
            y_start = bottom
            y_end = cards[index + 1][1]
            draw.line((WIDTH // 2, y_start, WIDTH // 2, y_end), fill=PALETTE["line"], width=5)
            draw.polygon(((WIDTH // 2 - 10, y_end - 18),
                          (WIDTH // 2 + 10, y_end - 18),
                          (WIDTH // 2, y_end - 4)), fill=PALETTE["muted"])
    progress = max(0.0, min(1.0, t / duration))
    y = int(620 + (1230 - 620) * progress)
    draw.ellipse((WIDTH // 2 - 13, y - 13, WIDTH // 2 + 13, y + 13),
                 fill=PALETTE["accent"])
    _center(draw, (WIDTH // 2, 1610), "动画仅解释验证边界，不展示或替代真实命令输出",
            _font(23), PALETTE["muted"])
    _center(draw, (WIDTH // 2, 1710), "真实录屏与 ≥35 秒合格来源时长：待 Owner 提供并复核",
            _font(22), PALETTE["accent"])
    _center(draw, (WIDTH // 2, 1810), f"原创辅助动画 · {t:04.1f}s / {duration:04.1f}s",
            _font(20), PALETTE["muted"])


def render_frame(project_slug: str, seconds: float) -> Image.Image:
    """Render one seek-stable frame from original vector shapes and typography."""
    profile = profile_for_project(project_slug)
    t = float(seconds)
    duration = float(profile["duration_s"])
    if not 0 <= t < duration:
        raise PreviewError(f"frame time must be in [0, {duration})")
    image = Image.new("RGB", (WIDTH, HEIGHT), PALETTE["base"])
    draw = ImageDraw.Draw(image)
    if profile["account"] == "x-superplay-future-intelligence":
        _future_frame(draw, t, duration)
    else:
        _1024_frame(draw, t, duration)
    return image


def _check_dependencies() -> Dict[str, Any]:
    import PIL

    python_version = ".".join(map(str, sys.version_info[:3]))
    pillow_version = str(PIL.__version__)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise PreviewError("ffmpeg is not available on PATH")
    probe = hidden_run([ffmpeg, "-version"], timeout=20)
    first_line = (probe.stdout or probe.stderr or "").splitlines()[0]
    match = re.search(r"ffmpeg version\s+(\S+)", first_line)
    ffmpeg_version = match.group(1) if match else "unknown"
    if python_version != "3.13.15" or pillow_version != "12.3.0" or not ffmpeg_version.startswith("8.1.1"):
        raise PreviewError(
            "local runtime differs from the recorded pin: "
            f"Python={python_version}, Pillow={pillow_version}, FFmpeg={ffmpeg_version}"
        )
    return {
        "python": {"version": python_version, "license": "PSF-2.0"},
        "pillow": {"version": pillow_version, "license": "MIT-CMU"},
        "ffmpeg": {"version": ffmpeg_version, "license": "GPL-3.0-or-later",
                   "binary": ffmpeg, "redistributed": False},
    }


def _write_video(project_slug: str, profile: Dict[str, Any], output: Path) -> int:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise PreviewError("ffmpeg is not available on PATH")
    frame_count = int(round(float(profile["duration_s"]) * FPS))
    command = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{WIDTH}x{HEIGHT}",
        "-framerate", str(FPS), "-i", "pipe:0", "-an", "-frames:v", str(frame_count),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart", str(output),
    ]
    process = hidden_popen(command, stdin=PIPE, stdout=DEVNULL, stderr=PIPE, text=False)
    try:
        assert process.stdin is not None
        for index in range(frame_count):
            t = index / FPS
            process.stdin.write(render_frame(project_slug, t).tobytes())
        process.stdin.close()
        stderr = process.stderr.read() if process.stderr else b""
        returncode = process.wait()
    except BaseException:
        process.terminate()
        process.wait()
        raise
    if returncode != 0:
        raise PreviewError(f"ffmpeg failed ({returncode}): {stderr.decode('utf-8', 'replace')[-1200:]}")
    return frame_count


def _write_snapshot(profile: Dict[str, Any], time_s: float, destination: Path) -> Dict[str, Any]:
    image = render_frame(profile["project"], time_s)
    image.save(destination, format="PNG", optimize=True)
    return {"path": f"project://assets/generated/{destination.name}",
            "sha256": sha256_file(destination), "time_s": time_s,
            "generated": True, "evidence_capable": False}


def render_project(project_slug: str) -> Dict[str, Any]:
    """Render a single allowlisted preview; refuse overwrites and report real checks."""
    profile = profile_for_project(project_slug)
    route = resolve_project_route(project_slug)
    if route["verdict"] != skill_route.VERDICT_RESOLVABLE:
        raise PreviewError(f"capability route blocked: {route['reason']}: {route['detail']}")
    dependencies = _check_dependencies()
    project_root = ROOT / "projects" / project_slug
    assets_dir = project_root / "assets" / "generated"
    work_dir = project_root / "work"
    assets_dir.mkdir(parents=True, exist_ok=True)
    output = assets_dir / "p6-native-motion-preview.mp4"
    receipt_path = project_root / "receipts" / "p6-native-motion-preview.json"
    route_path = work_dir / "p6-motion-route.json"
    if any(path.exists() for path in (output, receipt_path, route_path)):
        raise PreviewError("refusing to overwrite an existing P6 preview output or receipt")

    spec = {
        "schema": SCHEMA,
        "project": project_slug,
        "account": profile["account"],
        "version": VERSION,
        "resolution": f"{WIDTH}x{HEIGHT}",
        "fps": FPS,
        "duration_s": profile["duration_s"],
        "palette": PALETTE,
        "story_beats": profile["story_beats"],
        "visual_purpose": profile["visual_purpose"],
        "claims_current_result": profile["claims_current_result"],
        "generated": True,
        "evidence_capable": False,
    }
    spec_sha256 = hashlib.sha256(
        json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    frame_count = _write_video(project_slug, profile, output)
    output_hash = sha256_file(output)
    check = hidden_run(
        [python_executable(), str(ROOT / "scripts" / "check_motion_sample.py"),
         str(output), "--sha256", output_hash, "--json"],
        cwd=str(ROOT), timeout=120,
    )
    try:
        media_check = json.loads(check.stdout)
    except ValueError as exc:
        raise PreviewError(f"motion-sample checker did not return JSON: {exc}") from exc
    if check.returncode != 0 or media_check.get("state") != "TECHNICALLY_CHECKED":
        raise PreviewError(f"motion-sample technical check failed: {media_check}")

    snapshot_times = [0.7, profile["duration_s"] / 2.0,
                      profile["duration_s"] - 0.7]
    snapshots = []
    for index, timestamp in enumerate(snapshot_times, start=1):
        path = assets_dir / f"p6-native-motion-preview-frame-{index:02d}.png"
        if path.exists():
            raise PreviewError(f"refusing to overwrite existing snapshot: {path}")
        snapshots.append(_write_snapshot(profile, timestamp, path))

    completed = datetime.now(timezone.utc).isoformat(timespec="seconds")
    route_record = {
        "schema": "contentops.motion-route-result/v1",
        "selected_skill": CAPABILITY_ID,
        "version": VERSION,
        "dependencies": dependencies,
        "installed": True,
        "license_status": "LOCAL_ONLY_DECLARED",
        "input_contract": "allowlisted project slug and checked-in account profile; no external inputs",
        "output_contract": "silent generated MP4 plus digest-bound technical-check receipt",
        "contentops_execution_authorized": False,
        "contentops_grant_present": False,
        "user_task_scope_authorized": True,
        "execution_state": "EXECUTED_LOCAL_RENDER",
        "pipeline_state": "M4_5_M5_EASEL_NOT_YET_ATTEMPTED",
        "account": profile["account"],
        "project": project_slug,
        "created_at": completed,
        "output": {
            "path": f"project://assets/generated/{output.name}",
            "sha256": output_hash,
            "duration_s": profile["duration_s"],
            "resolution": f"{WIDTH}x{HEIGHT}",
            "fps": FPS,
            "frames": frame_count,
            "technical_state": media_check["state"],
            "generated": True,
            "evidence_capable": False,
            "snapshots": snapshots,
        },
        "execution_authorized": False,
        "production_ready": False,
        "publish_authorized": False,
    }
    receipt = {
        "schema": SCHEMA,
        "project": project_slug,
        "account": profile["account"],
        "version": VERSION,
        "renderer": {
            "source": "scripts/native_motion_preview.py",
            "source_sha256": sha256_file(Path(__file__).resolve()),
            "dependencies": dependencies,
        },
        "spec_sha256": spec_sha256,
        "input_profile": spec,
        "output": route_record["output"],
        "media_check": media_check,
        "rights": {
            "scope": "P6-requested internal review only",
            "third_party_assets": "NONE",
            "external_licenses": ["Python PSF-2.0", "Pillow MIT-CMU", "FFmpeg GPL-3.0-or-later local binary"],
            "ffmpeg_redistributed": False,
            "public_use_cleared": False,
        },
        "route": route_record,
        "execution_authorized": False,
        "contentops_grant_present": False,
        "production_ready": False,
        "publish_authorized": False,
        "created_at": completed,
    }
    if route_path.exists() or receipt_path.exists():
        raise PreviewError("refusing to overwrite route or receipt changed during render")
    route_path.write_text(json.dumps(route_record, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Render original local motion support; no GSAP.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    render = subparsers.add_parser("render", help="render one allowlisted project preview")
    render.add_argument("--project", required=True, choices=sorted(PROJECT_PROFILES))
    route = subparsers.add_parser("route", help="resolve one account's registered motion capability")
    route.add_argument("--project", required=True, choices=sorted(PROJECT_PROFILES))
    args = parser.parse_args(argv)
    try:
        if args.command == "route":
            print(json.dumps(resolve_project_route(args.project), ensure_ascii=False, indent=2))
            return 0
        receipt = render_project(args.project)
        print(json.dumps({
            "state": "TECHNICALLY_CHECKED",
            "project": receipt["project"],
            "output": receipt["output"],
            "receipt": f"projects/{args.project}/receipts/p6-native-motion-preview.json",
            "route": f"projects/{args.project}/work/p6-motion-route.json",
            "execution_authorized": False,
            "production_ready": False,
            "publish_authorized": False,
        }, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, PreviewError) as exc:
        print(json.dumps({"state": "BLOCKED", "reason": str(exc),
                          "execution_authorized": False,
                          "production_ready": False,
                          "publish_authorized": False}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
