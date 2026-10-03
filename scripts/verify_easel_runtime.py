#!/usr/bin/env python3
"""Prove the local Easel runtime is byte-identical to upstream at the pinned commit.

A GitHub release archive carries no `.git`, so `git rev-parse HEAD` cannot answer
"which commit is this?" for `.runtime/easel`. This script answers the question
from content instead: every local file is hashed the way git hashes a blob
(sha1 of `"blob <len>\\0" + bytes`) and compared against the upstream tree API
for the pinned commit.

That keeps the pin falsifiable without .git metadata. A swapped, patched or
half-extracted tree yields MISSING / MISMATCH / EXTRA entries instead of a
silent pass — which matters because AGENTS.md §1.6 pins Easel at v0.2.1 and
forbids upgrading it without the Founder's explicit consent.

Exit codes:  0 verified   1 not verified   3 could not verify (offline / no gh)
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime" / "easel"
REPO = "ZJU-REAL/Easel"
PINNED_TAG = "v0.2.1"
PINNED_COMMIT = "3fe2d9904c1619281ef57f81d9ee0b7854998399"

# Paths the pipeline itself writes into the runtime tree. They are expected to
# differ from upstream and are excluded from the comparison; everything else
# must match exactly.
GENERATED_PREFIXES = ("outputs/",)
GENERATED_NAMES = {".DS_Store"}
GENERATED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache"}


def blob_sha1(path: Path) -> str:
    """git's blob object id: sha1('blob <size>\\0' + content)."""
    data = path.read_bytes()
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def walk_local(runtime_dir: Path) -> dict[str, str]:
    """Map repo-relative posix path -> blob sha1 for every tracked-worthy file."""
    out: dict[str, str] = {}
    for p in sorted(runtime_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(runtime_dir).as_posix()
        if _is_generated(rel) or rel.endswith(".pyc") or rel.endswith(".egg-info"):
            continue
        out[rel] = blob_sha1(p)
    return out


def fetch_upstream_tree(repo: str, commit: str) -> dict[str, str]:
    """Fetch {path: blob_sha} for a commit via the GitHub API.

    Raises RuntimeError when the tree cannot be fetched (offline, no gh, no
    auth). Callers must treat that as "could not verify", never as a pass.
    """
    if not shutil.which("gh"):
        raise RuntimeError("gh CLI not found on PATH")
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/git/trees/{commit}?recursive=1"],
        capture_output=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh api failed: {(proc.stderr or '').strip()[:300]}")
    try:
        data = json.loads(proc.stdout)
    except Exception as e:
        raise RuntimeError(f"gh api returned unparsable JSON: {e}")
    if data.get("truncated"):
        raise RuntimeError("upstream tree response was truncated — refusing a partial compare")
    # Apply the same exclusions as walk_local so the two sides stay symmetric:
    # an asymmetry here reports excluded files as spurious "missing" entries.
    return {e["path"]: e["sha"] for e in data.get("tree", [])
            if e.get("type") == "blob" and not _is_generated(e["path"])}


def _is_generated(rel: str) -> bool:
    parts = rel.split("/")
    if any(part in GENERATED_DIRS for part in parts):
        return True
    if parts[-1] in GENERATED_NAMES:
        return True
    # outputs/ is the pipeline's write area, but the shipped outputs/.gitkeep is
    # a real upstream file — keep it in the comparison so the blob count covers
    # the entire upstream tree (982 for v0.2.1).
    return rel.startswith(GENERATED_PREFIXES) and rel != "outputs/.gitkeep"


def resolve_tag_commit(repo: str, tag: str) -> str:
    """Peel an annotated tag to its commit via the GitHub API."""
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/git/ref/tags/{tag}", "--jq", ".object.sha,.object.type"],
        capture_output=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"cannot resolve tag {tag}: {(proc.stderr or '').strip()[:200]}")
    lines = [l.strip() for l in (proc.stdout or "").splitlines() if l.strip()]
    if len(lines) != 2:
        raise RuntimeError(f"unexpected tag response: {proc.stdout!r}")
    sha, kind = lines
    if kind == "tag":  # annotated: one more hop to the commit
        proc = subprocess.run(
            ["gh", "api", f"repos/{repo}/git/tags/{sha}", "--jq", ".object.sha"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=60,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"cannot peel tag object {sha}")
        sha = (proc.stdout or "").strip()
    return sha


def verify(runtime_dir: Path = RUNTIME, repo: str = REPO,
           commit: str = PINNED_COMMIT) -> dict:
    """Compare the local runtime tree against upstream at `commit`."""
    result: dict = {
        "runtime_dir": str(runtime_dir),
        "repo": repo,
        "expected_commit": commit,
        "expected_tag": PINNED_TAG,
    }
    if not runtime_dir.is_dir():
        return {**result, "status": "MISSING",
                "reason": f"no runtime at {runtime_dir}"}

    if (runtime_dir / ".git").exists():
        # A .git dir means this is not the archive layout; content compare still
        # works, but record it so the provenance file is not misleading.
        result["has_git_metadata"] = True

    try:
        upstream = fetch_upstream_tree(repo, commit)
    except RuntimeError as e:
        return {**result, "status": "UNVERIFIED", "reason": str(e),
                "note": "content identity could not be confirmed; this is not a pass"}

    local = walk_local(runtime_dir)

    missing = sorted(set(upstream) - set(local))
    extra = sorted(set(local) - set(upstream))
    mismatch = sorted(p for p in (set(local) & set(upstream)) if local[p] != upstream[p])

    ok = not (missing or extra or mismatch)
    result.update({
        "status": "VERIFIED" if ok else "MISMATCH",
        "upstream_blob_count": len(upstream),
        "local_blob_count": len(local),
        "matched": len(set(local) & set(upstream)) - len(mismatch),
        "missing": missing[:20],
        "missing_count": len(missing),
        "mismatch": mismatch[:20],
        "mismatch_count": len(mismatch),
        "extra": extra[:20],
        "extra_count": len(extra),
        "method": "blob_sha1_tree_compare",
    })
    if not ok:
        result["reason"] = (f"{len(mismatch)} mismatched / {len(missing)} missing / "
                            f"{len(extra)} extra vs upstream {commit[:7]}")
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runtime", default=str(RUNTIME))
    p.add_argument("--repo", default=REPO)
    p.add_argument("--commit", default=PINNED_COMMIT)
    p.add_argument("--resolve-tag", action="store_true",
                   help="confirm --commit is the commit the pinned tag points at")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    res = verify(Path(args.runtime), args.repo, args.commit)

    if args.resolve_tag and res.get("status") != "MISSING":
        try:
            peeled = resolve_tag_commit(args.repo, PINNED_TAG)
            res["tag_resolved_commit"] = peeled
            res["tag_matches_commit"] = (peeled == args.commit)
            if peeled != args.commit:
                res["status"] = "MISMATCH"
                res["reason"] = (f"tag {PINNED_TAG} points at {peeled}, "
                                 f"but the pin expects {args.commit}")
        except RuntimeError as e:
            res["tag_resolve_error"] = str(e)

    print(json.dumps(res, indent=2, ensure_ascii=False))
    if res["status"] == "VERIFIED":
        return 0
    if res["status"] == "UNVERIFIED":
        return 3
    return 1


if __name__ == "__main__":
    sys.exit(main())
