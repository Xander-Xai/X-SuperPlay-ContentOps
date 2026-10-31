"""M5 -> media-use automation boundary. Offline synthetic fixtures, no providers."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT / "src", ROOT / "scripts"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import m5_production as m5  # noqa: E402

TESTS = []


def check(fn):
    TESTS.append(fn)
    return fn


def project_and_config():
    location = ROOT / ".verify-tmp" / "m5-media-use-workflow"
    location.mkdir(parents=True, exist_ok=True)
    project = Path(tempfile.mkdtemp(dir=location))
    (project / "assets").mkdir()
    (project / "sources").mkdir()
    (project / "script").mkdir()
    (project / "sources" / "assets.json").write_text(
        json.dumps({"schema": "contentops.m5-assets/v1", "assets": []}), encoding="utf-8"
    )
    image = project / "assets" / "support.png"
    image.write_bytes(b"synthetic-offline-fixture-only")
    sha = hashlib.sha256(image.read_bytes()).hexdigest()
    config = {
        "media_use": {
            "enabled": True,
            "mode": "local-only",
            "requests": [{
                "id": "support_visual", "kind": "image", "intent": "local support image",
                "license": "OWNED-FIXTURE", "rights_reviewed": True,
                "attribution": "synthetic test asset",
            }],
        },
        "source_refs": [],
        "id": "test-media-use",
    }
    return project, config, sha


class FakeMediaAdapter:
    """Only the adapter boundary is faked; the M5 stage implementation is real."""

    def __init__(self, digest: str):
        self.digest = digest
        self.calls = []
        self.importable = True
        self.verified = True

    def resolve(self, kind, intent, *, project_dir):
        self.calls.append(("resolve", kind, intent, str(project_dir)))
        return SimpleNamespace(
            importable=self.importable, source="project-candidate",
            record={"type": kind, "path": "assets/support.png", "sha256": self.digest},
        )

    def import_record(self, record, *, project_dir, kind, license, attribution):
        self.calls.append(("import", kind, license))
        return SimpleNamespace(
            logical_path="project://assets/support.png",
            asset_id="media-use-image-" + self.digest[:12],
            sha256=self.digest, receipt_ref="support.png.media-use-receipt.json",
        )

    def verify(self, *, project_dir, relative_path, expected_sha256):
        self.calls.append(("verify", relative_path, expected_sha256))
        good = hashlib.sha256((project_dir / relative_path).read_bytes()).hexdigest()
        return SimpleNamespace(ok=self.verified and good == expected_sha256)


def refused(fn):
    try:
        fn()
    except m5.M5Blocked:
        return
    raise AssertionError("expected M5Blocked")


@check
def disabled_keeps_existing_workflow_unchanged():
    project, config, _ = project_and_config()
    assert m5.stage_media_use(project, {}, adapter=None)["state"] == "DISABLED"
    assert m5.stage_media_use(project, {"media_use": {"enabled": False}})["state"] == "DISABLED"
    assert not (project / "receipts" / "media-use-stage.json").exists()


@check
def successful_stage_resolves_imports_verifies_and_feeds_assets():
    project, config, digest = project_and_config()
    adapter = FakeMediaAdapter(digest)
    result = m5.stage_media_use(project, config, adapter=adapter)
    assert [call[0] for call in adapter.calls] == ["resolve", "import", "verify"]
    assert result["state"] == "OK" and result["count"] == 1
    assets = m5.stage_assets(project, extra_assets=result["assets"])
    assert assets["support_visual"]["verified_sha256"] == digest
    assert assets["support_visual"]["type"] == "LICENSED_EXTERNAL"
    assert assets["support_visual"]["evidence_capable"] is False
    receipt = json.loads((project / "receipts" / "media-use-stage.json").read_text(encoding="utf-8"))
    assert receipt["network"] is False and receipt["paid"] is False
    assert receipt["results"][0]["provider_call"] is False


@check
def declared_assets_are_reused_before_any_adapter_call():
    project, config, digest = project_and_config()
    manifest = {"schema": "contentops.m5-assets/v1", "assets": [{
        "id": "support_visual", "repo_path": (project / "assets" / "support.png").relative_to(ROOT).as_posix(),
        "sha256": digest, "type": "REAL_SCREENSHOT", "permission": "CREATED_BY_OWNER",
    }]}
    (project / "sources" / "assets.json").write_text(json.dumps(manifest), encoding="utf-8")
    adapter = FakeMediaAdapter(digest)
    result = m5.stage_media_use(project, config, adapter=adapter)
    assert result["count"] == 0 and not adapter.calls
    assert result["assets"] == {}
    assert m5.stage_assets(project, extra_assets=result["assets"])["support_visual"]["type"] == "REAL_SCREENSHOT"


@check
def missing_license_or_rights_blocks_before_adapter_call():
    for key, value in (("license", ""), ("rights_reviewed", False), ("intent", "")):
        project, config, digest = project_and_config()
        config["media_use"]["requests"][0][key] = value
        adapter = FakeMediaAdapter(digest)
        refused(lambda: m5.stage_media_use(project, config, adapter=adapter))
        assert not adapter.calls


@check
def no_network_paid_or_cross_project_flags_can_enter_the_stage():
    for flag in ("allow_network", "allow_paid", "allow_cross_project_reuse"):
        project, config, digest = project_and_config()
        config["media_use"][flag] = True
        adapter = FakeMediaAdapter(digest)
        refused(lambda: m5.stage_media_use(project, config, adapter=adapter))
        assert not adapter.calls
    project, config, digest = project_and_config()
    config["media_use"]["mode"] = "network"
    refused(lambda: m5.stage_media_use(project, config, adapter=FakeMediaAdapter(digest)))


@check
def unimportable_and_tampered_bytes_block():
    project, config, digest = project_and_config()
    adapter = FakeMediaAdapter(digest)
    adapter.importable = False
    refused(lambda: m5.stage_media_use(project, config, adapter=adapter))
    project, config, digest = project_and_config()
    adapter = FakeMediaAdapter(digest)
    adapter.verified = False
    refused(lambda: m5.stage_media_use(project, config, adapter=adapter))


@check
def duplicate_ids_or_unsupported_audio_refuse():
    project, config, digest = project_and_config()
    config["media_use"]["requests"].append(dict(config["media_use"]["requests"][0]))
    refused(lambda: m5.stage_media_use(project, config, adapter=FakeMediaAdapter(digest)))
    project, config, digest = project_and_config()
    config["media_use"]["requests"][0]["kind"] = "sfx"
    refused(lambda: m5.stage_media_use(project, config, adapter=FakeMediaAdapter(digest)))


@check
def build_automatically_uses_the_stage_without_a_manual_adapter_cli():
    project, config, digest = project_and_config()
    (project / "script" / "claims.json").write_text(
        json.dumps({"schema": "contentops.claim-ledger/v1", "claims": []}), encoding="utf-8")
    (project / "script" / "script.json").write_text(
        json.dumps({"schema": "contentops.m5-script/v1",
                    "lines": [{"id": "s1", "asset_id": "support_visual",
                               "narration": "synthetic narration", "caption": "example"}]}),
        encoding="utf-8",
    )
    adapter = FakeMediaAdapter(digest)
    originals = (m5._read_yaml, m5.stage_narration, m5.stage_subtitles, m5.stage_storyboard)
    try:
        m5._read_yaml = lambda path: config
        m5.stage_narration = lambda project, script: {"duration_s": 1, "engine": "fixture", "lines": []}
        m5.stage_subtitles = lambda project, script, narration: {"cues": 0}
        m5.stage_storyboard = lambda project, config, script, narration, subtitles, assets: {
            "shots": len(assets), "asset_ids": list(assets),
        }
        result = m5.build(project, skip_compose=True, media_adapter=adapter)
    finally:
        m5._read_yaml, m5.stage_narration, m5.stage_subtitles, m5.stage_storyboard = originals
    assert result["stages"]["media_use"]["state"] == "OK"
    assert result["stages"]["assets"]["count"] == 1
    assert result["stages"]["storyboard"]["shots"] == 1
    assert [call[0] for call in adapter.calls] == ["resolve", "import", "verify"]
    assert result["production_ready"] is False


def main():
    errors = []
    for fn in TESTS:
        try:
            fn()
            print("[PASS]", fn.__name__)
        except Exception as exc:
            print("[FAIL]", fn.__name__, repr(exc))
            errors.append(fn.__name__)
    print(f"Passed {len(TESTS) - len(errors)}/{len(TESTS)} M5 media-use workflow tests")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
