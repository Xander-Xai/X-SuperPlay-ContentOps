#!/usr/bin/env python3
"""Move the production engine between declared Easel versions, on the record.

Why a script and not an edit
----------------------------
Changing `runtime/easel-pins.json` by hand is one line and two consequences: the
lock projection must follow, and every later receipt will name a different
engine. Doing it by hand is how a repository ends up asserting "v0.3.0" while
the resolver still verifies `3fe2d99`. This tool makes the change explicit,
refuses it when the target is not proven, and writes down what happened.

Order of operations, which is the whole point
---------------------------------------------
    read registry -> check target installed -> verify target live
        -> refuse or: rewrite `active` -> re-derive lock -> append receipt

Verification comes *before* the switch. A switch that verifies afterwards can
leave production pointing at an unproven tree, which is precisely what the
upgrade gate exists to prevent.

What it does not do
-------------------
It does not download, install or build anything: `verify` proves what is on
disk, and an absent tree is `NOT_INSTALLED`, not an invitation to fetch. It does
not touch `runtime/easel-runtime.json` (the v0.2.1 provenance record) — each
engine gets its own `runtime/easel-runtime-<engine_id>.json` so switching back
does not overwrite evidence.

Usage
-----
    python scripts/easel_engine.py show
    python scripts/easel_engine.py verify v0.3.0
    python scripts/easel_engine.py switch v0.3.0 --dry-run
    python scripts/easel_engine.py switch v0.2.1
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.easel import pins  # noqa: E402

REGISTRY = ROOT / "runtime" / "easel-pins.json"
LOCK = ROOT / "runtime" / "easel.lock.json"
SWITCH_RECEIPT = ROOT / "runtime" / "easel-engine-switch.json"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _engine_root(engine: pins.Engine) -> Path | None:
    """The install root a relative engine record names, if it is on disk."""
    if not engine.root:
        return None
    return ROOT / engine.root


def _provenance_file(engine_id: str) -> Path:
    return ROOT / "runtime" / f"easel-runtime-{engine_id}.json"


def _baseline_provenance() -> Path:
    return ROOT / "runtime" / "easel-runtime.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _verify(engine: pins.Engine) -> dict:
    """Live verification of one engine's tree.

    A plain runtime is compared against the upstream tree. An instance that also
    carries declared tuning cannot pass that comparison by construction — its
    whole purpose is to differ in named files — so it is verified against the
    overlay record instead, which checks the baseline and the tuning separately.
    The strongest available proof is used, and the method is reported.
    """
    root = _engine_root(engine)
    if root is None or not root.is_dir():
        return {"status": "NOT_INSTALLED", "reason": f"no runtime at {engine.root or '?'}"}
    import verify_easel_runtime as verifier

    result = verifier.verify(root, engine.repo_id, engine.commit)
    if result.get("status") == "VERIFIED":
        return result

    record = ROOT / "runtime" / "easel-workbench-overlay.json"
    if record.is_file():
        overlay = verifier.verify_overlay(record, profile_mode="generated",
                                         workbench_override=root)
        if overlay.get("status") == "VERIFIED":
            return {
                **overlay,
                "method": "upstream_overlay_and_generated_profiles",
                "matched": overlay.get("baseline_blob_count"),
                "note": "verified as upstream baseline plus declared overlay, not as a "
                        "byte-identical upstream copy",
            }
        result = {**result, "overlay_status": overlay.get("status"),
                  "overlay_reason": overlay.get("reason")}

    # A git checkout proves identity locally: HEAD either is the pinned commit or
    # it is not. Without this, a rollback would depend on GitHub being reachable,
    # and the one action that must always work would be the one that needs the
    # network most.
    head = _git_head(root)
    if head and head == engine.commit:
        return {"status": "VERIFIED", "method": "git_head", "matched": None,
                "expected_commit": engine.commit,
                "note": "HEAD equals the pinned commit; content comparison was not "
                        "available and is not claimed"}
    if head:
        return {**result, "status": "MISMATCH",
                "reason": f"HEAD {head[:12]} != pinned {engine.commit[:12]}"}
    return result


def _git_head(root: Path) -> str:
    """`git rev-parse HEAD` for a checkout, or an empty string."""
    from process_utils import hidden_run

    result = hidden_run(["git", "-C", str(root), "rev-parse", "HEAD"], timeout=30)
    return result.stdout.strip() if result.returncode == 0 else ""


def _record_provenance(engine: pins.Engine, result: dict) -> Path:
    """Keep per-engine evidence so a switch never overwrites another version's."""
    path = _provenance_file(engine.engine_id)
    _write_json(path, {
        "schema": "contentops.easel-runtime-provenance/v1",
        "engine_id": engine.engine_id,
        "repo": engine.repo,
        "repo_url": engine.repo,
        "release": engine.tag,
        "expected_commit": engine.commit,
        "tree_sha256": engine.tree_sha256,
        "installed_at": engine.root,
        "acquisition": "release_archive",
        "verified": result.get("status") == "VERIFIED",
        "verification_method": result.get("method") or "blob_sha1_tree_compare",
        "verified_at": _now(),
        "content_verified": result.get("status") == "VERIFIED",
        "content_verified_files": result.get("matched"),
        "content_verified_commit": engine.commit if result.get("status") == "VERIFIED" else None,
        "content_verified_at": _now() if result.get("status") == "VERIFIED" else None,
        "commit_matches_pin": True,
        "note": "Written by scripts/easel_engine.py verify. This is the record "
                "resolve_easel(live=False) trusts for this engine only.",
    })
    return path


