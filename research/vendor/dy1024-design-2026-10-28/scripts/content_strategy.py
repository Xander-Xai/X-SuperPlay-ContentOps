#!/usr/bin/env python3
"""Local, credential-free strategy route used by the X•超玩1024 profile."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from runtime_context import ACCOUNT
except ImportError:  # imported as scripts.content_strategy
    from scripts.runtime_context import ACCOUNT


ROOT = Path(__file__).resolve().parents[1]


def build_result(content_id: str = "", title: str = "") -> dict[str, object]:
    profile = json.loads((ROOT / "profiles" / "profile.json").read_text(encoding="utf-8"))
    strategy = profile.get("strategy", {}) if isinstance(profile, dict) else {}
    video = profile.get("video", {}) if isinstance(profile.get("video"), dict) else {}
    conversion = profile.get("conversion", {}) if isinstance(profile.get("conversion"), dict) else {}
    return {
        "schema_version": 1,
        "route": "content-strategy",
        "content_id": content_id,
        "title": title,
        "account": ACCOUNT,
        "pillars": list(strategy.get("pillars", [])),
        "pillar_weights": strategy.get("pillar_weights", {}),
        "pillar_contracts": strategy.get("pillar_contracts", {}),
        "account_role": str(strategy.get("account_role", "Explore")),
        "north_star": str(strategy.get("north_star", "")),
        "content_loop": list(strategy.get("content_loop", [])),
        "signal_levels": list(strategy.get("signal_levels", [])),
        "record_fields": list(strategy.get("record_fields", [])),
        "problem_log_fields": list(strategy.get("problem_log_fields", [])),
        "mvp_gate": list(strategy.get("mvp_gate", [])),
        "handoff_to_future_intelligence": list(strategy.get("handoff_to_future_intelligence", [])),
        "stop_rules": list(strategy.get("stop_rules", [])),
        "copy_contract": strategy.get("copy_contract", {}),
        "conversion": {
            "default_cta": str(conversion.get("default_cta", "")),
            "problem_signal_ctas": list(conversion.get("problem_signal_ctas", [])),
            "handoff_cta": str(conversion.get("handoff_cta", "")),
            "cta_policy": str(conversion.get("cta_policy", "")),
        },
        "cadence": str(strategy.get("cadence", "")),
        "duration_policy": video.get("duration_policy", {}),
        "status": "ready",
        "passed": True,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "remote_calls": [],
    }


def run(args: argparse.Namespace) -> int:
    result = build_result(args.content_id, args.title)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the local X•超玩1024 content strategy snapshot.")
    parser.add_argument("--content-id", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--output", required=True)
    parser.set_defaults(handler=run)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
