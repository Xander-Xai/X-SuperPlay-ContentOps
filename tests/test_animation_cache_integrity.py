"""Cache reuse must never skip the M5 registration boundary.

Run: python tests/test_animation_cache_integrity.py

The fixture builds the four registration artifacts a successful clip render
leaves behind. Each test deletes or tampers one of them and asserts the audit
either asks for a safe repair or blocks — it must never report a clean reuse
over a broken or escalated registration.

The multi-shot section exercises the shared manifest contract directly: two
and three clips registering into one ``work/m45/remotion-media-manifest.json``
must merge by asset_id, never overwrite each other, and keep every governance
fact intact through reuse, repair and re-render.
"""

from __future__ import annotations

import hashlib
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
from contentops.media.generated_clip import register_generated_clip  # noqa: E402
from contentops.media.quality_gate import MediaManifest  # noqa: E402

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


# --- Multi-shot shared manifest --------------------------------------------
# register_generated_clip writes the one M5 asset list per backend. Two or
# three clips must merge into it by asset_id: a sibling clip's envelope, gate
# state and timeline slot survive every later registration, so a cache-hit
# repair for one clip can never invalidate another clip.

CLIPS = {
    "a": {"asset_id": "clip-a", "placement_id": "beat-01", "fp": "1" * 64},
    "b": {"asset_id": "clip-b", "placement_id": "beat-02", "fp": "2" * 64},
    "c": {"asset_id": "clip-c", "placement_id": "beat-03", "fp": "3" * 64},
}


def _mp4_bytes(asset_id: str) -> bytes:
    return f"mp4-bytes-{asset_id}".encode("utf-8") * 16


def _sha_of(asset_id: str) -> str:
    return hashlib.sha256(_mp4_bytes(asset_id)).hexdigest()


def _register_clip(project: Path, clip: dict) -> dict:
    """Register one clip through the real writer, with the files it validates.

    Writes the dummy MP4 bytes, the receipt sidecar the gate reads, and the
    canonical receipt the audit reads — exactly the artifacts a real render
    leaves behind. Returns the registration plus the facts for audit calls.
    """
    sha = _sha_of(clip["asset_id"])
    final = project / "assets" / "generated" / "remotion" / f"{clip['asset_id']}.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(_mp4_bytes(clip["asset_id"]))
    sidecar = {
        "schema": "contentops.video-receipt/v1",
        "asset_id": clip["asset_id"],
        "placement_id": clip["placement_id"],
        "template": TEMPLATE,
        "fingerprint": clip["fp"],
        "output_sha256": sha,
        "generated": True,
        "evidence_capable": False,
        "technical_qc": {"approved": True, "reasons": []},
        "human_review": "PENDING_FOUNDER_REVIEW",
        "production_ready": False,
        "publish_authorized": False,
    }
    _write(final.parent / f"{clip['asset_id']}.mp4.receipt.json", sidecar)
    registration = register_generated_clip(
        project=project, repo_root=ROOT, asset_id=clip["asset_id"],
        placement_id=clip["placement_id"], output=final, sha256=sha,
        fingerprint=clip["fp"], backend="remotion",
        receipt_name=f"{clip['asset_id']}.mp4.receipt.json",
    )
    logical = registration["logical"]
    receipt = {
        "schema": ar._CACHE_RECEIPT_SCHEMA,
        "asset_id": clip["asset_id"],
        "placement_id": clip["placement_id"],
        "template": TEMPLATE,
        "sha256": sha,
        "fingerprint": clip["fp"],
        "output_path": logical,
        "account_id": ab.ACCOUNT_FUTURE,
    }
    receipt.update(ar._SAFE_RECEIPT_FIELDS)
    _write(project / "receipts" / f"animation-{clip['asset_id']}.json", receipt)
    expected = {
        "asset_id": clip["asset_id"],
        "placement_id": clip["placement_id"],
        "fingerprint": clip["fp"],
        "sha256": sha,
        "template": TEMPLATE,
        "logical": logical,
        "repo_path": registration["repo_path"],
        "receipt_name": f"animation-{clip['asset_id']}.json",
    }
    return {"registration": registration, "expected": expected}


