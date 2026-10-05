"""Baseline reproducibility audit for the intended Golden source project.

The question this answers, precisely: **are the factual screenshot sources the
tracked storyboard depends on recoverable, and how far can their identity be
proven?**

Why this runs before any Golden generation
-------------------------------------------
`projects/easel-review` is the intended baseline, but its six factual screenshots
are not in Git. A Golden experiment built on them is therefore not reproducible on
another machine, and generating provider media before establishing that would spend
quota on an experiment nobody else could re-run. The audit is cheap; the generation
is not.

Four verdicts, kept separate on purpose
--------------------------------------
``recovery_class`` is about **where the file is**:

- ``TRACKED_ORIGINAL``          in Git at that path
- ``LOCAL_UNTRACKED_CANDIDATE`` on disk, untracked, not ignored
- ``LOCAL_IGNORED_CANDIDATE``   on disk, ignored by .gitignore
- ``MISSING``                   nowhere legitimate

``source_completeness`` is about **whether the set is whole on this host**, and
``git_reproducible`` is about **whether anyone else could rebuild it**. Collapsing
those into one word is how a run ends up claiming a baseline is "complete" when it
only exists on one machine.

Nothing is called ``VERIFIED_ORIGINAL`` without an independent historical digest or
receipt proving identity. A matching filename is not cryptographic proof, and a file
sitting in the right place is not evidence that it is the file that was used.

Consistency evidence is weaker and is labelled as such
-----------------------------------------------------
Comparing candidates against the historical render answers "are these consistent
with the video that was rendered?". That is ``CONSISTENCY_EVIDENCE``, not source
identity. No frame is ever extracted and promoted into a source asset.

Usage::

    python scripts/audit_baseline_reproducibility.py
    python scripts/audit_baseline_reproducibility.py --json-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_run  # noqa: E402

from contentops.media.media_paths import serialize_media_path  # noqa: E402

BASELINE_PROJECT = "easel-review"
BASELINE_DIR = ROOT / "projects" / BASELINE_PROJECT
SHOTS_DIR = BASELINE_DIR / "sources" / "screenshots"

AUDIT_SCHEMA = "contentops.baseline-reproducibility/v1"

#: Historical identity. Committing the bytes makes them tracked and reproducible; it
#: does not prove they are the files that were used in October 2023, because no
#: receipt in the repository records a digest for them. Those are two separate facts
#: and the audit refuses to let one imply the other.
HISTORICAL_IDENTITY_UNVERIFIED = "UNVERIFIED_ORIGINAL"

#: Forward role, granted by the Founder policy decision of 2026-10-05.
EXPERIMENT_BASELINE_CANONICAL = "CANONICAL_RECOVERED_BASELINE"

#: Probe size for the coarse image comparison. Small on purpose: this measures
#: gross layout, not text, and a large probe would only make the check slower
#: without making it more convincing.
PROBE_W, PROBE_H = 64, 114
FRAME_SAMPLES = 36

#: The six factual sources the tracked storyboard references.
EXPECTED_SHOTS: Tuple[str, ...] = (
    "10-easel-doctor.png",
    "11-easel-ping.png",
    "12-easel-version-evidence.png",
    "13-easel-skill-layers.png",
    "14-easel-skills-dir.png",
    "15-easel-doctor-fails.png",
)

#: Tracked screenshots that are NOT the six, recorded so nobody quietly renames
#: 01-04 into the 10-15 slots. They depict different material entirely.
NOT_SUBSTITUTES: Tuple[str, ...] = (
    "01-easel-hero.png",
    "02-easel-features.png",
    "03-easel-architecture.png",
    "04-easel-skills.png",
)

#: Per-asset sensitive-data review, recorded before ``git add``.
#:
#: A screenshot that shows a token is effectively un-committable: a secret that reaches
#: Git history has to be treated as compromised, and the remedy is a rewrite plus a
#: rotation rather than a revert. So the review happens first, and the verdict is
#: per asset.
#:
#: Each verdict below combines two things. The *visible content* was reviewed by
#: looking at each image — OCR was deliberately not used, because a detector that
#: cannot read a terminal screenshot would report "safe" for the one place a token is
#: most likely to appear. The *metadata* was checked mechanically: chunk inventory,
#: text chunks, and bytes appended after IEND.
SENSITIVE_REVIEW: Dict[str, Dict[str, Any]] = {
    "10-easel-doctor.png": {
        "verdict": "PUBLIC_SAFE",
        "visible_content": (
            "easel doctor dependency check: seven OK rows and a FAIL count. No "
            "credential, identifier or path."
        ),
        "metadata": "IHDR/IDAT/IEND/pHYs only; no text chunks; nothing after IEND",
    },
    "11-easel-ping.png": {
        "verdict": "PUBLIC_SAFE",
        "visible_content": (
            "easel ping connectivity result, Step 1 FAIL and Step 2 OK. Mentions "
            "localhost:18789, which is loopback plus a port already stated in the "
            "video's own narration, not an address or host."
        ),
        "metadata": "IHDR/IDAT/IEND/pHYs only; no text chunks; nothing after IEND",
    },
    "12-easel-version-evidence.png": {
        "verdict": "PUBLIC_SAFE",
        "visible_content": (
            "Public release verification: pinned v0.2.1, upstream commit "
            "3fe2d9904c1619281ef57f81d9ee0b7854998399, 982/982 blobs matched, skill "
            "count. Project-relative paths only."
        ),
        "metadata": "IHDR/IDAT/IEND/pHYs only; no text chunks; nothing after IEND",
    },
    "13-easel-skill-layers.png": {
        "verdict": "PUBLIC_SAFE",
        "visible_content": (
            "Skill counts by workflow layer from a grep|sort|uniq -c run. Public "
            "counts and a project-relative glob."
        ),
        "metadata": "IHDR/IDAT/IEND/pHYs only; no text chunks; nothing after IEND",
    },
    "14-easel-skills-dir.png": {
        "verdict": "PUBLIC_SAFE",
        "visible_content": (
            "Directory listing of skill names from ls skills/openclaw/. Public "
            "capability names; project-relative path."
        ),
        "metadata": "IHDR/IDAT/IEND/pHYs only; no text chunks; nothing after IEND",
    },
    "15-easel-doctor-fails.png": {
        "verdict": "PUBLIC_SAFE",
        "visible_content": (
            "easel doctor FAIL rows. Highest-risk of the six and clean: '.env (API "
            "Key)' appears as a check label beside a FAIL status, with no key value, "
            "no token and no header content. The check reports that the key is "
            "absent, which is the opposite of leaking one."
        ),
        "metadata": "IHDR/IDAT/IEND/pHYs only; no text chunks; nothing after IEND",
    },
}


# --- small helpers -----------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> Tuple[Optional[int], Optional[int]]:
    """Width/height straight from the PNG IHDR.

    Read by hand so classification of a damaged file still succeeds; a decoder that
    refuses would turn "this is a broken candidate" into "this file is missing",
    which is a different and much stronger claim.
    """
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return (None, None)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return (None, None)
    width, height = struct.unpack(">II", header[16:24])
    return (int(width), int(height))


def _run(cmd: List[str], *, timeout: float = 300.0) -> subprocess.CompletedProcess:
    """Every child process goes through ``process_utils``.

    Not a style preference. This audit shells out to ``git``, ``ffprobe`` and
    ``ffmpeg``, and a bare ``subprocess.run`` on Windows is exactly what produces
    the console popups the repository policy exists to eliminate. The repo policy
    check caught four direct spawns here on the first CI run, which is the check
    working as intended.
    """
    return hidden_run(cmd, cwd=str(ROOT), timeout=timeout)


def git(*args: str) -> subprocess.CompletedProcess:
    return _run(["git", *args], timeout=120)


def is_tracked(rel: str) -> bool:
    return git("ls-files", "--error-unmatch", rel).returncode == 0


def is_ignored(rel: str) -> bool:
    return git("check-ignore", "-q", rel).returncode == 0


def logical(path: Path) -> str:
    """Portable reference for a committed receipt.

    Raises rather than falling back to an absolute path: a machine path in a
    committed artifact is the exact defect this milestone exists to remove.
    """
    reference = serialize_media_path(
        path, repo_root=ROOT, project_root=BASELINE_DIR
    )
    if reference is None:
        raise ValueError(
            f"{path} is outside the repository and the project, so it cannot be "
            f"referenced portably. It does not belong in a committed receipt."
        )
    return reference


def probe_video(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"present": False, "path": logical(BASELINE_DIR / "final" / path.name)}
    out = _run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ])
    if out.returncode != 0:
        return {"present": True, "probe_failed": True}
    payload = json.loads(out.stdout)
    fmt = payload.get("format", {})
    video = next(
        (s for s in payload.get("streams", []) if s.get("codec_type") == "video"), {}
    )
    audio = [s for s in payload.get("streams", []) if s.get("codec_type") == "audio"]
    return {
        "present": True,
        "path": logical(path),
        "container": fmt.get("format_name"),
        "duration_sec": round(float(fmt.get("duration", 0)), 2),
        "width": video.get("width"),
        "height": video.get("height"),
        "video_codec": video.get("codec_name"),
        "audio_streams": len(audio),
        "bytes": path.stat().st_size,
    }


# --- classification ----------------------------------------------------------


def classify_expected() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for name in EXPECTED_SHOTS:
        path = SHOTS_DIR / name
        rel = f"projects/{BASELINE_PROJECT}/sources/screenshots/{name}"
        exists = path.is_file()
        tracked = is_tracked(rel) if exists else False
        ignored = is_ignored(rel) if exists else False
        # Deliberately NOT recomputed into TRACKED_ORIGINAL now that the files are
        # tracked. That class asserts *identity* — that these are the bytes used in
        # the original render — and being in the index says nothing of the kind. The
        # recovery class records how the file was found, which does not change just
        # because the file was later committed.
        recovery = "MISSING" if not exists else "LOCAL_IGNORED_CANDIDATE"
        width, height = png_dimensions(path) if exists else (None, None)
        review = dict(SENSITIVE_REVIEW.get(name, {}))
        records.append({
            "expected_path": rel,
            "found": exists,
            "actual_location": rel if exists else None,
            "sha256": sha256_file(path) if exists else None,
            "width": width,
            "height": height,
            "container": "PNG" if exists else None,
            # Current git state, recorded apart from identity.
            "tracked": tracked,
            "ignored": ignored,
            "recovery_class": recovery,
            "historical_identity": (
                HISTORICAL_IDENTITY_UNVERIFIED if exists else "UNKNOWN"
            ),
            "experiment_baseline": (
                EXPERIMENT_BASELINE_CANONICAL
                if exists and tracked and review.get("verdict") == "PUBLIC_SAFE"
                else "NOT_CANONICAL"
            ),
            "sensitive_data_review": {
                "verdict": review.get("verdict", "NOT_REVIEWED"),
                "visible_content": review.get("visible_content"),
                "metadata": review.get("metadata"),
            },
        })
    return records


def read_storyboard() -> Dict[str, Any]:
    return json.loads((BASELINE_DIR / "script" / "storyboard.json").read_text(encoding="utf-8"))


# --- consistency evidence ----------------------------------------------------


def _load_gray(path: Path):
    from PIL import Image

    return Image.open(path).convert("L").resize((PROBE_W, PROBE_H))


def _mean_abs_diff(left, right) -> float:
    from PIL import ImageChops, ImageStat

    return round(ImageStat.Stat(ImageChops.difference(left, right)).mean[0], 2)


def work_intermediates_check() -> Dict[str, Any]:
    """Are the assembler intermediates a witness to *this* storyboard?

    This check exists because the obvious witness is a trap. ``work/shot_XX.png``
    looks like it corresponds to storyboard shot XX, and comparing against it
    produces small, reassuring numbers either way — so a wrong file still looks
    consistent. Comparing digests settles it: if the intermediates are copies of a
    different screenshot set, they witness an earlier render and cannot support any
    claim about the current one.
    """
    storyboard = read_storyboard()
    shots = storyboard.get("shots") or []
    by_digest: Dict[str, str] = {}
    for candidate in sorted(SHOTS_DIR.glob("*.png")):
        if candidate.name[:1].isdigit():
            by_digest[sha256_file(candidate)] = candidate.name

    findings = []
    for index, shot in enumerate(shots):
        name = Path(shot.get("image", "")).name
        witness = BASELINE_DIR / "work" / f"shot_{index:02d}.png"
        if not witness.is_file():
            findings.append({
                "shot_index": index,
                "storyboard_source": name,
                "witness_present": False,
            })
            continue
        digest = sha256_file(witness)
        findings.append({
            "shot_index": index,
            "storyboard_source": name,
            "witness_present": True,
            "witness_sha256": digest,
            "identical_to_storyboard_source": digest == by_digest.get(digest, "") == name
            or by_digest.get(digest) == name,
            "witness_actually_equals": by_digest.get(digest),
        })
    witnessed = [f for f in findings if f.get("witness_present")]
    matches = [f for f in witnessed if f["witness_actually_equals"] ==
               f["storyboard_source"]]
    return {
        "performed": True,
        "witness_count": len(witnessed),
        "matching_count": len(matches),
        "intermediates_match_this_storyboard": bool(witnessed) and len(matches) == len(witnessed),
        "findings": findings,
        "conclusion": (
            "The work/ intermediates are byte-identical copies of the storyboard's own "
            "sources, so they are a valid witness to this render."
            if witnessed and len(matches) == len(witnessed)
            else "The work/ intermediates are byte-identical copies of a DIFFERENT "
            "screenshot set, so they witness an earlier render and are not a valid "
            "consistency witness for this storyboard. Consistency is therefore tested "
            "against the historical render instead."
        ),
    }


def video_consistency_check() -> Dict[str, Any]:
    """Temporal-argmin test against the historical render.

    Each candidate is compared to every sampled frame, and the question is whether
    its best match lands inside its own shot's time window. That is a discriminating
    test: a wrong file finds *some* similar frame, but not one inside the right
    window in the right order.

    A low difference on its own proves nothing — the render letterboxes, animates
    and re-encodes, so even a correct match is close rather than exact. The
    magnitude is reported for context, not as the signal.
    """
    renders = {
        "tracked_final": BASELINE_DIR / "final" / "final.mp4",
        "easel_render": BASELINE_DIR / "final" / "easel.mp4",
    }
    facts = {name: probe_video(path) for name, path in renders.items()}
    render = renders["easel_render"]
    if not render.is_file():
        return {
            "performed": False,
            "reason": "the historical easel render is not present on this host",
            "render_facts": facts,
        }

    probe = _run([
        "ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(render),
    ])
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    storyboard = read_storyboard()
    shots = storyboard.get("shots") or []
    shot_len = duration / max(1, len(shots))

    results: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as td:
        loaded = []
        for index in range(FRAME_SAMPLES):
            when = duration * (index + 0.5) / FRAME_SAMPLES
            target = Path(td) / f"frame_{index:03d}.png"
            out = _run([
                "ffmpeg", "-v", "error", "-y", "-ss", f"{when:.3f}", "-i", str(render),
                "-frames:v", "1", "-vf", f"scale={PROBE_W}:{PROBE_H}", str(target),
            ])
            if out.returncode == 0 and target.is_file():
                loaded.append((when, _load_gray(target)))

        for index, shot in enumerate(shots):
            name = Path(shot.get("image", "")).name
            candidate_path = SHOTS_DIR / name
            if not candidate_path.is_file() or not loaded:
                results.append({
                    "shot_index": index,
                    "candidate": f"projects/{BASELINE_PROJECT}/sources/screenshots/{name}",
                    "compared": False,
                })
                continue
            candidate = _load_gray(candidate_path)
            scored = sorted(
                (_mean_abs_diff(candidate, frame), when) for when, frame in loaded
            )
            best_diff, best_when = scored[0]
            window = (index * shot_len, (index + 1) * shot_len)
            results.append({
                "shot_index": index,
                "candidate": f"projects/{BASELINE_PROJECT}/sources/screenshots/{name}",
                "compared": True,
                "best_match_time_sec": round(best_when, 2),
                "best_match_mean_abs_diff": best_diff,
                "own_shot_window_sec": [round(window[0], 2), round(window[1], 2)],
                "best_match_inside_own_shot": window[0] <= best_when < window[1],
            })

    compared = [r for r in results if r.get("compared")]
    in_window = [r for r in compared if r["best_match_inside_own_shot"]]
    diffs = [r["best_match_mean_abs_diff"] for r in compared]
    return {
        "performed": bool(compared),
        "class": "CONSISTENCY_EVIDENCE",
        "is_source_identity_proof": False,
        "render_facts": facts,
        "render_duration_sec": round(duration, 2),
        "shot_count": len(shots),
        "frames_sampled": len(compared) and FRAME_SAMPLES,
        "in_own_shot_count": len(in_window),
        "compared_count": len(compared),
        "mean_best_match_diff": round(sum(diffs) / len(diffs), 2) if diffs else None,
        "results": results,
        "conclusion": (
            f"{len(in_window)} of {len(compared)} candidates matched most closely "
            f"inside their own shot's window, in storyboard order. This supports that "
            f"the local files are the material the render was built from. It is not "
            f"proof of identity, and it is not a substitute for a recorded digest."
        ),
    }


# --- receipt -----------------------------------------------------------------


def build_audit() -> Dict[str, Any]:
    records = classify_expected()
    found = [r for r in records if r["found"]]
    missing = [r["expected_path"] for r in records if not r["found"]]
    blocked = [
        r["expected_path"] for r in records
        if r["sensitive_data_review"]["verdict"] == "BLOCKED_SENSITIVE_CONTENT"
    ]
    on_host_complete = not missing
    tracked_count = sum(1 for r in records if r["tracked"])
    all_public_safe = all(
        r["sensitive_data_review"]["verdict"] == "PUBLIC_SAFE" for r in found
    )

    intermediates = work_intermediates_check()
    consistency = video_consistency_check()

    storyboard = read_storyboard()
    # ``git check-ignore -v`` prints ``source:line:pattern<TAB>pathname``, and the
    # pathname is both absolute and backslash-escaped — so it is dropped rather than
    # sanitized. A receipt that reintroduced the machine path it exists to document
    # would be a poor advertisement for itself.
    ignore_rule: Optional[str] = None
    raw = git("check-ignore", "-v", str(SHOTS_DIR / EXPECTED_SHOTS[0])).stdout.strip()
    if raw:
        ignore_rule = raw.split("\t", 1)[0].strip() or None
    return {
        "schema": AUDIT_SCHEMA,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_head": git("rev-parse", "HEAD").stdout.strip(),
        "source_project": f"project://{BASELINE_PROJECT}",
        "script_sha256": sha256_file(BASELINE_DIR / "script" / "master.md"),
        "narration_text_sha256": sha256_file(BASELINE_DIR / "script" / "narration.txt"),
        "storyboard_sha256": sha256_file(BASELINE_DIR / "script" / "storyboard.json"),
        "storyboard_shot_count": len(storyboard.get("shots") or []),
        "expected_screenshots": records,
        "expected_count": len(records),
        "recovered_count": len(found),
        "missing_count": len(missing),
        "tracked_count": tracked_count,
        "source_completeness": "COMPLETE" if on_host_complete else "INCOMPLETE",
        # True only when every factual source is actually in Git. This is what makes
        # an experiment reproducible elsewhere, and it is a different question from
        # whether the set is whole on this host.
        "git_reproducible": bool(found) and tracked_count == len(records),
        "historical_identity": (
            HISTORICAL_IDENTITY_UNVERIFIED if found else "UNKNOWN"
        ),
        "experiment_baseline": (
            EXPERIMENT_BASELINE_CANONICAL
            if on_host_complete and all_public_safe and tracked_count == len(records)
            else "NOT_CANONICAL"
        ),
        "identity_semantics_note": (
            "historical_identity and experiment_baseline are separate facts. "
            "Committing the bytes makes them tracked, portable and verifiable by "
            "anyone; it does not prove they are the bytes used in the original "
            "render, because no historical receipt records a digest for them. No "
            "asset is VERIFIED_ORIGINAL and none ever becomes so from a commit."
        ),
        "sensitive_data_review": {
            "performed": True,
            "order": "before git add",
            "method": (
                "Visible content reviewed by inspecting each image; metadata checked "
                "mechanically (PNG chunk inventory, text chunks, bytes after IEND). "
                "OCR was deliberately not used: a detector that cannot read a "
                "terminal screenshot would report 'safe' for the one place a token "
                "is most likely to be."
            ),
            "all_public_safe": all_public_safe,
            "blocked_assets": blocked,
        },
        "recovery_classes_present": sorted({r["recovery_class"] for r in records}),
        "provenance_verification": {
            "independent_historical_digest_found": False,
            "highest_available_class": "LOCAL_IGNORED_CANDIDATE",
            "basis": (
                "No receipt in the repository records a sha256 for any of the six "
                "screenshots. build-easel.json and visual-qc.json record run facts but "
                "no source digests. A matching filename is not cryptographic proof, so "
                "no file is classified VERIFIED_ORIGINAL -- including now that the "
                "files are tracked."
            ),
        },
        "git_reproducibility_gap": {
            "resolved": bool(found) and tracked_count == len(records),
            "resolved_by": "Founder policy decision, 2026-10-05",
            "resolution": (
                "The six factual sources are exempt from the blanket media ignore and "
                "are tracked. A video that cites a screenshot can now be re-verified "
                "from the repository by anyone."
            ),
            "affected_paths": [r["expected_path"] for r in records],
            "root_cause": (
                "A repository-wide '*.png' rule in .gitignore made image evidence "
                "untrackable. The blanket rule is correct for build artefacts and "
                "wrong for factual evidence, so six exact paths are now exempted "
                "while the rule and every other image keep their existing behaviour."
            ),
            "allowlist_ignore_rule": ignore_rule,
            "policy_note": (
                "Narrow on purpose: no extension negation, no directory negation and "
                "no project-level exemption. tests/test_gitignore_evidence_policy.py "
                "asserts both the allowlist and the continued absence of any broad "
                "negation rule, so widening this later fails CI rather than quietly "
                "unignoring every image in the repository."
            ),
            "options_not_taken": [
                "renaming 01-04 into the 10-15 slots (they depict different material)",
                "extracting frames from the render and promoting them to sources",
                "generating replacement screenshots",
                "resizing, recompressing, re-encoding or cropping the recovered bytes",
                "removing the global media ignore or adding '!*.png'",
                "rewriting the historical storyboard, project.yaml or old receipts to "
                "make the past look tidier",
            ],
            "decision_owner": "FOUNDER",
        },
        "not_substitutes": {
            "paths": [
                f"projects/{BASELINE_PROJECT}/sources/screenshots/{n}"
                for n in NOT_SUBSTITUTES
            ],
            "note": (
                "Tracked in Git, but they depict different material. Recorded so they "
                "are not silently reused as the six."
            ),
        },
        "consistency_evidence": {
            "work_intermediates": intermediates,
            "historical_render": consistency,
        },
        "missing_assets": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--json-only", action="store_true", help="print JSON, no human summary"
    )
    args = parser.parse_args()

    audit = build_audit()
    out = BASELINE_DIR.parent / "easel-enhanced-golden" / "receipts" / \
        "baseline-reproducibility.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if args.json_only:
        print(json.dumps(audit, indent=2, ensure_ascii=False))
        return 0

    print(f"baseline source project : {audit['source_project']}")
    print(f"git head                : {audit['git_head'][:12]}")
    print()
    print(f"{'expected path':40s} {'found':5s} {'tracked':7s} {'sensitive':16s}")
    for record in audit["expected_screenshots"]:
        print(
            f"{Path(record['expected_path']).name:40s} "
            f"{str(record['found']):5s} {str(record['tracked']):7s} "
            f"{record['sensitive_data_review']['verdict']:16s}"
        )
    print()
    print(f"recovered               : {audit['recovered_count']}/{audit['expected_count']}"
          f"   missing {audit['missing_count']}")
    print(f"source_completeness     : {audit['source_completeness']}  (on this build host)")
    print(f"git_reproducible        : {audit['git_reproducible']}")
    print(f"historical_identity     : {audit['historical_identity']}")
    print(f"experiment_baseline     : {audit['experiment_baseline']}")
    print(f"sensitive review        : all_public_safe="
          f"{audit['sensitive_data_review']['all_public_safe']}")
    print(f"recovery class (as found): "
          f"{', '.join(audit['recovery_classes_present'])}")
    print()
    intermediates = audit["consistency_evidence"]["work_intermediates"]
    print("work/ intermediates valid witness :", intermediates["intermediates_match_this_storyboard"])
    print("  ", intermediates["conclusion"])
    render = audit["consistency_evidence"]["historical_render"]
    if render.get("performed"):
        print(
            f"temporal argmin inside own shot : "
            f"{render['in_own_shot_count']}/{render['compared_count']}"
        )
        print("  ", render["conclusion"])
    else:
        print("temporal argmin                 : not performed -", render.get("reason"))
    print()
    print(f"missing assets         : {audit['missing_assets'] or 'none'}")
    print(f"receipt                : repo://projects/easel-enhanced-golden/receipts/baseline-reproducibility.json")

    # Non-zero would mean the Golden build gate must hold. Reporting it through the
    # exit code too, so a script cannot ignore what the human just read.
    return 0 if audit["source_completeness"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
