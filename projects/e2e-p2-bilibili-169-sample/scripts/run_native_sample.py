#!/usr/bin/env python3
"""Render and verify a TEST_ONLY native 16:9 Easel engineering sample."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
PROJECT = Path(__file__).resolve().parents[1]
SLUG = "native-169-sample-v2"
OUTPUT = PROJECT / "final" / f"{SLUG}.mp4"
RECEIPT = PROJECT / "receipts" / "native-16x9-render-v2.json"

for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_run  # noqa: E402
import m5_production  # noqa: E402
import qc_video  # noqa: E402


def _font(family: str, size: int, bold: bool) -> ImageFont.FreeTypeFont:
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    mono = "mono" in family.casefold() or "consolas" in family.casefold()
    names = (("consolab.ttf", "consola.ttf") if mono and bold else
             ("consola.ttf",) if mono else
             ("arialbd.ttf", "segoeuib.ttf") if bold else
             ("arial.ttf", "segoeui.ttf"))
    for name in names:
        path = windows / name
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    raise FileNotFoundError(f"no local font for SVG family {family!r}")


def _path_tokens(value: str) -> list[str]:
    return re.findall(r"[MmLlHhVvZz]|-?\d+(?:\.\d+)?", value)


def _draw_path(draw: ImageDraw.ImageDraw, element: ET.Element) -> None:
    tokens = _path_tokens(element.attrib.get("d", ""))
    points: list[tuple[float, float]] = []
    current = (0.0, 0.0)
    command = ""
    index = 0
    closed = False
    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
            if command in "Zz":
                closed = True
                continue
        if command in "MmLl" and index + 1 < len(tokens):
            x, y = float(tokens[index]), float(tokens[index + 1])
            index += 2
            if command.islower():
                x, y = current[0] + x, current[1] + y
            current = (x, y)
            points.append(current)
            command = "l" if command == "m" else "L" if command == "M" else command
        elif command in "Hh" and index < len(tokens):
            x = float(tokens[index])
            index += 1
            current = (current[0] + x if command == "h" else x, current[1])
            points.append(current)
        elif command in "Vv" and index < len(tokens):
            y = float(tokens[index])
            index += 1
            current = (current[0], current[1] + y if command == "v" else y)
            points.append(current)
        else:
            raise ValueError(f"unsupported SVG path command in {element.attrib.get('d')!r}")
    fill = element.attrib.get("fill", "none")
    stroke = element.attrib.get("stroke", "none")
    width = int(float(element.attrib.get("stroke-width", "1")))
    if closed and fill != "none":
        draw.polygon(points, fill=fill)
    elif stroke != "none" and len(points) > 1:
        draw.line(points, fill=stroke, width=width, joint="curve")


def _render_svg(svg: Path, png: Path) -> None:
    """Rasterize the sample's simple rect/text/path SVGs with existing Pillow."""
    root = ET.parse(svg).getroot()
    width = int(float(root.attrib.get("width", "0")))
    height = int(float(root.attrib.get("height", "0")))
    if (width, height) != (1920, 1080):
        raise ValueError(f"layout SVG must declare 1920x1080: {svg.name}")
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    for element in root:
        tag = element.tag.rsplit("}", 1)[-1]
        attrs = element.attrib
        if tag == "rect":
            x, y = float(attrs.get("x", 0)), float(attrs.get("y", 0))
            x2 = x + float(attrs.get("width", 0))
            y2 = y + float(attrs.get("height", 0))
            fill, stroke = attrs.get("fill", "none"), attrs.get("stroke", "none")
            stroke_width = int(float(attrs.get("stroke-width", 1)))
            radius = float(attrs.get("rx", 0))
            box = (x, y, x2, y2)
            if radius:
                draw.rounded_rectangle(box, radius=radius,
                                       fill=None if fill == "none" else fill,
                                       outline=None if stroke == "none" else stroke,
                                       width=stroke_width)
            else:
                draw.rectangle(box, fill=None if fill == "none" else fill,
                               outline=None if stroke == "none" else stroke,
                               width=stroke_width)
        elif tag == "text":
            size = int(float(attrs.get("font-size", 24)))
            family = attrs.get("font-family", "sans-serif")
            bold = attrs.get("font-weight", "400") in {"bold", "700", "800", "900"}
            draw.text((float(attrs.get("x", 0)), float(attrs.get("y", 0))),
                      element.text or "", font=_font(family, size, bold),
                      fill=attrs.get("fill", "#000000"), anchor="ls")
        elif tag == "path":
            _draw_path(draw, element)
        else:
            raise ValueError(f"unsupported SVG element {tag!r} in {svg.name}")
    image.save(png, format="PNG")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command: list[str], *, timeout: int = 300):
    result = hidden_run(command, cwd=str(ROOT), timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "command failed")[-2000:])
    return result


