#!/usr/bin/env python3
"""Render a platform cover for an evidence cut and record its provenance.

Covers use the card-design system (`card-design` for the layout, the platform
card skill for the ratio) and render through the shared card renderer. The cover
title is a claim: this script resolves it from the Claim Map and refuses a
missing binding.

Current limitation, recorded honestly: the shipped covers are citation covers
built from the tracked document, not crops of a redacted capture. A cover that
used a raw frame would imply distribution rights the project has not approved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from process_utils import hidden_run, python_executable  # noqa: E402
from contentops.evidence.claim_map import ClaimMap  # noqa: E402
from contentops.evidence._common import ContractError  # noqa: E402

RENDER_CARD = ROOT / ".runtime/easel/skills/shared/scripts/render_card.py"
CARD_AUDIT = ROOT / ".runtime/easel/skills/openclaw/card-design/scripts/card_audit.py"
COVER_SCHEMA = "contentops.cover-receipt/v1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_yaml(path: Path) -> dict:
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip().strip('"')
    return data


def build(project: Path) -> dict:
    project = project.resolve()
    config = parse_yaml(project / "project.yaml")
    for required in ("cover_html", "cover_png", "cover_width", "cover_height",
                     "cover_platform", "cover_title_claim"):
        if not config.get(required):
            raise ContractError("MISSING_COVER_CONFIG",
                                f"project.yaml needs {required}")
    claim_map = ClaimMap.from_dict(json.loads(
        (project / "script" / "claim-map.json").read_text(encoding="utf-8")))
    claim = claim_map.by_id(config["cover_title_claim"])
    if not any(a["surface"] == "cover_title" for a in claim.appearances):
        raise ContractError("UNBOUND_COVER_TITLE",
                            f"{claim.claim_id} has no cover_title appearance")

    html = project / config["cover_html"]
    png = project / config["cover_png"]
    if not html.is_file():
        raise ContractError("MISSING_COVER_HTML", str(html))
    png.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    render = hidden_run([
        python_executable(), str(RENDER_CARD),
        "--html", str(html), "--out", str(png), "--full-page", "--scale", "1",
        "--width", config["cover_width"], "--height", config["cover_height"],
    ], cwd=str(ROOT / ".runtime" / "easel"), timeout=300, env=env)
    if render.returncode != 0 or not png.is_file():
        raise ContractError("COVER_RENDER_FAILED",
                            (render.stderr or render.stdout or "")[-500:])

    audit = hidden_run([
        python_executable(), str(CARD_AUDIT), "audit", "-f", str(png),
    ], cwd=str(ROOT / ".runtime" / "easel"), timeout=300, env=env)
    audit_text = ((audit.stdout or "") + (audit.stderr or "")).strip()
    # A cover is a standalone card, so the density gate is a real gate here.
    if "FAIL" in audit_text.upper():
        raise ContractError("COVER_DENSITY_FAILED", audit_text[-500:])

    from contentops.media.transport import ffprobe_json
    dims = ffprobe_json(png)
    width = dims["streams"][0]["width"]
    height = dims["streams"][0]["height"]
    expected = (int(config["cover_width"]), int(config["cover_height"]))
    if (width, height) != expected:
        raise ContractError("COVER_SIZE_MISMATCH", f"{width}x{height} != {expected}")

    receipt = {
        "schema": COVER_SCHEMA,
        "platform": config["cover_platform"],
        "width": width,
        "height": height,
        "claim_id": claim.claim_id,
        "claim_text": claim.text,
        "source": "citation_cover",
        "source_note": "built from the tracked document; no raw capture frame was "
                       "used because no capture is publishable yet",
        "html": {"path": f"project://{config['cover_html']}", "sha256": _sha(html)},
        "png": {"path": f"project://{config['cover_png']}", "sha256": _sha(png)},
        "audit": audit_text,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    receipts = project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / "cover.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    return receipt


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    args = parser.parse_args()
    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    try:
        result = build(project)
    except ContractError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)},
                         indent=2, ensure_ascii=False))
        return 4
    print(json.dumps({"status": "OK", **result}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
