"""Cache reuse must never skip the M5 registration boundary.

Run: python tests/test_animation_cache_integrity.py

The fixture builds the four registration artifacts a successful clip render
leaves behind. Each test deletes or tampers one of them and asserts the audit
either asks for a safe repair or blocks — it must never report a clean reuse
over a broken or escalated registration.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import animation_render as ar  # noqa: E402
from contentops.media import animation_backend as ab  # noqa: E402

ASSET = "clip-integrity"
PLACEMENT = "p-integrity"
SHA = "a" * 64
FP = "b" * 64
TEMPLATE = "title_card"
LOGICAL = f"project://assets/generated/remotion/{ASSET}.mp4"
REPO_PATH = f"projects/_local/fixture/assets/generated/remotion/{ASSET}.mp4"


def _expected() -> dict:
    return {
        "asset_id": ASSET,
        "placement_id": PLACEMENT,
        "fingerprint": FP,
        "sha256": SHA,
        "template": TEMPLATE,
        "logical": LOGICAL,
        "repo_path": REPO_PATH,
        "receipt_name": f"animation-{ASSET}.json",
    }


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fixture(project: Path) -> dict:
    """Write all four consistent registration artifacts; return their paths."""
    expected = _expected()
    receipt = {
        "schema": ar._CACHE_RECEIPT_SCHEMA,
        "asset_id": ASSET,
        "placement_id": PLACEMENT,
        "template": TEMPLATE,
        "sha256": SHA,
        "fingerprint": FP,
        "output_path": LOGICAL,
        "account_id": ab.ACCOUNT_FUTURE,
    }
    receipt.update(ar._SAFE_RECEIPT_FIELDS)
    sources = {"assets": [{"id": ASSET, "type": "GENERATED_VIDEO", "sha256": SHA,
                           "repo_path": REPO_PATH, "generated": True,
                           "evidence_capable": False, "usage_scope": "VISUAL_SUPPORT only"}]}
    script = {"assets": {ASSET: {"path": LOGICAL, "sha256": SHA,
                                 "generated": True, "evidence_use": "VISUAL_SUPPORT"}}}
    manifest = {"assets": [{"asset_id": ASSET, "path": LOGICAL, "sha256": SHA,
                            "fingerprint": FP, "generated": True, "evidence_capable": False,
                            "evidence_use": "VISUAL_SUPPORT", "technical_status": "PASS_TECHNICAL",
                            "human_review": "PENDING_FOUNDER_REVIEW", "production_ready": False}]}
    paths = {
        "receipt": project / "receipts" / expected["receipt_name"],
        "sources": project / "sources" / "assets.json",
        "script": project / "script" / "assets.json",
        "manifest": project / "work" / "m45" / "remotion-media-manifest.json",
    }
    for path, payload in ((paths["receipt"], receipt), (paths["sources"], sources),
                          (paths["script"], script), (paths["manifest"], manifest)):
        _write(path, payload)
    return paths


def _patch(path: Path, fn) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fn(payload)
    _write(path, payload)


def test_consistent_fixture_needs_no_repair():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        _fixture(project)
        result = ar._audit_cache_registration(project, _expected())
        assert result["state"] == "CONSISTENT", result
        assert not result["missing"] and not result["stale"] and not result["violations"]


def test_deleting_any_single_artifact_is_repairable():
    for name in ("receipt", "sources", "script", "manifest"):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            paths = _fixture(project)
            paths[name].unlink()
            result = ar._audit_cache_registration(project, _expected())
            assert result["state"] == "REPAIRABLE", (name, result)
            assert result["missing"], (name, result)
            assert not result["violations"], (name, result)


def test_deleting_only_the_row_is_repairable():
    cases = (
        ("sources", lambda p: p["assets"].clear()),
        ("script", lambda p: p["assets"].clear()),
        ("manifest", lambda p: p["assets"].clear()),
    )
    for name, mutate in cases:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            paths = _fixture(project)
            _patch(paths[name], mutate)
            result = ar._audit_cache_registration(project, _expected())
            assert result["state"] == "REPAIRABLE", (name, result)
            assert not result["violations"], (name, result)


def test_stale_identity_fields_are_repairable():
    cases = (
        ("receipt", lambda p: p.update({"sha256": "c" * 64})),
        ("receipt", lambda p: p.update({"fingerprint": "d" * 64})),
        ("sources", lambda p: p["assets"][0].update({"sha256": "c" * 64})),
        ("script", lambda p: p["assets"][ASSET].update({"sha256": "c" * 64})),
        ("manifest", lambda p: p["assets"][0].update({"fingerprint": "d" * 64})),
    )
    for name, mutate in cases:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            paths = _fixture(project)
            _patch(paths[name], mutate)
            result = ar._audit_cache_registration(project, _expected())
            assert result["state"] == "REPAIRABLE", (name, result)
            assert result["stale"], (name, result)
            assert not result["violations"], (name, result)


def test_tampering_any_evidence_flag_blocks_even_with_intact_mp4():
    """A cached MP4 is not a licence to escalate evidence/human/publish facts."""
    cases = (
        ("receipt", lambda p: p.update({"evidence_capable": True})),
        ("receipt", lambda p: p.update({"production_ready": True})),
        ("receipt", lambda p: p.update({"publish_authorized": True})),
        ("receipt", lambda p: p.update({"human_review": "APPROVED"})),
        ("receipt", lambda p: p.update({"counts_as_real_recording": True})),
        ("sources", lambda p: p["assets"][0].update({"evidence_capable": True})),
        ("sources", lambda p: p["assets"][0].update({"type": "REAL"})),
        ("script", lambda p: p["assets"][ASSET].update({"evidence_use": "EVIDENCE"})),
        ("manifest", lambda p: p["assets"][0].update({"evidence_capable": True})),
        ("manifest", lambda p: p["assets"][0].update({"production_ready": True})),
        ("manifest", lambda p: p["assets"][0].update({"human_review": "APPROVED"})),
    )
    for name, mutate in cases:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            paths = _fixture(project)
            _patch(paths[name], mutate)
            result = ar._audit_cache_registration(project, _expected())
            assert result["state"] == "BLOCKED", (name, result)
            assert result["violations"], (name, result)


def test_render_cache_hit_reports_reused_only_after_consistent_audit():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        _fixture(project)
        spec = project / "motion"
        spec.mkdir()
        (spec / "spec.json").write_text(json.dumps({
            "backend": "remotion", "template": TEMPLATE, "shot_type": "title_card",
            "duration_s": 3,
            "props": {"conflict": "冲突", "stakes": "结果"},
        }, ensure_ascii=False), encoding="utf-8")
        cached = {"sha256": SHA, "receipt_name": f"animation-{ASSET}.json",
                  "receipt": {"source_spec": "project://motion/spec.json"}}
        out = []
        with mock.patch.object(ar, "_trusted_cache_hit", return_value=cached), \
             mock.patch.object(ar, "clip_fingerprint", return_value=FP), \
             mock.patch.object(ar, "relative_label", return_value=REPO_PATH), \
             mock.patch.object(ar, "skill_readiness", return_value=True), \
             mock.patch.object(ar, "environment_probe", return_value={"node": True}), \
             mock.patch.object(ar, "preflight", return_value={"state": "READY"}), \
             mock.patch.object(ar, "_emit", side_effect=lambda p, c: out.append((p, c)) or c):
            code = ar.render(project, Path("motion/spec.json"), placement_id=PLACEMENT,
                             asset_id=ASSET, account_id=ab.ACCOUNT_FUTURE, purpose="test")
        assert code == 0 and out[0][0]["execution"]["state"] == "REUSED", out
        assert out[0][0]["execution"]["registration_repaired"] is False, out
        assert out[0][0]["registration"]["state"] == "CONSISTENT", out


def test_render_cache_hit_blocks_on_tampered_receipt():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        paths = _fixture(project)
        _patch(paths["receipt"], lambda p: p.update({"production_ready": True}))
        spec = project / "motion"
        spec.mkdir()
        (spec / "spec.json").write_text(json.dumps({
            "backend": "remotion", "template": TEMPLATE, "shot_type": "title_card",
            "duration_s": 3, "props": {"conflict": "冲突", "stakes": "结果"},
        }, ensure_ascii=False), encoding="utf-8")
        cached = {"sha256": SHA, "receipt_name": f"animation-{ASSET}.json", "receipt": {}}
        out = []
        with mock.patch.object(ar, "_trusted_cache_hit", return_value=cached), \
             mock.patch.object(ar, "skill_readiness", return_value=True), \
             mock.patch.object(ar, "environment_probe", return_value={"node": True}), \
             mock.patch.object(ar, "preflight", return_value={"state": "READY"}), \
             mock.patch.object(ar, "_emit", side_effect=lambda p, c: out.append((p, c)) or c):
            code = ar.render(project, Path("motion/spec.json"), placement_id=PLACEMENT,
                             asset_id=ASSET, account_id=ab.ACCOUNT_FUTURE, purpose="test")
        assert code == 1, out
        assert out[0][0]["execution"]["state"] == "BLOCKED", out
        assert out[0][0]["decision"]["code"] == "REGISTRATION_BOUNDARY", out


def test_render_cache_hit_repairs_missing_row_and_says_so():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        paths = _fixture(project)
        _patch(paths["script"], lambda p: p["assets"].clear())
        spec = project / "motion"
        spec.mkdir()
        (spec / "spec.json").write_text(json.dumps({
            "backend": "remotion", "template": TEMPLATE, "shot_type": "title_card",
            "duration_s": 3, "props": {"conflict": "冲突", "stakes": "结果"},
        }, ensure_ascii=False), encoding="utf-8")
        cached = {"sha256": SHA, "receipt_name": f"animation-{ASSET}.json",
                  "receipt": {"source_spec": "project://motion/spec.json"}}

        def fake_register(**kwargs):
            # Re-run the fixture repair idempotently, as register_generated_clip
            # would: restore both inventory rows flagged by the audit.
            _write(paths["script"], {"assets": {ASSET: {
                "path": LOGICAL, "sha256": SHA,
                "generated": True, "evidence_use": "VISUAL_SUPPORT"}}})
            return {"repo_path": REPO_PATH, "generated": True, "evidence_capable": False}

        out = []
        with mock.patch.object(ar, "_trusted_cache_hit", return_value=cached), \
             mock.patch.object(ar, "clip_fingerprint", return_value=FP), \
             mock.patch.object(ar, "relative_label", return_value=REPO_PATH), \
             mock.patch.object(ar, "skill_readiness", return_value=True), \
             mock.patch.object(ar, "environment_probe", return_value={"node": True}), \
             mock.patch.object(ar, "preflight", return_value={"state": "READY"}), \
             mock.patch.object(ar, "register_generated_clip", side_effect=fake_register), \
             mock.patch.object(ar, "_ffprobe", return_value={"codec_name": "h264"}), \
             mock.patch.object(ar, "_emit", side_effect=lambda p, c: out.append((p, c)) or c):
            code = ar.render(project, Path("motion/spec.json"), placement_id=PLACEMENT,
                             asset_id=ASSET, account_id=ab.ACCOUNT_FUTURE, purpose="test")
        assert code == 0 and out[0][0]["execution"]["state"] == "REUSED", out
        assert out[0][0]["execution"]["registration_repaired"] is True, out
        assert "script.asset_row" in out[0][0]["registration"]["repaired_rows"], out
        # The rebuilt canonical receipt must still carry the safe governance facts.
        rebuilt = json.loads((project / "receipts" / f"animation-{ASSET}.json").read_text(encoding="utf-8"))
        assert rebuilt["production_ready"] is False and rebuilt["publish_authorized"] is False
        assert rebuilt["evidence_capable"] is False and rebuilt["fingerprint"] == FP


def test_source_digests_collect_sha256_hidden_in_nested_props():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        spec = project / "spec.json"
        spec.write_text("{}", encoding="utf-8")
        nested = "e" * 64
        raw = {"props": {"nodes": ["Query", {"source_sha256": nested.upper()}],
                         "box": {"evidence": [nested]}}}
        digests = ar._source_digests(spec, raw, None)
        assert nested in digests, digests
        assert digests.count(nested) == 1, "duplicates must collapse in clip_fingerprint"


def test_template_digest_tracks_lockfile_and_nested_modules():
    from unittest import mock
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "src").mkdir()
        _write(root / "package.json", {"version": "1"})
        _write(root / "package-lock.json", {"lock": "v1"})
        _write(root / "tsconfig.json", {"compilerOptions": {}})
        comp = root / "src" / "index.tsx"
        comp.write_text("export default 1;", encoding="utf-8")
        with mock.patch.object(ar, "REMOTION_ROOT", root):
            base = ar._template_digest()
            comp.write_text("export default 2;", encoding="utf-8")
            assert ar._template_digest() != base, "component edit must invalidate"
            comp.write_text("export default 1;", encoding="utf-8")
            _write(root / "package-lock.json", {"lock": "v2"})
            assert ar._template_digest() != base, "lockfile edit must invalidate"
            _write(root / "package-lock.json", {"lock": "v1"})
            nested = root / "src" / "components"
            nested.mkdir()
            (nested / "shared.tsx").write_text("export const x = 1;", encoding="utf-8")
            assert ar._template_digest() != base, "nested module must be tracked"


def test_repair_that_does_not_restore_consistency_blocks():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        paths = _fixture(project)
        (paths["sources"]).unlink()
        expected = _expected()
        with mock.patch.object(ar, "register_generated_clip", return_value={}), \
             mock.patch.object(ar, "_ffprobe", return_value={"codec_name": "h264"}):
            result = ar._repair_cache_registration(
                project=project, final=project / "clip.mp4",
                sidecar_payload={"source_spec": "project://motion/spec.json"},
                expected=expected, account_id=ab.ACCOUNT_FUTURE, placement_id=PLACEMENT,
                purpose="test", gate={"code": "TEST_PURPOSE"}, probe={"codec_name": "h264"},
            )
        assert result["state"] == "REPAIRABLE" and "sources/assets.json" in result["missing"], result


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
            import traceback
            traceback.print_exc()
    total = len(TESTS)
    print(f"{total - failures}/{total} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
