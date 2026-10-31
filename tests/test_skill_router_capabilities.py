from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import skill_route as sr  # noqa: E402


def _entry(**overrides):
    entry = {
        "id": "demo",
        "name": "demo",
        "discovery": {"root": "shared", "dir": "demo"},
        "canonical_path": "src/contentops/media/media_use_adapter.py",
        "license": {"status": "declared", "spdx": "Apache-2.0"},
        "rights": {"status": "verified", "verified": True, "evidence": "receipt"},
        "accounts": ["*"],
        "pipelines": ["M5"],
        "stages": ["media_use"],
        "provider": {"authorized": True, "network": False, "paid": False,
                     "cross_project_reuse": False},
        "runtime": {},
        "verification": {"status": "VERIFIED"},
        "execution": {"adapter": "src/x.py", "m5_stage": "media_use",
                      "authorizes_execution": False},
    }
    entry.update(overrides)
    return entry


def _registry(*entries):
    return {"schema": sr.REGISTRY_SCHEMA, "skills": list(entries)}


class MediaUseRegistrationTests(unittest.TestCase):
    def test_media_use_is_declared_in_the_committed_registry(self) -> None:
        data = sr.load_registry()
        self.assertTrue(data["readable"], data)
        entries = sr.registry_entries(data)
        self.assertEqual([entry["id"] for entry in entries], ["media-use"])

    def test_the_declaration_records_every_required_field(self) -> None:
        entry = sr.registry_entries()[0]
        for field in ("id", "name", "discovery", "source", "canonical_path",
                      "license", "rights", "accounts", "pipelines", "stages",
                      "contract", "provider", "runtime", "verification", "execution"):
            self.assertIn(field, entry, field)
        self.assertEqual(entry["source"]["version"], "0.8.222")
        self.assertTrue(entry["source"]["source_commit"])
        self.assertEqual(entry["canonical_path"],
                         "src/contentops/media/media_use_adapter.py")
        self.assertFalse(entry["execution"]["authorizes_execution"])
        self.assertFalse(entry["provider"]["network"])
        self.assertFalse(entry["provider"]["paid"])

    def test_the_declaration_points_at_code_that_exists(self) -> None:
        entry = sr.registry_entries()[0]
        self.assertTrue((ROOT / entry["canonical_path"]).is_file())
        self.assertTrue((ROOT / entry["runtime"]["baseline"]).is_file())
        self.assertTrue((ROOT / entry["rights"]["evidence"]).is_file())


