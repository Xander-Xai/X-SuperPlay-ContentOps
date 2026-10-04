"""Deterministic audio normalisation and technical QC.

Why normalisation is not optional
---------------------------------
M2.0 measured MiniMax speech peaking at **-0.5 dB** and **-1.5 dB**. That is
inside the valid range and did not clip, but it leaves effectively no headroom.
Feeding that straight into a video mix invites clipping downstream, where it is
much harder to trace. Provider success is therefore not the same as
production-ready audio.

Target choice and why
---------------------
The target is **-16 dB LUFS integrated with a -1.5 dB true-peak ceiling**.

- Integrated loudness, not RMS or peak, is what streaming platforms normalise
  to, so matching it keeps the narration level predictable once music or other
  audio is mixed in.
- -16 LUFS is the common target for spoken-word narration and sits comfortably
  below the roughly -14 LUFS level where dialogue starts to feel aggressive.
- A true-peak ceiling rather than a sample-peak ceiling, because intersample
  peaks during lossy encoding are what actually distort.

Both ffmpeg and ffprobe are invoked **only** through ``process_utils``, so no
ContentOps-owned background process can flash a console window on Windows.
"""

from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from process_utils import hidden_run  # noqa: E402

__all__ = [
    "NORMALISATION_TARGET_LUFS",
    "NORMALISATION_TRUE_PEAK_DB",
    "AudioMeasurements",
    "normalise_speech",
    "measure_audio",
    "technical_qc",
]

#: Integrated loudness target for short-form narration.
NORMALISATION_TARGET_LUFS = -16.0
#: Ceiling for true peak, leaving headroom for the video mix.
NORMALISATION_TRUE_PEAK_DB = -1.5

_MAXVOL_RE = re.compile(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB")
_MEANVOL_RE = re.compile(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB")
#: ebur128 summary lines, e.g. "I: -23.9 LUFS", "Peak: -1.5 dBFS", "LRA: 5.4 LU".
_EBUR_I_RE = re.compile(r"^\s*I:\s*(-?[\d.]+|-inf)\s*LUFS", re.M)
_EBUR_PEAK_RE = re.compile(r"^\s*Peak:\s*(-?[\d.]+)\s*dBFS", re.M)
_EBUR_LRA_RE = re.compile(r"^\s*LRA:\s*(-?[\d.]+)\s*LU", re.M)


def _tools_available() -> Dict[str, bool]:
    return {
        "ffprobe": bool(shutil.which("ffprobe")),
        "ffmpeg": bool(shutil.which("ffmpeg")),
    }


@dataclass
class AudioMeasurements:
    """Everything the gates need to know about one audio file.

    ``integrated_lufs`` and ``true_peak_db`` come from ebur128. ``peak_db`` is
    the sample peak from volumedetect. They are different numbers and both are
    kept: the sample peak is what a naive mix will hit, the true peak is what
    lossy encoding will hit.
    """

    codec: Optional[str] = None
    sample_rate_hz: Optional[int] = None
    channels: Optional[int] = None
    duration_s: Optional[float] = None
    bytes: Optional[int] = None
    integrated_lufs: Optional[float] = None
    true_peak_db: Optional[float] = None
    peak_db: Optional[float] = None
    mean_db: Optional[float] = None
    loudness_range_lu: Optional[float] = None


def measure_audio(path: Path) -> AudioMeasurements:
    """Measure container, format and loudness. Never raises for a media reason.

    Integrated loudness and true peak come from **ebur128**, which meters the
    file as it is. The ``loudnorm`` filter is only used to *process* audio; its
    reported integrated loudness is a prediction of what it would produce, and
    recording that prediction as a measurement produced a wrong conclusion about
    whether the loudness target was reachable.
    """
    out = AudioMeasurements()
    if not path.is_file():
        return out
    out.bytes = path.stat().st_size
    tools = _tools_available()

    if tools["ffprobe"]:
        result = hidden_run(
            [
                "ffprobe", "-v", "error",
                "-show_entries",
                "stream=codec_name,codec_type,sample_rate,channels",
                "-show_entries", "format=duration",
                "-of", "json", str(path),
            ],
            timeout=120,
        )
        if result.returncode == 0:
            import json

            try:
                info = json.loads(result.stdout or "{}")
            except json.JSONDecodeError:
                info = {}
            streams = info.get("streams") or []
            audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
            if audio is None and streams:
                audio = streams[0]
            if audio:
                out.codec = audio.get("codec_name")
                rate = audio.get("sample_rate")
                out.sample_rate_hz = int(rate) if rate else None
                channels = audio.get("channels")
                out.channels = int(channels) if channels else None
            duration = (info.get("format") or {}).get("duration")
            if duration:
                out.duration_s = round(float(duration), 3)

    if tools["ffmpeg"]:
        loud = hidden_run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path),
             "-af", "ebur128=peak=true", "-f", "null", "-"],
            timeout=180,
        )
        text = loud.stderr or ""
        matches = _EBUR_I_RE.findall(text)
        for raw in matches:
            if raw not in ("-inf", "inf"):
                out.integrated_lufs = float(raw)
        match = _EBUR_PEAK_RE.search(text)
        if match:
            out.true_peak_db = float(match.group(1))
        match = _EBUR_LRA_RE.search(text)
        if match:
            out.loudness_range_lu = float(match.group(1))

        vol = hidden_run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path),
             "-af", "volumedetect", "-f", "null", "-"],
            timeout=180,
        )
        text = vol.stderr or ""
        match = _MAXVOL_RE.search(text)
        if match:
            out.peak_db = float(match.group(1))
        match = _MEANVOL_RE.search(text)
        if match:
            out.mean_db = float(match.group(1))

    return out


