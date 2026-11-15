#!/usr/bin/env python3
"""Acquire a public, digest-pinned Easel tree index for later offline checks.

This writes no runtime code, installs no dependencies, and never overwrites an
existing index. It does contact the public upstream tree API or commit archive.
"""
from __future__ import annotations

import json
import sys
import verify_easel_runtime as verifier


def main() -> int:
    record = verifier.load_overlay(verifier.OVERLAY_RECORD)
    upstream = record.get("upstream") or {}
    commit = upstream.get("commit")
    expected = upstream.get("tree_sha256")
    target = verifier.WORKBENCH_TREE_CACHE
    if target.exists() or verifier._linklike(target) or verifier._linklike(target.parent):
        print("BLOCKED: tree index already exists or target is linked", file=sys.stderr)
        return 4
    try:
        try:
            files = verifier.fetch_upstream_tree(verifier.REPO, commit)
            source = "github_tree_api"
        except RuntimeError:
            files = verifier.fetch_upstream_archive_tree(verifier.REPO, commit)
            source = "codeload_commit_archive"
        if verifier.upstream_tree_sha256(files) != expected or len(files) != upstream.get("tree_blob_count"):
            raise ValueError("upstream tree does not match pinned digest and count")
        payload = {"schema": "contentops.easel-upstream-tree/v1", "commit": commit,
                   "source": source, "files": files}
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        print(f"BLOCKED: upstream tree index not acquired: {type(exc).__name__}", file=sys.stderr)
        return 4
    print(f"Saved {len(files)} pinned upstream paths to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
