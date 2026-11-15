#!/usr/bin/env python3
"""Resolve (and if necessary acquire) the pinned Easel runtime.

AGENTS.md §1.6 forbids silently running anything other than the pinned engine.
The pin itself is not written here: it lives in `runtime/easel-pins.json` and is
read through `contentops.easel.pins`. This module decides which directory is the
production engine:

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
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from process_utils import PIPE, hidden_run

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE_FILE = ROOT / "runtime" / "easel-runtime.json"

def _required_paths(layout: str | None) -> tuple[str, ...]:
    """Paths the pipeline itself needs, in the layer this engine actually uses.

    v0.2.1 keeps its skills under ``skills/openclaw``; v0.3.0 moved them to
    ``skills/builtin``. Checking the wrong layer reports "required scripts
    missing" on a perfectly good tree — which is what happened the first time
    v0.3.0 was made active.
    """
    layer = layout or "openclaw"
    return (
        "pyproject.toml",
        f"skills/{layer}/auto-short-video/scripts/assemble.py",
        "skills/shared/scripts/tts.py",
    )


# Kept for callers that do not pass a layout (bootstrap, tests); the active
# layer comes from the registry at call time via ``_required_paths``.
REQUIRED_PATHS = _required_paths("openclaw")


def _pins():
    """Import the pin registry module, with ``src`` on the path."""
    src = ROOT / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from contentops.easel import pins

    return pins


def load_pin(root: Path | None = None) -> dict:
    """Return the active engine's pin from ``runtime/easel-pins.json``.

    There is deliberately no fallback. The previous version of this function
    returned a hardcoded commit whenever the lock file was unreadable, which is
    how one version ended up recorded in five places with no authority between
    them. If the registry cannot be read, resolution is BLOCKED.

    ``root`` names the tree to inspect; the registry itself always belongs to
    this repository, because it is repository configuration, not runtime state.
    """
    return _pin_from_engine(_pins().active())


def _pin_from_engine(engine) -> dict:
    """The resolver's pin record for one declared engine."""
    return {
        "repo": engine.repo,
        "tag": engine.tag,
        "commit": engine.commit,
        "engine_id": engine.engine_id,
        "layout": engine.layout,
        "skill_root": engine.skill_root,
        "root": engine.root,
    }


