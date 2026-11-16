#!/usr/bin/env python3
"""Prepare the explicit Huashu shot plan consumed by M5 for this TEST_ONLY film.

The project is deliberately not account-bound, so M5 must not infer a backend
from account DNA. This helper uses the same production compiler
(``contentops.media.motion_planner.build_auto_plan``) with the pinned future-
intelligence DNA copied into ``sources/pinned``. It only adds two derivations
that M5 auto-planning would normally perform from an account-bound project:

1. claim artifact IDs are resolved to source-ref paths;
2. a code_focus shot gets a source-bound focus rectangle from the registered
   anchor's text_layout.

No second planner, cache, registry or render entry point is introduced. Output
JSON is written as LF bytes so git's ``*.json text eol=lf`` normalization cannot
change its SHA-256 after checkout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
sys.path[:0] = [str(ROOT / "src")]

from contentops.media.motion_planner import (  # noqa: E402
    MotionPlanError,
    build_auto_plan,
)

ACCOUNT_ID = "x-superplay-future-intelligence"
DNA_PATH = ROOT / "config" / "accounts" / f"{ACCOUNT_ID}.json"
PINNED_DNA_PATH = PROJECT / "sources" / "pinned" / f"{ACCOUNT_ID}.json"
PLAN_PATH = PROJECT / "motion" / "shot-plan.json"
RECEIPT_PATH = PROJECT / "receipts" / "motion-plan-preparation.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def source_rect(asset: dict[str, Any], shot_id: str) -> list[float]:
    layout = asset.get("text_layout") or {}
    focus_lines = set(layout.get("focus_source_lines") or [])
    candidates = [
        row for row in (layout.get("lines") or [])
        if row.get("n") in focus_lines and str(row.get("text") or "").strip()
    ]
    if not candidates:
        raise MotionPlanError(
            f"AUTO_MOTION_FOCUS_MISSING: {shot_id} has no source-bound focus line"
        )
    rect = candidates[0].get("rect")
    if not isinstance(rect, list) or len(rect) != 4:
        raise MotionPlanError(f"AUTO_MOTION_FOCUS_RECT_INVALID: {shot_id}")
    x, y, width, _ = (float(value) for value in rect)
    # Keep the crop tied to the registered line position while making it tall
    # enough to remain legible at 1080x1920.
    height = 0.08
    if x < 0 or y < 0 or width <= 0 or x + width > 1 or y + height > 1:
        raise MotionPlanError(f"AUTO_MOTION_FOCUS_RECT_INVALID: {shot_id}")
    return [round(x, 6), round(y, 6), round(width, 6), height]


def main() -> int:
    script = read_json(PROJECT / "script" / "script.json")
    narration = read_json(PROJECT / "receipts" / "narration.json")
    assets_doc = read_json(PROJECT / "sources" / "assets.json")
    claims_doc = read_json(PROJECT / "script" / "claims.json")
    refs_doc = read_json(PROJECT / "sources" / "source-refs.json")
    dna = read_json(DNA_PATH if DNA_PATH.is_file() else PINNED_DNA_PATH)

    assets = {str(row.get("id")): row for row in assets_doc.get("assets", [])}
    claims = {str(row.get("id")): row for row in claims_doc.get("claims", [])}
    refs = {str(row.get("id")): row for row in refs_doc.get("refs", [])}

    lines = script.get("lines") or []
    enriched_visuals: list[dict[str, Any]] = []
    derived_focus: dict[str, list[float]] = {}
    for row in script.get("visual_shots") or []:
        segment_id = str(row.get("segment_id") or "")
        semantic = next(
            (item for item in lines if str(item.get("id")) == segment_id), None
        )
        if semantic is None:
            raise MotionPlanError(
                f"AUTO_MOTION_VISUAL_SHOT_INVALID: unknown segment {segment_id!r}"
            )
        claim = claims.get(str(semantic.get("claim"))) or {}
        source_refs = []
        for ref_id in claim.get("artifacts") or []:
            ref = refs.get(str(ref_id)) or {}
            value = ref.get("url") or ref.get("path")
            if value:
                source_refs.append(str(value))

        visual = {**row, "source_refs": source_refs}
        if row.get("animation_type") == "code_focus":
            asset_id = str(row.get("asset_id") or "")
            asset = assets.get(asset_id)
            if asset is None:
                raise MotionPlanError(f"AUTO_MOTION_TEMPLATE_SOURCE_MISSING: {asset_id}")
            rect = source_rect(asset, str(row.get("shot_id") or ""))
            derived_focus[asset_id] = rect
            visual["animation"] = {**(row.get("animation") or {}), "focus_rect": rect}
        enriched_visuals.append(visual)

    plan_script = {**script, "lines": lines, "visual_shots": enriched_visuals}
    generated = build_auto_plan(
        project=PROJECT,
        account_id=ACCOUNT_ID,
        account_dna=dna,
        script=plan_script,
        narration=narration,
        source_assets=assets,
    )
    plan = generated["plan"]
    write_json(PLAN_PATH, plan)
    write_json(RECEIPT_PATH, {
        "schema": "contentops.p2-motion-plan-preparation/v1",
        "backend": "huashu-art-motion",
        "account_id": ACCOUNT_ID,
        "project_account_bound": False,
        "purpose": "TEST_ONLY technical film; DNA supplies palette and grammar only",
        "compiler": "contentops.media.motion_planner.build_auto_plan",
        "input_sha256": generated["input_sha256"],
        "compiler_plan": generated["path"].relative_to(PROJECT).as_posix(),
        "consumed_plan": PLAN_PATH.relative_to(PROJECT).as_posix(),
        "shot_count": len(plan.get("shots") or []),
        "derived_focus_rects": derived_focus,
        "production_ready": False,
        "publish_authorized": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    })
    print(f"prepared {len(plan.get('shots') or [])} shots: "
          f"{PLAN_PATH.relative_to(PROJECT).as_posix()} "
          f"sha256={generated['input_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MotionPlanError as exc:
        print(f"MOTION_PLAN_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
