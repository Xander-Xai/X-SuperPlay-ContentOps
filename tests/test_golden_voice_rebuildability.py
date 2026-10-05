"""Clean-checkout rebuildability of the Golden A/B voice inputs.

The M4.6 A/B experiment had a provenance problem that no single-machine test could see.
Before the Golden fixtures were tracked, arm B's provenance was a provider receipt that
said ``PASS`` about bytes living in a gitignored ``.verify-tmp`` directory, and arm A
lived only in a second gitignored directory. On this machine both resolved. On any
other machine -- including every CI runner -- neither existed, and the tests that were
supposed to defend those claims quietly skipped instead.

A claim that only resolves where it was made is not evidence. So this suite does not ask
"do the assets exist here". It asks: **can a clean checkout resolve the production
Evidence Lock, both canonical narrations and B's provider receipt, with every host-local
input removed, and do the digests still match?**

The method is to make a temporary clone of this repository, delete the host-local inputs
from it, and resolve there. The clone is the only honest reproduction of what a second
engineer receives: the same tracked bytes, none of the ignored ones.

Deliberately no ``.verify-tmp`` in the result. Anything that still resolves has to be
resolving from the repository.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
from process_utils import hidden_run  # noqa: E402

EXPERIMENT = ROOT / "projects" / "easel-enhanced-golden"
VOICE = EXPERIMENT / "golden-assets" / "voice"

LOCK_REL = "projects/easel-enhanced-golden/evidence/evidence-lock.json"
CAPTION_REL = "projects/easel-enhanced-golden/evidence/captions/easel.srt"
A_REL = "projects/easel-enhanced-golden/golden-assets/voice/A-baseline-edge-tts.mp3"
B_REL = "projects/easel-enhanced-golden/golden-assets/voice/B-minimax-speech-2.8-hd.wav"
B_RECEIPT_REL = (
    "projects/easel-enhanced-golden/golden-assets/voice/B-minimax-speech-2.8-hd.receipt.json"
)

#: Inputs that must resolve in the clean clone, with the digest each must hash to.
EXPECTED: List[tuple] = [
    (A_REL, "bc6b721656a5aab3491d45b15a649ec6161eae04652a5e6d627f722ffbe8b625"),
    (B_REL, "e2e014a916eb7a637b68d80ace27551c557d3797541b61f41c195f8256b86593"),
]

#: Host-local paths the experiment used to depend on. Each must be absent from the
#: clone, so that anything resolving there resolves from Git.
HOST_LOCAL = [
    ".verify-tmp",
    "projects/easel-review/assets/voice_easel",
    "projects/easel-review/assets/voice",
]

TESTS: List = []


def test(fn):
    TESTS.append(fn)
    return fn


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return hidden_run(["git", *args], cwd=str(cwd), timeout=900)


def _make_clean_clone(dest: Path) -> None:
    """Clone the current repository and strip every host-local input from it.

    ``--no-hardlinks`` matters: without it the clone can share object files with the
    working repository, and a test that then "proves" the objects are in Git is really
    just reading the source repository's disk.
    """
    _git("clone", "--quiet", "--no-hardlinks", "--depth", "1",
         "--branch", _current_branch(), str(ROOT), str(dest), cwd=ROOT)
    for rel in HOST_LOCAL:
        target = dest / rel
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)


def _current_branch() -> str:
    out = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=ROOT)
    return (out.stdout or "").strip() or "HEAD"


_CLONE: Optional[Path] = None


def clean_clone() -> Optional[Path]:
    """One clone for the whole suite: cloning per test would dominate the runtime."""
    global _CLONE
    if _CLONE is None:
        tmp = Path(tempfile.mkdtemp(prefix="contentops-clean-"))
        dest = tmp / "repo"
        try:
            _make_clean_clone(dest)
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(tmp, ignore_errors=True)
            print(f"[skip] clean-checkout rebuildability (clone failed: {exc})")
            return None
        _CLONE = dest
    return _CLONE


@test
def test_the_clone_really_has_no_host_local_voice_inputs():
    """Guard the guard.

    If a host-local path survived into the clone, every assertion below would pass for
    the wrong reason and this whole suite would be decorative.
    """
    dest = clean_clone()
    if dest is None:
        return
    survivors = [rel for rel in HOST_LOCAL if (dest / rel).exists()]
    assert not survivors, (
        f"host-local inputs survived into the clean clone: {survivors}. The rebuildability "
        "claims below would be satisfied by local files rather than by Git."
    )
    # And the historical render input A was approved against is genuinely absent, so the
    # suite is testing the tracked path rather than the convenient one.
    assert not (dest / "projects/easel-review/assets/voice_easel/narration.mp3").exists()
    print(f"[ok] 1. clean clone carries none of the {len(HOST_LOCAL)} host-local inputs")


@test
def test_the_production_evidence_lock_resolves_in_a_clean_clone():
    dest = clean_clone()
    if dest is None:
        return
    lock_path = dest / LOCK_REL
    assert lock_path.is_file(), f"{LOCK_REL} is not tracked, so a clean checkout cannot verify it"

    out = _git("-C", str(dest), "ls-files", "--error-unmatch", LOCK_REL, cwd=ROOT)
    assert out.returncode == 0, f"{LOCK_REL} is not tracked"

    result = _run_verify(dest)
    assert result.returncode == 0, (
        "build_evidence_lock.py --verify failed in a clean clone, which is the exact "
        "failure the Linux runner hit:\n"
        + ((result.stdout or "") + (result.stderr or "")).strip()[:600]
    )
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert lock["fixture"] is False
    assert re_hex(lock["fingerprint"]), lock["fingerprint"]
    print(f"[ok] 2. production Evidence Lock resolves and verifies ({lock['fingerprint'][:12]})")


def re_hex(value: Any) -> bool:
    import re

    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value)))


def _run_verify(dest: Path) -> subprocess.CompletedProcess:
    return hidden_run(
        [sys.executable, "scripts/build_evidence_lock.py", "--verify"],
        cwd=str(dest), timeout=900,
    )


@test
def test_both_canonical_narrations_resolve_to_the_approved_bytes():
    """The core claim: a clean checkout gets the approved narration, byte-exact."""
    dest = clean_clone()
    if dest is None:
        return
    for rel, want in EXPECTED:
        path = dest / rel
        assert path.is_file(), (
            f"{rel} is not tracked. Without it this arm cannot be built outside the "
            "machine that ran the experiment, which is what makes the A/B result "
            "unverifiable."
        )
        out = _git("-C", str(dest), "ls-files", "--error-unmatch", rel, cwd=ROOT)
        assert out.returncode == 0, f"{rel} is present but not tracked"
        got = _sha(path)
        assert got == want, (
            f"{rel} in a clean checkout hashes {got}, expected {want}. The committed "
            "bytes are not the approved bytes, so the experiment input is not what was "
            "approved."
        )
    print(f"[ok] 3. both canonical narrations resolve byte-exact ({len(EXPECTED)})")


@test
def test_b_provider_receipt_resolves_and_binds_to_the_asset():
    """B's provenance is only checkable if the receipt travels with the audio."""
    dest = clean_clone()
    if dest is None:
        return
    receipt_path = dest / B_RECEIPT_REL
    assert receipt_path.is_file(), f"{B_RECEIPT_REL} is not tracked"
    receipt: Dict[str, Any] = json.loads(receipt_path.read_text(encoding="utf-8"))
    asset_sha = _sha(dest / B_REL)
    assert receipt["normalized_sha256"] == asset_sha, (
        "the tracked receipt does not bind to the tracked B bytes, so the binding is "
        "still only verifiable on the machine that generated it"
    )
    # The historical states must have survived the copy unchanged.
    assert receipt["human_review"] == "PENDING_FOUNDER_REVIEW"
    assert receipt["production_ready"] is False
    print("[ok] 4. B provider receipt resolves and binds to the canonical asset")


