#!/usr/bin/env python3
"""Offline native graphic package export for existing non-X editorial targets."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.platforms import graphic_specs, multichannel as mc
from contentops.workflow import shared_copy

SUPPORTED = {"wechat_article", "zhihu", "csdn", "juejin", "toutiao", "weibo"}


def verify_images(root, project, package):
    # Check the existing image rights receipt and bytes again before export.
    from contentops.media.rights_gate import validate_request_rights
    for item in package.get("images") or []:
        path = item["path"]
        image = shared_copy.inside(root, path[len("repo://"):]) if path.startswith("repo://") else shared_copy.inside(project, path)
        import hashlib
        if not image.is_file() or hashlib.sha256(image.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("graphic asset drift")
        current_rights = validate_request_rights({"rights": item["rights"]}, project)
        if current_rights != item["rights"]:
            raise ValueError("graphic asset rights receipt changed")


def build(root, project, platforms):
    root, project = Path(root).resolve(), Path(project).resolve()
    shared_copy.project_ref(root, project)
    if not platforms or len(set(platforms)) != len(platforms):
        raise ValueError("select distinct configured platforms")
    allowed = SUPPORTED.intersection(graphic_specs.platform_ids())
    if set(platforms) - allowed:
        raise ValueError("only existing non-X editorial targets; no Xiaohongshu image")
    package_file = shared_copy.inside(project, "receipts/graphic-package.json")
    package = shared_copy.document(package_file)
    lineage = shared_copy.verify_package(root, project, package)
    package["_package_root"] = str(project)
    verify_images(root, project, package)
    outputs = []
    for pid in platforms:
        adapter = mc.MultiChannelAdapter(pid, expected_bundle_sha256=package["bundle_sha256"], repo_root=root)
        draft = adapter.pack(package, {"account_slug": package["account"]})
        validation = adapter.validate(draft)
        receipt = adapter.prepare_handoff(draft)
        # A condensed hard-limit draft is not a safe projection. Preserve the
        # blocker but do not write the lossy text as a copyable artifact.
        hard = any(str(b).startswith(("BODY_OVER_HARD", "BODY_REWRITTEN", "TITLE_OVER_HARD")) for b in draft.blockers)
        preview = None if hard or not validation.ok else draft.body
        entry = {"schema": "contentops.shared-graphic-offline/v1", "platform": pid,
                 "shared_copy_id": lineage["shared_copy_id"], "copy_sha256": lineage["copy_sha256"],
                 "claim_lineage": lineage["claim_lineage"], "source_package_sha256": shared_copy.digest(package_file.read_bytes()),
                 "draft": draft.as_dict() if preview is not None else None,
                 "validation": validation.as_dict(), "receipt": receipt,
                 "status": "AWAITING_PLATFORM_REVIEW" if preview is not None else "BLOCKED",
                 "publish_authorized": False, "production_ready": False, "external_action": "none"}
        outputs.append(entry)
    # Directory identity binds the exact source and selected native output.
    key = shared_copy.digest(shared_copy.encode(outputs))[:24]
    for entry in outputs:
        name = entry["platform"]
        file = shared_copy.inside(project, "receipts/shared-graphic/" + key + "/" + name + ".json")
        shared_copy.write_once(file, shared_copy.json_bytes(entry))
    return {"schema": "contentops.shared-graphic-batch/v1", "shared_copy_id": lineage["shared_copy_id"],
            "batch": key, "platforms": [{"platform": e["platform"], "status": e["status"],
                                        "native_format": e["receipt"].get("native_format") or graphic_specs.spec(e["platform"])["native_format"]}
                                       for e in outputs], "external_action": "none", "publish_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", required=True, type=Path)
    p.add_argument("--platform", action="append", required=True)
    a = p.parse_args(argv)
    try:
        print(json.dumps(build(ROOT, a.project, a.platform), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
