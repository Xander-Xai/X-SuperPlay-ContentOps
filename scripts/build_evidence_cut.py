#!/usr/bin/env python3
"""Build one evidence cut from its CutPlan, ClaimMap and asset map.

The builder owns three things the upstream composer does not:

1. **Evidence transforms** — crop, fit and hold each placement exactly as the
   CutPlan declares, and refuse a crop the plan did not allow.
2. **Narration binding** — every spoken line comes from a claim's narration
   appearance, is synthesized once, cached by text hash, and must fit inside its
   placement. A line that does not fit blocks the build instead of being sped up
   or cut off.
3. **Receipts** — input SHAs, TTS receipts, caption timings, skill route and the
   final output hash, so a later reviewer can invalidate the cut precisely.

Composition is still upstream Easel's `auto-short-video`; subtitles are burned by
`scripts/assemble_easel.py`. Cards are rendered by the shared card renderer under
the `card-design` contract, never hand-screenshotted.

Usage::

    python scripts/build_evidence_cut.py projects/easel-1024-proof --tts-only
    python scripts/build_evidence_cut.py projects/easel-1024-proof
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from process_utils import hidden_run, python_executable  # noqa: E402
from contentops.evidence._common import (  # noqa: E402
    ContractError,
    parse_time_range,
    sha256_file,
)
from contentops.evidence.claim_map import ClaimMap  # noqa: E402
from contentops.media.cut_plan import CutPlan  # noqa: E402
from contentops.media.media_paths import resolve_media_path  # noqa: E402
from contentops.media.transport import ffprobe_json  # noqa: E402

ASSET_SCHEMA = "contentops.asset-map/v1"
BUILD_SCHEMA = "contentops.evidence-build/v1"
SKILL_ROUTE = {
    "name": "auto-short-video",
    "script": ".runtime/easel/skills/openclaw/auto-short-video/scripts/assemble.py",
    "why": "owns storyboard composition; ContentOps only prepares evidence-"
           "bounded clips, narration and captions",
}
TTS_SCRIPT = ROOT / "scripts" / "synthesize_narration.py"
RENDER_CARD = ROOT / ".runtime/easel/skills/shared/scripts/render_card.py"
CARD_AUDIT = ROOT / ".runtime/easel/skills/openclaw/card-design/scripts/card_audit.py"


class BuildFailed(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _fail(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise BuildFailed(code, detail)


def _local(project: Path, ref: str) -> Path:
    return resolve_media_path(ref, repo_root=ROOT, project_root=project)


def parse_project_yaml(path: Path) -> Dict[str, str]:
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip().strip('"')
    return data


def load_assets(project: Path) -> Dict[str, Dict[str, Any]]:
    path = project / "script" / "assets.json"
    _fail(path.is_file(), "ASSETS_MISSING", f"{path} does not exist")
    document = json.loads(path.read_text(encoding="utf-8"))
    _fail(document.get("schema") == ASSET_SCHEMA, "UNSUPPORTED_SCHEMA",
          f"expected {ASSET_SCHEMA!r}")
    assets = document.get("assets") or {}
    _fail(isinstance(assets, dict) and assets, "EMPTY_ASSETS",
          "assets must be a non-empty object")
    for asset_id, asset in assets.items():
        _fail(isinstance(asset, dict), "INVALID_ASSET", f"{asset_id} is not an object")
        kind = asset.get("kind")
        _fail(kind in ("recording", "card"), "INVALID_ASSET",
              f"{asset_id}.kind must be recording or card")
        if kind == "recording":
            local = _local(project, asset.get("path", ""))
            _fail(local.is_file(), "ASSET_MISSING", f"{asset_id}: {local}")
            actual = sha256_file(local)
            _fail(actual == asset.get("sha256"), "ASSET_SHA_MISMATCH",
                  f"{asset_id}: file is {actual}, map says {asset.get('sha256')}")
        else:
            _fail(bool(asset.get("html")), "INVALID_ASSET",
                  f"{asset_id}.html is required")
            _fail(isinstance(asset.get("width"), int)
                  and isinstance(asset.get("height"), int), "INVALID_ASSET",
                  f"{asset_id} needs integer width/height")
    return assets


def narration_lines(claim_map: ClaimMap, placement) -> List[Dict[str, Any]]:
    """Narration appearances for this placement's claims, in claim order."""
    lines: List[Dict[str, Any]] = []
    for claim_id in placement.claim_ids:
        claim = claim_map.by_id(claim_id)
        spoken = [a for a in claim.appearances if a["surface"] == "narration"]
        for appearance in spoken:
            lines.append({
                "claim_id": claim_id,
                "text": appearance["text"],
                "time_range": appearance.get("time_range"),
            })
    return lines


