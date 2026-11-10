#!/usr/bin/env python3
"""Unified end-to-end entry point for the gzh_未来智能 graphic-content workflow.

Runs the real engineering chain in one command and reports an auditable status:
  runtime deps -> identity -> matrix validation -> clean-room hygiene
  -> GitHub SDK adapter self-test -> all 10 gate checks (read-only)
  -> workflow status receipt

This driver NEVER advances a gate and NEVER fabricates a pass.  A blocked gate
is reported with its real error count.  Content creation, human review and
external publication remain explicit out-of-band steps.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from process_utils import hidden_run  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass


def _run(python: str, script: Path, args: list[str], cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    completed = hidden_run(
        [python, str(script), *args],
        cwd=str(cwd), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300,
    )
    text = (completed.stdout or "") + (completed.stderr or "")
    lines = [line for line in text.splitlines() if line.strip()]
    return {
        "script": script.name,
        "args": args,
        "returncode": completed.returncode,
        "status": "passed" if completed.returncode == 0 else "blocked",
        "output_head": lines[:12],
        "output_lines": len(lines),
    }


def _gate_summary(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    current: str | None = None
    gates: list[dict[str, Any]] = []
    for line in lines:
        if line.startswith("[PASS]") or line.startswith("[BLOCKED]"):
            match = re.match(r"\[(PASS|BLOCKED)\]\s+(\S+)", line)
            if not match:
                continue
            current = match.group(2)
            gates.append({"stage": current, "status": "passed" if match.group(1) == "PASS" else "blocked", "errors": 0})
        elif line.startswith("  - ") and gates and current == gates[-1]["stage"]:
            gates[-1]["errors"] += 1
    return {
        "stages": gates,
        "passed": sum(1 for g in gates if g["status"] == "passed"),
        "blocked": sum(1 for g in gates if g["status"] == "blocked"),
        "total_errors": sum(g["errors"] for g in gates),
    }


def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="工作流专用 venv 的 python")
    parser.add_argument("--workflow", required=True, type=Path)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--content-env", default="", help="仓库外内容凭证（AGNES_API_KEY）")
    parser.add_argument("--wechat-env", default="", help="仓库外微信凭证（WECHAT_1_*）")
    parser.add_argument("--output", type=Path, help="状态 JSON 输出路径")
    args = parser.parse_args()

    workflow = args.workflow.expanduser().resolve()
    article = args.article.expanduser().resolve()
    scripts = workflow / "scripts"
    env = dict(os.environ)
    env["GZH_ARTIFACT_ROOT"] = str(workflow.parent / "production")
    if args.wechat_env:
        env["WECHAT_ENV_PATH"] = str(Path(args.wechat_env).expanduser().resolve())
    python = str(Path(args.python).expanduser().resolve())

    steps: list[dict[str, Any]] = []
    steps.append(_run(python, scripts / "check_runtime_dependencies.py", ["--require-chrome"], workflow, env))
    steps.append(_run(python, scripts / "account_context.py", [], workflow, env))
    steps.append(_run(python, scripts / "validate_matrix.py", [], workflow, env))
    steps.append(_run(python, scripts / "workspace_hygiene.py", ["--check"], workflow, env))
    steps.append(_run(python, PROJECT_ROOT / "scripts" / "gzh_wechat_sdk_adapter.py",
                      ["self-test"], PROJECT_ROOT, env))

    wechat_probe: dict[str, Any] = {
        "status": "skipped",
        "reason": "未提供仓库外 WECHAT_1_* 凭证；发布链已接线，凭证到位后自动真实探测 token 与出口 IP",
    }
    wechat_env_path = Path(args.wechat_env).expanduser().resolve() if args.wechat_env else None
    if wechat_env_path and wechat_env_path.is_file():
        probe_proc = hidden_run(
            [python, str(PROJECT_ROOT / "scripts" / "gzh_wechat_sdk_adapter.py"),
             "probe", "--env", str(wechat_env_path)],
            cwd=str(PROJECT_ROOT), env=env, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=90,
        )
        try:
            wechat_probe = json.loads(probe_proc.stdout)
        except json.JSONDecodeError:
            wechat_probe = {"status": "blocked", "reason": "probe 输出无法解析",
                            "raw": (probe_proc.stdout or "")[:300]}
        steps.append({"script": "gzh_wechat_sdk_adapter.py probe", "args": ["probe"],
                      "returncode": probe_proc.returncode,
                      "status": wechat_probe.get("status", "blocked"),
                      "output_head": [wechat_probe.get("status", ""), wechat_probe.get("reason", "")],
                      "output_lines": len(probe_proc.stdout.splitlines())})

    gate_cmd = [python, str(scripts / "workflow_gate.py"), "--article", str(article),
                "--stage", "draft_submitted", "--all"]
    if args.content_env:
        gate_cmd += ["--env", str(Path(args.content_env).expanduser().resolve())]
    completed = hidden_run(gate_cmd, cwd=str(workflow), env=env, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=600)
    gate_text = (completed.stdout or "") + (completed.stderr or "")
    gates = _gate_summary(gate_text)
    steps.append({"script": "workflow_gate.py --all", "args": ["draft_submitted", "--all"],
                  "returncode": completed.returncode,
                  "status": "passed" if completed.returncode == 0 else "blocked",
                  "output_head": gate_text.splitlines()[:6], "output_lines": len(gate_text.splitlines())})
    steps.append(_run(python, scripts / "workflow_status.py", ["--article", str(article)], workflow, env))

    state_path = article / "matrix-state.json"
    state: dict[str, Any] = {}
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
    status_path = article / "workflow-status.json"

    blockers = {
        "wechat_credentials": not bool(args.wechat_env),
        "content_artifacts": gates["blocked"] > 1,
        "human_review": True,
        "ip_whitelist": "needs_operator_action",
    }
    payload = {
        "contract": "gzh-workflow-run-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workflow_root": str(workflow),
        "article_dir": str(article),
        "artifact_root": env["GZH_ARTIFACT_ROOT"],
        "python": python,
        "github_integration": {
            "repo": "https://github.com/wechatpy/wechatpy",
            "license": "MIT",
            "commit": "a695b89891e0473113c946a3a44d948fcf217404",
            "adapter": str(PROJECT_ROOT / "scripts" / "gzh_wechat_sdk_adapter.py"),
        },
        "engineering_chain": {
            "steps": steps,
            "passed": sum(1 for s in steps if s["status"] == "passed"),
            "blocked": sum(1 for s in steps if s["status"] == "blocked"),
        },
        "gates": gates,
        "wechat_probe": wechat_probe,
        "state": {
            "current_stage": state.get("current_stage"),
            "gate_history": state.get("gate_history", []),
            "status_receipt": str(status_path),
        },
        "blockers": blockers,
        "honesty": {
            "gate_advanced_in_this_run": False,
            "network_called_for_publishing": bool(wechat_probe.get("network_called")),
            "receipts_fabricated": False,
            "note": "只读门禁检查；内容产物、真人审核、微信凭证与 IP 加白均为真实外部前置条件",
        },
    }
    raw = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(raw, encoding="utf-8")
    print(raw)
    return 0 if payload["engineering_chain"]["blocked"] == 0 and gates["blocked"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