class ResolutionVerdictTests(unittest.TestCase):
    def test_unknown_skill_is_blocked(self) -> None:
        result = sr.resolve_capability("__missing__", registry=_registry())
        self.assertEqual(result["verdict"], sr.VERDICT_BLOCKED)
        self.assertEqual(result["reason"], sr.REASON_UNKNOWN_SKILL)
        self.assertFalse(result["execution_authorized"])

    def test_duplicate_declaration_is_blocked(self) -> None:
        registry = _registry(_entry(), _entry())
        result = sr.resolve_capability("demo", registry=registry)
        self.assertEqual(result["reason"], sr.REASON_DUPLICATE_AMBIGUITY)

    def test_unverified_rights_are_blocked(self) -> None:
        registry = _registry(_entry(rights={"status": "unverified", "verified": False}))
        result = sr.resolve_capability("demo", registry=registry,
                                       discovery_ready=True, runtime_ready=True)
        self.assertEqual(result["reason"], sr.REASON_UNVERIFIED_RIGHTS)

    def test_a_restricted_licence_is_blocked_even_when_rights_claim_verified(self) -> None:
        registry = _registry(_entry(license={"status": "restricted", "spdx": "AGPL-3.0"}))
        result = sr.resolve_capability("demo", registry=registry,
                                       discovery_ready=True, runtime_ready=True)
        self.assertEqual(result["reason"], sr.REASON_UNVERIFIED_RIGHTS)

    def test_an_unauthorized_provider_is_blocked(self) -> None:
        registry = _registry(_entry(provider={"authorized": False, "network": False,
                                              "paid": False, "cross_project_reuse": False}))
        result = sr.resolve_capability("demo", registry=registry,
                                       discovery_ready=True, runtime_ready=True)
        self.assertEqual(result["reason"], sr.REASON_UNAUTHORIZED_PROVIDER)

    def test_a_declared_network_or_paid_path_is_blocked(self) -> None:
        for flag in ("network", "paid", "cross_project_reuse"):
            provider = {"authorized": True, "network": False, "paid": False,
                        "cross_project_reuse": False}
            provider[flag] = True
            result = sr.resolve_capability("demo", registry=_registry(_entry(provider=provider)),
                                           discovery_ready=True, runtime_ready=True)
            self.assertEqual(result["reason"], sr.REASON_UNAUTHORIZED_PROVIDER, flag)

    def test_a_missing_skill_directory_is_blocked(self) -> None:
        result = sr.resolve_capability("demo", registry=_registry(_entry()),
                                       discovery_ready=False, runtime_ready=True)
        self.assertEqual(result["reason"], sr.REASON_SKILL_NOT_INSTALLED)

    def test_a_missing_runtime_is_blocked(self) -> None:
        registry = _registry(_entry(runtime={
            "dependency": "hyperframes@0.8.222",
            "baseline": "runtime/media-use-runtime-baseline.json",
            "lock_env": "CONTENTOPS_MEDIA_USE_RUNTIME_LOCK",
        }))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONTENTOPS_MEDIA_USE_RUNTIME_LOCK", None)
            result = sr.resolve_capability("demo", registry=registry, discovery_ready=True)
        self.assertEqual(result["reason"], sr.REASON_MISSING_RUNTIME)
        self.assertEqual(result["runtime"]["state"], "MISSING")

    def test_a_verified_local_capability_is_resolvable(self) -> None:
        result = sr.resolve_capability("demo", registry=_registry(_entry()),
                                       discovery_ready=True, runtime_ready=True)
        self.assertEqual(result["verdict"], sr.VERDICT_RESOLVABLE)
        self.assertEqual(result["reason"], sr.REASON_RESOLVABLE)
        self.assertFalse(result["execution_authorized"],
                         "resolution is a pointer, never an execution grant")


class ScopeIsolationTests(unittest.TestCase):
    def test_an_undeclared_pipeline_is_out_of_scope(self) -> None:
        result = sr.resolve_capability("demo", pipeline="M4",
                                       registry=_registry(_entry()),
                                       discovery_ready=True, runtime_ready=True)
        self.assertEqual(result["reason"], sr.REASON_OUT_OF_SCOPE)

    def test_an_undeclared_stage_is_out_of_scope(self) -> None:
        result = sr.resolve_capability("demo", stage="compose",
                                       registry=_registry(_entry()),
                                       discovery_ready=True, runtime_ready=True)
        self.assertEqual(result["reason"], sr.REASON_OUT_OF_SCOPE)

    def test_media_use_is_scoped_to_the_m5_media_stage(self) -> None:
        entry = sr.registry_entries()[0]
        self.assertEqual(entry["pipelines"], ["M5"])
        self.assertEqual(entry["stages"], ["media_use"])
        self.assertIn("*", entry["accounts"])

    def test_media_use_resolution_follows_its_declared_scope(self) -> None:
        allowed = sr.resolve_capability("media-use", pipeline="M5", stage="media_use",
                                        discovery_ready=True, runtime_ready=True)
        self.assertEqual(allowed["verdict"], sr.VERDICT_RESOLVABLE)
        blocked = sr.resolve_capability("media-use", pipeline="M4", stage="media_use",
                                        discovery_ready=True, runtime_ready=True)
        self.assertEqual(blocked["reason"], sr.REASON_OUT_OF_SCOPE)