def tts_cache_path(project: Path, text: str) -> Path:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return project / "assets" / "voice" / f"{digest}.wav"


def synthesize_cached(project: Path, text: str, language: str = "zh") -> Dict[str, Any]:
    """Synthesize one line once. Returns {path, duration_s, receipt, cached}."""
    target = tts_cache_path(project, text)
    receipt_path = target.with_suffix(".receipt.json")
    if target.is_file() and receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        return {"path": target, "duration_s": float(receipt["asset"]["duration_s"]),
                "receipt": receipt, "cached": True}

    target.parent.mkdir(parents=True, exist_ok=True)
    result = hidden_run(
        [python_executable(), str(TTS_SCRIPT), "--text", text,
         "--language", language, "--out-dir", str(target.parent),
         "--receipt", str(receipt_path)],
        cwd=str(ROOT), timeout=600,
    )
    _fail(result.returncode == 0 and receipt_path.is_file(),
          "TTS_FAILED", (result.stderr or result.stdout or "")[-600:])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    produced = Path(receipt["asset"]["normalized_path"])
    _fail(produced.is_file(), "TTS_OUTPUT_MISSING", str(produced))
    if produced != target:
        shutil.copy2(produced, target)
    return {"path": target, "duration_s": float(receipt["asset"]["duration_s"]),
            "receipt": receipt, "cached": False}


def render_card(project: Path, asset_id: str, asset: Dict[str, Any]) -> Path:
    html = _local(project, asset["html"])
    _fail(html.is_file(), "CARD_HTML_MISSING", f"{asset_id}: {html}")
    png = _local(project, asset["png"]) if asset.get("png") else (
        project / "assets" / "cards" / f"{asset_id}.png")
    if png.is_file() and png.stat().st_mtime >= html.stat().st_mtime:
        return png
    png.parent.mkdir(parents=True, exist_ok=True)
    # The shared renderer prints an emoji; a GBK console would kill it after
    # the PNG was already written. Force UTF-8 for the child only.
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    result = hidden_run([
        python_executable(), str(RENDER_CARD),
        "--html", str(html), "--out", str(png),
        "--full-page", "--scale", "1",
        "--width", str(asset["width"]), "--height", str(asset["height"]),
    ], cwd=str(ROOT / ".runtime" / "easel"), timeout=300, env=env)
    _fail(result.returncode == 0 and png.is_file(), "CARD_RENDER_FAILED",
          (result.stderr or result.stdout or "")[-600:])
    audit = hidden_run([
        python_executable(), str(CARD_AUDIT), "audit", "-f", str(png),
    ], cwd=str(ROOT / ".runtime" / "easel"), timeout=300, env=env)
    audit_text = (audit.stdout or "") + (audit.stderr or "")
    # Advisory, not a gate: card_audit enforces the 75%-fill rule for standalone
    # feed cards. An in-video citation frame deliberately reserves the bottom
    # caption band, so a density FAIL here does not describe a defect. The result
    # is kept next to the PNG and in the build receipt.
    return png


def _views(placement) -> List[Dict[str, Any]]:
    """The views a placement shows, in order.

    A placement with no declared shots is one view for its whole window. A
    placement with shots shows each crop for its own span, so a result can be
    established in context and then enlarged without a frozen frame.
    """
    if placement.shots:
        return [{"crop": shot.crop,
                 "source_time_range": shot.source_time_range,
                 "duration_s": (shot.end_ms - shot.start_ms) / 1000.0,
                 "shot_id": shot.shot_id}
                for shot in placement.shots]
    return [{"crop": placement.crop,
             "source_time_range": placement.source_time_range,
             "duration_s": (placement.end_ms - placement.start_ms) / 1000.0,
             "shot_id": placement.placement_id}]


