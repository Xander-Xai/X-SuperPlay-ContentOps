#!/usr/bin/env python3
"""Install, lock, verify and approve a HyperFrames media-use runtime.

Five separate actions, on purpose:

``install``   fetch the approved release and install its locked dependency tree
``lock``      hash the installed tree into a machine-local runtime lock
``verify``    re-check a lock against the committed baseline
``approve``   flip the committed baseline's approval record (a human decision)
``selfcheck`` run local offline operations through the production adapter

Generating a lock never approves anything, and approving never installs
anything. A lock that does not derive from the approved baseline is refused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from process_utils import hidden_run  # noqa: E402

from contentops.media.media_use_adapter import (  # noqa: E402
    BASELINE_SCHEMA,
    DEFAULT_BASELINE,
    RUNTIME_LOCK_SCHEMA,
    package_tree_digest,
    verify_runtime_lock,
)

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_BLOCKED = 5

DEFAULT_LOCKFILE = REPO_ROOT / "runtime" / "media-use-package-lock.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _load_baseline(path: Path) -> Dict[str, Any]:
    payload = _read_json(path)
    if payload.get("schema") != BASELINE_SCHEMA:
        raise SystemExit(f"baseline schema is not {BASELINE_SCHEMA}: {path}")
    return payload


def _emit(payload: Dict[str, Any], code: int) -> int:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return code


# --- commands ---------------------------------------------------------------


def cmd_install(args: argparse.Namespace) -> int:
    """Fetch the approved release and install its dependency tree.

    This is the only command allowed to use the network, and it refuses an
    unapproved baseline so a stray version cannot be installed "for testing"
    and later mistaken for the approved one.
    """
    baseline = _load_baseline(Path(args.baseline))
    if (baseline.get("approval") or {}).get("status") != "approved":
        return _emit(
            {
                "ok": False,
                "state": "BASELINE_NOT_APPROVED",
                "message": "approve the baseline before installing it",
            },
            EXIT_BLOCKED,
        )
    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    node = Path(args.node).expanduser().resolve()
    if not node.is_file():
        return _emit({"ok": False, "state": "NODE_MISSING", "node": str(node)}, EXIT_BLOCKED)
    version = baseline["version"]
    expected_integrity = baseline["integrity"]
    approved_lock = Path(args.lockfile).expanduser()
    if not approved_lock.is_file():
        return _emit({"ok": False, "state": "LOCKFILE_MISSING", "lockfile": str(approved_lock)}, EXIT_BLOCKED)
    if _sha256(approved_lock) != baseline.get("dependency_lock_sha256"):
        return _emit(
            {
                "ok": False,
                "state": "LOCKFILE_MISMATCH",
                "message": "the dependency lock does not match the approved digest",
                "lockfile": str(approved_lock),
            },
            EXIT_BLOCKED,
        )

    runtime_dir.mkdir(parents=True, exist_ok=True)
    package_json = runtime_dir / "package.json"
    _write_json(
        package_json,
        {
            "name": "contentops-media-use-runtime",
            "private": True,
            "version": "0.0.0",
            "dependencies": {baseline["package"]: version},
        },
    )
    lockfile = runtime_dir / "package-lock.json"
    shutil.copyfile(approved_lock, lockfile)
    npm = node.parent / ("npm.cmd" if os.name == "nt" else "npm")
    env = {k: v for k, v in os.environ.items() if k.upper() in {
        "PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA",
        "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMDATA", "COMSPEC", "PATHEXT",
        "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
    }}
    proc = hidden_run(
        [str(npm), "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--loglevel=error"],
        cwd=str(runtime_dir),
        timeout=1800,
        check=False,
        env=env,
    )
    if proc.returncode != 0:
        return _emit(
            {
                "ok": False,
                "state": "INSTALL_FAILED",
                "returncode": proc.returncode,
                "stderr": (proc.stderr or "")[-2000:],
            },
            EXIT_FAIL,
        )

    lockfile = runtime_dir / "package-lock.json"
    lockfile_digest = _sha256(lockfile) if lockfile.is_file() else None
    installed = _read_json(runtime_dir / "node_modules" / baseline["package"] / "package.json")

    problems: List[str] = []
    if installed.get("version") != version:
        problems.append(f"installed {installed.get('version')} != approved {version}")
    if lockfile_digest != baseline.get("dependency_lock_sha256"):
        problems.append(
            "package-lock.json does not match the approved dependency lock; "
            "npm resolved a different tree than the reviewed one"
        )
    tree = _read_json(lockfile) if lockfile.is_file() else {}
    entry = (tree.get("packages") or {}).get(f"node_modules/{baseline['package']}") or {}
    if entry.get("integrity") != expected_integrity:
        problems.append("installed package integrity does not match the approved release")

    return _emit(
        {
            "ok": not problems,
            "state": "INSTALLED" if not problems else "INSTALL_UNVERIFIED",
            "runtime_dir": str(runtime_dir),
            "version": installed.get("version"),
            "package_lock_sha256": lockfile_digest,
            "problems": problems,
        },
        EXIT_OK if not problems else EXIT_BLOCKED,
    )


def cmd_lock(args: argparse.Namespace) -> int:
    """Hash the installed tree into a machine-local lock."""
    baseline_path = Path(args.baseline).expanduser()
    baseline = _load_baseline(baseline_path)
    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    node = Path(args.node).expanduser().resolve()
    entry = runtime_dir / baseline["entry"]
    if not entry.is_file():
        return _emit({"ok": False, "state": "RUNTIME_MISSING", "entry": str(entry)}, EXIT_BLOCKED)
    if not node.is_file():
        return _emit({"ok": False, "state": "NODE_MISSING", "node": str(node)}, EXIT_BLOCKED)

    files: Dict[str, str] = {}
    for path in sorted(runtime_dir.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        files[path.relative_to(runtime_dir).as_posix()] = _sha256(path)
    lockfile = runtime_dir / "package-lock.json"

    payload = {
        "schema": RUNTIME_LOCK_SCHEMA,
        "baseline_sha256": _sha256(baseline_path),
        "package": baseline["package"],
        "version": baseline["version"],
        "integrity": baseline["integrity"],
        "entry": baseline["entry"],
        "verb_prefix": baseline.get("verb_prefix") or ["media-use"],
        "root": str(runtime_dir),
        "node": str(node),
        "node_sha256": _sha256(node),
        "file_count": len(files),
        "files": files,
        "installed": {
            "platform": platform.system().lower(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "package_lock_sha256": _sha256(lockfile) if lockfile.is_file() else None,
        },
    }
    out = Path(args.out).expanduser()
    _write_json(out, payload)
    tree_digest = package_tree_digest(str(baseline["package"]), files)
    verification = verify_runtime_lock(out, baseline_path=baseline_path)
    return _emit(
        {
            "ok": verification.trusted,
            "state": verification.state,
            "lock": str(out),
            "file_count": len(files),
            "package_tree_sha256": tree_digest,
            "baseline_package_tree_sha256": baseline.get("package_tree_sha256"),
            "verification": verification.as_dict(),
        },
        EXIT_OK if verification.trusted else EXIT_BLOCKED,
    )


def cmd_verify(args: argparse.Namespace) -> int:
    verification = verify_runtime_lock(
        Path(args.lock).expanduser() if args.lock else None,
        baseline_path=Path(args.baseline).expanduser() if args.baseline else None,
    )
    return _emit(
        {"ok": verification.trusted, "verification": verification.as_dict()},
        EXIT_OK if verification.trusted else EXIT_BLOCKED,
    )


def cmd_approve(args: argparse.Namespace) -> int:
    """Record a human approval. Refuses to approve without a named approver."""
    if not (args.approved_by or "").strip():
        return _emit(
            {"ok": False, "state": "APPROVER_REQUIRED", "message": "--approved-by is required"},
            EXIT_BLOCKED,
        )
    path = Path(args.baseline).expanduser()
    baseline = _load_baseline(path)
    if not str(baseline.get("package_tree_sha256") or "").strip():
        return _emit(
            {
                "ok": False,
                "state": "TREE_DIGEST_REQUIRED",
                "message": "record package_tree_sha256 from a reviewed install first",
            },
            EXIT_BLOCKED,
        )
    approval = dict(baseline.get("approval") or {})
    if not (approval.get("evidence") or "").strip():
        return _emit(
            {"ok": False, "state": "EVIDENCE_REQUIRED", "message": "record evidence first"},
            EXIT_BLOCKED,
        )
    approval.update({"status": "approved", "approved_by": args.approved_by.strip()})
    approval["approved_at"] = args.approved_at or approval.get("approved_at") or date.today().isoformat()
    baseline["approval"] = approval
    _write_json(path, baseline)
    return _emit({"ok": True, "state": "APPROVED", "baseline": str(path), "approval": approval}, EXIT_OK)


def cmd_selfcheck(args: argparse.Namespace) -> int:
    """Run local, offline media-use operations through the production adapter."""
    from contentops.media.media_use_adapter import MediaUseAdapter, MediaUseError

    adapter = MediaUseAdapter(
        runtime_lock=Path(args.lock).expanduser(),
        baseline=Path(args.baseline).expanduser() if args.baseline else None,
        node=args.node,
        timeout=args.timeout,
    )
    status = adapter.status()
    if not status.available:
        return _emit({"ok": False, "state": "RUNTIME_NOT_TRUSTED", "status": status.as_dict()}, EXIT_BLOCKED)
    project = Path(args.project).expanduser().resolve()
    results: Dict[str, Any] = {"ok": True, "status": status.as_dict()}
    try:
        adopted = adapter.adopt(project_dir=project)
        results["adopt"] = {"count": len(adopted), "assets": adopted[:5]}
        candidates = adapter.candidates("image", project_dir=project)
        results["candidates"] = [c.id for c in candidates]
        resolution = adapter.resolve("sfx", "click", project_dir=project)
        results["resolve"] = {
            "source": resolution.source,
            "importable": resolution.importable,
            "asset_id": resolution.record.get("id"),
            "sha256": resolution.record.get("sha"),
        }
    except MediaUseError as exc:
        results.update({"ok": False, "error": exc.as_dict()})
    return _emit(results, EXIT_OK if results["ok"] else EXIT_BLOCKED)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install", help="install the approved release (network)")
    install.add_argument("--runtime-dir", required=True)
    install.add_argument("--node", required=True, help="pinned node binary for this host")
    install.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    install.add_argument("--lockfile", default=str(DEFAULT_LOCKFILE))
    install.set_defaults(func=cmd_install)

    lock = sub.add_parser("lock", help="hash the installed tree into a machine lock")
    lock.add_argument("--runtime-dir", required=True)
    lock.add_argument("--node", required=True)
    lock.add_argument("--out", required=True)
    lock.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    lock.set_defaults(func=cmd_lock)

    verify = sub.add_parser("verify", help="verify a lock against the approved baseline")
    verify.add_argument("--lock", default="")
    verify.add_argument("--baseline", default="")
    verify.set_defaults(func=cmd_verify)

    approve = sub.add_parser("approve", help="record a human approval of a baseline")
    approve.add_argument("--approved-by", default="")
    approve.add_argument("--approved-at", default="")
    approve.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    approve.set_defaults(func=cmd_approve)

    check = sub.add_parser("selfcheck", help="offline adopt/candidates through the adapter")
    check.add_argument("--lock", required=True)
    check.add_argument("--project", required=True)
    check.add_argument("--baseline", default="")
    check.add_argument("--node", default=None)
    check.add_argument("--timeout", type=float, default=120.0)
    check.set_defaults(func=cmd_selfcheck)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
