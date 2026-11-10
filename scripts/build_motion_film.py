#!/usr/bin/env python3
"""Build one motion film end to end: narration -> beats -> clips -> film -> QC.

Why this exists
---------------
The 2026-10-28 cut was assembled by hand, and two failures only showed up at
compose time:

- ``pad_mode=trim`` hard-fails when a clip is even milliseconds shorter than its
  beat, which is what exact-duration renders produce;
- a clip still being written has no ``moov`` atom, and the upstream assembler
  reports that as an *empty* ffmpeg error after several minutes of work.

Both are properties of the step order, not of any one render, so they belong
here rather than in a shell history: clips render with headroom, every clip is
probed before compose starts, and a failure names the step and the file.

Stages (each one prints and is recorded in ``receipts/motion-build.json``):

    speed     optional atempo so the voice can be retimed without re-synthesis
    split     one wav per caption line, plus receipts/voice-lines.json
    timeline  motion/timeline.json from the measured line durations
    render    motion/specs/pNN.json -> work/clips/pNN.mp4, then probe them all
    compose   build_code_animation_sample.py
    qc        qc_video.py

Usage:
    python scripts/build_motion_film.py projects/x-superplay-1024
    python scripts/build_motion_film.py projects/x-superplay-1024 --speed 1.10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from process_utils import hidden_run, python_executable  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ART_MOTION_REPOSITORY = "https://github.com/alchaincyf/huashu-art-motion"
ART_MOTION_VERSION = "1.2.0"
ART_MOTION_COMMIT = "8f0a349a18b4bdf802b8d58715a2259c3e1ce709"
ART_MOTION_ENTRYPOINT = "scripts/engine/render.py"
ART_MOTION_BASELINE = ROOT / "runtime" / "huashu-art-motion-baseline.json"
DEFAULT_ART_MOTION_RUNTIME = Path("D:/Toolchains/huashu-art-motion/1.2.0")
PAD_S = 0.4


class MotionExecutionBlocked(SystemExit):
    """The external renderer was refused before any project mutation or render."""


def _normalized_repository(value: str) -> str:
    value = (value or "").strip().removesuffix(".git").rstrip("/").lower()
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.split(":", 1)[1].removesuffix(".git")
    elif value.startswith("ssh://git@github.com/"):
        value = "https://github.com/" + value.split("github.com/", 1)[1].removesuffix(".git")
    return value


def _default_git_probe(root: Path, *args: str) -> tuple[int, str]:
    proc = hidden_run(["git", "-C", str(root), *args], timeout=30)
    return proc.returncode, (proc.stdout or "").strip()


def verify_art_motion_runtime(runtime_root: Path, *, lock: dict | None = None,
                              lock_path: Path = ART_MOTION_BASELINE,
                              git_probe=None) -> dict:
    """Verify a clean checkout against the exact reviewed art-motion baseline.

    This verifies bytes' provenance only. Execution authority is checked separately;
    the current ADR permits registration but explicitly does not permit execution.
    """
    if lock is None:
        try:
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return {"status": "BLOCKED", "reason": f"BASELINE_UNAVAILABLE: {exc}"}

    expected = {
        "schema": "contentops.huashu-art-motion-baseline/v1",
        "capability": "huashu-art-motion",
        "repository": f"{ART_MOTION_REPOSITORY}.git",
        "version": ART_MOTION_VERSION,
        "commit": ART_MOTION_COMMIT,
        "entrypoint": ART_MOTION_ENTRYPOINT,
        "clip_schema": "scripts/engine/clip_schema.json",
        "font_registry": "scripts/engine/lib/fonts/index.json",
        "cjk_font": "scripts/engine/lib/fonts/NotoSerifJP-600.woff",
    }
    if not isinstance(lock, dict) or any(lock.get(key) != value for key, value in expected.items()):
        return {"status": "BLOCKED", "reason": "BASELINE_MISMATCH"}

    root = Path(runtime_root).resolve()
    if not root.is_dir():
        return {"status": "BLOCKED", "reason": "RUNTIME_ROOT_MISSING",
                "runtime_root": root}

    engine_candidate = root / ART_MOTION_ENTRYPOINT
    engine = engine_candidate.resolve()
    if not engine.is_relative_to(root):
        return {"status": "BLOCKED", "reason": "ENTRYPOINT_ESCAPED_RUNTIME_ROOT",
                "runtime_root": root, "entrypoint": engine}
    if not engine.is_file():
        return {"status": "BLOCKED", "reason": "ENTRYPOINT_MISSING",
                "runtime_root": root, "entrypoint": engine}

    license_candidate = root / "LICENSE"
    license_path = license_candidate.resolve()
    if not license_path.is_relative_to(root):
        return {"status": "BLOCKED", "reason": "LICENSE_ESCAPED_RUNTIME_ROOT",
                "runtime_root": root, "license": license_path}
    if not license_path.is_file():
        return {"status": "BLOCKED", "reason": "LICENSE_MISSING",
                "runtime_root": root, "license": license_path}

    required_files = {
        "CLIP_SCHEMA_MISSING": lock["clip_schema"],
        "FONT_REGISTRY_MISSING": lock["font_registry"],
        "CJK_FONT_MISSING": lock["cjk_font"],
    }
    resolved_required: dict[str, Path] = {}
    for reason, relative in required_files.items():
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root):
            return {"status": "BLOCKED", "reason": f"{reason.replace('_MISSING', '')}_ESCAPED_RUNTIME_ROOT",
                    "runtime_root": root, "path": candidate}
        if not candidate.is_file():
            return {"status": "BLOCKED", "reason": reason,
                    "runtime_root": root, "path": candidate}
        resolved_required[reason] = candidate
    try:
        font_index = json.loads(resolved_required["FONT_REGISTRY_MISSING"].read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": "BLOCKED", "reason": "FONT_REGISTRY_INVALID", "detail": str(exc)}
    if not isinstance(font_index, list) or not any(
        isinstance(row, list) and len(row) >= 2
        and row[0] == Path(lock["cjk_font"]).name and row[1] == ART_MOTION_FONT_FAMILY
        for row in font_index
    ):
        return {"status": "BLOCKED", "reason": "CJK_FONT_UNREGISTERED"}

    probe = git_probe or _default_git_probe
    checks = (
        (("rev-parse", "HEAD"), ART_MOTION_COMMIT, "COMMIT_MISMATCH"),
        (("remote", "get-url", "origin"), ART_MOTION_REPOSITORY, "UPSTREAM_MISMATCH"),
        (("status", "--porcelain", "--untracked-files=all"), "", "DIRTY_RUNTIME"),
    )
    for command, expected_value, reason in checks:
        try:
            result = probe(root, *command)
            code, actual = result if isinstance(result, tuple) else (result.returncode, result.stdout)
        except Exception as exc:
            return {"status": "BLOCKED", "reason": f"GIT_VERIFICATION_FAILED: {exc}"}
        actual = (actual or "").strip()
        if code != 0:
            return {"status": "BLOCKED", "reason": f"GIT_VERIFICATION_FAILED: {' '.join(command)}"}
        if command[0] == "remote":
            valid = _normalized_repository(actual) == _normalized_repository(expected_value)
        else:
            valid = actual == expected_value
        if not valid:
            return {"status": "BLOCKED", "reason": reason}
    return {"status": "TRUSTED_RUNTIME", "version": ART_MOTION_VERSION,
            "commit": ART_MOTION_COMMIT, "engine": engine,
            "font_family": ART_MOTION_FONT_FAMILY,
            "font_review_status": "CJK_GLYPH_VISUAL_REVIEW_REQUIRED"}


ART_MOTION_GRAMMARS = {
    "t1_3b1b", "t2_keynote_ui", "t3_finance_chart", "y1_kurzgesagt",
    "y2_vox", "y3_whiteboard", "y4_storytime", "y5_kinetic_type",
}
ART_MOTION_THEMES = {"paper", "poster", "ink", "navy", "bauhaus", "snow", "wood", "chalk"}
ART_MOTION_CJK_FONT = "NotoSerifJP-600.woff"
ART_MOTION_FONT_FAMILY = "Noto Serif JP"
_CJK = re.compile(r"[㐀-鿿]")


def validate_art_motion_spec(spec_path: Path, *, project_root: Path,
                             runtime_root: Path, render_duration_s: float,
                             font_family: str = ART_MOTION_FONT_FAMILY) -> dict:
    """Validate the pinned parameterized-clip contract and bind every local input.

    The upstream spec stays unchanged. The returned binding is suitable for the
    operation receipt and records the exact source spec/assets/font before render.
    """
    project = Path(project_root).resolve()
    spec_file = Path(spec_path).resolve()
    runtime = Path(runtime_root).resolve()
    if not spec_file.is_relative_to(project) or not spec_file.is_file():
        raise ValueError("spec path is missing or escapes the project")
    try:
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"spec is not readable UTF-8 JSON: {exc}") from exc
    if not isinstance(spec, dict) or spec.get("grammar") not in ART_MOTION_GRAMMARS:
        raise ValueError("spec grammar is missing or not supported by the pinned clip schema")
    try:
        duration = float(spec.get("duration"))
        render_duration = float(render_duration_s)
        fps = float(spec.get("fps"))
    except (TypeError, ValueError) as exc:
        raise ValueError("spec duration, fps, and render duration must be numeric") from exc
    if not all(math.isfinite(value) for value in (duration, render_duration, fps)):
        raise ValueError("spec timing must be finite")
    if not (0.0 < render_duration <= 8.0) or duration <= 0 or duration > 8.0:
        raise ValueError("each motion clip and its rendered duration must fit the 8s clip contract")
    if fps != 30 or spec.get("fps") != 30:
        raise ValueError("motion clips must use the pinned 30 fps sample contract")
    if spec.get("width") != 1080 or spec.get("height") != 1920:
        raise ValueError("motion clips must be portrait 1080x1920")
    if spec.get("theme") not in ART_MOTION_THEMES:
        raise ValueError("spec must name one supported Art Motion theme")
    cues = spec.get("cues")
    if not isinstance(cues, list) or not cues:
        raise ValueError("parameterized motion spec must contain cues")
    has_cjk = False
    asset_refs: set[str] = set()
    for cue in cues:
        if not isinstance(cue, dict):
            raise ValueError("spec cues must be objects")
        try:
            at = float(cue.get("at"))
        except (TypeError, ValueError) as exc:
            raise ValueError("each cue needs a numeric at value") from exc
        if not math.isfinite(at) or at < 0 or at >= duration:
            raise ValueError("cue time must be finite and inside the source spec duration")
        for key in ("text", "sub"):
            text = cue.get(key)
            if text is not None and not isinstance(text, str):
                raise ValueError(f"cue {key} must be text")
            has_cjk = has_cjk or bool(_CJK.search(text or ""))
        for key in ("image", "frames"):
            value = cue.get(key)
            candidates = value if isinstance(value, list) else [value]
            for ref in candidates:
                if isinstance(ref, str):
                    asset_refs.add(ref)
    if has_cjk and font_family != ART_MOTION_FONT_FAMILY:
        raise ValueError("Chinese copy requires the pinned Noto Serif JP font contract")
    font_file = (runtime / "scripts" / "engine" / "lib" / "fonts" / ART_MOTION_CJK_FONT).resolve()
    if not font_file.is_relative_to(runtime) or not font_file.is_file():
        raise ValueError("CJK font file is missing or escapes the pinned Art Motion runtime")
    registry = runtime / "scripts" / "engine" / "lib" / "fonts" / "index.json"
    try:
        font_index = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"pinned font registry is unavailable: {exc}") from exc
    if not isinstance(font_index, list) or not any(
        isinstance(row, list) and len(row) >= 2
        and row[0] == ART_MOTION_CJK_FONT and row[1] == ART_MOTION_FONT_FAMILY
        for row in font_index
    ):
        raise ValueError("selected font is not listed in the pinned runtime font registry")

    assets: dict[str, str] = {}
    for ref in sorted(asset_refs):
        candidate_ref = Path(ref)
        if candidate_ref.is_absolute() or "\\" in ref or ":" in ref or ".." in candidate_ref.parts:
            raise ValueError(f"spec input path is not project-relative: {ref}")
        asset = project.joinpath(*candidate_ref.parts).resolve()
        if not asset.is_relative_to(project) or not asset.is_file():
            raise ValueError(f"spec input is missing or escapes the project: {ref}")
        assets[ref] = hashlib.sha256(asset.read_bytes()).hexdigest()
    return {
        "schema": "contentops.huashu-art-motion-render-binding/v1",
        "spec_path": spec_file.relative_to(project).as_posix(),
        "spec_sha256": hashlib.sha256(spec_file.read_bytes()).hexdigest(),
        "input_asset_hashes": assets,
        "font_family": font_family,
        "font_file_sha256": hashlib.sha256(font_file.read_bytes()).hexdigest(),
        "font_review_status": "CJK_GLYPH_VISUAL_REVIEW_REQUIRED" if has_cjk else "BUNDLED_FONT_VERIFIED",
        "duration_s": render_duration,
        "resolution": "1080x1920",
        "fps": 30,
        "audio_policy": "REPLACE",
        "generated": True,
        "evidence_capable": False,
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }


def validate_art_motion_output(path: Path, *, project_root: Path,
                               expected_sha256: str, probe: dict,
                               render_binding: dict) -> dict:
    """Check the real bytes against the canonical silent-motion clip gate.

    The result is the shared Huashu motion record, so an Art Motion clip and a
    huashu-motion clip reach M4.5 through one vocabulary.
    """
    from contentops.media import huashu_motion
    from contentops.media.motion_sample import check_motion_clip

    root = Path(project_root).resolve()
    output = Path(path).resolve()
    if not output.is_relative_to(root) or not output.is_file():
        raise ValueError("Art Motion output is missing or escapes the project")
    result = check_motion_clip(
        output, probe=probe, expected_sha256=expected_sha256,
        min_duration_s=0.0, max_duration_s=8.0, reason_prefix="CLIP",
    )
    if result.get("state") != "TECHNICALLY_CHECKED":
        raise ValueError(result.get("reason", "Art Motion output failed sample validation"))
    if render_binding.get("schema") != "contentops.huashu-art-motion-render-binding/v1":
        raise ValueError("output has no verified render binding")
    return huashu_motion.build_output_record(
        engine=huashu_motion.ENGINE_ART_MOTION,
        spec_sha256=render_binding["spec_sha256"],
        clip_path="project://" + output.relative_to(root).as_posix(),
        clip_sha256=result["sha256"],
        duration=result["duration_s"],
        resolution=f"{result['width']}x{result['height']}",
        fps=result["fps"],
        audio_policy="REPLACE",
        input_asset_hashes=render_binding["input_asset_hashes"],
        extra={
            "font_family": render_binding["font_family"],
            "font_review_status": render_binding["font_review_status"],
        },
    )


def make_art_motion_envelope(record: dict, *, asset_id: str, placement_id: str,
                             receipt_ref: str, derived_from: str,
                             transform_receipt_ref: str):
    """Convert only a checked, transformed Art Motion output into the shared index."""
    from contentops.media.huashu_motion import make_envelope

    return make_envelope(
        record, asset_id=asset_id, placement_id=placement_id,
        receipt_ref=receipt_ref, derived_from=derived_from,
        transform_receipt_ref=transform_receipt_ref,
    )


def art_motion_execution_blocker(lock: dict) -> str:
    """Registration and a baseline boolean are not execution grants.

    This adapter is not yet wired to the managed execution gate, and the current
    ADR grants no execution authority. Refuse even if a local file is edited to
    claim authorization; only a future gate integration may enable execution.
    """
    if lock.get("execution_authorized") is not True:
        return "EXECUTION_NOT_AUTHORIZED"
    return "MANAGED_EXECUTION_GATE_REQUIRED"


def resolve_art_motion_engine(runtime_root: Path, *, engine_override: str | None = None) -> Path:
    """Fail closed unless path, upstream bytes and explicit execution authority agree."""
    root = Path(runtime_root).resolve()
    allowed = {DEFAULT_ART_MOTION_RUNTIME.resolve()}
    if root not in allowed:
        raise MotionExecutionBlocked(f"BLOCKED: unsupported art-motion runtime location: {root}")
    try:
        lock = json.loads(ART_MOTION_BASELINE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MotionExecutionBlocked(f"BLOCKED: art-motion baseline unavailable: {exc}")
    verified = verify_art_motion_runtime(root, lock=lock)
    if verified["status"] != "TRUSTED_RUNTIME":
        raise MotionExecutionBlocked(f"BLOCKED: huashu-art-motion {verified.get('reason', 'unverified')}")
    blocker = art_motion_execution_blocker(lock)
    if blocker:
        raise MotionExecutionBlocked(f"BLOCKED: {blocker}; ADR-014 registration is not execution authority")
    engine = verified["engine"]
    if engine_override and Path(engine_override).resolve() != engine:
        raise MotionExecutionBlocked("BLOCKED: --engine must resolve to the pinned runtime entrypoint")
    return engine


def _log(stage: str, message: str) -> None:
    print(f"[{stage}] {message}", flush=True)


def _ffprobe_duration(path: Path) -> float:
    proc = hidden_run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                       "-of", "default=nw=1:nk=1", str(path)], timeout=120)
    try:
        return float((proc.stdout or "").strip())
    except ValueError:
        return -1.0


def _atempo(source: Path, target: Path, speed: float) -> Path:
    """Retime the voice without changing its pitch.

    atempo accepts 0.5-2.0 per filter; outside that, chain instances so any
    factor remains supported rather than silently clamping.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    factor, chain = speed, []
    while factor > 2.0:
        chain.append("atempo=2.0")
        factor /= 2.0
    while factor < 0.5:
        chain.append("atempo=0.5")
        factor /= 0.5
    chain.append(f"atempo={factor:.6f}")
    proc = hidden_run(["ffmpeg", "-y", "-i", str(source), "-filter:a", ",".join(chain),
                       "-c:a", "pcm_s16le", str(target)], timeout=600)
    if proc.returncode != 0 or not target.is_file():
        raise SystemExit(f"atempo failed: {(proc.stderr or '')[-400:]}")
    return target