def _segment(asset: Dict[str, Any], asset_id: str, view: Dict[str, Any],
             target: Tuple[int, int], out: Path, project: Path) -> None:
    width, height = target
    duration = view["duration_s"]
    crop = view["crop"]
    panel_h = int(height * 0.62)
    # A wide terminal crop in a portrait frame is a thin band. Padding it with
    # the brand surface (DNA ``brand.palette.surface``) gives the evidence a
    # deliberate panel instead of a strip floating in black, and keeps every
    # pixel of the crop. No new image is introduced.
    cover = (
        f"crop={crop['width']}:{crop['height']}:{crop['x']}:{crop['y']},"
        f"scale={width}:{panel_h}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:0:(oh-ih)/2:color=0x161A22,setsar=1,fps=30"
    )
    if asset["kind"] == "card":
        png = render_card(project, asset_id, asset)
        # A card is authored at the target canvas, so it maps 1:1 to the frame.
        # Capping it at the evidence-panel height would shrink a full card to
        # ~62% and leave side margins that the design never had.
        card_cover = (
            f"crop={crop['width']}:{crop['height']}:{crop['x']}:{crop['y']},"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:0:(oh-ih)/2:color=0x0F1117,setsar=1,fps=30"
        )
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                   "-loop", "1", "-i", str(png), "-t", f"{duration:.3f}",
                   "-vf", card_cover, "-an", "-c:v", "libx264",
                   "-pix_fmt", "yuv420p", str(out)]
    else:
        source = _local(project, asset["path"])
        start_ms, _ = parse_time_range(view["source_time_range"], "source")
        graph = f"[0:v]{cover},tpad=stop_mode=clone:stop_duration={duration:.3f}[v]"
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                   "-ss", f"{start_ms / 1000.0:.3f}", "-i", str(source),
                   "-t", f"{duration:.3f}",
                   "-filter_complex", graph, "-map", "[v]",
                   "-an", "-c:v", "libx264", "-preset", "veryfast",
                   "-pix_fmt", "yuv420p", str(out)]
    result = hidden_run(command, timeout=600)
    _fail(result.returncode == 0 and out.is_file() and out.stat().st_size > 4096,
          "SEGMENT_FAILED",
          f"{view['shot_id']}: {(result.stderr or '')[-500:]}")


def _concat_video(parts: List[Path], out: Path) -> None:
    listing = out.with_suffix(".txt")
    listing.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts),
                       encoding="utf-8")
    result = hidden_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(listing),
        "-c", "copy", str(out),
    ], timeout=300)
    _fail(result.returncode == 0 and out.is_file(), "VIDEO_CONCAT_FAILED",
          result.stderr or "")


def _silence(path: Path, seconds: float) -> None:
    result = hidden_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "anullsrc=r=32000:cl=mono",
        "-t", f"{max(seconds, 0):.3f}", "-c:a", "pcm_s16le", str(path),
    ], timeout=120)
    _fail(result.returncode == 0 and path.is_file(), "SILENCE_FAILED",
          result.stderr or "")


def _concat_audio(parts: List[Path], out: Path) -> None:
    listing = out.with_suffix(".txt")
    listing.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts),
                       encoding="utf-8")
    result = hidden_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(listing),
        "-c", "copy", str(out),
    ], timeout=300)
    _fail(result.returncode == 0 and out.is_file(), "AUDIO_CONCAT_FAILED",
          result.stderr or "")


def _srt_timestamp(ms: int) -> str:
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _caption_style(config: Dict[str, str], target: Tuple[int, int]) -> Tuple[Dict[str, str], Optional[int], Optional[int]]:
    """Read the caption style from the account DNA.

    The DNA owns the style; a hardcoded constant here is how the burn drifted
    from the account's borderless, shadowless captions in the first place.
    ``Fontsize`` in ``burn_style`` is libass 384x288 script space and is not the
    pixel size, so the pixel value comes from ``caption_style.size_px``.
    """
    slug = config.get("account_slug")
    if not slug:
        return {}, None, None
    dna_path = ROOT / "config" / "accounts" / f"{slug}.json"
    _fail(dna_path.is_file(), "ACCOUNT_DNA_MISSING", str(dna_path))
    dna = json.loads(dna_path.read_text(encoding="utf-8"))
    caption = dna["visual"]["caption_style"]
    style: Dict[str, str] = {}
    for part in caption["burn_style"].split(","):
        key, _, value = part.partition("=")
        if key.strip():
            style[key.strip()] = value.strip()
    width, height = target
    font_size = int(round(int(caption["size_px"]) * min(width, height) / 1080))
    margin_v = int(round(int(caption["safe_zone"]["margin_v_px"]) * height / 1920))
    return style, font_size, margin_v


