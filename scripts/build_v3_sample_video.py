#!/usr/bin/env python3
"""Render the v3 narration sample as a video, closing the narration -> video gap.

Why this exists
---------------
The v3 round (ADR-009) ends at three audio candidates. Everything downstream of
the audio -- storyboard, captions, composition, QC -- has so far only ever run on
the *locked* six-shot script with the v2/B narration. Nothing turned a v3
candidate into something watchable, so the Founder could hear the new delivery
but never see it in context.

This script is that bridge, and it is deliberately a **sample** bridge:

```
creator-script.json + narration-plan.json  (already verified by verify_creator_script)
        -> one v3 candidate WAV              (reused; zero provider calls)
        -> unit -> evidence-placement map    (from the creator script's source_paragraphs)
        -> per-unit durations                (measured from the audio, silence-refined)
        -> storyboard + SRT                  (one shot and one caption per unit)
        -> pinned Easel v0.2.1 assemble      (via assemble_easel, upstream untouched)
        -> qc_video
        -> receipt
```

What it is not
--------------
- not a full-narration run: the sample covers three units (U01, U03, U05)
- not a production golden: the audio lives under gitignored `outputs/`, so this
  is host-local and fails loudly on a checkout that never generated it
- not approved: `production_ready=false`, `human_review=PENDING_FOUNDER_REVIEW`
- it spends nothing: no speech, image or video provider call is made

Timing
------
The candidate audio is one continuous take (or two joined group takes for E).
Per-unit boundaries are needed because one evidence placement per unit is the
whole point of the mapping. The boundary is chosen as the detected silence whose
midpoint is nearest the character-proportional expectation; when no usable
silence exists the proportional split is used and the receipt says so. The
method is recorded per boundary rather than silently assumed.

Usage
-----
```
python scripts/build_v3_sample_video.py --arm E
python scripts/build_v3_sample_video.py --arm D --out-name v3-sample-D
python scripts/build_v3_sample_video.py --audio <path> --arm E
```
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_run  # noqa: E402
from verify_creator_script import load_verified_plan  # noqa: E402

RECEIPT_JSON = (
    ROOT / "projects" / "easel-enhanced-golden" / "review"
    / "narration-v3-sample-receipt.json"
)
SAMPLE_DIR = ROOT / "outputs" / "founder-v3-sample"
EVIDENCE_LOCK = ROOT / "projects" / "easel-enhanced-golden" / "evidence" / "evidence-lock.json"
BASELINE_STORYBOARD = ROOT / "projects" / "easel-review" / "script" / "storyboard.json"
DEFAULT_PROJECT = ROOT / "projects" / "easel-enhanced-golden" / "v3-sample-video"

SCHEMA = "contentops.narration-video/v1"

#: Silence detector settings. The provider renders a paragraph break as a pause;
#: 0.12 s is the shortest gap worth calling a boundary, and -35 dB is below the
#: measured noise floor of every v3 candidate.
SILENCE_NOISE_DB = -35
SILENCE_MIN_SECONDS = 0.15
BOUNDARY_MIN_SECONDS = 0.12

#: Caption segmentation. A phrase cue is a clause, not a whole sentence.
PHRASE_BREAK_CHARS = "，。：；！？、—"
MIN_PHRASE_CHARS = 6
MIN_CUE_SECONDS = 0.45


class BuildRefused(RuntimeError):
    """The build cannot proceed, and the reason is not a bug."""


@dataclass
class UnitTiming:
    unit_id: str
    text: str
    paragraph: int
    placement_id: str
    image: str
    start_s: float
    duration_s: float
    boundary_method: str = ""
    logical_path: str = ""


@dataclass
class CaptionCue:
    start_s: float
    duration_s: float
    text: str


# --- media probes ------------------------------------------------------------


def probe_duration(path: Path) -> float:
    out = hidden_run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        timeout=60,
    )
    if out.returncode != 0:
        raise BuildRefused(f"ffprobe could not read {path}: {(out.stderr or '').strip()}")
    try:
        return float((out.stdout or "").strip())
    except ValueError as exc:
        raise BuildRefused(f"ffprobe returned no duration for {path}") from exc


def detect_silences(path: Path) -> List[Tuple[float, float]]:
    """Silence intervals from ffmpeg's silencedetect, end-inclusive.

    A trailing silence that never gets a `silence_end` is closed at the file
    duration, because a boundary at the end of a group is still a real boundary.
    """
    out = hidden_run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
         "-af", f"silencedetect=noise={SILENCE_NOISE_DB}dB:d={SILENCE_MIN_SECONDS}",
         "-f", "null", "-"],
        timeout=180,
    )
    text = f"{out.stdout or ''}\n{out.stderr or ''}"
    intervals: List[Tuple[float, float]] = []
    start: Optional[float] = None
    for line in text.splitlines():
        found = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if found:
            start = max(0.0, float(found.group(1)))
            continue
        found = re.search(r"silence_end:\s*(-?[\d.]+)", line)
        if found and start is not None:
            intervals.append((start, float(found.group(1))))
            start = None
    if start is not None:
        intervals.append((start, probe_duration(path)))
    return intervals


def _midpoint(interval: Tuple[float, float]) -> float:
    return (interval[0] + interval[1]) / 2.0


# --- timing ------------------------------------------------------------------


def split_group(
    *,
    group_start: float,
    group_end: float,
    weights: Sequence[int],
    silences: Sequence[Tuple[float, float]],
    labels: Sequence[str],
) -> List[Tuple[float, float, str]]:
    """Split one synthesis group into per-unit intervals.

    Returns ``[(start, duration, method)]``. The last interval ends at
    ``group_end`` exactly, so the sum is the measured group duration and no
    rounding drift accumulates into the video length.
    """
    if len(labels) != len(weights) - 1:
        raise ValueError("one label is required per internal boundary")
    if len(weights) == 1:
        return [(group_start, group_end - group_start, "single_unit_group")]

    span = group_end - group_start
    total_weight = sum(weights)
    cumulative = []
    running = 0
    for weight in weights[:-1]:
        running += weight
        cumulative.append(running / total_weight)

    usable = [
        interval for interval in silences
        if interval[0] > group_start + 0.05
        and interval[1] < group_end - 0.05
        and (interval[1] - interval[0]) >= BOUNDARY_MIN_SECONDS
    ]
    window = max(1.5, span * 0.35)
    used: List[Tuple[float, float]] = []
    boundaries: List[Tuple[float, str]] = []
    for share, label in zip(cumulative, labels):
        expected = group_start + span * share
        choices = [
            interval for interval in usable
            if interval not in used and abs(_midpoint(interval) - expected) <= window
        ]
        if choices:
            chosen = min(choices, key=lambda item: abs(_midpoint(item) - expected))
            used.append(chosen)
            boundaries.append((_midpoint(chosen), "silence_midpoint"))
        else:
            boundaries.append((expected, "proportional_no_silence"))

    # Keep boundaries strictly increasing even after a fallback.
    boundaries.sort(key=lambda item: item[0])
    results: List[Tuple[float, float, str]] = []
    cursor = group_start
    for boundary, method in boundaries:
        boundary = min(max(boundary, cursor + 0.05), group_end - 0.05)
        results.append((cursor, boundary - cursor, method))
        cursor = boundary
    results.append((cursor, group_end - cursor, "group_tail"))
    return results


def allocate_unit_timings(
    *,
    units: Sequence[Any],
    groups: Sequence[Dict[str, Any]],
    total_s: float,
    silences: Sequence[Tuple[float, float]],
    measured_group_durations: Optional[Sequence[float]] = None,
) -> List[UnitTiming]:
    """Turn the candidate's group structure into per-unit intervals.

    ``groups`` carries ``units``, ``synthesis_characters`` and
    ``pause_after_s`` (the declared join gap). When the per-group WAVs are on
    disk their measured durations are used; otherwise group speech length is
    derived from the measured total minus the declared gaps, weighted by the
    synthesis character count recorded in the receipt. Either way the final sum
    is checked against the measured joined duration.
    """
    texts = {unit.id: unit.text for unit in units}
    paragraphs = {unit.id: unit.source_paragraphs for unit in units}

    gaps = sum(float(group.get("pause_after_s") or 0.0) for group in groups[:-1])
    speech_total = total_s - gaps
    if speech_total <= 0:
        raise BuildRefused("the declared join gaps exceed the audio duration")

    if measured_group_durations and len(measured_group_durations) == len(groups):
        measured_total = sum(measured_group_durations)
        if abs(measured_total - speech_total) > 0.02:
            raise BuildRefused(
                f"per-group durations sum to {measured_total:.3f}s but the joined "
                f"audio implies {speech_total:.3f}s"
            )
        group_sizes = list(measured_group_durations)
        group_size_method = "measured_group_files"
    else:
        weights = [int(group.get("synthesis_characters") or 1) for group in groups]
        total_weight = sum(weights)
        group_sizes = [speech_total * weight / total_weight for weight in weights]
        group_size_method = "proportional_to_synthesis_characters"

    timings: List[UnitTiming] = []
    cursor = 0.0
    for group, size in zip(groups, group_sizes):
        group_units = list(group["units"])
        start = cursor
        end = cursor + size
        label_weights = [max(1, len(texts[unit_id])) for unit_id in group_units]
        intervals = split_group(
            group_start=start,
            group_end=end,
            weights=label_weights,
            silences=silences,
            labels=[
                f"{group_units[i]}/{group_units[i + 1]}"
                for i in range(len(group_units) - 1)
            ],
        )
        for unit_id, (unit_start, unit_duration, method) in zip(group_units, intervals):
            timings.append(UnitTiming(
                unit_id=unit_id,
                text=texts[unit_id],
                paragraph=_first_paragraph(paragraphs[unit_id], unit_id),
                placement_id="",
                image="",
                start_s=unit_start,
                duration_s=unit_duration,
                boundary_method=method,
            ))
        cursor = end + float(group.get("pause_after_s") or 0.0)
        # The gap belongs to the group's last unit so the shot clock stays continuous.
        timings[-1].duration_s += float(group.get("pause_after_s") or 0.0)

    measured = sum(item.duration_s for item in timings)
    if abs(measured - total_s) > 0.01:
        raise BuildRefused(
            f"unit durations sum to {measured:.3f}s but the audio is {total_s:.3f}s"
        )
    return timings, group_size_method


def _first_paragraph(value: Any, unit_id: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple)) and value:
        return int(value[0])
    raise BuildRefused(f"unit {unit_id} has no source_paragraphs")


# --- evidence mapping --------------------------------------------------------


def placement_for_paragraph(lock: Dict[str, Any], paragraph: int) -> Dict[str, Any]:
    """Map a 1-based source paragraph to the locked evidence placement.

    The lock's placements are the baseline storyboard's six shots in order, and
    the creator script's ``source_paragraphs`` index the same six paragraphs.
    The mapping is checked against the baseline storyboard rather than assumed:
    if either side ever changes shape, the build stops instead of pairing a
    sentence with the wrong evidence.
    """
    evidence = lock.get("evidence") or []
    baseline = json.loads(BASELINE_STORYBOARD.read_text(encoding="utf-8"))
    shots = baseline.get("shots") or []
    if len(evidence) != len(shots):
        raise BuildRefused(
            f"evidence lock has {len(evidence)} placements but the baseline "
            f"storyboard has {len(shots)} shots"
        )
    if not 1 <= paragraph <= len(evidence):
        raise BuildRefused(
            f"source paragraph {paragraph} is outside 1..{len(evidence)}"
        )
    return evidence[paragraph - 1]


def _logical_to_local(logical: str, source_project: str) -> Path:
    """Resolve ``project://sources/...`` against the lock's ``project://<slug>``."""
    if not logical.startswith("project://"):
        raise BuildRefused(f"unsupported logical path: {logical}")
    if not source_project.startswith("project://"):
        raise BuildRefused(f"evidence lock has no project scope: {source_project!r}")
    slug = source_project[len("project://"):].strip("/")
    tail = logical[len("project://"):].lstrip("/")
    if not slug or not tail:
        raise BuildRefused(f"malformed logical path: {logical}")
    return ROOT / "projects" / slug / tail