def _audit_clip(project: Path, facts: dict) -> dict:
    return ar._audit_cache_registration(project, facts["expected"])


def _manifest_ids(project: Path) -> list:
    manifest = json.loads(
        (project / "work" / "m45" / "remotion-media-manifest.json").read_text(encoding="utf-8"))
    return [row["asset_id"] for row in manifest.get("assets") or []]


def test_multishot_abab_keeps_both_registrations_consistent():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        facts = {key: _register_clip(project, clip) for key, clip in CLIPS.items()
                 if key in ("a", "b")}
        # A -> B -> A -> B, exactly the reuse-and-repair loop the audit drives.
        for key in ("a", "b", "a", "b"):
            _register_clip(project, CLIPS[key])
            ids = _manifest_ids(project)
            assert sorted(ids) == ["clip-a", "clip-b"], (key, ids)
            for other in ("a", "b"):
                result = _audit_clip(project, facts[other])
                assert result["state"] == "CONSISTENT", (key, other, result)
        manifest = MediaManifest.load(
            project / "work" / "m45" / "remotion-media-manifest.json")
        slots = {p.placement_id: p.active_asset_id for p in manifest.timeline}
        assert slots == {"beat-01": "clip-a", "beat-02": "clip-b"}, slots


def test_multishot_abc_each_clip_has_its_own_timeline_slot():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        facts = {}
        for key, clip in CLIPS.items():
            facts[key] = _register_clip(project, clip)
        manifest = MediaManifest.load(
            project / "work" / "m45" / "remotion-media-manifest.json")
        assert sorted(manifest.gate_states) == ["clip-a", "clip-b", "clip-c"], manifest.gate_states
        slots = {p.placement_id: p.active_asset_id for p in manifest.timeline}
        assert slots == {"beat-01": "clip-a", "beat-02": "clip-b", "beat-03": "clip-c"}, slots
        # Composition reads exactly one active asset per placement, and the
        # timeline must resolve without the duplicated-slot error.
        assert len(manifest.active_visual_assets()) == 3
        for key in CLIPS:
            result = _audit_clip(project, facts[key])
            assert result["state"] == "CONSISTENT", (key, result)


def test_reregistering_b_with_new_identity_does_not_stale_a():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        facts = {key: _register_clip(project, clip) for key, clip in CLIPS.items()
                 if key in ("a", "b")}
        # B re-renders: new bytes, new fingerprint — a genuinely new clip.
        reedited = dict(CLIPS["b"])
        reedited["fp"] = "9" * 64
        facts_b2 = _register_clip(project, reedited)
        manifest = MediaManifest.load(
            project / "work" / "m45" / "remotion-media-manifest.json")
        old_a = manifest.envelope_for("clip-a")
        assert old_a.sha256 == facts["a"]["expected"]["sha256"], old_a
        assert old_a.fingerprint == CLIPS["a"]["fp"], old_a
        new_b = manifest.envelope_for("clip-b")
        assert new_b.fingerprint == "9" * 64 and new_b.sha256 == facts_b2["expected"]["sha256"]
        # A's cache identity is untouched, so its reuse stays a clean hit.
        assert _audit_clip(project, facts["a"])["state"] == "CONSISTENT"
        assert _audit_clip(project, facts_b2)["state"] == "CONSISTENT"


def _b_rows(project: Path) -> dict:
    """Clip B's own rows in every shared artifact, for before/after comparison."""
    manifest = json.loads(
        (project / "work" / "m45" / "remotion-media-manifest.json").read_text(encoding="utf-8"))
    sources = json.loads((project / "sources" / "assets.json").read_text(encoding="utf-8"))
    script = json.loads((project / "script" / "assets.json").read_text(encoding="utf-8"))
    return {
        "envelope": next(r for r in manifest["assets"] if r["asset_id"] == "clip-b"),
        "gate_state": manifest["counts"]["by_gate_state"]["clip-b"],
        "timeline": [p for p in manifest["timeline"] if p["active_asset_id"] == "clip-b"],
        "sources_row": next(r for r in sources["assets"] if r["id"] == "clip-b"),
        "script_row": script["assets"]["clip-b"],
    }


