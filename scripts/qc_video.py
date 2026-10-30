#!/usr/bin/env python3
"""Quality gate for a V1 video project.

Checks:
    - final.mp4 exists, > 100 KB
    - ffprobe parses it
    - 9:16 1080x1920, H.264 + AAC
    - 30 <= duration <= 120 sec
    - storyboard / script / source_refs indicators present
    - no unreferenced AI-generated assets left behind

Emits:
    projects/<slug>/receipts/qc-report.json
    projects/<slug>/receipts/qc-report.md

Status: PASS / WARN / FAIL. FAIL -> final is not production-ready.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from process_utils import hidden_run

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

MIN_FILE_BYTES = 100 * 1024  # 100 KB
MIN_DURATION = 30.0
MAX_DURATION = 120.0
EXPECTED_W, EXPECTED_H = 1080, 1920
# Evidence-first policy: the majority of shots must come from real captured
# assets, not generated visuals.
MIN_REAL_SOURCE_RATIO = 0.70
MAX_GENERATED_RATIO = 0.10

# One vocabulary, shared with the claim and cut gates: a storyboard that says
# `screen_recording` is a capture, not an unlabelled shot.
from contentops.media.claim_coverage import CAPTURE_SPELLINGS  # noqa: E402

REAL_SOURCE_TYPES = set(CAPTURE_SPELLINGS) | {"diagram"}
GENERATED_SOURCE_TYPES = {"generated", "ai_generated", "stock", "title_card"}


def audio_is_not_silence(path: Path) -> dict:
    """Measure loudness so a silent track can't pass as 'has voice'."""
    r = hidden_run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect",
         "-f", "null", "-"],
        timeout=120,
    )
    text = r.stderr or ""
    mean = None
    peak = None
    for line in text.splitlines():
        if "mean_volume:" in line:
            mean = line.split("mean_volume:")[1].strip()
        if "max_volume:" in line:
            peak = line.split("max_volume:")[1].strip()
    def _db(v):
        try:
            return float(v.replace("dB", "").strip())
        except Exception:
            return None
    mean_db, peak_db = _db(mean or ""), _db(peak or "")
    ok = peak_db is not None and peak_db > -50.0
    return {"ok": ok, "mean_volume_db": mean, "max_volume_db": peak,
            "threshold_db": -50.0}


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
    data = {}
    current_section = None
    list_section = None
    list_item = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - ") and list_section is not None:
            kv = line[4:]
            if ":" in kv:
                k, _, v = kv.partition(":")
                list_item = {k.strip(): v.strip().strip('"')}
                list_section.append(list_item)
                current_section = None
            continue
        if line.startswith("  ") and list_item is not None and ":" in line:
            kv = line.strip()
            k, _, v = kv.partition(":")
            list_item[k.strip()] = v.strip().strip('"')
            continue
        if line.startswith("    ") and list_item is not None and ":" in line:
            kv = line.strip()
            k, _, v = kv.partition(":")
            list_item[k.strip()] = v.strip().strip('"')
            continue
        if line.startswith("  ") and current_section is not None:
            kv = line.strip()
            if ":" in kv:
                k, _, v = kv.partition(":")
                current_section[k.strip()] = v.strip().strip('"')
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip().strip('"')
            list_item = None
            if v == "":
                # detect list section (next lines start with "  -")
                list_section = []
                data[k] = list_section
                current_section = None
            else:
                data[k] = v
                current_section = None
                list_section = None
    return data


