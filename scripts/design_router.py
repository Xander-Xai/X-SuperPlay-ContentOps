"""Turn an approved brief into a design plan (audience, duration, strategy, route).

This is the missing S4 seam between a brief and the script/renderer. It reads
only local JSON, refuses an unapproved brief, and writes one plan document. It
never contacts a source, a provider or a platform.

Usage:
    python scripts/design_router.py --brief <brief.json> --account <account.json> \
        --platform douyin --target-sec 40 --line-count 7 [--out plan.json]

What is not claimed
-------------------
A design plan is not a script and not an approval. The copy review and the
human gate remain after it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.workflow.audience import plan_audience, validate_audience  # noqa: E402
from contentops.workflow.contract import WorkflowError  # noqa: E402
from contentops.workflow.copy_strategy import choose_strategy, validate_strategy  # noqa: E402
from contentops.workflow.duration import plan_duration, validate_duration  # noqa: E402
from contentops.workflow.platform import constraints_for, validate_target  # noqa: E402

SCHEMA = "contentops.design-plan/v1"


def _load(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkflowError("DESIGN_READ", f"{path}: {exc}")
    if not isinstance(data, dict):
        raise WorkflowError("DESIGN_READ", f"{path}: expected a JSON object")
    return data


def build_design(*, brief: Dict[str, Any], account: Dict[str, Any], platform: str,
                 target_sec: float, line_count: int) -> Dict[str, Any]:
    intent = brief.get("intent") if isinstance(brief.get("intent"), dict) else {}
    if intent.get("approval_status") not in ("approved", "human_approved"):
        raise WorkflowError(
            "BRIEF_NOT_APPROVED",
            "the brief is not human-approved; an automation approval cannot be designed for production",
        )
    approved_by = str(intent.get("approved_by") or "").strip().lower()
    if approved_by in ("automation", "acceptance", "router-e2e"):
        raise WorkflowError("BRIEF_AUTOMATION_APPROVAL", "an automation approval is not a human approval")

    audience = validate_audience(plan_audience(account, brief))
    route = brief.get("route") if isinstance(brief.get("route"), dict) else {}
    strategy = validate_strategy(choose_strategy(
        route.get("mode") or intent.get("route_mode") or "USER_TOPIC",
        intent.get("evidence_status") or "verification_required",
        has_real_material=bool(intent.get("source_artifact_refs")),
    ))
    constraints = constraints_for(platform, ROOT / "config" / "registry" / "platforms.json")
    target = validate_target(
        {"aspect_ratio": constraints["aspect_ratio"], "duration_target_sec": target_sec},
        constraints,
    )
    duration = validate_duration(plan_duration(target_sec, line_count))
    return {
        "schema": SCHEMA,
        "brief_id": brief.get("brief_id"),
        "audience": audience,
        "copy_strategy": strategy,
        "platform": constraints,
        "target": target,
        "duration": duration,
        "production_ready": False,
        "note": "design plan only; script, copy review and human gate follow",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Design an approved brief into audience/duration/strategy.")
    parser.add_argument("--brief", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--platform", default="douyin")
    parser.add_argument("--target-sec", type=float, default=40.0)
    parser.add_argument("--line-count", type=int, default=7)
    parser.add_argument("--out", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = build_design(
            brief=_load(Path(args.brief)),
            account=_load(Path(args.account)),
            platform=args.platform,
            target_sec=args.target_sec,
            line_count=args.line_count,
        )
    except WorkflowError as exc:
        print(json.dumps({"ok": False, "state": "BLOCKED", "reason": f"{exc.code}: {exc.detail}"},
                         ensure_ascii=False, indent=2))
        return 2
    text = json.dumps(plan, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "out": args.out}, ensure_ascii=False))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