def test_repairing_a_keeps_b_and_its_records_intact():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        facts = {key: _register_clip(project, clip) for key, clip in CLIPS.items()
                 if key in ("a", "b")}
        b_receipt_before = (project / "receipts" / "animation-clip-b.json").read_bytes()
        b_rows_before = _b_rows(project)
        # Lose every A registration row the way a partial wipe would.
        (project / "receipts" / "animation-clip-a.json").unlink()
        for rel, mutate in (
            ("sources", lambda p: p.__setitem__("assets", [r for r in p["assets"] if r["id"] != "clip-a"])),
            ("script", lambda p: p["assets"].pop("clip-a")),
        ):
            path = {"sources": project / "sources" / "assets.json",
                    "script": project / "script" / "assets.json"}[rel]
            payload = json.loads(path.read_text(encoding="utf-8"))
            mutate(payload)
            _write(path, payload)
        manifest_path = project / "work" / "m45" / "remotion-media-manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["assets"] = [r for r in payload["assets"] if r["asset_id"] != "clip-a"]
        payload["counts"]["assets"] = len(payload["assets"])
        payload["counts"]["by_gate_state"].pop("clip-a")
        payload["timeline"] = [p for p in payload["timeline"] if p["active_asset_id"] != "clip-a"]
        payload["counts"]["placements"] = len(payload["timeline"])
        _write(manifest_path, payload)
        # The repair the render script runs: real register + real receipt rebuild.
        with mock.patch.object(ar, "_ffprobe", return_value={"codec_name": "h264"}):
            result = ar._repair_cache_registration(
                project=project, final=project / "assets" / "generated" / "remotion" / "clip-a.mp4",
                sidecar_payload={"source_spec": "project://spec.json"},
                expected=facts["a"]["expected"], account_id=ab.ACCOUNT_FUTURE,
                placement_id=CLIPS["a"]["placement_id"], purpose="test",
                gate={"code": "TEST_PURPOSE"}, probe={"codec_name": "h264"},
            )
        assert result["state"] == "CONSISTENT", result
        assert sorted(_manifest_ids(project)) == ["clip-a", "clip-b"]
        assert _audit_clip(project, facts["b"])["state"] == "CONSISTENT"
        b_rows_after = _b_rows(project)
        assert b_rows_after == b_rows_before, "repairing A must not rewrite any of B's rows"
        # The shared files legitimately gained A's rows back, but B's own
        # canonical receipt file is untouched byte for byte.
        assert (project / "receipts" / "animation-clip-b.json").read_bytes() == b_receipt_before


def test_evidence_escalation_still_blocks_after_merges():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        facts = {key: _register_clip(project, clip) for key, clip in CLIPS.items()
                 if key in ("a", "b")}
        manifest_path = project / "work" / "m45" / "remotion-media-manifest.json"
        _patch(manifest_path, lambda p: p["assets"][1].update({"production_ready": True}))
        sources_path = project / "sources" / "assets.json"
        _patch(sources_path, lambda p: p["assets"][1].update({"evidence_capable": True}))
        blocked = _audit_clip(project, facts["b"])
        assert blocked["state"] == "BLOCKED", blocked
        assert "m45.production_ready" in blocked["violations"], blocked
        assert "sources.evidence_capable" in blocked["violations"], blocked
        # A later registration merges around the violation without curing it:
        # the escalated rows stay exactly as they were, and stay blocked.
        _register_clip(project, CLIPS["a"])
        again = _audit_clip(project, facts["b"])
        assert again["state"] == "BLOCKED" and again["violations"], again
        assert _audit_clip(project, facts["a"])["state"] == "CONSISTENT"