def _probe(path: Path) -> dict:
    result = _run([
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-of", "json", str(path),
    ], timeout=120)
    return json.loads(result.stdout)


def main() -> int:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite existing render: {OUTPUT}")
    if RECEIPT.exists():
        raise FileExistsError(f"refusing to overwrite existing receipt: {RECEIPT}")

    generated_images = []
    for index in (1, 2, 3):
        svg = PROJECT / "assets" / "layouts" / f"scene-0{index}-v2.svg"
        image = PROJECT / "assets" / "generated" / "native-169" / f"scene-0{index}-v2.png"
        if not svg.is_file():
            raise FileNotFoundError(f"layout source missing: {svg.relative_to(ROOT)}")
        if not image.exists():
            _render_svg(svg, image)
        metadata = _probe(image)
        stream = next((row for row in metadata.get("streams", [])
                       if row.get("codec_type") == "video"), {})
        geometry = (int(stream.get("width") or 0), int(stream.get("height") or 0))
        if geometry != (1920, 1080):
            raise RuntimeError(f"layout source {index} is {geometry}, expected 1920x1080")
        generated_images.append({
            "path": f"project://assets/generated/native-169/{image.name}",
            "sha256": _sha256(image),
            "width": geometry[0], "height": geometry[1],
            "source_svg": f"project://assets/layouts/{svg.name}",
            "generated": True, "evidence_capable": False,
        })

    compose = m5_production.stage_compose(PROJECT, SLUG)
    if compose.get("status") != "OK" or not OUTPUT.is_file():
        raise RuntimeError(f"M5/Easel compose did not produce a video: {compose}")

    qc = qc_video.qc(PROJECT, target=f"{SLUG}.mp4")
    report_path = PROJECT / "receipts" / f"qc-report-{SLUG}.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    metadata = _probe(OUTPUT)
    video = next((row for row in metadata.get("streams", [])
                  if row.get("codec_type") == "video"), {})
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    fps_text = str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1")
    fps = float(Fraction(fps_text))
    duration = float((metadata.get("format") or {}).get("duration") or 0)

    decode = hidden_run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-i", str(OUTPUT), "-f", "null", "-"],
        cwd=str(ROOT), timeout=600,
    )
    frame_dir = PROJECT / "receipts" / "native-169-keyframes-v2"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_refs = {}
    for name, timestamp in (("first", 0.1), ("middle", duration / 2),
                            ("last", max(0.0, duration - 0.1))):
        frame = frame_dir / f"{name}.png"
        if frame.exists():
            raise FileExistsError(f"refusing to overwrite keyframe: {frame}")
        _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{timestamp:.3f}",
              "-i", str(OUTPUT), "-frames:v", "1", str(frame)], timeout=120)
        frame_refs[name] = f"project://receipts/{frame_dir.name}/{frame.name}"

    checks_by_id = {row.get("id"): row for row in report.get("checks", [])}
    required_native_ids = (
        "resolution", "aspect_ratio_16_9", "native_storyboard_source_geometry",
    )
    native_checks = {name: checks_by_id.get(name, {}) for name in required_native_ids}
    native_pass = (
        width == 1920 and height == 1080 and abs(fps - 30.0) < 0.01
        and decode.returncode == 0
        and all(row.get("severity") == "PASS" and row.get("ok") is True
                for row in native_checks.values())
    )
    warnings = [row.get("id") for row in report.get("checks", [])
                if row.get("severity") == "WARN"]
    payload = {
        "schema": "contentops.native-16x9-render/v1",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "state": "PASS" if native_pass else "FAIL",
        "scope": "TEST_ONLY engineering sample; not an account deliverable",
        "runtime": {"engine": "easel", "engine_id": "v0.3.0",
                    "commit": "bb3c8ff0463f36c202454d74171682ba6e470cb1"},
        "output": {
            "path": f"project://final/{OUTPUT.name}",
            "sha256": _sha256(OUTPUT), "bytes": OUTPUT.stat().st_size,
            "width": width, "height": height, "fps": fps,
            "duration_s": duration, "video_codec": video.get("codec_name"),
        },
        "source_scenes": generated_images,
        "full_decode": {"state": "PASS" if decode.returncode == 0 else "FAIL",
                        "returncode": decode.returncode,
                        "stderr": decode.stderr[-1000:]},
        "native_platform_checks": native_checks,
        "full_qc": {"overall": qc.get("overall"),
                    "warn_checks": warnings,
                    "receipt": f"project://receipts/qc-report-{SLUG}.json",
                    "expected_test_sample_duration_warning": "general QC uses a 30s production minimum; this engineering sample intentionally follows the requested 5–15s range"},
        "keyframes": frame_refs,
        "visual_review": "PENDING_FOUNDER_REVIEW",
        "production_ready": False,
        "publish_authorized": False,
    }
    RECEIPT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if native_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