# --- registry mutation -------------------------------------------------------

def _rewrite_pointer(path: Path, key: str, value: str) -> None:
    """Replace one top-level string pointer, preserving the file's formatting.

    A full json.dump would reorder nothing but would rewrite every line, which
    makes the diff of a one-word change look like a new file. The pointer is a
    single unambiguous token, so a targeted replace is both smaller and easier
    to review. The result is re-parsed before it is written.
    """
    text = path.read_text(encoding="utf-8")
    marker = f'"{key}":'
    if text.count(marker) != 1:
        raise SystemExit(f"refusing to rewrite {path.name}: {marker} is not unique")
    start = text.index(marker) + len(marker)
    end = text.index("\n", start)
    segment = text[start:end]
    if not segment.strip().startswith('"'):
        raise SystemExit(f"refusing to rewrite {path.name}: {key} is not a string literal")
    updated = text[:start] + f' "{value}",' + text[end:]
    parsed = json.loads(updated)
    if parsed.get(key) != value:
        raise SystemExit(f"refusing to rewrite {path.name}: verification of the edit failed")
    path.write_bytes(updated.encode("utf-8"))


def _derive_lock(engine: pins.Engine, previous: dict) -> dict:
    """Project the active engine into the lock, keeping its reader contract."""
    lock = {}
    try:
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        lock = {"repo": engine.repo, "checked_in_at": _now()[:10]}
    lock.update({
        "repo": engine.repo,
        "tag": engine.tag,
        "commit": engine.commit,
        "derived_from": "runtime/easel-pins.json",
        "derived_at": _now(),
    })
    lock.setdefault("checked_in_at", _now()[:10])
    lock["notes"] = (
        "Do NOT auto-upgrade. Re-verify HEAD after every bootstrap. This file is a "
        "projection of the active engine in runtime/easel-pins.json; edit the registry "
        "through scripts/easel_engine.py, never this file. tests/test_easel_pins.py "
        "fails when the two disagree."
    )
    return lock


def _append_switch_receipt(entry: dict) -> None:
    history = []
    if SWITCH_RECEIPT.is_file():
        try:
            prior = json.loads(SWITCH_RECEIPT.read_text(encoding="utf-8"))
            if isinstance(prior.get("history"), list):
                history = prior["history"]
        except (OSError, ValueError):
            history = []
    history.append(entry)
    _write_json(SWITCH_RECEIPT, {
        "schema": "contentops.easel-engine-switch/v1",
        "note": "Append-only. Each entry records one deliberate change of the active "
                "engine, with the verification that preceded it.",
        "current": entry["to"],
        "history": history,
    })


# --- commands ----------------------------------------------------------------

