#!/usr/bin/env python3
"""Re-render a project's pinned-source anchors with the reading-first renderer.

The first auto-motion run produced its anchors outside any checked-in code
path, so the stills could not be reproduced and quietly drifted from what
Huashu's ``t2_keynote_ui`` grammar needs (the code sat in the top third at
20 px, ~60% of the frame was flat surface colour, and the OCR rectangles
spanned the whole column so the camera could only push 1.14x). This script
makes the anchors a build product again:

* the excerpt window, wrapping, syntax tone and pixel geometry all come from
  :mod:`contentops.media.source_anchor`;
* the anchor's ``text_layout`` is written back into ``sources/assets.json`` so
  the motion planner can aim the camera at real source lines;
* the pinned document's sha256 is re-checked before anything is drawn, so an
  edit to the vendored source cannot silently change what the film shows.

It renders stills only. It never calls a paid service, never touches M5
receipts and never marks anything publishable.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from contentops.media.motion_planner import _labelled_steps, _topic_kind  # noqa: E402
from contentops.media.source_anchor import render_anchor, render_flow_anchor  # noqa: E402

# The explanatory account tells its story with drawn schematics; the evidence-led
# account shows the pinned source itself. Same renderer grammar, different
# still -- which is what makes the two films different films rather than twins.
VECTOR_LED_ACCOUNTS = {"x-superplay-future-intelligence"}
TRANSITION_STEPS = {
    "x-superplay-1024": ["看真实源码", "对照配置项", "核对来源"],
    "x-superplay-future-intelligence": ["先讲机制", "落到代码", "核对来源"],
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _roles(project: Path) -> Dict[str, str]:
    script = _read(project / "script" / "script.json")
    return {str(shot.get("asset_id") or ""): str(shot.get("visual_role") or "explain")
            for shot in script.get("visual_shots") or []}


def _focus(project: Path, asset_id: str) -> str:
    script = _read(project / "script" / "script.json")
    for shot in script.get("visual_shots") or []:
        if str(shot.get("asset_id") or "") == asset_id:
            return str(shot.get("visual_focus") or "")
    return ""

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _palette(dna: Dict[str, Any], account_id: str) -> Dict[str, str]:
    visual = dna.get("visual") or {}
    profile = (visual.get("motion") or {}).get("motion_profile") or \
        visual.get("motion_profile") or {}
    variants = profile.get("style_variants") or {}
    recommended = str(profile.get("recommended_variant") or "")
    palette = variants.get(recommended) or profile.get("palette") or {}
    keys = ("bg", "surface", "ink", "sub", "accent", "accent2")
    if all(str(palette.get(key) or "").startswith("#") for key in keys):
        return {key: str(palette[key]) for key in keys}
    raise SystemExit(f"account {account_id} has no complete six-colour palette")


def _queries(project: Path, asset_id: str) -> List[str]:
    """Everything the film says while this still is on screen."""
    script = _read(project / "script" / "script.json")
    lines = {str(row.get("id") or ""): row for row in script.get("lines") or []}
    claims_path = project / "script" / "claims.json"
    claims = {str(row.get("id") or ""): row for row in
              (_read(claims_path).get("claims") or [])} if claims_path.is_file() else {}
    phrases: List[str] = []
    for shot in script.get("visual_shots") or []:
        if str(shot.get("asset_id") or "") != asset_id:
            continue
        segment = lines.get(str(shot.get("segment_id") or ""), {})
        for source in (shot, segment):
            for key in ("visual_focus", "narration", "caption"):
                value = str(source.get(key) or "").strip()
                if value and value not in phrases:
                    phrases.append(value)
        claim = claims.get(str(shot.get("claim") or segment.get("claim") or ""))
        if claim:
            value = str(claim.get("text") or "").strip()
            if value and value not in phrases:
                phrases.append(value)
    return phrases


def _account_id(project: Path) -> str:
    config = project / "project.yaml"
    if not config.is_file():
        raise SystemExit("project.yaml is missing; refusing to guess the account")
    match = re.search(r"^account_slug:\s*[\"']?([A-Za-z0-9_-]+)", config.read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit("project.yaml declares no account_slug")
    return match.group(1)


def rebuild(project: Path, *, dry_run: bool = False) -> Dict[str, Any]:
    project = project.resolve()
    account_id = _account_id(project)
    dna = _read(ROOT / "config" / "accounts" / f"{account_id}.json")
    palette = _palette(dna, account_id)

    manifest_path = project / "sources" / "assets.json"
    manifest = _read(manifest_path)
    rebuilt, skipped = [], []
    used_lines: Dict[str, set] = {}
    asset_ordinal: Dict[str, int] = {}
    # A short document (this repo's config.py is 38 lines) cannot supply one
    # distinct excerpt per shot. Rather than render a five-line card into a
    # 19-row body -- which is exactly the "dead background" failure the still
    # is supposed to fix -- the second shot shares the same still and the
    # motion planner moves the camera to a different block of it.
    by_sha: Dict[str, Dict[str, Any]] = {}
    roles = _roles(project)
    vector_led = account_id in VECTOR_LED_ACCOUNTS
    for row in manifest.get("assets") or []:
        if not isinstance(row, dict):
            continue
        asset_type = str(row.get("type") or "").upper()
        if asset_type not in {"CODE_SNAPSHOT", "GENERATED_IMAGE"}:
            continue
        asset_id = str(row.get("id") or "")
        role = roles.get(asset_id, "explain")
        document = str(row.get("source_document") or "")
        target = Path(str(row.get("repo_path") or ""))
        if target.suffix.lower() not in IMAGE_SUFFIXES:
            skipped.append({"id": asset_id, "reason": "not a still"})
            continue
        absolute_target = target if target.is_absolute() else ROOT / target
        query_text = _focus(project, asset_id) or " ".join(_queries(project, asset_id))

        if (vector_led and role != "proof") or (asset_type == "GENERATED_IMAGE" and not document):
            steps = (TRANSITION_STEPS[account_id] if role == "transition"
                     else [label for label, _icon in
                           _labelled_steps(_topic_kind(query_text), query_text)])
            if dry_run:
                rebuilt.append({"id": asset_id, "kind": "concept", "steps": steps})
                continue
            rendered = render_flow_anchor(
                title=(query_text.split(";")[0] or asset_id).strip()[:28],
                steps=steps, palette=palette, out_path=absolute_target,
                provenance="schematic drawn from the reviewed narration · no runtime output shown")
            row.update({
                "sha256": rendered.sha256,
                "anchor_canvas": [rendered.width, rendered.height],
                "text_layout": rendered.layout(),
                "anchor_kind": "CONCEPT_SCHEMATIC",
                "origin": "Deterministic concept card drawn from the reviewed narration",
            })
            row.pop("ocr_regions", None)
            row.pop("display_transform", None)
            rebuilt.append({"id": asset_id, "kind": "concept", "sha256": rendered.sha256[:12],
                            "target": row.get("repo_path")})
            continue

        if not document:
            skipped.append({"id": asset_id, "reason": "no source document"})
            continue
        source_path = project / document
        if not source_path.is_file():
            skipped.append({"id": asset_id, "reason": f"missing {document}"})
            continue
        expected = str(row.get("source_document_sha256") or "")
        if expected and _sha(source_path) != expected:
            raise SystemExit(f"pinned source bytes changed for {document}; refusing to redraw")
        queries = _queries(project, asset_id)
        source_url = str(row.get("source_url") or "")
        repository = source_url.split("github.com/")[-1].split("/blob/")[0] if "github.com/" in source_url \
            else "pinned source"
        absolute_target = target if target.is_absolute() else ROOT / target
        # How many readable excerpts a document can actually supply. A 38-line
        # config file cannot feed five 19-row cards; asking for them produces
        # near-empty stills, so the surplus shots share the first card instead.
        line_count = len(source_path.read_text(encoding="utf-8").splitlines())
        capacity = max(1, line_count // 12)
        ordinal = asset_ordinal.get(document, 0)
        asset_ordinal[document] = ordinal + 1
        exclude = used_lines.get(document, set()) if ordinal < capacity else set()
        if dry_run:
            rebuilt.append({"id": row.get("id"), "queries": len(queries),
                            "capacity": capacity, "ordinal": ordinal})
            continue
        rendered = render_anchor(
            source_text=source_path.read_text(encoding="utf-8"),
            filename=source_path.name,
            title="",
            repository=repository,
            commit=str(row.get("source_commit") or ""),
            spdx=str(row.get("source_spdx_license") or ""),
            palette=palette,
            queries=queries,
            out_path=absolute_target,
            exclude_lines=exclude)
        used_lines.setdefault(document, set()).update(number - 1 for number in rendered.source_lines)
        shared = by_sha.get(rendered.sha256)
        if shared and shared.get("document") == document and not shared.get("dry_run"):
            # Only remove a file that is genuinely redundant. On a second run the
            # surplus row already points at the shared card, and unlinking it
            # would delete the card the whole document depends on.
            if shared["repo_path"] != row.get("repo_path"):
                absolute_target.unlink(missing_ok=True)
            row.update({
                "repo_path": shared["repo_path"],
                "sha256": rendered.sha256,
                "anchor_canvas": [rendered.width, rendered.height],
                "text_layout": rendered.layout(),
                "origin": "Deterministic excerpt card rendered from pinned repository bytes",
                "shared_with": shared["id"],
            })
            row.pop("ocr_regions", None)
            row.pop("display_transform", None)
            rebuilt.append({"id": row.get("id"), "sha256": rendered.sha256[:12],
                            "lines": len(rendered.lines), "target": shared["repo_path"],
                            "shared_with": shared["id"]})
            continue
        by_sha[rendered.sha256] = {"id": row.get("id"), "document": document,
                                   "repo_path": row.get("repo_path"), "dry_run": dry_run}
        row.update({
            "sha256": rendered.sha256,
            "anchor_canvas": [rendered.width, rendered.height],
            "text_layout": rendered.layout(),
            "origin": "Deterministic excerpt card rendered from pinned repository bytes",
        })
        # The old boxes were full-column OCR detections injected by hand; the
        # planner now reads text_layout, and leaving them behind would let a
        # stale rectangle win if a layout were ever missing.
        row.pop("ocr_regions", None)
        row.pop("display_transform", None)
        rebuilt.append({"id": row.get("id"), "sha256": rendered.sha256[:12],
                        "lines": len(rendered.lines), "target": str(absolute_target.relative_to(ROOT))})
    if not dry_run:
        _write(manifest_path, manifest)
    return {"schema": "contentops.source-anchor-rebuild/v1", "project": project.name,
            "account_id": account_id, "rebuilt": rebuilt, "skipped": skipped,
            "dry_run": dry_run, "production_ready": False, "publish_authorized": False}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", help="project directory under projects/<slug>")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = rebuild(Path(args.project), dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