# --- captions ----------------------------------------------------------------


def srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def split_phrases(text: str) -> List[str]:
    """Break a unit into clause-sized cues, keeping the punctuation attached.

    Only Chinese punctuation is a break. Latin full stops are not, because
    ``v0.2.1`` and ``.env`` must survive intact. A fragment shorter than
    :data:`MIN_PHRASE_CHARS` is merged with its neighbour so the caption does not
    flicker on a two-character particle.
    """
    parts: List[str] = []
    current = ""
    for char in text:
        current += char
        if char in PHRASE_BREAK_CHARS:
            if current.strip():
                parts.append(current.strip())
            current = ""
    if current.strip():
        parts.append(current.strip())

    merged: List[str] = []
    for part in parts:
        if merged and (len(part) < MIN_PHRASE_CHARS or len(merged[-1]) < MIN_PHRASE_CHARS):
            merged[-1] += part
        else:
            merged.append(part)
    return merged or [text]


def build_caption_cues(
    timings: Sequence[UnitTiming], caption_mode: str
) -> List[CaptionCue]:
    """One cue per unit (``sentence``) or per clause (``phrase``).

    A unit's audio duration is split across its clauses by character count. The
    last clause takes the remainder, so the cues of a unit sum to that unit's
    measured duration exactly and the caption clock never drifts from the voice.
    """
    if caption_mode == "sentence":
        return [
            CaptionCue(item.start_s, item.duration_s, item.text) for item in timings
        ]
    if caption_mode != "phrase":
        raise BuildRefused(f"unknown caption mode: {caption_mode}")

    cues: List[CaptionCue] = []
    for item in timings:
        phrases = split_phrases(item.text)
        weights = [max(1, len(phrase)) for phrase in phrases]
        total_weight = sum(weights)
        cursor = item.start_s
        for index, (phrase, weight) in enumerate(zip(phrases, weights)):
            if index == len(phrases) - 1:
                duration = item.start_s + item.duration_s - cursor
            else:
                duration = item.duration_s * weight / total_weight
            cues.append(CaptionCue(cursor, duration, phrase))
            cursor += duration

    merged: List[CaptionCue] = []
    for cue in cues:
        if merged and cue.duration_s < MIN_CUE_SECONDS:
            merged[-1].duration_s += cue.duration_s
            merged[-1].text += cue.text
        else:
            merged.append(cue)
    return merged


