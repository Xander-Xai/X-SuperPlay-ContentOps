#!/usr/bin/env python3
"""Segmented IndexTTS2.5 narration renderer.

Why this exists
---------------
The stock ``indextts/infer_v2_5.py`` CLI exposes no sampling or emotion
controls, so a single CLI call can only use the model's default path.  That
path is also fed the **entire** narration in one inference.  Measured against
the CAM++ speaker-identity metric, long single-shot synthesis drifts away from
the reference speaker:

    text length   method              CAM++ vs reference
    ~70 chars     single shot         0.886
    504 chars     single shot         0.714   <-- below the 0.82 floor
    504 chars     segmented (22 x ~23) 0.902
    504 chars     segmented (14 x ~36) 0.827

The drift is a property of the long utterance, not of the sampling parameters,
the reference file, or the output duration -- all three were ruled out by
controlled probes recorded in ``voice-identity-diagnosis.json``.

This module therefore splits the approved narration into short segments, runs
each segment through the IndexTTS2.5 Python API with the tested IT25-PROD-01
sampling profile, trims per-segment silence, and joins the result with a small
fixed gap.  Speaker identity stays stable because the model never has to carry
conditioning across a long horizon.
"""

from __future__ import annotations

import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


# IT25-PROD-01 sampling with the E01 low-variance profile that measured best
# in the closed-loop identity experiment.  Kept identical to the experiment so
# an approved script renders reproducibly.
SAMPLING: dict[str, Any] = {
    "do_sample": True,
    "top_p": 0.75,
    "top_k": 20,
    "temperature": 0.65,
    "num_beams": 1,
    "length_penalty": 0.0,
    "repetition_penalty": 10.0,
    "max_mel_tokens": 1500,
    "max_text_tokens_per_segment": 120,
    "interval_silence": 0,
    "duration_factor": 1.0,
    "use_random": False,
    "verbose": False,
}
BASE_SEED = 20260831
MAX_SEGMENT_CHARS = 36
SEGMENT_GAP_SECONDS = 0.10
TAIL_PAD_SECONDS = 0.05
TRIM_THRESHOLD_RATIO = 0.06
SAMPLE_RATE = 22050
# H3 is a scene-level audio-conditioned generator.  A segment that lands on
# 15.000 seconds is not safe: codec/container rounding can push it over the
# model's hard 15-second ceiling.  Keep a small safety margin and use a strict
# ``<`` comparison everywhere in the workflow.
MAX_SEGMENT_AUDIO_SECONDS = 14.90
MIN_SEGMENT_AUDIO_SECONDS = 4.0
MAX_SEGMENT_SPLIT_DEPTH = 8

_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？；!?;])")


def segment_narration(text: str, max_chars: int = MAX_SEGMENT_CHARS) -> list[str]:
    """Split narration at sentence boundaries, then pack into short segments.

    Sentence boundaries are preferred so prosody stays natural.  A sentence
    longer than ``max_chars`` is hard-wrapped at its internal comma or
    enumeration punctuation rather than being truncated.
    """

    clean = " ".join(str(text or "").split())
    if not clean:
        return []
    sentences = [item.strip() for item in _SENTENCE_BOUNDARY.split(clean) if item.strip()]
    segments: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                segments.append(current)
                current = ""
            pieces = [item for item in re.split(r"(?<=[，,、])", sentence) if item]
            buffer = ""
            for piece in pieces:
                # A single clause can still exceed the budget; split it flat.
                while len(piece) > max_chars:
                    if buffer:
                        segments.append(buffer)
                        buffer = ""
                    segments.append(piece[:max_chars])
                    piece = piece[max_chars:]
                if len(buffer) + len(piece) <= max_chars:
                    buffer += piece
                else:
                    if buffer:
                        segments.append(buffer)
                    buffer = piece
            if buffer:
                segments.append(buffer)
            continue
        if len(current) + len(sentence) <= max_chars:
            current += sentence
        else:
            if current:
                segments.append(current)
            current = sentence
    if current:
        segments.append(current)
    return segments


