#!/usr/bin/env python3
"""Regression test for the permission/IP whitelist preflight."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "publish_preflight.py"


def main() -> int:
    test_env = os.environ.copy()
    test_env["WORKFLOW_TEST_MODE"] = "1"
    with tempfile.TemporaryDirectory(prefix="publish-preflight-") as raw:
        root = Path(raw)
        article = root / "article"
        env = root / "aws.env"
        env.write_text("WECHAT_1_APPID=fixture\nWECHAT_1_APPSECRET=fixture\n", encoding="utf-8")
        pending = subprocess.run(
            [sys.executable, str(SCRIPT), "--article", str(article), "--env", str(env), "--account-slot", "1"],
            cwd=ROOT,
            env=test_env,
        )
        assert pending.returncode == 1
        approved = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--article",
                str(article),
                "--env",
                str(env),
                "--account-slot",
                "1",
                "--approve",
                "--draft-permission-confirmed",
                "--ip-whitelist-confirmed",
            ],
            cwd=ROOT,
            env=test_env,
        )
        assert approved.returncode == 0
        result = json.loads((article / "publish-preflight.json").read_text(encoding="utf-8"))
        assert result["status"] == "passed"
        assert result["ip_whitelist_checked"] is True
        assert result["draft_permission"] is True
    print("PUBLISH PREFLIGHT TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
