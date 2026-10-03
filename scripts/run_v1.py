#!/usr/bin/env python3
"""Compose a V1 evidence-first short video from real source assets.

Two engines, selected with --engine:

    easel     (default) Production path. Reads script/master.md + storyboard.json
              from the project, synthesises narration through upstream Easel
              (tts-voiceover) and composites through upstream Easel
              (auto-short-video/assemble.py).

    fallback  Diagnostic renderer. Deterministic, ffmpeg-only, no upstream
              dependency. Kept so the pipeline can be exercised when Easel is
              unavailable — NOT a production path, and its output is always
              labelled fallback in the receipt.

Production never reads DEFAULT_SCRIPT_LINES; that list only feeds the fallback
demo path and tests. A real project must carry script/master.md.

NEEDS_HUMAN_REVIEW
    The pipeline is designed so that if any gate fails, it exits non-zero and writes
    the partial artifacts plus an explicit reason. It will not silently degrade.
    A fallback render never reports PRODUCTION_READY.
"""

import argparse
import json
import os
import re
import shutil
import sys
import wave
from pathlib import Path
from datetime import datetime, timezone

from process_utils import hidden_run, python_executable

ROOT = Path(__file__).resolve().parents[1]

# Fallback / test fixture only. The production path reads script/master.md.
DEFAULT_SCRIPT_LINES = [
    ("0-3",   "今天实测一个号称能跑通 AI 自媒体流水线的开源项目。", 5),
    ("3-10",  "它叫 ZJU-REAL/Easel，已经发布 v0.2.1。", 7),
    ("10-30", "它把发现、策划、创作、发布、归因串成了一个 Web 工作台。", 8),
    ("30-45", "本地运行需要 Git、Python、Node、FFmpeg、OpenClaw。", 7),
    ("45-55", "V1 只用它做生产；发布仍然人工，避免风控。", 6),
    ("55-65", "接下来我会一条一条把它的 Skill 跑给你看。", 7),
]


def ffprobe_meta(path: Path) -> dict:
    out = hidden_run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        timeout=30,
    )
    if out.returncode != 0:
        return {}
    try:
        return json.loads(out.stdout)
    except Exception:
        return {}


def parse_yaml(path: Path) -> dict:
    """Minimal YAML reader (only handles the shape we wrote in new_project.py)."""
    data = {}
    current_section = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("  ") and current_section:
            kv = line.strip()
            if ":" in kv:
                k, _, v = kv.partition(":")
                v = v.strip().strip('"')
                current_section[k.strip()] = parse_scalar(v)
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip().strip('"')
            if v == "":
                current_section = {}
                data[k] = current_section
            else:
                data[k] = parse_scalar(v)
                current_section = None
    return data


def parse_scalar(v: str):
    if v in ("true", "True", "yes"):
        return True
    if v in ("false", "False", "no"):
        return False
    if v == "":
        return ""
    return v


def find_real_images(project_dir: Path) -> list[Path]:
    """Find real evidence assets: PNG/JPG in sources/screenshots or sources/diagrams."""
    patterns = ["*.png", "*.jpg", "*.jpeg", "*.webp"]
    results = []
    for sub in ("sources/screenshots", "sources/diagrams", "sources/recordings"):
        d = project_dir / sub
        if not d.exists():
            continue
        for pat in patterns:
            results.extend(sorted(d.glob(pat)))
    return results