def _cue_moments(srt: Path | None, duration: float) -> list[float]:
    """Seconds worth sampling: the middle of each declared cue.

    Fixed fractions of the film are wrong whenever the cues are sparse — six
    equally spaced frames can land in the gaps between five cues and report
    "nothing burned in" for a film whose captions are all there. The cue's own
    midpoint is where a burned caption is guaranteed to be up.
    """
    if srt is None or not Path(srt).is_file():
        return [duration * frac for frac in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9)]
    try:
        from contentops.quality.subtitle import parse_srt

        cues = parse_srt(Path(srt).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - an unreadable SRT falls back to sampling
        cues = []
    moments = [(cue.start_ms + cue.end_ms) / 2000.0 for cue in cues]
    moments = [m for m in moments if 0 < m < duration]
    if not moments:
        # A placeholder file with no cue must not become "no caption was ever up":
        # fixed fractions still search the film for burned-in text.
        return [duration * frac for frac in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9)]
    if len(moments) <= 6:
        return moments
    step = len(moments) / 6
    return [moments[int(i * step)] for i in range(6)]


def _expected_size(declared, override) -> tuple[int, int]:
    """The frame this film is supposed to have.

    ``qc_video`` used to grade against the constant 1080x1920, so it could not
    grade a horizontal or 3:4 cut at all: a 1920x1080 bilibili master failed
    ``resolution`` for being exactly the shape its own ``project.yaml`` declares.
    The declaration is the contract; the constant is the fallback only when a
    project does not say, and a malformed value falls back rather than accepting
    whatever arrived.
    """
    for candidate in (override, declared):
        if not candidate:
            continue
        parts = str(candidate).lower().replace("*", "x").split("x")
        if len(parts) != 2:
            continue
        try:
            width, height = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if width > 0 and height > 0:
            return width, height
    return EXPECTED_W, EXPECTED_H


def _subtitles_burned(video: Path, sb: dict, srt: Path | None = None,
                      expect: tuple[int, int] = (EXPECTED_W, EXPECTED_H)) -> dict:
    """Decide whether subtitles are visible: a real subtitle stream, or burned in.

    A subtitle file existing next to the video is NOT evidence that anything is
    visible. Sample a frame where a caption should be up and check whether
    bright pixels appeared in the lower band (the subtitle zone).
    """
    meta = ffprobe_meta(video)
    for s in meta.get("streams", []):
        if s.get("codec_type") == "subtitle":
            return {"ok": True, "method": "subtitle_stream"}

    declared = sb.get("subtitle")
    if not declared:
        return {"ok": False, "method": "none",
                "note": "no subtitle declared and none present"}

    import tempfile
    dur = float(meta.get("format", {}).get("duration", "0") or 0)
    if dur <= 2:
        return {"ok": False, "method": "unknown",
                "note": "video too short to sample"}

    moments = _cue_moments(srt, dur)
    if not moments:
        return {"ok": False, "method": "burned_in_scan",
                "note": "no caption cue falls inside the film"}

    expect_w, expect_h = expect
    band_start = int(expect_h * 0.82) * expect_w
    expected = expect_w * expect_h
    best, samples = 0.0, 0
    with tempfile.TemporaryDirectory() as td:
        for index, seconds in enumerate(moments):
            out = Path(td) / f"f{index}.png"
            r = hidden_run(
                ["ffmpeg", "-y", "-ss", f"{seconds:.2f}", "-i", str(video),
                 "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", str(out)],
                timeout=120,
            )
            if r.returncode != 0 or not out.exists():
                continue
            data = out.read_bytes()
            if len(data) < expected:
                continue
            samples += 1
            band = data[band_start:expected]
            bright = sum(1 for b in band if b > 200)
            best = max(best, bright / max(len(band), 1))
    ok = best > 0.002
    return {"ok": ok, "method": "burned_in_scan",
            "source": "caption_cues" if srt and Path(srt).is_file() else "fixed_fractions",
            "note": f"max bright-pixel ratio across {samples} samples = {best:.5f}"}