def _split_index(text: str) -> int:
    """Find a lossless, speech-friendly split close to the midpoint."""

    value = str(text)
    if len(value) < 2:
        raise ValueError("cannot split a one-character narration segment")
    midpoint = len(value) / 2.0
    # Keep punctuation with the clause on its left.  Searching by distance
    # makes repeated retry splits deterministic while preferring Chinese
    # phrase boundaries over a flat character cut.
    boundaries = [
        index + 1
        for index, char in enumerate(value)
        if char in "。！？；!?;，,、：:"
        and 0 < index + 1 < len(value)
    ]
    if boundaries:
        return min(boundaries, key=lambda index: (abs(index - midpoint), index))
    whitespace = [
        match.end()
        for match in re.finditer(r"\s+", value)
        if 0 < match.end() < len(value)
    ]
    if whitespace:
        return min(whitespace, key=lambda index: (abs(index - midpoint), index))
    return max(1, min(len(value) - 1, int(round(midpoint))))


def split_overlong_text(text: str) -> tuple[str, str]:
    """Split an overlong TTS take without dropping or rewriting characters."""

    value = str(text)
    index = _split_index(value)
    left, right = value[:index], value[index:]
    if not left or not right or left + right != value:
        raise ValueError("duration retry split was not lossless")
    return left, right


def segment_duration_passes(seconds: float, max_seconds: float = MAX_SEGMENT_AUDIO_SECONDS) -> bool:
    """Return whether a rendered take meets the H3 duration interval."""

    try:
        value = float(seconds)
        limit = float(max_seconds)
    except (TypeError, ValueError):
        return False
    return math.isfinite(value) and MIN_SEGMENT_AUDIO_SECONDS <= value and math.isfinite(limit) and value < limit


def refine_segments_by_duration(
    initial_segments: Sequence[str],
    render_segment: Callable[[str, int, int], Mapping[str, Any]],
    *,
    max_seconds: float = MAX_SEGMENT_AUDIO_SECONDS,
    max_split_depth: int = MAX_SEGMENT_SPLIT_DEPTH,
) -> dict[str, Any]:
    """Render and recursively split takes until every take is ``< max_seconds``.

    ``render_segment`` is called as ``(text, origin_index, split_depth)`` and
    must return a mapping containing ``duration_seconds`` plus its artifact
    metadata (normally ``audio``/``audio_sha256``).  Overlong artifacts are
    retained in the returned ``split_events`` as rejected evidence, while
    only bounded artifacts appear in ``segments``.  The function never
    changes the text: concatenating all accepted texts reproduces the exact
    concatenation of the initial segments.
    """

    limit = float(max_seconds)
    if not math.isfinite(limit) or limit <= 0:
        raise ValueError("max_seconds must be a positive finite number")
    if max_split_depth < 0:
        raise ValueError("max_split_depth must be non-negative")
    queue: list[tuple[str, int, int]] = [
        (str(text), index, 0)
        for index, text in enumerate(initial_segments)
        if str(text)
    ]
    if not queue:
        raise ValueError("duration-bounded segmentation received no text")
    accepted: list[dict[str, Any]] = []
    split_events: list[dict[str, Any]] = []
    while queue:
        text, origin_index, depth = queue.pop(0)
        result = dict(render_segment(text, origin_index, depth))
        try:
            duration = float(result.get("duration_seconds"))
        except (TypeError, ValueError) as error:
            raise ValueError(f"rendered segment has no numeric duration: {text!r}") from error
        result.update(
            {
                "text": text,
                "chars": len(text),
                "origin_segment_index": origin_index,
                "split_depth": depth,
                "duration_seconds": round(duration, 6),
            }
        )
        if segment_duration_passes(duration, limit):
            result["status"] = "accepted"
            accepted.append(result)
            continue
        if math.isfinite(duration) and 0 < duration < MIN_SEGMENT_AUDIO_SECONDS:
            raise ValueError(
                f"rendered segment is below the H3 minimum ({duration:.6f}s < {MIN_SEGMENT_AUDIO_SECONDS:.6f}s): {text!r}"
            )
        if depth >= max_split_depth or len(text) < 2:
            raise ValueError(
                "IndexTTS segment is outside the H3 duration interval "
                f"[{MIN_SEGMENT_AUDIO_SECONDS:.6f}s, {limit:.6f}s) after {depth} splits: {text!r}"
            )
        left, right = split_overlong_text(text)
        result["status"] = "split_required"
        result["duration_limit_seconds"] = limit
        result["split_into"] = [left, right]
        split_events.append(result)
        # Insert left then right at the head so the final accepted list keeps
        # the source narration order.
        queue[0:0] = [(left, origin_index, depth + 1), (right, origin_index, depth + 1)]
    if "".join(item["text"] for item in accepted) != "".join(str(item) for item in initial_segments):
        raise ValueError("duration-bounded segmentation changed the approved narration text")
    return {
        "segments": accepted,
        "split_events": split_events,
        "max_segment_audio_seconds": limit,
        "strict_less_than": True,
    }


