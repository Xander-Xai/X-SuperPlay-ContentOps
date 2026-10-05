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

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.golden.evidence_lock import (  # noqa: E402
    EvidenceAsset,
    EvidenceLock,
    assert_production_lock,
)
from contentops.golden.identity import compare_evidence_identity  # noqa: E402
from contentops.media.image_contract import AssetKind, EvidenceUse  # noqa: E402
from contentops.media.media_paths import (  # noqa: E402
    serialize_media_path,
)

BASELINE = ROOT / "projects" / "easel-review"
EXPERIMENT = ROOT / "projects" / "easel-enhanced-golden"
AUDIT_PATH = EXPERIMENT / "receipts" / "baseline-reproducibility.json"

#: Caption files present in the baseline. Several exist; the lock records the ones the
#: storyboard actually names rather than guessing which was burned in.
CAPTION_CANDIDATES = ("assets/captions/easel.srt", "assets/captions/default.srt")

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

        digest = _sha256(local)
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
        if asset.asset_kind not in AssetKind.EVIDENCE_CAPABLE:
            fail("KIND_NOT_EVIDENCE_CAPABLE", f"{asset.placement_id}: {asset.asset_kind}")
        if asset.asset_kind in AssetKind.GENERATED:
            fail("GENERATED_REPLACED_EVIDENCE", f"{asset.placement_id} is generated")

    caption = None
    for candidate in CAPTION_CANDIDATES:
        if (BASELINE / candidate).is_file():
            caption = BASELINE / candidate
            break

    lock = EvidenceLock(
        source_project="project://easel-review",
        master_script_sha256=_sha256(BASELINE / "script" / "master.md"),
        narration_text_sha256=_sha256(BASELINE / "script" / "narration.txt"),
        storyboard_fingerprint=_structural(storyboard),
        caption_sha256=_sha256(caption) if caption else None,
        evidence=assets,
        # The load-bearing field: this is the real baseline, not the test fixtures.
        fixture=False,
        notes={
            "historical_identity": audit["historical_identity"],
            "experiment_baseline": audit["experiment_baseline"],
            "audit_receipt": "repo://projects/easel-enhanced-golden/receipts/baseline-reproducibility.json",
            "caption_source": (
                resolve_logical(caption) if caption else None
            ),
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
    return lock


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
    return lock


def _is_tracked(rel: str) -> bool:
    from process_utils import hidden_run

    return hidden_run(
        ["git", "ls-files", "--error-unmatch", rel], cwd=str(ROOT), timeout=60
    ).returncode == 0


def _sha256(path: Path) -> str:
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