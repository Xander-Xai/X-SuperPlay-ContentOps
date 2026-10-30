#!/usr/bin/env python3
"""The WeChat workflow's pin: one vendored tree, one digest, one check.

The Future Intelligence 公众号 workflow used to live in its own repository at
`D:\\Projects\\gzh_x未来智能`, whose local history was **divergent** from GitHub
origin (`origin/main` was `e9303d1`, the checkout `93645f1`). That checkout, its
remote and the cold archive made from it are being retired, so the workflow now
lives here, at `vendor/gzh-thinktank/gzh_未来智能`, imported verbatim.

With the archive gone, this directory is the only copy. The pin therefore checks
the tree's content digest — which also catches an edit made in place, the thing
"do not edit the vendor tree" is meant to prevent. `vendor/gzh-thinktank/MANIFEST.md`
records what retirement cost (the original's commits and the files this repository
cannot track).

Usage
-----
    python scripts/gzh_pin.py
    python scripts/gzh_pin.py --json
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
#: The cold archive is retired: the Founder is deleting it together with the
#: original checkout and its remote. From here the vendored tree is the only copy,
#: and `MANIFEST.md` records what that costs (the original's commits and the twelve
#: files this repository cannot track).
BUNDLE_RETIRED = True

VENDORED_DIGEST = "0b96d179a224f0b9668843fd78fcdcefb8f9a83d7918b7d8127fce5d6687919a"


def _file_digest(path: Path) -> str:
    """SHA-256 of a file's content with CRLF folded to LF.

    The digest exists to catch an edit to the tree, not to police how a platform
    checked it out. Git's ``core.autocrlf`` rewrites line endings on checkout on
    some platforms and not others, so hashing raw bytes would let the same commit
    pass on Linux and fail on Windows (or on a ``git archive`` extraction). Folding
    CRLF to LF preserves the content-level guarantee — a changed line still changes
    the digest — and makes the pin platform-independent. Line endings alone are
    not content this pin is defending.
    """
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def vendored_digest(root: Path) -> tuple[int, str]:
    """Hash the vendored tree by content, not by commit.

    The vendored copy is not a git checkout (the import dropped caches and the
    credential-bearing config), so a tree object cannot identify it. Hashing every
    file's path and content can, and it also catches an edit made in place — which
    is exactly what "do not edit the vendor tree" means.
    """
    rows = []
    # Sort by the relative POSIX path string, not by Path objects: Windows
    # compares paths case-insensitively and POSIX does not, so the same tree
    # would hash in two different orders and produce two digests.
    for path in sorted(root.rglob("*"),
                       key=lambda item: item.relative_to(root).as_posix()):
        if not path.is_file():
            continue
        # Running the vendored workflow writes __pycache__ inside it. Those are
        # interpreter output, not content, and excluding them is what lets the pin
        # survive the workflow being used at all.
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rows.append((path.relative_to(root).as_posix(), _file_digest(path)))
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
    if not present:
        # The archive is being retired; the vendored tree becomes the only copy.
        # Absence is then expected, not a failure -- but if a bundle is still
        # there, it has to be the one this pin describes.
        checks.append({"id": "bundle_retired", "ok": BUNDLE_RETIRED,
                       "note": "the cold archive is retired; the vendored tree is the "
                               "source of truth" if BUNDLE_RETIRED
                               else "no bundle and no retirement recorded"})
        return checks
    checks.append({"id": "bundle_present", "ok": True, "path": str(bundle)})
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
        print(f"repository  {result['pin']['repo']}  (provenance, not a live clone)")
        print(f"upstream    {result['pin']['commit']}  ({result['pin']['commit_subject']})")
        print(f"            {result['pin']['tracked_files']} tracked files at that commit; "
              f"{VENDORED_FILES} vendored here")
        if result["bundle"].endswith(".bundle") and not Path(result["bundle"]).is_file():
            print("archive     retired — the vendored tree is the only copy")
        else:
            print(f"bundle      {result['bundle']}")
        for check in result["checks"]:
            print(f"  {'OK  ' if check['ok'] else 'FAIL'} {check['id']}")
        if result["failures"]:
            print()
            print("FAILED: " + ", ".join(result["failures"]))
            if Path(result["bundle"]).is_file():
                print("Restore with: git clone <bundle> D:\\Projects\\gzh-Future-Intelligence")
            else:
                print("The archive is retired; re-import the workflow and update the pin "
                      "(see vendor/gzh-thinktank/MANIFEST.md).")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
