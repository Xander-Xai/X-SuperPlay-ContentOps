#!/usr/bin/env python3
"""Build the two account-native videos from one locked source.

One Source, Multiple Native Assets:
  1024 / Explore   result-first re-order, conflict -> problem -> context -> verdict
  Future Intelligence / Build   full eight-unit engineering walkthrough

Both reuse the approved v3 narration and the six editorial cards. The narration
is cut at unit boundaries with audio_ops, composed through the pinned Easel
path, then intro/outro are attached with video-intro-outro. No provider call and
no auto-publish: each package stops at PENDING_FOUNDER_REVIEW.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from process_utils import hidden_run  # noqa: E402
from assemble_easel import run as assemble_run  # noqa: E402
from qc_video import qc as qc_run  # noqa: E402
from contentops.media.qc_canonical import (  # noqa: E402
    CURRENCY_CURRENT,
    canonical_qc_report,
    render_canonical_qc_markdown,
)

FULL_RECEIPT = (ROOT / "projects" / "easel-enhanced-golden" / "v3-full-editorial"
                / "receipts" / "v3-sample-video.json")
EVIDENCE_LOCK = (ROOT / "projects" / "easel-enhanced-golden" / "evidence"
                 / "evidence-lock.json")
NARRATION = ROOT / "outputs" / "founder-v3-full" / "narration.wav"
INTRO = ROOT / "outputs" / "editorial" / "intro-editorial.mp4"
OUTRO = ROOT / "outputs" / "editorial" / "outro-editorial.mp4"
SHARED = ROOT / ".runtime" / "easel" / "skills" / "shared" / "scripts"

def load_specs() -> Dict[str, Dict[str, Any]]:
    """Account DNA is the gene: the workflow reads it, it is not hardcoded here."""
    specs: Dict[str, Dict[str, Any]] = {}
    for path in sorted((ROOT / "config" / "accounts").glob("*.json")):
        dna = json.loads(path.read_text(encoding="utf-8"))
        slug = dna["slug"]
        specs[slug] = {
            "account": dna["account"],
            "role": dna["role"],
            "units": dna["narrative"]["beats"],
            "opening_unit": dna["narrative"]["opening_unit"],
            "target_duration": dna["narrative"]["target_duration_s"],
            "out_name": slug.replace("x-superplay-", ""),
            "title": dna["title"],
            "description": dna["description"],
            "hashtags": dna["hashtags"],
            "platforms": dna["platforms"],
            "card_dir": dna["visual"]["card_set"],
            "intro": dna["visual"].get("motion_intro",
                                      "outputs/editorial/intro-editorial.mp4"),
            "motion_segments": dna["visual"].get("motion_segments", {}),
            "cover_time": dna["visual"]["cover_time_s"],
            "cta": dna["narrative"]["cta"],
            "horizontal": dna.get("horizontal", False),
            "gpu_required": dna["gpu_required"],
            "dna": path.relative_to(ROOT).as_posix(),
        }
    if not specs:
        raise SystemExit("no account DNA found under config/accounts/")
    return specs


VARIANTS = load_specs()


def _run(cmd: List[Any], timeout: int = 900) -> Dict[str, Any]:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = hidden_run([str(item) for item in cmd], timeout=timeout, env=env)
    return {"rc": proc.returncode, "stdout": (proc.stdout or "")[-600:],
            "stderr": (proc.stderr or "")[-600:]}


def probe_duration(path: Path) -> float:
    proc = hidden_run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path),
    ], timeout=60)
    try:
        return float((proc.stdout or "").strip())
    except ValueError as exc:
        raise SystemExit(f"ffprobe could not read {path}") from exc


def cut_audio(units: Dict[str, Dict[str, Any]], order: List[str], work: Path) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    segments = []
    for unit_id in order:
        unit = units[unit_id]
        out = work / f"{unit_id}.wav"
        result = _run([
            sys.executable, str(SHARED / "audio_ops.py"), "trim",
            str(NARRATION), "-o", str(out),
            "--start", f"{unit['start_s']:.3f}",
            "--duration", f"{unit['duration_s']:.3f}",
        ])
        if result["rc"] != 0 or not out.is_file():
            raise SystemExit(f"trim failed for {unit_id}: {result['stderr']}")
        segments.append(out)
    joined = work / "narration-cut.wav"
    result = _run([
        sys.executable, str(SHARED / "audio_ops.py"), "concat",
        *[str(segment) for segment in segments], "-o", str(joined),
    ])
    if result["rc"] != 0 or not joined.is_file():
        raise SystemExit(f"concat failed: {result['stderr']}")
    return joined


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + chr(10),
                    encoding="utf-8")


def write_loop_artifacts(project: Path, spec: Dict[str, Any], *,
                         qc_overall: str, duration_s: float, cover_exists: bool,
                         storyboard: Dict[str, Any],
                         publish: Dict[str, Any]) -> Dict[str, Any]:
    """Record the stages reached and the ones that are honestly blocked.

    A closed loop is not a claim that publishing happened. Claim-ledger absence,
    the human gate, manual publish, metrics and weekly review are all named.
    """
    receipts = project / "receipts"
    lock = json.loads(EVIDENCE_LOCK.read_text(encoding="utf-8"))
    claim_status = str(lock.get("claim_ledger_status") or "UNKNOWN")
    claims_status = "PARTIAL" if "NOT_AVAILABLE" in claim_status else "PASS"

    shots = storyboard["shots"]
    units = list(dict.fromkeys(shot["unit"] for shot in shots))
    images = [shot["image"] for shot in shots if shot.get("image")]
    low, high = spec["target_duration"]
    editorial_checks = [
        {"id": "opening_matches_dna",
         "ok": bool(units) and units[0] == spec["opening_unit"],
         "value": units[:1], "expected": spec["opening_unit"]},
        {"id": "unit_count_matches_dna",
         "ok": len(units) == len(spec["units"]),
         "value": len(units), "expected": len(spec["units"])},
        {"id": "duration_in_account_range",
         "ok": low <= duration_s <= high,
         "value_s": round(duration_s, 3), "range_s": [low, high]},
        {"id": "title_has_hook",
         "ok": any(marker in spec["title"] for marker in
                   ("实测", "拆解", "能跑", "没过", "错配", "跑得起来")),
         "value": spec["title"]},
        {"id": "cta_present", "ok": bool(spec["cta"]), "value": spec["cta"]},
        {"id": "card_set_matches_dna",
         "ok": bool(images) and all(image.startswith(spec["card_dir"]) for image in images)},
    ]
    editorial_overall = "PASS" if all(check["ok"] for check in editorial_checks) else "WARN"
    _write_json(receipts / "editorial-qc.json", {
        "schema": "contentops.editorial-qc/v1",
        "account": spec["account"],
        "overall": editorial_overall,
        "checks": editorial_checks,
    })

    stages = [
        {"name": "SOURCE_LOCKED", "status": "PASS",
         "evidence": FULL_RECEIPT.relative_to(ROOT).as_posix(),
         "evidence_lock_fingerprint": lock.get("fingerprint")},
        {"name": "CLAIMS_BOUND", "status": claims_status, "reason": claim_status},
        {"name": "ACCOUNT_ROUTED", "status": "PASS", "evidence": spec["dna"]},
        {"name": "NARRATIVE_ADAPTED", "status": "PASS", "evidence": spec["units"]},
        {"name": "AUDIO_READY", "status": "PASS",
         "evidence": "project://work/audio/narration-cut.wav"},
        {"name": "VISUALS_READY", "status": "PASS", "evidence": spec["card_dir"]},
        {"name": "COMPOSED", "status": "PASS",
         "evidence": f"project://final/{spec['out_name']}.mp4"},
        {"name": "EDITORIAL_QC", "status": editorial_overall,
         "evidence": "project://receipts/editorial-qc.json"},
        {"name": "TECHNICAL_QC", "status": qc_overall,
         "evidence": f"project://receipts/qc-report-{spec['out_name']}.json"},
        {"name": "HUMAN_REVIEW", "status": "PENDING",
         "reason": "Founder must watch the cut and fill human-review.json"},
        {"name": "PUBLISHED", "status": "BLOCKED",
         "reason": "manual publish only; the repository forbids auto-publish"},
        {"name": "METRICS_SNAPSHOT", "status": "BLOCKED",
         "reason": "requires a real published URL"},
        {"name": "WEEKLY_REVIEW", "status": "BLOCKED",
         "reason": "requires publication receipts and metrics"},
    ]
    run_state = {
        "schema": "contentops.account-run/v1",
        "account": spec["account"],
        "role": spec["role"],
        "account_dna": spec["dna"],
        "gpu_required": spec["gpu_required"],
        "stage": "PENDING_HUMAN_REVIEW",
        "stages": stages,
    }
    _write_json(receipts / "run-state.json", run_state)

    asset_map = publish.get("platform_asset_map", {})
    checklist = {
        "schema": "contentops.publish-checklist/v1",
        "account": spec["account"],
        "platforms": spec["platforms"],
        "checks": [
            {"id": "title_present", "ok": bool(spec["title"])},
            {"id": "title_length", "ok": len(spec["title"]) <= 60,
             "value": len(spec["title"])},
            {"id": "description_present", "ok": bool(spec["description"])},
            {"id": "hashtags", "ok": len(spec["hashtags"]) >= 3,
             "value": len(spec["hashtags"])},
            {"id": "cover_exists", "ok": cover_exists},
            {"id": "duration_in_account_range", "ok": low <= duration_s <= high,
             "value_s": round(duration_s, 3), "range_s": [low, high]},
            {"id": "platform_asset_map", "ok": set(asset_map) == set(spec["platforms"]),
             "value": asset_map},
            {"id": "editorial_qc", "ok": editorial_overall == "PASS",
             "status": editorial_overall},
            {"id": "human_review", "ok": False, "status": "PENDING"},
            {"id": "real_url", "ok": False, "status": "NOT_PUBLISHED"},
        ],
        "publish_status": "NOT_PUBLISHED",
    }
    _write_json(receipts / "publish-checklist.json", checklist)

    _write_json(receipts / "human-review.json", {
        "schema": "contentops.human-review/v1",
        "account": spec["account"],
        "status": "PENDING_FOUNDER_REVIEW",
        "scores": {"voice": None, "image_usefulness": None,
                   "visual_consistency": None, "artifact_severity": None,
                   "pace": None, "publishability": None},
        "decision": None,
        "failure_positions": [],
    })
    _write_json(receipts / "metrics-snapshot.json", {
        "schema": "contentops.metrics-snapshot/v1",
        "account": spec["account"],
        "platforms": spec["platforms"],
        "status": "BLOCKED",
        "reason": "requires a real published URL; fill after manual publishing",
        "source": "MANUAL",
        "metrics": None,
    })
    _write_json(receipts / "publish-receipt.json", {
        "schema": "contentops.publish-receipt/v1",
        "account": spec["account"],
        "platforms": spec["platforms"],
        "status": "NOT_PUBLISHED",
        "published_at": None,
        "urls": {},
        "note": "fill after manual publishing; automation never claims a URL",
    })
    _write_json(receipts / "weekly-review.json", {
        "schema": "contentops.weekly-review/v1",
        "account": spec["account"],
        "status": "BLOCKED",
        "reason": "requires publication receipts and metrics",
        "week": None,
        "metrics": None,
        "decisions": [],
    })
    return run_state


def build_variant(slug: str, spec: Dict[str, Any], units: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    project = ROOT / "projects" / slug
    for directory in (project / "script", project / "final", project / "receipts",
                      project / "work" / "audio", project / "assets" / "voice"):
        directory.mkdir(parents=True, exist_ok=True)

    narration = cut_audio(units, spec["units"], project / "work" / "audio")
    local_voice = project / "assets" / "voice" / "narration.wav"
    shutil.copyfile(narration, local_voice)
    cards_root = ROOT / spec.get("card_dir", "outputs/editorial/by-placement")

    shots = []
    motion_used: Dict[str, Dict[str, Any]] = {}
    motion_fallbacks: Dict[str, str] = {}
    for unit_id in spec["units"]:
        unit = units[unit_id]
        card = cards_root / f"{unit['placement_id']}.png"
        if not card.is_file():
            raise SystemExit(f"card missing: {card}")
        remaining = float(unit["duration_s"])
        segment = (spec.get("motion_segments") or {}).get(unit_id)
        if segment:
            seg_path = ROOT / segment["path"]
            seg_duration = float(segment.get("duration_s", 0))
            if seg_path.is_file() and 0.5 <= seg_duration < remaining:
                shots.append({
                    "video": seg_path.relative_to(ROOT).as_posix(),
                    "duration": round(seg_duration, 3),
                    "source": unit["image_logical"],
                    "source_type": "real_screenshot",
                    "narration": unit.get("text", ""),
                    "unit": unit_id,
                    "placement": unit["placement_id"],
                    "motion_segment": True,
                })
                motion_used[unit_id] = {
                    "path": segment["path"],
                    "duration_s": seg_duration,
                }
                remaining = round(remaining - seg_duration, 3)
            else:
                motion_fallbacks[unit_id] = (
                    "segment file missing" if not seg_path.is_file()
                    else f"segment {seg_duration}s does not fit unit {unit['duration_s']}s"
                )
        if remaining > 0.05:
            shots.append({
                "image": card.relative_to(ROOT).as_posix(),
                "duration": round(remaining, 3),
                "source": unit["image_logical"],
                "source_type": "real_screenshot",
                "narration": unit.get("text", ""),
                "unit": unit_id,
                "placement": unit["placement_id"],
                "designed_card": card.relative_to(ROOT).as_posix(),
            })

    narration_s = probe_duration(narration)
    planned = sum(shot["duration"] for shot in shots)
    if abs(narration_s - planned) > 0.05:
        # The concat rounds sample boundaries; absorb the residue in the last
        # shot so the video clock matches the audio exactly.
        shots[-1]["duration"] = round(shots[-1]["duration"] + (narration_s - planned), 3)

    storyboard = {
        "size": "1080x1920",
        "image_motion": "static",
        "pad_mode": "trim",
        "shots": shots,
        "narration": local_voice.relative_to(ROOT).as_posix(),
        "subtitle": None,
        "engine": "easel",
        "voice_provider": "minimax_m_plan/speech-2.8-hd (v3 full, founder clone)",
        "generated_visuals": {"count": 0, "policy": "real_assets_only"},
        "timeline_policy": (
            "unit durations are the measured v3 full-narration timings; the 1024 "
            "variant re-orders complete units rather than cutting mid-sentence"
        ),
    }
    (project / "script" / "storyboard.json").write_text(
        json.dumps(storyboard, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (project / "script" / "master.md").write_text(
        f"# {spec['account']} · {spec['title']}\n\n"
        f"Role: {spec['role']}. Source units: {', '.join(spec['units'])}.\n"
        "One locked evidence source; the two accounts differ in order, length and "
        "framing, not in facts.\n",
        encoding="utf-8",
    )
    (project / "project.yaml").write_text(
        f'slug: {slug}\ntitle: "{spec["title"]}"\naccount: "{spec["account"]}"\n'
        f'role: {spec["role"]}\nplatforms: [{", ".join(spec["platforms"])}]\n',
        encoding="utf-8",
    )

    composed = assemble_run(project, out_name="main")
    if composed.get("status") != "OK":
        raise SystemExit(f"{slug}: compose blocked: {composed}")

    account_out = project / "final" / f"{spec['out_name']}.mp4"
    intro_path = ROOT / spec["intro"]
    intro_fallback = not intro_path.is_file()
    if intro_fallback:
        intro_path = INTRO
    attached = _run([
        sys.executable, str(SHARED / "intro_outro.py"), "attach",
        "--main", str(project / "final" / "main.mp4"),
        "--intro", str(intro_path), "--outro", str(OUTRO),
        "--transition", "fade", "--trans-duration", "0.5",
        "-o", str(account_out),
    ])
    if attached["rc"] != 0 or not account_out.is_file():
        raise SystemExit(f"{slug}: intro/outro attach failed: {attached['stderr']}")

    cover = project / "final" / "cover.png"
    cover_result = _run([
        sys.executable, str(SHARED / "video_ops.py"), "frame",
        "-i", str(account_out), "-o", str(cover),
        "--time", f"{spec['cover_time']:.2f}",
    ])
    if cover_result["rc"] != 0:
        cover = None

    derived = []
    if spec.get("horizontal"):
        horizontal = project / "final" / f"{spec['out_name']}-16x9.mp4"
        result = _run([
            sys.executable, str(SHARED / "reframe.py"), "reframe",
            "-i", str(account_out), "-o", str(horizontal),
            "--ratio", "16:9", "--mode", "blur",
        ])
        if result["rc"] == 0 and horizontal.is_file():
            derived.append({
                "platform": "bilibili",
                "path": f"project://final/{horizontal.name}",
                "width": 1920,
                "height": 1080,
                "mode": "blur",
            })

    qc_runtime = qc_run(project, target=account_out.name)
    qc_report = canonical_qc_report(
        qc_runtime, repo_root=ROOT, project_root=project,
        graded_target=f"project://final/{account_out.name}", currency=CURRENCY_CURRENT,
    )
    qc_report["evidence_provenance"] = {
        "mode": "canonical_reference_by_path",
        "copies_in_project": 0,
        "reason": "shots reuse the locked screenshots by canonical repository path",
    }
    (project / "receipts" / f"qc-report-{spec['out_name']}.json").write_text(
        json.dumps(qc_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (project / "receipts" / f"qc-report-{spec['out_name']}.md").write_text(
        render_canonical_qc_markdown(qc_report, project_name=slug), encoding="utf-8")

    asset_map = {
        platform: f"project://final/{account_out.name}"
        for platform in spec["platforms"]
    }
    for asset in derived:
        asset_map[asset["platform"]] = asset["path"]

    publish = {
        "schema": "contentops.publish-package/v1",
        "account": spec["account"],
        "role": spec["role"],
        "title": spec["title"],
        "description": spec["description"],
        "hashtags": spec["hashtags"],
        "audience_cta": spec["cta"],
        "platforms": spec["platforms"],
        "account_dna": spec["dna"],
        "gpu_required": spec["gpu_required"],
        "video": f"project://final/{account_out.name}",
        "cover": f"project://final/cover.png" if cover else None,
        "derived_assets": derived,
        "platform_asset_map": asset_map,
        "duration_s": round(probe_duration(account_out), 3),
        "human_review": "PENDING_FOUNDER_REVIEW",
        "publish_status": "NOT_PUBLISHED",
        "note": "No URL is claimed until a human publishes and records it.",
    }
    (project / "receipts" / "publish-package.json").write_text(
        json.dumps(publish, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    receipt = {
        "schema": "contentops.account-variant/v1",
        "account": spec["account"],
        "role": spec["role"],
        "account_dna": spec["dna"],
        "audience_cta": spec["cta"],
        "gpu_required": spec["gpu_required"],
        "intro": {
            "requested": spec["intro"],
            "used": intro_path.relative_to(ROOT).as_posix(),
            "fallback": intro_fallback,
        },
        "motion_segments": motion_used,
        "motion_fallbacks": motion_fallbacks,
        "source": {
            "narration": NARRATION.relative_to(ROOT).as_posix(),
            "units": spec["units"],
            "cards": sorted({unit["placement_id"] for unit in units.values()
                             if unit["unit_id"] in spec["units"]}),
        },
        "storyboard": f"project://script/storyboard.json",
        "compose": {"status": composed.get("status"),
                    "video": f"project://final/{account_out.name}"},
        "qc": {"overall": qc_report.get("overall")},
        "editorial_qc": "project://receipts/editorial-qc.json",
        "derived_assets": derived,
        "platform_asset_map": asset_map,
        "publish_package": f"project://receipts/publish-package.json",
        "skill_route": {
            "audio_edit": "audio-editing (audio_ops.py trim/concat)",
            "design": "card-design + render_card.py",
            "compose": "auto-short-video/assemble.py via assemble_easel",
            "intro_outro": "video-intro-outro (intro_outro.py attach)",
            "cover": "video-editing (video_ops.py frame)",
            "qc": "qc_video.py",
        },
        "provider_calls": {"speech": 0, "image": 0, "video": 0},
        "loop": "project://receipts/run-state.json",
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }
    (project / "receipts" / "variant-receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_loop_artifacts(
        project, spec,
        qc_overall=qc_report.get("overall", "UNKNOWN"),
        duration_s=probe_duration(account_out),
        cover_exists=cover is not None,
        storyboard=storyboard,
        publish=publish,
    )
    return {
        "slug": slug,
        "video": account_out.relative_to(ROOT).as_posix(),
        "duration_source_units": spec["units"],
        "qc": qc_report.get("overall"),
        "cover": cover.relative_to(ROOT).as_posix() if cover else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=tuple(VARIANTS), default="",
                        help="build one account variant only")
    args = parser.parse_args()
    receipt = json.loads(FULL_RECEIPT.read_text(encoding="utf-8"))
    units = {unit["unit_id"]: unit for unit in receipt["units"]}
    for unit in units.values():
        unit["text"] = ""
    # The full receipt stores image_logical; the narration text lives in the
    # storyboard. Pull it back for the storyboard's provenance field.
    storyboard = json.loads((ROOT / "projects" / "easel-enhanced-golden"
                             / "v3-full-editorial" / "script" / "storyboard.json")
                            .read_text(encoding="utf-8"))
    for shot in storyboard["shots"]:
        if shot.get("unit") in units:
            units[shot["unit"]]["text"] = shot.get("narration", "")

    results = []
    for slug, spec in VARIANTS.items():
        if args.only and slug != args.only:
            continue
        results.append(build_variant(slug, spec, units))
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
