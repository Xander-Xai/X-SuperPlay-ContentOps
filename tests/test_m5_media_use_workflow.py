"""M5 -> media-use automation boundary. Offline synthetic fixtures, no providers."""
from __future__ import annotations

import hashlib
import json
import re
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


def rights_record(project, asset_id, *, license_id="OWNED-BY-OPERATOR",
                  source_url="OWNED", attribution="synthetic test asset",
                  synthetic=False, reviewed_by="fixture-reviewer",
                  reviewed_at="2026-10-31"):
    """Write a review sidecar and return the matching request rights block."""
    relative = f"assets/{asset_id}.rights.json"
    record = {
        "schema": "contentops.media-rights-review/v1",
        "license_id": license_id,
        "source_url": source_url,
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "attribution": attribution,
        "synthetic": synthetic,
    }
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record), encoding="utf-8")
    return {
        "schema": "contentops.media-rights/v1",
        "license_id": license_id,
        "source_url": source_url,
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "review_evidence": relative,
        "attribution": attribution,
        "synthetic": synthetic,
    }


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
                "rights": rights_record(project, "support_visual"),
            }],
        },
        "source_refs": [],
        "id": "test-media-use",
    }
    return project, config, sha


class FakeMediaAdapter:
    """Only the adapter boundary is faked; the M5 stage implementation is real."""

    PATHS = {
        "image": "assets/support.png",
        "icon": "assets/support.png",
        "logo": "assets/support.png",
        "bgm": "assets/bed.mp3",
        "sfx": ".media/audio/sfx/sfx_001.mp3",
    }

    def __init__(self, digest: str):
        self.digest = digest
        self.calls = []
        self.importable = True
        self.verified = True
        self.sfx_override = None

    def _path(self, kind):
        if kind == "sfx" and self.sfx_override:
            return self.sfx_override
        return self.PATHS[kind]

    def adopt(self, *, project_dir):
        self.calls.append(("adopt", str(project_dir)))
        return [{"type": "image", "path": "assets/support.png"}]

    def resolve(self, kind, intent, *, project_dir):
        self.calls.append(("resolve", kind, intent, str(project_dir)))
        relative = self._path(kind)
        file = Path(project_dir) / relative
        digest = hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else self.digest
        return SimpleNamespace(
            importable=self.importable, source="project-candidate",
            record={"type": kind, "path": relative, "sha256": digest},
        )

    def import_record(self, record, *, project_dir, kind, license, attribution):
        self.calls.append(("import", kind, license))
        relative = record["path"]
        digest = hashlib.sha256((Path(project_dir) / relative).read_bytes()).hexdigest()
        return SimpleNamespace(
            logical_path="project://" + relative,
            asset_id="media-use-%s-%s" % (kind, digest[:12]),
            sha256=digest, receipt_ref=relative.rsplit("/", 1)[-1] + ".receipt.json",
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
    assert [call[0] for call in adapter.calls] == ["adopt", "resolve", "import", "verify"]
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
    for mutate in (
        lambda req: req.pop("rights", None),
        lambda req: req.update({"intent": ""}),
        lambda req: req["rights"].update({"review_evidence": ""}),
    ):
        project, config, digest = project_and_config()
        mutate(config["media_use"]["requests"][0])
        adapter = FakeMediaAdapter(digest)
        refused(lambda: m5.stage_media_use(project, config, adapter=adapter))
        assert not adapter.calls


@check
def a_bare_rights_reviewed_flag_is_not_evidence():
    project, config, digest = project_and_config()
    config["media_use"]["requests"][0].pop("rights", None)
    config["media_use"]["requests"][0]["rights_reviewed"] = True
    adapter = FakeMediaAdapter(digest)
    refused(lambda: m5.stage_media_use(project, config, adapter=adapter))
    assert not adapter.calls


@check
def software_and_noncommercial_licences_cannot_license_media():
    for license_id in ("Apache-2.0", "MIT", "AGPL-3.0", "CC-BY-NC-4.0", "UNKNOWN-1.0"):
        project, config, digest = project_and_config()
        config["media_use"]["requests"][0]["rights"].update({"license_id": license_id})
        adapter = FakeMediaAdapter(digest)
        refused(lambda: m5.stage_media_use(project, config, adapter=adapter))
        assert not adapter.calls


@check
def the_review_record_must_match_the_request_and_exist():
    for field, value in (("source_url", "https://example.com/other"),
                         ("attribution", "different credit"),
                         ("reviewed_at", "2026-10-30")):
        project, config, digest = project_and_config()
        config["media_use"]["requests"][0]["rights"].update({field: value})
        refused(lambda: m5.stage_media_use(project, config, adapter=FakeMediaAdapter(digest)))
    project, config, digest = project_and_config()
    (project / "assets" / "support_visual.rights.json").unlink()
    refused(lambda: m5.stage_media_use(project, config, adapter=FakeMediaAdapter(digest)))


@check
def a_third_party_asset_needs_an_http_source_and_attribution():
    project, config, digest = project_and_config()
    config["media_use"]["requests"][0]["rights"] = rights_record(
        project, "support_visual", license_id="Pixabay-Content-License",
        source_url="pixabay", attribution="Pixabay item",
    )
    refused(lambda: m5.stage_media_use(project, config, adapter=FakeMediaAdapter(digest)))
    project, config, digest = project_and_config()
    config["media_use"]["requests"][0]["rights"] = rights_record(
        project, "support_visual", license_id="CC-BY-4.0",
        source_url="https://example.com/asset", attribution="",
    )
    refused(lambda: m5.stage_media_use(project, config, adapter=FakeMediaAdapter(digest)))


@check
def synthetic_assets_are_never_evidence():
    project, config, digest = audio_config()
    adapter = FakeMediaAdapter(digest)
    result = m5.stage_media_use(project, config, adapter=adapter)
    assert result["audio"]["bgm"]["rights"]["synthetic"] is True
    assert result["audio"]["bgm"]["rights"]["evidence_capable"] is False
    receipt = json.loads((project / "receipts" / "media-use-stage.json").read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in receipt["results"]}
    assert by_id["bed"]["rights"]["synthetic"] is True
    assert by_id["bed"]["evidence_capable"] is False
    assert by_id["support_visual"]["evidence_capable"] is False


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
        m5.stage_storyboard = lambda project, config, script, narration, subtitles, assets, media_audio=None: {
            "shots": len(assets), "asset_ids": list(assets), "storyboard": {},
        }
        result = m5.build(project, skip_compose=True, media_adapter=adapter)
    finally:
        m5._read_yaml, m5.stage_narration, m5.stage_subtitles, m5.stage_storyboard = originals
    assert result["stages"]["media_use"]["state"] == "OK"
    assert result["stages"]["assets"]["count"] == 1
    assert result["stages"]["storyboard"]["shots"] == 1
    assert [call[0] for call in adapter.calls] == ["adopt", "resolve", "import", "verify"]
    assert result["production_ready"] is False


def audio_config():
    """A project with one visual, one local BGM and one bundled SFX request."""
    project, config, digest = project_and_config()
    (project / "assets" / "bed.mp3").write_bytes(b"synthetic-bgm-fixture")
    sfx = project / ".media" / "audio" / "sfx" / "sfx_001.mp3"
    sfx.parent.mkdir(parents=True)
    sfx.write_bytes(b"synthetic-sfx-fixture")
    config["media_use"]["requests"] += [
        {"id": "bed", "kind": "bgm", "intent": "calm bed", "volume": 0.2,
         "rights": rights_record(
             project, "bed", license_id="OWNED-GENERATED-LOCAL",
             source_url="GENERATED", attribution="deterministic tone bed",
             synthetic=True,
         )},
        {"id": "click", "kind": "sfx", "intent": "soft click",
         "at": 1.5, "volume": 0.6,
         "rights": rights_record(
             project, "click", license_id="Pixabay-Content-License",
             source_url="https://pixabay.com/sound-effects/",
             attribution="bundled media-use SFX (Pixabay Content License)",
         )},
    ]
    return project, config, digest


def one_line_script():
    return {"lines": [{"id": "s1", "asset_id": "support_visual",
                       "narration": "synthetic narration", "caption": "example",
                       "claim": None}]}


@check
def audio_is_imported_and_placed_without_becoming_a_visual_asset():
    project, config, digest = audio_config()
    adapter = FakeMediaAdapter(digest)
    result = m5.stage_media_use(project, config, adapter=adapter)
    assert set(result["assets"]) == {"support_visual"}
    assert result["assets"]["support_visual"]["evidence_capable"] is False
    assert result["audio"]["bgm"]["volume"] == 0.2
    assert result["audio"]["sfx"][0]["at"] == 1.5
    assert result["count"] == 3
    narration = {"duration_s": 10.0, "lines": [{"start": 0.0, "duration": 10.0}]}
    storyboard = m5.stage_storyboard(
        project, config, one_line_script(), narration, {},
        result["assets"], media_audio=result["audio"],
    )["storyboard"]
    assert storyboard["bgm"].endswith("assets/bed.mp3")
    assert storyboard["bgm_volume"] == 0.2
    assert storyboard["sfx"][0]["at"] == 1.5
    receipt = json.loads((project / "receipts" / "media-use-stage.json").read_text(encoding="utf-8"))
    assert {row["kind"] for row in receipt["results"]} == {"image", "bgm", "sfx"}


@check
def audio_placement_and_volume_are_validated_before_import():
    for change in ({"at": None}, {"at": -1}, {"volume": 0}, {"volume": 1.5},
                   {"volume": "loud"}):
        project, config, digest = audio_config()
        config["media_use"]["requests"][2].update(change)
        adapter = FakeMediaAdapter(digest)
        refused(lambda: m5.stage_media_use(project, config, adapter=adapter))
        assert not adapter.calls


@check
def a_second_bgm_request_is_refused():
    project, config, digest = audio_config()
    config["media_use"]["requests"].append(dict(config["media_use"]["requests"][1]))
    config["media_use"]["requests"][-1]["id"] = "bed_two"
    refused(lambda: m5.stage_media_use(project, config, adapter=FakeMediaAdapter(digest)))


@check
def sfx_beyond_the_timeline_or_duplicated_is_refused():
    project, config, digest = audio_config()
    adapter = FakeMediaAdapter(digest)
    result = m5.stage_media_use(project, config, adapter=adapter)
    narration = {"duration_s": 1.0, "lines": [{"start": 0.0, "duration": 1.0}]}
    refused(lambda: m5.stage_storyboard(
        project, config, one_line_script(), narration, {},
        result["assets"], media_audio=result["audio"]))
    result["audio"]["sfx"].append(dict(result["audio"]["sfx"][0]))
    refused(lambda: m5.stage_storyboard(
        project, config, one_line_script(),
        {"duration_s": 10.0, "lines": [{"start": 0.0, "duration": 10.0}]}, {},
        result["assets"], media_audio=result["audio"]))


@check
def disabled_media_use_leaves_the_storyboard_audio_unchanged():
    project, config, digest = audio_config()
    result = m5.stage_media_use(project, {"media_use": {"enabled": False}},
                                adapter=None)
    assert result["audio"] == {"bgm": None, "sfx": []}
    narration = {"duration_s": 10.0, "lines": [{"start": 0.0, "duration": 10.0}]}
    storyboard = m5.stage_storyboard(
        project, config, one_line_script(), narration, {},
        {"support_visual": {"type": "REAL_SCREENSHOT",
                            "repo_path": "projects/fixture/assets/support.png"}},
        media_audio=result["audio"],
    )["storyboard"]
    assert "bgm" not in storyboard and "sfx" not in storyboard


@check
def an_audio_request_cannot_be_declared_in_the_visual_manifest():
    project, config, digest = audio_config()
    manifest = {"schema": "contentops.m5-assets/v1", "assets": [{
        "id": "bed", "repo_path": "projects/fixture/assets/bed.mp3",
        "sha256": digest, "type": "REAL_SCREENSHOT", "permission": "CREATED_BY_OWNER",
    }]}
    (project / "sources" / "assets.json").write_text(json.dumps(manifest), encoding="utf-8")
    refused(lambda: m5.stage_media_use(project, config, adapter=FakeMediaAdapter(digest)))


@check
def committed_example_receipts_carry_no_machine_paths():
    skip = {".media", "final", "work", "assets"}
    for name in ("m5-media-use", "m5-easel-pin"):
        root = ROOT / "projects" / name
        for path in root.rglob("*"):
            if not path.is_file() or skip & set(path.relative_to(root).parts):
                continue
            if path.suffix not in {".json", ".yaml", ".md"}:
                continue
            text = path.read_text(encoding="utf-8")
            machine = re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/c/Users|/d/Projects", text)
            assert not machine, f"machine path {machine.group(0)!r} in {path}"


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