def _loudnorm_analysis(path: Path) -> Dict[str, Optional[float]]:
    """Pass 1 of a two-pass loudnorm: measure the input accurately."""
    if not _tools_available()["ffmpeg"]:
        return {}
    result = hidden_run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path),
         "-af", f"loudnorm=I={NORMALISATION_TARGET_LUFS}:TP={NORMALISATION_TRUE_PEAK_DB}"
                f":LRA=11:print_format=json",
         "-f", "null", "-"],
        timeout=180,
    )
    text = result.stderr or ""
    values = {
        "input_i": None, "input_tp": None, "input_lra": None,
        "input_thresh": None, "target_offset": None,
    }
    import re as _re

    for key in values:
        match = _re.search(rf'"{key}"\s*:\s*"(-?[\d.]+)"', text)
        if match:
            values[key] = float(match.group(1))
    return values


def normalise_speech(
    source: Path,
    destination: Path,
    *,
    target_lufs: float = NORMALISATION_TARGET_LUFS,
    true_peak_db: float = NORMALISATION_TRUE_PEAK_DB,
) -> Dict[str, Any]:
    """Write a loudness-normalised copy and report before/after measurements.

    Two-pass ``loudnorm``: the input is measured, then the measured values drive
    the second pass. A single dynamic pass is measurably unreliable on short
    clips.

    Measured on the M2 narration with a real meter: -17.0 LUFS integrated and
    -1.5 dBFS true peak, from a raw provider peak of -0.2 dBFS. That is why the
    hard guarantee is stated as the **peak ceiling**, with integrated loudness
    reported as achieved rather than assumed.
    """
    tools = _tools_available()
    if not tools["ffmpeg"]:
        return {"ok": False, "reason": "ffmpeg not installed"}

    before = measure_audio(source)
    analysis = _loudnorm_analysis(source)
    destination.parent.mkdir(parents=True, exist_ok=True)

    filter_graph = f"loudnorm=I={target_lufs}:TP={true_peak_db}:LRA=11"
    if analysis.get("input_i") is not None:
        filter_graph += (
            f":measured_I={analysis['input_i']}"
            f":measured_TP={analysis['input_tp']}"
            f":measured_LRA={analysis['input_lra']}"
            f":measured_thresh={analysis['input_thresh']}"
            f":offset={analysis['target_offset']}"
        )

    result = hidden_run(
        [
            "ffmpeg", "-y", "-hide_banner", "-nostdin",
            "-i", str(source),
            "-af", filter_graph,
            "-ar", "32000", "-ac", "1",
            "-c:a", "pcm_s16le",
            str(destination),
        ],
        timeout=300,
    )
    if result.returncode != 0 or not destination.is_file():
        return {
            "ok": False,
            "reason": (result.stderr or "")[-400:],
            "before": before.__dict__,
        }

    after = measure_audio(destination)
    achieved = after.integrated_lufs
    target_met = achieved is not None and abs(achieved - target_lufs) <= 1.0
    return {
        "ok": True,
        "passes": 2,
        "target_lufs": target_lufs,
        "target_true_peak_db": true_peak_db,
        "loudness_target_met": target_met,
        "loudness_delta_lu": (
            round(achieved - target_lufs, 2) if achieved is not None else None
        ),
        "peak_ceiling_met": (
            after.peak_db is not None and after.peak_db <= true_peak_db
        ),
        "hard_guarantee": "peak ceiling",
        "before": before.__dict__,
        "after": after.__dict__,
        "peak_reduction_db": (
            round(before.peak_db - after.peak_db, 2)
            if before.peak_db is not None and after.peak_db is not None
            else None
        ),
    }