def render_srt(cues: Sequence[Any]) -> str:
    blocks: List[str] = []
    for index, item in enumerate(cues, 1):
        end = item.start_s + item.duration_s
        blocks.append(
            f"{index}\n{srt_timestamp(item.start_s)} --> {srt_timestamp(end)}\n"
            f"{item.text}\n"
        )
    return "\n".join(blocks)


# --- build -------------------------------------------------------------------


def _load_arm_audio(arm: str, audio_override: Optional[str]) -> Tuple[Path, Dict[str, Any]]:
    receipt = json.loads(RECEIPT_JSON.read_text(encoding="utf-8"))
    key = receipt.get("listening_key") or {}
    by_arm = {value: candidate for candidate, value in key.items()}
    if arm not in by_arm:
        raise BuildRefused(f"arm {arm!r} is not in the listening key {key}")

    record = receipt["candidates"][arm]
    if audio_override:
        audio = Path(audio_override)
        if not audio.is_absolute():
            audio = ROOT / audio
        expected_sha = (record.get("audio") or {}).get("sha256")
    else:
        audio = SAMPLE_DIR / f"{by_arm[arm]}.wav"
        expected_sha = (record.get("audio") or {}).get("sha256")

    if not audio.is_file():
        raise BuildRefused(
            f"{audio} is absent. The v3 candidates live under gitignored outputs/; "
            "this pilot is host-local by design and will not fabricate audio."
        )
    if expected_sha:
        import hashlib

        digest = hashlib.sha256(audio.read_bytes()).hexdigest()
        if digest != expected_sha:
            raise BuildRefused(
                f"{audio.name} hashes {digest[:12]}, not the receipt's "
                f"{expected_sha[:12]}; refusing to render different bytes than the "
                "ones that were reviewed."
            )
    return audio, receipt


