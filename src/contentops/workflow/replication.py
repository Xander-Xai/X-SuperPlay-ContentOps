"""Rebuild a reference creator's shot grammar as an original episode.

Why this exists
---------------
"复刻对标博主" was the one instruction the pipeline could not answer. It had a
compositor, a voice, captions and QC, but no step that turned *a reference video*
into *this account's next episode*. Without it, "replication" meant copying a
transcript and hoping the pictures looked similar.

Two things make that dangerous, and both are mechanical properties of the
artefacts rather than matters of taste:

- **A transcript is not an observation.** ASR gives words and rough timings. It
  cannot say where a cut lands, how long a shot holds, or what replaces it. A
  shot list "derived" from subtitles is a guess wearing a timeline, so this
  module refuses to produce one: frame timings exist only when the film was
  opened, and the file's digest is re-checked every time the plan is read.
- **An observation is not a JSON document.** A typed shot list is the same guess
  with a `mode` field set to `FRAME_VIEWED`. So a frame-viewed shot must carry
  the frame itself: :func:`extract_frames` cuts one out of the reference at the
  shot's midpoint, stores 32x32 of it, and the digest of those bytes is
  re-extracted and compared on every validation. A record whose frames do not
  appear in the film it points at is refused, whatever its `mode` says.
- **A reference is a style, not a source.** Nothing from the reference film may
  reach the cut. That is not a policy statement — it is checked against the
  storyboard, so a shot that points at the reference file fails.

What the plan is, and is not
----------------------------
The plan is the *pacing and duties* an original episode must satisfy: how long
each of the account's template beats runs, how fast the cut moves, what each
beat must show, and which composition the account DNA demands. It deliberately
does **not** write the copy. The copy is still written, still reviewed by a
person through :mod:`contentops.workflow.copy_review`, and that review is still
the only gate that unlocks production.

So the order is: observe (gated on a real file) → derive a budget → write the
copy → human review → build → verify the finished cut still honours the budget.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from contentops.media.claim_coverage import CAPTURE_SPELLINGS

__all__ = [
    "FUNCTIONS",
    "FRAMES",
    "OBSERVATION",
    "PLAN",
    "RENDER",
    "ReplicationError",
    "TEMPLATE_FUNCTION",
    "check",
    "composition_shares",
    "cut_frame",
    "declared_account",
    "derive_plan",
    "extract_frames",
    "load_dna",
    "load_plan",
    "load_observation",
    "probe_reference",
    "shot_grammar",
    "validate_observation",
    "write_plan",
]

SCHEMA_OBSERVATION = "contentops.reference-observation/v1"
SCHEMA_PLAN = "contentops.replication-plan/v1"
SCHEMA_CHECK = "contentops.replication-check/v1"

OBSERVATION = Path("reference") / "observation.json"
PLAN = Path("script") / "replication-plan.json"
#: Frames cut out of the reference, one pair per observed shot.
FRAMES = Path("reference") / "frames"
#: The film a replication check measures. A plan that conforms is not a
#: replication until something was rendered from it.
RENDER = Path("final") / "easel.mp4"

#: Frame observation versus subtitle inference. The distinction is the whole
#: point: only the first may carry a timeline.
FRAME_VIEWED = "FRAME_VIEWED"
TRANSCRIPT_ONLY = "TRANSCRIPT_ONLY"
OBSERVATION_MODES = (FRAME_VIEWED, TRANSCRIPT_ONLY)

#: What a shot is *for*. A closed vocabulary, because a free-text function is a
#: place for two episodes to disagree about what "hook" means.
FUNCTIONS: Tuple[str, ...] = (
    "hook",
    "task_statement",
    "measured_process",
    "failure_or_boundary",
    "cost_and_limits",
    "who_its_for",
    "next_validation",
    "requirement_tradeoff",
    "architecture_chain",
    "key_code",
    "root_cause",
    "acceptance_metrics",
    "repro",
    "transition",
)

#: Account template beat -> the shot function that serves it. Both accounts'
#: templates are covered, so a beat with no picture duty is impossible rather
#: than silently dropped.
TEMPLATE_FUNCTION: Dict[str, str] = {
    "HOOK_3S_CONFLICT": "hook",
    "HOOK_3S_PAIN": "hook",
    "TASK_STATEMENT": "task_statement",
    "MEASURED_PROCESS_WITH_EVIDENCE": "measured_process",
    "FAILURE_OR_BOUNDARY": "failure_or_boundary",
    "COST_AND_LIMITS": "cost_and_limits",
    "WHO_IT_IS_FOR_AND_NOT_FOR": "who_its_for",
    "NEXT_VALIDATION_OPPORTUNITY": "next_validation",
    "REQUIREMENT_AND_TRADEOFF": "requirement_tradeoff",
    "ARCHITECTURE_CHAIN": "architecture_chain",
    "KEY_CODE_EXPLAINED": "key_code",
    "ROOT_CAUSE": "root_cause",
    "ACCEPTANCE_METRICS_AND_RISK": "acceptance_metrics",
    "REPRO_AND_REPO": "repro",
}

#: Beats whose picture must be a capture of something real. The rest may be
#: abstraction or comparison, which is what the account composition pays for.
EVIDENCE_FUNCTIONS = frozenset({
    "measured_process", "failure_or_boundary", "architecture_chain", "key_code",
    "root_cause", "acceptance_metrics",
})

COMPARISON_FUNCTIONS = frozenset({"cost_and_limits", "who_its_for"})

#: How far the finished cut may drift from the derived budget. Wide enough for
#: measured speech, narrow enough that the plan still means something.
DURATION_TOLERANCE = 0.15
COMPOSITION_TOLERANCE_PCT = 8.0

#: DNA roles that promise a capture of something real. A role is a free label,
#: so each one must point at a source type that can actually produce a capture:
#: a generated clip relabelled ``screen_recording_evidence`` used to spend the
#: account's evidence budget without ever showing evidence.
EVIDENCE_ROLES = frozenset({
    "screen_recording_evidence", "real_recording", "real_screenshot", "real_document",
})

#: Storyboard ``source_type`` values that are a capture of something that
#: existed. ``generated`` and friends are not, whatever the role says.
#: Spellings that count as a capture, shared with the claim and cut gates so an
#: episode cannot pass one and fail another for choosing a synonym. ``diagram``
#: is added here because a hand-drawn diagram is a real artefact this contract
#: accepts for an evidence beat, even though it is not a screen capture.
CAPTURE_SOURCE_TYPES = frozenset(CAPTURE_SPELLINGS) | {"diagram"}

#: What the founder may have decided a reference is cleared for. The two study
#: scopes cover a third-party film; the rest record the common honest bases (a
#: film of one's own, a public-domain source, a licence, written permission).
#: None of them permit reusing the film in the cut — ``reuse_reference_media``
#: stays false — so this is a record of the *basis*, not a reuse switch.
RIGHTS_SCOPES = (
    "study_only",
    "study_and_adapt",
    "own_work",
    "public_domain",
    "licensed",
    "permission_granted",
)

#: The stored frame: a 32x32 grey thumbnail, scaled with nearest-neighbour.
#:
#: Nearest-neighbour is not an aesthetic choice. It is exactly specified, so the
#: same film and the same timestamp give the same 1024 bytes on any ffmpeg build,
#: which is what lets a stored frame be re-extracted and compared later. A
#: bilinear thumbnail would differ by a few bytes between builds and the check
#: would have to be loose enough to accept a different film.
FRAME_SIZE = 32
#: How often the shipped film is sampled when comparing it against the frames
#: cut from the reference. It is one constant because the hit report quotes a
#: timestamp derived from this rate: two numbers would eventually disagree.
FRAME_SAMPLE_FPS = 2.0
#: Seeking is not exact across ffmpeg builds, so a frame is accepted if it
#: appears within this many seconds of where it was recorded.
FRAME_SEEK_TOLERANCE_S = 0.3

REPO_ROOT = Path(__file__).resolve().parents[3]


class ReplicationError(ValueError):
    """A plan or observation that cannot honestly be produced."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return document if isinstance(document, dict) else None


