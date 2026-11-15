#!/usr/bin/env python3
"""Run the deterministic offline Easel task scaffold.

Input is one JSON object on stdin with exactly ``account``, ``project``,
``brief`` and ``idempotency_key``. No model, gateway, Agent, network or shell
is called. Draft and receipt files are written only under an existing project.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.easel.offline_task import OfflineTaskError, run_offline_draft_task  # noqa: E402


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def main() -> int:
    # Windows redirected stdout otherwise commonly uses a legacy code page,
    # which cannot represent arbitrary Chinese draft/profile text in JSON.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raw = sys.stdin.buffer.read(32_769)
    if len(raw) > 32_768:
        print(json.dumps({"error": "INPUT_TOO_LARGE"}))
        return 2
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError):
        print(json.dumps({"error": "INPUT_INVALID", "detail": "expected UTF-8 JSON on stdin"}))
        return 2
    expected = {"account", "project", "brief", "idempotency_key"}
    if not isinstance(payload, dict) or set(payload) != expected:
        print(json.dumps({"error": "INPUT_SCHEMA_INVALID",
                          "detail": "required keys: account, project, brief, idempotency_key"}))
        return 2
    try:
        result = run_offline_draft_task(
            repo_root=ROOT,
            account=payload["account"],
            project_slug=payload["project"],
            brief=payload["brief"],
            idempotency_key=payload["idempotency_key"],
        )
    except OfflineTaskError as exc:
        failure = {"error": exc.code, "detail": exc.detail}
        if exc.failure_receipt:
            failure["failure_receipt"] = exc.failure_receipt
        print(json.dumps(failure, ensure_ascii=False))
        return 4
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