def _groups_for_arm(
    arm: str, receipt: Dict[str, Any], sample_ids: Sequence[str]
) -> Tuple[List[Dict[str, Any]], Optional[List[float]]]:
    """The candidate's group structure, plus measured per-group durations if any.

    The per-group WAVs are a local cache, not a contract: when they are absent
    the caller falls back to the receipt's synthesis-character weights. They are
    preferred when present because they are the measured truth, and a mismatch
    between them and the joined audio is refused rather than averaged.
    """
    record = receipt["candidates"][arm]
    measured: Optional[List[float]] = None
    if record.get("segmented"):
        groups = []
        durations: List[Optional[float]] = []
        for group in record.get("groups") or []:
            groups.append({
                "id": group["group"],
                "units": list(group["units"]),
                "synthesis_characters": int(group.get("synthesis_characters") or 1),
                "pause_after_s": float(
                    (group.get("director_controls") or {}).get("pause_after_s") or 0.0
                ),
            })
            path = SAMPLE_DIR / f"{arm}-{group['group']}.wav"
            durations.append(probe_duration(path) if path.is_file() else None)
        if all(value is not None for value in durations):
            measured = [float(value) for value in durations]  # type: ignore[arg-type]
    else:
        # One request with no internal joins; group weight is irrelevant.
        groups = [{
            "id": f"{arm}-single",
            "units": list(sample_ids),
            "synthesis_characters": 1,
            "pause_after_s": 0.0,
        }]
    return groups, measured