def _inside(project: Path, relative: str) -> Optional[Path]:
    """Resolve a project-relative path, refusing anything that escapes it."""
    if not relative or Path(relative).is_absolute():
        return None
    target = (project / relative).resolve()
    try:
        target.relative_to(project.resolve())
    except ValueError:
        return None
    return target


def load_observation(project: Path) -> Optional[Dict[str, Any]]:
    return _load_json(Path(project) / OBSERVATION)


def load_plan(project: Path) -> Optional[Dict[str, Any]]:
    return _load_json(Path(project) / PLAN)


def load_dna(account_slug: str, root: Path = REPO_ROOT) -> Dict[str, Any]:
    path = Path(root) / "config" / "accounts" / f"{account_slug}.json"
    document = _load_json(path)
    if document is None:
        raise ReplicationError(f"no account DNA at {path}")
    return document


def declared_account(project: Path) -> str:
    """The account ``project.yaml`` declares, or "".

    The observation is a writable project file, so an observation that names a
    different account than the episode's own would let a plan be derived from
    another account's template and then graded against this one. This is the
    episode's canonical identity; the callers require it to agree with the
    observation.
    """
    path = Path(project) / "project.yaml"
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("account_slug:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return ""


# --- observation ---------------------------------------------------------

def validate_observation(project: Path, *, require_frames: bool = True) -> List[str]:
    """Everything wrong with the reference record, as plain sentences.

    An empty list means the record can be believed: the file is present, its
    bytes are the ones the observation was written against, every timing in it
    came from looking at frames, and — unless ``require_frames`` is false — each
    of those frames is stored and still hashes to what was recorded.

    ``require_frames=False`` exists for :func:`extract_frames`, which has to read
    the record *before* the frames exist. Nothing else may pass it.
    """
    project = Path(project)
    path = project / OBSERVATION
    if not path.is_file():
        return [f"no {OBSERVATION.as_posix()} in this project"]
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return [f"{OBSERVATION.as_posix()} is not valid JSON"]
    if not isinstance(document, dict):
        return [f"{OBSERVATION.as_posix()} must be a JSON object"]

    errors: List[str] = []
    if document.get("schema") != SCHEMA_OBSERVATION:
        errors.append(f"schema must be {SCHEMA_OBSERVATION!r}")

    source = document.get("source")
    if not isinstance(source, dict):
        return errors + ["source must be an object naming the reference file"]
    relative = str(source.get("path") or "")
    declared = str(source.get("sha256") or "")
    path = _inside(project, relative)
    if path is None:
        errors.append(f"source.path {relative!r} must be a path inside this project")
    elif not path.is_file():
        errors.append(f"REFERENCE_NOT_PRESENT: {relative} is not in this checkout, "
                      "so nothing here was observed")
    elif not declared:
        errors.append("source.sha256 is required: an observation is bound to bytes")
    else:
        actual = _file_sha256(path)
        if actual != declared:
            errors.append(f"REFERENCE_CHANGED: {relative} is now {actual[:12]}, the "
                          f"observation was written against {declared[:12]}")

    observation = document.get("observation") if isinstance(document.get("observation"), dict) else {}
    mode = observation.get("mode")
    if mode not in OBSERVATION_MODES:
        errors.append(f"observation.mode must be one of {OBSERVATION_MODES}")
        mode = None
    if not str(observation.get("observer") or "").strip():
        errors.append("observation.observer must name who watched the film")

    shots = document.get("shots")
    if not isinstance(shots, list) or not shots:
        return errors + ["shots must be a non-empty array"]

    duration = source.get("duration_s")
    if not isinstance(duration, (int, float)) or duration <= 0:
        errors.append("source.duration_s must be the measured length of the film")

    previous_end = 0.0
    for index, shot in enumerate(shots):
        where = f"shots[{index}]"
        if not isinstance(shot, dict):
            errors.append(f"{where} must be an object")
            continue
        function = shot.get("function")
        if function not in FUNCTIONS:
            errors.append(f"{where}.function {function!r} is not in the vocabulary")
        evidence = shot.get("evidence")
        if evidence not in OBSERVATION_MODES:
            errors.append(f"{where}.evidence must be one of {OBSERVATION_MODES}")
        start, end = shot.get("start_s"), shot.get("end_s")
        if mode == TRANSCRIPT_ONLY:
            # A transcript has no cut points. Numbers here would be invented.
            if start is not None or end is not None:
                errors.append(f"{where} carries timings on a transcript-only "
                              "observation; cut points require frames")
            continue
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            errors.append(f"{where} needs start_s and end_s from the frames")
            continue
        if end <= start:
            errors.append(f"{where} ends at {end} before it starts at {start}")
        if start < previous_end - 0.05:
            errors.append(f"{where} starts at {start} before the previous shot ends "
                          f"at {previous_end}")
        previous_end = max(previous_end, end)
        if evidence != FRAME_VIEWED:
            errors.append(f"{where}.evidence is {evidence!r} but the shot carries "
                          "timings; only a frame the observer saw has a cut point")
        elif require_frames:
            errors.extend(_frame_problems(project, where, shot, start, end))
    if mode == FRAME_VIEWED and isinstance(duration, (int, float)) and previous_end > duration + 0.5:
        errors.append(f"shots run to {previous_end}s but the film is {duration}s")
    return errors


def _frame_problems(project: Path, where: str, shot: Dict[str, Any],
                    start: Any, end: Any) -> List[str]:
    """A frame-viewed shot has to carry the frame, not just claim a mode."""
    gray = _inside(project, str(shot.get("frame_gray") or ""))
    declared = str(shot.get("frame_sha256") or "")
    if gray is None or not gray.is_file():
        return [f"FRAME_MISSING: {where} carries no extracted frame; a FRAME_VIEWED "
                "shot must carry the frame the observer looked at — run --frames"]
    png = _inside(project, str(shot.get("frame") or ""))
    problems: List[str] = []
    if png is None or not png.is_file():
        problems.append(f"FRAME_MISSING: {where} has no viewable frame next to "
                        f"{shot.get('frame_gray')!r}")
    if gray.stat().st_size != FRAME_SIZE * FRAME_SIZE:
        problems.append(f"FRAME_MISSING: {where} stores {gray.stat().st_size} bytes, "
                        f"not a {FRAME_SIZE}x{FRAME_SIZE} frame")
        return problems
    if not declared:
        problems.append(f"{where}.frame_sha256 is required: a frame is bound by its bytes")
    else:
        actual = _file_sha256(gray)
        if actual != declared:
            problems.append(f"FRAME_CHANGED: {where} was recorded as {declared[:12]} "
                            f"and is now {actual[:12]}")
    at = shot.get("frame_at_s")
    if not isinstance(at, (int, float)):
        problems.append(f"{where}.frame_at_s is required: a frame is cut at a time")
    elif (isinstance(start, (int, float)) and isinstance(end, (int, float))
          and not start - 1e-6 <= at <= end + 1e-6):
        problems.append(f"{where}.frame_at_s {at} is outside the shot ({start}–{end})")
    return problems


def _frame_gray(film: Path, at_s: float) -> bytes:
    """One 32x32 grey frame of ``film`` at ``at_s``, as raw bytes."""
    from process_utils import hidden_run

    proc = hidden_run(
        ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{max(0.0, at_s):.3f}",
         "-i", str(film), "-frames:v", "1",
         "-vf", f"scale={FRAME_SIZE}:{FRAME_SIZE}:flags=neighbor",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        timeout=180, text=False)
    if proc.returncode != 0:
        detail = (proc.stderr or b"")[:200].decode("utf-8", "replace").strip()
        raise ReplicationError(
            f"could not cut a frame from {film.name} at {at_s:.2f}s: "
            f"{detail or 'ffmpeg exited nonzero'}")
    return proc.stdout or b""


def _frame_png(film: Path, at_s: float, out: Path) -> None:
    """The same frame at human size, so a person can check what was observed."""
    from process_utils import hidden_run

    out.parent.mkdir(parents=True, exist_ok=True)
    proc = hidden_run(
        ["ffmpeg", "-y", "-v", "error", "-nostdin", "-ss", f"{max(0.0, at_s):.3f}",
         "-i", str(film), "-frames:v", "1",
         "-vf", "scale=160:-2:flags=neighbor", str(out)],
        timeout=180, text=False)
    if proc.returncode != 0 or not out.is_file() or not out.stat().st_size:
        detail = (proc.stderr or b"")[:200].decode("utf-8", "replace").strip()
        raise ReplicationError(
            f"could not write the viewable frame {out.name} at {at_s:.2f}s: "
            f"{detail or 'ffmpeg produced no image'}")


def _frame_times(start: float, end: float, duration: float) -> List[float]:
    """Where to look for a shot's frame, nearest the midpoint first.

    The midpoint of a film's last shot can land one frame past the film's final
    frame, which yields no pixels at all. Stepping back *within the same shot* is
    honest — the frame still has to come out of the film at that moment — while
    moving to a different shot would be a different observation.
    """
    mid = (start + end) / 2.0
    moments = [mid] + [mid - step for step in (0.5, 1.0, 1.5, 2.0)] + [start + 0.05]
    limit = max(0.0, duration - 0.05) if duration else end
    seen: List[float] = []
    for moment in moments:
        if moment < 0 or moment > limit:
            continue
        rounded = round(moment, 3)
        if rounded not in seen:
            seen.append(rounded)
    return seen


def cut_frame(film: Path, start: float, end: float,
              duration: float = 0.0) -> Tuple[bytes, float]:
    """The frame for a shot, and the timestamp it actually came from.

    Returns ``FRAME_SIZE`` squared grey bytes and the moment used, or ``b""`` and
    ``0.0`` when the film has no frame inside the shot at all.
    """
    for moment in _frame_times(float(start), float(end), float(duration)):
        try:
            gray = _frame_gray(film, moment)
        except ReplicationError:
            continue
        if len(gray) == FRAME_SIZE * FRAME_SIZE:
            return gray, moment
    return b"", 0.0


def extract_frames(project: Path) -> List[str]:
    """Cut one frame per observed shot out of the reference film.

    This is the step that turns a shot list into an observation: afterwards every
    FRAME_VIEWED shot carries a frame that :func:`probe_reference` can re-extract
    from the film and compare byte for byte. It rewrites
    ``reference/observation.json`` in place and keeps the observer's own fields.
    """
    project = Path(project)
    document = load_observation(project)
    if document is None:
        return [f"no readable {OBSERVATION.as_posix()} to extract frames for"]
    problems = validate_observation(project, require_frames=False)
    if problems:
        return [f"cannot extract frames: {problem}" for problem in problems]
    film = _inside(project, str((document.get("source") or {}).get("path") or ""))
    if film is None or not film.is_file():
        return ["cannot extract frames: the reference film is not in this checkout"]
    length = float((document.get("source") or {}).get("duration_s") or 0.0)

    errors: List[str] = []
    for position, shot in enumerate(document.get("shots") or []):
        if not isinstance(shot, dict) or shot.get("evidence") != FRAME_VIEWED:
            continue
        start, end = shot.get("start_s"), shot.get("end_s")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            continue
        number = shot.get("index") if isinstance(shot.get("index"), int) else position + 1
        png_rel = (FRAMES / f"{number:03d}.png").as_posix()
        gray_rel = (FRAMES / f"{number:03d}.gray").as_posix()
        gray, at = cut_frame(film, float(start), float(end), length)
        if not gray:
            errors.append(f"shots[{position}]: no frame could be cut between "
                          f"{start}s and {end}s of {film.name}")
            continue
        try:
            _frame_png(film, at, project / png_rel)
        except ReplicationError as exc:
            errors.append(str(exc))
            continue
        (project / gray_rel).write_bytes(gray)
        shot["frame"] = png_rel
        shot["frame_gray"] = gray_rel
        shot["frame_sha256"] = _sha256(gray)
        shot["frame_at_s"] = at
    if errors:
        return errors
    (project / OBSERVATION).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return []


def _rights_problems(document: Dict[str, Any]) -> List[str]:
    """A reference nobody decided the rights for is not a reference yet.

    Everything downstream assumes somebody established what this film may be
    used for. Nothing recorded it, and "复刻对标博主" is exactly the request that
    needs the answer written down before a single frame is studied.
    """
    rights = document.get("rights")
    if not isinstance(rights, dict):
        return ["RIGHTS_MISSING: the observation must record who cleared the "
                "reference and for what (rights.cleared_by / decided_at / scope)"]
    problems: List[str] = []
    if not str(rights.get("cleared_by") or "").strip():
        problems.append("RIGHTS_MISSING: rights.cleared_by must name the person "
                        "who made the decision")
    if not str(rights.get("decided_at") or "").strip():
        problems.append("RIGHTS_MISSING: rights.decided_at must date the decision")
    scope = str(rights.get("scope") or "").strip().lower()
    if scope not in RIGHTS_SCOPES:
        problems.append(f"RIGHTS_SCOPE: rights.scope must be one of {RIGHTS_SCOPES}, "
                        f"not {scope or 'nothing'}")
    return problems


def probe_reference(project: Path) -> List[str]:
    """The bytes are a *film*, it is as long as the record says, and the recorded
    frames actually come out of it.

    The hash proves the observation was written against *these* bytes; it cannot
    prove the bytes decode or that anybody looked. Both need ffprobe/ffmpeg, so
    their absence is a refusal rather than a silent pass: an unverified record
    is not a verified one. The file must also carry a video stream — an
    audio-only file whose digest matches would otherwise "prove" a shot list
    nobody could have looked at.
    """
    from contentops.media.video_qc import HAVE_FFMPEG, HAVE_FFPROBE

    if not (HAVE_FFPROBE and HAVE_FFMPEG):
        missing = [
            name for name, present in (("ffprobe", HAVE_FFPROBE), ("ffmpeg", HAVE_FFMPEG))
            if not present
        ]
        return [f"REFERENCE_UNVERIFIED: {' and '.join(missing)} unavailable, so the "
                "reference film cannot be decoded or its frames re-cut"]
    project = Path(project)
    document = load_observation(project) or {}
    rights = _rights_problems(document)
    if rights:
        return rights
    source = document.get("source") or {}
    path = _inside(project, str(source.get("path") or ""))
    if path is None or not path.is_file():
        return []
    from contentops.media.transport import ffprobe_json

    try:
        meta = ffprobe_json(path)
    except Exception as exc:  # noqa: BLE001
        return [f"REFERENCE_NOT_DECODABLE: {path.name} could not be probed ({exc})"]
    streams = meta.get("streams") or []
    if not any(s.get("codec_type") == "video" for s in streams):
        return [f"REFERENCE_NOT_A_FILM: {path.name} carries no video stream; frames "
                "cannot have been observed in it"]
    duration = float((meta.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        return [f"REFERENCE_NOT_DECODABLE: {path.name} reports no duration"]
    declared = float(source.get("duration_s") or 0)
    if declared and abs(duration - declared) > 1.0:
        return [f"REFERENCE_LENGTH_MISMATCH: the file is {duration:.2f}s but the "
                f"record claims {declared:.2f}s; the cut points are for another film"]
    return _frame_provenance(project, path, duration, document)


def _frame_provenance(project: Path, film: Path, duration: float,
                      document: Dict[str, Any]) -> List[str]:
    """Every recorded frame must come back out of the film at its own timestamp."""
    problems: List[str] = []
    offsets = (0.0, -FRAME_SEEK_TOLERANCE_S, FRAME_SEEK_TOLERANCE_S)
    for index, shot in enumerate(document.get("shots") or []):
        if not isinstance(shot, dict) or shot.get("evidence") != FRAME_VIEWED:
            continue
        at = shot.get("frame_at_s")
        gray = _inside(project, str(shot.get("frame_gray") or ""))
        if not isinstance(at, (int, float)) or gray is None or not gray.is_file():
            continue
        stored = gray.read_bytes()
        found = False
        for offset in offsets:
            moment = float(at) + offset
            if moment < 0 or moment > duration:
                continue
            try:
                if _frame_gray(film, moment) == stored:
                    found = True
                    break
            except ReplicationError:
                continue
        if not found:
            problems.append(
                f"FRAME_NOT_FROM_REFERENCE: shots[{index}] frame does not appear in "
                f"{film.name} at {float(at):.2f}s; this shot list was not cut from "
                "that film")
    return problems


def shot_grammar(document: Dict[str, Any]) -> Dict[str, Any]:
    """The only thing a reference may be copied for: its pacing.

    Returns per-function second totals plus the three numbers an original cut
    inherits — mean shot length, longest hold, and how fast the hook lands.
    """
    shots = [s for s in (document.get("shots") or []) if isinstance(s, dict)]
    timed = [s for s in shots if isinstance(s.get("start_s"), (int, float))
             and isinstance(s.get("end_s"), (int, float))]
    if not timed:
        raise ReplicationError(
            "this observation has no frame timings, so it cannot set a pacing "
            "budget; watch the film and record the cuts")
    durations = [float(s["end_s"]) - float(s["start_s"]) for s in timed]
    by_function: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for shot, seconds in zip(timed, durations):
        function = str(shot.get("function"))
        by_function[function] = by_function.get(function, 0.0) + seconds
        counts[function] = counts.get(function, 0) + 1
    return {
        "shots": len(timed),
        "total_s": round(sum(durations), 3),
        "mean_shot_s": round(sum(durations) / len(durations), 3),
        "longest_shot_s": round(max(durations), 3),
        "shortest_shot_s": round(min(durations), 3),
        "hook_s": round(durations[0], 3),
        "seconds_by_function": {k: round(v, 3) for k, v in sorted(by_function.items())},
        "shots_by_function": dict(sorted(counts.items())),
    }


# --- plan ----------------------------------------------------------------

def _target_duration(dna: Dict[str, Any], reference_s: float) -> float:
    window = (dna.get("narrative") or {}).get("target_duration_s") or [45, 60]
    low, high = float(window[0]), float(window[-1])
    return float(min(max(reference_s, low), high))


def _duty(function: str) -> str:
    if function in EVIDENCE_FUNCTIONS:
        return "evidence"
    if function in COMPARISON_FUNCTIONS:
        return "comparison"
    return "abstraction"


def derive_plan(project: Path, dna: Optional[Dict[str, Any]] = None,
                target_s: Optional[float] = None) -> Dict[str, Any]:
    """Turn a verified observation into the budget this account's episode owes.

    The reference supplies weights; the account DNA supplies the template, the
    duration window and the composition. Where the reference never shows a beat,
    that beat falls back to the mean shot length rather than disappearing — a
    missing beat is a declared omission, never a silent one.
    """
    project = Path(project)
    problems = validate_observation(project)
    if problems:
        raise ReplicationError("; ".join(problems))
    document = load_observation(project) or {}
    dna = dna if dna is not None else load_dna(str(document.get("account_slug") or ""))
    grammar = shot_grammar(document)

    template = list((dna.get("narrative") or {}).get("template") or [])
    if not template:
        raise ReplicationError("the account DNA declares no narrative template")

    unknown = [beat for beat in template if beat not in TEMPLATE_FUNCTION]
    if unknown:
        raise ReplicationError(
            f"the template beats {unknown} have no picture duty in TEMPLATE_FUNCTION; "
            "add the mapping before deriving a plan")

    weights: Dict[str, float] = {}
    for beat in template:
        function = TEMPLATE_FUNCTION[beat]
        weights[beat] = grammar["seconds_by_function"].get(function, 0.0)

    matched = [beat for beat, weight in weights.items() if weight > 0]
    if not matched:
        raise ReplicationError(
            "this reference shares no beat with the account template, so it is not "
            f"a reference for {document.get('account_slug')!r}: reference functions "
            f"{sorted(grammar['seconds_by_function'])}, template duties "
            f"{sorted({TEMPLATE_FUNCTION[b] for b in template})}")

    reference_s = float((document.get("source") or {}).get("duration_s") or grammar["total_s"])
    window = (dna.get("narrative") or {}).get("target_duration_s") or [45, 60]
    low_s, high_s = float(window[0]), float(window[-1])
    budget = float(target_s) if target_s else _target_duration(dna, reference_s)
    # An explicit override may choose *where* in the account's window the episode
    # lands; it may not leave it. Otherwise a --target-seconds 90 plan would
    # certify a film this account never publishes.
    budget = min(max(budget, low_s), high_s)
    if budget <= 0:
        raise ReplicationError("the pacing budget must be a positive number of seconds")

    mean_shot = grammar["mean_shot_s"]
    for beat, weight in list(weights.items()):
        if weight <= 0:
            weights[beat] = mean_shot

    total_weight = sum(weights.values())
    beats: List[Dict[str, Any]] = []
    for index, beat in enumerate(template, 1):
        function = TEMPLATE_FUNCTION[beat]
        share = weights[beat] / total_weight
        beats.append({
            "beat_id": f"B{index:02d}",
            "template_beat": beat,
            "function": function,
            "target_s": round(budget * share, 2),
            "weight_source": "reference" if grammar["seconds_by_function"].get(function) else "mean_shot",
            "visual_duty": _duty(function),
        })

    # Absorb the rounding drift into the longest beat so the budget is exact.
    drift = round(budget - sum(b["target_s"] for b in beats), 2)
    if drift:
        largest = max(beats, key=lambda b: b["target_s"])
        largest["target_s"] = round(largest["target_s"] + drift, 2)

    retention = dna.get("retention") or {}
    composition = (dna.get("visual") or {}).get("composition") or {}
    plan = {
        "schema": SCHEMA_PLAN,
        "account_slug": document.get("account_slug"),
        "reference": {
            "observation": OBSERVATION.as_posix(),
            "observation_sha256": _sha256(
                (project / OBSERVATION).read_bytes()),
            "video_sha256": (document.get("source") or {}).get("sha256"),
            "duration_s": reference_s,
            **grammar,
        },
        "pacing": {
            "target_s": round(budget, 2),
            "max_hook_s": retention.get("max_hook_s", 3),
            "max_static_hold_s": retention.get(
                "max_static_hold_s", round(grammar["longest_shot_s"], 2)),
            "tolerance": DURATION_TOLERANCE,
        },
        "beats": beats,
        "composition": {
            "basis": composition.get("basis", "duration_weighted"),
            "segments": composition.get("segments") or [],
            "tolerance_pct": COMPOSITION_TOLERANCE_PCT,
        },
        "reuse_reference_media": False,
    }
    return plan


def write_plan(project: Path, plan: Dict[str, Any]) -> Path:
    path = Path(project) / PLAN
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# --- verification --------------------------------------------------------

def _check(check_id: str, ok: bool, severity: str, detail: str) -> Dict[str, Any]:
    return {"id": check_id, "ok": bool(ok),
            "severity": "PASS" if ok else severity, "detail": detail}


def _shot_seconds(shot: Dict[str, Any]) -> float:
    try:
        return float(shot.get("duration") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def composition_shares(shots: List[Dict[str, Any]]) -> Dict[str, float]:
    """Duration per declared DNA role, as percentages of the declared total."""
    totals: Dict[str, float] = {}
    for shot in shots:
        role = str(shot.get("dna_role") or "unclassified")
        totals[role] = totals.get(role, 0.0) + _shot_seconds(shot)
    total = sum(totals.values())
    if not total:
        return {}
    return {role: seconds / total * 100.0 for role, seconds in totals.items()}


def stage_gate(project: Path, storyboard: Optional[Path] = None) -> List[str]:
    """Blocking replication errors for a producer, or [] when there is no plan.

    Every producer runs this immediately before it writes a film. A project that
    never claimed a reference returns [], so nothing about an ordinary episode
    changes; a project that did claim one cannot render until its cut honours
    the plan it was derived from.

    The render cannot be required here — this is the gate that runs *before* one
    exists. What a producer gets is the cheaper claim: this cut, if rendered,
    would honour the plan. :func:`check` on the finished film is the stronger one.
    """
    project = Path(project)
    if not (project / PLAN).is_file():
        return []
    result = check(project, storyboard=storyboard, require_render=False)
    return [f"{row['id']}: {row['detail']}" for row in result["checks"]
            if not row["ok"] and row["severity"] == "FAIL"]


def _storyboard(project: Path,
                storyboard: Optional[Path] = None) -> Tuple[List[Dict[str, Any]], List[str]]:
    path = Path(storyboard) if storyboard is not None else Path(project) / "script" / "storyboard.json"
    document = _load_json(path)
    if document is None:
        return [], [f"{path.name} is missing or not an object"]
    shots = document.get("shots")
    if not isinstance(shots, list) or not shots:
        return [], [f"{path.name} declares no shots"]
    return [s for s in shots if isinstance(s, dict)], []


def _measure_render(path: Path) -> Tuple[Optional[Any], str]:
    """Duration and longest frozen run, measured from the film's pixels.

    Duration alone is not enough: a 47 s film made of one still image has the
    right length and no cut. ``longest_freeze_run_s`` is what a declared shot
    table cannot fake, so the hold gate is graded on it wherever it is
    measurable.
    """
    from contentops.media.video_qc import HAVE_FFMPEG, HAVE_FFPROBE, measure_video

    if not (HAVE_FFMPEG and HAVE_FFPROBE):
        return None, "ffmpeg/ffprobe are unavailable, so the film is unmeasured"
    try:
        measured = measure_video(path)
    except Exception as exc:  # noqa: BLE001
        return None, f"{path.name} could not be analysed ({exc})"
    if measured.duration_s is None:
        return None, f"{path.name} reports no duration"
    return measured, ""


def _gray_sequence(film: Path, fps: float = FRAME_SAMPLE_FPS) -> List[bytes]:
    """The film as 32x32 grey frames, sampled so a reused shot cannot slip by."""
    from process_utils import hidden_run

    proc = hidden_run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", str(film),
         "-vf", f"fps={fps},scale={FRAME_SIZE}:{FRAME_SIZE}:flags=neighbor",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        timeout=300, text=False)
    if proc.returncode != 0:
        raise ReplicationError(
            f"could not sample {film.name}: "
            f"{(proc.stderr or b'').decode('utf-8', 'replace').strip()}")
    size = FRAME_SIZE * FRAME_SIZE
    data = proc.stdout or b""
    return [data[i:i + size] for i in range(0, len(data) - size + 1, size)]


def _is_flat(frame: bytes) -> bool:
    """A blank or near-blank frame: identical in every film, so never evidence."""
    if len(frame) < 2:
        return True
    mean = sum(frame) / len(frame)
    variance = sum((value - mean) ** 2 for value in frame) / len(frame)
    return variance < 4.0


def _reference_frames_in_cut(project: Path,
                             render_path: Path) -> Tuple[List[str], str]:
    """Reference pixels that reappear in the shipped cut, and how the look went.

    The substring test on storyboard paths only catches a shot that *points* at
    the reference; a builder that copied the frames and repointed the path
    passes it. This samples the cut and compares each frame byte-for-byte with
    every frame cut out of the reference. It detects verbatim reuse (the actual
    copy risk), not a recoloured or cropped steal — that still needs eyes.

    The status is the point, because an empty hit list means different things:
    ``compared`` (we looked and found nothing), ``none`` (no frame was ever
    captured, so the contract itself is unmet) and ``flat`` (every captured
    frame is near-uniform, so no frame could be told apart from any other
    blank). Collapsing those into "clean" would be the self-certification this
    module exists to refuse.
    """
    shots = [s for s in (load_observation(project) or {}).get("shots") or []
             if isinstance(s, dict)]
    captured = 0
    stored: List[Tuple[Any, bytes]] = []
    for shot in shots:
        path = _inside(project, str(shot.get("frame_gray") or ""))
        if path is None or not path.is_file():
            continue
        data = path.read_bytes()
        if len(data) != FRAME_SIZE * FRAME_SIZE:
            continue
        captured += 1
        if not _is_flat(data):
            stored.append((shot.get("frame_at_s"), data))
    if not stored:
        return [], "flat" if captured else "none"
    try:
        sequence = _gray_sequence(render_path)
    except ReplicationError as exc:
        return [f"REFERENCE_LEAK_UNMEASURED: {exc}"], "none"
    hits: List[str] = []
    for index, frame in enumerate(sequence):
        if _is_flat(frame):
            continue
        for at, data in stored:
            if frame == data:
                hits.append(f"the reference frame at {at}s reappears in the cut "
                            f"around {index / FRAME_SAMPLE_FPS:.1f}s")
                break
    return hits, "compared"


def _plan_matches_derivation(project: Path, plan: Dict[str, Any],
                             dna: Optional[Dict[str, Any]]) -> bool:
    """The plan on disk must still equal the plan this observation derives.

    Without this, the plan is the one artefact in the chain with no fingerprint
    on it — and it carries every threshold the check applies. Editing it (budget
    47 → 60, hook 3 → 999, composition 70/25/5 → 0/100/0) would certify itself.
    Deriving again from the verified observation and the account DNA is what
    makes such an edit visible: the DNA, not the plan, says how long a hook may
    run and what the composition must be.
    """
    try:
        if dna is None:
            slug = str((load_observation(project) or {}).get("account_slug") or "")
            dna = load_dna(slug)
        target = (plan.get("pacing") or {}).get("target_s")
        derived = derive_plan(project, dna,
                              target_s=float(target) if target else None)
    except (ReplicationError, TypeError, ValueError):
        return False
    return derived == plan


def check(project: Path, dna: Optional[Dict[str, Any]] = None,
          storyboard: Optional[Path] = None, render: Optional[Path] = None,
          require_render: bool = True) -> Dict[str, Any]:
    """Whether the cut on disk still honours the plan and the account DNA.

    Every failure here is structural: a missing plan, a reference that changed
    under a plan, a shot pointing at the reference film, a hook longer than the
    account allows, a composition the DNA never asked for.

    By default the *shipped film* is graded, not only the storyboard that was
    supposed to become it: the duration is ffprobe's measurement of
    ``final/easel.mp4``, and a plan with no film behind it fails. Summing the
    storyboard's own ``duration`` fields would let a 47 s plan certify a 2 s
    render, which is the one thing a replication check exists to prevent.

    ``require_render=False`` is the pre-render claim used by :func:`stage_gate`;
    it says the cut *would* honour the plan and says nothing about a film.
    """
    project = Path(project)
    checks: List[Dict[str, Any]] = []
    plan = load_plan(project)
    checks.append(_check("plan_present", plan is not None, "FAIL",
                         PLAN.as_posix() if plan is not None
                         else f"no {PLAN.as_posix()}: run --plan first"))

    observation_errors = validate_observation(project)
    checks.append(_check("observation_verified", not observation_errors, "FAIL",
                         "; ".join(observation_errors) or "the reference is present and unchanged"))

    shots, storyboard_errors = _storyboard(project, storyboard)
    checks.append(_check("storyboard_present", not storyboard_errors, "FAIL",
                         "; ".join(storyboard_errors) or f"{len(shots)} shots"))

    render_path = Path(render) if render is not None else project / RENDER
    if not render_path.is_absolute():
        render_path = project / render_path
    measured: Optional[float] = None
    render_qc: Optional[Any] = None
    if plan is not None and require_render:
        present = render_path.is_file() and render_path.stat().st_size > 0
        try:
            shown = render_path.relative_to(project).as_posix()
        except ValueError:
            shown = str(render_path)
        checks.append(_check(
            "render_present", present, "FAIL",
            f"{shown} was measured" if present
            else f"no {shown}: a plan that conforms is not a replication until a "
                 "film exists, and no duration here may be claimed for one"))
        if present:
            render_qc, why = _measure_render(render_path)
            measured = getattr(render_qc, "duration_s", None)
            checks.append(_check(
                "render_duration_measured", measured is not None, "FAIL",
                f"{shown} runs {measured:.2f}s" if measured is not None
                else f"{shown} could not be measured: {why}"))

    if plan is not None and dna is not None:
        want, got = dna.get("slug"), plan.get("account_slug")
        checks.append(_check("plan_account", want == got, "FAIL",
                             f"the plan was derived for {got!r}, this episode is "
                             f"{want!r}" if want != got else f"plan derived for {want!r}"))

    if plan is not None and (project / OBSERVATION).is_file():
        want = (plan.get("reference") or {}).get("observation_sha256")
        got = _sha256((project / OBSERVATION).read_bytes())
        checks.append(_check("plan_matches_observation", want == got, "FAIL",
                             "the plan was derived from a different observation; "
                             "re-run --plan" if want != got else "plan and observation agree"))

    if plan is not None:
        derived_ok = _plan_matches_derivation(project, plan, dna)
        checks.append(_check(
            "plan_matches_derivation", derived_ok, "FAIL",
            "the plan equals what the observation and the account DNA derive"
            if derived_ok else
            "the plan no longer equals its derivation: a budget, hook, hold, beat "
            "or composition threshold was edited; re-run --plan"))

    if plan is not None:
        reuse = plan.get("reuse_reference_media")
        checks.append(_check("reference_media_not_reused", reuse is False, "FAIL",
                             "plan.reuse_reference_media must be false; a reference is "
                             "a style, never a source" if reuse is not False else "nothing reused"))

    if plan is not None and shots:
        leaked = []
        for shot in shots:
            for key in ("image", "video", "source"):
                value = str(shot.get(key) or "")
                if not value:
                    continue
                if value.startswith("reference/") or "/reference/" in value.replace("\\", "/"):
                    leaked.append(f"{key}={value}")
        checks.append(_check("no_reference_asset_in_cut", not leaked, "FAIL",
                             f"shots point at the reference film: {leaked}" if leaked
                             else "no shot draws on the reference film"))

        if render_qc is not None:
            reappeared, looked = _reference_frames_in_cut(project, render_path)
            if looked == "compared":
                ok, severity = not reappeared, "FAIL"
                detail = ("; ".join(reappeared) if reappeared else
                          "no frame of the reference reappears in the shipped film")
            elif looked == "flat":
                ok, severity = False, "WARN"
                detail = ("every captured reference frame is near-uniform, so a reused "
                          "frame could not be told from any other blank one; pixel reuse "
                          "was reported, not measured")
            else:
                ok, severity = False, "FAIL"
                detail = ("no reference frame was captured, so reuse was never measured; "
                          "run --frames before claiming the cut is clean")
            checks.append(_check("reference_frames_not_in_cut", ok, severity, detail))

        claim_map = _load_json(project / "script" / "claim-map.json")
        if isinstance(claim_map, dict):
            document = load_observation(project) or {}
            reference_hashes = {
                str((document.get("source") or {}).get("sha256") or "")
            }
            reference_hashes |= {
                str(shot.get("frame_sha256"))
                for shot in (document.get("shots") or []) if isinstance(shot, dict)
            }
            reference_hashes.discard("")
            cited = []
            for claim in claim_map.get("claims") or []:
                if not isinstance(claim, dict):
                    continue
                for evidence in claim.get("evidence") or []:
                    if not isinstance(evidence, dict):
                        continue
                    if str(evidence.get("sha256") or "") in reference_hashes:
                        cited.append(f"{claim.get('claim_id')} cites the reference film "
                                     "as evidence for a claim")
            checks.append(_check(
                "claims_do_not_cite_the_reference", not cited, "FAIL",
                "; ".join(cited) if cited
                else "no claim is evidenced by the reference film's bytes"))

        pacing = plan.get("pacing") or {}
        declared_total = sum(_shot_seconds(s) for s in shots)
        if measured is not None:
            total, basis = measured, "the rendered film"
        else:
            total, basis = declared_total, f"the storyboard's {len(shots)} shots"
        target = float(pacing.get("target_s") or 0.0)
        tolerance = float(pacing.get("tolerance") or DURATION_TOLERANCE)
        within = target > 0 and abs(total - target) <= target * tolerance
        checks.append(_check("duration_within_budget", within, "FAIL",
                             f"{basis} runs {total:.2f}s against a {target:.2f}s "
                             f"budget (±{tolerance:.0%})"))

        hook_limit = float(pacing.get("max_hook_s") or 0.0)
        hook = _shot_seconds(shots[0])
        # A shot with no declared duration used to read as 0.0 and pass "0 <= 3".
        checks.append(_check("hook_within_limit", 0.0 < hook <= hook_limit, "FAIL",
                             f"first shot {hook:.2f}s (max {hook_limit:.2f}s)"))

        hold_limit = float(pacing.get("max_static_hold_s") or 0.0)
        frozen = getattr(render_qc, "longest_freeze_run_s", None)
        if render_qc is not None and frozen is None:
            # The film exists but its motion could not be read. Falling back to
            # the storyboard here would grade the declaration again.
            checks.append(_check("static_hold_within_limit", False, "FAIL",
                                 "the shipped film's frozen runs could not be measured"))
        else:
            if frozen is not None:
                longest, hold_basis = float(frozen), "the rendered film holds one image for"
            else:
                longest = max((_shot_seconds(s) for s in shots), default=0.0)
                hold_basis = "the longest declared shot runs"
            checks.append(_check("static_hold_within_limit", longest <= hold_limit, "FAIL",
                                 f"{hold_basis} {longest:.2f}s (max {hold_limit:.2f}s)"))

        order = [str(shot.get("function") or "") for shot in shots]
        known = [f for f in order if f in FUNCTIONS]
        missing = [i for i, f in enumerate(order) if f not in FUNCTIONS]
        checks.append(_check("shot_functions_declared", not missing, "FAIL",
                             f"shots {missing} declare no function from the vocabulary"
                             if missing else f"{len(order)} shots declared"))

        beat_functions = [b.get("function") for b in (plan.get("beats") or [])]
        # Several shots may serve one beat, so a repeat of the current beat is in
        # order; anything else has to be a later beat.
        position, in_order = 0, True
        for function in known:
            if position < len(beat_functions) and function == beat_functions[position]:
                continue
            try:
                position = beat_functions.index(function, position + 1)
            except ValueError:
                in_order = False
                break
        checks.append(_check("beat_order_followed", in_order, "FAIL",
                             "the cut follows the template order" if in_order
                             else f"{known} does not follow {beat_functions}"))

        shares = composition_shares(shots)
        unclassified = shares.pop("unclassified", 0.0)
        checks.append(_check("dna_roles_declared", unclassified <= 0.5, "FAIL",
                             f"{unclassified:.1f}% of the cut declares no dna_role"
                             if unclassified > 0.5 else "every shot declares a dna role"))

        # A role is a label the storyboard writes about itself. If an evidence
        # role may sit on a generated source, the account's evidence budget is
        # spent without a single real capture — the composition check would
        # still report 70% "screen recording".
        mislabeled = [
            f"shots[{index}] {shot.get('dna_role')} on "
            f"{(shot.get('source_type') or 'no source_type')!r}"
            for index, shot in enumerate(shots)
            if str(shot.get("dna_role") or "") in EVIDENCE_ROLES
            and str(shot.get("source_type") or "") not in CAPTURE_SOURCE_TYPES
        ]
        checks.append(_check("dna_role_matches_source", not mislabeled, "FAIL",
                             f"an evidence role on a non-capture source: {mislabeled}"
                             if mislabeled else "evidence roles point at declared captures"))

        segments = (plan.get("composition") or {}).get("segments") or []
        tolerance_pct = float((plan.get("composition") or {}).get("tolerance_pct")
                              or COMPOSITION_TOLERANCE_PCT)
        drifting = []
        for segment in segments:
            try:
                wanted = float(segment.get("pct"))
            except (TypeError, ValueError):
                continue
            got = shares.get(str(segment.get("role")), 0.0)
            if abs(got - wanted) > tolerance_pct:
                drifting.append(f"{segment.get('role')} {got:.0f}% vs {wanted:.0f}%")
        summary = ", ".join(f"{role} {pct:.0f}%" for role, pct in sorted(shares.items()))
        checks.append(_check("composition_matches_dna", bool(segments) and not drifting,
                             "FAIL",
                             f"{summary}; outside ±{tolerance_pct:.0f}pp: {', '.join(drifting)}"
                             if drifting else (summary or "no composition declared")))

    overall = "PASS"
    for row in checks:
        if not row["ok"] and row["severity"] == "FAIL":
            overall = "FAIL"
            break
    return {
        "schema": SCHEMA_CHECK,
        "project": project.name,
        "overall": overall,
        "checks": checks,
    }
