#!/usr/bin/env python3
"""Validate the v3 creator chain and emit its version map. Issue #34.

The v3 chain has four artifacts that must not be confused:

1. **fact script** -- `projects/easel-review/script/narration.txt` (locked);
2. **creator script** -- `script/creator-script.json` (editorial derivative);
3. **director plan** -- `script/narration-plan.json` (internal metadata + the
   conservative mapping to emotion/speed/pauses/groups);
4. **synthesis texts** -- what the provider would actually receive: the mapped
   texts after the pronunciation lexicon is applied (markers preserved).

This script checks every mechanical invariant of (2) against (1) and the
evidence lock, and of (3) against (2), then (with `--write`) records the SHA256
mapping of all four -- original, creator, plan, and the concrete synthesis texts
for the D (single request) and E (director groups) candidates.

No provider interaction exists here. Exit: 0 = verified, 1 = verification
failed, 2 = input missing.
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

from contentops.media.creator_script import (  # noqa: E402
    CreatorScriptError,
    load_creator_script,
    verify_creator_script,
)
from contentops.media.lexicon import default_zh_lexicon  # noqa: E402
from contentops.media.minimax_native_tts import normalize_paragraph_newlines  # noqa: E402
from contentops.media.narration_director import (  # noqa: E402
    NarrationDirectorError,
    load_director_plan,
    mapped_groups,
    verify_director_plan,
)
from contentops.media.native_rounds import canonical_blob_sha256  # noqa: E402

FACT_SCRIPT = ROOT / "projects/easel-review/script/narration.txt"
EVIDENCE_LOCK = ROOT / "projects/easel-enhanced-golden/evidence/evidence-lock.json"
CREATOR_SCRIPT = ROOT / "projects/easel-enhanced-golden/script/creator-script.json"
DIRECTOR_PLAN = ROOT / "projects/easel-enhanced-golden/script/narration-plan.json"
VERSION_MAP = ROOT / "projects/easel-enhanced-golden/script/creator-version-map.json"


def synthesis_text(text: str, lexicon) -> str:
    """The exact provider-facing text: lexicon applied, markers preserved."""
    return normalize_paragraph_newlines(lexicon.spoken_text(text))


def _evidence_lock_digest() -> str:
    if not EVIDENCE_LOCK.is_file():
        raise SystemExit(f"evidence lock missing: {EVIDENCE_LOCK}")
    payload = json.loads(EVIDENCE_LOCK.read_text(encoding="utf-8"))
    return str(payload.get("narration_text_sha256") or "")


def load_verified_plan() -> dict:
    """Load the whole v3 chain and verify it, or raise SystemExit.

    Shared with the D/E/F sample runner so the experiment can only ever run
    exactly the texts this verifier admitted.
    """
    for path in (FACT_SCRIPT, CREATOR_SCRIPT, DIRECTOR_PLAN):
        if not path.is_file():
            raise SystemExit(f"required artifact missing: {path}")
    original_text = FACT_SCRIPT.read_text(encoding="utf-8")
    creator = load_creator_script(CREATOR_SCRIPT)
    plan = load_director_plan(DIRECTOR_PLAN)
    canonical = canonical_blob_sha256(FACT_SCRIPT)
    try:
        creator_report = verify_creator_script(
            creator,
            original_text=original_text,
            canonical_original_digest=canonical,
            evidence_lock_digest=_evidence_lock_digest(),
        )
    except CreatorScriptError as exc:
        raise SystemExit(f"[creator script] {exc}")
    creator_working = hashlib.sha256(CREATOR_SCRIPT.read_bytes()).hexdigest()
    try:
        director_report = verify_director_plan(
            plan, creator, expected_creator_digest=creator_working
        )
    except NarrationDirectorError as exc:
        raise SystemExit(f"[director plan] {exc}")
    return {
        "creator": creator,
        "plan": plan,
        "creator_report": creator_report,
        "director_report": director_report,
        "original_text": original_text,
        "digests": {
            "fact_script_canonical_blob_sha256": canonical,
            "creator_script_working_tree_sha256": creator_working,
            "creator_script_canonical_blob_sha256": canonical_blob_sha256(CREATOR_SCRIPT),
            "director_plan_working_tree_sha256": hashlib.sha256(
                DIRECTOR_PLAN.read_bytes()
            ).hexdigest(),
        },
    }


def _entry(text: str, lexicon, *, units=None) -> dict:
    synth = synthesis_text(text, lexicon)
    return {
        "display_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "synthesis_sha256": hashlib.sha256(synth.encode("utf-8")).hexdigest(),
        "synthesis_characters": len(synth),
        "units": list(units or []),
    }


def _version_map(result: dict) -> dict:
    lexicon = default_zh_lexicon()
    creator = result["creator"]
    plan = result["plan"]
    sample_units = plan.sample_unit_ids
    d_text = "\n".join(creator.unit(uid).text for uid in sample_units)
    sample_groups = mapped_groups(plan, creator, section="sample.groups")
    full_groups = mapped_groups(plan, creator, section="groups")
    return {
        "schema": "contentops.creator-version-map/v1",
        "issue": "#34",
        "fact_script": {
            "path": FACT_SCRIPT.relative_to(ROOT).as_posix(),
            "canonical_blob_sha256": result["digests"]["fact_script_canonical_blob_sha256"],
        },
        "creator_script": {
            "path": CREATOR_SCRIPT.relative_to(ROOT).as_posix(),
            "working_tree_sha256": result["digests"]["creator_script_working_tree_sha256"],
            "canonical_blob_sha256": result["digests"]["creator_script_canonical_blob_sha256"],
            "unit_display_sha256": {
                unit.id: hashlib.sha256(unit.text.encode("utf-8")).hexdigest()
                for unit in creator.units
            },
        },
        "director_plan": {
            "path": DIRECTOR_PLAN.relative_to(ROOT).as_posix(),
            "working_tree_sha256": result["digests"]["director_plan_working_tree_sha256"],
            "model": plan.model,
            "groups": [group.id for group in plan.groups],
            "sample_groups": [group.id for group in plan.sample_groups],
        },
        "lexicon": {
            "language": lexicon.language,
            "version": lexicon.version,
            "fingerprint_component": lexicon.fingerprint_component(),
        },
        "synthesis": {
            "candidate_D_single_request": _entry(d_text, lexicon, units=sample_units),
            "candidate_E_director_groups": {
                group.id: _entry(group.text, lexicon, units=group.units)
                for group in sample_groups
            },
            "planned_full_groups_not_executed": {
                group.id: _entry(group.text, lexicon, units=group.units)
                for group in full_groups
            },
        },
        "mechanical_checks": {
            "creator_script": result["creator_report"],
            "director_plan": {
                key: value
                for key, value in result["director_report"].items()
                if key != "mapped_full_groups"
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="write creator-version-map.json (tracked)")
    parser.add_argument("--json", action="store_true",
                        help="print the map instead of the summary")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    result = load_verified_plan()
    version_map = _version_map(result)
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

    director = result["director_report"]
    print("=== CREATOR SCRIPT + DIRECTOR PLAN VERIFIED ===")
    print(f"  fact script  : {version_map['fact_script']['canonical_blob_sha256'][:16]}...")
    print(f"  creator      : {version_map['creator_script']['working_tree_sha256'][:16]}...")
    print(f"  plan         : {version_map['director_plan']['working_tree_sha256'][:16]}...")
    print(f"  units/groups : {director['units']}/{director['groups']} core groups")
    print(f"  explicit emotions: {director['explicit_emotions']}")
    print(f"  sample groups: {director['sample_groups']} "
          f"(est {director['sample_estimated_seconds']} s)")
    for name, entry in version_map["synthesis"].items():
        if isinstance(entry, dict) and "synthesis_sha256" in entry:
            print(f"  synthesis {name:34s}: {entry['synthesis_sha256'][:16]}...")
        else:
            for group_id, group_entry in entry.items():
                print(f"  synthesis {name}.{group_id:17s}: "
                      f"{group_entry['synthesis_sha256'][:16]}...")
    print("  NOT proven : " + "; ".join(director["not_proven_by_this_check"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
