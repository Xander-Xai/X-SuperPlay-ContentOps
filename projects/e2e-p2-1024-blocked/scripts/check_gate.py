#!/usr/bin/env python3
"""Reproduce the 1024 production block from the canonical backend contract."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
sys.path[:0] = [str(ROOT / "src")]

from contentops.media import animation_backend as ab  # noqa: E402

EVIDENCE_FILES = (
    "config/accounts/x-superplay-1024.json",
    "src/contentops/media/animation_backend.py",
    "scripts/animation_render.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    production_gate = ab.production_gate(
        account_id=ab.ACCOUNT_1024, has_real_recording=False)
    backend_decision = ab.select_backend(
        account_id=ab.ACCOUNT_1024,
        shot_type="annotation",
        explicit="remotion",
        readiness={"state": "READY"},
        purpose="production",
        has_real_recording=False,
    )
    receipt = {
        "schema": "contentops.p2-account-block/v1",
        "account_id": ab.ACCOUNT_1024,
        "state": "BLOCKED",
        "code": "MISSING_REAL_RECORDING",
        "checked_at": datetime.now(timezone.utc).replace(
            microsecond=0).isoformat().replace("+00:00", "Z"),
        "canonical_gates": {
            "production_gate": production_gate,
            "backend_selection": backend_decision,
        },
        "evidence": {
            "has_real_recording": False,
            "registered_real_recording": None,
            "source_hashes": {
                relative: sha256(ROOT / relative) for relative in EVIDENCE_FILES
            },
        },
        "reason": (
            "The 1024 DNA requires 70% real screen-recording evidence. "
            "No intake-verified cropped user recording was provided. Generated "
            "animation is explicitly non-evidence and cannot substitute."
        ),
        "impact": (
            "No 45-60s formal 1024 video may be produced, approved or published "
            "from this project. Only the technical clip chain can be tested in "
            "a separate TEST_ONLY project."
        ),
        "fix_conditions": [
            "User provides an original manual screen recording",
            "Recording passes intake and is cropped/redacted into a registered asset",
            "Claim ledger binds the recording SHA-256 and usage permission",
            "Formal M5 run is re-executed with has_real_recording=true",
        ],
        "user_actions": [
            "Record the real CLI/browser workflow manually and supply the file",
            "Confirm permission and which segments may be shown",
            "Re-run M5 only after intake registers the recording",
        ],
        "generated": True,
        "evidence_capable": False,
        "counts_as_real_recording": False,
        "production_ready": False,
        "publish_authorized": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }
    out = PROJECT / "receipts" / "production-block.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes((json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["code"] == "MISSING_REAL_RECORDING" else 1


if __name__ == "__main__":
    raise SystemExit(main())
