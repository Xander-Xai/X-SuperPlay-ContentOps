#!/usr/bin/env python3
"""Validate the spoken script and emit the narration version map. Issue #34.

Three versions of the narration exist from this round on, and they must not be
confused with one another:

1. **original** -- `projects/easel-review/script/narration.txt`, locked by
   `projects/easel-enhanced-golden/evidence/evidence-lock.json`;
2. **spoken** -- `projects/easel-enhanced-golden/script/narration-spoken.json`,
   the editorial derivative this round authors;
3. **synthesis** -- what the provider actually receives: the spoken text with
   the pronunciation lexicon applied (and the `<#x#>` markers preserved).

This script checks every mechanical invariant of the spoken script against the
original and the lock (see `contentops.media.spoken_script`), and -- with
`--write` -- writes the SHA256 mapping of all three plus the C-variant
segment texts to `narration-version-map.json`.

It never touches the original, never clears the lock, and makes no provider
call. Exit codes: 0 = verified, 1 = verification failed, 2 = input missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.lexicon import default_zh_lexicon  # noqa: E402
from contentops.media.native_rounds import canonical_blob_sha256  # noqa: E402
from contentops.media.spoken_script import (  # noqa: E402
    SpokenScriptError,
    load_spoken_script,
    synthesis_versions,
    verify_script,
)

ORIGINAL = ROOT / "projects/easel-review/script/narration.txt"
EVIDENCE_LOCK = ROOT / "projects/easel-enhanced-golden/evidence/evidence-lock.json"
SPOKEN_SCRIPT = ROOT / "projects/easel-enhanced-golden/script/narration-spoken.json"
VERSION_MAP = ROOT / "projects/easel-enhanced-golden/script/narration-version-map.json"


def _spoken_digest_fields(path: Path) -> tuple:
    """``(working_tree_sha256, canonical_blob_sha256_or_None)``.

    Two digests, because the spoken script is new in the change that writes the
    version map:

    - ``working_tree_sha256`` is the sha256 of the file's actual bytes. The file
      is written with LF, and ``.gitattributes`` pins ``*.json text eol=lf``, so
      those bytes are what a commit stores -- but this script states the bytes
      it hashed rather than assuming that.
    - ``canonical_blob_sha256`` is the digest of the committed blob
      (:func:`contentops.media.native_rounds.canonical_blob_sha256`), or ``None``
      before the file is tracked. When both exist they must agree; a working
      tree that differs from its committed blob is an ambiguous state and is
      refused rather than hashed into a permanent record.
    """
    import hashlib as _hashlib

    working = _hashlib.sha256(path.read_bytes()).hexdigest()
    canonical = canonical_blob_sha256(path)
    if canonical is not None and canonical != working:
        raise SystemExit(
            "refusing: the spoken script's working tree differs from its "
            "committed blob; commit or restore it before regenerating the map"
        )
    return working, canonical


def _evidence_lock_digest() -> str:
    if not EVIDENCE_LOCK.is_file():
        raise SystemExit(f"evidence lock missing: {EVIDENCE_LOCK}")
    try:
        payload = json.loads(EVIDENCE_LOCK.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"evidence lock is not readable JSON: {exc}")
    return str(payload.get("narration_text_sha256") or "")


def _version_map(script, report) -> dict:
    lexicon = default_zh_lexicon()
    versions = synthesis_versions(script, lexicon)
    original_digest = canonical_blob_sha256(ORIGINAL)
    spoken_working, spoken_canonical = _spoken_digest_fields(SPOKEN_SCRIPT)
    return {
        "schema": "contentops.narration-version-map/v1",
        "issue": "#34",
        "original": {
            "path": ORIGINAL.relative_to(ROOT).as_posix(),
            "canonical_blob_sha256": original_digest,
        },
        "evidence_lock": {
            "path": EVIDENCE_LOCK.relative_to(ROOT).as_posix(),
            "narration_text_sha256": _evidence_lock_digest(),
        },
        "spoken_script": {
            "path": SPOKEN_SCRIPT.relative_to(ROOT).as_posix(),
            "working_tree_sha256": spoken_working,
            "canonical_blob_sha256": spoken_canonical,
            "display_text_sha256": hashlib.sha256(
                script.full_text().encode("utf-8")
            ).hexdigest(),
            "segment_display_sha256": {
                spec.id: hashlib.sha256(spec.text.encode("utf-8")).hexdigest()
                for spec in script.segments
            },
        },
        "sample": {
            "segments": list(script.sample_segment_ids),
            "original_paragraphs": list(script.sample_original_paragraphs),
            "target_duration_s": list(script.target_duration_s),
        },
        "lexicon": {
            "language": lexicon.language,
            "version": lexicon.version,
            "fingerprint_component": lexicon.fingerprint_component(),
        },
        "synthesis": versions,
        "mechanical_checks": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="write narration-version-map.json (tracked)")
    parser.add_argument("--json", action="store_true",
                        help="print the map instead of the summary")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if not ORIGINAL.is_file():
        print(f"[FAIL] original narration missing: {ORIGINAL}", file=sys.stderr)
        return 2
    if not SPOKEN_SCRIPT.is_file():
        print(f"[FAIL] spoken script missing: {SPOKEN_SCRIPT}", file=sys.stderr)
        return 2

    original_text = ORIGINAL.read_text(encoding="utf-8")
    script = load_spoken_script(SPOKEN_SCRIPT)
    try:
        report = verify_script(
            script,
            original_text=original_text,
            canonical_original_digest=canonical_blob_sha256(ORIGINAL),
            evidence_lock_digest=_evidence_lock_digest(),
        )
    except SpokenScriptError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    version_map = _version_map(script, report)
    if args.write:
        VERSION_MAP.write_text(
            json.dumps(version_map, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"wrote {VERSION_MAP.relative_to(ROOT).as_posix()}")
    if args.json:
        print(json.dumps(version_map, indent=2, ensure_ascii=False))
        return 0

    print("=== SPOKEN SCRIPT VERIFIED ===")
    print(f"  original digest  : {version_map['original']['canonical_blob_sha256'][:16]}...")
    print(
        f"  spoken digest    : {version_map['spoken_script']['working_tree_sha256'][:16]}..."
    )
    for name, entry in version_map["synthesis"].items():
        print(
            f"  synthesis {name:14s}: {entry['synthesis_sha256'][:16]}... "
            f"({entry['synthesis_characters']} chars)"
        )
    print("  mechanically checked: " + "; ".join(report["mechanically_checked"]))
    print("  NOT proven : " + "; ".join(report["not_proven_by_this_check"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