def build(
    *,
    arm: str,
    audio_override: Optional[str],
    project: Path,
    out_name: str,
    motion: str = "static",
    caption_mode: str = "sentence",
) -> Dict[str, Any]:
    verified = load_verified_plan()
    creator = verified["creator"]
    plan = verified["plan"]

    audio, receipt = _load_arm_audio(arm, audio_override)
    total_s = probe_duration(audio)
    silences = detect_silences(audio)

    sample_ids = list(plan.sample_unit_ids)
    units = [creator.unit(unit_id) for unit_id in sample_ids]
    groups, measured_group_durations = _groups_for_arm(arm, receipt, sample_ids)
    recorded = [unit_id for group in groups for unit_id in group["units"]]
    if recorded != sample_ids:
        raise BuildRefused(
            f"receipt groups cover {recorded} but the plan's sample units are "
            f"{sample_ids}"
        )

    timings, group_size_method = allocate_unit_timings(
        units=units,
        groups=groups,
        total_s=total_s,
        silences=silences,
        measured_group_durations=measured_group_durations,
    )

    lock = json.loads(EVIDENCE_LOCK.read_text(encoding="utf-8"))
    if lock.get("fixture"):
        raise BuildRefused("refusing to build from a fixture evidence lock")
    for item in timings:
        placement = placement_for_paragraph(lock, item.paragraph)
        item.placement_id = placement["placement_id"]
        item.logical_path = placement["asset_path"]
        local = _logical_to_local(placement["asset_path"], lock.get("source_project", ""))
        if not local.is_file():
            raise BuildRefused(f"evidence asset is absent: {local}")
        # The storyboard carries a real path for ffmpeg; the receipt keeps the
        # logical reference. They are the same bytes, checked above.
        item.image = local.resolve().relative_to(ROOT).as_posix()

    # -- materialise the project --------------------------------------------
    for directory in (
        project / "script", project / "assets" / "voice",
        project / "assets" / "captions", project / "final",
        project / "receipts", project / "work",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    local_audio = project / "assets" / "voice" / f"narration{audio.suffix}"
    shutil.copyfile(audio, local_audio)

    caption = project / "assets" / "captions" / f"{out_name}.srt"
    cues = build_caption_cues(timings, caption_mode)
    caption.write_text(render_srt(cues), encoding="utf-8")

    baseline = json.loads(BASELINE_STORYBOARD.read_text(encoding="utf-8"))
    storyboard: Dict[str, Any] = {
        "size": baseline.get("size", "1080x1920"),
        "image_motion": motion,
        "pad_mode": baseline.get("pad_mode", "trim"),
        "shots": [
            {
                "image": item.image,
                "duration": round(item.duration_s, 3),
                "source": item.image,
                "source_type": "real_screenshot",
                "narration": item.text,
                "unit": item.unit_id,
                "placement": item.placement_id,
            }
            for item in timings
        ],
        "narration": local_audio.relative_to(ROOT).as_posix(),
        "subtitle": caption.relative_to(ROOT).as_posix(),
        "engine": "easel",
        "runtime": baseline.get("runtime"),
        "voice_provider": (
            f"minimax_m_plan/{receipt.get('model', 'speech-2.8-hd')} "
            f"(v3 arm {arm})"
        ),
        "generated_visuals": {"count": 0, "policy": "real_assets_only"},
        "derived_from": {
            "creator_script": verified["digests"]["creator_script_working_tree_sha256"],
            "director_plan": verified["digests"]["director_plan_working_tree_sha256"],
            "narration_sha256": (receipt["candidates"][arm].get("audio") or {}).get("sha256"),
            "sample_units": sample_ids,
        },
        "timing_policy": (
            "per-unit durations measured from the candidate audio; internal "
            "boundaries are silence midpoints nearest the character-proportional "
            "expectation, with the method recorded per boundary in the receipt"
        ),
    }
    storyboard_path = project / "script" / "storyboard.json"
    storyboard_path.write_text(
        json.dumps(storyboard, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    (project / "script" / "master.md").write_text(
        "# Narration v3 sample video\n\n"
        f"Derived from `projects/easel-enhanced-golden/script/creator-script.json` "
        f"and `narration-plan.json` (arm {arm}). The factual content is fixed by the "
        "Evidence Lock; this is a three-unit excerpt, not the full six-shot script.\n\n"
        "The narration audio is the already-generated v3 candidate, reused without a "
        "provider call. Nothing here is production-ready.\n",
        encoding="utf-8",
    )

    from assemble_easel import run as assemble_run  # noqa: PLC0415
    from qc_video import qc as qc_run  # noqa: PLC0415
    from contentops.media.qc_canonical import (  # noqa: PLC0415
        CURRENCY_CURRENT,
        canonical_qc_report,
        render_canonical_qc_markdown,
    )

    composed = assemble_run(project, out_name=out_name)
    qc_runtime = qc_run(project, target=f"{out_name}.mp4")
    qc_report = canonical_qc_report(
        qc_runtime,
        repo_root=ROOT,
        project_root=project,
        graded_target=f"project://final/{out_name}.mp4",
        currency=CURRENCY_CURRENT,
    )
    qc_report["evidence_provenance"] = {
        "mode": "canonical_reference_by_path",
        "copies_in_project": 0,
        "reason": (
            "the excerpt reuses the locked evidence by canonical repository path, so "
            "it cannot drift from the lock; qc_video's real_evidence_present is "
            "directory-local and therefore reports 0"
        ),
    }
    receipts = project / "receipts"
    (receipts / f"qc-report-{out_name}.json").write_text(
        json.dumps(qc_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (receipts / f"qc-report-{out_name}.md").write_text(
        render_canonical_qc_markdown(qc_report, project_name=project.name),
        encoding="utf-8",
    )

    report: Dict[str, Any] = {
        "schema": SCHEMA,
        "stage": "NARRATION_V3_SAMPLE_VIDEO",
        "issue": "#34",
        "arm": arm,
        "narration": {
            "path": audio.relative_to(ROOT).as_posix() if audio.is_relative_to(ROOT) else str(audio),
            "sha256": (receipt["candidates"][arm].get("audio") or {}).get("sha256"),
            "duration_s": round(total_s, 3),
            "voice_id": receipt["candidates"][arm].get("voice_id"),
            "model": receipt.get("model"),
        },
        "units": [
            {
                "unit_id": item.unit_id,
                "paragraph": item.paragraph,
                "placement_id": item.placement_id,
                "image": item.image,
                "image_logical": item.logical_path,
                "start_s": round(item.start_s, 3),
                "duration_s": round(item.duration_s, 3),
                "boundary_method": item.boundary_method,
            }
            for item in timings
        ],
        "groups": groups,
        "timing": {
            "group_size_method": group_size_method,
            "silence_noise_db": SILENCE_NOISE_DB,
            "silence_min_seconds": SILENCE_MIN_SECONDS,
            "audio_duration_s": round(total_s, 3),
        },
        "look": {
            "image_motion": motion,
            "caption_mode": caption_mode,
            "caption_cues": len(cues),
        },
        "evidence": {
            "source": "contentops.evidence-lock/v1",
            "placements_used": sorted({item.placement_id for item in timings}),
            "generated_assets": 0,
            "substitution": False,
        },
        "compose": {
            "status": composed.get("status"),
            "video": (
                Path(composed["video"]).relative_to(ROOT).as_posix()
                if composed.get("video") else None
            ),
            "subtitles_burned": composed.get("subtitles_burned"),
            "stage": composed.get("stage"),
            "reason": composed.get("reason"),
        },
        "qc": {"overall": qc_report.get("overall")},
        "provider_calls": {"speech": 0, "image": 0, "video": 0},
        "quota": "untouched; the candidate audio was generated by the v3 sample run",
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
        "limitations": [
            "three-unit excerpt (U01, U03, U05), not the full eight-unit script",
            "the candidate audio is gitignored, so this build is host-local",
            "an internal shot boundary may be off by up to one clause when no "
            "usable silence was detected (see per-unit boundary_method)",
            *(
                ["ken-burns comes from the pinned upstream filter, which zooms "
                 "toward the top-left because it sets no x/y expression"]
                if motion == "ken-burns" else []
            ),
            *(
                ["phrase cues are allocated by character count within a unit, "
                 "so a fast clause can lead or lag its spoken words by a fraction "
                 "of a second"]
                if caption_mode == "phrase" else []
            ),
        ],
    }
    (project / "receipts" / "v3-sample-video.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=("D", "E", "F"), default="E")
    parser.add_argument("--audio", default="", help="explicit candidate WAV (must match the arm's sha)")
    parser.add_argument("--project", default=str(DEFAULT_PROJECT))
    parser.add_argument("--out-name", default="v3-sample")
    parser.add_argument(
        "--motion", choices=("static", "ken-burns"), default="static",
        help="shot motion; ken-burns delegates to the pinned upstream filter",
    )
    parser.add_argument(
        "--caption-mode", choices=("sentence", "phrase"), default="sentence",
        help="one cue per unit, or one cue per clause",
    )
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / project).resolve()

    report = build(
        arm=args.arm,
        audio_override=args.audio or None,
        project=project,
        out_name=args.out_name,
        motion=args.motion,
        caption_mode=args.caption_mode,
    )
    print(json.dumps({k: report[k] for k in ("arm", "compose", "qc", "production_ready")},
                     indent=2, ensure_ascii=False))
    for item in report["units"]:
        print(f"  {item['unit_id']} -> {item['placement_id']}  "
              f"{item['start_s']:6.2f}s +{item['duration_s']:5.2f}s  "
              f"({item['boundary_method']})")
    return 0 if report["compose"]["status"] == "OK" else 5


if __name__ == "__main__":
    sys.exit(main())