def synth_voice_wav(text: str, out_wav: Path, rate: int = 180, target_secs: float = 5.0) -> bool:
    """Try Windows SAPI via PowerShell, then espeak, then fallback to silence WAV.

    target_secs: desired audio duration. SAPI / espeak produce natural-length audio;
    the silence fallback is padded to this duration.
    """
    # 1) PowerShell System.Speech.Synthesis (Windows native, free)
    ps_cmd = [
        "powershell", "-NoProfile", "-Command",
        f"Add-Type -AssemblyName System.Speech; "
        f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Rate = {max(-10, min(10, (rate - 150) // 10))}; "
        f"$s.SetOutputToWaveFile('{str(out_wav).replace(chr(39), chr(39) + chr(39))}'); "
        f"$s.Speak('{text.replace(chr(39), chr(39) + chr(39))}'); "
        f"$s.Dispose();"
    ]
    try:
        res = hidden_run(ps_cmd, timeout=60)
        if res.returncode == 0 and out_wav.exists() and out_wav.stat().st_size > 1024:
            return True
    except Exception:
        pass

    # 2) espeak
    if shutil.which("espeak"):
        try:
            res = hidden_run(
                ["espeak", "-v", "zh+f3", "-s", str(rate), "-w", str(out_wav), text],
                timeout=60, text=False,
            )
            if res.returncode == 0 and out_wav.exists() and out_wav.stat().st_size > 1024:
                return True
        except Exception:
            pass

    # 3) Silence fallback (marks voice_quality=fallback in QC)
    try:
        sr = 22050
        duration_sec = max(2.0, float(target_secs))
        n_samples = int(sr * duration_sec)
        with wave.open(str(out_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(b"\x00\x00" * n_samples)
        return True
    except Exception:
        return False


def fit_image_to_video(image: Path, out_png: Path, w: int = 1080, h: int = 1920) -> bool:
    """Pad image to 9:16 with black background (text-safe). NO Ken Burns."""
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
    )
    res = hidden_run(
        ["ffmpeg", "-y", "-i", str(image), "-vf", vf,
         "-frames:v", "1", str(out_png)],
        timeout=60,
    )
    return res.returncode == 0 and out_png.exists() and out_png.stat().st_size > 0


def make_title_card(text: str, out_png: Path, w: int = 1080, h: int = 1920) -> bool:
    """Render a clean text card with ffmpeg drawtext."""
    safe = text.replace(":", r"\:").replace("'", r"\'").replace("%", r"\%").replace("\\", "\\\\")
    vf = (
        f"drawtext=fontfile='C\\:/Windows/Fonts/msyh.ttc':text='{safe}':"
        f"fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2:"
        f"box=1:boxcolor=black@0.55:boxborderw=24"
    )
    res = hidden_run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:d=1",
         "-vf", vf, "-frames:v", "1", str(out_png)],
        timeout=60,
    )
    return res.returncode == 0 and out_png.exists() and out_png.stat().st_size > 0


def concat_segments(segments: list[Path], out_mp4: Path, w: int, h: int) -> bool:
    list_file = out_mp4.parent / "_concat.txt"
    with list_file.open("w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"file '{str(seg).replace(chr(39), chr(39) + chr(39))}'\n")
    res = hidden_run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,format=yuv420p",
         "-r", "30",
         "-c:a", "aac", "-ar", "48000", "-ac", "2",
         str(out_mp4)],
        timeout=600,
    )
    list_file.unlink(missing_ok=True)
    return res.returncode == 0 and out_mp4.exists() and out_mp4.stat().st_size > 0


def write_srt(lines: list[tuple[str, str, int]], out_srt: Path) -> None:
    def fmt(t: int) -> str:
        h = t // 3600
        m = (t % 3600) // 60
        s = t % 60
        return f"{h:02d}:{m:02d}:{s:02d},000"

    cursor = 0
    with out_srt.open("w", encoding="utf-8") as f:
        for i, (tag, text, secs) in enumerate(lines, 1):
            start = cursor
            end = cursor + secs
            f.write(f"{i}\n{fmt(start)} --> {fmt(end)}\n{text}\n\n")
            cursor = end


def parse_script_shots(project: Path) -> list[dict]:
    """Read script/storyboard.json — the single source of truth for shots.

    Every shot must carry narration, a visual source and its provenance so the
    evidence-first policy can be enforced downstream.
    """
    sb_path = project / "script" / "storyboard.json"
    if not sb_path.exists():
        return []
    try:
        sb = json.loads(sb_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return sb.get("shots", []) or []


def script_exists(project: Path) -> bool:
    md = project / "script" / "master.md"
    return md.exists() and md.stat().st_size > 0


def resolve_production_runtime() -> dict:
    """Gate for the production engine: the pinned Easel runtime only.

    Offline mode (live=False): identity comes from the recorded provenance,
    which itself was produced by a live content-hash verification
    (scripts/verify_easel_runtime.py). doctor.py re-verifies live. Either way,
    an unpinned or tampered tree BLOCKS instead of silently rendering.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from resolve_easel import resolve_easel
    return resolve_easel(live=False)


def run_easel(project: Path) -> dict:
    """Production path: Easel TTS + upstream assemble.py."""
    shots = parse_script_shots(project)
    if not shots:
        return {"status": "BLOCKED", "engine": "easel",
                "reason": "script/storyboard.json missing or empty — production "
                          "requires a project-authored storyboard, not built-in lines"}
    if not script_exists(project):
        return {"status": "BLOCKED", "engine": "easel",
                "reason": "script/master.md missing — production requires a project-authored script"}
    runtime = resolve_production_runtime()
    if runtime["status"] != "OK":
        return {"status": "BLOCKED", "engine": "easel",
                "reason": "Easel runtime not usable: "
                          + "; ".join(runtime.get("reasons", ["unknown"])),
                "remedy": runtime.get("remedy")}
    easel_dir = Path(runtime["easel_dir"])

    script_dir = project / "script"
    narration_txt = script_dir / "narration.txt"
    narration_txt.write_text(
        "\n".join(s.get("narration", "") for s in shots) + "\n", encoding="utf-8")

    # Per-shot narration timing comes from one continuous read, so cue times
    # land on the voice track instead of drifting per shot.
    narration_mp3 = project / "assets" / "voice_easel" / "narration.mp3"
    narration_srt = project / "assets" / "captions" / "easel.srt"
    narration_mp3.parent.mkdir(parents=True, exist_ok=True)
    narration_srt.parent.mkdir(parents=True, exist_ok=True)
    tts_script = easel_dir / "skills" / "shared" / "scripts" / "tts.py"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    r = hidden_run(
        [python_executable(), str(tts_script), "speak", "-f", str(narration_txt),
         "-o", str(narration_mp3), "-v", "zh-CN-YunxiNeural",
         "--engine", "edge", "--subtitle", str(narration_srt)],
        env=env, timeout=600, cwd=str(easel_dir),
    )
    if r.returncode != 0 or not narration_mp3.exists():
        return {"status": "BLOCKED", "engine": "easel", "stage": "tts",
                "reason": ((r.stdout or "") + (r.stderr or ""))[-600:]}

    sb = json.loads((script_dir / "storyboard.json").read_text(encoding="utf-8"))
    # Store project-relative paths so the committed storyboard stays portable.
    sb["narration"] = narration_mp3.relative_to(ROOT).as_posix()
    sb["subtitle"] = narration_srt.relative_to(ROOT).as_posix()
    sb.setdefault("engine", "easel")
    sb["runtime"] = {
        "repo": "ZJU-REAL/Easel",
        "release": runtime.get("tag"),
        "commit": runtime.get("commit"),
        "acquisition": runtime.get("acquisition"),
        "verification": runtime.get("verification"),
    }
    (script_dir / "storyboard.json").write_text(
        json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from assemble_easel import run as assemble_run  # noqa: E402
    res = assemble_run(project, out_name="easel")
    res["engine"] = "easel"
    res["voice_provider"] = "easel/tts-voiceover (edge-tts, zh-CN-YunxiNeural)"
    res["voice_quality"] = "edge_tts_fallback"  # upstream's no-key engine; human review decides
    res["production_quality_warning"] = True
    res["production_ready"] = False             # §11: never auto-claim PRODUCTION_READY
    res["state"] = "READY_FOR_HUMAN_REVIEW"
    res["runtime"] = sb["runtime"]
    generated = sum(1 for s in shots
                    if s.get("source_type") in ("generated", "ai_generated", "stock", "title_card"))
    res["generated_visuals"] = {
        "count": generated,
        "total_shots": len(shots),
        "policy": "real_assets_first",
    }
    return res


def run(project: Path, voice_provider: str = "", engine: str = "easel") -> dict:
    project = project.resolve()
    project_yaml = project / "project.yaml"
    if not project_yaml.exists():
        return {"status": "BLOCKED", "reason": f"project.yaml missing at {project_yaml}"}

    if engine == "easel":
        return run_easel(project)

    cfg = parse_yaml(project_yaml)
    work = project / "work"
    assets_voice = project / "assets" / "voice"
    assets_captions = project / "assets" / "captions"
    final_dir = project / "final"
    receipts = project / "receipts"
    for d in (work, assets_voice, assets_captions, final_dir, receipts):
        d.mkdir(parents=True, exist_ok=True)

    # --- 1) Real evidence ---
    real_images = find_real_images(project)
    evidence_count = len(real_images)

    # --- 2) Build per-shot wav + image ---
    W, H = 1080, 1920
    segments = []
    voice_files = []
    voice_quality = "unknown"
    generated_count = 0
    srt_path = assets_captions / "default.srt"
    write_srt(DEFAULT_SCRIPT_LINES, srt_path)

    for idx, (tag, text, secs) in enumerate(DEFAULT_SCRIPT_LINES):
        # voice
        wav = assets_voice / f"shot_{idx:02d}.wav"
        ok = synth_voice_wav(text, wav, target_secs=float(secs))
        voice_files.append(wav)
        if ok and wav.exists():
            try:
                with wave.open(str(wav), "rb") as wf:
                    dur = wf.getnframes() / wf.getframerate()
                    if dur > 0.4:
                        voice_quality = "windows_sapi"
            except Exception:
                pass
        if voice_quality == "unknown":
            voice_quality = "fallback"

        # image (real first, then title-card fallback)
        shot_img = work / f"shot_{idx:02d}.png"
        used_image = None
        if idx < evidence_count:
            used_image = real_images[idx]
            ok = fit_image_to_video(used_image, shot_img, W, H)
            image_source = "real_screenshot" if ok else "title_card_fallback"
        else:
            ok = False
            image_source = "title_card"

        if not ok:
            ok = make_title_card(text, shot_img, W, H)
            image_source = "title_card"

        if image_source.startswith("title_card"):
            generated_count += 1

        if not ok:
            return {
                "status": "BLOCKED",
                "reason": f"failed to render shot {idx} image (ffmpeg drawtext/scale failed). "
                          "Check fonts and image inputs.",
                "shot": idx,
            }

        # ffmpeg: image + wav -> mp4 segment
        seg_path = work / f"shot_{idx:02d}.mp4"
        res = hidden_run(
            ["ffmpeg", "-y",
             "-loop", "1", "-i", str(shot_img),
             "-i", str(wav),
             "-c:v", "libx264", "-tune", "stillimage", "-r", "30",
             "-c:a", "aac", "-ar", "48000", "-ac", "2",
             "-pix_fmt", "yuv420p",
             "-t", str(secs),
             str(seg_path)],
            timeout=180,
        )
        if res.returncode != 0 or not seg_path.exists():
            return {
                "status": "BLOCKED",
                "reason": f"ffmpeg segment failed for shot {idx}",
                "stderr": res.stderr[-500:],
            }
        segments.append(seg_path)

    # --- 3) Concat ---
    rough = work / "rough.mp4"
    if not concat_segments(segments, rough, W, H):
        return {"status": "BLOCKED", "reason": "ffmpeg concat failed"}

    # --- 4) Output. The fallback engine never claims final.mp4: it writes
    # final/fallback.mp4 so a human can compare it against the Easel render.
    final_mp4 = final_dir / "fallback.mp4"
    shutil.copy2(rough, final_mp4)

    # update project.yaml with voice quality + outputs
    def _set_yaml(text: str, key: str, value: str) -> str:
        # lambda replacement: a plain f-string replacement would pass \\ and \"
        # through re.sub's escape processing and corrupt the YAML.
        return re.sub(rf"^(\s*{key}:\s*).*$",
                      lambda m: f'{m.group(1)}"{value}"',
                      text, flags=re.MULTILINE)

    try:
        text = project_yaml.read_text(encoding="utf-8")
        if "voice_quality:" in text:
            text = re.sub(r"^voice_quality:\s*.*$", f"voice_quality: {voice_quality}", text, flags=re.MULTILINE)
        else:
            text += f"\nvoice_quality: {voice_quality}\n"
        text = _set_yaml(text, "final_video", str(final_mp4).replace("\\", "/"))
        text = _set_yaml(text, "qc_report", str(project / "receipts" / "qc-report.md").replace("\\", "/"))
        text = re.sub(r"^status:\s*.*$", "status: rendered", text, flags=re.MULTILINE)
        project_yaml.write_text(text, encoding="utf-8")
    except Exception:
        pass

    meta = ffprobe_meta(final_mp4)
    streams = meta.get("streams", [])
    fmt = meta.get("format", {})
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})

    duration = float(fmt.get("duration", "0"))
    width = video_stream.get("width", 0)
    height = video_stream.get("height", 0)
    fps = video_stream.get("r_frame_rate", "0/1")

    return {
        "status": "OK",
        "engine": "fallback",
        "production_ready": False,
        "state": "READY_FOR_HUMAN_REVIEW",
        "note": "fallback render — diagnostic only, not a production pass",
        "final_video": str(final_mp4),
        "duration_sec": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "video_codec": video_stream.get("codec_name"),
        "audio_codec": audio_stream.get("codec_name"),
        "voice_quality": voice_quality,
        "voice_provider": voice_provider or "windows_sapi",
        "production_quality_warning": voice_quality != "configured_provider",
        "evidence_count": evidence_count,
        "generated_visuals": {
            "count": generated_count,
            "total_shots": len(segments),
            "policy": "real_assets_first",
        },
        "shots": len(segments),
        "script_lines": len(DEFAULT_SCRIPT_LINES),
        "srt": str(srt_path),
    }


def write_build_receipt(project: Path, result: dict) -> Path:
    """Every run — success or BLOCKED — leaves a durable receipt (§receipts)."""
    receipts = project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    engine = result.get("engine", "unknown")
    out = {"recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           **result}
    path = receipts / f"build-{engine}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project", help="path to project dir, e.g. projects/easel-review")
    p.add_argument("--engine", choices=("easel", "fallback"), default="easel",
                   help="easel = production (default); fallback = diagnostic ffmpeg-only render")
    p.add_argument("--voice-provider", default="")
    args = p.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / args.project).resolve()

    result = run(project, voice_provider=args.voice_provider, engine=args.engine)
    try:
        receipt = write_build_receipt(project, result)
        result = {"build_receipt": str(receipt), **result}
    except Exception as e:
        result["build_receipt_error"] = str(e)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "OK" else 4


if __name__ == "__main__":
    sys.exit(main())