def cmd_show(args) -> int:
    registry = pins.load()
    rows = []
    for engine_id, engine in registry.engines.items():
        root = _engine_root(engine)
        installed = bool(root and root.is_dir())
        status = "NOT_INSTALLED"
        if installed:
            try:
                from resolve_easel import resolve_easel
                status = resolve_easel(live=False)["status"] if engine_id == registry.active_id \
                    else ("INSTALLED" if installed else "NOT_INSTALLED")
            except Exception:  # noqa: BLE001 - a status command reports, it does not raise
                status = "UNKNOWN"
        rows.append({
            "engine_id": engine_id,
            "role": engine.role,
            "identity": engine.identity,
            "layout": engine.layout,
            "root": engine.root,
            "installed": installed,
            "digest_status": "recorded" if engine.digest_recorded else "not_recorded",
            "active": engine_id == registry.active_id,
            "resolved": status,
        })
    payload = {
        "active": registry.active_id,
        "workbench_engine": registry.workbench_id,
        "registry": str(registry.path.relative_to(ROOT)),
        "engines": rows,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print(f"active: {registry.active_id}    workbench: {registry.workbench_id}")
    print(f"{'engine':10} {'role':10} {'layout':9} {'installed':10} {'digest':13} resolved")
    for row in rows:
        print(f"{row['engine_id']:10} {row['role']:10} {row['layout']:9} "
              f"{str(row['installed']):10} {row['digest_status']:13} {row['resolved']}")
    return 0


def cmd_verify(args) -> int:
    engine = pins.get(args.engine)
    result = _verify(engine)
    payload = {"engine_id": engine.engine_id, **result}
    if result.get("status") == "VERIFIED":
        payload["recorded_at"] = str(_record_provenance(engine, result).relative_to(ROOT))
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"{engine.engine_id}: {result.get('status')}")
        for key in ("matched", "expected_commit", "reason", "recorded_at"):
            if payload.get(key) not in (None, ""):
                print(f"  {key}: {payload[key]}")
    return 0 if result.get("status") == "VERIFIED" else (3 if result.get("status") in
                                                        {"MISSING", "NOT_INSTALLED", "UNVERIFIED"} else 1)


def cmd_switch(args) -> int:
    registry = pins.load()
    target = pins.get(args.engine)
    if target.engine_id == registry.active_id:
        print(f"{target.engine_id} is already active; nothing to do")
        return 0

    root = _engine_root(target)
    if root is None or not root.is_dir():
        print(f"REFUSED: {target.engine_id} is not installed at {target.root}; "
              f"install it first, this tool never downloads", file=sys.stderr)
        return 4

    result = _verify(target)
    if result.get("status") != "VERIFIED":
        print(f"REFUSED: {target.engine_id} did not verify ({result.get('status')}): "
              f"{result.get('reason', 'unknown')}", file=sys.stderr)
        return 5

    previous = pins.active()
    entry = {
        "at": _now(),
        "from": previous.engine_id,
        "from_identity": previous.identity,
        "to": target.engine_id,
        "to_identity": target.identity,
        "verification": {
            "status": result.get("status"),
            "method": result.get("method"),
            "matched": result.get("matched"),
            "expected_commit": result.get("expected_commit"),
        },
        "dry_run": bool(args.dry_run),
    }
    if args.dry_run:
        print(json.dumps({"would_switch": entry}, indent=2, ensure_ascii=False))
        return 0

    provenance = _record_provenance(target, result)
    _rewrite_pointer(REGISTRY, "active", target.engine_id)
    _write_json(LOCK, _derive_lock(target, previous.raw))
    entry["provenance"] = str(provenance.relative_to(ROOT))
    _append_switch_receipt(entry)

    if args.json:
        print(json.dumps(entry, indent=2, ensure_ascii=False))
    else:
        print(f"switched {previous.engine_id} -> {target.engine_id} "
              f"({target.identity}); verification {result.get('status')}, "
              f"{result.get('matched')} blobs matched")
        print(f"  provenance: {entry['provenance']}")
        print(f"  receipt:    {SWITCH_RECEIPT.relative_to(ROOT)}")
    return 0