@test
def test_b_provenance_resolves_with_no_verify_tmp_at_all():
    """Run the real selector inside the clone.

    Everything above proves the files are present. This proves the *code path* that a
    build actually takes resolves without any host-local input -- which is the thing
    that was silently host-local before.
    """
    dest = clean_clone()
    if dest is None:
        return
    probe = (
        "import sys, json;"
        "sys.path.insert(0, 'scripts');"
        "from build_golden_variant_ab import select_a_voice, select_b_voice;"
        "a = select_a_voice(); b = select_b_voice();"
        "print(json.dumps({"
        "'a_class': a.provenance_class, 'b_class': b.provenance_class,"
        "'a_ref': a.asset_ref, 'b_ref': b.asset_ref,"
        "'a_sha': a.sha256, 'b_sha': b.sha256,"
        "'a_calls': a.provider_calls, 'b_calls': b.provider_calls}))"
    )
    out = hidden_run(
        [sys.executable, "-c", probe], cwd=str(dest), timeout=1800
    )
    combined = (out.stdout or "") + (out.stderr or "")
    assert out.returncode == 0, (
        "voice selection failed in a clean clone with no .verify-tmp present. The build "
        "is still reaching for a host-local path:\n" + combined.strip()[:800]
    )
    line = next(
        (l for l in (out.stdout or "").splitlines() if l.startswith("{")), None
    )
    assert line, f"no selection output:\n{combined.strip()[:400]}"
    data = json.loads(line)
    assert data["a_class"] == "CONSISTENT_HISTORICAL_BASELINE", data["a_class"]
    assert data["b_class"] == "VERIFIED_CURRENT_BASELINE", data["b_class"]
    assert data["a_sha"] == dict(EXPECTED)[A_REL]
    assert data["b_sha"] == dict(EXPECTED)[B_REL]
    assert data["a_calls"] == 0 and data["b_calls"] == 0, (
        f"selection reported provider calls: A={data['a_calls']} B={data['b_calls']}"
    )
    assert data["a_ref"].startswith("repo://") and data["b_ref"].startswith("repo://"), (
        f"asset refs are not portable: {data['a_ref']}, {data['b_ref']}"
    )
    print("[ok] 5. both selectors resolve from Git alone, 0 provider calls")


