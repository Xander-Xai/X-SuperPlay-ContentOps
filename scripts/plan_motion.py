#!/usr/bin/env python3
"""Plan a hybrid motion shot list: one backend per shot, only ready ones.

Usage:
    python scripts/plan_motion.py projects/my-video [--json]

Reads ``script/script.json`` and ``project.yaml``, probes every motion backend
through its real readiness path, and writes ``receipts/motion-orchestration.json``.
It does not render, does not sign a review and does not grant publication.

Huashu readiness is probed through the M5 adapter (the path that actually renders
its clips); Remotion / Motion Canvas / Manim through animation_render's clip
preflight. A backend that is not READY is excluded, never substituted silently.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.media.animation_backend import (  # noqa: E402
    CLIP_BACKENDS,
    HUASHU_BACKENDS,
    KNOWN_BACKENDS,
)
from contentops.media.animation_orchestrator import (  # noqa: E402
    OrchestrationBlocked,
    plan,
)

BLOCKED_EXIT = 4


def _read_yaml_value(text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}\s*:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip().strip('"').strip("'") if match else ""


def probe_readiness(project: Path) -> dict:
    """Real readiness per backend. The caller must not fake a READY state."""
    readiness: Dict[str, str] = {}

    try:
        import huashu_motion_adapter as adapter
        pre = adapter._preflight(project, mode="AUTO")
        state = str((pre.get("execution_policy") or {}).get("state") or "")
        huashu_ready = state == "LOCAL_ONLY_PERMITTED"
        for backend in HUASHU_BACKENDS:
            readiness[backend] = "READY" if huashu_ready else "BLOCKED"
    except Exception:  # noqa: BLE001 - a failed probe is BLOCKED, never READY
        for backend in HUASHU_BACKENDS:
            readiness[backend] = "BLOCKED"

    try:
        import animation_render as ar
        for backend in CLIP_BACKENDS:
            try:
                probe = ar.environment_probe(backend)
                result = ar.preflight(backend, probe)
                readiness[backend] = ("READY" if str(result.get("state")) == "READY"
                                      else "BLOCKED")
            except Exception:  # noqa: BLE001
                readiness[backend] = "BLOCKED"
    except Exception:  # noqa: BLE001
        for backend in CLIP_BACKENDS:
            readiness[backend] = "BLOCKED"

    return readiness


def _editorial_title_props(line: Mapping[str, Any]) -> Optional[Dict[str, str]]:
    """Editorial title-card display fields, never a factual claim or source path.

    Returns None when the line cannot be turned into an honest title card. A
    title card is support material: it carries the hook's conflict and stakes as
    display text, no evidence_ref and no source path (plan_clip strips those too).
    """
    text = str(line.get("narration") or line.get("caption") or "").strip()
    if not text or len(text) > 60:
        return None
    # Split near the middle on a punctuation boundary so neither card is empty.
    # A trailing question mark must not leave the stakes side blank.
    middle = len(text) // 2
    pivot = -1
    for token in ("；", ";", "，", ",", "。", "？", "?"):
        candidates = [i for i, ch in enumerate(text)
                      if ch == token and len(text) * 0.25 <= i <= len(text) * 0.75]
        if candidates:
            pivot = min(candidates, key=lambda i: abs(i - middle))
            break
    if pivot > 0:
        conflict, stakes = text[:pivot + 1], text[pivot + 1:]
    else:
        conflict, stakes = text[:middle], text[middle:]
    if not conflict.strip() or not stakes.strip():
        return None
    return {"conflict": conflict.strip()[:40], "stakes": stakes.strip()[:40],
            "kicker": "学习路线 · 编辑性字卡"}


def materialize(project: Path, result: Dict[str, Any],
                script: Dict[str, Any]) -> Dict[str, Any]:
    """Turn a planning result into an M5-consumable hybrid shot plan.

    Only shots that can be given an honest, contract-valid spec are materialized
    on their assigned clip backend. The rest fall back to Huashu's own authored
    plan and are recorded, never silently changed. The shot plan is marked
    ``orchestrated: true`` so M5 enforces the assignment on exactly this plan.
    """
    import animation_render as ar

    lines = {str(line.get("id")): line for line in script.get("lines") or []}
    specs_dir = project / "motion" / "orchestrated"
    specs_dir.mkdir(parents=True, exist_ok=True)
    shots: List[Dict[str, Any]] = []
    fallback: List[str] = []
    for assignment in result.get("assignments") or []:
        placement = str(assignment.get("placement_id") or "")
        backend = str(assignment.get("backend") or "")
        line = lines.get(placement)
        if line is None:
            raise OrchestrationBlocked("PLACEMENT_MISSING", f"{placement} not in script")
        if backend not in CLIP_BACKENDS:
            # Huashu shots are NOT put in the overlay. M5's own auto-plan authors
            # their spec from the *measured* narration duration; inventing a
            # duration here would be a degradation. They simply stay untouched.
            continue
        props = _editorial_title_props(line)
        if not (assignment.get("shot_kind") == "title_card" and props is not None
                and ar.preflight("remotion", ar.environment_probe("remotion")).get("state") == "READY"):
            fallback.append(placement)  # no honest spec -> leave on Huashu, record it
            continue
        spec = {"backend": backend, "template": "title_card",
                "shot_type": "title_card", "duration_s": 3.0, "props": props}
        spec_path = specs_dir / f"{placement}.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        shots.append({"placement_id": placement,
                      "asset_id": f"orch-{placement}",
                      "source_asset_id": str(line.get("asset_id") or ""),
                      "backend": backend, "shot_type": "title_card",
                      "spec": spec_path.relative_to(project).as_posix()})

    # An overlay, not a full plan: only clip shots are named. M5 applies these
    # on top of its Huashu auto-plan, so every Huashu shot keeps a real duration.
    plan_doc = {"schema": "contentops.m5-motion-overlay/v1", "orchestrated": True,
                "kind": "clip_overlay", "backend": "hybrid", "shots": shots}
    plan_path = project / "motion" / "orchestrated-plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan_doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    # Make the receipt self-describing: each assignment records both the
    # planned skill and what will actually run, so nobody reads 25 "remotion"
    # assignments and assumes 25 clips were rendered.
    clip_ids = {str(row.get("placement_id")) for row in shots}
    for assignment in result.get("assignments") or []:
        pid = str(assignment.get("placement_id") or "")
        planned = str(assignment.get("backend") or "")
        assignment["materialized"] = pid in clip_ids
        assignment["execution_backend"] = planned if pid in clip_ids else "huashu-art-motion"
        if pid in fallback:
            assignment["fallback_reason"] = "no honest contract-valid clip spec"
    return {"plan": plan_path.relative_to(project).as_posix(),
            "plan_shots": len(shots), "huashu_fallback": fallback,
            "materialized": True}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="plan but write nothing")
    parser.add_argument("--materialize", action="store_true",
                        help="generate an M5-consumable hybrid shot plan and specs")
    parser.add_argument("--purpose", default="production", choices=("production", "test"))
    args = parser.parse_args(argv)

    project = Path(args.project)
    script_path = project / "script" / "script.json"
    yaml_path = project / "project.yaml"
    try:
        if not script_path.is_file():
            raise OrchestrationBlocked("SCRIPT_MISSING", "script/script.json not found")
        script = json.loads(script_path.read_text(encoding="utf-8"))
        yaml_text = yaml_path.read_text(encoding="utf-8") if yaml_path.is_file() else ""
        account = _read_yaml_value(yaml_text, "account_slug")
        if not account:
            raise OrchestrationBlocked("ACCOUNT_REQUIRED", "project.yaml has no account_slug")

        readiness = probe_readiness(project)
        result = plan(
            script.get("lines") or [], account_id=account, readiness=readiness,
            purpose=args.purpose,
        )
        result["readiness"] = readiness
        result["project"] = project.as_posix()
        result["materialized"] = False  # planning-only by default; never blocks M5

        if args.materialize and not args.dry_run:
            detail = materialize(project, result, script)
            result.update(detail)
            result["materialized"] = True

        receipt = project / "receipts" / "motion-orchestration.json"
        if not args.dry_run:
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
            result["written"] = [receipt.relative_to(project).as_posix()]
            if args.materialize:
                # The overlay is applied on top of M5's auto-plan; do NOT point
                # motion.shot_plan at it, or M5 would skip auto-plan entirely and
                # the Huashu shots would have no authored spec.
                result["next_step"] = (
                    "overlay applied automatically on the next m5_production run; "
                    "leave project.yaml motion.shot_plan unset")

        if args.dry_run:
            result.pop("written", None)

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"{'HYBRID' if result['hybrid'] else 'SINGLE'} plan: "
                  f"{len(result['assignments'])} shots, backends {result['backends']}")
            for backend in KNOWN_BACKENDS:
                print(f"  {backend:20} {readiness.get(backend)}")
        return 0
    except (OrchestrationBlocked, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, OrchestrationBlocked) else "READ_FAILED"
        detail = exc.detail if isinstance(exc, OrchestrationBlocked) else str(exc)
        if args.json:
            print(json.dumps({"state": code, "detail": detail}, ensure_ascii=False, indent=2))
        else:
            print(f"{code}: {detail}")
        return BLOCKED_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