def test_same_placement_yields_single_active_asset():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        first = dict(CLIPS["a"], placement_id="beat-shared")
        second = dict(CLIPS["b"], placement_id="beat-shared")
        facts_first = _register_clip(project, first)
        _register_clip(project, second)
        manifest = MediaManifest.load(
            project / "work" / "m45" / "remotion-media-manifest.json")
        slots = [p for p in manifest.timeline if p.placement_id == "beat-shared"]
        assert len(slots) == 1, manifest.timeline
        # Policy: earliest declared wins, so the first registration keeps the
        # slot and the second clip stays inventory-only until someone decides.
        assert slots[0].active_asset_id == "clip-a", slots[0]
        assert len(manifest.active_visual_assets()) == 1
        # Re-registering either clip never produces a second slot.
        _register_clip(project, second)
        _register_clip(project, first)
        manifest = MediaManifest.load(
            project / "work" / "m45" / "remotion-media-manifest.json")
        slots = [p for p in manifest.timeline if p.placement_id == "beat-shared"]
        assert len(slots) == 1 and slots[0].active_asset_id == "clip-a", slots
        assert sorted(_manifest_ids(project)) == ["clip-a", "clip-b"]
        assert _audit_clip(project, facts_first)["state"] == "CONSISTENT"


def test_registration_is_idempotent_byte_for_byte():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        manifest_path = project / "work" / "m45" / "remotion-media-manifest.json"
        _register_clip(project, CLIPS["a"])
        first = manifest_path.read_bytes()
        _register_clip(project, CLIPS["a"])
        assert manifest_path.read_bytes() == first, "same clip must rewrite identical bytes"
        _register_clip(project, CLIPS["b"])
        with_b = manifest_path.read_bytes()
        assert with_b != first
        _register_clip(project, CLIPS["a"])
        assert manifest_path.read_bytes() == with_b, "re-registering A must not disturb the merged manifest"


def test_merge_refuses_unreadable_or_inconsistent_manifests():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        manifest_path = project / "work" / "m45" / "remotion-media-manifest.json"
        # 1. Unparseable bytes: refuse loudly, never silently start a fresh
        #    manifest (that would delete the other clips' registrations).
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text("{not json", encoding="utf-8")
        try:
            _register_clip(project, CLIPS["a"])
            raise AssertionError("expected MEDIA_MANIFEST_UNREADABLE")
        except ValueError as exc:
            assert "MEDIA_MANIFEST_UNREADABLE" in str(exc), exc
        assert manifest_path.read_text(encoding="utf-8") == "{not json", "refusal must not rewrite"
        # 2. An asset without a recorded gate state cannot be carried over.
        _write(manifest_path, {"schema": "contentops.media-manifest/v1", "assets": [
            {"asset_id": "ghost", "modality": "VIDEO", "path": "project://ghost.mp4",
             "sha256": "0" * 64, "generated": True, "evidence_capable": False,
             "evidence_use": "VISUAL_SUPPORT", "technical_status": "PASS_TECHNICAL",
             "human_review": "PENDING_FOUNDER_REVIEW", "production_ready": False}],
            "counts": {"by_gate_state": {}}, "timeline": []})
        try:
            _register_clip(project, CLIPS["a"])
            raise AssertionError("expected MEDIA_MANIFEST_GATE_MISSING")
        except ValueError as exc:
            assert "MEDIA_MANIFEST_GATE_MISSING" in str(exc), exc
        # 3. Two different asset ids may not claim one output file.
        _write(manifest_path, {"schema": "contentops.media-manifest/v1", "assets": [
            {"asset_id": "twin", "modality": "VIDEO", "placement_id": "beat-01",
             "path": "project://assets/generated/remotion/clip-a.mp4",
             "sha256": "0" * 64, "generated": True, "evidence_capable": False,
             "evidence_use": "VISUAL_SUPPORT", "technical_status": "PASS_TECHNICAL",
             "human_review": "PENDING_FOUNDER_REVIEW", "production_ready": False}],
            "counts": {"by_gate_state": {"twin": "PENDING_HUMAN_REVIEW"}}, "timeline": []})
        try:
            _register_clip(project, CLIPS["a"])
            raise AssertionError("expected MEDIA_MANIFEST_PATH_COLLISION")
        except ValueError as exc:
            assert "MEDIA_MANIFEST_PATH_COLLISION" in str(exc), exc