def _has_cues(path: Path) -> bool:
    """An SRT with no timing line is a placeholder, not captions.

    A zero-byte ``<target>.srt`` used to win the choice below simply because the
    file existed, and then reported "no caption cue falls inside the film" for a
    film whose captions were burned in. Existence is not content.
    """
    try:
        return "-->" in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _graded_inputs(project: Path, target_name: str,
                   storyboard_override: Path | None = None) -> tuple:
    """A variant render is graded against its own captions and storyboard.

    The easel engine writes and burns ``assets/captions/easel.srt``. Grading it
    against ``default.srt`` — a legacy demo asset the production path never
    writes — reported "no captions" for a film that had them burned in, so the
    target's own captions win and ``default.srt`` is only a fallback.
    """
    candidates = [
        project / "assets" / "captions" / f"{target_name}.srt",
        # An evidence cut's captions are written against its cut plan as
        # assets/captions/cut.srt; that is also the file cut_qc grades. Looking
        # only for <target>.srt/default.srt reported "no captions" for a film
        # whose cues were there.
        project / "assets" / "captions" / "cut.srt",
        project / "assets" / "captions" / "default.srt",
    ]
    present = [c for c in candidates if c.is_file()]
    srt = next((c for c in present if _has_cues(c)), present[0] if present else None)
    if storyboard_override is not None:
        storyboard = storyboard_override
    else:
        storyboard = project / "work" / target_name / "storyboard.json"
        if target_name == "easel" or not storyboard.is_file():
            storyboard = project / "script" / "storyboard.json"
        if not storyboard.is_file():
            # The evidence and code-animation builders write the storyboard they
            # actually render to work/storyboard.json. Grading such a project
            # against an absent script/storyboard.json reported "no storyboard"
            # for a film that has one, and measured its ratio over zero shots.
            storyboard = project / "work" / "storyboard.json"
    return srt, storyboard


def _cut_plan_shares(project: Path) -> dict | None:
    """Provenance measured from the cut plan, when the project declares one.

    Returns None when there is no cut plan. The caller treats a cut plan that
    exists but cannot be read as a failure, not as "no plan": a project that
    cites one and cannot satisfy it must not be graded as if it had not.
    """
    plan_path = project / "script" / "cut-plan.json"
    assets_path = project / "script" / "assets.json"
    if not plan_path.is_file() or not assets_path.is_file():
        return None
    from contentops.media.cut_plan import CutPlan
    from contentops.media.cut_qc import source_shares

    plan = CutPlan.from_dict(json.loads(plan_path.read_text(encoding="utf-8")))
    assets = json.loads(assets_path.read_text(encoding="utf-8"))["assets"]
    shares = source_shares(plan, assets)
    cited = []
    for placement in plan.placements:
        cited.append(placement.asset_id)
        cited += [shot.asset_id for shot in placement.shots if shot.asset_id]
    def _proven(asset_id: str) -> bool:
        return any(assets.get(asset_id, {}).get(key)
                   for key in ("sha256", "path", "png", "html", "video"))

    shares["unproven_assets"] = sorted(
        asset_id for asset_id in set(cited) if not _proven(asset_id))
    # Evidence means a recording that can point at its source, not merely a
    # recording-typed entry that declares nothing.
    shares["real_assets"] = sorted(
        asset_id for asset_id in set(cited)
        if assets.get(asset_id, {}).get("kind") == "recording" and _proven(asset_id))
    return shares


