"""Create an explicitly local-only M5 manifest bridge E2E fixture project.

This test helper never resolves credentials or calls a media provider. It refuses
an existing manifest and delegates video bytes plus AudioPolicy receipts to the
canonical local fixture and transform implementations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.fixtures_local import build_shot_fixture  # noqa: E402
from contentops.media.media_envelope import (  # noqa: E402
    HUMAN_REVIEW_PENDING,
    MediaAssetEnvelope,
    MediaModality,
)
from contentops.media.media_transform import apply_audio_policy  # noqa: E402
from contentops.media.quality_gate import (  # noqa: E402
    GATE_PENDING_HUMAN_REVIEW,
    MediaManifest,
    TimelinePlacement,
)


def create(project: Path) -> Path:
    project = Path(project).resolve()
    try:
        project.relative_to(ROOT / "projects")
    except ValueError as exc:
        raise SystemExit("fixture project must be under repository projects/") from exc
    manifest_path = project / "receipts" / "media-manifest.json"
    if manifest_path.exists():
        raise SystemExit(f"refusing to overwrite existing manifest: {manifest_path}")
    generated = project / "assets" / "generated"
    processed = project / "assets" / "processed"
    if generated.exists() and any(generated.iterdir()):
        raise SystemExit(f"refusing to overwrite existing generated media: {generated}")
    if processed.exists() and any(processed.iterdir()):
        raise SystemExit(f"refusing to overwrite existing processed media: {processed}")
    assets = []
    gates = {}
    timeline = []
    for index in range(1, 8):
        placement = f"P-{index:02d}"
        source_id, active_id = f"{placement}-source", f"{placement}-replaced"
        source_path, source_receipt, fingerprint = build_shot_fixture(
            generated / f"{placement}.mp4", seed=f"manifest-bridge-{placement}", seconds=6
        )
        source = MediaAssetEnvelope(
            asset_id=source_id,
            modality=MediaModality.VIDEO,
            placement_id=placement,
            path=f"project://assets/generated/{placement}.mp4",
            sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
            receipt_ref=source_receipt.name,
            fingerprint=fingerprint,
            asset_kind="GENERATED_VIDEO",
            generated=True,
            evidence_capable=False,
            evidence_use="VISUAL_SUPPORT",
            human_review=HUMAN_REVIEW_PENDING,
            production_ready=False,
        )
        application = apply_audio_policy(
            source_video=source_path,
            policy="REPLACE",
            output_dir=processed,
            source_receipt_ref=source_receipt.name,
            source_fingerprint=fingerprint,
            source_generated=True,
        )
        output = Path(application.output_path)
        active = MediaAssetEnvelope(
            asset_id=active_id,
            modality=MediaModality.VIDEO,
            placement_id=placement,
            path=f"project://assets/processed/{output.name}",
            sha256=application.transform_receipt.output_sha256,
            fingerprint=fingerprint,
            asset_kind="GENERATED_VIDEO",
            generated=True,
            evidence_capable=False,
            evidence_use="VISUAL_SUPPORT",
            human_review=HUMAN_REVIEW_PENDING,
            production_ready=False,
            audio_policy="REPLACE",
            derived_from=source_id,
            transform_receipt_ref=Path(application.receipt_path).name,
        )
        assets.extend((source, active))
        gates[source_id] = gates[active_id] = GATE_PENDING_HUMAN_REVIEW
        timeline.append(TimelinePlacement(
            placement_id=placement,
            active_asset_id=active_id,
            selection_reason=f"AudioPolicy REPLACE activates derived fixture from {source_id}",
            superseded_asset_ids=[source_id],
        ))
    manifest = MediaManifest(
        assets=assets,
        gate_states=gates,
        timeline=timeline,
        narration={
            "required": True,
            "source": "project://assets/voice/narration.wav",
            "reason": "REPLACE removed fixture audio; M5 narration is required.",
        },
        notes={
            "fixture": True,
            "fixture_notice": "Deterministic local test-pattern clips; not real MiniMax output, not evidence, and not approved.",
            "provider_calls_made": 0,
            "not_production_golden": True,
            "not_founder_approved": True,
        },
    )
    return manifest.write(manifest_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    output = create(args.project if args.project.is_absolute() else ROOT / args.project)
    print(json.dumps({
        "manifest": output.relative_to(ROOT).as_posix(),
        "schema": "contentops.media-manifest/v1",
        "placements": 7,
        "provider_calls": 0,
        "fixture": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