def _retime_srt(source: Path, target: Path, speed: float) -> Path:
    """Scale every cue by ``speed`` so the caption still describes the retimed audio.

    Splitting a sped-up recording against the original timestamps would take each
    line from the wrong place — the first would be short and the last would fall
    off the end — so the caption has to move with the voice.
    """
    import re
    cue = re.compile(r"(\d+)\n(\d\d:\d\d:\d\d,\d+) --> (\d\d:\d\d:\d\d,\d+)\n(.+?)(?=\n\n|\Z)", re.S)

    def seconds(stamp: str) -> float:
        h, m, s = stamp.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    def stamp(value: float) -> str:
        ms = int(round(value * 1000))
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    rows = []
    for index, match in enumerate(cue.finditer(source.read_text(encoding="utf-8")), 1):
        start = seconds(match.group(2)) / speed
        end = seconds(match.group(3)) / speed
        rows.append(f"{index}\n{stamp(start)} --> {stamp(end)}\n{match.group(4).strip()}\n")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(rows), encoding="utf-8")
    return target


def _film_track(clips: list[tuple[Path, float]], out: Path) -> Path:
    """Cut each clip to its beat and join the beats into one visual track.

    The upstream assembler builds and joins fifteen temporary shots, and that path
    fails on this host with an empty ffmpeg error at the join. Cutting here keeps
    the join deterministic and removes a failure mode that reports nothing.
    """
    parts = out.parent / "film-parts"
    parts.mkdir(parents=True, exist_ok=True)
    lines = []
    for index, (clip, duration) in enumerate(clips):
        part = parts / f"{index:02d}.mp4"
        proc = hidden_run(["ffmpeg", "-y", "-i", str(clip), "-t", f"{duration:.3f}",
                           "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                                  "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30",
                           "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                           "-pix_fmt", "yuv420p", str(part)], timeout=600)
        if proc.returncode != 0 or not part.is_file():
            raise SystemExit(f"trim failed for {clip.name}: {(proc.stderr or '')[-400:]}")
        lines.append(f"file '{(parts / part.name).as_posix()}'")
    listing = parts / "list.txt"
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    proc = hidden_run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                       "-c", "copy", str(out)], timeout=1200)
    if proc.returncode != 0 or not out.is_file():
        raise SystemExit(f"concat failed: {(proc.stderr or '')[-400:]}")
    return out


