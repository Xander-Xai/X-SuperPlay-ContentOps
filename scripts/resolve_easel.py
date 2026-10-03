#!/usr/bin/env python3
"""Resolve (and if necessary acquire) the pinned Easel runtime.

AGENTS.md §1.6 pins Easel at v0.2.1 / commit 3fe2d99 and forbids silently
running anything else. This module is the single place that decides which
directory is the production engine:

  1. `.runtime/easel` with `.git`      -> remote MUST be ZJU-REAL/Easel (§3) and
                                          HEAD MUST equal the pinned commit.
  2. `.runtime/easel` without `.git`   -> a release archive; identity is proven
                                          by content hash against the upstream
                                          tree (verify_easel_runtime), never by
                                          .git metadata (§2).
  3. `Easel/` (legacy working clone)   -> only accepted when it actually sits at
                                          the pinned commit; an unpinned clone is
                                          reported, never silently selected.

Anything else is BLOCKED with an explicit reason — the pipeline must not fall
back to "whatever Easel-looking directory is lying around".

`bootstrap()` implements the acquisition ladder from the V1 spec:
  Strategy A  git clone the exact tag and verify HEAD == pinned commit
  Strategy B  GitHub release tarball via `gh api`, extract, content-verify
  BLOCKED     both failed — report why, acquire nothing

A `.runtime/easel` whose remote is not ZJU-REAL/Easel is moved aside (never
deleted) before re-acquisition, so the bad state stays auditable (§3).
"""

import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = ROOT / "runtime" / "easel.lock.json"
PROVENANCE_FILE = ROOT / "runtime" / "easel-runtime.json"

# Fallback pin if the lock file is unreadable; the lock file is the source of truth.
_FALLBACK_PIN = {
    "repo": "https://github.com/ZJU-REAL/Easel.git",
    "tag": "v0.2.1",
    "commit": "3fe2d9904c1619281ef57f81d9ee0b7854998399",
}

REQUIRED_PATHS = (
    "pyproject.toml",
    "skills/openclaw/auto-short-video/scripts/assemble.py",
    "skills/shared/scripts/tts.py",
)


def load_pin(root: Path = ROOT) -> dict:
    try:
        data = json.loads((root / "runtime" / "easel.lock.json").read_text(encoding="utf-8"))
        return {"repo": data["repo"], "tag": data["tag"], "commit": data["commit"]}
    except Exception:
        return dict(_FALLBACK_PIN)


