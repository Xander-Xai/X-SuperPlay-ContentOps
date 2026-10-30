#!/usr/bin/env python3
"""The X growth workflow's pin: one commit, one tree, one digest.

`Xander-Xai/X-SuperPlay-X-Growth-OS` is a private repository owned by the same
person as this one. It is not upstream in the Easel sense (nothing here tracks
it), and it has no release: `main` at `3154db49` is the whole of it. Importing
it verbatim is what makes the X track reproducible after that repository is
archived, and this module is what makes "verbatim" checkable.

Unlike the 公众号 pin (`gzh_pin.py`) there is no bundle and no divergence to
explain: Growth-OS history is linear and its remote still holds it, so a
`--checkout` of a fresh clone is a valid second copy. The pin therefore records
the commit and tree, and refuses a checkout that disagrees.

The vendored tree is hashed by content rather than by commit, because the copy
in this repository is not a git checkout. `MANIFEST.md` sits inside
`vendor/x-growth-os/` and is ours, not upstream's, so it is excluded from the
digest — otherwise editing our own provenance notes would look like an edit to
vendored code.

Usage
-----
    python scripts/x_growth_pin.py
    python scripts/x_growth_pin.py --checkout D:\\Temp\\x-growth-os --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from process_utils import hidden_run  # noqa: E402

SCHEMA = "contentops.external-pin/v1"

PIN = {
    "repo": "https://github.com/Xander-Xai/X-SuperPlay-X-Growth-OS.git",
    "access": "private",
    "commit": "3154db49ad2b070bf5dea2d8fb9a1fc4fdba6f44",
    "tree": "a19584f16d0cb26f231e554646358f1307bb012e",
    "tracked_files": 64,
    "total_bytes": 345872,
    "commit_subject": "ci(x): make URL integrity checks valid after real publish receipts arrive",
    #: The upstream repository declares no license file. Recorded as a fact so
    #: nobody assumes a permission that was never granted.
    "license": "ABSENT",
}

#: The copy in this repository. `MANIFEST.md` is ours and stays out of the digest.
VENDORED = ROOT / "vendor" / "x-growth-os"
MANIFEST_NAME = "MANIFEST.md"
VENDORED_FILES = PIN["tracked_files"]
VENDORED_BYTES = PIN["total_bytes"]
VENDORED_DIGEST = "4a99c01ebb6515ebce9d861e7b2d8b0dd1dd43abfcdef43ad1a1afbf620a0674"

#: A name that looks like it carries a secret is refused outright. The source
#: repository had none at import; this keeps a later import from slipping one in.
CREDENTIAL_NAME = re.compile(
    r"(^\.env|\.env$|\.key$|\.pem$|\.p12$|\.pfx$|credential|secret|cookie|password)",
    re.IGNORECASE,
)
#: `check_repo_policy.py` refuses a tracked file over 5 MiB; the vendored copy
#: would otherwise be the way a binary enters this repository.
MAX_FILE_BYTES = 5 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _vendored_files(root: Path, exclude: frozenset[str]) -> List[Path]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        # `__pycache__` is written by running the vendored suite; it is
        # interpreter output, not content.
        if "__pycache__" in rel.parts or path.suffix == ".pyc":
            continue
        if rel.as_posix() in exclude:
            continue
        files.append(path)
    return files


def vendored_digest(root: Path, exclude: frozenset[str] = frozenset({MANIFEST_NAME})) -> tuple[int, int, str]:
    """Hash the vendored tree by content: path, then file digest, then newline.

    Returns ``(file_count, total_bytes, digest)``. Byte count is pinned as well as
    file count, because a same-count content swap is the one edit a count alone
    cannot see.
    """
    files = _vendored_files(root, exclude)
    digest = hashlib.sha256()
    total = 0
    for path in files:
        rel = path.relative_to(root).as_posix()
        total += path.stat().st_size
        digest.update(rel.encode("utf-8") + b"\0" + _sha256(path).encode("ascii") + b"\n")
    return len(files), total, digest.hexdigest()


def _check_vendored(root: Path = VENDORED) -> List[Dict[str, Any]]:
    if not root.is_dir():
        return [{"id": "vendored_present", "ok": False, "path": str(root)}]
    count, total, digest = vendored_digest(root)
    files = _vendored_files(root, frozenset({MANIFEST_NAME}))
    credentials = [p.relative_to(root).as_posix() for p in files if CREDENTIAL_NAME.search(p.name)]
    oversized = [p.relative_to(root).as_posix() for p in files if p.stat().st_size > MAX_FILE_BYTES]
    return [
        {"id": "vendored_present", "ok": True, "path": str(root)},
        {"id": "vendored_files", "ok": count == VENDORED_FILES,
         "value": count, "expected": VENDORED_FILES},
        {"id": "vendored_bytes", "ok": total == VENDORED_BYTES,
         "value": total, "expected": VENDORED_BYTES},
        {"id": "vendored_digest", "ok": digest == VENDORED_DIGEST,
         "value": digest, "expected": VENDORED_DIGEST},
        {"id": "credential_shape", "ok": not credentials, "value": credentials},
        {"id": "oversize_file", "ok": not oversized, "value": oversized},
    ]


def _git(cwd: Path, *args: str):
    return hidden_run(["git", *args], cwd=str(cwd), timeout=120)


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
    listed = _git(checkout, "ls-files", "-z")
    count = len([line for line in (listed.stdout or "").split("\0") if line.strip()])
    checks.append({"id": "tracked_files", "ok": count == PIN["tracked_files"],
                   "value": count, "expected": PIN["tracked_files"]})
    return checks


def verify(checkout: Optional[Path] = None, vendored: Optional[Path] = None) -> Dict[str, Any]:
    root = vendored or VENDORED
    checks = _check_vendored(root)
    if checkout is not None:
        checks += _check_checkout(checkout)
    failures = [check["id"] for check in checks if not check["ok"]]
    return {
        "schema": SCHEMA,
        "pin": dict(PIN),
        "vendored": str(root),
        "checkout": str(checkout) if checkout else None,
        "ok": not failures,
        "failures": failures,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the pinned X growth workflow.")
    parser.add_argument("--checkout", default=None,
                        help="a clone of the source repository to verify against the pin")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = verify(Path(args.checkout) if args.checkout else None)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"repository  {result['pin']['repo']}  ({result['pin']['access']})")
        print(f"commit      {result['pin']['commit']}  ({result['pin']['commit_subject']})")
        print(f"tree        {result['pin']['tree']}")
        print(f"files       {result['pin']['tracked_files']}  bytes {result['pin']['total_bytes']}")
        print(f"vendored    {result['vendored']}")
        for check in result["checks"]:
            print(f"  {'OK  ' if check['ok'] else 'FAIL'} {check['id']}")
        if result["failures"]:
            print()
            print("FAILED: " + ", ".join(result["failures"]))
            print("A change to vendor/x-growth-os is a new import with a new digest, "
                  "not an edit.")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
