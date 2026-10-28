#!/usr/bin/env python3
"""Compose a code-animation sample from external-skill clips.

The animation is rendered by an external skill (huashu-art-motion's engine);
this driver owns the parts that belong to ContentOps:

1. **Timeline** — `motion/timeline.json` lists beat segments and optional
   claim-free inserts. Each beat binds one synthesised line; an insert plays
   silently, so no factual assertion rides on generated media.
2. **Narration placement** — each line sits at its segment start, so voice and
   picture share one timeline (audio-first).
3. **Captions** — an SRT from the measured line durations, burned with the
   account DNA style through ``assemble_easel``.
4. **Receipts** — spec/clip/output hashes, engine provenance, the generated
   duration share, ffprobe facts and a technical QC summary. It refuses a
   generated share of 10 % or more and never claims production readiness.

Usage::

    python scripts/build_code_animation_sample.py projects/easel-fi-what-is-agent
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from contentops.media.transport import ffprobe_json  # noqa: E402
from contentops.media.video_qc import measure_video  # noqa: E402

BEAT_SECONDS = 4.0
MAX_GENERATED_RATIO = 0.10
SAMPLE_SCHEMA = "contentops.code-animation-sample/v1"

#: Segments that carry speech. A presenter opening is one more voiced segment,
#: not a new kind of timing: it is spoken, so it is neither a tail nor a bridge.
VOICED_TYPES = ("beat", "presenter")

#: The presenter speaks before line 1 exists, so it is addressed as line 0.
PRESENTER_LINE = 0


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _yaml(path: Path) -> Dict[str, str]:
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip().strip('"')
    return data


def _peak_db(path: Path) -> float:
    from process_utils import hidden_run
    result = hidden_run(["ffmpeg", "-hide_banner", "-i", str(path), "-af",
                         "volumedetect", "-f", "null", "NUL"], timeout=120)
    text = (result.stderr or "") + (result.stdout or "")
    for line in text.splitlines():
        if "max_volume:" in line:
            return float(line.split("max_volume:")[1].replace("dB", "").strip())
    return 0.0


def _mix_bgm(project: Path, narration: Path,
             out_dir: Optional[Path] = None,
             bed_offset_s: float = 0.0) -> Tuple[Path, Dict[str, Any]]:
    """Mix a synthetic bed under the voice, refusing less than 18 dB headroom.

    ``bed_offset_s`` starts the bed later, so an opening that speaks before the
    first card stays dry and the bed still ends flush with the film.
    """
    from process_utils import hidden_run
    bgm = project / "work" / "bgm.wav"
    if not bgm.is_file():
        return narration, {"role": "bgm", "status": "OMITTED"}
    voice_peak, bgm_peak = _peak_db(narration), _peak_db(bgm)
    headroom = voice_peak - bgm_peak
    if headroom < 18:
        raise SystemExit(f"BGM is only {headroom:.1f} dB below the voice; 18 dB is the floor")
    mixed = project / (out_dir or Path("work")) / "narration-mix.wav"
    mixed.parent.mkdir(parents=True, exist_ok=True)
    delay_ms = int(round(bed_offset_s * 1000))
    graph = ("[0:a][1:a]amix=inputs=2:duration=first:normalize=0[a]" if delay_ms == 0 else
             f"[1:a]adelay={delay_ms}:all=1[bed];"
             f"[0:a][bed]amix=inputs=2:duration=first:normalize=0[a]")
    result = hidden_run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                         "-i", str(narration), "-i", str(bgm),
                         "-filter_complex", graph,
                         "-map", "[a]", "-c:a", "pcm_s16le", str(mixed)], timeout=300)
    if result.returncode != 0 or not mixed.is_file():
        raise SystemExit(f"BGM mix failed: {(result.stderr or '')[-400:]}")
    bed_receipt = bgm.with_suffix(".json")
    return mixed, {
        "role": "bgm", "status": "CODE_SYNTH", "path": "project://work/bgm.wav",
        "sha256": hashlib.sha256(bgm.read_bytes()).hexdigest(),
        "voice_peak_db": voice_peak, "bgm_peak_db": bgm_peak,
        "headroom_db": round(headroom, 1),
        "bed_offset_s": round(bed_offset_s, 3),
        "receipt": "project://work/bgm.json" if bed_receipt.is_file() else None,
        "policy": "synthesised locally; no sample library and no provider",
    }


def _caption_style(slug: str) -> Dict[str, Any]:
    dna = json.loads((ROOT / "config" / "accounts" / f"{slug}.json").read_text(
        encoding="utf-8"))
    caption = dna["visual"]["caption_style"]
    style: Dict[str, str] = {}
    for part in caption["burn_style"].split(","):
        key, _, value = part.partition("=")
        key = key.strip()
        if key and key not in ("Fontsize", "MarginV", "Alignment"):
            style[key] = value.strip()
    return {"style": style, "font_size": int(caption["size_px"]),
            "margin_v": int(caption["safe_zone"]["margin_v_px"])}


def _voice_lines(voice: Dict[str, Any], variant: str) -> Dict[int, Dict[str, Any]]:
    """Every spoken line this variant uses, keyed by the timeline's line number.

    The presenter opening is eras-only, so the baseline keeps exactly the
    twelve-line manifest it was built from.
    """
    lines = {int(row["line"]): row for row in voice["lines"]}
    presenter = voice.get("presenter")
    # A presenter belongs to the variant it was recorded for. Projects with a
    # baseline to protect declare "eras"; a project with no baseline can declare
    # the variant it actually builds, so the opening is not silently dropped.
    if presenter and presenter.get("variant", "eras") == variant:
        lines[PRESENTER_LINE] = {**presenter, "line": PRESENTER_LINE}
    return lines


def _validate_segments(segments: List[Dict[str, Any]], line_count: int) -> None:
    for segment in segments:
        segment.setdefault("duration", BEAT_SECONDS if segment["type"] == "beat" else None)
        if segment["type"] == "beat":
            if not 1 <= int(segment["line"]) <= line_count:
                raise SystemExit(f"timeline line out of range: {segment}")
        elif segment["type"] == "presenter":
            # Without a variant this segment would also enter the baseline, which
            # has no audio for it: the variant is what keeps the two films apart.
            if not segment.get("variant"):
                raise SystemExit(
                    f"a presenter segment must declare the variant it belongs to: {segment}")
            if int(segment["line"]) != PRESENTER_LINE:
                raise SystemExit(f"a presenter segment speaks line 0: {segment}")
            # A presenter is voiced, so it has no BEAT_SECONDS default to fall
            # back on; a missing duration would reach float(None) later.
            if not segment.get("duration"):
                raise SystemExit(f"a presenter segment must declare its duration: {segment}")
        elif segment["type"] != "insert":
            raise SystemExit(f"unknown segment type: {segment['type']}")


def _timeline(project: Path, line_count: int,
              variant: str = "easel") -> List[Dict[str, Any]]:
    path = project / "motion" / "timeline.json"
    if path.is_file():
        doc = json.loads(path.read_text(encoding="utf-8"))
        segments = doc["segments"]
    else:
        segments = [{"type": "beat", "clip": f"p{i:02d}", "line": i}
                    for i in range(1, line_count + 1)]
    # A segment with no variant belongs to every film; one that names a variant
    # belongs only to that film.
    segments = [segment for segment in segments
                if not segment.get("variant") or segment["variant"] == variant]
    _validate_segments(segments, line_count)
    return segments


def _clip_path(project: Path, clip: str, variant: str) -> Path:
    """Where this clip lives, mirroring ``motion/film/render.py::_source``.

    An eras-only re-render (the presenter opening) sits in ``work/eras/clips``;
    the baseline clip it replaces stays byte-identical.
    """
    if variant == "eras":
        override = project / "work" / "eras" / "clips" / f"{clip}.mp4"
        if override.is_file():
            return override
    return project / "work" / "clips" / f"{clip}.mp4"


def _storyboard_shots(segments: List[Dict[str, Any]],
                      motion_video: Optional[Path]) -> List[Dict[str, Any]]:
    total_s = sum(float(segment["duration"]) for segment in segments)
    if motion_video is not None:
        return [{"video": str(motion_video), "duration": total_s}]
    return [{"video": str(segment["path"]), "duration": float(segment["duration"])}
            for segment in segments]


def _variant_paths(variant: str) -> Dict[str, Path]:
    """Project-relative outputs per variant; the baseline stays the default."""
    if variant == "eras":
        return {"srt": Path("assets/captions/eras.srt"), "work": Path("work/eras"),
                "receipt": Path("receipts/eras/sample.json")}
    return {"srt": Path("assets/captions/default.srt"), "work": Path("work"),
            "receipt": Path("receipts/sample.json")}


def _place_narration(project: Path, lines: Dict[int, Dict[str, Any]],
                     segments: List[Dict[str, Any]],
                     target_dir: Optional[Path] = None) -> Tuple[Path, List[Dict[str, Any]]]:
    """Write one PCM track; each beat line starts at its segment start."""
    first_line = next(line for line in lines.values())
    first_path = project / first_line["path"].replace("project://", "")
    with wave.open(str(first_path), "rb") as first:
        rate, channels, width = first.getframerate(), first.getnchannels(), first.getsampwidth()
    total_s = sum(float(segment["duration"]) for segment in segments)
    buffer = bytearray(int(round(total_s * rate)) * channels * width)
    cursor = 0.0
    placed = []
    for segment in segments:
        if segment["type"] in VOICED_TYPES:
            row = lines[int(segment["line"])]
            source = project / row["path"].replace("project://", "")
            with wave.open(str(source), "rb") as handle:
                if (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()) != (rate, channels, width):
                    raise SystemExit(f"sample format differs: {source}")
                frames = handle.readframes(handle.getnframes())
            offset = int(round(cursor * rate)) * channels * width
            buffer[offset:offset + len(frames)] = frames
            placed.append({"line": int(segment["line"]), "start_s": round(cursor, 3),
                           "duration_s": row["duration_s"]})
        cursor += float(segment["duration"])
    target = project / (target_dir or Path("work")) / "narration.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(bytes(buffer))
    return target, placed


def _write_srt(project: Path, lines: Dict[int, Dict[str, Any]],
               placed: List[Dict[str, Any]],
               target: Optional[Path] = None) -> Path:
    target = project / (target or Path("assets/captions/default.srt"))
    target.parent.mkdir(parents=True, exist_ok=True)

    def ts(ms: int) -> str:
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    rows = []
    for index, item in enumerate(placed, 1):
        row = lines[item["line"]]
        start = int(round(item["start_s"] * 1000))
        end = min(start + int(round(row["duration_s"] * 1000)), start + 3900)
        rows.append(f"{index}\n{ts(start)} --> {ts(end)}\n{row['text']}\n")
    target.write_text("\n".join(rows), encoding="utf-8")
    return target


def _reconciliation(segments: List[Dict[str, Any]], placed: List[Dict[str, Any]],
                    lines: Dict[int, Dict[str, Any]], srt_end_s: float,
                    output_duration_s: float) -> Dict[str, Any]:
    """Prove the film length is voice + declared tails + the silent bridge."""
    cursor, rows = 0.0, []
    for segment in segments:
        duration = float(segment["duration"])
        rows.append({"id": segment["clip"], "type": segment["type"],
                     "start_s": round(cursor, 3), "end_s": round(cursor + duration, 3)})
        cursor += duration
    voice_s = sum(float(row["duration_s"]) for row in lines.values())
    voiced_segments = [s for s in segments if s["type"] in VOICED_TYPES]
    film_s = sum(float(s["duration"]) for s in segments)
    tails_s = round(sum(float(s["duration"]) for s in voiced_segments)
                    - sum(float(lines[int(s["line"])]["duration_s"]) for s in voiced_segments), 3)
    bridge_s = round(sum(float(s["duration"]) for s in segments if s["type"] == "insert"), 3)
    return {
        "schema": "contentops.timing-reconciliation/v1",
        "segments": rows,
        "film_seconds": round(film_s, 3),
        "voice_seconds": round(voice_s, 3),
        "tail_seconds": tails_s,
        "silent_bridge_seconds": bridge_s,
        "arithmetic": f"{voice_s:.3f} + {tails_s:.3f} + {bridge_s:.3f}",
        "srt_last_cue_end_s": round(srt_end_s, 3),
        "output_duration_s": round(output_duration_s, 3),
        "checks": {
            "voice_plus_tails_plus_bridge_equals_film":
                abs(voice_s + tails_s + bridge_s - film_s) < 0.002,
            "output_matches_film": abs(output_duration_s - film_s) <= 1 / 30 + 0.002,
            "no_caption_in_the_silent_bridge": all(
                not (row["type"] == "insert"
                     and any(p["start_s"] < row["end_s"] and p["start_s"] >= row["start_s"]
                             for p in placed))
                for row in rows),
        },
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--out-name", default="easel")
    parser.add_argument("--variant", choices=("easel", "eras"), default="easel",
                        help="eras keeps the baseline clips, captions and receipts untouched")
    parser.add_argument("--motion-video", type=Path,
                        help="one huashu eras render used as the complete visual track")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()
    config = _yaml(project / "project.yaml")
    paths = _variant_paths(args.variant)
    voice = json.loads((project / "receipts" / "voice-lines.json").read_text(encoding="utf-8"))
    beat_lines = len(voice["lines"])
    lines = _voice_lines(voice, args.variant)
    segments = _timeline(project, beat_lines, args.variant)

    # A project that declares a presenter opening must actually carry it: the
    # contract is the difference between "he happened to be in this build" and
    # "every build of this variant has him".
    import presenter_opening
    presenter_contract = presenter_opening.load_contract(project)
    opening_issues = presenter_opening.problems(
        presenter_contract, project, segments, args.variant, voice)
    if opening_issues:
        print(json.dumps({"status": "BLOCKED", "reason": "presenter opening",
                          "problems": opening_issues}, ensure_ascii=False))
        return 4

    presenter_s = sum(float(segment["duration"]) for segment in segments
                      if segment["type"] == "presenter")

    clips = []
    for segment in segments:
        clip = _clip_path(project, segment["clip"], args.variant)
        if not clip.is_file():
            print(json.dumps({"status": "BLOCKED", "reason": f"missing clip {clip}"},
                             ensure_ascii=False))
            return 4
        try:
            ffprobe_json(clip)
        except RuntimeError as exc:
            # A render still writing its MP4 has no moov atom yet. Without this
            # probe the upstream assembler dies with an opaque "Invalid data
            # found when processing input" hundreds of frames in.
            print(json.dumps({"status": "BLOCKED",
                              "reason": f"clip is not a complete media file: {clip.name}",
                              "detail": str(exc)}, ensure_ascii=False))
            return 4
        segment["path"] = clip
        clips.append(clip)

    narration, placed = _place_narration(project, lines, segments, target_dir=paths["work"])
    srt = _write_srt(project, lines, placed, target=paths["srt"])
    narration, bgm = _mix_bgm(project, narration, out_dir=paths["work"],
                              bed_offset_s=presenter_s)
    motion_video = args.motion_video.resolve() if args.motion_video else None
    if motion_video is not None and not motion_video.is_file():
        raise SystemExit(f"missing full-film motion render: {motion_video}")

    storyboard = {
        "size": config.get("format", "1080x1920"),
        "engine": "easel",
        "pad_mode": "trim",
        "narration": str(narration),
        "subtitle": str(srt),
        "voice_provider": "minimax-mplan",
        "shots": _storyboard_shots(segments, motion_video),
    }
    storyboard_path = project / paths["work"] / "storyboard.json"
    storyboard_path.parent.mkdir(parents=True, exist_ok=True)
    storyboard_path.write_text(json.dumps(storyboard, indent=2, ensure_ascii=False),
                               encoding="utf-8")

    total_s = sum(float(segment["duration"]) for segment in segments)
    generated_s = sum(float(segment["duration"]) for segment in segments
                      if segment["type"] == "insert" and segment.get("generated"))
    ratio = generated_s / total_s if total_s else 0.0
    if ratio >= MAX_GENERATED_RATIO:
        print(json.dumps({"status": "BLOCKED",
                          "reason": f"generated share {ratio:.1%} is not below "
                                    f"{MAX_GENERATED_RATIO:.0%}"}, ensure_ascii=False))
        return 6
    silent_claims = [segment for segment in segments
                     if segment["type"] == "insert" and segment.get("claim_bearing")]
    if silent_claims:
        print(json.dumps({"status": "BLOCKED",
                          "reason": "an insert may not be claim-bearing"}, ensure_ascii=False))
        return 6

    style = _caption_style(config["account_slug"])
    from assemble_easel import run as assemble
    result = assemble(project, out_name=args.out_name, strict_captions=True,
                      storyboard_path=storyboard_path,
                      caption_style=style["style"],
                      caption_font_size=style["font_size"],
                      caption_margin_v=style["margin_v"])
    if result.get("status") != "OK":
        print(json.dumps(result, ensure_ascii=False))
        return 5

    output = Path(result["video"])
    measured = measure_video(output)
    meta = ffprobe_json(output)
    audio = next((s for s in meta.get("streams", []) if s.get("codec_type") == "audio"), {})
    visual = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), {})

    segment_rows = []
    grammars = set()
    for segment in segments:
        row = {"type": segment["type"],
               "clip": f"project://{segment['path'].relative_to(project).as_posix()}",
               "duration_s": float(segment["duration"]),
               "clip_sha256": _sha(segment["path"])}
        if segment["type"] == "beat":
            spec = project / "motion" / "specs" / f"{segment['clip']}.json"
            spec_doc = json.loads(spec.read_text(encoding="utf-8"))
            grammars.add(spec_doc.get("grammar", ""))
            row.update({"line": int(segment["line"]),
                        "spec": f"project://motion/specs/{spec.name}",
                        "spec_sha256": _sha(spec),
                        "grammar": spec_doc.get("grammar")})
        elif segment["type"] == "presenter":
            # A generated face is drawn, not filmed, and it must say so on the row
            # rather than hide inside the insert accounting.
            presenter_line = lines[PRESENTER_LINE]
            row.update({"line": PRESENTER_LINE,
                        "role": "AI digital-human opening",
                        "text": presenter_line["text"],
                        "voice": presenter_line.get("voice"),
                        "generated": True,
                        "claim_bearing": False,
                        "labelled_ai_synthesised": True,
                        "speech_text_verified":
                            bool(presenter_line.get("speech_text_verified", False))})
        else:
            row.update({"generated": segment.get("generated"),
                        "claim_bearing": bool(segment.get("claim_bearing", False)),
                        "role": "claim-free insert"})
        segment_rows.append(row)

    receipt = {
        "schema": SAMPLE_SCHEMA,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "package_id": project.name,
        "content_type": "DEFINITIONAL_EXPLAINER",
        "claim_bearing": False,
        "external_skill": {
            "name": "huashu-art-motion",
            "version": "1.2.0",
            "license": "MIT",
            "engine": "scripts/engine/render.py",
            "grammar": sorted(g for g in grammars if g),
            "windows_adapter": "Playwright channel fallback (chrome/msedge) and PYTHONUTF8=1 for spec JSON",
        },
        "timeline": {"total_s": round(total_s, 3), "segments": len(segments),
                     "beats": sum(1 for s in segments if s["type"] == "beat"),
                     "inserts": sum(1 for s in segments if s["type"] == "insert"),
                     "presenter": sum(1 for s in segments if s["type"] == "presenter")},
        "generated_media": {
            "seconds": round(generated_s, 3),
            "ratio": round(ratio, 4),
            "cap": MAX_GENERATED_RATIO,
            "policy": "claim-free inserts only; deletes if it does not improve",
            # The cap governs inserts. The opening is a generated face on screen,
            # so it is declared here with its own ratio instead of being folded
            # into the insert budget and quietly passing the check.
            "ai_presenter": ({
                "seconds": round(presenter_s, 3),
                "ratio": round(presenter_s / total_s, 4),
                "kind": "AI digital human, MiniMax H3 Ref2VA",
                "claim_bearing": False,
                "labelled_ai_synthesised": True,
                "speech_text_verified": bool(
                    (voice.get("presenter") or {}).get("speech_text_verified", False)),
                "shot": (voice.get("presenter") or {}).get("shot"),
                "shot_sha256": (voice.get("presenter") or {}).get("shot_sha256"),
                "shot_receipt": (voice.get("presenter") or {}).get("shot_receipt"),
                "contract": ("project://motion/presenter/contract.json"
                             if presenter_contract else None),
                "outside_the_insert_cap": "founder-requested opening; declared, not exempted silently",
            } if presenter_s else None),
        },
        "segments": segment_rows,
        "bgm": bgm,
        "voice": {"provider": voice.get("voice", "speech-2.8-hd"),
                  "clone_alias": voice.get("clone_alias"),
                  "clone_id_hash": voice.get("clone_id_hash"),
                  "lines": voice["lines"],
                  "presenter": voice.get("presenter"),
                  "receipts": "project://receipts/voice-lines.json"},
        "captions": {"path": f"project://{paths['srt'].as_posix()}", "sha256": _sha(srt),
                     "style_source": f"config/accounts/{config['account_slug']}.json",
                     "cues": len(placed)},
        "visual_track": (
            {"mode": "full_film_eras",
             "path": f"project://{motion_video.relative_to(project).as_posix()}",
             "sha256": _sha(motion_video)}
            if motion_video is not None else {"mode": "beat_clips"}
        ),
        "output": {"path": f"project://{output.relative_to(project).as_posix()}",
                   "sha256": _sha(output),
                   "duration_s": float(meta["format"]["duration"]),
                   "width": visual.get("width"), "height": visual.get("height"),
                   "video_codec": visual.get("codec_name"),
                   "audio_codec": audio.get("codec_name") or None},
        "technical_qc": {
            "decodable": measured.decodable,
            "longest_black_run_s": measured.longest_black_run_s,
            "longest_freeze_run_s": measured.longest_freeze_run_s,
            "analysed_frames": measured.analysed_frames,
            "notes": list(measured.notes),
            "reasons": list(measured.reasons),
        },
        "red_lines": {
            "manual_recording": "none — pure code animation",
            "mouse_or_desktop": "none",
            "ai_generated_footage": (
                "generated inserts are claim-free and below the 10% cap; the "
                "eras opening is an AI digital human, labelled AI-synthesised and "
                "declared separately in generated_media.ai_presenter"
                if presenter_s else
                "generated inserts are claim-free and below the 10% cap"),
            "platform_url_claimed": False,
        },
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }
    receipt_path = project / paths["receipt"]
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    if args.variant == "eras":
        srt_end_s = max(p["start_s"] + p["duration_s"] for p in placed)
        reconciliation = _reconciliation(segments, placed, lines, srt_end_s,
                                         float(meta["format"]["duration"]))
        (receipt_path.parent / "timing-reconciliation.json").write_text(
            json.dumps(reconciliation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if not all(reconciliation["checks"].values()):
            print(json.dumps({"status": "BLOCKED",
                              "reconciliation": reconciliation["checks"]}, ensure_ascii=False))
            return 7
    receipt_path.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "OK", "output": receipt["output"],
                      "generated_ratio": ratio,
                      "qc": {"decodable": measured.decodable,
                             "freeze_s": measured.longest_freeze_run_s,
                             "black_s": measured.longest_black_run_s},
                      "receipt": paths["receipt"].as_posix()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