def _compose_outcome(output: str) -> tuple[bool, dict | None]:
    # The composer emits a complete JSON object after any diagnostic lines.
    # Decode from line boundaries rather than interpreting nested objects as
    # independent results; the final envelope must have no trailing output.
    decoder = json.JSONDecoder()
    for index, char in enumerate(output):
        if char != "{" or (index and output[index - 1] != "\n"):
            continue
        try:
            result, end = decoder.raw_decode(output, index)
        except ValueError:
            continue
        if isinstance(result, dict) and not output[end:].strip():
            return result.get("status") == "OK", result
    return False, None


def _compose_output_matches(project: Path, result: dict) -> bool:
    output = result.get("output")
    if not isinstance(output, dict):
        return False
    ref, expected = output.get("path"), output.get("sha256")
    if not isinstance(ref, str) or not ref.startswith("project://") or not isinstance(expected, str):
        return False
    path = (project / ref[len("project://"):]).resolve()
    if not path.is_relative_to(project.resolve()) or not path.is_file():
        return False
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return False
    return digest.hexdigest() == expected


def _qc_outcome(proc) -> str:
    if proc.returncode != 0:
        return "FAIL"
    try:
        report = json.loads((proc.stdout or "").strip())
    except (ValueError, TypeError):
        return "FAIL"
    if not isinstance(report, dict):
        return "FAIL"
    return report.get("overall") if report.get("overall") in {"PASS", "WARN"} else "FAIL"


