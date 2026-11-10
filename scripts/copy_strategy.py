#!/usr/bin/env python3
"""Expose the existing copy-strategy decision as a small planning CLI.

This is a planning result only: it does not approve a brief or copy, and it
never marks the strategy production-ready.

Usage:
    python scripts/copy_strategy.py --route-mode USER_TOPIC \
        --evidence-status verified [--has-real-material]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow.contract import WorkflowError  # noqa: E402
from contentops.workflow.copy_strategy import (  # noqa: E402
    choose_strategy,
    validate_strategy,
)


def build_strategy_record(*, route_mode: str, evidence_status: str,
                          has_real_material: bool = False) -> Dict[str, Any]:
    """Build a validated strategy without granting approval or readiness."""
    record = validate_strategy(choose_strategy(
        route_mode, evidence_status, has_real_material=has_real_material))
    return {**record, "review_status": "PENDING_OWNER_REVIEW"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--route-mode", required=True)
    parser.add_argument("--evidence-status", required=True)
    parser.add_argument("--has-real-material", action="store_true")
    args = parser.parse_args(argv)
    try:
        record = build_strategy_record(
            route_mode=args.route_mode,
            evidence_status=args.evidence_status,
            has_real_material=args.has_real_material,
        )
    except WorkflowError as exc:
        print(json.dumps({"state": "BLOCKED", "reason": exc.code,
                          "detail": exc.detail}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