def qc(project: Path, target: str = "", storyboard_override: Path | None = None,
       expect: str | None = None) -> dict:
    project = project.resolve()
    # --video selects which render to grade: "easel", "fallback" or an explicit
    # filename. Defaults to easel.mp4 when it exists (the production render),
    # otherwise falls back to the legacy final.mp4.
    if target:
        final = project / "final" / target
    else:
        easel_vid = project / "final" / "easel.mp4"
        final = easel_vid if easel_vid.exists() else project / "final" / "final.mp4"
    # The frame comes from the project's own declaration, not from a constant:
    # a project that says 1920x1080 is a horizontal film, not a broken vertical one.
    config_path = project / "project.yaml"
    declared_format = parse_yaml(config_path).get("format") if config_path.exists() else None
    expect_w, expect_h = _expected_size(declared_format, expect)
    target_name = Path(target).stem if target else final.stem
    receipts = project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)

    checks = [{"id": "_video", "ok": True, "severity": "INFO", "path": str(final)}]

    # 1) final.mp4 exists
    if not final.exists():
        checks.append({
            "id": "final_exists", "ok": False,
            "severity": "FAIL",
            "msg": f"final.mp4 not found at {final}",
        })
        return _emit(project, checks, target_name)

    # 2) file size
    size = final.stat().st_size
    checks.append({
        "id": "file_size", "ok": size >= MIN_FILE_BYTES,
        "severity": "FAIL" if size < MIN_FILE_BYTES else "PASS",
        "value_bytes": size,
        "min_bytes": MIN_FILE_BYTES,
    })

    # 3) ffprobe parse
    meta = ffprobe_meta(final)
    parse_ok = bool(meta)
    checks.append({
        "id": "ffprobe_parse", "ok": parse_ok,
        "severity": "FAIL" if not parse_ok else "PASS",
    })
    if not parse_ok:
        return _emit(project, checks, target_name)

    streams = meta.get("streams", [])
    fmt = meta.get("format", {})
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})

    width = video.get("width", 0)
    height = video.get("height", 0)
    duration = float(fmt.get("duration", "0"))

    # 4) resolution
    ok_res = (width == expect_w and height == expect_h)
    checks.append({
        "id": "resolution", "ok": ok_res,
        "severity": "FAIL" if not ok_res else "PASS",
        "value": f"{width}x{height}", "expected": f"{expect_w}x{expect_h}",
    })

    # 5) aspect: the film's ratio against the frame it declares, not against a
    # constant. A 16:9 bilibili master is not a broken 9:16 one.
    expected_ratio = expect_w / expect_h
    actual_ratio = width / height if height else 0.0
    aspect_ok = actual_ratio > 0 and abs(actual_ratio - expected_ratio) <= expected_ratio * 0.005
    checks.append({
        "id": "aspect_ratio", "ok": aspect_ok,
        "severity": "FAIL" if not aspect_ok else "PASS",
        "value": f"{width}:{height}",
        "expected": f"{expect_w}:{expect_h}",
    })

    # 6) duration
    dur_ok = MIN_DURATION <= duration <= MAX_DURATION
    checks.append({
        "id": "duration_range", "ok": dur_ok,
        "severity": "WARN" if not dur_ok else "PASS",
        "value_sec": round(duration, 2),
        "expected_range_sec": [MIN_DURATION, MAX_DURATION],
    })

    # 7) video codec
    vcodec = video.get("codec_name", "")
    checks.append({
        "id": "video_codec_h264", "ok": vcodec in ("h264", "libx264"),
        "severity": "WARN" if vcodec not in ("h264", "libx264") else "PASS",
        "value": vcodec,
    })

    # 8) audio present
    has_audio = bool(audio)
    checks.append({
        "id": "audio_present", "ok": has_audio,
        "severity": "WARN" if not has_audio else "PASS",
    })

    # 9) audio codec
    acodec = audio.get("codec_name", "")
    checks.append({
        "id": "audio_codec_aac", "ok": acodec in ("aac",),
        "severity": "WARN" if acodec not in ("aac",) else "PASS",
        "value": acodec,
    })

    # 10) script / storyboard / source_refs
    project_yaml = project / "project.yaml"
    cfg = parse_yaml(project_yaml) if project_yaml.exists() else {}
    source_refs = cfg.get("source_refs", [])
    checks.append({
        "id": "project_yaml", "ok": bool(cfg),
        "severity": "WARN" if not cfg else "PASS",
    })
    checks.append({
        "id": "source_refs_recorded", "ok": isinstance(source_refs, list),
        "severity": "WARN" if not isinstance(source_refs, list) else "PASS",
        "value_count": len(source_refs) if isinstance(source_refs, list) else 0,
    })

    srt, storyboard = _graded_inputs(project, target_name, storyboard_override)
    checks.append({"id": "graded_storyboard", "ok": storyboard.is_file(),
                   "severity": "FAIL" if not storyboard.is_file() else "PASS",
                   "path": str(storyboard)})
    # No caption file at all is a finding, not a crash: calling ``.exists()`` on
    # ``None`` used to abort the whole report before a single ratio was measured.
    checks.append({
        "id": "caption_srt_present", "ok": srt is not None,
        "severity": "WARN" if srt is None else "PASS",
        "path": str(srt) if srt is not None else "",
    })

    # --- evidence-first checks -------------------------------------------------
    script_md = project / "script" / "master.md"
    checks.append({
        "id": "script_exists", "ok": script_md.exists() and script_md.stat().st_size > 0,
        "severity": "FAIL" if not script_md.exists() else "PASS",
        "path": str(script_md),
    })

    sb = {}
    if storyboard.exists():
        try:
            sb = json.loads(storyboard.read_text(encoding="utf-8"))
        except Exception as e:
            sb = {}
            checks.append({
                "id": "storyboard_parses", "ok": False, "severity": "FAIL",
                "msg": f"invalid JSON: {e}",
            })
    checks.append({
        "id": "storyboard_exists", "ok": bool(sb.get("shots")),
        "severity": "FAIL" if not sb.get("shots") else "PASS",
        "shot_count": len(sb.get("shots", []) or []),
    })

    # --- a replication must still honour the plan it was derived from ---------
    # Only projects that wrote script/replication-plan.json are graded here, so
    # an ordinary episode is untouched. For one that claims a reference, every
    # drift is a FAIL: the account composition, the derived budget, the hook and
    # the ban on touching the reference film.
    if (project / "script" / "replication-plan.json").is_file():
        from contentops.workflow import replication

        # Grade the plan against the film that exists, not only the storyboard
        # that was meant to become it. Summing the storyboard's declared
        # durations once certified a budget the render did not meet.
        #
        # The account comes from project.yaml, not from the observation: the
        # observation is a writable project file, so a plan derived for another
        # account would otherwise only ever be compared with itself.
        dna = None
        declared = replication.declared_account(project)
        observed = str((replication.load_observation(project) or {}).get("account_slug") or "")
        if not declared:
            checks.append({"id": "replication_account_declared", "ok": False,
                           "severity": "FAIL",
                           "detail": "project.yaml declares no account_slug, so the "
                                     "plan cannot be graded against an account DNA"})
        else:
            try:
                dna = replication.load_dna(declared)
            except replication.ReplicationError as exc:
                checks.append({"id": "replication_account_declared", "ok": False,
                               "severity": "FAIL", "detail": str(exc)})
            checks.append({"id": "replication_observation_account", "ok": observed == declared,
                           "severity": "FAIL",
                           "detail": f"the observation names {observed!r}, the episode is "
                                     f"{declared!r}" if observed != declared
                           else f"observation and project.yaml agree on {declared!r}"})
        contract = replication.check(project, dna=dna, storyboard=storyboard, render=final)
        for row in contract["checks"]:
            checks.append({"id": f"replication_{row['id']}", "ok": row["ok"],
                           "severity": row["severity"], "detail": row["detail"]})

    shots = sb.get("shots", []) or []
    real_n = sum(1 for s in shots if s.get("source_type") in REAL_SOURCE_TYPES)
    gen_n = sum(1 for s in shots if s.get("source_type") in GENERATED_SOURCE_TYPES)

    def _seconds(predicate) -> float:
        total = 0.0
        for shot in shots:
            if not predicate(shot):
                continue
            try:
                total += float(shot.get("duration") or 0.0)
            except (TypeError, ValueError):
                continue
        return total

    # Duration, not shot count: one ten-second generated clip must not weigh the
    # same as ten one-second real shots. The count version reported 88% real for
    # a cut whose measured screen time was mostly animation.
    real_s = _seconds(lambda s: s.get("source_type") in REAL_SOURCE_TYPES)
    gen_s = _seconds(lambda s: s.get("source_type") in GENERATED_SOURCE_TYPES)
    declared_s = real_s + gen_s
    if declared_s:
        ratio = real_s / declared_s
        basis = "storyboard_duration"
    elif real_n + gen_n:
        # Duration is the right basis, but a storyboard that declares captures
        # without per-shot durations has no screen time to weigh. Publishing 0.0
        # was not a measurement: it reported "0% real" for a cut full of
        # captures and, for an evidence-led account, turned that artefact into a
        # FAIL. The shot count is coarser, but it is something that was counted.
        ratio = real_n / (real_n + gen_n)
        basis = "storyboard_shot_count"
    else:
        ratio = None
        basis = "unmeasured"
    real_shots, gen_shots = real_n, gen_n
    real_assets = generated_assets = None

    # A cut plan carries the provenance the storyboard usually omits: the
    # evidence builders record which captured asset each placement shows, and
    # cut_qc already measures it by final-cut duration. When both exist the cut
    # plan wins, so the two gates cannot contradict each other about one film.
    plan_shares = None
    try:
        plan_shares = _cut_plan_shares(project)
    except Exception as exc:  # noqa: BLE001 - a broken plan must surface, not crash
        checks.append({"id": "cut_plan_readable", "ok": False, "severity": "FAIL",
                       "error": str(exc)[:200]})
    if plan_shares is not None:
        real_s = plan_shares["real_s"]
        gen_s = plan_shares["generated_s"]
        declared_s = plan_shares["total_s"]
        ratio = plan_shares["real_ratio"]
        basis = "cut_plan_duration"
        # Shot counts describe a storyboard this measurement did not read; the
        # plan's asset ids are the honest count for this basis.
        real_shots = gen_shots = None
        real_assets, generated_assets = len(plan_shares["real_assets"]), 0
    # Which account owns this episode decides whether a thin real-source share is
    # advisory or fatal. An evidence-led account (1024) publishes captures; an
    # explanatory one (Future Intelligence) is built from abstractions and must
    # not be punished for it.
    account_mode = ""
    max_generated = MAX_GENERATED_RATIO
    try:
        from contentops.workflow import replication as _replication

        account_slug = str(cfg.get("account_slug") or "")
        if account_slug:
            dna = _replication.load_dna(account_slug)
            account_mode = str((dna.get("evidence") or {}).get("mode") or "")
            segments = (((dna.get("visual") or {}).get("composition") or {})
                        .get("segments") or [])
            evidence_pct = 0.0
            for segment in segments:
                if str(segment.get("role")) in _replication.EVIDENCE_ROLES:
                    evidence_pct += float(segment.get("pct") or 0.0)
            if segments:
                # The account's own composition already says how much of the cut
                # may be abstraction. A flat 10% cap made 1024's declared 25%
                # vector budget unreachable, so the ceiling is the account's own
                # non-evidence share; with no DNA the flat floor still applies.
                max_generated = max(MAX_GENERATED_RATIO, (100.0 - evidence_pct) / 100.0)
    except Exception:  # noqa: BLE001 - an unreadable DNA is graded elsewhere
        account_mode = ""
    evidence_led = account_mode == "EVIDENCE_LED"

    if ratio is None:
        checks.append({
            "id": "real_source_ratio", "ok": False,
            "severity": "FAIL" if evidence_led else "INFO",
            "value": None, "min": MIN_REAL_SOURCE_RATIO,
            "account_mode": account_mode or "unresolved", "basis": basis,
            "real_shots": real_shots, "generated_shots": gen_shots,
            "note": "no shot declares both a source type and a duration, so the "
                    "real share was not measured",
        })
    else:
        checks.append({
            "id": "real_source_ratio", "ok": ratio >= MIN_REAL_SOURCE_RATIO,
            "severity": ("FAIL" if evidence_led else "WARN")
            if ratio < MIN_REAL_SOURCE_RATIO else "PASS",
            "value": round(ratio, 3),
            "min": MIN_REAL_SOURCE_RATIO,
            "account_mode": account_mode or "unresolved",
            "basis": basis,
            "real_seconds": round(real_s, 3),
            "generated_seconds": round(gen_s, 3),
            "real_shots": real_shots, "generated_shots": gen_shots,
            "real_assets": real_assets, "generated_assets": generated_assets,
            "note": "AI-generated key visuals must not be the majority",
        })

    # The floor alone says nothing about the ceiling: a cut could be 20% real,
    # 80% still generated and clear no floor while the generated share is what
    # actually filled the screen.
    generated_ratio = None if ratio is None else (gen_s / declared_s if declared_s else 0.0)
    if generated_ratio is None:
        checks.append({
            "id": "generated_ratio", "ok": False,
            "severity": "FAIL" if evidence_led else "INFO",
            "value": None, "max": round(max_generated, 3),
            "account_mode": account_mode or "unresolved", "basis": basis,
            "note": "the generated share was not measured: no shot declares both "
                    "a source type and a duration",
        })
    else:
        checks.append({
            "id": "generated_ratio", "ok": generated_ratio <= max_generated,
            "severity": ("FAIL" if evidence_led else "WARN")
            if generated_ratio > max_generated else "PASS",
            "value": round(generated_ratio, 3),
            "max": round(max_generated, 3),
            "account_mode": account_mode or "unresolved",
            "basis": basis,
            "note": "a generated clip may illustrate a beat, never carry the cut",
        })

    if plan_shares is not None:
        unproven = plan_shares["unproven_assets"]
        checks.append({
            "id": "source_provenance_complete", "ok": not unproven,
            "severity": "WARN" if unproven else "PASS",
            "basis": "cut_plan",
            "assets_without_a_source": unproven,
        })
    else:
        missing_prov = [i for i, s in enumerate(shots)
                        if not s.get("source") or not s.get("source_type")]
        checks.append({
            "id": "source_provenance_complete", "ok": not missing_prov,
            "severity": "WARN" if missing_prov else "PASS",
            "basis": "storyboard",
            "missing_shot_indices": missing_prov,
        })

    engine = (sb.get("engine") or cfg.get("engine") or "").strip()
    checks.append({
        "id": "engine_recorded", "ok": bool(engine),
        "severity": "WARN" if not engine else "PASS",
        "value": engine or "unrecorded",
    })

    # --- voice is actually audible --------------------------------------------
    if final.exists():
        vol = audio_is_not_silence(final)
        checks.append({
            "id": "voice_not_silence", "ok": vol["ok"],
            "severity": "WARN" if not vol["ok"] else "PASS",
            "max_volume_db": vol["max_volume_db"],
            "mean_volume_db": vol["mean_volume_db"],
        })

    # --- subtitles are burned in ---------------------------------------------
    burned = _subtitles_burned(final, sb, srt, expect=(expect_w, expect_h))
    checks.append({
        "id": "subtitle_burned_or_track", "ok": burned["ok"],
        "severity": "WARN" if not burned["ok"] else "PASS",
        "method": burned["method"],
        "source": burned.get("source", ""),
        "note": burned.get("note", ""),
    })

    # 11) no unreferenced AI-generated assets: count real vs generated
    if plan_shares is not None:
        # An evidence cut keeps its captures in the capture project and cites
        # them by repo:// path; the old directory probe found nothing and warned
        # about a film made entirely of recordings. The plan's own declarations
        # are the evidence, and they are already proven above.
        checks.append({
            "id": "real_evidence_present", "ok": bool(plan_shares["real_assets"]),
            "severity": "WARN" if not plan_shares["real_assets"] else "PASS",
            "basis": "cut_plan",
            "assets": plan_shares["real_assets"],
        })
    else:
        real = []
        for sub in ("sources/screenshots", "sources/diagrams", "sources/recordings"):
            d = project / sub
            if d.exists():
                for pat in ("*.png", "*.jpg", "*.jpeg"):
                    real.extend(d.glob(pat))
        checks.append({
            "id": "real_evidence_present", "ok": len(real) > 0,
            "severity": "WARN" if len(real) == 0 else "PASS",
            "basis": "sources_directory",
            "value_count": len(real),
        })

    # 12) voice provenance. Prefer the storyboard's recorded provider — it is
    # what actually produced THIS render. project.yaml's voice_quality reflects
    # whichever engine ran last (usually the fallback) and must not be
    # attributed to an Easel render.
    sb_provider = (sb.get("voice_provider") or "").strip()
    yaml_voice = (cfg.get("voice_quality") or "").strip()
    provider = sb_provider or yaml_voice or "unknown"
    low = provider.lower()
    if "edge" in low:
        vq, warn = "edge_tts_fallback", True
    elif "sapi" in low or "silence" in low or low == "fallback":
        vq, warn = "fallback", True
    elif provider == "unknown":
        vq, warn = "unknown", True
    else:
        vq, warn = "configured_provider", False
    checks.append({
        "id": "voice_quality_declared", "ok": True,
        "severity": "INFO",
        "voice_provider": provider,
        "voice_quality": vq,
        "production_quality_warning": warn,
        "note": "mechanical/fallback voice keeps the render at READY_FOR_HUMAN_REVIEW; "
                "only a human can accept it as production (V1 spec §11)",
    })

    return _emit(project, checks, target_name)


