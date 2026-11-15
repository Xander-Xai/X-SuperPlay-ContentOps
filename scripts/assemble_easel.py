#!/usr/bin/env python3
"""Run upstream Easel's assemble.py for a project, working around its Windows
subtitle-path bug WITHOUT modifying upstream.

Upstream `auto-short-video/scripts/assemble.py` escapes the subtitle path like:

    escaped = str(ass_path).replace("'", "\\\\'").replace(":", "\\\\:")
    _run(["ffmpeg", ..., "-vf", f"subtitles='{escaped}'", ...])

That escapes the drive-letter colon but leaves Windows path separators bare.
ffmpeg's filter parser then eats the backslashes, so
`D:\\Temp\\tmp123\\sub.ass` arrives as `D:Temptmp123sub.ass` and the subtitles
filter aborts:

    [Parsed_subtitles_0] Unable to open D:Temptmp0kbmkti2sub.ass
    [AVFilterGraph] Error initializing filters

Strategy (orchestration only, upstream file untouched):
  1. Run upstream assemble.py with the subtitle field REMOVED from a temp copy
     of the storyboard. Everything upstream does — per-shot composition, padding,
     concat, narration/BGM mixing — runs on the real upstream code path.
  2. Burn the subtitles ourselves in one extra ffmpeg pass. Run ffmpeg in the
     temporary subtitle directory and refer to the fixed relative filename,
     so the filter parser does not have to interpret a Windows absolute path.

The recipe mirrors upstream's own subtitle styling knobs (--sub-font / --sub-size
/ --sub-margin-v default to the same values upstream would have used).
"""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from subprocess import TimeoutExpired

from process_utils import hidden_run, python_executable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from contentops.easel.path_safety import is_linklike as _linklike  # noqa: E402

DEFAULT_SUB_FONT = "Noto Sans CJK SC"