def build(project: Path, *, speed: float, runtime_root: Path, pad: float,
          engine_override: str | None = None, skip_render: bool = False) -> dict:
    engine = resolve_art_motion_engine(runtime_root, engine_override=engine_override)
    import split_narration_lines as splitter
    from contentops.workflow import copy_review

    try:
        copy_review.require_approved(project)
    except copy_review.CopyReviewRequired as exc:
        raise SystemExit(f"BLOCKED: {exc.reason}\n  remedy: {exc.remedy}")

    storyboard = json.loads((project / "script" / "storyboard.json").read_text(encoding="utf-8"))
    narration = ROOT / str(storyboard.get("narration") or "")
    if not narration.is_file():
        raise SystemExit(f"narration not found: {narration}")
    captions = sorted((project / "script").glob("*.srt"))
    if len(captions) != 1:
        raise SystemExit(f"expected one caption in script/, found {len(captions)}")
    caption = captions[0]
    receipt: dict = {"schema": "contentops.motion-build/v1", "stages": {}}
    presenter = None

    if abs(speed - 1.0) > 1e-6:
        retimed = project / "work" / f"narration-{speed:.2f}x.wav"
        _log("speed", f"atempo {speed:.2f} -> {retimed.relative_to(project).as_posix()}")
        narration = _atempo(narration, retimed, speed)
        caption = _retime_srt(caption, project / "work" / f"caption-{speed:.2f}x.srt", speed)
        receipt["stages"]["speed"] = {"applied": speed, "path": str(retimed),
                                      "caption": str(caption)}
    else:
        receipt["stages"]["speed"] = {"applied": 1.0, "path": None}

    document = splitter.split(project, narration, caption)
    _log("split", f"{len(document['lines'])} lines, {document['total_s']}s")
    receipt["stages"]["split"] = {"lines": len(document["lines"]), "total_s": document["total_s"]}

    specs = sorted((project / "motion" / "specs").glob("p*.json"))
    if len(specs) != len(document["lines"]):
        raise SystemExit(f"{len(specs)} specs but {len(document['lines'])} lines — "
                         f"author one spec per line before building")
    receipt["stages"]["specs"] = {"count": len(specs)}

    segments = [{"type": "beat", "clip": f"p{row['line']:02d}", "line": row["line"],
                 "duration": round(float(row["duration_s"]), 3)}
                for row in document["lines"]]

    # A declared presenter opening is a segment, not an edit: it speaks line 0 and
    # the beat whose words it carries is dropped, so the hook is said once.
    contract_path = project / "motion" / "presenter" / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8")) if contract_path.is_file() else None
    if contract:
        presenter = document.get("presenter")
        if not isinstance(presenter, dict) or not presenter.get("shot"):
            raise SystemExit(
                "motion/presenter/contract.json declares an opening but "
                "receipts/voice-lines.json has no presenter block with a shot")
        variant = contract.get("variant", "eras")
        segments.insert(0, {"type": "presenter", "clip": contract.get("clip", "p00"), "line": 0,
                            "duration": round(float(presenter["duration_s"]), 3),
                            "variant": variant})
        replaced = contract.get("replaces_line")
        if replaced:
            segments = [s for s in segments
                        if not (s["type"] == "beat" and s["line"] == int(replaced))]
        receipt["stages"]["presenter"] = {"clip": contract.get("clip", "p00"),
                                          "replaces_line": replaced, "variant": variant}

    timeline = project / "motion" / "timeline.json"
    timeline.write_text(json.dumps({"schema": "contentops.timeline/v1", "segments": segments},
                                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _log("timeline", f"{len(segments)} segments written")

    clips = project / "work" / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    render_bindings: dict[int, dict] = {}
    for row, spec in zip(document["lines"], specs):
        duration = round(float(row["duration_s"]) + pad, 3)
        binding = validate_art_motion_spec(
            spec, project_root=project, runtime_root=runtime_root,
            render_duration_s=duration,
        )
        render_bindings[int(row["line"])] = binding
        out = clips / f"p{row['line']:02d}.mp4"
        if out.exists():
            raise MotionExecutionBlocked(f"BLOCKED: refusing to overwrite existing motion output: {out}")
        data = json.loads(spec.read_text(encoding="utf-8"))
        data["duration"] = duration
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", prefix=f".{spec.stem}.render-",
            dir=spec.parent, delete=False,
        ) as temp_spec_file:
            json.dump(data, temp_spec_file, ensure_ascii=False, indent=2)
            temp_spec_file.write("\\n")
            render_spec = Path(temp_spec_file.name)
        binding["render_spec_sha256"] = hashlib.sha256(render_spec.read_bytes()).hexdigest()
        try:
            if skip_render:
                _log("render", f"{spec.stem}: cache unverified; rendering again")
            _log("render", f"{spec.stem} ({duration}s)")
            proc = hidden_run(
                [python_executable(), str(engine), "--spec", str(render_spec), "--out", str(out)],
                timeout=1800, env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
            )
        finally:
            render_spec.unlink(missing_ok=True)
        if proc.returncode != 0 or not out.is_file():
            raise SystemExit(f"render failed for {spec.stem}: {(proc.stderr or '')[-400:]}")
        from check_motion_sample import _probe
        binding_after = validate_art_motion_spec(
            spec, project_root=project, runtime_root=runtime_root,
            render_duration_s=duration,
        )
        for key in ("spec_sha256", "input_asset_hashes", "font_file_sha256"):
            if binding_after.get(key) != binding.get(key):
                raise MotionExecutionBlocked(f"BLOCKED: {spec.name} {key} changed during render")
        clip_record = validate_art_motion_output(
            out, project_root=project,
            expected_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
            probe=_probe(out), render_binding=binding,
        )
        clip_receipt = project / "receipts" / f"art-motion-output-p{row['line']:02d}.json"
        if clip_receipt.exists():
            raise MotionExecutionBlocked(f"BLOCKED: refusing to overwrite existing output receipt: {clip_receipt}")
        clip_receipt.parent.mkdir(parents=True, exist_ok=True)
        clip_receipt.write_text(
            json.dumps(clip_record, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8"
        )
        receipt.setdefault("motion_outputs", []).append({
            "path": f"project://{out.relative_to(project).as_posix()}",
            "sha256": clip_record["clip_sha256"],
            "spec_sha256": clip_record["spec_sha256"],
            "asset_hashes": clip_record["asset_hashes"],
            "duration": clip_record["duration"],
            "resolution": clip_record["resolution"],
            "fps": clip_record["fps"],
            "audio_policy": clip_record["audio_policy"],
            "rights": clip_record["rights"],
            "review_status": clip_record["review_status"],
        })

    # Probe before compose: a half-written MP4 fails later with an empty ffmpeg
    # error, and the shot it names is the symptom rather than the cause.
    track: list[tuple[Path, float]] = []
    for segment in segments:
        if segment["type"] == "presenter":
            shot = project / str(presenter["shot"]).replace("project://", "")
            # The composer probes work/clips/<clip>.mp4 for every segment even when
            # a full-film render is supplied, so the opening is staged there too.
            staged = clips / f"{segment['clip']}.mp4"
            proc = hidden_run(["ffmpeg", "-y", "-i", str(shot),
                               "-t", f"{segment['duration']:.3f}",
                               "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                                      "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30",
                               "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                               "-pix_fmt", "yuv420p", str(staged)], timeout=600)
            if proc.returncode != 0 or not staged.is_file():
                raise SystemExit(f"presenter staging failed: {(proc.stderr or '')[-400:]}")
            source = staged
        else:
            source = clips / f"{segment['clip']}.mp4"
        got = _ffprobe_duration(source)
        if got < segment["duration"]:
            raise SystemExit(f"{source.name} is {got:.3f}s but the segment needs "
                             f"{segment['duration']:.3f}s (pad {pad}s)")
        track.append((source, segment["duration"]))
    _log("render", f"{len(track)} segments probed")
    receipt["stages"]["render"] = {"clips": len(track), "pad_s": pad}

    film = _film_track(track, project / "work" / "film.mp4")
    film_s = _ffprobe_duration(film)
    expected = round(sum(segment["duration"] for segment in segments), 3)
    if abs(film_s - expected) > 0.1:
        raise SystemExit(f"film track is {film_s:.3f}s, the timeline is {expected:.3f}s")
    _log("film", f"{film_s:.3f}s")

    _log("compose", "build_code_animation_sample")
    proc = hidden_run([python_executable(), str(ROOT / "scripts" / "build_code_animation_sample.py"),
                       str(project), "--out-name", "easel", "--motion-video", str(film)],
                      timeout=3600, cwd=str(ROOT))
    compose_out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        raise SystemExit(f"compose failed:\n{compose_out[-800:]}\n{(proc.stderr or '')[-800:]}")
    compose_ok, compose_result = _compose_outcome(compose_out)
    receipt["stages"]["compose"] = {"returncode": proc.returncode,
                                    "result": compose_result}
    if not compose_ok or not _compose_output_matches(project, compose_result):
        raise SystemExit(f"compose returned no verified successful output:\n{compose_out[-800:]}\n"
                         f"{(proc.stderr or '')[-800:]}")

    _log("qc", "qc_video")
    proc = hidden_run([python_executable(), str(ROOT / "scripts" / "qc_video.py"),
                       str(project), "--storyboard", str(project / "work" / "storyboard.json")],
                      timeout=1800, cwd=str(ROOT))
    verdict = _qc_outcome(proc)
    receipt["stages"]["qc"] = {"returncode": proc.returncode, "overall": verdict}
    receipt["overall"] = verdict

    out = project / "receipts" / "motion-build.json"
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="atempo factor applied to the recorded narration before splitting")
    parser.add_argument("--runtime-root", default=os.environ.get(
        "CONTENTOPS_HUASHU_ART_MOTION_ROOT", str(DEFAULT_ART_MOTION_RUNTIME)),
        help="approved Huashu art-motion checkout root (default: D:/Toolchains/huashu-art-motion/1.2.0)")
    parser.add_argument("--engine", default=None,
                        help="legacy alias; must equal the pinned runtime entrypoint")
    parser.add_argument("--pad", type=float, default=PAD_S,
                        help="extra seconds rendered per clip so trim always has headroom")
    parser.add_argument("--skip-render", action="store_true",
                        help="legacy option: renders again until cache provenance is verifiable")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()
    runtime_root = Path(args.runtime_root)
    try:
        receipt = build(project, speed=args.speed, runtime_root=runtime_root, pad=args.pad,
                        engine_override=args.engine, skip_render=args.skip_render)
    except MotionExecutionBlocked as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 5
    print(json.dumps({"status": "BLOCKED" if receipt.get("overall") == "FAIL" else "OK",
                      "overall": receipt.get("overall"),
                      "receipt": "receipts/motion-build.json"}, ensure_ascii=False))
    return 1 if receipt.get("overall") == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
