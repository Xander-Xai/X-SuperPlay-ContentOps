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

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from contentops.evidence._common import ContractError
from contentops.evidence.claim_map import ClaimMap
from contentops.media.claim_coverage import (REAL_EVIDENCE_KINDS, evidence_mode_policy,
                                             validate_claim_coverage)
from contentops.media.cut_plan import DEFAULT_MAX_VISUAL_HOLD_MS, CutPlan
from contentops.media.media_paths import resolve_media_path
from contentops.media.transport import ffprobe_json
from contentops.media.video_qc import HAVE_FFMPEG, HAVE_FFPROBE, measure_video

MIN_REAL_SOURCE_RATIO = 0.70
MAX_GENERATED_RATIO = 0.10
#: A declared composition (vector / code / metric) is a target, not an exact
#: contract; this is how far a role may drift before the cut is refused.
COMPOSITION_TOLERANCE_PCT = 8.0

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Asset ``kind`` values and DNA composition role names are two vocabularies for
#: the same picture duty. Comparing them without a translation is why the same
#: film measured 73/27 in one gate and 0/0 in the other.
ROLE_ALIASES = {
    "recording": "screen_recording_evidence",
    "card": "comparison_card",
    "generated": "vector_animation",
    "generated_image": "vector_animation",
    "generated_video": "vector_animation",
}

#: Roles that promise a real capture. Each must sit on an asset whose ``kind`` is
#: in :data:`REAL_EVIDENCE_KINDS`; otherwise the role is a free label.
EVIDENCE_ROLES = frozenset({
    "screen_recording_evidence", "real_recording", "real_screenshot", "real_document",
})

#: Recording permissions form an ordering; evidence modes do not. CLAIM_LED
#: requires per-claim coverage while EVIDENCE_LED requires a whole-film floor,
#: so neither can replace the other without discarding a different protection.
STRICTNESS = {
    "manual_recording": {"ALLOWED": 0, "ALLOWED_CROPPED": 1, "FORBIDDEN": 2},
}


def _looser(declared: Any, owned: Any, field: str) -> bool:
    """Refuse replacing an incomparable evidence mode or relaxing a policy."""
    if declared == owned:
        return False
    if field == "evidence_mode":
        return True
    order = STRICTNESS[field]
    if declared in order and owned in order:
        return bool(order[declared] < order[owned])
    return True


