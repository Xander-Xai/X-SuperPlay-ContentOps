#!/usr/bin/env python3
"""Validate a project's WeChat article HTML and build the browser preview.

    python scripts/render_article.py projects/my-article
    python scripts/render_article.py projects/my-article --html assets/article/article.html
    python scripts/render_article.py projects/my-article --json
    python scripts/render_article.py projects/my-article --workbench-runtime

What it runs (nothing else):
    1. ``.runtime/easel/skills/{openclaw|builtin}/gzh-design/scripts/validate_gzh_html.py`` — WeChat HTML validation
    2. ``.runtime/easel/skills/{openclaw|builtin}/gzh-design/scripts/wrap_preview.py`` — wrap preview with copy button

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
import hashlib
import json
import os
import sys
import uuid
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
from contentops.easel.path_safety import is_linklike as linked  # noqa: E402

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
    parser.add_argument("--input", dest="input_file", help="project-relative or absolute path to article-input.json")
    parser.add_argument("--runtime-root", help="override .runtime/easel root directory")
    parser.add_argument("--workbench-runtime", action="store_true",
                        help="use v0.3 only after upstream, overlay and profile verification")
    parser.add_argument("--json", action="store_true", help="print receipt JSON to stdout")
    args = parser.parse_args(argv)

    if args.workbench_runtime and args.runtime_root:
        parser.error("--runtime-root and --workbench-runtime are mutually exclusive")
    if args.workbench_runtime and args.preview:
        parser.error("--preview cannot override the isolated candidate output")

    project_dir = Path(args.project)
    if not project_dir.is_absolute():
        project_dir = ROOT / project_dir
    runtime_root = Path(args.runtime_root) if args.runtime_root else RUNTIME_ROOT
    candidate_dir = None
    candidate_id = None
    candidate_commit = None
    overlay_digest = None

    def candidate_failure(stage: str, reason: str) -> None:
        """Record a bounded failure after a candidate run has been allocated."""
        if candidate_id is None:
            return
        target = project_dir / "receipts" / f"gzh-article-v030-{candidate_id}.json"
        failure = {
            "schema": "contentops.easel-candidate-article-failure/v1",
            "candidate_runtime": "easel-v0.3.0", "candidate_commit": candidate_commit,
            "candidate_run_id": candidate_id, "project": project_dir.name,
            "status": "BLOCKED", "stage": stage, "reason_code": reason,
            "production_ready": False, "publish_authorized": False,
            "human_review": "PENDING", "qc": "NOT_RUN",
        }
        try:
            with target.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(failure, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        except OSError:
            sys.stderr.write("BLOCKED: candidate failure receipt could not be written\n")

    if args.workbench_runtime:
        projects = ROOT / "projects"
        local_projects = projects / "_local"
        if (project_dir.parent not in (projects, local_projects) or linked(projects) or linked(project_dir)
                or (project_dir.parent == local_projects and linked(local_projects))
                or not project_dir.is_dir() or project_dir.resolve().parent != project_dir.parent.resolve()):
            sys.stderr.write("BLOCKED: candidate project must be a non-linked projects or projects/_local child\n")
            return BLOCKED_EXIT
        project_dir = project_dir.resolve()
        overlay_path = ROOT / "runtime" / "easel-workbench-overlay.json"
        try:
            if linked(overlay_path) or linked(overlay_path.parent):
                raise ValueError("linked overlay")
            overlay_bytes = overlay_path.read_bytes()
            overlay = json.loads(overlay_bytes.decode("utf-8"))
            recorded_commit = (overlay.get("upstream") or {}).get("commit")
            overlay_digest = hashlib.sha256(overlay_bytes).hexdigest()
        except (OSError, UnicodeError, ValueError, AttributeError, TypeError):
            sys.stderr.write("BLOCKED: candidate overlay record is unavailable or invalid\n")
            return BLOCKED_EXIT
        from resolve_easel import resolve_easel_workbench
        resolved = resolve_easel_workbench(ROOT)
        if resolved["status"] != "OK":
            sys.stderr.write("BLOCKED: Easel workbench is not verified: "
                             + "; ".join(resolved.get("reasons", ["unknown"])) + "\n")
            return BLOCKED_EXIT
        runtime_root = Path(resolved["easel_dir"])
        candidate_commit = resolved.get("commit")
        if candidate_commit != recorded_commit:
            sys.stderr.write("BLOCKED: candidate identity changed during verification\n")
            return BLOCKED_EXIT
        work = project_dir / "work"
        candidates = work / "easel-v030-article"
        receipts = project_dir / "receipts"
        for directory, parent in ((work, project_dir), (candidates, work), (receipts, project_dir)):
            if linked(directory):
                sys.stderr.write("BLOCKED: linked candidate output directory\n")
                return BLOCKED_EXIT
            directory.mkdir(exist_ok=True)
            if not directory.is_dir() or directory.resolve().parent != parent.resolve():
                sys.stderr.write("BLOCKED: unsafe candidate output directory\n")
                return BLOCKED_EXIT
        candidate_id = str(uuid.uuid4())
        candidate_dir = candidates / candidate_id
        candidate_dir.mkdir()

    try:
        p = plan(
            project_dir,
            html_path=args.html,
            preview_path=(candidate_dir / "preview.html") if candidate_dir else args.preview,
            input_file=args.input_file,
            runtime_root=runtime_root,
        )
    except ArticleError as err:
        candidate_failure("plan", err.code)
        sys.stderr.write(f"BLOCKED: {err}\n")
        return BLOCKED_EXIT
    except Exception as exc:
        candidate_failure("plan", type(exc).__name__)
        sys.stderr.write(f"ERROR: unexpected planning failure: {type(exc).__name__}\n")
        return BLOCKED_EXIT

    python_bin = _article_python()

    candidate_runner = _runner
    if candidate_dir is not None:
        def candidate_runner(argv, *, timeout: int = 120):
            names = ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "LANG")
            env = {name: os.environ[name] for name in names if name in os.environ}
            env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
                       TEMP=str(candidate_dir), TMP=str(candidate_dir))
            return hidden_run(argv, timeout=timeout, check=False, env=env)

    try:
        receipt = run(p, runner=candidate_runner, article_python=python_bin)
    except ArticleError as err:
        candidate_failure("render", err.code)
        sys.stderr.write(f"FAILED: {err}\n")
        return BLOCKED_EXIT
    except Exception as exc:
        candidate_failure("render", type(exc).__name__)
        sys.stderr.write(f"ERROR: unexpected failure: {type(exc).__name__}\n")
        return BLOCKED_EXIT

    if candidate_dir is not None:
        try:
            if linked(overlay_path) or hashlib.sha256(overlay_path.read_bytes()).hexdigest() != overlay_digest:
                raise ValueError("overlay changed")
        except (OSError, ValueError):
            candidate_failure("identity", "CANDIDATE_IDENTITY_CHANGED")
            sys.stderr.write("BLOCKED: candidate overlay changed during article preview\n")
            return BLOCKED_EXIT
        receipt.update({"candidate_runtime": "easel-v0.3.0", "candidate_commit": candidate_commit,
                        "candidate_run_id": candidate_id, "production_ready": False,
                        "publish_authorized": False, "human_review": "PENDING",
                        "image_rights": "NOT_VERIFIED", "overlay_record_sha256": overlay_digest})
        # The shared article receipt defaults to the production v0.2.1 pin.
        # This run used the verified candidate, so identify that runtime here.
        receipt["tools"]["easel_runtime_commit"] = candidate_commit
        receipt["cannot"].append("local image presence and hashes do not establish usage rights")
        receipt_target = p.project / "receipts" / f"gzh-article-v030-{candidate_id}.json"
        try:
            with receipt_target.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(receipt, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            receipt_path = receipt_target
        except OSError:
            sys.stderr.write("BLOCKED: candidate article receipt could not be written without overwriting\n")
            return BLOCKED_EXIT
    else:
        receipt_path = write_receipt(receipt, p.project)

    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    else:
        print(f"PASS: article verified and wrapped -> {receipt_path}")
        print(f"      preview: {p.preview_out}")
        print(f"      span leaf wrappers: {receipt['validation']['span_leaf_count']}")
        print(f"      image files checked: {len(receipt['images'])} (usage rights not established)")
        print(f"      status: {receipt['status']} (production_ready: {receipt['production_ready']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