def _upstream_assemble(*, workbench_runtime: bool = False) -> Path:
    """Resolve the production composer or an explicitly verified v0.3 candidate.

    Production stays on ``resolve_easel``. The workbench path is opt-in and
    refuses to run unless the upstream-plus-overlay verifier approves it.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from contentops.easel.skill_paths import resolve_skill_dir
    if workbench_runtime:
        from resolve_easel import resolve_easel_workbench
        resolved = resolve_easel_workbench()
        if resolved["status"] != "OK":
            raise RuntimeError("Easel workbench runtime is not verified: "
                               + "; ".join(resolved.get("reasons", ["unknown"])))
        easel_dir = Path(resolved["easel_dir"])
        return resolve_skill_dir(easel_dir, "auto-short-video") / "scripts" / "assemble.py"

    from resolve_easel import resolve_easel
    res = resolve_easel(live=False)
    if res["status"] != "OK":
        raise RuntimeError("Easel runtime not usable: "
                           + "; ".join(res.get("reasons", ["unknown"])))
    return resolve_skill_dir(Path(res["easel_dir"]), "auto-short-video") / "scripts" / "assemble.py"


def _subtitle_vf(ass_path: Path) -> str:
    # Forward slashes survive ffmpeg's filter parser; the drive colon must be escaped.
    posix = ass_path.resolve().as_posix()
    return f"subtitles=filename='{posix.replace(':', chr(92) + ':')}'"


def _ms(stamp: str) -> int:
    match = re.fullmatch(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})", stamp)
    if not match:
        raise ValueError("invalid subtitle timestamp")
    hours, minutes, seconds = (int(value) for value in match.groups()[:3])
    if minutes >= 60 or seconds >= 60:
        raise ValueError("invalid subtitle timestamp")
    millis = int(match.group(4).ljust(3, "0"))
    return hours * 3600000 + minutes * 60000 + seconds * 1000 + millis


def _caption_srt(shots: list, narration: object, destination: Path, *, env: dict) -> list[float]:
    """Create captions with the same per-shot duration rule as Easel v0.3."""
    if not shots or any(not isinstance(shot, dict) for shot in shots):
        raise ValueError("invalid storyboard shots")
    default_duration = 3.0
    if narration and any(not shot.get("duration") for shot in shots):
        probe = hidden_run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", str(narration)],
                           timeout=120, env=env)
        if probe.returncode != 0:
            raise ValueError("could not read narration duration")
        total = float(probe.stdout.strip())
        if not math.isfinite(total) or total <= 0:
            raise ValueError("invalid narration duration")
        default_duration = max(1.0, total / len(shots))
    elapsed = 0.0
    cues = []
    durations = []

    def timestamp(seconds: float) -> str:
        value = int(seconds * 1000)
        hours, value = divmod(value, 3600000)
        minutes, value = divmod(value, 60000)
        seconds, milliseconds = divmod(value, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    for shot in shots:
        if not isinstance(shot, dict):
            raise ValueError("invalid storyboard shot")
        raw_duration = shot.get("duration")
        if isinstance(raw_duration, bool):
            raise ValueError("invalid shot duration")
        duration = float(raw_duration or default_duration)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("invalid shot duration")
        durations.append(duration)
        caption = shot.get("caption") or ""
        if not isinstance(caption, str) or "\x00" in caption:
            raise ValueError("invalid shot caption")
        caption = caption.strip().replace("\r\n", "\n").replace("\r", "\n")
        if caption:
            caption = " ".join(caption.splitlines())
            cues.append(f"{len(cues) + 1}\n{timestamp(elapsed)} --> {timestamp(elapsed + duration)}\n{caption}\n")
        elapsed += duration
    if not cues:
        raise ValueError("no captions to burn")
    destination.write_text("\n".join(cues), encoding="utf-8")
    return durations


def _wrap(text: str, width_px: int, font_size: int) -> str:
    """Break a cue into lines of at most width_px, joined with ASS \\N.

    Measured advance widths (libass, CJK face): a full-width glyph advances
    ~font_size px, a latin glyph ~font_size/2 px (ratio 2.02:1 measured at 54).
    """
    cjk_px = font_size
    lat_px = font_size / 2.0

    def px(s: str) -> float:
        return sum(cjk_px if ord(c) > 0x2E80 else lat_px for c in s)

    lines, cur, cur_px = [], "", 0.0
    for ch in text:
        wpx = cjk_px if ord(ch) > 0x2E80 else lat_px
        if cur and cur_px + wpx > width_px:
            lines.append(cur)
            cur, cur_px = "", 0.0
        cur += ch
        cur_px += wpx
    if cur:
        lines.append(cur)
    return lines


def _fit(text: str, width_px: int, font_size: int, max_lines: int = 2,
         *, strict: bool = False) -> tuple[int, str]:
    """Shrink the font until the cue fits in max_lines. Returns (size, body).

    Uses an inline ASS override so each cue can carry its own size; the style's
    default stays at font_size.
    """
    size = font_size
    floor = min(font_size, max(1, 22, int(font_size * 0.6)))
    while size >= floor:
        lines = _wrap(text, width_px, size)
        if len(lines) <= max_lines:
            return size, "\\N".join(lines)
        size -= 2
    lines = _wrap(text, width_px, floor)
    if strict and len(lines) > max_lines:
        raise ValueError("subtitle cue exceeds the supported display area")
    return floor, "\\N".join(lines[:max_lines])


def _srt_to_ass(srt_path: Path, ass_path: Path, w: int, h: int,
                font: str, font_size: int, margin_v: int, *, strict: bool = False) -> None:
    """Mirror upstream _srt_to_ass styling (bottom-centre, wrapped at 2 lines)."""
    def ts(ms: int) -> str:
        h_, rem = divmod(ms, 3600000)
        m_, rem = divmod(rem, 60000)
        s_, ms_ = divmod(rem, 1000)
        # ASS wants centiseconds (2 digits); libass reads a 3-digit fraction as
        # cs*10, which stretches every cue and makes neighbours overlap.
        return f"{h_}:{m_:02d}:{s_:02d}.{ms_ // 10:02d}"

    cues = []
    blocks = srt_path.read_text(encoding="utf-8-sig").strip().split("\n\n")
    for b in blocks:
        lines = [l.strip() for l in b.splitlines() if l.strip()]
        if len(lines) >= 2 and "-->" in lines[1]:
            idx = lines[0]
            start, _, end = lines[1].partition("-->")
            text = " ".join(lines[2:])
            if strict and ("{" in text or "}" in text or "\\" in text):
                raise ValueError("subtitle contains unsupported ASS control characters")
            cues.append((ts(_ms(start.strip())), ts(_ms(end.strip())), text))
        elif strict and lines:
            raise ValueError("subtitle contains an invalid cue")

    if strict and (not cues or any(not text.strip() for _, _, text in cues)):
        raise ValueError("subtitle has no usable text cues")

    # edge-tts emits cues that can overlap by a few hundred ms; clamp so two
    # lines never render stacked on top of each other.
    fixed = []
    for i, (s, e, t) in enumerate(cues):
        start, end = _ms(s), _ms(e)
        if fixed and start < _ms(fixed[-1][1]):
            start = _ms(fixed[-1][1])
        if end <= start:
            if strict:
                raise ValueError("subtitle cue has no visible duration after overlap adjustment")
            end = start + 600
        fixed.append((ts(start), ts(end), t))

    # WrapStyle 2 disables libass auto-wrap, so the wrap width is fully
    # determined here: 86% of frame width leaves a clear side margin.
    width_px = int(w * 0.86)
    body = ""
    for s, e, t in fixed:
        size, text = _fit(t, width_px, font_size, strict=strict)
        override = "" if size == font_size else f"{{\\fs{size}}}"
        body += f"Dialogue: 0,{s},{e},D,,0,0,0,,{override}{text}\n"

    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\n"
        "ScaledBorderAndShadow: yes\nWrapStyle: 2\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: D,{font},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,"
        f"&H80000000,0,0,0,0,100,100,0,0,1,{max(2, font_size // 12)},0,2,"
        f"0,0,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    ass_path.write_text(head + body, encoding="utf-8")


def _run_impl(project: Path, out_name: str = "easel", *,
              workbench_runtime: bool = False, candidate_dir: Path | None = None,
              candidate_storyboard: dict | None = None) -> dict:
    project = project.resolve()
    storyboard = project / "script" / "storyboard.json"
    if not storyboard.exists():
        return {"status": "BLOCKED", "reason": f"storyboard missing: {storyboard}"}
    try:
        upstream_assemble = _upstream_assemble(workbench_runtime=workbench_runtime)
    except RuntimeError as e:
        return {"status": "BLOCKED", "reason": str(e)}

    sb = (candidate_storyboard if candidate_storyboard is not None
          else json.loads(storyboard.read_text(encoding="utf-8")))
    sub_rel = sb.get("subtitle")
    has_captions = any(isinstance(shot, dict) and shot.get("caption")
                       for shot in sb.get("shots", []))
    size = sb.get("size") or "1080x1920"
    try:
        w, h = (int(x) for x in str(size).lower().split("x"))
        if w <= 0 or h <= 0:
            raise ValueError("dimensions must be positive")
    except (TypeError, ValueError):
        return {"status": "BLOCKED", "stage": "storyboard",
                "reason": "invalid video size; expected positive WIDTHxHEIGHT"}

    # Upstream requires the output to live under outputs/<topic>/; keep it there,
    # then copy into the project so the project owns its deliverable.
    # The shared resolver supports both v0.2 openclaw and v0.3 builtin layouts.
    easel_dir = upstream_assemble.parents[4]
    topic_out = ((candidate_dir / "outputs" / project.name) if candidate_dir is not None
                 else (easel_dir / "outputs" / project.name))
    topic_out.mkdir(parents=True, exist_ok=True)
    upstream_out = topic_out / "final.mp4"

    with tempfile.TemporaryDirectory(dir=candidate_dir) as td:
        tmp_sb = Path(td) / "storyboard.json"
        # Strip BOTH the explicit subtitle and the per-shot captions: upstream
        # falls back to auto-generating a subtitle from `caption`
        # (assemble.py: `elif any(s.get("caption")...)`), which would re-enter the
        # same broken burn. We do that step ourselves, correctly, below.
        no_sub = dict(sb)
        no_sub.pop("subtitle", None)
        no_sub["shots"] = [
            {k: v for k, v in shot.items() if k != "caption"}
            for shot in no_sub.get("shots", [])
        ]
        if candidate_dir is None:
            env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        else:
            # A composer does not need the host's provider keys or sessions.
            names = ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "LANG")
            env = {name: os.environ[name] for name in names if name in os.environ}
            env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", TEMP=td, TMP=td)
            # v0.3 treats a native-audio shot without an audio stream as a
            # silent shot. Refuse that degradation before invoking upstream.
            for index, shot in enumerate(sb.get("shots", []), start=1):
                if shot.get("audio_mode") != "native":
                    continue
                source = shot.get("video")
                if not source:
                    return {"status": "BLOCKED", "stage": "native_audio",
                            "reason": f"shot {index} requests native audio without video"}
                try:
                    probe = hidden_run(
                        ["ffprobe", "-v", "error", "-select_streams", "a:0",
                         "-show_entries", "stream=index", "-of", "csv=p=0", str(source)],
                        timeout=120, env=env,
                    )
                except (OSError, TimeoutExpired):
                    return {"status": "BLOCKED", "stage": "native_audio",
                            "reason": f"shot {index} native audio could not be inspected"}
                if probe.returncode != 0 or not probe.stdout.strip():
                    return {"status": "BLOCKED", "stage": "native_audio",
                            "reason": f"shot {index} requests native audio but no audio stream was found"}
        generated_subtitle = None
        if not sub_rel and has_captions:
            generated_subtitle = Path(td) / "shot-captions.srt"
            try:
                durations = _caption_srt(sb["shots"], sb.get("narration"), generated_subtitle, env=env)
            except (OSError, TypeError, ValueError, OverflowError) as exc:
                return {"status": "BLOCKED", "reason": f"caption timing invalid: {exc}"}
            for shot, duration in zip(no_sub["shots"], durations):
                shot["duration"] = duration
        tmp_sb.write_text(json.dumps(no_sub, ensure_ascii=False), encoding="utf-8")
        try:
            proc = hidden_run(
                [python_executable(), str(upstream_assemble), "assemble",
                 "--storyboard", str(tmp_sb), "-o", str(upstream_out)],
                cwd=str(ROOT), env=env, timeout=1800,
            )
        except TimeoutExpired:
            return {"status": "BLOCKED", "stage": "upstream_assemble",
                    "reason": "upstream composition timed out"}
        except OSError:
            return {"status": "BLOCKED", "stage": "upstream_assemble",
                    "reason": "upstream composer could not be started"}
        if proc.returncode != 0 or not upstream_out.exists():
            return {"status": "BLOCKED", "stage": "upstream_assemble",
                    "reason": (proc.stderr or proc.stdout or "")[-800:]}

        final_dir = (candidate_dir / "final") if candidate_dir is not None else (project / "final")
        final_dir.mkdir(parents=True, exist_ok=True)
        out_mp4 = final_dir / f"{out_name}.mp4"

        if not sub_rel and not has_captions:
            shutil.copyfile(upstream_out, out_mp4)
            return {"status": "OK", "video": str(out_mp4), "subtitles_burned": False,
                    "upstream": str(upstream_assemble)}

        # --- our one extra pass: burn subtitles (upstream's step that breaks on Windows)
        if sub_rel:
            raw = Path(sub_rel)
            candidates = [raw] if raw.is_absolute() else [project / raw, ROOT / raw]
            sub_path = next((c for c in candidates if c.is_file()), None)
            if sub_path is None:
                return {"status": "BLOCKED", "reason": f"subtitle not found: {sub_rel}"}
        else:
            sub_path = generated_subtitle

        ass_path = Path(td) / "sub.ass"
        try:
            if sub_path.suffix.lower() == ".ass":
                # Upstream accepts authored ASS directly. Keep its styles and
                # still use a relative filename for Windows FFmpeg escaping.
                shutil.copyfile(sub_path, ass_path)
            else:
                _srt_to_ass(sub_path, ass_path, w, h, DEFAULT_SUB_FONT,
                            max(1, int(min(w, h) * 0.05)), int(h * 0.07), strict=True)
        except (OSError, UnicodeError, ValueError, OverflowError) as exc:
            return {"status": "BLOCKED", "stage": "subtitle_conversion",
                    "reason": f"subtitle conversion failed: {str(exc)[:300]}"}

        try:
            burn = hidden_run(
                ["ffmpeg", "-y", "-i", str(upstream_out),
                 "-vf", "subtitles=filename='sub.ass'", "-c:a", "copy", str(out_mp4)],
                cwd=td, timeout=900, env=env,
            )
        except TimeoutExpired:
            return {"status": "BLOCKED", "stage": "subtitle_burn", "reason": "subtitle burn timed out"}
        except OSError:
            return {"status": "BLOCKED", "stage": "subtitle_burn", "reason": "ffmpeg could not be started"}
        if burn.returncode != 0 or not out_mp4.exists():
            return {"status": "BLOCKED", "stage": "subtitle_burn",
                    "reason": (burn.stderr or "")[-800:]}

    return {
        "status": "OK",
        "video": str(out_mp4),
        "subtitles_burned": True,
        "upstream": str(upstream_assemble),
        "upstream_intermediate": str(upstream_out),
    }


def _hash_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def _candidate_input_path(value: str, project: Path, *, allow_declared_project_asset: bool = False) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("empty or invalid media path")
    text = value.removeprefix("project://")
    raw = Path(text)
    if ".." in raw.parts:
        raise ValueError("media path contains parent traversal")
    candidates = [raw] if raw.is_absolute() else [project / raw, ROOT / raw]
    found = []
    root = ROOT.resolve()
    project_prefix = project.relative_to(root).parts
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            relative = resolved.relative_to(root)
            same_project = relative.parts[:len(project_prefix)] == project_prefix
            hidden_index = len(project_prefix)
            allowed_hidden = (same_project and len(relative.parts) > hidden_index
                              and relative.parts[hidden_index] == ".media")
            if (len(relative.parts) < 3 or relative.parts[0] != "projects"
                    or (not same_project and not allow_declared_project_asset)
                    or any(part.startswith(".") and not (allowed_hidden and index == hidden_index)
                           for index, part in enumerate(relative.parts))):
                continue
            current = root
            for part in candidate.absolute().relative_to(root).parts:
                current = current / part
                if _linklike(current):
                    raise ValueError("linked media path")
            if resolved.is_file() and resolved not in found:
                found.append(resolved)
        except (OSError, ValueError):
            continue
    if len(found) != 1:
        raise ValueError("media path is missing, unsafe or ambiguous")
    return found[0]


def _candidate_inputs(project: Path) -> tuple[dict, list[dict], str]:
    """Bind candidate media to the existing project asset and rights contracts."""
    sys.path.insert(0, str(ROOT / "src"))
    from contentops.media.rights_gate import RightsError, validate_declared_asset
    from contentops.media.local_assets import is_valid_local_preview_asset

    storyboard_path = project / "script" / "storyboard.json"
    manifest_path = project / "sources" / "assets.json"
    for path in (storyboard_path, storyboard_path.parent, manifest_path, manifest_path.parent):
        if _linklike(path):
            raise ValueError("linked storyboard or asset manifest")
    storyboard_bytes = storyboard_path.read_bytes()
    storyboard = json.loads(storyboard_bytes.decode("utf-8"))
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if not isinstance(storyboard, dict) or not isinstance(manifest, dict):
        raise ValueError("storyboard and asset manifest must be objects")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise ValueError("asset manifest is invalid")
    shots = storyboard.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("storyboard has no shots")
    media_values = []
    for shot in shots:
        if not isinstance(shot, dict):
            raise ValueError("invalid storyboard shot")
        # Older M5 storyboards wrote duration_s only. Easel reads duration,
        # otherwise it silently redistributes timing against the narration.
        duration = shot.get("duration")
        legacy_duration = shot.get("duration_s")
        for value in (duration, legacy_duration):
            if value is not None and (type(value) not in (int, float)
                                      or not math.isfinite(value) or value <= 0):
                raise ValueError("shot duration must be a finite positive number")
        if duration is not None and legacy_duration is not None and abs(duration - legacy_duration) > 0.001:
            raise ValueError("shot duration and duration_s disagree")
        if duration is None and legacy_duration is not None:
            shot["duration"] = legacy_duration
        media_values.append(shot.get("video") or shot.get("image"))
    if storyboard.get("bgm"):
        media_values.append(storyboard["bgm"])
    for item in storyboard.get("sfx") or []:
        if not isinstance(item, dict) or not item.get("file"):
            raise ValueError("sound effect entry has no file")
        media_values.append(item["file"])
    needed_paths = {_candidate_input_path(value, project, allow_declared_project_asset=True)
                    for value in media_values}
    by_path = {}
    for asset in assets:
        if not isinstance(asset, dict) or not asset.get("repo_path"):
            continue
        try:
            path = _candidate_input_path(asset["repo_path"], project, allow_declared_project_asset=True)
        except (OSError, ValueError):
            continue
        if path not in needed_paths:
            continue
        if path in by_path:
            raise ValueError("duplicate asset path")
        by_path[path] = asset
    media_receipt = project / "receipts" / "media-use-stage.json"
    stage_bytes = None
    if media_receipt.is_file() and not _linklike(media_receipt) and not _linklike(media_receipt.parent):
        stage_bytes = media_receipt.read_bytes()
        stage = json.loads(stage_bytes.decode("utf-8"))
        if (not isinstance(stage, dict) or stage.get("schema") != "contentops.m5-media-use/v1"
                or not isinstance(stage.get("results"), list)):
            raise ValueError("media-use stage receipt is invalid")
        for item in stage["results"]:
            if not isinstance(item, dict) or item.get("state") != "IMPORTED":
                continue
            try:
                path = _candidate_input_path(item.get("path"), project)
            except (OSError, ValueError):
                continue
            if path not in needed_paths:
                continue
            if path in by_path:
                raise ValueError("asset path has multiple declarations")
            if item.get("kind") not in {"image", "icon", "logo", "bgm", "sfx"}:
                raise ValueError("media-use kind is invalid")
            receipt = _candidate_input_path(item.get("receipt_ref"), project)
            sidecar = path.with_name(path.name + ".receipt.json")
            if _linklike(sidecar) or not sidecar.is_file():
                raise ValueError("media-use import sidecar is missing or unsafe")
            receipt_bytes = receipt.read_bytes()
            if sidecar.read_bytes() != receipt_bytes:
                raise ValueError("media-use import receipts differ")
            imported = json.loads(receipt_bytes.decode("utf-8"))
            relative = path.relative_to(project).as_posix()
            if (not isinstance(imported, dict) or imported.get("schema") != "contentops.media-import/v1"
                    or imported.get("output_sha256") != item.get("sha256")
                    or imported.get("project_relative_path") != relative
                    or imported.get("imported_kind") != item.get("kind")
                    or imported.get("license") != item.get("license")):
                raise ValueError("media-use import receipt does not match asset")
            by_path[path] = {"id": item.get("id"), "repo_path": str(path),
                             "sha256": item.get("sha256"), "permission": "LICENSED",
                             "license": item.get("license"), "rights": item.get("rights"),
                             "candidate_kind": item.get("kind"),
                             "candidate_receipt": receipt, "candidate_sidecar": sidecar,
                             "candidate_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest()}
    evidence = []
    evidence.append({"kind": "asset_manifest",
                     "path": manifest_path.relative_to(ROOT.resolve()).as_posix(),
                     "sha256": hashlib.sha256(manifest_bytes).hexdigest()})
    if any("candidate_receipt" in asset for asset in by_path.values()):
        evidence.append({"kind": "media_use_stage_receipt",
                         "path": media_receipt.relative_to(ROOT.resolve()).as_posix(),
                         "sha256": hashlib.sha256(stage_bytes).hexdigest()})

    def resolve_media(value, kind):
        path = _candidate_input_path(value, project, allow_declared_project_asset=True)
        asset = by_path.get(path)
        if asset is None:
            raise ValueError(f"{kind} is not in the project asset manifest")
        recorded_kind = asset.get("candidate_kind")
        if recorded_kind and not (recorded_kind == kind or
                                  (kind == "visual" and recorded_kind in {"image", "icon", "logo"})):
            raise ValueError(f"{kind} does not match the media-use import kind")
        digest = _hash_file(path)
        if digest != asset.get("sha256"):
            raise ValueError(f"{kind} asset digest mismatch")
        preview = is_valid_local_preview_asset(asset, project, ROOT)
        rights = {}
        if not preview:
            if asset.get("permission") not in {"OWNED", "CREATED_BY_OWNER", "LICENSED"}:
                raise ValueError(f"{kind} asset permission is missing")
            try:
                rights = validate_declared_asset(asset, project)
            except RightsError:
                raise ValueError(f"{kind} rights could not be established") from None
            if rights.get("evidence_only") or rights.get("media_use_authorized") is False:
                raise ValueError(f"{kind} is restricted to evidence-only use")
            if rights.get("review_evidence"):
                rights_path = _candidate_input_path(rights["review_evidence"], project)
                rights_digest = _hash_file(rights_path)
                if rights_digest != rights.get("review_evidence_sha256"):
                    raise ValueError(f"{kind} rights review changed")
                evidence.append({"kind": "rights_review", "path": rights_path.relative_to(ROOT.resolve()).as_posix(),
                                 "sha256": rights_digest})
        for key in ("candidate_receipt", "candidate_sidecar"):
            if key in asset:
                receipt_path = asset[key]
                evidence.append({"kind": "media_use_import_receipt",
                                 "path": receipt_path.relative_to(ROOT.resolve()).as_posix(),
                                 "sha256": asset["candidate_receipt_sha256"]})
        evidence.append({"kind": kind, "asset_id": asset.get("id"),
                         "path": path.relative_to(ROOT.resolve()).as_posix(), "sha256": digest,
                         "rights_review_sha256": rights.get("review_evidence_sha256"),
                         "rights_basis": "LOCAL_PREVIEW" if preview else rights.get("license_id")})
        return str(path)

    for shot in shots:
        # Upstream prefers video when both fields are present.
        media_key = "video" if shot.get("video") else "image"
        shot[media_key] = resolve_media(shot.get(media_key), "visual")
    if storyboard.get("bgm"):
        storyboard["bgm"] = resolve_media(storyboard["bgm"], "bgm")
        volume = storyboard.get("bgm_volume")
        # Easel v0.3 uses `value or 0.25`, which silently makes zero audible.
        # Omit an explicitly muted track while keeping it in the input receipt.
        if type(volume) in (int, float) and volume == 0:
            evidence[-1]["mix_state"] = "MUTED"
            storyboard.pop("bgm")
        elif volume is not None and (type(volume) not in (int, float)
                                     or not math.isfinite(volume) or volume < 0):
            raise ValueError("bgm volume must be a finite nonnegative number")
    audible_sfx = []
    for item in storyboard.get("sfx") or []:
        if not isinstance(item, dict) or not item.get("file"):
            raise ValueError("sound effect entry has no file")
        at = item.get("at")
        if at is not None and (type(at) not in (int, float)
                               or not math.isfinite(at) or at < 0):
            raise ValueError("sound effect time must be a finite nonnegative number")
        item["file"] = resolve_media(item["file"], "sfx")
        volume = item.get("volume")
        if type(volume) in (int, float) and volume == 0:
            evidence[-1]["mix_state"] = "MUTED"
            continue
        if volume is not None and (type(volume) not in (int, float)
                                   or not math.isfinite(volume) or volume < 0):
            raise ValueError("sound effect volume must be a finite nonnegative number")
        audible_sfx.append(item)
    if "sfx" in storyboard:
        storyboard["sfx"] = audible_sfx
    if storyboard.get("narration"):
        audio = _candidate_input_path(storyboard["narration"], project)
        receipt = project / "receipts" / "narration.json"
        if _linklike(receipt) or not receipt.is_file():
            raise ValueError("narration receipt missing or unsafe")
        receipt_bytes = receipt.read_bytes()
        data = json.loads(receipt_bytes.decode("utf-8"))
        digest = _hash_file(audio)
        if (not isinstance(data, dict) or data.get("schema") != "contentops.m5-narration/v1"
                or data.get("sha256") != digest
                or (project / str(data.get("audio") or "")).resolve() != audio):
            raise ValueError("narration does not match its receipt")
        evidence.append({"kind": "narration_receipt",
                         "path": receipt.relative_to(ROOT.resolve()).as_posix(),
                         "sha256": hashlib.sha256(receipt_bytes).hexdigest()})
        storyboard["narration"] = str(audio)
        evidence.append({"kind": "narration", "path": audio.relative_to(ROOT.resolve()).as_posix(),
                         "sha256": digest})
    if storyboard.get("subtitle"):
        subtitle = _candidate_input_path(storyboard["subtitle"], project)
        storyboard["subtitle"] = str(subtitle)
        evidence.append({"kind": "subtitle", "path": subtitle.relative_to(ROOT.resolve()).as_posix(),
                         "sha256": _hash_file(subtitle)})
    return storyboard, evidence, hashlib.sha256(storyboard_bytes).hexdigest()


def run(project: Path, out_name: str = "easel", *,
        workbench_runtime: bool = False) -> dict:
    """Use the production adapter or create a separate, receipted candidate run."""
    if not workbench_runtime:
        return _run_impl(project, out_name=out_name)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", out_name):
        return {"status": "BLOCKED", "reason": "invalid candidate output name"}
    project = Path(project)
    if not project.is_absolute():
        project = ROOT / project
    projects = ROOT / "projects"
    local_projects = projects / "_local"
    allowed_parent = project.parent in (projects, local_projects)
    if (not allowed_parent or _linklike(projects) or _linklike(project)
            or (project.parent == local_projects and _linklike(local_projects))
            or not project.is_dir() or project.resolve().parent != project.parent.resolve()):
        return {"status": "BLOCKED", "reason": "candidate project must be a non-linked projects or projects/_local child"}
    project = project.resolve()
    for name in ("work", "receipts"):
        directory = project / name
        if _linklike(directory):
            return {"status": "BLOCKED", "reason": f"{name} directory is linked"}
        directory.mkdir(exist_ok=True)
        if not directory.is_dir() or directory.resolve().parent != project:
            return {"status": "BLOCKED", "reason": f"unsafe {name} directory"}
    candidate_root = project / "work" / "easel-v030-candidate"
    if _linklike(candidate_root):
        return {"status": "BLOCKED", "reason": "candidate directory is linked"}
    candidate_root.mkdir(exist_ok=True)
    if not candidate_root.is_dir() or candidate_root.resolve().parent != (project / "work").resolve():
        return {"status": "BLOCKED", "reason": "unsafe candidate directory"}
    run_id = str(uuid.uuid4())
    candidate_dir = candidate_root / run_id
    candidate_dir.mkdir()
    inputs = []
    input_storyboard_digest = None
    overlay_file = ROOT / "runtime" / "easel-workbench-overlay.json"
    candidate_commit, overlay_digest = None, None
    try:
        if _linklike(overlay_file) or _linklike(overlay_file.parent):
            raise ValueError("candidate overlay record is linked")
        overlay_bytes = overlay_file.read_bytes()
        overlay = json.loads(overlay_bytes.decode("utf-8"))
        candidate_commit = (overlay.get("upstream") or {}).get("commit")
        if not isinstance(candidate_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", candidate_commit):
            raise ValueError("candidate commit is invalid")
        overlay_digest = hashlib.sha256(overlay_bytes).hexdigest()
        candidate_storyboard, inputs, input_storyboard_digest = _candidate_inputs(project)
        result = _run_impl(project, out_name=out_name, workbench_runtime=True,
                           candidate_dir=candidate_dir, candidate_storyboard=candidate_storyboard)
        if (_hash_file(project / "script" / "storyboard.json") != input_storyboard_digest
                or any(_hash_file(ROOT / item["path"]) != item["sha256"] for item in inputs)
                or _linklike(overlay_file) or _hash_file(overlay_file) != overlay_digest):
            result = {"status": "BLOCKED", "reason": "candidate input changed during composition"}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result = {"status": "BLOCKED", "reason": f"candidate inputs invalid: {str(exc)[:300]}"}
    except Exception as exc:  # noqa: BLE001 - preserve a failure receipt
        result = {"status": "BLOCKED", "reason": f"candidate execution failed: {type(exc).__name__}"}
    video = Path(result["video"]) if result.get("video") else None
    digest = None
    expected_video = candidate_dir / "final" / f"{out_name}.mp4"
    if video is not None and (video != expected_video or _linklike(candidate_dir / "final")
                              or _linklike(video)):
        result = {"status": "BLOCKED", "stage": "candidate_output",
                  "reason": "candidate output path is unexpected or linked"}
        video = None
    if video is not None and video.is_file():
        try:
            sha = hashlib.sha256()
            with video.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    sha.update(block)
            digest = sha.hexdigest()
        except OSError:
            result = {"status": "BLOCKED", "reason": "candidate output could not be hashed"}
    if result.get("status") == "OK" and digest is None:
        result = {"status": "BLOCKED", "reason": "candidate output is missing or unsafe"}
    record = {
        "schema": "contentops.easel-candidate-compose/v1",
        "run_id": run_id, "project": project.name,
        "requested_runtime": "easel-v0.3.0-candidate",
        "candidate_commit": candidate_commit,
        "overlay_record_sha256": overlay_digest,
        "storyboard_sha256": input_storyboard_digest,
        "inputs": inputs,
        "status": result.get("status", "BLOCKED"),
        "output": video.relative_to(project).as_posix() if video is not None and digest else None,
        "output_sha256": digest,
        "subtitles_burned": result.get("subtitles_burned"),
        "failure_stage": result.get("stage") if result.get("status") != "OK" else None,
        "failure_reason": result.get("reason") if result.get("status") != "OK" else None,
        "production_ready": False, "publish_authorized": False,
        "human_review": "PENDING", "qc": "NOT_RUN",
    }
    receipt = project / "receipts" / f"build-easel-v030-{run_id}.json"
    try:
        with receipt.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except OSError:
        return {"status": "BLOCKED", "run_id": run_id,
                "reason": "candidate receipt could not be written",
                "production_ready": False, "publish_authorized": False,
                "human_review": "PENDING"}
    return {**result, "run_id": run_id, "receipt": str(receipt),
            "production_ready": False, "publish_authorized": False,
            "human_review": "PENDING"}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("project", help="project dir, e.g. projects/easel-review")
    p.add_argument("--out-name", default="easel", help="final/<name>.mp4")
    p.add_argument("--workbench-runtime", action="store_true",
                   help="use the v0.3 candidate only after upstream+overlay verification")
    args = p.parse_args()
    proj = Path(args.project)
    if not proj.is_absolute():
        proj = ROOT / proj
    res = run(proj, out_name=args.out_name,
              workbench_runtime=args.workbench_runtime)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if res.get("status") == "OK" else 4


if __name__ == "__main__":
    sys.exit(main())
