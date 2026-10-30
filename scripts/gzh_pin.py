#!/usr/bin/env python3
"""The WeChat workflow's durable pin: one bundle, one commit, one check.

The Future Intelligence 公众号 workflow lives in its own repository
(`D:\\Projects\\gzh_x未来智能`). Its local history is **divergent** from GitHub
origin: `origin/main` is `e9303d1`, the working copy is `93645f1`, and the four
local commits exist on no remote. So that folder is not a cache of something
reproducible — it is the only copy, and the pattern `verify_easel_runtime.py` uses
(compare against a live upstream tree) cannot check it.

What makes it durable instead is a cold archive outside both repositories:
`D:\\Archives\\repos\\gzh-thinktank\\2026-10-30\\gzh-thinktank.bundle`, verified at
creation to restore a clone with an identical tree. This module records what that
archive must reproduce and refuses a checkout that disagrees.

Restore:

    git clone <bundle> D:\\Projects\\gzh-Future-Intelligence
    python scripts/gzh_pin.py --checkout D:\\Projects\\gzh-Future-Intelligence

Usage
-----
    python scripts/gzh_pin.py
    python scripts/gzh_pin.py --checkout D:\\Projects\\gzh-Future-Intelligence --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from process_utils import hidden_run  # noqa: E402

SCHEMA = "contentops.external-pin/v1"

#: The same account under two names. Neither repository may rename it silently.
ACCOUNT = {
    "gzh_account_id": "thinktank",
    "contentops_account_slug": "x-superplay-future-intelligence",
}

UPSTREAM = "https://github.com/yandexuanxuan/gzh-Future-Intelligence.git"

PIN = {
    "repo": UPSTREAM,
    "commit": "93645f178418c1e0a03cbb3fc06a7f87ee11f631",
    "tree": "7b75e4e840b29a18f5262c0e81e64c080c274c6a",
    "tracked_files": 718,
    "commit_subject": "fix: allow verified draft resubmission",
    #: The remote this checkout diverged from. Recorded so nobody assumes that
    #: cloning upstream reproduces this history.
    "diverged_from": {"ref": "origin/main", "commit": "e9303d18066a4232838b9dafff6827f6b4e8adf1"},
    "bundle": Path(r"D:\Archives\repos\gzh-thinktank\2026-10-30\gzh-thinktank.bundle"),
    "bundle_sha256": "fc6965c076af07d1e6842b06bb11afae760d4315d950545604a041a97e4fb4e7",
    "bundle_bytes": 14724716,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


#: The copy that lives in this repository, imported from the checkout above.
#: `vendor/gzh-thinktank/MANIFEST.md` explains what was left out and why.
VENDORED = ROOT / "vendor" / "gzh-thinktank" / "gzh_未来智能"
VENDORED_FILES = 667
VENDORED_DIGEST = "39d3ee1cdc80c9a44e598586cf5199bf4a297c016d0fd82295464ca76ba48e52"


def vendored_digest(root: Path) -> tuple[int, str]:
    """Hash the vendored tree by content, not by commit.

    The vendored copy is not a git checkout (the import dropped caches and the
    credential-bearing config), so a tree object cannot identify it. Hashing every
    file's path and bytes can, and it also catches an edit made in place — which is
    exactly what "do not edit the vendor tree" means.
    """
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        # Running the vendored workflow writes __pycache__ inside it. Those are
        # interpreter output, not content, and excluding them is what lets the pin
        # survive the workflow being used at all.
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rows.append((path.relative_to(root).as_posix(), _sha256(path)))
    digest = hashlib.sha256()
    for rel, file_digest in rows:
        digest.update(rel.encode("utf-8") + b"\0" + file_digest.encode("ascii") + b"\n")
    return len(rows), digest.hexdigest()


def _check_vendored() -> List[Dict[str, Any]]:
    if not VENDORED.is_dir():
        return [{"id": "vendored_present", "ok": False, "path": str(VENDORED)}]
    count, digest = vendored_digest(VENDORED)
    return [
        {"id": "vendored_present", "ok": True, "path": str(VENDORED)},
        {"id": "vendored_files", "ok": count == VENDORED_FILES,
         "value": count, "expected": VENDORED_FILES},
        {"id": "vendored_digest", "ok": digest == VENDORED_DIGEST,
         "value": digest, "expected": VENDORED_DIGEST},
    ]


def _git(cwd: Path, *args: str):
    return hidden_run(["git", *args], cwd=str(cwd), timeout=120)


def _check(bundle: Path) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    present = bundle.is_file()
    checks.append({"id": "bundle_present", "ok": present, "path": str(bundle)})
    if not present:
        return checks
    checks.append({
        "id": "bundle_bytes", "ok": bundle.stat().st_size == PIN["bundle_bytes"],
        "value": bundle.stat().st_size, "expected": PIN["bundle_bytes"],
    })
    digest = _sha256(bundle)
    checks.append({
        "id": "bundle_digest", "ok": digest == PIN["bundle_sha256"],
        "value": digest, "expected": PIN["bundle_sha256"],
    })
    return checks


def _check_checkout(checkout: Path) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    if not checkout.exists():
        return [{"id": "checkout_present", "ok": False, "path": str(checkout)}]
    head = _git(checkout, "rev-parse", "HEAD")
    if head.returncode != 0:
        return [{"id": "checkout_is_repo", "ok": False, "path": str(checkout)}]
    checks.append({"id": "checkout_present", "ok": True, "path": str(checkout)})
    commit = (head.stdout or "").strip()
    checks.append({"id": "commit", "ok": commit == PIN["commit"],
                   "value": commit, "expected": PIN["commit"]})
    tree = _git(checkout, "rev-parse", "HEAD^{tree}")
    tree_id = (tree.stdout or "").strip()
    checks.append({"id": "tree", "ok": tree_id == PIN["tree"],
                   "value": tree_id, "expected": PIN["tree"]})
    listed = _git(checkout, "ls-files")
    count = len([line for line in (listed.stdout or "").splitlines() if line.strip()])
    checks.append({"id": "tracked_files", "ok": count == PIN["tracked_files"],
                   "value": count, "expected": PIN["tracked_files"]})
    return checks


def verify(checkout: Optional[Path] = None, bundle: Optional[Path] = None) -> Dict[str, Any]:
    bundle = bundle or PIN["bundle"]
    checks = _check(bundle) + _check_vendored()
    if checkout is not None:
        checks += _check_checkout(checkout)
    failures = [check["id"] for check in checks if not check["ok"]]
    return {
        "schema": SCHEMA,
        "account": ACCOUNT,
        "pin": {key: (str(value) if isinstance(value, Path) else value)
                for key, value in PIN.items()},
        "bundle": str(bundle),
        "checkout": str(checkout) if checkout else None,
        "ok": not failures,
        "failures": failures,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the pinned 公众号 workflow archive.")
    parser.add_argument("--checkout", default=None,
                        help="a restored clone to verify in addition to the bundle")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = verify(Path(args.checkout) if args.checkout else None)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"repository  {result['pin']['repo']}")
        print(f"commit      {result['pin']['commit']}  ({result['pin']['commit_subject']})")
        print(f"tree        {result['pin']['tree']}")
        print(f"files       {result['pin']['tracked_files']}")
        print(f"bundle      {result['bundle']}")
        for check in result["checks"]:
            print(f"  {'OK  ' if check['ok'] else 'FAIL'} {check['id']}")
        if result["failures"]:
            print()
            print("FAILED: " + ", ".join(result["failures"]))
            print("Restore with: git clone <bundle> D:\\Projects\\gzh-Future-Intelligence")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