def _git(path: Path, *args: str) -> str:
    r = hidden_run(
        ["git", "-C", str(path), *args],
        timeout=30,
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def _is_easel_remote(url: str) -> bool:
    return bool(url) and "ZJU-REAL" in url and "Easel" in url


def _looks_like_easel(easel_dir: Path) -> bool:
    return (easel_dir / "pyproject.toml").is_file()


def _usable(easel_dir: Path, layout: str | None = None) -> bool:
    return all((easel_dir / rel).is_file() for rel in _required_paths(layout))


def _provenance(root: Path, engine_id: str | None = None) -> dict:
    """Recorded verification for one engine.

    The per-engine record (`runtime/easel-runtime-<engine>.json`) wins over the
    legacy single-file record, because two coexisting trees cannot both be
    described by one document: before this, verifying v0.3.0 overwrote the only
    evidence that v0.2.1 had been verified.
    """
    candidates = []
    if engine_id:
        candidates.append(root / "runtime" / f"easel-runtime-{engine_id}.json")
    candidates.append(root / "runtime" / "easel-runtime.json")
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data:
            return data
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
    try:
        return verify_easel_runtime.verify(easel_dir, verify_easel_runtime.REPO, commit)
    except Exception as exc:  # noqa: BLE001
        # A dropped GitHub connection is "could not verify", not a crash and not
        # a pass. Unhandled, it took down the whole resolver on one bad read.
        return {"status": "UNVERIFIED",
                "reason": f"verification unavailable: {type(exc).__name__}"}


def _verify_overlay_content(root: Path, easel_dir: Path) -> dict:
    """Verify a tuned instance against its overlay record.

    A production instance that carries declared tuning can never pass a plain
    byte comparison — differing in the named files is the whole point of the
    overlay. Verified through the record instead, which still requires the
    baseline to match upstream and every tuned file to match its recorded
    digest, and re-projects the account profiles from current DNA.
    """
    record = root / "runtime" / "easel-workbench-overlay.json"
    if not record.is_file():
        return {"status": "NOT_DECLARED"}
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import verify_easel_runtime as verifier
    except ImportError as exc:  # pragma: no cover
        return {"status": "UNVERIFIED", "reason": f"verifier unavailable: {exc}"}
    try:
        return verifier.verify_overlay(record, profile_mode="generated",
                                       workbench_override=easel_dir)
    except Exception as exc:  # noqa: BLE001 - unverifiable is not a pass
        return {"status": "UNVERIFIED", "reason": type(exc).__name__}


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
        if not _usable(easel_dir, pin.get("layout")):
            return {**base, "ok": False,
                    "reason": "pinned commit but required pipeline scripts missing"}
        prov = _provenance(root, pin.get("engine_id"))
        content_proved = bool(prov.get("content_verified")) and \
            prov.get("content_verified_commit") == pin["commit"]
        return {**base, "ok": True, "acquisition": "git_checkout",
                "commit": head, "verification": "git_head",
                "content_verified": content_proved,
                "note": ("git HEAD matches the pin; content was also verified by blob "
                         "comparison" if content_proved
                         else "git HEAD matches the pin; content is not verified — "
                              "run verify_easel_runtime.py --record")}

    # No .git: release-archive layout. Identity comes from content, not metadata.
    if not _looks_like_easel(easel_dir):
        return {**base, "ok": False,
                "reason": "no .git and no pyproject.toml — not an Easel tree"}
    if not _usable(easel_dir, pin.get("layout")):
        return {**base, "ok": False,
                "reason": "required pipeline scripts missing (assemble.py / tts.py)"}

    if live:
        v = _verify_content(root, easel_dir, pin["commit"])
        if v.get("status") == "VERIFIED":
            return {**base, "ok": True, "acquisition": "release_archive",
                    "commit": pin["commit"], "verification": "live_content_hash",
                    "verified_blobs": v.get("matched")}
        if v.get("status") == "MISMATCH":
            overlay = _verify_overlay_content(root, easel_dir)
            if overlay.get("status") == "VERIFIED":
                return {**base, "ok": True, "acquisition": "release_archive",
                        "commit": pin["commit"],
                        "verification": "upstream_overlay_and_generated_profiles",
                        "verified_blobs": overlay.get("baseline_blob_count"),
                        "note": "an instance with declared tuning cannot match byte for "
                                "byte; the overlay record proves the baseline and every "
                                "tuned file instead"}
            return {**base, "ok": False,
                    "reason": f"content does not match upstream {pin['commit'][:12]}: "
                              f"{v.get('reason', '')} — refusing to run a tampered tree"}
        # UNVERIFIED (offline / no gh): fall through to recorded provenance.

    prov = _provenance(root, pin.get("engine_id"))
    recorded = (prov.get("content_verified") or prov.get("commit_matches_pin")
                or prov.get("verified"))
    if (recorded and prov.get("expected_commit") == pin["commit"]
            and prov.get("acquisition")):
        proof = "content" if prov.get("content_verified") else "commit"
        return {**base, "ok": True, "acquisition": prov.get("acquisition", "release_archive"),
                "commit": pin["commit"], "verification": "recorded",
                "provenance_proves": proof,
                "verified_at": prov.get("verified_at", "?"),
                "note": "offline: trusting recorded provenance; run doctor online to re-verify"}
    return {**base, "ok": False,
            "reason": f"archive layout but no recorded verification and live "
                      f"verification unavailable — cannot prove this is {pin['tag']}"}


def resolve_easel(root: Path = ROOT, live: bool = True,
                  engine_id: str | None = None) -> dict:
    """Resolve the production Easel runtime.

    Returns {"status": "OK", easel_dir, acquisition, commit, ...} or
    {"status": "BLOCKED", "reasons": [...]}. Never returns an unpinned tree, and
    never resolves against a guessed pin: an unreadable registry is a BLOCKED
    result with `PINS_UNREADABLE`, not a default version.
    """
    try:
        pin = load_pin() if engine_id is None else _pin_from_engine(_pins().get(engine_id))
    except Exception as exc:  # noqa: BLE001 - an unreadable pin must refuse, not guess
        return {
            "status": "BLOCKED",
            "reasons": [f"PINS_UNREADABLE: {exc}"],
            "remedy": "restore runtime/easel-pins.json; this resolver has no fallback pin",
        }

    engine_root = root / pin["root"] if pin.get("root") else root / ".runtime" / "easel"
    candidates = [
        (engine_root, "runtime"),
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
                "engine_id": pin.get("engine_id"),
                "layout": pin.get("layout"),
                "verification": rec["verification"],
                **{k: rec[k] for k in ("verified_blobs", "verified_at", "note",
                                       "content_verified") if k in rec},
            }
        if path.exists():
            reasons.append(f"{path.name}: {rec.get('reason', '?')}")
    return {
        "status": "BLOCKED",
        "rejected_foreign_checkout": rejected,
        "reasons": reasons or ["no Easel runtime found"],
        "expected": {"repo": pin["repo"], "tag": pin["tag"], "commit": pin["commit"],
                     "engine_id": pin.get("engine_id")},
        "remedy": "python scripts/resolve_easel.py --bootstrap",
    }


def resolve_easel_workbench(root: Path = ROOT) -> dict:
    """Resolve the separate v0.3.0 workbench only after full overlay verification.

    This never participates in production selection. It follows the repository
    overlay manifest (including its explicit per-process path override) and
    verifies the generated profiles before returning a runtime directory.
    """
    root = Path(root).resolve()
    record_path = root / "runtime" / "easel-workbench-overlay.json"
    verifier_path = root / "scripts" / "verify_easel_runtime.py"
    if not record_path.is_file():
        return {"status": "BLOCKED", "reasons": ["workbench overlay record is missing"]}
    if not verifier_path.is_file():
        return {"status": "BLOCKED", "reasons": ["workbench verifier is missing"]}
    scripts_dir = str(verifier_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        import verify_easel_runtime
        workbench = _pins().workbench()
        overlay = verify_easel_runtime.load_overlay(record_path)
        upstream = overlay.get("upstream") or {}
        if (not overlay.get("readable") or overlay.get("schema") != "contentops.easel-workbench-overlay/v1"
                or not isinstance(upstream, dict) or upstream.get("repo") != workbench.repo
                or upstream.get("commit") != workbench.commit):
            return {"status": "BLOCKED", "reasons": ["workbench identity does not match the declared workbench engine"]}
        result = verify_easel_runtime.verify_overlay(
            record_path=record_path, profile_mode="generated")
    except Exception as exc:  # noqa: BLE001 - failure to verify must refuse selection
        return {"status": "BLOCKED",
                "reasons": [f"workbench verification failed: {type(exc).__name__}"]}
    if result.get("status") != "VERIFIED":
        detail = result.get("reason") or result.get("status") or "unknown verifier result"
        return {"status": "BLOCKED", "reasons": [str(detail)],
                "verification": result}
    if result.get("expected_commit") != workbench.commit:
        return {"status": "BLOCKED", "reasons": ["workbench identity changed during verification"]}
    return {
        "status": "OK",
        "easel_dir": result["workbench_path"],
        "commit": result.get("expected_commit"),
        "tag": result.get("expected_tag"),
        "engine_id": workbench.engine_id,
        "layout": workbench.layout,
        "verification": "upstream_overlay_and_generated_profiles",
        "verification_result": result,
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
    r = hidden_run(
        ["git", "clone", "--depth", "1", "--branch", pin["tag"],
         pin["repo"], str(target)],
        timeout=600,
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
            r = hidden_run(
                ["gh", "api", f"repos/{repo}/tarball/{pin['tag']}"],
                stdout=fh, stderr=PIPE, timeout=600, text=False,
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
                "commit_matches_pin": True,
                "content_verified": bool(res.get("verified_blobs")),
                "verification_method": "git_head" if res["acquisition"] == "git_clone" else "blob_sha1_tree_compare",
                "verified": bool(res.get("verified_blobs")),
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
    p.add_argument("--engine", default=None,
                   help="resolve a declared engine instead of the active one "
                        "(a rollback drill, not a switch)")
    p.add_argument("--offline", action="store_true",
                   help="skip live content verification; use recorded provenance")
    args = p.parse_args()

    result = (bootstrap() if args.bootstrap
              else resolve_easel(live=not args.offline, engine_id=args.engine))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
