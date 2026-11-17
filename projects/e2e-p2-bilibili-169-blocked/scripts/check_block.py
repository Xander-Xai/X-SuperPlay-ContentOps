#!/usr/bin/env python3
"""Record the native 1920x1080 Bilibili variant block from real repository facts."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
sys.path[:0] = [str(ROOT / "src")]

from contentops.platforms import adaptation as ad  # noqa: E402

EVIDENCE_FILES = (
    "config/accounts/x-superplay-future-intelligence.json",
    "config/platforms/video-platforms.yaml",
    "scripts/m5_production.py",
    "scripts/video_deliver.py",
    "src/contentops/platforms/adaptation.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    plan = ad.plan(PROJECT, repo_root=ROOT)
    bilibili = next(
        (row for row in plan.get("platforms", [])
         if row.get("platform_id") == "bilibili"), {})
    receipt = {
        "schema": "contentops.p2-platform-block/v1",
        "account_id": plan.get("account", {}).get("slug"),
        "platform": "bilibili",
        "state": "BLOCKED",
        "code": "NATIVE_16_9_RENDER_UNAVAILABLE",
        "checked_at": datetime.now(timezone.utc).replace(
            microsecond=0).isoformat().replace("+00:00", "Z"),
        "platform_plan": {
            "status": plan.get("status"),
            "reason": plan.get("reason"),
            "master_canvas": plan.get("master_canvas"),
            "bilibili_row": bilibili,
        },
        "evidence": {
            "dna_native_cut": (
                "config/accounts/x-superplay-future-intelligence.json declares "
                "a B站加长版 1920×1080 derived cut"
            ),
            "platform_registry_note": (
                "config/platforms/video-platforms.yaml states that the render layer "
                "currently refuses anything but 1080x1920x30 and that the horizontal "
                "cut is recorded as BLOCKED"
            ),
            "render_contract": (
                "scripts/m5_production.py scales every composed visual to "
                "1080:1920 and has no native 1920x1080 storyboard/render path"
            ),
            "carrier_is_not_native": (
                "scripts/video_deliver.py can derive a blurred-pad 1920x1080 carrier "
                "and explicitly labels it as not the DNA-required native re-layout"
            ),
            "source_hashes": {
                relative: sha256(ROOT / relative) for relative in EVIDENCE_FILES
            },
        },
        "reason": (
            "A platform adaptation plan correctly marks Bilibili as requiring a "
            "1920x1080 variant, but the shipped M5/Easel render contract only "
            "produces 1080x1920. Stretching or blurred padding would be a silent "
            "substitution, which is forbidden."
        ),
        "impact": (
            "Only the 9:16 vertical cut is technically validated. No native B站 "
            "1920x1080 long cut is claimed, approved or packaged."
        ),
        "fix_conditions": [
            "Implement an explicit 16:9 storyboard layout and safe-zone QC",
            "Render that layout through a supported 1920x1080 pipeline",
            "Verify real composition, subtitle safe area and ffprobe 1920x1080",
            "Keep the vertical cut as a separate registered variant",
        ],
        "user_actions": [
            "Approve a distinct 16:9 re-layout scope if the native B站 cut is required",
        ],
        "generated": True,
        "evidence_capable": False,
        "production_ready": False,
        "publish_authorized": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }
    out = PROJECT / "receipts" / "native-169-block.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes((json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({
        "code": receipt["code"],
        "platform_status": plan.get("status"),
        "requires_variant": bilibili.get("requires_variant"),
        "canvas": bilibili.get("canvas"),
        "receipt": out.relative_to(ROOT).as_posix(),
    }, ensure_ascii=False, indent=2))
    return 0 if bilibili.get("requires_variant") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