class DiscoveryTests(unittest.TestCase):
    def test_media_use_is_discovered_in_the_shared_store(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            shared = Path(raw)
            skill = shared / "media-use"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\nname: media-use\ndescription: demo\n---\n", encoding="utf-8")
            with mock.patch.object(sr, "SHARED_SKILL_ROOT", shared):
                names = [item["name"] for item in sr.shared_catalog()]
                state = sr._discovery_state(sr.registry_entries()[0])
        self.assertIn("media-use", names)
        self.assertTrue(state["installed"])
        self.assertEqual(state["root"], "shared")

    def test_an_absent_shared_store_is_reported_not_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with mock.patch.object(sr, "SHARED_SKILL_ROOT", Path(raw) / "absent"):
                self.assertEqual(sr.shared_catalog(), [])

    def test_windows_and_posix_paths_resolve_to_the_same_display(self) -> None:
        repo_relative = ROOT / "scripts" / "skill_route.py"
        self.assertEqual(sr._display(repo_relative), "scripts/skill_route.py")
        self.assertEqual(sr._display(repo_relative).count("\\"), 0)

    def test_a_skill_directory_with_spaces_and_unicode_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            shared = Path(raw) / "shared store"
            directory = shared / "未来 智能"
            directory.mkdir(parents=True)
            (directory / "SKILL.md").write_text(
                "---\nname: unicode-skill\ndescription: demo\n---\n", encoding="utf-8")
            with mock.patch.object(sr, "SHARED_SKILL_ROOT", shared):
                names = [item["name"] for item in sr.shared_catalog()]
        self.assertEqual(names, ["unicode-skill"])


class LegacyIndependenceTests(unittest.TestCase):
    def test_the_m5_entry_does_not_import_the_router(self) -> None:
        source = (ROOT / "scripts" / "m5_production.py").read_text(encoding="utf-8")
        self.assertNotIn("skill_route", source,
                         "the M5 entry must keep running without the router")
        self.assertNotIn("skill-registry", source)

    def test_the_router_does_not_import_the_m5_entry(self) -> None:
        source = (ROOT / "scripts" / "skill_route.py").read_text(encoding="utf-8")
        self.assertNotIn("import m5_production", source)
        self.assertNotIn("from m5_production", source)

    def test_the_router_is_importable_without_contentops(self) -> None:
        code = (
            "import sys; sys.path.insert(0, 'scripts');"
            "import skill_route as sr;"
            "assert 'contentops' not in [m for m in sys.modules if m == 'contentops'];"
            "print(sr.REGISTRY_SCHEMA)"
        )
        completed = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                                   capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(sr.REGISTRY_SCHEMA, completed.stdout)


class CliTests(unittest.TestCase):
    def _run(self, *args: str):
        return subprocess.run([sys.executable, "scripts/skill_route.py", *args],
                              cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")

    def test_list_and_sources_exit_zero(self) -> None:
        self.assertEqual(self._run("--sources").returncode, 0)
        self.assertEqual(self._run("--capabilities").returncode, 0)

    def test_resolve_media_use_reports_a_verdict(self) -> None:
        completed = self._run("--resolve", "media-use", "--pipeline", "M5",
                              "--stage", "media_use", "--json")
        # Exit 2 is correct when the runtime lock is absent or the skill is not
        # installed; the verdict must still be a machine-readable record.
        payload = json.loads(completed.stdout)
        self.assertIn(payload["verdict"], {sr.VERDICT_RESOLVABLE, sr.VERDICT_BLOCKED})
        self.assertFalse(payload["execution_authorized"])

    def test_resolve_unknown_name_blocks_and_exits_two(self) -> None:
        completed = self._run("--resolve", "__missing__", "--json")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["copies"], [])

    def test_doctor_is_machine_readable(self) -> None:
        report = sr.doctor()
        self.assertEqual(report["capabilities"]["total"], 1)
        # A resolvable count of 1 is only honest when a runtime lock exists.
        if report["capabilities"]["resolvable"]:
            self.assertTrue(os.environ.get("CONTENTOPS_MEDIA_USE_RUNTIME_LOCK"))


if __name__ == "__main__":
    unittest.main()