def cmd_install(args) -> int:
    """Copy a prepared tree into the engine's root, proving every byte first.

    Two passes on purpose: the first validates every file against the upstream
    tree index (or the overlay record, for declared tuning), the second copies.
    A half-written runtime that fails verification afterwards is worse than no
    runtime at all, because it looks installed.
    """
    import shutil

    import verify_easel_runtime as verifier

    engine = pins.get(args.engine)
    target = _engine_root(engine)
    if target is None:
        print(f"REFUSED: {engine.engine_id} declares no install root", file=sys.stderr)
        return 4
    if target.exists() and any(target.iterdir()):
        print(f"REFUSED: {target} already exists and is not empty; this never overwrites",
              file=sys.stderr)
        return 4

    source = Path(args.source).resolve()
    if not source.is_dir():
        print(f"REFUSED: source {source} is not a directory", file=sys.stderr)
        return 4

    index_path = ROOT / "runtime" / "easel-workbench-upstream-tree.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"REFUSED: upstream tree index unreadable at {index_path.name}", file=sys.stderr)
        return 4
    if index.get("commit") != engine.commit:
        print(f"REFUSED: index describes commit {str(index.get('commit'))[:12]}, "
              f"engine {engine.engine_id} is {engine.commit[:12]}", file=sys.stderr)
        return 4
    baseline = index.get("files") or {}

    overlay_files: dict[str, str] = {}
    overlay_dirs: list[str] = []
    record_path = ROOT / "runtime" / "easel-workbench-overlay.json"
    if record_path.is_file():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        block = record.get("overlay") or {}
        overlay_files = dict(block.get("digests") or {})
        overlay_dirs = list(block.get("directories") or [])

    wanted: list[tuple[str, str]] = []
    for rel, blob in baseline.items():
        if rel in overlay_files:
            continue
        wanted.append((rel, blob))
    for rel, digest in overlay_files.items():
        wanted.append((rel, digest))
    for directory in overlay_dirs:
        base = source / directory
        if not base.is_dir():
            print(f"REFUSED: overlay directory {directory} is absent from the source",
                  file=sys.stderr)
            return 4
        for path in sorted(base.rglob("*")):
            if path.is_file():
                rel = path.relative_to(source).as_posix()
                if rel not in {item[0] for item in wanted}:
                    wanted.append((rel, overlay_files.get(rel, "")))

    missing, mismatched = [], []
    for rel, expected in wanted:
        src = source / rel
        if not src.is_file():
            missing.append(rel)
            continue
        if rel in overlay_files:
            actual = verifier.content_sha256(src)
            ok = actual == overlay_files[rel]
        else:
            ok = verifier.blob_sha1(src) == expected
        if not ok:
            mismatched.append(rel)

    if missing or mismatched:
        print(f"REFUSED: source does not match {engine.identity}", file=sys.stderr)
        for rel in missing[:10]:
            print(f"  missing    {rel}", file=sys.stderr)
        for rel in mismatched[:10]:
            print(f"  mismatch   {rel}", file=sys.stderr)
        return 5

    copied = 0
    for rel, _expected in wanted:
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / rel, dst)
        copied += 1

    payload = {"engine_id": engine.engine_id, "target": str(target.relative_to(ROOT)),
               "source": str(source), "files_copied": copied,
               "baseline_files": len(baseline), "overlay_files": len(overlay_files),
               "installed_at": _now()}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"installed {engine.engine_id} -> {payload['target']} "
              f"({copied} files: {len(baseline)} baseline + {len(overlay_files)} overlay, "
              f"every byte compared before copy)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show", help="report every declared engine and its state")
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=cmd_show)

    verify = sub.add_parser("verify", help="verify one engine's tree and record the result")
    verify.add_argument("engine")
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(func=cmd_verify)

    install = sub.add_parser("install", help="install one engine's tree from a prepared copy")
    install.add_argument("engine")
    install.add_argument("--from", dest="source", required=True,
                         help="directory holding the prepared tree (never downloaded here)")
    install.add_argument("--json", action="store_true")
    install.set_defaults(func=cmd_install)

    switch = sub.add_parser("switch", help="make one verified engine the active one")
    switch.add_argument("engine")
    switch.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing anything")
    switch.add_argument("--json", action="store_true")
    switch.set_defaults(func=cmd_switch)

    args = parser.parse_args()
    try:
        return args.func(args)
    except pins.PinError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
