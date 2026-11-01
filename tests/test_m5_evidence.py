"""Evidence layer: a claim is only as good as the bytes it points at.

These tests cover the two refusals that matter more than the happy path:

- an artifact whose permission does not allow citation cannot back a claim,
  even when the quote is present;
- a claim whose quote no longer occurs in the artifact is an assertion, not
  evidence, and `verify()` says so instead of passing quietly.

They also cover the M5 stage guards (asset hash drift, undeclared asset, unknown
claim, duplicated line) and the SRT→ASS timestamp format, which is what decides
whether a burned subtitle actually appears on the frame it was written for.

Everything here is offline: no ffmpeg, no network, no provider.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.evidence import (  # noqa: E402
    CLAIM_SCHEMA,
    ClaimLedger,
    ClaimLedgerError,
    SourceArtifact,
    SourceArtifactError,
    build_artifacts,
)
import assemble_easel  # noqa: E402
import m5_production  # noqa: E402

WORKROOT = ROOT / ".verify-tmp" / "m5-tests"


def _tmpdir() -> Path:
    WORKROOT.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=WORKROOT))


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _ledger(claims: List[dict]) -> ClaimLedger:
    return ClaimLedger.from_payload({"schema": CLAIM_SCHEMA, "claims": claims})


def _raises(exc, fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except exc as error:
        return str(error)
    raise AssertionError(f"expected {exc.__name__} from {getattr(fn, '__name__', fn)}")


# --- artifacts ---------------------------------------------------------------


def test_artifact_hashes_bytes_and_records_permission() -> None:
    work = _tmpdir()
    source = _write(work / "note.md", "Easel is pinned at v0.2.1.\n")
    artifact = SourceArtifact.from_path(
        id="note", source_type="repo_doc", title="note", path=source,
        repo_root=ROOT, permission="CREATED_BY_OWNER",
    )
    assert artifact.evidence_capable is True
    assert artifact.bytes == source.stat().st_size
    assert len(artifact.sha256) == 64
    assert artifact.path.endswith("note.md")
    assert artifact.text(ROOT) == "Easel is pinned at v0.2.1.\n"
    print("[ok] 1. an owned artifact is hashed and marked evidence-capable")


def test_permission_none_is_not_evidence_capable() -> None:
    work = _tmpdir()
    source = _write(work / "stock.md", "some footage\n")
    artifact = SourceArtifact.from_path(
        id="stock", source_type="stock", title="stock", path=source,
        repo_root=ROOT, permission="NONE",
    )
    assert artifact.evidence_capable is False, "NONE must never back a claim"
    print("[ok] 2. permission NONE is hashed but cannot back a claim")


def test_artifact_outside_the_repository_is_refused() -> None:
    work = _tmpdir()
    source = _write(work / "outside.md", "x")
    outside = ROOT.parent / "definitely-not-inside-the-repo.md"
    outside.write_text("x", encoding="utf-8")
    try:
        message = _raises(
            SourceArtifactError, SourceArtifact.from_path,
            id="out", source_type="repo_doc", title="out", path=outside,
            repo_root=work, permission="OWNED",
        )
        assert "outside the repository" in message
    finally:
        outside.unlink(missing_ok=True)
    assert source.exists()
    print("[ok] 3. a source outside the repository is refused")


def test_missing_file_and_unknown_permission_are_refused() -> None:
    work = _tmpdir()
    _raises(
        SourceArtifactError, SourceArtifact.from_path,
        id="gone", source_type="repo_doc", title="gone", path=work / "gone.md",
        repo_root=ROOT, permission="OWNED",
    )
    real = _write(work / "real.md", "x")
    _raises(
        SourceArtifactError, SourceArtifact.from_path,
        id="bad", source_type="repo_doc", title="bad", path=real,
        repo_root=ROOT, permission="MAYBE",
    )
    print("[ok] 4. a missing file and an unknown permission are both refused")


def test_verify_bytes_detects_a_single_byte_change() -> None:
    work = _tmpdir()
    source = _write(work / "note.md", "abcdef\n")
    artifact = SourceArtifact.from_path(
        id="note", source_type="repo_doc", title="note", path=source,
        repo_root=ROOT, permission="OWNED",
    )
    assert artifact.verify_bytes(ROOT) is True
    source.write_text("abcdef!\n", encoding="utf-8")
    assert artifact.verify_bytes(ROOT) is False, "one extra byte must invalidate the artifact"
    print("[ok] 5. verify_bytes notices a one-byte change")


def test_build_artifacts_rejects_duplicates_and_incomplete_refs() -> None:
    work = _tmpdir()
    source = _write(work / "a.md", "a\n")
    ref = {"id": "a", "type": "repo_doc", "title": "a",
           "path": str(source.relative_to(ROOT)), "permission": "OWNED"}
    built = build_artifacts([ref], repo_root=ROOT)
    assert set(built) == {"a"}
    message = _raises(SourceArtifactError, build_artifacts, [ref, ref], repo_root=ROOT)
    assert "duplicate" in message
    incomplete = {k: v for k, v in ref.items() if k != "permission"}
    message = _raises(SourceArtifactError, build_artifacts, [incomplete], repo_root=ROOT)
    assert "missing" in message.lower() or "misses" in message.lower()
    print("[ok] 6. duplicate ids and incomplete source refs are refused")


# --- claims ------------------------------------------------------------------


def test_valid_claim_verifies_with_a_verbatim_quote() -> None:
    work = _tmpdir()
    source = _write(work / "rules.md", "**No auto-upgrade.** Upstream upgrades require Founder approval.")
    artifacts = build_artifacts(
        [{"id": "rules", "type": "repo_doc", "title": "rules",
          "path": str(source.relative_to(ROOT)), "permission": "CREATED_BY_OWNER"}],
        repo_root=ROOT,
    )
    ledger = _ledger([{"id": "no_upgrade", "text": "no auto upgrade",
                       "artifacts": ["rules"], "quotes": ["No auto-upgrade."]}])
    assert ledger.verify(artifacts, ROOT) == []
    print("[ok] 7. a claim with a verbatim quote verifies clean")


def test_claim_without_a_matching_quote_is_reported() -> None:
    work = _tmpdir()
    source = _write(work / "rules.md", "nothing about upgrades here")
    artifacts = build_artifacts(
        [{"id": "rules", "type": "repo_doc", "title": "rules",
          "path": str(source.relative_to(ROOT)), "permission": "OWNED"}],
        repo_root=ROOT,
    )
    ledger = _ledger([{"id": "no_upgrade", "text": "no auto upgrade",
                       "artifacts": ["rules"], "quotes": ["No auto-upgrade."]}])
    problems = ledger.verify(artifacts, ROOT)
    assert any("no quote occurs" in p for p in problems), problems
    print("[ok] 8. a claim whose quote is absent is reported, not accepted")


def test_claim_cannot_cite_a_non_evidence_artifact() -> None:
    work = _tmpdir()
    source = _write(work / "stock.md", "No auto-upgrade.")
    artifacts = build_artifacts(
        [{"id": "stock", "type": "stock", "title": "stock",
          "path": str(source.relative_to(ROOT)), "permission": "NONE"}],
        repo_root=ROOT,
    )
    ledger = _ledger([{"id": "c", "text": "t", "artifacts": ["stock"], "quotes": ["No auto-upgrade."]}])
    problems = ledger.verify(artifacts, ROOT)
    assert any("cannot back a claim" in p for p in problems), problems
    print("[ok] 9. permission NONE is refused even when the quote matches")


def test_claim_citing_unknown_or_changed_artifacts_is_reported() -> None:
    work = _tmpdir()
    source = _write(work / "rules.md", "upgrade needs approval")
    artifacts = build_artifacts(
        [{"id": "rules", "type": "repo_doc", "title": "rules",
          "path": str(source.relative_to(ROOT)), "permission": "OWNED"}],
        repo_root=ROOT,
    )
    ledger = _ledger([{"id": "c", "text": "t", "artifacts": ["ghost"], "quotes": ["approval"]}])
    assert any("unknown artifact" in p for p in ledger.verify(artifacts, ROOT))

    source.write_text("changed after the artifact was built", encoding="utf-8")
    ledger = _ledger([{"id": "c", "text": "t", "artifacts": ["rules"], "quotes": ["approval"]}])
    problems = ledger.verify(artifacts, ROOT)
    assert any("bytes changed" in p for p in problems), problems
    print("[ok] 10. unknown artifacts and post-hoc edits are both reported")


def test_malformed_ledgers_are_refused() -> None:
    _raises(ClaimLedgerError, ClaimLedger.from_payload, {"schema": "wrong", "claims": []})
    _raises(ClaimLedgerError, _ledger, [{"id": "a", "text": "", "artifacts": ["x"]}])
    _raises(ClaimLedgerError, _ledger, [{"id": "a", "text": "t", "artifacts": []}])
    _raises(ClaimLedgerError, _ledger, [
        {"id": "a", "text": "t", "artifacts": ["x"]},
        {"id": "a", "text": "u", "artifacts": ["y"]},
    ])
    print("[ok] 11. wrong schema, empty text, no artifact and duplicate ids are refused")


def test_require_used_names_claims_the_script_never_cites() -> None:
    ledger = _ledger([
        {"id": "used", "text": "t", "artifacts": ["x"], "quotes": ["q"]},
        {"id": "forgotten", "text": "t", "artifacts": ["x"], "quotes": ["q"]},
    ])
    assert ledger.require_used({"used"}) == ["forgotten"]
    assert ledger.require_used({"used", "forgotten"}) == []
    print("[ok] 12. a claim the script never cites is named")


# --- M5 stage guards ---------------------------------------------------------


def _project() -> Path:
    work = _tmpdir()
    _write(work / "sources" / "assets.json", json.dumps({"schema": "contentops.m5-assets/v1", "assets": []}))
    return work


def test_stage_assets_refuses_hash_drift() -> None:
    work = _project()
    asset = _write(work / "card.png", "not really a png")
    manifest = {"schema": "contentops.m5-assets/v1", "assets": [{
        "id": "card", "repo_path": str(asset.relative_to(ROOT)),
        "sha256": "0" * 64, "type": "REAL_SCREENSHOT", "permission": "CREATED_BY_OWNER",
    }]}
    _write(work / "sources" / "assets.json", json.dumps(manifest))
    message = _raises(m5_production.M5Blocked, m5_production.stage_assets, work)
    assert "sha256" in message
    print("[ok] 13. an asset whose bytes drifted is refused before it is used")


def test_stage_assets_refuses_a_path_outside_the_repository() -> None:
    work = _project()
    manifest = {"schema": "contentops.m5-assets/v1", "assets": [{
        "id": "card", "repo_path": "../outside.png",
        "sha256": "0" * 64, "type": "REAL_SCREENSHOT", "permission": "CREATED_BY_OWNER",
    }]}
    _write(work / "sources" / "assets.json", json.dumps(manifest))
    message = _raises(m5_production.M5Blocked, m5_production.stage_assets, work)
    assert "escapes the repository" in message
    print("[ok] 14. an asset path outside the repository is refused")


def _script_project(lines: List[dict], claims: List[dict]) -> Path:
    work = _project()
    _write(work / "script" / "script.json",
           json.dumps({"schema": m5_production.SCRIPT_SCHEMA, "lines": lines}))
    _write(work / "script" / "claims.json",
           json.dumps({"schema": "contentops.claim-ledger/v1", "claims": claims}))
    return work


def test_stage_script_refuses_unknown_claim_and_undeclared_asset() -> None:
    work = _script_project(
        [{"id": "l1", "claim": "ghost", "narration": "n", "caption": "c", "asset_id": "card"}],
        [{"id": "real", "text": "t", "artifacts": ["a"], "quotes": ["q"]}],
    )
    ledger = _ledger([{"id": "real", "text": "t", "artifacts": ["a"], "quotes": ["q"]}])
    message = _raises(m5_production.M5Blocked, m5_production.stage_script, work, ledger, {})
    assert "unknown claims" in message

    work = _script_project(
        [{"id": "l1", "claim": "real", "narration": "n", "caption": "c", "asset_id": "ghost"}],
        [{"id": "real", "text": "t", "artifacts": ["a"], "quotes": ["q"]}],
    )
    message = _raises(m5_production.M5Blocked, m5_production.stage_script, work, ledger, {})
    assert "not in sources/assets.json" in message
    print("[ok] 15. an unknown claim and an undeclared asset are both refused")


def test_stage_script_refuses_duplicate_ids_and_empty_narration() -> None:
    ledger = _ledger([{"id": "real", "text": "t", "artifacts": ["a"], "quotes": ["q"]}])
    assets = {"card": {"repo_path": "scripts/qc_video.py", "type": "REAL_SCREENSHOT"}}
    work = _script_project(
        [{"id": "l1", "claim": "real", "narration": "n", "caption": "c", "asset_id": "card"},
         {"id": "l1", "claim": "real", "narration": "n", "caption": "c", "asset_id": "card"}],
        [{"id": "real", "text": "t", "artifacts": ["a"], "quotes": ["q"]}],
    )
    _raises(m5_production.M5Blocked, m5_production.stage_script, work, ledger, assets)

    work = _script_project(
        [{"id": "l1", "claim": "real", "narration": "   ", "caption": "c", "asset_id": "card"}],
        [{"id": "real", "text": "t", "artifacts": ["a"], "quotes": ["q"]}],
    )
    message = _raises(m5_production.M5Blocked, m5_production.stage_script, work, ledger, assets)
    assert "narration is empty" in message
    print("[ok] 16. duplicate line ids and empty narration are refused")


def test_stage_subtitles_refuses_poor_coverage() -> None:
    work = _project()
    script = {"lines": [{"id": "l1", "caption": "一"},
                        {"id": "l2", "caption": "二"}]}
    narration = {"duration_s": 100.0,
                 "lines": [{"start": 0.0, "duration": 1.0},
                           {"start": 1.0, "duration": 1.0}]}
    message = _raises(m5_production.M5Blocked, m5_production.stage_subtitles, work, script, narration)
    assert "coverage" in message
    print("[ok] 17. subtitle coverage below 0.8 blocks the run")


# --- subtitle timing ---------------------------------------------------------

def test_ass_timestamps_are_centiseconds_and_match_the_srt() -> None:
    work = _tmpdir()
    srt = _write(
        work / "default.srt",
        "1\n00:00:00,000 --> 00:00:05,830\n甲\n\n"
        "2\n00:00:06,110 --> 00:00:10,860\n乙\n",
    )
    ass = work / "default.ass"
    assemble_easel._srt_to_ass(srt, ass, 1080, 1920, "Noto Sans CJK SC", 54, 160)
    dialogues = [line for line in ass.read_text(encoding="utf-8").splitlines()
                 if line.startswith("Dialogue:")]
    assert len(dialogues) == 2, dialogues
    # libass reads a 3-digit fraction as centiseconds*10, which stretched every
    # cue and made neighbours overlap. Two digits, always.
    for line in dialogues:
        start, end = line.split(",")[1:3]
        for stamp in (start, end):
            assert len(stamp.rsplit(".", 1)[-1]) == 2, f"not centiseconds: {stamp}"
    assert dialogues[0].split(",")[2] == "0:00:05.83"
    assert dialogues[1].split(",")[1] == "0:00:06.11"
    print("[ok] 18. ASS timestamps are centiseconds and round-trip the SRT times")


TESTS = [
    test_artifact_hashes_bytes_and_records_permission,
    test_permission_none_is_not_evidence_capable,
    test_artifact_outside_the_repository_is_refused,
    test_missing_file_and_unknown_permission_are_refused,
    test_verify_bytes_detects_a_single_byte_change,
    test_build_artifacts_rejects_duplicates_and_incomplete_refs,
    test_valid_claim_verifies_with_a_verbatim_quote,
    test_claim_without_a_matching_quote_is_reported,
    test_claim_cannot_cite_a_non_evidence_artifact,
    test_claim_citing_unknown_or_changed_artifacts_is_reported,
    test_malformed_ledgers_are_refused,
    test_require_used_names_claims_the_script_never_cites,
    test_stage_assets_refuses_hash_drift,
    test_stage_assets_refuses_a_path_outside_the_repository,
    test_stage_script_refuses_unknown_claim_and_undeclared_asset,
    test_stage_script_refuses_duplicate_ids_and_empty_narration,
    test_stage_subtitles_refuses_poor_coverage,
    test_ass_timestamps_are_centiseconds_and_match_the_srt,
]


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
    print(f"All {len(TESTS)} M5 evidence tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
