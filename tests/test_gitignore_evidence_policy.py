"""Gitignore policy for source evidence — a regression test on the exception itself.

Six screenshots were exempted from the blanket media ignore so a published video's
evidence could be verified from the repository. That is the right exception and also
the easiest one to widen by accident: move the negations above ``*.png`` and every
image in the repository becomes trackable, and nothing about that looks wrong in a
diff.

So the *narrowness* is what gets tested, not just the presence of the allowlist:

- the six exact paths are trackable;
- everything else stays ignored — other screenshots in the same directory, generated
  and processed assets, finals, and an arbitrary PNG anywhere;
- no broad negation exists anywhere in the file.

``git check-ignore --no-index`` is used rather than plain ``check-ignore`` because the
four older ``01``–``04`` screenshots are already tracked, and the index — not
``.gitignore`` — governs those. Asking ``--no-index`` tests the rules themselves, so
this suite would still catch a widened rule if those four files were ever untracked.
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from process_utils import hidden_run  # noqa: E402

GITIGNORE = ROOT / ".gitignore"
SHOTS = "projects/easel-review/sources/screenshots"

#: The six paths the Founder approved. Exactly these, nothing more.
ALLOWLIST: List[str] = [
    f"{SHOTS}/10-easel-doctor.png",
    f"{SHOTS}/11-easel-ping.png",
    f"{SHOTS}/12-easel-version-evidence.png",
    f"{SHOTS}/13-easel-skill-layers.png",
    f"{SHOTS}/14-easel-skills-dir.png",
    f"{SHOTS}/15-easel-doctor-fails.png",
]

#: Must stay ignored. Build artefacts are reproducible; evidence is not, which is the
#: whole reason the exception exists.
MUST_STAY_IGNORED: List[str] = [
    f"{SHOTS}/01-easel-hero.png",
    f"{SHOTS}/02-easel-features.png",
    f"{SHOTS}/03-easel-architecture.png",
    f"{SHOTS}/04-easel-skills.png",
    f"{SHOTS}/99-arbitrary-new-screenshot.png",
    "projects/easel-review/sources/screenshots/screenshot.png",
    "projects/demo/assets/generated/frame.png",
    "projects/demo/assets/processed/shot-replace.png",
    "projects/demo/final/thumbnail.png",
    "projects/demo/work/shot_00.png",
    "docs/diagram.png",
    "random.png",
]

#: Negation patterns that would widen the exception beyond the six files.
BROAD_NEGATIONS = (
    "!*.png", "!*.jpg", "!*.jpeg", "!*.gif", "!*.webp",
    "!projects/*/sources/",
    "!projects/*/sources/**",
    "!projects/easel-review/sources/screenshots/",
    "!projects/*/sources/screenshots/",
)

TESTS: List = []


def test(fn):
    TESTS.append(fn)
    return fn


def ignored(rel: str) -> bool:
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


@test
def test_the_six_evidence_screenshots_are_trackable():
    for rel in ALLOWLIST:
        assert not ignored(rel), f"{rel} is still ignored by the rules"
        assert tracked(rel), f"{rel} is not tracked; the exception exists but nothing was added"
    print(f"[ok] 1. all {len(ALLOWLIST)} allowlisted evidence files are tracked")


@test
def test_the_allowlisted_files_are_present_with_real_bytes():
    """An exemption for a file that does not exist is a policy with nothing behind it."""
    for rel in ALLOWLIST:
        path = ROOT / rel
        assert path.is_file(), f"{rel} does not exist on disk"
        raw = path.read_bytes()
        assert raw[:8] == b"\x89PNG\r\n\x1a\n", f"{rel} is not a PNG"
        assert len(raw) > 1024, f"{rel} is implausibly small ({len(raw)} bytes)"
        # Dimensions come from the IHDR, so a truncated or mislabelled file is caught
        # without a decoder dependency.
        width, height = struct.unpack(">II", raw[16:24])
        assert (width, height) == (1080, 1920), (
            f"{rel} is {width}x{height}, not the 1080x1920 the baseline storyboard "
            f"composes at. A different size means the bytes are not what was rendered."
        )
    print("[ok] 2. every allowlisted file exists with real 1080x1920 PNG bytes")


@test
def test_every_other_image_stays_ignored():
    """The narrowness of the exception. A widened rule would fail here first."""
    wrong = [rel for rel in MUST_STAY_IGNORED if not ignored(rel)]
    assert not wrong, (
        "these are no longer ignored, so the source-evidence exception has widened "
        f"beyond the six approved files: {wrong}"
    )
    print(f"[ok] 3. all {len(MUST_STAY_IGNORED)} non-approved images stay ignored")


@test
def test_no_broad_negation_rule_is_present():
    """The failure mode that has no visible symptom until someone commits 40 MB.

    Gitignore is last-match-wins, so an ``!*.png`` placed above the ``*.png`` rule
    silently unignores every image in the repository. Asserting the absence of these
    patterns is the only cheap way to catch that.
    """
    text = GITIGNORE.read_text(encoding="utf-8")
    present = [pattern for pattern in BROAD_NEGATIONS
               if re.search(rf"^\s*{re.escape(pattern)}\s*$", text, re.MULTILINE)]
    assert not present, (
        f"broad negation rule(s) present in .gitignore: {present}. The exception must "
        f"name the six exact files, never a directory, glob or extension."
    )
    print("[ok] 4. no broad negation rule exists in .gitignore")


@test
def test_the_global_media_ignore_is_still_intact():
    """The exception must not have been bought by weakening the blanket rule."""
    text = GITIGNORE.read_text(encoding="utf-8")
    for rule in ("*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.mp4", "*.wav"):
        assert re.search(rf"^\s*{re.escape(rule)}\s*$", text, re.MULTILINE), (
            f"the global {rule} ignore is gone. Removing it would make the exception "
            f"unnecessary and would let every build artefact be committed."
        )
    print("[ok] 5. the global media ignore rules are still present")


@test
def test_the_negations_come_after_the_rule_they_negate():
    """Ordering is the whole mechanism, and it is invisible in a file listing."""
    text = GITIGNORE.read_text(encoding="utf-8")
    png_rule = text.index("*.png")
    for rel in ALLOWLIST:
        position = text.index(f"!{rel}")
        assert position > png_rule, (
            f"!{rel} appears before the *.png rule. gitignore is last-match-wins, so "
            f"an earlier negation has no effect and the file stays ignored."
        )
    print("[ok] 6. every negation is positioned after the rule it negates")


@test
def test_the_allowlist_has_no_duplicates_or_stray_entries():
    lines = [
        line.strip() for line in GITIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("!") and line.strip().endswith(".png")
    ]
    assert len(lines) == len(set(lines)), f"duplicate png negations: {lines}"
    stray = sorted(set(lines) - {f"!{rel}" for rel in ALLOWLIST})
    assert not stray, (
        f"unexpected png negation(s) beyond the six approved files: {stray}. Any new "
        f"entry needs the same sensitive-data review and Founder decision."
    )
    print("[ok] 7. the png allowlist is exactly six entries, no duplicates")


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
    print(f"All {len(TESTS)} source-evidence gitignore policy tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())