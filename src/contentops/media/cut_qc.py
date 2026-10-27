"""Target-aware quality gate for an evidence cut.

The legacy gate assumed 1080×1920 and counted *shots*. Both assumptions fail
here: one package is 1920×1080, and a single ten-second generated clip must weigh
more than ten one-second real shots. So this gate:

- reads the target from the package's CutPlan, not from constants;
- measures real-source and generated share by **final-cut duration**;
- counts overlapping intervals once;
- checks narration/caption/claim/asset presence;
- fails closed when ffprobe or the decode cannot run.

It still cannot decide whether the cut is good. That remains a human playback
review recorded in the review bundle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from contentops.evidence._common import ContractError
from contentops.evidence.claim_map import ClaimMap
from contentops.media.cut_plan import DEFAULT_MAX_VISUAL_HOLD_MS, CutPlan
from contentops.media.media_paths import resolve_media_path
from contentops.media.transport import ffprobe_json
from contentops.media.video_qc import HAVE_FFMPEG, HAVE_FFPROBE, measure_video

MIN_REAL_SOURCE_RATIO = 0.70
MAX_GENERATED_RATIO = 0.10


def _union_seconds(intervals: Iterable[Tuple[int, int]]) -> float:
    """Total covered time; overlapping intervals count once."""
    spans = sorted((start, end) for start, end in intervals if end > start)
    total = 0
    current_start = current_end = None
    for start, end in spans:
        if current_start is None:
            current_start, current_end = start, end
        elif start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    if current_start is not None:
        total += current_end - current_start
    return total / 1000.0


def source_shares(cut_plan: CutPlan,
                  assets: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    """Real-source and generated duration shares of the whole cut."""
    real: List[Tuple[int, int]] = []
    generated: List[Tuple[int, int]] = []
    card: List[Tuple[int, int]] = []
    for placement in cut_plan.placements:
        asset = assets.get(placement.asset_id)
        if asset is None:
            raise ContractError("UNKNOWN_ASSET",
                                f"{placement.placement_id} cites {placement.asset_id}")
        interval = (placement.start_ms, placement.end_ms)
        kind = asset.get("kind")
        if kind == "recording" and asset.get("source_type", "real_recording") in (
                "real_recording", "real_screenshot", "real_document"):
            real.append(interval)
        elif kind in ("generated_image", "generated_video", "generated"):
            generated.append(interval)
        else:
            card.append(interval)
    end_ms = max((p.end_ms for p in cut_plan.placements), default=0)
    total = max(end_ms, 1) / 1000.0
    return {
        "total_s": total,
        "real_s": _union_seconds(real),
        "generated_s": _union_seconds(generated),
        "citation_or_support_s": _union_seconds(card),
        "real_ratio": _union_seconds(real) / total,
        "generated_ratio": _union_seconds(generated) / total,
    }


def qc_cut(project: Path, video: Optional[Path] = None) -> Dict[str, Any]:
    project = project.resolve()
    checks: List[Dict[str, Any]] = []
    claim_map = ClaimMap.from_dict(_load(project / "script" / "claim-map.json"))
    cut_plan = CutPlan.from_dict(_load(project / "script" / "cut-plan.json"))
    cut_plan.validate_claims(claim_map)
    assets = _load(project / "script" / "assets.json")["assets"]
    target = cut_plan.target

    video = video or project / "final" / "easel.mp4"
    # The committed receipt carries a logical reference, so it stays valid on a
    # second checkout and does not publish a machine path.
    logical = (f"project://{video.relative_to(project).as_posix()}"
               if video.is_relative_to(project) else str(video))
    checks.append(_check("video_exists", video.is_file(), "FAIL", logical))
    if not video.is_file():
        return _emit(project, checks, target)

    meta = ffprobe_json(video)
    streams = meta.get("streams") or []
    visual = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    duration = float(meta.get("format", {}).get("duration", 0) or 0)

    checks.append(_check("resolution",
                         visual.get("width") == target["width"]
                         and visual.get("height") == target["height"],
                         "FAIL",
                         f"{visual.get('width')}x{visual.get('height')} expected "
                         f"{target['width']}x{target['height']}"))
    low, high = target["duration_ms_range"]
    checks.append(_check("duration", low / 1000.0 - 0.5 <= duration <= high / 1000.0 + 0.5,
                         "FAIL", f"{duration:.2f}s expected {low/1000:.0f}-{high/1000:.0f}s"))
    checks.append(_check("video_codec", visual.get("codec_name") in ("h264", "libx264"),
                         "FAIL", visual.get("codec_name") or "none"))
    checks.append(_check("audio_present", bool(audio), "FAIL",
                         audio.get("codec_name") or "none"))

    max_hold_ms = target.get("max_visual_hold_ms", DEFAULT_MAX_VISUAL_HOLD_MS)
    # Structural: a placement may run as long as its narration, but if it shows
    # one unchanging view for longer than the hold limit it must declare the
    # views that replace it. This is the check the old gate lacked -- it passed
    # a wholly static cut because *any* reading beat was declared.
    undeclared = [p.placement_id for p in cut_plan.placements
                  if p.end_ms - p.start_ms > max_hold_ms and not p.shots]
    checks.append(_check("views_declared", not undeclared, "FAIL",
                         f"static placements over {max_hold_ms}ms: {undeclared}"
                         if undeclared else f"every static view is <= {max_hold_ms}ms"))

    if HAVE_FFMPEG and HAVE_FFPROBE:
        measured = measure_video(video)
        # Measured: the render may still freeze even when the plan declares
        # views (a held last frame, a repeated still). The limit is the same
        # declared hold, plus a frame of encoder tolerance.
        freeze_limit = max_hold_ms / 1000.0 + 0.2
        longest = measured.longest_freeze_run_s
        blocking = [r for r in measured.reasons if "frozen run" not in r]
        checks.append(_check("decodes_and_analyses", not blocking, "FAIL",
                             "; ".join(blocking) or "OK"))
        checks.append(_check("static_hold_within_limit",
                             longest is None or longest <= freeze_limit, "FAIL",
                             f"longest frozen run {longest if longest is not None else 0:.2f}s "
                             f"(limit {freeze_limit:.2f}s)"))
        checks.append(_check("black_and_freeze_measured",
                             measured.analysed_frames > 0, "FAIL",
                             f"analysed_frames={measured.analysed_frames}"))
    else:
        checks.append(_check("decodes_and_analyses", False, "FAIL",
                             "ffmpeg/ffprobe unavailable; unverified"))

    shares = source_shares(cut_plan, assets)
    checks.append(_check("real_source_ratio", shares["real_ratio"] >= MIN_REAL_SOURCE_RATIO,
                         "FAIL", f"{shares['real_ratio']:.1%} of {shares['total_s']:.1f}s "
                                 f"(min {MIN_REAL_SOURCE_RATIO:.0%})"))
    checks.append(_check("generated_ratio", shares["generated_ratio"] < MAX_GENERATED_RATIO,
                         "FAIL", f"{shares['generated_ratio']:.1%} "
                                 f"(max {MAX_GENERATED_RATIO:.0%})"))
    checks.append(_check("claim_bindings",
                         all(cid in {c.claim_id for c in claim_map.claims}
                             for cid in cut_plan.claim_ids()),
                         "FAIL", f"{len(cut_plan.claim_ids())} claim ids"))

    cover_receipt = project / "receipts" / "cover.json"
    checks.append(_check("cover_present", cover_receipt.is_file(), "FAIL",
                         "receipts/cover.json"))

    captions = project / "assets" / "captions" / "cut.srt"
    cue_count = _cue_count(captions)
    checks.append(_check("captions_present", captions.is_file() and cue_count > 0,
                         "FAIL", f"{cue_count} cues"))
    checks.append(_check("captions_inside_duration",
                         _cues_within(captions, duration), "FAIL",
                         f"{duration:.2f}s"))

    # A card that carries the claim verbatim is allowed to have no burned cue;
    # every non-card narration still needs one.
    card_claims = {cid for p in cut_plan.placements
                   if assets[p.asset_id]["kind"] == "card" for cid in p.claim_ids}
    narrated = {c.claim_id for c in claim_map.claims
                if any(a["surface"] == "narration" for a in c.appearances)}
    missing = narrated - card_claims - _cue_claim_ids(captions, claim_map)
    checks.append(_check("narration_has_cues", not missing, "FAIL",
                         f"missing: {sorted(missing)}" if missing else "OK"))

    return _emit(project, checks, target, shares=shares, duration=duration)


def _load(path: Path):
    import json

    if not path.is_file():
        raise ContractError("MISSING_FILE", f"{path} does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


def _check(check_id: str, ok: bool, severity: str, detail: str) -> Dict[str, Any]:
    return {"id": check_id, "ok": bool(ok),
            "severity": "PASS" if ok else severity, "detail": detail}


def _cue_count(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines()
               if "-->" in line)


def _cues_within(path: Path, duration: float) -> bool:
    if not path.is_file():
        return False
    import re

    for line in path.read_text(encoding="utf-8").splitlines():
        if "-->" not in line:
            continue
        end = line.split("-->")[1].strip()
        h, m, rest = end.split(":")
        s, ms = rest.replace(",", ".").split(".")
        seconds = int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
        if seconds > duration + 0.25:
            return False
    return True


def _cue_claim_ids(path: Path, claim_map: ClaimMap) -> set:
    if not path.is_file():
        return set()
    found = set()
    blocks = path.read_text(encoding="utf-8").strip().split("\n\n")
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 3:
            continue
        text = " ".join(lines[2:])
        try:
            found.add(claim_map.claim_for("caption", text).claim_id)
        except ContractError:
            continue
    return found


def _emit(project: Path, checks: List[Dict[str, Any]], target: Dict[str, Any],
          **extra) -> Dict[str, Any]:
    overall = "PASS"
    for check in checks:
        if not check["ok"] and check["severity"] == "FAIL":
            overall = "FAIL"
            break
    report = {
        "schema": "contentops.cut-qc/v1",
        "project": project.name,
        "target": target,
        "overall": overall,
        "checks": checks,
        **extra,
    }
    receipts = project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    import json

    (receipts / "qc-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