def _git(path: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True, text=True, timeout=30,
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def _is_easel_remote(url: str) -> bool:
    return bool(url) and "ZJU-REAL" in url and "Easel" in url


def _looks_like_easel(easel_dir: Path) -> bool:
    return (easel_dir / "pyproject.toml").is_file()


def _usable(easel_dir: Path) -> bool:
    return all((easel_dir / rel).is_file() for rel in REQUIRED_PATHS)


def _provenance(root: Path) -> dict:
    try:
        return json.loads((root / "runtime" / "easel-runtime.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_provenance(root: Path, data: dict) -> None:
    prov = root / "runtime" / "easel-runtime.json"
    prov.parent.mkdir(parents=True, exist_ok=True)
    prov.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _verify_content(root: Path, easel_dir: Path, commit: str) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import verify_easel_runtime
    except ImportError as e:  # pragma: no cover
        return {"status": "UNVERIFIED", "reason": f"verifier unavailable: {e}"}
    return verify_easel_runtime.verify(easel_dir, verify_easel_runtime.REPO, commit)


def _check_candidate(easel_dir: Path, label: str, pin: dict,
                     root: Path, live: bool) -> dict:
    """Evaluate one candidate directory. Returns a resolution record."""
    base = {"candidate": str(easel_dir), "source": label}
    if not easel_dir.exists():
        return {**base, "ok": False, "reason": "not present"}

    if (easel_dir / ".git").exists():
        remote = _git(easel_dir, "config", "--get", "remote.origin.url")
        if remote and not _is_easel_remote(remote):
            # §3: never treat a foreign checkout as Easel.
            return {**base, "ok": False, "rejected": True,
                    "reason": f"remote is {remote!r}, not ZJU-REAL/Easel — "
                              f"refusing to treat this directory as Easel"}
        head = _git(easel_dir, "rev-parse", "HEAD")
        if head != pin["commit"]:
            return {**base, "ok": False,
                    "reason": f"HEAD {head[:12] or '?'} != pinned {pin['commit'][:12]} "
                              f"— unpinned tree, not the production engine"}
        if not _usable(easel_dir):
            return {**base, "ok": False,
                    "reason": "pinned commit but required pipeline scripts missing"}
        return {**base, "ok": True, "acquisition": "git_checkout",
                "commit": head, "verification": "git_head"}

    # No .git: release-archive layout. Identity comes from content, not metadata.
    if not _looks_like_easel(easel_dir):
        return {**base, "ok": False,
                "reason": "no .git and no pyproject.toml — not an Easel tree"}
    if not _usable(easel_dir):
        return {**base, "ok": False,
                "reason": "required pipeline scripts missing (assemble.py / tts.py)"}

    if live:
        v = _verify_content(root, easel_dir, pin["commit"])
        if v.get("status") == "VERIFIED":
            return {**base, "ok": True, "acquisition": "release_archive",
                    "commit": pin["commit"], "verification": "live_content_hash",
                    "verified_blobs": v.get("matched")}
        if v.get("status") == "MISMATCH":
            return {**base, "ok": False,
                    "reason": f"content does not match upstream {pin['commit'][:12]}: "
                              f"{v.get('reason', '')} — refusing to run a tampered tree"}
        # UNVERIFIED (offline / no gh): fall through to recorded provenance.

    prov = _provenance(root)
    if (prov.get("verified") and prov.get("expected_commit") == pin["commit"]
            and prov.get("acquisition")):
        return {**base, "ok": True, "acquisition": prov.get("acquisition", "release_archive"),
                "commit": pin["commit"], "verification": "recorded",
                "verified_at": prov.get("verified_at", "?"),
                "note": "offline: trusting recorded provenance; run doctor online to re-verify"}
    return {**base, "ok": False,
            "reason": "archive layout but no recorded verification and live "
                      "verification unavailable — cannot prove this is v0.2.1"}


def resolve_easel(root: Path = ROOT, live: bool = True) -> dict:
    """Resolve the production Easel runtime.

    Returns {"status": "OK", easel_dir, acquisition, commit, ...} or
    {"status": "BLOCKED", "reasons": [...]}. Never returns an unpinned tree.
    """
    pin = load_pin(root)
    candidates = [
        (root / ".runtime" / "easel", "runtime"),
        (root / "Easel", "legacy"),
    ]
    reasons, rejected = [], False
    for path, label in candidates:
        rec = _check_candidate(path, label, pin, root, live)
        if rec.get("rejected"):
            rejected = True
        if rec.get("ok"):
            return {
                "status": "OK",
                "easel_dir": str(path),
                "source": label,
                "acquisition": rec["acquisition"],
                "commit": rec["commit"],
                "tag": pin["tag"],
                "verification": rec["verification"],
                **{k: rec[k] for k in ("verified_blobs", "verified_at", "note") if k in rec},
            }
        if path.exists():
            reasons.append(f"{path.name}: {rec.get('reason', '?')}")
    return {
        "status": "BLOCKED",
        "rejected_foreign_checkout": rejected,
        "reasons": reasons or ["no Easel runtime found"],
        "expected": {"repo": pin["repo"], "tag": pin["tag"], "commit": pin["commit"]},
        "remedy": "python scripts/resolve_easel.py --bootstrap",
    }


# --------------------------------------------------------------------------
# bootstrap: acquire the runtime when resolution fails (§2 ladder + §3 cleanup)
# --------------------------------------------------------------------------

def _move_aside(path: Path, tag: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = path.with_name(f"{path.name}.{tag}-{stamp}")
    path.rename(dest)
    return dest


def _strategy_git_clone(root: Path, pin: dict, target: Path) -> dict:
    """Strategy A: clone the tag, then prove HEAD == pinned commit (tags can move)."""
    r = subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", pin["tag"],
         pin["repo"], str(target)],
        capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0 or not target.exists():
        return {"ok": False, "reason": (r.stderr or r.stdout or "git clone failed")[-400:]}
    head = _git(target, "rev-parse", "HEAD")
    if head != pin["commit"]:
        return {"ok": False,
                "reason": f"tag {pin['tag']} resolved to {head[:12]}, expected "
                          f"{pin['commit'][:12]} — tag moved; refusing"}
    return {"ok": True, "acquisition": "git_clone", "commit": head}


def _strategy_release_archive(root: Path, pin: dict, target: Path) -> dict:
    """Strategy B: release tarball via gh, extract, content-verify (§2)."""
    if not shutil.which("gh"):
        return {"ok": False, "reason": "gh CLI not found"}
    repo = pin["repo"].removesuffix(".git").split("github.com/")[-1]
    with tempfile.TemporaryDirectory() as td:
        tgz = Path(td) / "easel.tar.gz"
        with tgz.open("wb") as fh:
            r = subprocess.run(
                ["gh", "api", f"repos/{repo}/tarball/{pin['tag']}"],
                stdout=fh, stderr=subprocess.PIPE, timeout=600,
            )
        if r.returncode != 0 or tgz.stat().st_size < 1024:
            err = (r.stderr or b"").decode(errors="replace")
            return {"ok": False, "reason": f"gh tarball fetch failed: {err[-300:]}"}
        target.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tgz, "r:gz") as tf:
            members = tf.getmembers()
            top = members[0].name.split("/")[0] if members else ""
            for m in members:
                # strip the single top-level "Owner-Repo-<sha>/" component
                rel = Path(m.name)
                if top and rel.parts and rel.parts[0] == top:
                    rel = Path(*rel.parts[1:])
                if not rel.parts or rel.is_absolute() or ".." in rel.parts:
                    continue
                m.name = str(rel).replace("\\", "/")
                try:
                    tf.extract(m, target, filter="data")
                except TypeError:  # Python < 3.12 has no filter=
                    tf.extract(m, target)
    v = _verify_content(root, target, pin["commit"])
    if v.get("status") != "VERIFIED":
        return {"ok": False, "reason": f"archive content verification failed: {v.get('reason', v.get('status'))}"}
    return {"ok": True, "acquisition": "release_archive", "commit": pin["commit"],
            "verified_blobs": v.get("matched")}


def bootstrap(root: Path = ROOT) -> dict:
    """Acquire the pinned runtime. Existing bad state is moved aside, never deleted."""
    pin = load_pin(root)
    runtime_dir = root / ".runtime" / "easel"

    existing = resolve_easel(root, live=True)
    if existing["status"] == "OK" and existing.get("source") == "runtime":
        return {"status": "OK", "action": "already_present", **existing}

    if runtime_dir.exists():
        moved = _move_aside(runtime_dir, "rejected")
        note = f"moved unusable runtime aside to {moved.name}"
    else:
        note = "no existing runtime"

    for name, strat in (("git_clone", _strategy_git_clone),
                        ("release_archive", _strategy_release_archive)):
        res = strat(root, pin, runtime_dir)
        if res.get("ok"):
            prov = {
                "repo": "ZJU-REAL/Easel",
                "repo_url": pin["repo"],
                "release": pin["tag"],
                "expected_commit": pin["commit"],
                "acquisition": res["acquisition"],
                "installed_at": ".runtime/easel",
                "has_git_metadata": (runtime_dir / ".git").exists(),
                "verified": True,
                "verification_method": "git_head" if res["acquisition"] == "git_clone" else "blob_sha1_tree_compare",
                "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            }
            if res.get("verified_blobs"):
                prov["verified_blobs"] = res["verified_blobs"]
            _write_provenance(root, prov)
            return {"status": "OK", "action": "acquired", "strategy": name,
                    "easel_dir": str(runtime_dir), "note": note, **prov}
        last_error = res.get("reason", "?")

    return {"status": "BLOCKED", "note": note,
            "reason": f"both strategies failed (last: {last_error})",
            "expected": pin}


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--bootstrap", action="store_true",
                   help="acquire the pinned runtime if missing/broken (git -> archive -> BLOCKED)")
    p.add_argument("--offline", action="store_true",
                   help="skip live content verification; use recorded provenance")
    args = p.parse_args()

    result = bootstrap() if args.bootstrap else resolve_easel(live=not args.offline)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