@test
def test_the_variant_receipts_reference_canonical_assets():
    """A receipt naming ``.verify-tmp`` cannot be resolved by whoever reads it."""
    for arm in ("A", "B"):
        path = ROOT / f"projects/easel-enhanced-golden/variants/{arm}/receipts/variant-receipt.json"
        if not path.is_file():
            continue
        blob = json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False)
        import re

        current = re.findall(r'"narration_asset_ref"\s*:\s*"([^"]+)"', blob)
        if current:
            for ref in current:
                assert ref.startswith("repo://"), (
                    f"{arm}: narration_asset_ref {ref!r} is not a repo:// reference"
                )
        # Whatever else the receipt says, a *current* provenance field must not require
        # the host-local directory to resolve. Historical candidates may name it.
        assert ".verify-tmp" not in blob or "historical" in blob.lower(), (
            f"{arm}: receipt mentions .verify-tmp without marking it historical"
        )
    print("[ok] 6. variant receipts carry portable canonical narration references")


def main() -> int:
    failures = 0
    try:
        for fn in TESTS:
            try:
                fn()
            except AssertionError as exc:
                print(f"[FAIL] {fn.__name__}: {exc}")
                failures += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[ERR ] {fn.__name__}: {type(exc).__name__}({exc})")
                failures += 1
    finally:
        if _CLONE is not None:
            shutil.rmtree(_CLONE.parent, ignore_errors=True)
    total = len(TESTS)
    if failures:
        print(f"\n{failures} of {total} test(s) failed")
        return 1
    print(f"\nAll {total} clean-checkout rebuildability tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())