def account_dna_for(project: Path) -> Optional[Dict[str, Any]]:
    """The account DNA the episode belongs to, or None when it names none.

    ``project.yaml`` carries a handful of scalar keys, so this reads the one line
    it needs rather than taking on a YAML dependency. An unreadable or
    unannounced account returns None, which means "no pinning" — not "pinned to
    the episode's own word for it".
    """
    path = Path(project) / "project.yaml"
    if not path.is_file():
        return None
    slug = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("account_slug:"):
            slug = line.split(":", 1)[1].strip().strip("'\"")
            break
    if not slug:
        return None
    dna_path = REPO_ROOT / "config" / "accounts" / f"{slug}.json"
    if not dna_path.is_file():
        return None
    try:
        document = json.loads(dna_path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return document if isinstance(document, dict) else None


def _views(placement) -> List[Tuple[str, int, int]]:
    """Every (asset, start, end) that actually reaches the screen.

    A placement may switch asset inside itself, so its own asset is only the
    default. Counting by placement credited a generated view to the recording it
    replaced, which is the one direction this gate must never be wrong in.
    """
    shots = getattr(placement, "shots", None) or []
    if shots:
        return [(shot.asset_id or placement.asset_id, shot.start_ms, shot.end_ms)
                for shot in shots]
    return [(placement.asset_id, placement.start_ms, placement.end_ms)]


def _role_seconds(cut_plan: CutPlan,
                  assets: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    """Duration per asset role, counting shots rather than placements."""
    totals: Dict[str, float] = {}
    for placement in cut_plan.placements:
        for asset_id, start_ms, end_ms in _views(placement):
            role = assets.get(asset_id, {}).get("role") or assets.get(
                asset_id, {}).get("kind", "unknown")
            totals[role] = totals.get(role, 0.0) + (end_ms - start_ms) / 1000.0
    return totals


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
        for asset_id, start_ms, end_ms in _views(placement):
            asset = assets.get(asset_id)
            if asset is None:
                raise ContractError("UNKNOWN_ASSET",
                                    f"{placement.placement_id} cites {asset_id}")
            interval = (start_ms, end_ms)
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

    # The account owns the evidence mode and the recording policy. An episode may
    # repeat or strengthen them, never weaken them: an episode that could write
    # evidence_mode=EXPLANATORY switched off the very ratio gate it was about to
    # fail, and one that wrote manual_recording=ALLOWED cancelled the ban its
    # account declares. So the account is the floor, and every gate below uses the
    # stricter of the two declarations.
    dna = account_dna_for(project)
    owned = (dna or {}).get("evidence") or {}
    conflicts: List[str] = []
    for field, key in (("evidence_mode", "mode"), ("manual_recording", "manual_recording")):
        value = owned.get(key)
        if not value:
            continue
        declared = target.get(field)
        if declared is not None:
            if _looser(declared, value, field):
                conflicts.append(f"target.{field}={declared!r} licenses more than the "
                                 f"account's {value!r}")
            elif _looser(value, declared, field):
                # The episode is stricter than its account. Its own rule governs;
                # the account's value is a floor, not a ceiling on strictness.
                continue
        target = {**target, field: value}
    if dna is not None:
        checks.append(_check(
            "account_policy", not conflicts, "FAIL",
            "; ".join(conflicts)
            or f"{owned.get('mode')} / {owned.get('manual_recording')} from {dna.get('slug')}"))

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
    # The account owns how long an episode runs, and nothing used to check it. The
    # audio-first planner sizes its target window from the narration it has just
    # measured, so a 25-second cut declared 24.5--25.5 s, matched itself, and passed
    # while missing a 90--120 s account contract outright. A window an episode sets
    # from its own output is not a contract, so the account's window is graded
    # separately and the episode's own declaration cannot satisfy it.
    account_span = ((dna or {}).get("narrative") or {}).get("target_duration_s")
    if account_span:
        span_low, span_high = float(account_span[0]), float(account_span[1])
        checks.append(_check(
            "account_duration",
            span_low - 0.5 <= duration <= span_high + 0.5,
            "FAIL",
            f"{duration:.2f}s vs {dna.get('slug')} {span_low:.0f}-{span_high:.0f}s"))
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
    mode = target.get("evidence_mode", "EVIDENCE_LED")
    policy = evidence_mode_policy(mode)
    if policy["require_claim_coverage"]:
        # Claim-led: the whole-film share is advisory, because the per-claim
        # gate below is the one that can actually be satisfied or violated.
        checks.append(_check("real_source_ratio",
                             shares["real_ratio"] >= MIN_REAL_SOURCE_RATIO, "WARN",
                             f"{shares['real_ratio']:.1%} of {shares['total_s']:.1f}s; "
                             f"advisory (claim coverage is the gate)"))
    elif policy["ratio_severity"] == "FAIL":
        checks.append(_check("real_source_ratio",
                             shares["real_ratio"] >= MIN_REAL_SOURCE_RATIO, "FAIL",
                             f"{shares['real_ratio']:.1%} of {shares['total_s']:.1f}s "
                             f"(min {MIN_REAL_SOURCE_RATIO:.0%})"))
    else:
        checks.append(_check("real_source_ratio", True, "INFO",
                             "not applicable: explanatory account, no recording asset by policy"))
    # The ceiling on generated time comes from the account's own composition: the
    # share it does not spend on captures is the share abstraction may fill. A
    # flat 10 % contradicted 1024's declared 25 % vector budget — the alias table
    # maps generated media into that budget, so the two gates refused a cut that
    # met its DNA. Without a DNA the flat floor still applies.
    segments = ((dna or {}).get("visual") or {}).get("composition") or {}
    segments = segments.get("segments") or []
    evidence_pct = sum(float(segment.get("pct") or 0) for segment in segments
                       if str(segment.get("role")) in EVIDENCE_ROLES)
    max_generated = (max(MAX_GENERATED_RATIO, (100.0 - evidence_pct) / 100.0)
                     if segments else MAX_GENERATED_RATIO)
    if policy["require_claim_coverage"]:
        cap_severity = "WARN"
    elif policy["ratio_severity"] == "INFO":
        cap_severity = "INFO"
    else:
        cap_severity = "FAIL"
    checks.append(_check("generated_ratio", shares["generated_ratio"] <= max_generated,
                         cap_severity, f"{shares['generated_ratio']:.1%} "
                                       f"(max {max_generated:.0%})"))

    if policy["require_claim_coverage"]:
        coverage = validate_claim_coverage(cut_plan, claim_map, assets)
        checks.append(_check("claim_coverage", coverage.ok, "FAIL",
                             "; ".join(coverage.errors) if coverage.errors
                             else f"{len(coverage.covered)} supported claim(s) covered, "
                                  f"{len(coverage.uncovered)} never appear"))

    # An account may forbid manual recordings outright (Future Intelligence).
    # The check follows shots too, because a plan can switch asset inside a
    # placement and hide a recording behind a card placement.
    if target.get("manual_recording") == "FORBIDDEN":
        used = {p.asset_id for p in cut_plan.placements}
        used |= {shot.asset_id for p in cut_plan.placements for shot in p.shots
                 if shot.asset_id}
        offenders = sorted(aid for aid in used
                           if assets.get(aid, {}).get("kind") == "recording")
        checks.append(_check("manual_recording_forbidden", not offenders, "FAIL",
                             f"recording assets in a no-recording account: {offenders}"
                             if offenders else "no recording asset appears"))

    declared = target.get("composition")
    if declared:
        actual = _role_seconds(cut_plan, assets)
        total = sum(actual.values()) or 1.0
        drift = []
        for segment in declared:
            role = segment["role"]
            wanted = float(segment["pct"])
            got = actual.get(role, 0.0) / total * 100.0
            if abs(got - wanted) > COMPOSITION_TOLERANCE_PCT:
                drift.append(f"{role} {got:.0f}% vs {wanted:.0f}%")
        summary = ", ".join(f"{role} {seconds / total:.0%}"
                            for role, seconds in sorted(actual.items()))
        checks.append(_check("composition_ratio", not drift, "FAIL",
                             f"{summary}; outside ±{COMPOSITION_TOLERANCE_PCT:.0f}pp: "
                             f"{', '.join(drift)}" if drift
                             else f"{summary} within ±{COMPOSITION_TOLERANCE_PCT:.0f}pp"))

    # A role is a label the asset map writes about itself. If an evidence role
    # may sit on a generated asset, the composition gate counts screen recording
    # that was never shot, and the account's evidence budget is spent on nothing.
    mislabeled = [
        f"{aid}: role {entry.get('role')!r} on kind {entry.get('kind')!r}"
        for aid, entry in assets.items()
        if str(entry.get("role") or "") in EVIDENCE_ROLES
        and entry.get("kind") not in REAL_EVIDENCE_KINDS
    ]
    checks.append(_check("role_matches_source", not mislabeled, "FAIL",
                         "; ".join(mislabeled) if mislabeled
                         else "every evidence role points at a real capture"))

    # The declared composition is measured against the episode's own word. With a
    # DNA resolved there is a second, stronger question: does the cut spend the
    # account's picture budget? Deleting target.composition used to skip the
    # ratio gate altogether, which left the account's own composition unmeasured.
    if dna is not None:
        segments = ((dna.get("visual") or {}).get("composition") or {}).get("segments") or []
        actual = _role_seconds(cut_plan, assets)
        total = sum(actual.values()) or 1.0
        aliased: Dict[str, float] = {}
        for role, seconds in actual.items():
            name = ROLE_ALIASES.get(role, role)
            aliased[name] = aliased.get(name, 0.0) + seconds
        wanted_roles = {str(s.get("role")) for s in segments}
        drift = []
        for segment in segments:
            role = str(segment.get("role"))
            try:
                wanted = float(segment.get("pct"))
            except (TypeError, ValueError):
                continue
            got = aliased.get(role, 0.0) / total * 100.0
            if abs(got - wanted) > COMPOSITION_TOLERANCE_PCT:
                drift.append(f"{role} {got:.0f}% vs {wanted:.0f}%")
        residual = sum(sec for role, sec in aliased.items() if role not in wanted_roles)
        for role, seconds in sorted(aliased.items()):
            if segments and role not in wanted_roles:
                share = seconds / total * 100.0
                # The DNA names the surfaces it pays for. A small surface it never
                # mentioned — a transition, a title card — is not a violation
                # until the unlisted share as a whole eats more than the tolerance
                # the declared budgets already allow.
                if residual / total * 100.0 > COMPOSITION_TOLERANCE_PCT:
                    drift.append(f"{role} {share:.0f}% has no DNA budget")
        summary = ", ".join(f"{role} {seconds / total:.0%}"
                            for role, seconds in sorted(aliased.items()))
        checks.append(_check(
            "account_composition", bool(segments) and not drift, "FAIL",
            f"{summary}; outside ±{COMPOSITION_TOLERANCE_PCT:.0f}pp: {', '.join(drift)}"
            if drift else (summary or "no screen time measured")))
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
