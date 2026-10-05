"""The regression for the bug this stage was opened to fix.

``git_reproducible`` was computed from the six screenshots alone. A production lock
pinned ``easel-review/assets/captions/easel.srt``, which Git ignores — and the summary
still reported the baseline as reproducible, because the screenshots were in Git and
nothing asked about anything else. A lock that pins bytes another machine cannot obtain
is not a lock, and it read as a pass.

So the tests below check the *whole* input set, not just the part that happened to be
tracked when the bug was written:

- every locked input missing from Git must refuse with a named code;
- the specific case that slipped through — a caption that is present, correct, and
  untracked — must refuse;
- a caption swapped for ``default.srt`` must refuse, because that is a different and
  shorter asset that would otherwise produce a plausible-looking wrong lock;
- the healthy case must pass, or the refusals prove nothing.

The untracked case is induced with ``git rm --cached`` and the index restored
afterwards, because a mutation that also repointed the path would trip
``EVIDENCE_ASSET_REPLACED`` first and never reach the tracking check.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_run  # noqa: E402

EXPERIMENT = ROOT / "projects" / "easel-enhanced-golden"
LOCK = EXPERIMENT / "evidence" / "evidence-lock.json"
SCRIPT = ROOT / "projects" / "easel-review" / "script" / "master.md"
NARRATION = ROOT / "projects" / "easel-review" / "script" / "narration.txt"
STORYBOARD = ROOT / "projects" / "easel-review" / "script" / "storyboard.json"
CANONICAL_CAPTION = EXPERIMENT / "evidence" / "captions" / "easel.srt"
HISTORICAL_CAPTION = ROOT / "projects" / "easel-review" / "assets" / "captions" / "easel.srt"
OTHER_CAPTION = ROOT / "projects" / "easel-review" / "assets" / "captions" / "default.srt"

TESTS: List = []


def test(fn):
    TESTS.append(fn)
    return fn


def _git(*args: str):
    return hidden_run(["git", *args], cwd=str(ROOT), timeout=60)


def verify() -> subprocess.CompletedProcess:
    return hidden_run(
        [sys.executable, str(ROOT / "scripts" / "build_evidence_lock.py"), "--verify"],
        cwd=str(ROOT), timeout=300,
    )


def _refuses(expected_code: str, label: str) -> None:
    _refuses_any({expected_code}, label)


def _refuses_any(codes: set, label: str) -> None:
    """Refuse with one of ``codes``.

    Which code fires depends on whether the edit was staged. An unstaged edit leaves
    the blob intact, so the precise finding is ``EVIDENCE_WORKTREE_DIVERGED`` — "the
    committed baseline is fine, your working copy is not". Staged, the blob moves too
    and it becomes a digest mismatch. Both are correct refusals; asserting one exact
    code would pin the test to an accident of how the mutation was made.
    """
    result = verify()
    combined = (result.stdout or "") + (result.stderr or "")
    assert result.returncode != 0, f"{label}: verify PASSED but must refuse"
    hit = [code for code in codes if code in combined]
    assert hit, (
        f"{label}: refused, but not with any of {sorted(codes)}\n{combined.strip()[:400]}"
    )
    print(f"[ok] {label}: refused with {hit[0]}")


# --- the healthy case ------------------------------------------------------


@test
def test_the_healthy_locked_baseline_verifies():
    """Everything tracked and matching. The refusals below prove nothing without it."""
    if not LOCK.is_file():
        print("[skip] healthy locked baseline verifies (no lock written)")
        return
    result = verify()
    assert result.returncode == 0, (
        "the unmodified baseline must verify, or these refusals prove nothing:\n"
        + ((result.stdout or "") + (result.stderr or ""))[:400]
    )
    print("[ok] healthy: every locked input is present, tracked and matching")


# --- the gap that was missed ----------------------------------------------


@test
def test_an_untracked_caption_refuses_the_verification():
    """Present on disk, correct bytes, correct digest — but absent from Git.

    This is the exact state the last lock was in, and it is the state that reported
    itself reproducible. It has to refuse, because a caption only this machine can
    read is not reproducible input.
    """
    if not LOCK.is_file() or not CANONICAL_CAPTION.is_file():
        print("[skip] untracked caption refuses (no lock or no caption)")
        return
    _git("rm", "--cached", "-q",
         "projects/easel-enhanced-golden/evidence/captions/easel.srt")
    try:
        _refuses("EVIDENCE_INPUT_NOT_TRACKED", "caption present but untracked")
    finally:
        _git("add", "projects/easel-enhanced-golden/evidence/captions/easel.srt")


@test
def test_each_locked_input_refuses_when_untracked():
    """Not just the caption. A lock is only as reproducible as its weakest input."""
    if not LOCK.is_file():
        print("[skip] locked inputs refuse when untracked (no lock written)")
        return
    for label, rel in (
        ("script", "projects/easel-review/script/master.md"),
        ("narration text", "projects/easel-review/script/narration.txt"),
        ("storyboard", "projects/easel-review/script/storyboard.json"),
    ):
        _git("rm", "--cached", "-q", rel)
        try:
            _refuses("EVIDENCE_INPUT_NOT_TRACKED", f"{label} untracked")
        finally:
            _git("add", rel)


# --- the substitution that would have looked fine --------------------------


@test
def test_substituting_default_srt_refuses():
    """``default.srt`` is a different, shorter asset.

    It would have produced a lock with a valid-looking caption digest describing
    captions nobody rendered. The refusal has to name the mismatch rather than accept
    any ``.srt`` that happens to exist.
    """
    if not LOCK.is_file() or not CANONICAL_CAPTION.is_file() or not OTHER_CAPTION.is_file():
        print("[skip] default.srt substitution refuses (missing lock or caption)")
        return
    backup = CANONICAL_CAPTION.read_bytes()
    try:
        shutil.copyfile(OTHER_CAPTION, CANONICAL_CAPTION)
        _refuses_any({"EVIDENCE_SHA_CHANGED", "EVIDENCE_WORKTREE_DIVERGED"}, "caption replaced with default.srt")
    finally:
        CANONICAL_CAPTION.write_bytes(backup)


@test
def test_a_changed_caption_refuses():
    if not LOCK.is_file() or not CANONICAL_CAPTION.is_file():
        print("[skip] changed caption refuses (no lock or caption)")
        return
    backup = CANONICAL_CAPTION.read_bytes()
    try:
        CANONICAL_CAPTION.write_bytes(
            backup + b"\r\n10\r\n00:01:01,900 --> 00:01:03,000\r\nappended\r\n"
        )
        _refuses_any({"EVIDENCE_SHA_CHANGED", "EVIDENCE_WORKTREE_DIVERGED"}, "caption bytes changed")
    finally:
        CANONICAL_CAPTION.write_bytes(backup)


@test
def test_a_removed_caption_refuses():
    if not LOCK.is_file() or not CANONICAL_CAPTION.is_file():
        print("[skip] removed caption refuses (no lock or caption)")
        return
    backup = CANONICAL_CAPTION.read_bytes()
    try:
        CANONICAL_CAPTION.unlink()
        # Which code fires depends on whether the *historical* caption is present on
        # this host. With it, the refusal names the ignored file and tells you to copy
        # the bytes across. Without it — a clean checkout — there is nothing to point
        # at, so the finding is that neither candidate reproduces the locked digest.
        # Both are correct; neither is a pass.
        _refuses_any(
            {
                "EVIDENCE_INPUT_NOT_TRACKED",
                "EVIDENCE_INPUT_MISSING",
                "CAPTION_BASELINE_MISMATCH",
            },
            "canonical caption removed",
        )
    finally:
        CANONICAL_CAPTION.write_bytes(backup)


@test
def test_a_lock_pinning_the_ignored_historical_caption_refuses():
    """The original defect, reproduced against the lock's provenance claim.

    ``easel-review/assets/captions/easel.srt`` has the right bytes and is ignored by
    Git. The digest alone cannot detect this — the historical file and the tracked copy
    are byte-identical, so a lock pinned to the ignored original verified clean. What
    distinguishes them is the *declared canonical path*, so that is what gets corrupted
    here and what the verifier now refuses on.
    """
    if not LOCK.is_file() or not HISTORICAL_CAPTION.is_file():
        print("[skip] ignored historical caption refuses (missing lock or source)")
        return
    backup = LOCK.read_bytes()
    try:
        body = json.loads(LOCK.read_text(encoding="utf-8"))
        provenance = body.get("notes", {}).get("caption_provenance", {}) or {}
        provenance["canonical_path"] = "repo://projects/easel-review/assets/captions/easel.srt"
        body.setdefault("notes", {})["caption_provenance"] = provenance
        LOCK.write_text(json.dumps(body, indent=2), encoding="utf-8")
        _refuses("CAPTION_PROVENANCE_MISMATCH", "lock claims the ignored historical caption")
    finally:
        LOCK.write_bytes(backup)


# --- changed non-caption inputs -------------------------------------------


@test
def test_a_changed_script_or_storyboard_refuses():
    if not LOCK.is_file():
        print("[skip] changed script/storyboard refuses (no lock written)")
        return
    for path, code, label in (
        (SCRIPT, "EVIDENCE_SHA_CHANGED", "master script changed"),
        (NARRATION, "EVIDENCE_SHA_CHANGED", "narration text changed"),
    ):
        backup = path.read_bytes()
        try:
            path.write_bytes(backup + b"\n")
            _refuses_any({"EVIDENCE_SHA_CHANGED", "EVIDENCE_WORKTREE_DIVERGED"}, label)
        finally:
            path.write_bytes(backup)

    backup = STORYBOARD.read_bytes()
    try:
        payload = json.loads(STORYBOARD.read_text(encoding="utf-8"))
        payload["shots"] = payload["shots"][:2]
        STORYBOARD.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        # Dropping shots breaks the placement bindings before the structural check is
        # reached, and EVIDENCE_ASSET_REPLACED is the more specific finding. Accept
        # either: what matters is that a changed storyboard cannot verify.
        result = verify()
        combined = (result.stdout or "") + (result.stderr or "")
        assert result.returncode != 0, "a changed storyboard verified clean"
        assert (
            "EVIDENCE_STORYBOARD_CHANGED" in combined
            or "EVIDENCE_ASSET_REPLACED" in combined
            or "EVIDENCE_ASSET_REMOVED" in combined
        ), f"storyboard change refused with an unexpected code:\n{combined[:400]}"
        print("[ok] storyboard structure changed: refused")
    finally:
        STORYBOARD.write_bytes(backup)


@test
def test_the_repository_is_left_exactly_as_found():
    """The other tests mutate the index and the working tree.

    Compared against the state captured before the suite ran, not against Git: the
    lock is legitimately modified in the working tree during development, so asserting
    a clean ``git status`` would fail for reasons that have nothing to do with whether
    these tests cleaned up after themselves.
    """
    if not LOCK.is_file():
        print("[skip] repository left as found (no lock written)")
        return
    result = verify()
    assert result.returncode == 0, (
        "the repository did not return to a verified state after the mutation tests:\n"
        + ((result.stdout or "") + (result.stderr or ""))[:400]
    )
    for path in (LOCK, CANONICAL_CAPTION, SCRIPT, NARRATION, STORYBOARD):
        rel = path.relative_to(ROOT).as_posix()
        assert _sha(path) == _SUITE_START.get(rel), (
            f"{rel} was left modified by the mutation tests"
        )
    print("[ok] every file touched by the mutation tests is back to its starting bytes")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


#: Digests captured before any test mutates anything, so the final cleanup assertion
#: can prove restoration rather than assume it.
_SUITE_START = {
    path.relative_to(ROOT).as_posix(): _sha(path)
    for path in (LOCK, CANONICAL_CAPTION, SCRIPT, NARRATION, STORYBOARD)
    if path.is_file()
}


@test
def test_locked_digests_come_from_git_blobs_not_the_working_tree():
    """A working-tree digest is a host-specific digest.

    ``.gitattributes`` normalises ``*.md``/``*.txt``/``*.json`` to LF, so the blob is
    what every platform reproduces. But this Windows checkout still holds CRLF copies
    of files that were authored before that rule applied -- Git only applies
    ``.gitattributes`` on checkout, so those files were never rewritten -- and an
    earlier lock read exactly those bytes.

    The Linux CI runner then measured ``master.md`` at ``99767915`` against the
    ``7df3adbd`` this host had pinned, and the lock failed on every platform but this
    one. That is a reproducibility bug in the lock, not in the repository, and it is
    invisible from a single machine by construction.

    So the assertion is about provenance of the digest, not about a value: the lock
    must agree with the blob, and the blob must be what a fresh checkout produces.
    """
    if not LOCK.is_file():
        print("[skip] lock digests come from git blobs (no lock written)")
        return
    from build_evidence_lock import canonical_bytes, worktree_matches_canonical

    lock = _load(LOCK)
    checks = (
        ("script", SCRIPT, lock["master_script_sha256"]),
        ("narration_text", NARRATION, lock["narration_text_sha256"]),
    )
    for label, path, pinned in checks:
        raw = canonical_bytes(path)
        actual = hashlib.sha256(raw).hexdigest()
        assert actual == pinned, (
            f"{label}: the lock pins {pinned[:12]} but its Git blob hashes "
            f"{actual[:12]}. The lock must digest the blob, not the working tree."
        )
        # And a CRLF-only difference must not be mistaken for content drift.
        assert worktree_matches_canonical(path), (
            f"{label}: the working tree differs from its blob beyond line endings"
        )

    # Binary assets are marked `binary` in .gitattributes, so their bytes are
    # preserved exactly and blob == working tree. This is the control case proving
    # the blob rule does not silently alter binary content.
    assert _sha(CANONICAL_CAPTION) == lock["caption_sha256"], (
        "the caption is declared binary, so its digest must be the raw bytes"
    )
    print("[ok] locked digests come from Git blobs, and binary assets are unaffected")


def main() -> int:
    failures = []
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    print()
    if failures:
        print(f"{len(failures)} of {len(TESTS)} test(s) failed")
        return 1
    print(f"All {len(TESTS)} locked-input reproducibility tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())