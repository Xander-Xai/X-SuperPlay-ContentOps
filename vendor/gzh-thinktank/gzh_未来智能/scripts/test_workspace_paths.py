#!/usr/bin/env python3
"""Regression tests for the external article-workspace contract."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from workspace_audit import audit
from workspace_lifecycle import transition
from workspace_paths import (
    ARTIFACT_ROOT_ENV,
    DEFAULT_ARTIFACT_ROOT,
    ROOT,
    allocate_workspace,
    resolve_article_workspace,
    resolve_workspace_root,
)


def main() -> int:
    assert DEFAULT_ARTIFACT_ROOT == ROOT.parent / "production"
    old_root = os.environ.get(ARTIFACT_ROOT_ENV)
    try:
        with tempfile.TemporaryDirectory(prefix="gzh-workspace-contract-") as raw:
            base = Path(raw).resolve()
            os.environ[ARTIFACT_ROOT_ENV] = str(base)
            first, first_id, first_seq = allocate_workspace("第一篇文章", date_value="20260813")
            second, second_id, second_seq = allocate_workspace("第二篇文章", date_value="20260813")
            assert first_id == "THK-20260813-001" and first_seq == 1
            assert second_id == "THK-20260813-002" and second_seq == 2
            assert first.parent == base / "active"
            assert (first / "work").is_dir() and (first / "exports").is_dir()
            assert resolve_article_workspace(first) == first
            assert resolve_article_workspace("active/" + first.name) == first
            delivered = transition(str(second), "delivered", root=base)
            assert delivered.parent == base / "delivered"
            archived = transition(str(delivered), "archive", root=base)
            assert archived.parent == base / "archive"
            try:
                resolve_workspace_root("drafts")
            except ValueError as exc:
                assert "drafts" in str(exc)
            else:
                raise AssertionError("legacy drafts root was accepted")
            registry = json.loads((base / "registry" / "workspace-index.json").read_text(encoding="utf-8"))
            assert [row["workspace_id"] for row in registry["workspaces"]] == [first_id, second_id]
            assert registry["workspaces"][1]["lifecycle"] == "archive"
            assert not audit(base), audit(base)
    finally:
        if old_root is None:
            os.environ.pop(ARTIFACT_ROOT_ENV, None)
        else:
            os.environ[ARTIFACT_ROOT_ENV] = old_root
    print("WORKSPACE PATH TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
