"""Gitignore policy for the Golden A/B voice fixtures -- a regression test on the exception.

The two narration files behind the M4.6 A/B experiment were exempted from the blanket
audio ignore so that voice provenance survives on a fresh checkout. Before this, arm B's
provenance rested on a provider receipt that said ``PASS`` about bytes living in a
gitignored ``.verify-tmp`` directory: a claim with nothing on disk to check it against,
resolvable only on the machine that happened to generate it.

That is the right exception and also the easiest one to widen by accident. Add
``!*.wav`` and every audio file in the repository becomes trackable; add
``!projects/*/golden-assets/`` and the next generated clip comes with it. Neither looks
wrong in a diff, and both commit megabytes nobody can verify.

So the *narrowness* is what gets tested, not just the presence of the allowlist:

- the two exact approved audio files are trackable, on disk, and byte-exact;
- everything else stays ignored -- random audio anywhere, arbitrary provider output,
  the ``.verify-tmp`` candidates, another project's voice assets, the historical
  ``voice_easel`` asset, and every rendered ``final.mp4``;
- the global ``*.wav`` / ``*.mp3`` / ``projects/*/assets/voice/`` rules all survive;
- no broad negation exists anywhere in the file.

Tracking a file also must not be mistaken for strengthening its provenance. Arm A has no
generation receipt, so its class stays ``CONSISTENT_HISTORICAL_BASELINE``; a tracked file
that is easy to find is not a verified one, and test 9 pins that distinction so a future
commit cannot quietly upgrade it by co-location.

``.gitignore`` is read with ``\\r`` stripped before matching. This host keeps CRLF line
endings, and an ``$``-anchored pattern fails against a CRLF line while passing against an
LF one -- a policy test that only proves the rule on whichever platform happens to hold
the LF copy is not testing the rule.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from process_utils import hidden_run  # noqa: E402

GITIGNORE = ROOT / ".gitignore"
VOICE = "projects/easel-enhanced-golden/golden-assets/voice"

#: Exactly the two files the Founder approved, with the SHA256 each must keep. Not
#: hard-coded into the build: the build reads this, so the audit and the policy cannot
#: drift apart.
CANONICAL: List[tuple] = [
    (
        f"{VOICE}/A-baseline-edge-tts.mp3",
        "bc6b721656a5aab3491d45b15a649ec6161eae04652a5e6d627f722ffbe8b625",
    ),
    (
        f"{VOICE}/B-minimax-speech-2.8-hd.wav",
        "e2e014a916eb7a637b68d80ace27551c557d3797541b61f41c195f8256b86593",
    ),
]

#: The tracked B provider receipt. Not audio, so it is already trackable; pinned here
#: because arm B's provenance is worthless without it.
CANONICAL_RECEIPT = f"{VOICE}/B-minimax-speech-2.8-hd.receipt.json"
PROVENANCE_INDEX = f"{VOICE}/GOLDEN-VOICE-ASSETS.json"

#: Everything that must stay ignored. Rendered output is here on purpose: fixed
#: experiment inputs are tracked, renders are reproducible from them.
MUST_STAY_IGNORED: List[str] = [
    "random.mp3",
    "random.wav",
    "docs/clip.mp3",
    "docs/clip.wav",
    "assets/voice/someone-elses-take.wav",
    ".verify-tmp/m2/ab/A-edge-tts.mp3",
    ".verify-tmp/m2/ab/B-minimax-mplan.wav",
    ".verify-tmp/m2/narration/narration-441c2b8634a43a33.wav",
    "projects/easel-review/assets/voice_easel/narration.mp3",
    "projects/easel-enhanced-golden/assets/voice/narration.wav",
    "projects/some-other-project/assets/voice/2026-10-06-take.wav",
    "projects/demo/assets/generated/frame.wav",
    "projects/demo/assets/processed/shot-replace.mp3",
    "projects/demo/final/final.mp4",
    "projects/easel-enhanced-golden/variants/A/final/final.mp4",
    "projects/easel-enhanced-golden/variants/B/final/final.mp4",
]

#: Negations that would widen the exception past the two approved files.
BROAD_NEGATIONS = (
    "!*.wav",
    "!*.mp3",
    "!*.mp4",
    "!projects/*/golden-assets/",
    "!projects/*/golden-assets/**",
    "!projects/easel-enhanced-golden/golden-assets/",
    "!projects/easel-enhanced-golden/golden-assets/**",
    "!projects/*/voice/",
    "!projects/*/assets/voice/",
    "!projects/*/assets/voice/**",
    "!**/*.wav",
    "!**/*.mp3",
)

#: Global rules that must survive the exception.
GLOBAL_RULES = ("*.wav", "*.mp3", "projects/*/assets/voice/")

TESTS: List = []


def test(fn):
    TESTS.append(fn)
    return fn


def ignored(rel: str) -> bool:
    """Ask gitignore itself, not a re-implementation of it.

    ``--no-index`` because the two canonical files are now tracked, and the index --
    not ``.gitignore`` -- governs tracked paths. Asking ``--no-index`` tests the rules
    themselves, so the suite would still catch a widened rule if the files were ever
    untracked again.
    """
    out = hidden_run(
        ["git", "check-ignore", "-q", "--no-index", "--", rel],
        cwd=str(ROOT), timeout=60,
    )
    return out.returncode == 0


def tracked(rel: str) -> bool:
    out = hidden_run(
        ["git", "ls-files", "--error-unmatch", rel], cwd=str(ROOT), timeout=60
    )
    return out.returncode == 0


def ignore_rules() -> List[str]:
    """Every .gitignore line, CRLF-normalised, comments and blanks dropped."""
    text = GITIGNORE.read_text(encoding="utf-8", errors="replace")
    lines = [ln.strip().rstrip("\r") for ln in text.splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


@test
def test_the_two_canonical_voice_files_are_tracked():
    for rel, _sha in CANONICAL:
        assert not ignored(rel), f"{rel} is still ignored by the rules"
        assert tracked(rel), f"{rel} is not tracked; the exception exists but nothing was added"
    print(f"[ok] 1. both canonical voice fixtures ({len(CANONICAL)}) are tracked")


@test
def test_the_canonical_voice_files_hold_their_exact_bytes():
    """The SHA is the whole point.

    These are experiment inputs, so a silently trimmed, resampled or re-tagged file
    would not be a near-miss: it would be a different audio file wearing the right
    filename, and every provenance claim downstream of it would be describing bytes
    nobody is listening to.
    """
    for rel, want in CANONICAL:
        path = ROOT / rel
        assert path.is_file(), f"{rel} does not exist on disk"
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        assert got == want, (
            f"{rel} hashes {got}, expected {want}. The copy must be byte-exact -- no "
            "decode, re-encode, trim, resample or metadata rewrite."
        )
    print("[ok] 2. both canonical voice files are byte-exact against their recorded SHA256")


@test
def test_every_other_audio_file_stays_ignored():
    """The narrowness of the exception. A widened rule fails here first."""
    wrong = [rel for rel in MUST_STAY_IGNORED if not ignored(rel)]
    assert not wrong, (
        "these are no longer ignored, so the Golden voice exception has widened past "
        f"the two approved fixtures: {wrong}"
    )
    print(f"[ok] 3. all {len(MUST_STAY_IGNORED)} non-approved audio/video files stay ignored")


@test
def test_rendered_finals_stay_ignored():
    """Tracked inputs, reproducible output.

    ``variants/*/final/final.mp4`` is the one thing that must not get pulled in. It is
    the product of the experiment rather than an input to it, and committing it would
    make the two arms look reproducible when what is actually reproducible is the
    evidence, the script and the narration.
    """
    for arm in ("A", "B"):
        rel = f"projects/easel-enhanced-golden/variants/{arm}/final/final.mp4"
        assert ignored(rel), f"{rel} is no longer ignored; rendered output must stay out of Git"
    print("[ok] 4. both variant final.mp4 renders stay ignored and rebuildable")


@test
def test_no_broad_negation_rule_is_present():
    """The failure mode with no visible symptom until someone commits megabytes."""
    rules = set(ignore_rules())
    present = [p for p in BROAD_NEGATIONS if p in rules]
    assert not present, (
        "broad negation(s) present, which would unignore far more than the two "
        f"approved fixtures: {present}"
    )
    print(f"[ok] 5. none of the {len(BROAD_NEGATIONS)} broad negations is present")


@test
def test_global_audio_ignores_survive():
    for rule in GLOBAL_RULES:
        assert rule in set(ignore_rules()), (
            f"the global rule {rule!r} is gone. The exception adds two paths; it must "
            "not remove the blanket rule that makes provider output untrackable by "
            "default."
        )
    print(f"[ok] 6. all {len(GLOBAL_RULES)} global audio ignores survive")


@test
def test_the_audio_allowlist_is_exactly_two():
    """Count, not just presence.

    A third ``!*.wav``-adjacent exception would be easy to add and would read as
    housekeeping. Pinning the count means the next one has to be argued for.
    """
    exceptions = [r for r in ignore_rules() if r.startswith("!") and r.endswith((".wav", ".mp3"))]
    expected = sorted("!" + rel for rel, _ in CANONICAL)
    assert sorted(exceptions) == expected, (
        "the exact Golden audio allowlist is not exactly the two approved files.\n"
        f"  found:    {sorted(exceptions)}\n"
        f"  expected: {expected}"
    )
    print(f"[ok] 7. the exact Golden audio allowlist is exactly {len(CANONICAL)} paths")


@test
def test_the_b_provider_receipt_is_tracked_and_binds_to_the_asset():
    """Arm B's provenance is only as good as the receipt that pins its bytes.

    Without a tracked receipt, B was a filename on a machine nobody else had. The
    binding that makes it checkable is ``normalized_sha256`` equalling the asset's own
    SHA256 -- not merely being present in the same directory.
    """
    rel = CANONICAL_RECEIPT
    assert not ignored(rel), f"{rel} is ignored"
    assert tracked(rel), f"{rel} is not tracked; arm B cannot be validated without it"
    receipt = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    b_sha = dict(CANONICAL)[f"{VOICE}/B-minimax-speech-2.8-hd.wav"]
    assert receipt["normalized_sha256"] == b_sha, (
        "the receipt does not bind to the canonical B bytes: "
        f"receipt.normalized_sha256={receipt['normalized_sha256']} vs asset {b_sha}"
    )
    assert receipt["human_review"] == "PENDING_FOUNDER_REVIEW", (
        "the historical receipt must keep its own PENDING_FOUNDER_REVIEW state; code "
        "does not perform human review"
    )
    assert receipt["production_ready"] is False, (
        "the historical receipt says production_ready=false and that must survive"
    )
    print("[ok] 8. the B provider receipt is tracked and binds to the canonical asset")


@test
def test_tracking_arm_a_did_not_upgrade_its_provenance_class():
    """Tracking a file is not verifying it.

    Arm A is tracked so the experiment's control arm exists on every machine. It still
    has no generation receipt, so its class stays CONSISTENT_HISTORICAL_BASELINE. This
    is the assertion that stops the two being conflated later: the asset is now as easy
    to find as B's, and the easy-to-find-ness is exactly what makes the weaker class
    easy to forget.
    """
    index = json.loads((ROOT / PROVENANCE_INDEX).read_text(encoding="utf-8"))
    assert index["is_provider_receipt"] is False, (
        "the Golden asset index must declare that it is not a provider receipt"
    )
    by_arm = {e["arm"]: e for e in index["canonical_assets"]}
    assert by_arm["A"]["provenance_class"] == "CONSISTENT_HISTORICAL_BASELINE", (
        f"arm A was upgraded to {by_arm['A']['provenance_class']!r}; no generation "
        "receipt exists for it, so it must not claim to be verified"
    )
    assert by_arm["A"]["provider_receipt"] is None, (
        "arm A has no provider receipt. A file shaped like one would be read as one and "
        "would silently upgrade a weaker provenance class."
    )
    assert by_arm["B"]["provenance_class"] == "VERIFIED_CURRENT_BASELINE", (
        "arm B is bound by a receipt, a SHA and a text binding; its class should be "
        "VERIFIED_CURRENT_BASELINE"
    )
    print("[ok] 9. tracking A did not upgrade its provenance class")


@test
def test_the_tracked_receipts_carry_no_credential_or_host_path():
    """These files become permanent the moment they are committed.

    A tracked secret stays tracked. The B receipt was already credential-sanitised at
    generation, but it did carry an absolute host path in two fields; that was rewritten
    to a ``repo://`` reference because where the provider wrote its output on one machine
    is incidental, while the repo-relative remainder is the historical fact.
    """
    import re

    host_path = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]{1,2}[A-Za-z0-9_.\-]")
    secret = re.compile(
        r"(?i)(sk-[A-Za-z0-9]{8,}|eyJ[A-Za-z0-9_\-]{10,}|AKIA[A-Z0-9]{12,}"
        r"|xox[baprs]-|gh[pousr]_[A-Za-z0-9]{20,})"
    )
    for rel in (CANONICAL_RECEIPT, PROVENANCE_INDEX):
        assert not ignored(rel), f"{rel} is ignored"
        assert tracked(rel), f"{rel} is not tracked"
        blob = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        m = host_path.search(blob)
        assert not m, f"{rel} carries a machine absolute path: {m.group(0)!r}"
        s = secret.search(blob)
        assert not s, f"{rel} carries a credential-shaped literal: {s.group(0)[:12]!r}"
    print("[ok] 10. tracked provenance files carry no host path and no credential")


def main() -> int:
    failures = 0
    for fn in TESTS:
        name = fn.__name__
        try:
            fn()
        except AssertionError as exc:
            print(f"[FAIL] {name}: {exc}")
            failures += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR ] {name}: {type(exc).__name__}({exc})")
            failures += 1
    total = len(TESTS)
    if failures:
        print(f"\n{failures} of {total} test(s) failed")
        return 1
    print(f"\nAll {total} Golden voice media policy tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())