def _emit(project: Path, checks: list[dict], target_name: str = "") -> dict:
    severity_rank = {"FAIL": 3, "WARN": 2, "INFO": 1, "PASS": 0}
    overall = "PASS"
    for c in checks:
        sev = c.get("severity", "PASS")
        if sev == "INFO":
            continue  # informational only, doesn't affect PASS/WARN/FAIL rollup
        if severity_rank.get(sev, 0) > severity_rank.get(overall, 0):
            overall = sev
        if not c.get("ok"):
            if sev == "FAIL":
                overall = "FAIL"
                break
            if sev == "WARN" and overall == "PASS":
                overall = "WARN"

    out = {
        "project": str(project),
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "video": checks[0].get("_video", "") if checks else "",
        "overall": overall,
        "checks": [{k: v for k, v in c.items() if not k.startswith("_")} for c in checks],
    }
    suffix = f"-{target_name}" if target_name else ""
    json_path = project / "receipts" / f"qc-report{suffix}.json"
    md_path = project / "receipts" / f"qc-report{suffix}.md"
    json_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [f"# QC Report — {project.name}", "", f"**Video**: `{target_name}`", "", f"**Overall**: `{overall}`", ""]
    lines.append(f"**Checked at**: {out['checked_at']}")
    lines.append("")
    lines.append("| Check | Status | Severity | Detail |")
    lines.append("|---|---|---|---|")
    for c in checks:
        status = "OK" if c.get("ok") else "FAIL"
        sev = c.get("severity", "PASS")
        detail = ", ".join(f"{k}={v}" for k, v in c.items() if k not in ("id", "ok", "severity"))
        lines.append(f"| {c['id']} | {status} | {sev} | {detail} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project", help="project dir, e.g. projects/easel-review")
    p.add_argument("--video", default="",
                   help="which render to grade: easel | fallback | <file>.mp4")
    p.add_argument("--storyboard", type=Path,
                   help="grade the storyboard used for this render, not a legacy script")
    p.add_argument("--expect", default=None,
                   help="expected frame, WxH (default: the project's own format)")
    args = p.parse_args()
    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / args.project).resolve()
    result = qc(project, target=args.video, storyboard_override=args.storyboard,
                expect=args.expect)
    return 1 if result.get("overall") == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())