# Readable aliases for callers that describe this operation as a hard gate.
bound_segments_by_duration = refine_segments_by_duration
split_until_duration = refine_segments_by_duration


def _seed_all(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except Exception:
        pass
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


def _trim_silence(samples: Any, sample_rate: int, np: Any) -> Any:
    """Trim leading/trailing near-silence so segments join without dead air."""

    window = max(1, int(0.01 * sample_rate))
    if len(samples) <= window:
        return samples
    frames = np.abs(samples[: len(samples) - (len(samples) % window)]).reshape(-1, window)
    envelope = frames.max(axis=1)
    if envelope.size == 0 or envelope.max() <= 0:
        return samples
    threshold = max(float(envelope.max()) * TRIM_THRESHOLD_RATIO, 1e-4)
    active = np.flatnonzero(envelope > threshold)
    if active.size == 0:
        return samples
    start = max(0, int(active[0]) * window - int(0.02 * sample_rate))
    stop = min(len(samples), (int(active[-1]) + 1) * window + int(TAIL_PAD_SECONDS * sample_rate))
    return samples[start:stop]


def render(
    *,
    text: str,
    reference: Path,
    output: Path,
    index_root: Path,
    tts_python: Path | None = None,
) -> dict[str, Any]:
    """Render ``text`` to ``output`` with per-segment synthesis.

    Returns a receipt describing the segmentation and the exact parameters.
    The caller owns gate decisions; this function only reports what it did.
    """

    segments = segment_narration(text)
    if not segments:
        raise ValueError("narration text produced no segments")
    if not reference.is_file():
        raise FileNotFoundError(f"voice reference does not exist: {reference}")

    output.parent.mkdir(parents=True, exist_ok=True)
    work_dir = output.parent / f".{output.stem}-segments"
    work_dir.mkdir(parents=True, exist_ok=True)
    for stale in work_dir.glob("*.wav"):
        stale.unlink()

    payload = {
        "index_root": str(index_root),
        "reference": str(reference),
        "segments": segments,
        "sampling": SAMPLING,
        "base_seed": BASE_SEED,
        "work_dir": str(work_dir),
        "output": str(output),
        "sample_rate": SAMPLE_RATE,
        "gap_seconds": SEGMENT_GAP_SECONDS,
        "max_segment_audio_seconds": MAX_SEGMENT_AUDIO_SECONDS,
        "max_split_depth": MAX_SEGMENT_SPLIT_DEPTH,
        "receipt": str(work_dir / "segment-receipt.json"),
    }
    try:
        from media_tools import resolve_tool
    except ImportError:  # imported as scripts.segmented_narration
        try:
            from scripts.media_tools import resolve_tool
        except ImportError:
            resolve_tool = None
    if resolve_tool is not None:
        try:
            payload["ffmpeg"] = resolve_tool("ffmpeg")
        except RuntimeError:
            payload["ffmpeg"] = ""
    driver = work_dir / "_render_driver.py"
    driver.write_text(_DRIVER_SOURCE, encoding="utf-8")
    spec = work_dir / "_render_spec.json"
    spec.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    python = str(tts_python) if tts_python else str(index_root / ".venv" / "Scripts" / "python.exe")
    if not Path(python).is_file():
        raise FileNotFoundError(f"pinned TTS python is missing: {python}")
    result = subprocess.run(
        [python, str(driver), str(spec)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0 or not output.is_file():
        raise RuntimeError(
            "segmented narration render failed: "
            + json.dumps(
                {"exit_code": result.returncode, "stderr_tail": (result.stderr or "")[-1500:]},
                ensure_ascii=False,
            )
        )
    receipt_path = work_dir / "segment-receipt.json"
    receipt: dict[str, Any] = {}
    if receipt_path.is_file():
        try:
            value = json.loads(receipt_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                receipt = value
        except (OSError, json.JSONDecodeError):
            receipt = {}
    accepted = receipt.get("segments") if isinstance(receipt.get("segments"), list) else []
    split_events = receipt.get("split_events") if isinstance(receipt.get("split_events"), list) else []
    max_duration = max(
        (float(item.get("duration_seconds", 0) or 0) for item in accepted if isinstance(item, dict)),
        default=0.0,
    )
    if accepted and any(not segment_duration_passes(item.get("duration_seconds", 0)) for item in accepted if isinstance(item, dict)):
        raise RuntimeError("segmented narration receipt contains an unbounded IndexTTS take")
    if not accepted:
        # A child that produced an output but no auditable receipt is not
        # promotable: the workflow must know which text each audio take owns.
        raise RuntimeError("segmented narration did not produce a segment receipt")
    return {
        "mode": "segmented",
        "segment_count": len(accepted),
        "max_segment_chars": MAX_SEGMENT_CHARS,
        "max_segment_audio_seconds": MAX_SEGMENT_AUDIO_SECONDS,
        "max_rendered_segment_seconds": round(max_duration, 6),
        "split_count": len(split_events),
        "segments": accepted,
        "split_events": split_events,
        "receipt": str(receipt_path),
        "segment_duration_policy": receipt.get(
            "segment_duration_policy",
            {
                "min_seconds": 4.0,
                "max_seconds": MAX_SEGMENT_AUDIO_SECONDS,
                "comparison": "strictly-less-than",
            },
        ),
        "gap_seconds": SEGMENT_GAP_SECONDS,
        "base_seed": BASE_SEED,
        "sampling": SAMPLING,
        "stdout_tail": (result.stdout or "")[-1200:],
    }


_DRIVER_SOURCE = '''"""Child process: runs inside the pinned IndexTTS2.5 environment."""

import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf


def seed_all(seed):
    random.seed(seed)
    np.random.seed(seed)
    import torch
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def trim(samples, rate):
    window = max(1, int(0.01 * rate))
    if len(samples) <= window:
        return samples
    usable = len(samples) - (len(samples) % window)
    frames = np.abs(samples[:usable]).reshape(-1, window)
    envelope = frames.max(axis=1)
    if envelope.size == 0 or envelope.max() <= 0:
        return samples
    threshold = max(float(envelope.max()) * 0.06, 1e-4)
    active = np.flatnonzero(envelope > threshold)
    if active.size == 0:
        return samples
    start = max(0, int(active[0]) * window - int(0.02 * rate))
    stop = min(len(samples), (int(active[-1]) + 1) * window + int(0.05 * rate))
    return samples[start:stop]


def split_text(text):
    value = str(text)
    if len(value) < 2:
        raise RuntimeError("an overlong one-character IndexTTS segment cannot be split")
    midpoint = len(value) / 2.0
    boundaries = [
        index + 1
        for index, char in enumerate(value)
        if char in "。！？；!?;，,、：:" and 0 < index + 1 < len(value)
    ]
    if boundaries:
        index = min(boundaries, key=lambda item: (abs(item - midpoint), item))
    else:
        spaces = [match.end() for match in re.finditer(r"\\s+", value) if 0 < match.end() < len(value)]
        index = min(spaces, key=lambda item: (abs(item - midpoint), item)) if spaces else max(1, min(len(value) - 1, int(round(midpoint))))
    left, right = value[:index], value[index:]
    if not left or not right or left + right != value:
        raise RuntimeError("duration retry split changed the narration text")
    return left, right


def normalize_samples(path, ffmpeg, rate):
    """Return mono samples at the fixed workflow rate without tempo changes."""
    source = Path(path)
    if ffmpeg:
        normalized_path = source.with_name(source.stem + "-normalized.wav")
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
             "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le", str(normalized_path)],
            check=True,
        )
        source = normalized_path
    samples, file_rate = sf.read(str(source))
    if getattr(samples, "ndim", 1) > 1:
        samples = samples.mean(axis=1)
    samples = np.asarray(samples, dtype=np.float32)
    if int(file_rate) != int(rate) and len(samples) > 1:
        target_length = max(1, int(round(len(samples) * float(rate) / float(file_rate))))
        source_x = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
        target_x = np.linspace(0.0, 1.0, num=target_length, endpoint=False)
        samples = np.interp(target_x, source_x, samples).astype(np.float32)
    return samples, int(rate)


def main():
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    index_root = Path(spec["index_root"])
    reference = Path(spec["reference"])
    work_dir = Path(spec["work_dir"])
    sampling = dict(spec["sampling"])
    base_seed = int(spec["base_seed"])
    rate = int(spec["sample_rate"])
    gap = float(spec["gap_seconds"])
    limit = float(spec.get("max_segment_audio_seconds", 14.9))
    max_depth = int(spec.get("max_split_depth", 8))
    ffmpeg = str(spec.get("ffmpeg") or "")

    sys.path.insert(0, str(index_root))
    from indextts.infer_v2_5 import IndexTTS2

    seed_all(base_seed)
    tts = IndexTTS2(
        cfg_path=str(index_root / "checkpoints" / "config.yaml"),
        model_dir=str(index_root / "checkpoints"),
        use_bf16=True,
        use_cuda_kernel=False,
        use_deepspeed=False,
        use_qwen_emo=True,
    )

    pending = [(str(text), index, 0) for index, text in enumerate(spec["segments"]) if str(text)]
    accepted = []
    split_events = []
    pieces = []
    attempt = 0
    while pending:
        text, origin_index, depth = pending.pop(0)
        raw = work_dir / f"seg-attempt-{attempt:04d}.wav"
        raw.unlink(missing_ok=True)
        seed_all(base_seed + attempt)
        tts.infer(
            spk_audio_prompt=str(reference),
            text=text,
            output_path=str(raw),
            lang="ZH",
            emo_audio_prompt=None,
            emo_alpha=0.0,
            use_emo_text=False,
            emo_text=None,
            **sampling,
        )
        if not raw.is_file():
            raise RuntimeError("IndexTTS did not produce the requested segment WAV")
        samples, normalized_rate = normalize_samples(raw, ffmpeg, rate)
        trimmed = trim(samples, normalized_rate)
        duration = len(trimmed) / float(normalized_rate or 1)
        record = {
            "text": text,
            "chars": len(text),
            "origin_segment_index": origin_index,
            "split_depth": depth,
            "attempt": attempt,
            "duration_seconds": round(duration, 6),
            "sample_rate": normalized_rate,
            "channels": 1,
            "audio_sha256": "",
        }
        if not math.isfinite(duration) or duration <= 0:
            raise RuntimeError("IndexTTS produced an empty segment WAV")
        if duration >= limit:
            if depth >= max_depth or len(text) < 2:
                raise RuntimeError(
                    "IndexTTS segment remains at or above the strict duration limit "
                    f"({duration:.6f}s >= {limit:.6f}s): {text!r}"
                )
            left, right = split_text(text)
            record.update({"status": "split_required", "duration_limit_seconds": limit, "split_into": [left, right], "audio": str(raw)})
            split_events.append(record)
            pending[0:0] = [(left, origin_index, depth + 1), (right, origin_index, depth + 1)]
            attempt += 1
            continue
        accepted_path = work_dir / f"accepted-{len(accepted):04d}.wav"
        sf.write(str(accepted_path), trimmed, normalized_rate, subtype="PCM_16")
        record.update({"status": "accepted", "audio": str(accepted_path)})
        # Hash after the fixed-rate PCM write so the receipt binds the exact
        # waveform that is concatenated into the final narration.
        import hashlib
        digest = hashlib.sha256()
        with accepted_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        record["audio_sha256"] = digest.hexdigest()
        accepted.append(record)
        pieces.append(trimmed)
        pieces.append(np.zeros(int(gap * normalized_rate), dtype=np.float32))
        print("rendered bounded segment %d (source %d, split depth %d, %.3fs)" % (len(accepted), origin_index + 1, depth, duration), flush=True)
        attempt += 1

    if not accepted:
        raise RuntimeError("IndexTTS produced no bounded segment")
    merged = np.concatenate(pieces[:-1]) if len(pieces) > 1 else pieces[0]
    sf.write(spec["output"], merged, rate, subtype="PCM_16")
    receipt = {
        "schema_version": 1,
        "mode": "segmented-duration-bounded",
        "max_segment_audio_seconds": limit,
        "strict_less_than": True,
        "segment_duration_policy": {
            "min_seconds": 4.0,
            "max_seconds": limit,
            "comparison": "strictly-less-than",
            "rule": "every accepted IndexTTS take must satisfy 4.0 <= duration < max_seconds",
        },
        "segments": accepted,
        "split_events": split_events,
        "segment_count": len(accepted),
        "split_count": len(split_events),
        "output": str(spec["output"]),
        "output_duration_seconds": round(len(merged) / float(rate or 1), 6),
        "sample_rate": rate,
        "channels": 1,
        "gap_seconds": gap,
    }
    Path(spec["receipt"]).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    print(json.dumps({"segments": len(accepted), "splits": len(split_events), "samples": int(len(merged)), "rate": rate}))


if __name__ == "__main__":
    main()
'''


def __main__() -> int:  # pragma: no cover - manual smoke test helper
    print(
        json.dumps(
            {
                "module": "segmented_narration",
                "max_segment_chars": MAX_SEGMENT_CHARS,
                "max_segment_audio_seconds": MAX_SEGMENT_AUDIO_SECONDS,
                "strict_less_than": True,
            }
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(__main__())
