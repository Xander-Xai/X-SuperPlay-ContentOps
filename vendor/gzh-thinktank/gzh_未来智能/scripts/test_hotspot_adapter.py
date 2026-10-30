#!/usr/bin/env python3
"""Regression tests for the GZH Agent Reach hotspot adapter."""

from __future__ import annotations

import sys
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hotspot"))
import agent_reach_hotspot as hotspot  # noqa: E402


class HotspotAdapterTests(unittest.TestCase):
    def tearDown(self) -> None:
        hotspot._opencli_browser_connected.cache_clear()

    def test_opencli_probe_requires_connected_extension_markers(self) -> None:
        with patch.object(hotspot.shutil, "which", return_value="C:/bin/opencli.exe"), patch.object(
            hotspot.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(
                ["opencli", "doctor"], 0, "[MISSING] Extension: not connected\n", ""
            ),
        ):
            connected, reason = hotspot._opencli_browser_connected()
        self.assertFalse(connected)
        self.assertIn("not connected", reason)

    def test_opencli_probe_accepts_connection_markers(self) -> None:
        with patch.object(hotspot.shutil, "which", return_value="C:/bin/opencli.exe"), patch.object(
            hotspot.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(
                ["opencli", "doctor"], 0, "[OK] Extension: connected\n[OK] Connectivity: OK\n", ""
            ),
        ):
            connected, reason = hotspot._opencli_browser_connected()
        self.assertTrue(connected)
        self.assertIn("connected", reason)

    def test_remaining_timeout_never_exceeds_source_budget(self) -> None:
        with patch.object(hotspot.time, "monotonic", return_value=100.0):
            self.assertEqual(hotspot._remaining_timeout(112.0, 30), 12)
            self.assertIsNone(hotspot._remaining_timeout(100.0, 30))

    def test_mcp_login_probe_accepts_human_readable_logged_in_response(self) -> None:
        with patch.object(
            hotspot,
            "_run_agent_reach_cli",
            return_value="✅ 已登录\n用户名: X超玩未来智能\n",
        ) as run_cli:
            ready, reason = hotspot._mcporter_xhs_login_ready()
        self.assertTrue(ready)
        self.assertIn("confirmed", reason)
        command = run_cli.call_args.args[0]
        self.assertIn("120000", command)
        self.assertEqual(run_cli.call_args.kwargs["timeout"], 20)

    def test_existing_local_mcp_is_reused_without_starting_process(self) -> None:
        with patch.object(hotspot, "_local_mcp_health", return_value=True), patch.object(
            hotspot.subprocess, "Popen"
        ) as popen:
            ready, reason = hotspot._ensure_xhs_mcp()
        self.assertTrue(ready)
        self.assertIn("already healthy", reason)
        popen.assert_not_called()

    def test_installed_local_mcp_is_started_when_health_is_down(self) -> None:
        binary = Mock()
        binary.is_file.return_value = True
        binary.parent = "C:/mcp"
        health = Mock(side_effect=[False, False, True])
        with patch.object(hotspot, "XHS_MCP_BINARY", binary), patch.object(
            hotspot, "_local_mcp_health", health
        ), patch.object(hotspot.subprocess, "Popen") as popen, patch.object(
            hotspot.time, "sleep", return_value=None
        ):
            ready, reason = hotspot._ensure_xhs_mcp()
        self.assertTrue(ready)
        self.assertIn("started installed", reason)
        popen.assert_called_once()

    def test_account_source_policy_is_explicit(self) -> None:
        self.assertEqual(
            hotspot.SOURCE_PRIORITY_TIERS["primary_global"],
            ("twitter", "github", "youtube"),
        )
        self.assertEqual(
            hotspot.SOURCE_PRIORITY_TIERS["primary_domestic"],
            ("douyin", "xhs", "bilibili", "weibo"),
        )
        self.assertEqual(
            hotspot.SOURCE_PRIORITY_TIERS["supplementary"],
            ("domestic_rss", "rss", "v2ex"),
        )

    def test_one_primary_failure_does_not_block_healthy_collection(self) -> None:
        def failed(_query: str, _limit: int):
            raise RuntimeError("session expired")

        report = hotspot.collect_hotspot_report(
            "AI Agent",
            limit=2,
            sources=("twitter", "github"),
            collectors={
                "twitter": failed,
                "github": lambda _query, _limit: [
                    {"fullName": "example/agent", "url": "https://github.com/example/agent"}
                ],
            },
        )
        report = hotspot.apply_required_source_policy(report, required=("twitter", "github"))
        self.assertTrue(report["passed"])
        self.assertFalse(report["required_sources_ok"])
        self.assertEqual(report["required_source_failures"][0]["source"], "twitter")
        self.assertEqual(report["collection_gate"], "passed-with-primary-source-warnings")

    def test_strict_mode_is_explicit_opt_in(self) -> None:
        report = {
            "passed": True,
            "freshness_verified": True,
            "items": [{"source_url": "https://example.com/item"}],
            "source_health": [
                {"source": "xhs", "status": "error", "item_count": 0, "error": "session expired"}
            ],
        }
        report = hotspot.apply_required_source_policy(report, required=("xhs",), strict=True)
        self.assertFalse(report["passed"])
        self.assertEqual(report["collection_gate"], "blocked-required-source-failure")

    def test_resolved_proxy_overrides_stale_child_proxy(self) -> None:
        class FakeProcess:
            pid = 123
            returncode = 0

            def communicate(self, timeout=None):
                return "ok", ""

        with patch.object(hotspot.shutil, "which", return_value="fake-cli"), \
                patch.object(hotspot, "_resolve_proxy", return_value=("http://127.0.0.1:7897", "windows-internet-settings")), \
                patch.object(hotspot.subprocess, "Popen", return_value=FakeProcess()) as popen:
            self.assertEqual(hotspot._run_agent_reach_cli(["fake-cli", "--version"]), "ok")
        child_env = popen.call_args.kwargs["env"]
        self.assertEqual(child_env["HTTP_PROXY"], "http://127.0.0.1:7897")
        self.assertEqual(child_env["HTTPS_PROXY"], "http://127.0.0.1:7897")


if __name__ == "__main__":
    unittest.main()
