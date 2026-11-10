#!/usr/bin/env python3
"""Validate a project's WeChat article HTML and build the browser preview.

    python scripts/render_article.py projects/my-article
    python scripts/render_article.py projects/my-article --html assets/article/article.html
    python scripts/render_article.py projects/my-article --json

What it runs (nothing else):
    1. ``.runtime/easel/skills/openclaw/gzh-design/scripts/validate_gzh_html.py`` — WeChat HTML validation
    2. ``.runtime/easel/skills/openclaw/gzh-design/scripts/wrap_preview.py`` — wrap preview with copy button

and writes ``projects/<slug>/receipts/gzh-article.json``.

It adds no renderer, starts no host, calls no agent, and accesses no network.
A validation PASS is not an approval: the receipt keeps
``production_ready: false`` and ``publish_authorized: false``.

Interpreter: uses explicit ``CONTENTOPS_PYTHON`` or falls back to ``sys.executable``.
Never scans or guesses interpreters automatically.

Exit codes: 0 article validated and wrapped; 4 blocked or validation failed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.graphic.articles import (  # noqa: E402
    ArticleError,
    plan,
    run,
    write_receipt,
)
from process_utils import hidden_run  # noqa: E402

BLOCKED_EXIT = 4
RUNTIME_ROOT = ROOT / ".runtime" / "easel"


def _article_python() -> str:
    """The interpreter for article tools, strictly explicit.

    Uses CONTENTOPS_PYTHON if provided; otherwise current sys.executable.
    Automatic scanning or guessing across the filesystem is prohibited by policy.
    """
    return os.environ.get("CONTENTOPS_PYTHON") or sys.executable


def _runner(argv, *, timeout: int = 120):
    """Run an article tool through the repository's hidden-window subprocess layer."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return hidden_run(argv, timeout=timeout, check=False, env=env)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("project", help="path to project directory (e.g. projects/gzh-qc-gap)")
    parser.add_argument("--html", help="override relative or absolute path to article.html")
    parser.add_argument("--preview", help="override path to output preview html")
    parser.add_argument("--input", dest="input_file", help="path to article-input.json")
    parser.add_argument("--runtime-root", help="override .runtime/easel root directory")
    parser.add_argument("--json", action="store_true", help="print receipt JSON to stdout")
    args = parser.parse_args(argv)

    project_dir = Path(args.project)
    runtime_root = Path(args.runtime_root) if args.runtime_root else RUNTIME_ROOT

    try:
        p = plan(
            project_dir,
            html_path=args.html,
            preview_path=args.preview,
            input_file=args.input_file,
            runtime_root=runtime_root,
        )
    except ArticleError as err:
        sys.stderr.write(f"BLOCKED: {err}\n")
        return BLOCKED_EXIT

    python_bin = _article_python()

    try:
        receipt = run(p, runner=_runner, article_python=python_bin)
    except ArticleError as err:
        sys.stderr.write(f"FAILED: {err}\n")
        return BLOCKED_EXIT
    except Exception as exc:
        sys.stderr.write(f"ERROR: unexpected failure: {exc}\n")
        return BLOCKED_EXIT

    receipt_path = write_receipt(receipt, p.project)

    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    else:
        print(f"PASS: article verified and wrapped -> {receipt_path}")
        print(f"      preview: {p.preview_out}")
        print(f"      span leaf wrappers: {receipt['validation']['span_leaf_count']}")
        print(f"      images verified: {len(receipt['images'])}")
        print(f"      status: {receipt['status']} (production_ready: {receipt['production_ready']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
