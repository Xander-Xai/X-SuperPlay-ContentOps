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
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from process_utils import hidden_run, python_executable  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENGINE = r"C:\Users\Administrator\.agents\skills\huashu-art-motion\scripts\engine\render.py"
PAD_S = 0.4


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


def build(project: Path, *, speed: float, engine: Path, pad: float,
          skip_render: bool = False) -> dict:
    import split_narration_lines as splitter

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
    for row, spec in zip(document["lines"], specs):
        duration = round(float(row["duration_s"]) + pad, 3)
        data = json.loads(spec.read_text(encoding="utf-8"))
        data["duration"] = duration
        spec.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        out = clips / f"p{row['line']:02d}.mp4"
        if skip_render and _ffprobe_duration(out) >= duration:
            _log("render", f"{spec.stem} reused")
            continue
        _log("render", f"{spec.stem} ({duration}s)")
        proc = hidden_run([python_executable(), str(engine), "--spec", str(spec), "--out", str(out)],
                          timeout=1800, env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"))
        if proc.returncode != 0 or not out.is_file():
            raise SystemExit(f"render failed for {spec.stem}: {(proc.stderr or '')[-400:]}")

    # Probe before compose: a half-written MP4 fails later with an empty ffmpeg
    # error, and the shot it names is the symptom rather than the cause.
    track: list[tuple[Path, float]] = []
    for segment in segments:
        if segment["type"] == "presenter":
            shot = project / str(presenter["shot"]).replace("project://", "")
            # The composer probes work/clips/<clip>.mp4 for every segment even when
            # a full-film render is supplied, so the opening is staged there too.
            staged = clips / f"{segment['clip']}.mp4"
            if _ffprobe_duration(staged) < segment["duration"]:
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
    # The composer prints its envelope last, but ffmpeg notices reach stdout too,
    # so scan from the end for the first line that parses instead of assuming the
    # final line is the JSON.
    compose_result = None
    for line in reversed(compose_out.splitlines()):
        try:
            compose_result = json.loads(line)
            break
        except ValueError:
            continue
    receipt["stages"]["compose"] = {"returncode": proc.returncode,
                                    "result": compose_result}

    _log("qc", "qc_video")
    proc = hidden_run([python_executable(), str(ROOT / "scripts" / "qc_video.py"), str(project)],
                      timeout=1800, cwd=str(ROOT))
    receipt["stages"]["qc"] = {"returncode": proc.returncode}
    verdict = "-"
    report = project / "receipts" / "qc-report-easel.json"
    if report.is_file():
        verdict = json.loads(report.read_text(encoding="utf-8")).get("overall", "-")
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
    parser.add_argument("--engine", default=os.environ.get("HUASHU_ENGINE", DEFAULT_ENGINE))
    parser.add_argument("--pad", type=float, default=PAD_S,
                        help="extra seconds rendered per clip so trim always has headroom")
    parser.add_argument("--skip-render", action="store_true",
                        help="reuse rendered clips that already cover their beat")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()
    engine = Path(args.engine)
    if not engine.is_file():
        raise SystemExit(f"motion engine not found: {engine} (set HUASHU_ENGINE)")

    receipt = build(project, speed=args.speed, engine=engine, pad=args.pad,
                    skip_render=args.skip_render)
    print(json.dumps({"status": "OK", "overall": receipt.get("overall"),
                      "receipt": "receipts/motion-build.json"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