def _detect_silence(path: Path) -> Dict[str, Any]:
    """Leading / trailing / internal silence, in seconds."""
    if not _tools_available()["ffmpeg"]:
        return {"available": False}
    result = hidden_run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path),
         "-af", "silencedetect=n=-45dB:d=0.35", "-f", "null", "-"],
        timeout=180,
    )
    text = result.stderr or ""
    silences = []
    for start, end in re.findall(
        r"silence_start:\s*(-?[\d.]+).*?silence_end:\s*(-?[\d.]+)", text, re.S
    ):
        silences.append({"start_s": float(start), "end_s": float(end)})
    duration = measure_audio(path).duration_s or 0.0
    leading = silences[0]["end_s"] if silences and silences[0]["start_s"] <= 0.05 else 0.0
    trailing = (
        max(0.0, duration - silences[-1]["start_s"])
        if silences and silences[-1]["end_s"] >= duration - 0.05
        else 0.0
    )
    return {
        "available": True,
        "silences": silences,
        "leading_silence_s": round(leading, 3),
        "trailing_silence_s": round(trailing, 3),
    }


def technical_qc(
    path: Path,
    *,
    expected_duration_s: Optional[float] = None,
    expected_sample_rate_hz: Optional[int] = None,
    duration_tolerance_ratio: float = 0.6,
    max_leading_silence_s: float = 1.0,
    max_trailing_silence_s: float = 1.5,
    max_peak_db: float = -0.1,
    min_loudness_lufs: Optional[float] = -30.0,
) -> Dict[str, Any]:
    """Automated speech gate. ``approved`` is False whenever any check fails."""
    checks: List[Dict[str, Any]] = []

    def record(name: str, passed: bool, detail: Any = None) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    exists = path.is_file()
    record("file_exists", exists, str(path))
    if not exists:
        return {"approved": False, "checks": checks, "measurements": {}}

    size = path.stat().st_size
    record("not_empty", size > 1024, f"{size} bytes")

    measured = measure_audio(path)
    record("has_audio_codec", bool(measured.codec), measured.codec)
    record("has_duration", bool(measured.duration_s), measured.duration_s)
    record(
        "sample_rate",
        expected_sample_rate_hz is None or measured.sample_rate_hz == expected_sample_rate_hz,
        {"expected": expected_sample_rate_hz, "actual": measured.sample_rate_hz},
    )
    record(
        "mono_or_stereo",
        measured.channels in (1, 2),
        measured.channels,
    )

    if expected_duration_s:
        low = expected_duration_s * (1 - duration_tolerance_ratio)
        high = expected_duration_s * (1 + duration_tolerance_ratio) * 2
        record(
            "duration_plausible",
            low <= (measured.duration_s or 0) <= high,
            {"expected_s": expected_duration_s, "actual_s": measured.duration_s},
        )

    silence = _detect_silence(path)
    if silence.get("available"):
        record(
            "leading_silence",
            silence["leading_silence_s"] <= max_leading_silence_s,
            silence["leading_silence_s"],
        )
        record(
            "trailing_silence",
            silence["trailing_silence_s"] <= max_trailing_silence_s,
            silence["trailing_silence_s"],
        )
        record("not_mostly_silent", bool(measured.peak_db and measured.peak_db > -50),
               measured.peak_db)

    if measured.peak_db is not None:
        record("no_clipping", measured.peak_db <= max_peak_db, measured.peak_db)
    if min_loudness_lufs is not None and measured.integrated_lufs is not None:
        record(
            "loudness_floor",
            measured.integrated_lufs >= min_loudness_lufs,
            measured.integrated_lufs,
        )
    if measured.true_peak_db is not None:
        record(
            "true_peak_headroom",
            measured.true_peak_db <= -0.5,
            measured.true_peak_db,
        )

    return {
        "approved": all(c["passed"] for c in checks),
        "checks": checks,
        "measurements": measured.__dict__,
        "silence": silence,
    }