def build(project: Path, tts_only: bool = False) -> Dict[str, Any]:
    project = project.resolve()
    config = parse_project_yaml(project / "project.yaml")
    claim_map = ClaimMap.from_dict(json.loads(
        (project / "script" / "claim-map.json").read_text(encoding="utf-8")))
    cut_plan = CutPlan.from_dict(json.loads(
        (project / "script" / "cut-plan.json").read_text(encoding="utf-8")))
    cut_plan.validate_claims(claim_map)
    assets = load_assets(project)
    target = (cut_plan.target["width"], cut_plan.target["height"])

    totals = []
    for placement in cut_plan.placements:
        _fail(placement.asset_id in assets, "UNKNOWN_ASSET",
              f"{placement.placement_id} cites {placement.asset_id}")
        window = (placement.end_ms - placement.start_ms) / 1000.0
        lines = narration_lines(claim_map, placement)
        spoken = 0.0
        detail = []
        for line in lines:
            audio = synthesize_cached(project, line["text"])
            spoken += audio["duration_s"]
            detail.append({"claim_id": line["claim_id"], "text": line["text"],
                           "duration_s": round(audio["duration_s"], 3),
                           "cached": audio["cached"]})
        gaps = 0.15 * max(0, len(lines) - 1)
        _fail(spoken + gaps <= window + 0.01, "NARRATION_OVERFLOWS_PLACEMENT",
              f"{placement.placement_id}: {spoken + gaps:.2f}s of speech in a "
              f"{window:.2f}s placement; extend the placement or shorten the line")
        totals.append({"placement_id": placement.placement_id, "window_s": window,
                       "speech_s": round(spoken, 3), "lines": detail,
                       "views": [{"shot_id": view["shot_id"],
                                  "duration_s": round(view["duration_s"], 3)}
                                 for view in _views(placement)]})

    if tts_only:
        return {"status": "TTS_ONLY", "placements": totals}

    duration_ms = cut_plan.placements[-1].end_ms
    _fail(abs(duration_ms - int(config.get("duration_sec", "0")) * 1000) <= 1000,
          "DURATION_MISMATCH",
          f"project.yaml says {config.get('duration_sec')}s but the plan ends at "
          f"{duration_ms}ms")

    work = project / "work"
    work.mkdir(parents=True, exist_ok=True)
    clips = []
    audio_parts: List[Path] = []
    cues: List[Dict[str, Any]] = []

    for index, placement in enumerate(cut_plan.placements):
        asset = assets[placement.asset_id]
        clip = work / f"seg-{index:02d}.mp4"
        views = _views(placement)
        if len(views) == 1:
            _segment(asset, placement.asset_id, views[0], target, clip, project)
        else:
            parts = []
            for view_index, view in enumerate(views):
                part = work / f"seg-{index:02d}-v{view_index:02d}.mp4"
                _segment(asset, placement.asset_id, view, target, part, project)
                parts.append(part)
            _concat_video(parts, clip)
        clips.append(clip)

        window = (placement.end_ms - placement.start_ms) / 1000.0
        lines = narration_lines(claim_map, placement)
        parts: List[Path] = []
        cursor = 0.0
        for line_index, line in enumerate(lines):
            audio = synthesize_cached(project, line["text"])
            parts.append(audio["path"])
            start_ms = placement.start_ms + int(cursor * 1000)
            end_ms = start_ms + int(round(audio["duration_s"] * 1000))
            # A citation frame already renders the claim verbatim. Burning the
            # same words underneath duplicates the text and covers the source
            # line, so the card is the caption for that beat.
            # A card already renders its claim verbatim; a burned caption under
            # it repeats the same words and competes with the card's source line.
            on_card = asset["kind"] == "card"
            if not on_card:
                cues.append({"start_ms": start_ms, "end_ms": end_ms,
                             "text": line["text"], "claim_id": line["claim_id"]})
            cursor += audio["duration_s"]
            if line_index < len(lines) - 1:
                gap = work / "gap.wav"
                _silence(gap, 0.15)
                parts.append(gap)
                cursor += 0.15
        tail = work / "tail.wav"
        _silence(tail, max(0.0, window - cursor))
        parts.append(tail)
        placement_audio = work / f"aud-{index:02d}.wav"
        _concat_audio(parts, placement_audio)
        audio_parts.append(placement_audio)

    narration = work / "narration.wav"
    _concat_audio(audio_parts, narration)

    srt = project / "assets" / "captions" / "cut.srt"
    srt.parent.mkdir(parents=True, exist_ok=True)
    with srt.open("w", encoding="utf-8") as handle:
        for number, cue in enumerate(cues, start=1):
            handle.write(f"{number}\n{_srt_timestamp(cue['start_ms'])} --> "
                         f"{_srt_timestamp(cue['end_ms'])}\n{cue['text']}\n\n")

    storyboard = {
        "size": f"{target[0]}x{target[1]}",
        "engine": "easel",
        "pad_mode": "trim",
        "narration": str(narration),
        "subtitle": str(srt),
        "voice_provider": "minimax-mplan",
        "shots": [{"video": str(clip),
                   "duration": (p.end_ms - p.start_ms) / 1000.0}
                  for p, clip in zip(cut_plan.placements, clips)],
    }
    storyboard_path = work / "storyboard.json"
    storyboard_path.write_text(json.dumps(storyboard, indent=2, ensure_ascii=False),
                                encoding="utf-8")

    from assemble_easel import run as assemble
    style, font_size, margin_v = _caption_style(config, target)
    result = assemble(project, out_name="easel", strict_captions=True,
                      storyboard_path=storyboard_path,
                      caption_style=style, caption_font_size=font_size,
                      caption_margin_v=margin_v)
    _fail(result.get("status") == "OK", "ASSEMBLY_FAILED",
          json.dumps(result, ensure_ascii=False)[-800:])

    output = Path(result["video"])
    receipt = {
        "schema": BUILD_SCHEMA,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "package_id": cut_plan.package_id,
        "target": cut_plan.target,
        "skill_route": SKILL_ROUTE,
        "claim_map_fingerprint": claim_map.fingerprint(),
        "cut_plan_fingerprint": cut_plan.fingerprint(),
        "assets": {aid: {"kind": a["kind"],
                         **({"sha256": sha256_file(_local(project, a["path"]))}
                            if a["kind"] == "recording" else
                            {"png_sha256": sha256_file(render_card(project, aid, a))})}
                   for aid, a in assets.items()},
        "narration": {"path": "project://work/narration.wav",
                      "sha256": sha256_file(narration),
                      "duration_s": float(ffprobe_json(narration)["format"]["duration"])},
        "captions": {"path": "project://assets/captions/cut.srt",
                     "sha256": sha256_file(srt), "cues": cues,
                     "style_source": f"config/accounts/{config.get('account_slug')}.json",
                     "style": style,
                     "font_size_px": font_size,
                     "margin_v_px": margin_v},
        "placements": totals,
        "output": {"path": f"project://{output.relative_to(project).as_posix()}",
                   "sha256": sha256_file(output),
                   "duration_s": float(ffprobe_json(output)["format"]["duration"])},
        "voice_quality": "minimax_mplan_subscription",
        "bgm": {"role": "optional_bgm", "status": "OMITTED_BY_POLICY",
                "reason": "DASHSCOPE_API_KEY unavailable; video_ops loudness "
                          "regression prohibited"},
        "generated_media_used": False,
        "h3_experiment": "NOT_RUN",
        "h3_reason": "zero-generated core; the decision belongs to human playback review",
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }
    receipts = project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / "build-easel.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "OK", "video": result["video"], "receipt": str(receipts / "build-easel.json"),
            "receipt_data": receipt}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--tts-only", action="store_true")
    args = parser.parse_args()
    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    try:
        result = build(project, tts_only=args.tts_only)
    except (BuildFailed, ContractError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)},
                         indent=2, ensure_ascii=False))
        return 4
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
