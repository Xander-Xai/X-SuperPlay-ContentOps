"""Build the NON-FIXTURE production evidence lock from the canonical baseline.

The first real lock. Its sources are the six screenshots the Founder approved for
tracking, and it is the artefact the Enhanced Golden experiment will be measured
against.

What it asserts, and what it deliberately does not
--------------------------------------------------
It freezes the script, the narration text, the storyboard structure, the captions and
every factual image digest. It records ``claim_refs`` as **empty**, with the reason
written into the receipt: a Claim Ledger does not exist until #6, and a lock that
asserted claims nobody had verified would be worse than one that admits it has none.

Two identity facts stay separate throughout. ``historical_identity`` is
``UNVERIFIED_ORIGINAL`` — no historical receipt records a digest for these screenshots,
so committing them proved they are portable and verifiable, not that they are the
bytes used in the original render. ``experiment_baseline`` is
``CANONICAL_RECOVERED_BASELINE``, which is what they are for going forward.

Verification before writing
---------------------------
Every entry is checked against the storyboard that cites it. A placement bound to a
file the storyboard does not reference, a kind that cannot support evidence, or a
generated asset in a factual slot all refuse. The lock is written only after those
pass, so a lock on disk has already been validated rather than merely described.

Writes ``fixture=false``. That flag is the only thing separating this from the test
locks in the suite, so it is asserted here rather than assumed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.golden.evidence_lock import (  # noqa: E402
    EvidenceAsset,
    EvidenceLock,
    assert_production_lock,
    structural_fingerprint,
)
from contentops.golden.identity import compare_evidence_identity  # noqa: E402
from contentops.media.image_contract import AssetKind, EvidenceUse  # noqa: E402
from contentops.media.media_paths import (  # noqa: E402
    serialize_media_path,
)

#: Same two identity facts the audit records, kept identical so the audit and the lock
#: cannot drift into telling different stories about the same files.
HISTORICAL_IDENTITY_UNVERIFIED = "UNVERIFIED_ORIGINAL"
EXPERIMENT_BASELINE_CANONICAL = "CANONICAL_RECOVERED_BASELINE"

BASELINE = ROOT / "projects" / "easel-review"
EXPERIMENT = ROOT / "projects" / "easel-enhanced-golden"
AUDIT_PATH = EXPERIMENT / "receipts" / "baseline-reproducibility.json"

#: Caption candidates in the historical baseline, in preference order. Only the first
#: that exists is considered, and it is verified against the locked digest before use.
CAPTION_CANDIDATES = ("assets/captions/easel.srt", "assets/captions/default.srt")

#: The canonical caption the experiment owns and tracks. Copied byte-for-byte from the
#: historical file, so it satisfies both roles at once: identical evidence bytes, and a
#: path that is actually in the repository.
CANONICAL_CAPTION = EXPERIMENT / "evidence" / "captions" / "easel.srt"

#: Where that caption came from, recorded for provenance. The source stays ignored and
#: is never rewritten -- the experiment consumes the past through its own copy.
CAPTION_SOURCE_CANDIDATE = BASELINE / "assets" / "captions" / "easel.srt"


def _is_tracked(rel: str) -> bool:
    from process_utils import hidden_run

    return hidden_run(
        ["git", "ls-files", "--error-unmatch", rel], cwd=str(ROOT), timeout=60
    ).returncode == 0


def canonical_bytes(path: Path) -> bytes:
    """The repository-canonical content of a tracked file: its Git blob.

    Why the blob and not the working tree
    -------------------------------------
    ``.gitattributes`` declares ``*.md``, ``*.txt`` and ``*.json`` as
    ``text eol=lf``, so every platform reproduces the *same* LF bytes. A Windows
    working tree can still hold CRLF — these three files were authored on Windows
    before that rule applied, and Git only applies ``.gitattributes`` on checkout, so
    the local copies were never rewritten.

    Digesting the working tree therefore produced a lock that verified on one machine
    and failed on every other: the Linux CI runner measured ``master.md`` at
    ``99767915`` against the ``7df3adbd`` this host had pinned. The repository was
    right and the lock was wrong. Pinning the blob is what makes the digest mean the
    same thing to everyone.

    Untracked files have no blob, so their bytes are read directly.
    """
    from process_utils import hidden_run

    rel = _repo_relative(path)
    if not _is_tracked(rel):
        return path.read_bytes()
    # text=False: the blob is bytes, and decoding it as UTF-8 with replacement would
    # corrupt any byte sequence that is not valid UTF-8 -- which is exactly the case
    # for a binary file such as the caption.
    for spec in (f":{rel}", f"HEAD:{rel}"):
        out = hidden_run(
            ["git", "cat-file", "blob", spec], cwd=str(ROOT), timeout=60, text=False
        )
        if out.returncode == 0 and out.stdout is not None:
            return out.stdout
    return path.read_bytes()


def eol_normalized(raw: bytes) -> bytes:
    """CRLF and bare CR collapsed to LF, for comparing against a blob."""
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def worktree_matches_canonical(path: Path) -> bool:
    """Does the working tree agree with the blob once EOLs are normalised?

    Separates line-ending noise from a real edit. Without this, a platform
    difference looks like content drift; with it, changing a word in the script still
    fails loudly, because the digests differ beyond the line endings.
    """
    try:
        return eol_normalized(path.read_bytes()) == eol_normalized(canonical_bytes(path))
    except OSError:
        return False


def _repo_relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def locked_inputs_reproducibility(lock: "EvidenceLock") -> Dict[str, Any]:
    """Is every file-backed input of the lock present in Git?

    This exists because the previous definition was wrong in a way that read as a
    pass. ``git_reproducible`` was computed from the six screenshots alone, so a lock
    pinning an untracked caption still reported ``true`` — the screenshots were in Git,
    the caption was not, and the summary said everything was reproducible. A lock whose
    script, narration, storyboard, caption or screenshots are missing from Git cannot be
    reproduced by anyone, so every one of them is counted here.

    Screenshot tracking is reported as ``n/6`` rather than a boolean, because "tracked"
    was exactly the word that hid a partial answer before.
    """
    checks: Dict[str, Any] = {}

    for label, path, expected_digest in (
        ("script", BASELINE / "script" / "master.md", lock.master_script_sha256),
        ("narration_text", BASELINE / "script" / "narration.txt", lock.narration_text_sha256),
        ("storyboard", BASELINE / "script" / "storyboard.json", None),
        ("caption", CANONICAL_CAPTION, lock.caption_sha256),
    ):
        rel = _repo_relative(path)
        present = path.is_file()
        tracked = present and _is_tracked(rel)
        digest = _canonical_sha(path) if present else None
        entry: Dict[str, Any] = {
            "path": rel,
            "exists": present,
            "tracked": tracked,
            "sha256": digest,
            "sha256_source": "git_blob",
            # A working tree that differs only by line endings is normal on Windows
            # and must not read as drift. One that differs beyond EOL is a real edit.
            "worktree_matches_canonical": worktree_matches_canonical(path) if present else None,
        }
        if expected_digest is not None:
            entry["sha256_matches_lock"] = digest == expected_digest
        else:
            # The storyboard is pinned by structural fingerprint, not raw digest, so
            # key reordering and timestamps do not cause a false failure.
            entry["sha256_matches_lock"] = (
                _structural(json.loads(canonical_bytes(path).decode("utf-8")))
                == lock.storyboard_fingerprint
            ) if present else False
        entry["ok"] = bool(
            present and tracked and entry["sha256_matches_lock"]
            and entry["worktree_matches_canonical"] is not False
        )
        checks[label] = entry

    tracked_shots = 0
    for asset in lock.evidence:
        # Resolved through the path contract, never by string surgery on the logical
        # reference -- the same reason the verifier resolves rather than rewrites.
        from contentops.media.media_paths import resolve_media_path

        local = resolve_media_path(
            asset.asset_path, repo_root=ROOT, project_root=BASELINE
        )
        if local.is_file() and _is_tracked(_repo_relative(local)):
            tracked_shots += 1
    checks["screenshots"] = {
        "path": f"projects/{BASELINE.name}/sources/screenshots/",
        "tracked": f"{tracked_shots}/{len(lock.evidence)}",
        "expected": len(lock.evidence),
        "ok": tracked_shots == len(lock.evidence) and bool(lock.evidence),
    }

    checks["all_tracked"] = all(
        entry["ok"] for key, entry in checks.items() if key != "all_tracked"
    )
    return checks

#: The Factual bindings come from the storyboard, not from a hand-written list. A
#: hand-written list would be a second source of truth that could disagree with the
#: thing it claims to describe.
SOURCE_REFS: Dict[str, str] = {
    "10-easel-doctor": "repo://projects/easel-review/script/master.md#实测证据",
    "11-easel-ping": "repo://projects/easel-review/script/master.md#实测证据",
    "12-easel-version-evidence": "repo://projects/easel-review/receipts/runtime-receipt.md",
    "13-easel-skill-layers": "repo://projects/easel-review/receipts/runtime-receipt.md",
    "14-easel-skills-dir": "repo://projects/easel-review/script/master.md#实测证据",
    "15-easel-doctor-fails": "repo://projects/easel-review/receipts/runtime-receipt.md",
}


def resolve_logical(local: Path) -> str:
    reference = serialize_media_path(local, repo_root=ROOT, project_root=BASELINE)
    if reference is None:
        raise ValueError(
            f"{local} lies outside the repository and the baseline project, so it "
            f"cannot be referenced portably."
        )
    return reference


def fail(code: str, detail: str) -> None:
    raise SystemExit(f"[{code}] {detail}")


def build() -> EvidenceLock:
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    if audit.get("source_completeness") != "COMPLETE":
        fail("BASELINE_INCOMPLETE", "the baseline audit is not COMPLETE")
    if not audit.get("git_reproducible"):
        fail("BASELINE_NOT_REPRODUCIBLE", "the baseline sources are not tracked")
    if not audit.get("sensitive_data_review", {}).get("all_public_safe"):
        fail("BASELINE_SENSITIVE", "a baseline source is not cleared as public-safe")

    storyboard = json.loads(
        (BASELINE / "script" / "storyboard.json").read_text(encoding="utf-8")
    )
    shots = storyboard.get("shots") or []

    # Placement bindings are derived from the storyboard so they cannot drift from it.
    by_file: Dict[str, int] = {}
    for index, shot in enumerate(shots):
        name = Path(shot.get("image", "")).name
        by_file[name] = index

    assets: List[EvidenceAsset] = []
    for record in audit["expected_screenshots"]:
        name = Path(record["expected_path"]).name
        index = by_file.get(name)
        if index is None:
            fail(
                "EVIDENCE_ASSET_REPLACED",
                f"{name} is in the baseline audit but the storyboard does not "
                f"reference it. The audit and the storyboard disagree.",
            )
        local = ROOT / record["expected_path"]
        if not local.is_file():
            fail("EVIDENCE_ASSET_REMOVED", f"{record['expected_path']} does not exist")

        digest = _canonical_sha(local)
        if digest != record["sha256"]:
            fail(
                "EVIDENCE_SHA_CHANGED",
                f"{record['expected_path']} has sha256 {digest[:12]} but the audit "
                f"recorded {str(record['sha256'])[:12]}",
            )

        stem = Path(name).stem
        assets.append(EvidenceAsset(
            placement_id=f"shot_{index:02d}",
            asset_path=resolve_logical(local),
            asset_sha256=digest,
            asset_kind=AssetKind.SCREENSHOT,
            evidence_use=EvidenceUse.EVIDENCE,
            claim_refs=[],
            source_ref=SOURCE_REFS.get(stem),
        ))

    if len(assets) != len(shots):
        fail(
            "EVIDENCE_ASSET_REMOVED",
            f"{len(shots)} storyboard shots but {len(assets)} locked assets",
        )

    # An evidence lock admits nothing generated and nothing evidence-incapable.
    for asset in assets:
        if asset.asset_kind in AssetKind.GENERATED:
            fail(
                "GENERATED_REPLACED_EVIDENCE",
                f"{asset.placement_id} holds {asset.asset_kind}. Generated media can "
                f"never occupy a factual placement, derived or not.",
            )
        if asset.asset_kind not in AssetKind.EVIDENCE_CAPABLE:
            fail(
                "KIND_NOT_EVIDENCE_CAPABLE",
                f"{asset.placement_id}: {asset.asset_kind} cannot support a factual claim",
            )

    caption, caption_note = resolve_caption()

    lock = EvidenceLock(
        source_project="project://easel-review",
        master_script_sha256=_canonical_sha(BASELINE / "script" / "master.md"),
        narration_text_sha256=_canonical_sha(BASELINE / "script" / "narration.txt"),
        storyboard_fingerprint=_structural(storyboard),
        caption_sha256=_sha256(caption) if caption else None,
        evidence=assets,
        # The load-bearing field: this is the real baseline, not the test fixtures.
        fixture=False,
        notes={
            "historical_identity": audit["historical_identity"],
            "experiment_baseline": audit["experiment_baseline"],
            "audit_receipt": "repo://projects/easel-enhanced-golden/receipts/baseline-reproducibility.json",
            "caption_source": resolve_logical(caption) if caption else None,
            "caption_provenance": caption_note,
            "claim_ledger_status": (
                "Claim Ledger does not exist until #6. claim_refs are intentionally "
                "empty; no claim was fabricated to populate the field."
            ),
        },
    )
    # The lock must survive its own round trip before it is written, and it must pass
    # the production assertion. A lock that cannot be reloaded is not a lock.
    reloaded = EvidenceLock.from_dict(lock.as_dict())
    assert reloaded.fingerprint() == lock.fingerprint(), "lock does not round trip"
    assert_production_lock(lock)

    # Refuse to WRITE a lock whose inputs are not all in Git. Writing it and reporting
    # `git_reproducible: false` afterwards is precisely what let the caption gap
    # through: the lock was written, the six screenshots were tracked, and the
    # summary said the baseline was reproducible while pinning an untracked file.
    reproducibility = locked_inputs_reproducibility(lock)
    if not reproducibility["all_tracked"]:
        broken = [
            key for key, entry in reproducibility.items()
            if key != "all_tracked" and not entry["ok"]
        ]
        fail(
            "EVIDENCE_INPUT_NOT_TRACKED",
            f"locked input(s) not present and tracked in Git: {broken}. The lock would "
            f"pin bytes nobody else can obtain, so it is not written.",
        )
    return lock


def resolve_caption():
    """Pick the caption the experiment tracks, and prove it is the historical bytes.

    The lock used to pin ``easel-review/assets/captions/easel.srt``, which Git
    ignores. That made the lock reference a file nobody else could obtain while the
    summary still reported reproducibility — the failure this stage exists to close.

    So the caption must resolve to the experiment's own tracked copy, and that copy
    must be byte-identical to the historical file. ``default.srt`` is a different asset
    and is never a substitute: it is 582 bytes against 1189 and its digest does not
    match, so quietly swapping it would have produced a plausible-looking lock
    describing captions nobody rendered.
    """
    if not CANONICAL_CAPTION.is_file():
        fail(
            "CAPTION_NOT_PRESENT",
            f"{_repo_relative(CANONICAL_CAPTION)} does not exist. Copy the historical "
            f"caption byte-for-byte; do not author a replacement.",
        )
    if not _is_tracked(_repo_relative(CANONICAL_CAPTION)):
        fail(
            "EVIDENCE_INPUT_NOT_TRACKED",
            f"{_repo_relative(CANONICAL_CAPTION)} is not tracked. A locked input absent "
            f"from Git cannot be reproduced by another machine.",
        )
    if not CAPTION_SOURCE_CANDIDATE.is_file():
        return CANONICAL_CAPTION, {
            "source_candidate": None,
            "note": (
                "the historical caption is absent from this host; the tracked "
                "experiment copy is authoritative for the experiment"
            ),
        }

    canonical_digest = _canonical_sha(CANONICAL_CAPTION)
    source_digest = _sha256(CAPTION_SOURCE_CANDIDATE)
    if canonical_digest != source_digest:
        fail(
            "CAPTION_BASELINE_MISMATCH",
            f"the tracked canonical caption hashes {canonical_digest[:12]} but "
            f"{_repo_relative(CAPTION_SOURCE_CANDIDATE)} hashes {source_digest[:12]}. "
            f"Refusing to proceed: substituting different caption bytes would make the "
            f"lock describe material that was never rendered. default.srt is a "
            f"different asset and is not a substitute.",
        )
    return CANONICAL_CAPTION, {
        "source_candidate": _repo_relative(CAPTION_SOURCE_CANDIDATE),
        "source_candidate_sha256": source_digest,
        "canonical_path": f"repo://{_repo_relative(CANONICAL_CAPTION)}",
        "sha256": canonical_digest,
        "byte_identical_to_source": True,
        "line_endings_preserved": "copied as bytes; no text round-trip",
        "historical_identity": HISTORICAL_IDENTITY_UNVERIFIED,
        "experiment_baseline": EXPERIMENT_BASELINE_CANONICAL,
        "sensitive_data_review": "PUBLIC_SAFE",
        "note": (
            "Captions are the on-screen narration text. No API key, token, account "
            "identifier or other sensitive value appears; the '.env also has no API "
            "Key' line states an absence and carries no value."
        ),
    }


def verify() -> EvidenceLock:
    """Reload the written lock and re-check it against the repository.

    Separate from :func:`build` on purpose. Building proves the lock could be
    constructed; verifying proves the thing on disk still describes the repository.
    That distinction matters because the failure this guards is drift: someone
    re-encodes a screenshot, or points a placement at a different file, and a lock
    that is only ever built would keep reporting a confident fingerprint for bytes
    that no longer exist.

    Refuses by code:
        ``LOCK_NOT_PRESENT``      no lock has been written
        ``LOCK_SCHEMA_UNKNOWN``   the file is not an evidence lock
        ``LOCK_FIXTURE``          a fixture lock cannot back the real baseline
        ``EVIDENCE_ASSET_REMOVED`` a locked file is gone
        ``EVIDENCE_ASSET_REPLACED`` a path is not the canonical repo-relative one
        ``EVIDENCE_SHA_CHANGED``  the bytes changed
        ``EVIDENCE_NOT_TRACKED``  the file exists but is not in Git, so the baseline
                                  is not reproducible even though it is present
        ``KIND_NOT_EVIDENCE_CAPABLE`` / ``GENERATED_REPLACED_EVIDENCE``
                                  a factual slot holds something that cannot be evidence
    """
    target = EXPERIMENT / "evidence" / "evidence-lock.json"
    if not target.is_file():
        fail("LOCK_NOT_PRESENT", f"{target} does not exist. Run this script without --verify.")
    lock = EvidenceLock.load(target)

    if lock.fixture:
        fail("LOCK_FIXTURE", "the written lock is fixture=True and cannot back the baseline")
    assert_production_lock(lock)

    storyboard = json.loads(
        (BASELINE / "script" / "storyboard.json").read_text(encoding="utf-8")
    )
    shots = storyboard.get("shots") or []
    expected_files = {Path(s.get("image", "")).name for s in shots}

    for asset in lock.evidence:
        # Recover the local file from the logical reference via the path contract,
        # never by string surgery, so resolution matches every other consumer.
        from contentops.media.media_paths import resolve_media_path

        path = resolve_media_path(
            asset.asset_path, repo_root=ROOT, project_root=BASELINE
        )
        if Path(path).name not in expected_files:
            fail(
                "EVIDENCE_ASSET_REPLACED",
                f"{asset.placement_id} points at {Path(path).name}, which the "
                f"storyboard does not reference",
            )
        if not path.is_file():
            fail("EVIDENCE_ASSET_REMOVED", f"{asset.asset_path} no longer exists")
        if resolve_logical(path) != asset.asset_path:
            fail(
                "EVIDENCE_ASSET_REPLACED",
                f"{asset.asset_path} is not the canonical repository path "
                f"(resolved to {resolve_logical(path)})",
            )
        repo_relative = f"projects/easel-review/{asset.asset_path.split('project://', 1)[1]}"
        if not _is_tracked(repo_relative):
            fail(
                "EVIDENCE_NOT_TRACKED",
                f"{repo_relative} exists but is not tracked, so the baseline is "
                f"present-but-not-reproducible",
            )
        digest = _sha256(path)
        if digest != asset.asset_sha256:
            fail(
                "EVIDENCE_SHA_CHANGED",
                f"{asset.asset_path} has sha256 {digest[:12]}; the lock recorded "
                f"{asset.asset_sha256[:12]}",
            )
        # Generated is checked BEFORE evidence-capable. Both refuse, but a generated
        # kind in a factual slot is the more specific finding, and reporting it as
        # merely "not evidence capable" would understate what went wrong.
        if asset.asset_kind in AssetKind.GENERATED:
            fail(
                "GENERATED_REPLACED_EVIDENCE",
                f"{asset.placement_id} holds {asset.asset_kind}. Generated media can "
                f"never occupy a factual placement, derived or not.",
            )
        if asset.asset_kind not in AssetKind.EVIDENCE_CAPABLE:
            fail(
                "KIND_NOT_EVIDENCE_CAPABLE",
                f"{asset.placement_id}: {asset.asset_kind} cannot support a factual claim",
            )

    if len(lock.evidence) != len(shots):
        fail(
            "EVIDENCE_ASSET_REMOVED",
            f"the lock has {len(lock.evidence)} assets for {len(shots)} storyboard shots",
        )

    # Every file-backed input, not just the screenshots. The screenshots-only check is
    # what let a lock pin an untracked caption and still pass, so the caption, script,
    # narration text and storyboard are each verified for presence, tracking and digest.
    verify_locked_inputs(lock)
    return lock


def verify_locked_inputs(lock: "EvidenceLock") -> Dict[str, Any]:
    """Presence, Git tracking and digest for every file-backed lock input."""
    checks: Dict[str, Any] = {}

    def check_input(label: str, path: Path, expected: Optional[str], mode: str) -> None:
        rel = _repo_relative(path)
        if not path.is_file():
            fail("EVIDENCE_INPUT_MISSING", f"{label}: {rel} does not exist")
        if not _is_tracked(rel):
            fail(
                "EVIDENCE_INPUT_NOT_TRACKED",
                f"{label}: {rel} exists but is not tracked, so the locked input cannot "
                f"be obtained by another machine or in CI",
            )
        raw = canonical_bytes(path)
        digest = hashlib.sha256(raw).hexdigest()
        if mode == "structural":
            actual = _structural(json.loads(raw.decode("utf-8")))
        else:
            actual = digest
        if actual != expected:
            code = (
                "EVIDENCE_STORYBOARD_CHANGED" if mode == "structural"
                else "EVIDENCE_SHA_CHANGED"
            )
            fail(
                code,
                f"{label}: {rel} hashes {actual[:12]}; the lock pinned "
                f"{str(expected)[:12]}",
            )
        if not worktree_matches_canonical(path):
            # The blob matches, so the *committed* baseline is intact — but the local
            # file has been edited past its line endings. Reported rather than
            # ignored, because the next commit would change the evidence underneath a
            # lock that currently verifies.
            fail(
                "EVIDENCE_WORKTREE_DIVERGED",
                f"{label}: {rel} matches its blob but the working copy has been "
                f"edited beyond line endings. The lock pins the committed baseline; "
                f"commit or revert the change before trusting a rebuild from this tree.",
            )
        checks[label] = {
            "path": rel, "exists": True, "tracked": True,
            "sha256": digest, "matches_lock": True,
            "sha256_source": "git_blob",
            "worktree_matches_canonical": True,
        }

    check_input("script", BASELINE / "script" / "master.md",
                lock.master_script_sha256, "digest")
    check_input("narration_text", BASELINE / "script" / "narration.txt",
                lock.narration_text_sha256, "digest")
    check_input("storyboard", BASELINE / "script" / "storyboard.json",
                lock.storyboard_fingerprint, "structural")

    if lock.caption_sha256 is None:
        fail(
            "EVIDENCE_INPUT_MISSING",
            "the lock pins no caption. A lock without a caption leaves the "
            "subtitle state of every build unverifiable.",
        )
    # The caption must be the tracked experiment copy, not the ignored historical one.
    # `default.srt` is a different asset and must never be accepted here.
    if CANONICAL_CAPTION.is_file():
        check_input("caption", CANONICAL_CAPTION, lock.caption_sha256, "digest")
        # The digest alone cannot prove *which* file was meant: the historical caption
        # and the tracked copy are byte-identical, so a lock pinned to the ignored
        # original verified clean. The declared provenance is what distinguishes them,
        # so it is checked rather than trusted.
        declared = (lock.notes or {}).get("caption_provenance", {}) or {}
        declared_path = declared.get("canonical_path")
        expected_path = f"repo://{_repo_relative(CANONICAL_CAPTION)}"
        if declared_path is not None and declared_path != expected_path:
            fail(
                "CAPTION_PROVENANCE_MISMATCH",
                f"the lock declares its canonical caption as {declared_path!r}, but the "
                f"only tracked copy is {expected_path!r}. The historical caption is "
                f"ignored by Git, so a lock pointing at it pins bytes another machine "
                f"cannot obtain.",
            )
    else:
        historical = BASELINE / "assets" / "captions" / "easel.srt"
        if historical.is_file() and _sha256(historical) == lock.caption_sha256:
            fail(
                "EVIDENCE_INPUT_NOT_TRACKED",
                "the locked caption resolves only to the ignored historical file "
                f"{_repo_relative(historical)}. Copy the exact bytes into "
                f"{_repo_relative(CANONICAL_CAPTION)} and track that instead.",
            )
        fail(
            "CAPTION_BASELINE_MISMATCH",
            f"neither {_repo_relative(CANONICAL_CAPTION)} nor the historical caption "
            f"reproduces the locked caption digest {lock.caption_sha256[:12]}",
        )
    return checks


def _is_tracked(rel: str) -> bool:
    from process_utils import hidden_run

    return hidden_run(
        ["git", "ls-files", "--error-unmatch", rel], cwd=str(ROOT), timeout=60
    ).returncode == 0


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(path: Path) -> str:
    """sha256 of the repository-canonical bytes. See :func:`canonical_bytes`.

    Reading the working tree here is what made the lock machine-specific: the Windows
    copies of these files still carry CRLF, and only this host has them that way.
    """
    import hashlib

    return hashlib.sha256(canonical_bytes(path)).hexdigest()
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _structural(value: Any) -> str:
    from contentops.golden.evidence_lock import structural_fingerprint

    return structural_fingerprint(value)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if "--verify" in sys.argv:
        lock = verify()
        print(f"verified    : repo://projects/easel-enhanced-golden/evidence/evidence-lock.json")
        print(f"fixture     : {lock.fixture}")
        print(f"assets      : {len(lock.evidence)}")
        print(f"fingerprint : {lock.fingerprint()}")
        print()
        print("Every locked file exists, is tracked, is the canonical path, and its bytes")
        print("still hash to the locked digest. No provider call, no quota, no render.")
        return 0

    lock = build()
    target = EXPERIMENT / "evidence" / "evidence-lock.json"
    lock.write(target)

    body = lock.as_dict()
    print(f"lock        : repo://projects/easel-enhanced-golden/evidence/evidence-lock.json")
    print(f"fixture     : {body['fixture']}")
    print(f"source      : {body['source_project']}")
    print(f"assets      : {len(body['evidence'])}")
    print(f"fingerprint : {body['fingerprint']}")
    print(f"asset digest: {body['asset_digest']}")
    print()
    print(f"{'placement':10s} {'sha256':18s} {'kind':14s} {'use':10s} claims")
    for asset in body["evidence"]:
        print(
            f"{asset['placement_id']:10s} {asset['asset_sha256'][:16]:18s} "
            f"{asset['asset_kind']:14s} {asset['evidence_use']:10s} "
            f"{asset['claim_refs'] or '[] (no Claim Ledger until #6)'}"
        )
    print()

    # Cross-check with the same function the four-arm comparison uses, so the lock
    # is verified by the mechanism that will later verify the experiment.
    identity = compare_evidence_identity({"baseline": body["evidence"], "baseline_copy": body["evidence"]})
    print(f"self identity check : {identity['verdict']} "
          f"({identity['placements_compared']} placements)")
    if identity["verdict"] != "EXPERIMENT_VALID":
        fail("LOCK_SELF_CHECK_FAILED", json.dumps(identity["mismatches"], indent=2))
    print()
    print("No provider call. No quota. No render. The lock is validated and written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())