def test_old_single_asset_manifest_upgrades_in_place():
    """A manifest written before the merge fix loads, merges and keeps its facts."""
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        facts = {key: _register_clip(project, clip) for key, clip in CLIPS.items()
                 if key in ("a", "b")}
        manifest_path = project / "work" / "m45" / "remotion-media-manifest.json"
        _patch(manifest_path, lambda p: (
            p["assets"].pop(0),  # pretend the old writer kept only clip-b
            p["timeline"].pop(0),
            p["counts"].update({"assets": 1, "placements": 1}),
            p["counts"]["by_gate_state"].pop("clip-a"),
            p["counts"]["by_modality"].pop("VIDEO") or p["counts"]["by_modality"].update({"VIDEO": 1}),
            p.update({"scheduling": {"seed": 7}, "narration": {"voice": "narrator-x"}}),
        ))
        assert _manifest_ids(project) == ["clip-b"]
        _register_clip(project, CLIPS["a"])
        manifest = MediaManifest.load(manifest_path)
        assert sorted(_manifest_ids(project)) == ["clip-a", "clip-b"]
        assert manifest.scheduling == {"seed": 7}, manifest.scheduling
        assert manifest.narration == {"voice": "narrator-x"}, manifest.narration
        assert {p.placement_id: p.active_asset_id for p in manifest.timeline} == {
            "beat-01": "clip-a", "beat-02": "clip-b"}
        for key in ("a", "b"):
            assert _audit_clip(project, facts[key])["state"] == "CONSISTENT", key


def test_render_cache_repair_blocked_when_manifest_unreadable():
    """A manifest the merge refuses turns the repair into BLOCKED, not success."""
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        facts = _register_clip(project, dict(CLIPS["a"], fp=FP))
        _register_clip(project, dict(CLIPS["b"], fp="2" * 64))
        (project / "work" / "m45" / "remotion-media-manifest.json").write_text(
            "{corrupt", encoding="utf-8")
        spec = project / "motion"
        spec.mkdir()
        (spec / "spec.json").write_text(json.dumps({
            "backend": "remotion", "template": TEMPLATE, "shot_type": "title_card",
            "duration_s": 3, "props": {"conflict": "冲突", "stakes": "结果"},
        }, ensure_ascii=False), encoding="utf-8")
        cached = {"sha256": facts["expected"]["sha256"],
                  "receipt_name": facts["expected"]["receipt_name"],
                  "receipt": {"source_spec": "project://motion/spec.json"}}
        out = []
        with mock.patch.object(ar, "_trusted_cache_hit", return_value=cached), \
             mock.patch.object(ar, "clip_fingerprint", return_value=FP), \
             mock.patch.object(ar, "relative_label", return_value=facts["expected"]["repo_path"]), \
             mock.patch.object(ar, "skill_readiness", return_value=True), \
             mock.patch.object(ar, "environment_probe", return_value={"node": True}), \
             mock.patch.object(ar, "preflight", return_value={"state": "READY"}), \
             mock.patch.object(ar, "_ffprobe", return_value={"codec_name": "h264"}), \
             mock.patch.object(ar, "_emit", side_effect=lambda p, c: out.append((p, c)) or c):
            code = ar.render(project, Path("motion/spec.json"), placement_id=CLIPS["a"]["placement_id"],
                             asset_id=CLIPS["a"]["asset_id"], account_id=ab.ACCOUNT_FUTURE,
                             purpose="test")
        assert code == 1, out
        payload = out[0][0]
        assert payload["execution"]["state"] == "BLOCKED", payload
        assert payload["decision"]["code"] == "REGISTRATION_REPAIR_FAILED", payload
        assert "MEDIA_MANIFEST_UNREADABLE" in str(payload["decision"].get("detail")), payload
        # The corrupt file is left untouched for a human, not overwritten.
        assert (project / "work" / "m45" / "remotion-media-manifest.json").read_text(
            encoding="utf-8") == "{corrupt"


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
