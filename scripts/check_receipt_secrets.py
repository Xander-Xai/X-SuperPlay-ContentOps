#!/usr/bin/env python3
"""Reject new or changed sensitive values in tracked receipts.

Why this exists
---------------
The public repository already contains receipts with raw provider voice IDs,
task/trace IDs and account balances, plus a PAYG key fingerprint. Those cannot be
removed from public history by a new commit. What a new commit *can* do is stop
adding or changing them.

The earlier field-path-only baseline allowed a changed value at an already
baselined path. This version is **diff-relative**: a field is allowed only when
its path is reviewed *and* its value is unchanged from a trusted base (the PR
base or the previous main commit). No value and no hash of a low-entropy value is
stored in the baseline.

Usage
-----
    python scripts/check_receipt_secrets.py
    python scripts/check_receipt_secrets.py --base origin/main
    python scripts/check_receipt_secrets.py --write-baseline   # explicit maintenance

The check prints file names, field paths and reasons. It never prints a value.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from process_utils import hidden_run  # noqa: E402

SCHEMA = "contentops.receipt-exposure-baseline/v2"
LEGACY_SCHEMAS = {"contentops.receipt-exposure-baseline/v1"}
DEFAULT_BASELINE = ROOT / "reports" / "audits" / "receipt-exposure-baseline.json"

ID_KEYS = frozenset({
    "voice_id", "task_id", "trace_id", "file_id", "upload_file_id",
})
FINGERPRINT_KEYS = frozenset({"payg_key_fingerprint"})
CREDENTIAL_KEYS = frozenset({
    "api_key", "secret_key", "access_token", "auth_token", "bearer",
    "cookie", "password",
})
REDACTED = {"", "<redacted>", "redacted", "null", "none", "***"}

KEY_LIKE = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY)")
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
NUMERIC = re.compile(r"^-?\d+(\.\d+)?$")


class CheckError(Exception):
    """A refusal that is not a receipt violation."""


def _tracked_receipts(root: Path) -> List[Path]:
    result = hidden_run(
        ["git", "ls-files", "-z", "projects", "research/providers/receipts"],
        cwd=str(root), text=False, timeout=60)
    if result.returncode != 0:
        raise CheckError("cannot list tracked receipts")
    paths: List[Path] = []
    for raw in (result.stdout or b"").split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="replace").replace("\\", "/")
        if "/receipts/" not in rel and not rel.startswith("research/providers/receipts/"):
            continue
        path = root / rel
        if path.is_file():
            paths.append(path)
    return sorted(paths)


def _is_redacted(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in REDACTED


def _kind_for(key: str, value: Any) -> Optional[str]:
    folded = key.casefold()
    if folded.endswith("_hash"):
        return None
    if folded in ID_KEYS:
        if _is_redacted(value) or (isinstance(value, str) and HEX64.fullmatch(value)):
            return None
        return "provider_id"
    if folded in FINGERPRINT_KEYS:
        return None if _is_redacted(value) else "key_fingerprint"
    if folded.endswith("_balance") or folded == "balance":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return "balance"
        if isinstance(value, str) and NUMERIC.fullmatch(value.strip()):
            return "balance"
        return None
    if folded in CREDENTIAL_KEYS:
        return None if _is_redacted(value) else "credential"
    return None


def _walk(value: Any, path: str = "") -> Iterable[Tuple[str, str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            kind = _kind_for(str(key), child)
            if kind:
                yield child_path, kind, child
            yield from _walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text_tokens(text: str) -> Set[str]:
    return {match.group(0) for match in KEY_LIKE.finditer(text)}


def _scan_values(root: Path, paths: Optional[Iterable[Path]] = None
                 ) -> Tuple[List[Tuple[str, str, str, Any]], List[Tuple[str, str, str, Any]]]:
    """Return (structured values, text tokens); no value is printed."""
    files = sorted(Path(item) for item in paths) if paths is not None \
        else _tracked_receipts(root)
    structured: List[Tuple[str, str, str, Any]] = []
    text_hits: List[Tuple[str, str, str, Any]] = []
    for path in files:
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if path.suffix.lower() == ".json":
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                structured.append((rel, "<json>", "malformed_json", None))
            else:
                for field, kind, value in _walk(data):
                    structured.append((rel, field, kind, value))
        tokens = _text_tokens(text)
        if tokens:
            text_hits.append((rel, "<text>", "credential_value", tokens))
    return structured, text_hits


def scan(root: Path = ROOT, paths: Optional[Iterable[Path]] = None
         ) -> List[Tuple[str, str, str]]:
    structured, text_hits = _scan_values(root, paths=paths)
    found = {(rel, field, kind) for rel, field, kind, _ in structured + text_hits}
    return sorted(found)


def _git_show(root: Path, ref: str, rel: str) -> Optional[str]:
    result = hidden_run(["git", "show", f"{ref}:{rel}"], cwd=str(root),
                        text=True, timeout=60)
    return result.stdout if result.returncode == 0 else None


def _base_value(root: Path, base: str, rel: str, field: str, kind: str,
                current: Any) -> Tuple[bool, str]:
    """Whether the current value equals the base value at the same path."""
    text = _git_show(root, base, rel)
    if text is None:
        return False, "base_file_missing"
    if kind == "malformed_json":
        return False, "malformed_json"
    if field == "<text>":
        return _text_tokens(text) == current, "changed_text_token"
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False, "base_json_malformed"
    for candidate_field, candidate_kind, candidate_value in _walk(data):
        if candidate_field == field and candidate_kind == kind:
            return _canonical(candidate_value) == _canonical(current), "changed_value"
    return False, "base_field_missing"


def _read_baseline_from_text(text: str, *, require_v2: bool) -> Dict[str, Set[str]]:
    data = json.loads(text)
    schema = data.get("schema")
    if require_v2 and schema != SCHEMA:
        raise CheckError("BASELINE_LEGACY" if schema in LEGACY_SCHEMAS
                         else "BASELINE_SCHEMA_INVALID")
    if not require_v2 and schema not in {SCHEMA, *LEGACY_SCHEMAS}:
        raise CheckError("BASELINE_SCHEMA_INVALID")
    files = data.get("files") or {}
    return {str(name): set(str(item) for item in items)
            for name, items in files.items()}


def _read_baseline(path: Path, *, require_v2: bool) -> Dict[str, Set[str]]:
    if not path.is_file():
        return {}
    return _read_baseline_from_text(path.read_text(encoding="utf-8"), require_v2=require_v2)


def _baseline_payload(root: Path, paths: Optional[Iterable[Path]] = None) -> Dict[str, Any]:
    violations = scan(root, paths=paths)
    files: Dict[str, List[str]] = {}
    for rel, field, kind in violations:
        files.setdefault(rel, []).append(f"{field}::{kind}")
    return {
        "schema": SCHEMA,
        "note": "Field paths only. Values are compared against the trusted base; no value or value hash is stored.",
        "files": {name: sorted(set(items)) for name, items in sorted(files.items())},
    }


def _resolve_base(root: Path, explicit: Optional[str]) -> str:
    requested = explicit if explicit is not None else os.environ.get("CONTENTOPS_RECEIPT_BASE")
    candidates = [requested] if requested is not None else ["origin/main", "HEAD^"]
    for candidate in candidates:
        if not candidate:
            continue
        result = hidden_run(["git", "rev-parse", "--verify", f"{candidate}^{{commit}}"],
                            cwd=str(root), text=True, timeout=30)
        if result.returncode == 0:
            return candidate
    raise CheckError("BASE_REQUIRED")


def check(root: Path = ROOT, baseline: Path = DEFAULT_BASELINE,
          paths: Optional[Iterable[Path]] = None,
          base: Optional[str] = None) -> Dict[str, Any]:
    current = _read_baseline(baseline, require_v2=True)
    base_ref = _resolve_base(root, base)
    try:
        baseline_rel = baseline.relative_to(root).as_posix()
    except ValueError:
        baseline_rel = None
    if baseline_rel:
        base_text = _git_show(root, base_ref, baseline_rel)
        if base_text:
            try:
                base_current = _read_baseline_from_text(base_text, require_v2=False)
            except CheckError:
                base_current = {}
        else:
            base_current = {}
    else:
        base_current = {}
    growth = sorted(
        f"{name}::{item}"
        for name, items in current.items()
        for item in items - base_current.get(name, set()))
    structured, text_hits = _scan_values(root, paths=paths)
    new: List[Dict[str, str]] = []
    for rel, field, kind, value in structured + text_hits:
        key = f"{field}::{kind}"
        if key not in current.get(rel, set()):
            new.append({"file": rel, "field": field, "kind": kind, "reason": "new_path"})
            continue
        unchanged, reason = _base_value(root, base_ref, rel, field, kind, value)
        if not unchanged:
            new.append({"file": rel, "field": field, "kind": kind, "reason": reason})
    if growth:
        new.append({"file": str(baseline), "field": "<baseline>",
                    "kind": "baseline_growth", "reason": "baseline_growth"})
    return {
        "schema": "contentops.receipt-secret-check/v1",
        "ok": not new,
        "base": base_ref,
        "violations": len(structured) + len(text_hits),
        "baseline_entries": sum(len(items) for items in current.values()),
        "growth": growth,
        "new": new,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--base", default=None,
                        help="trusted base ref/SHA; default origin/main or HEAD^")
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--allow-baseline-growth", action="store_true",
                        help="explicit reviewed migration; never used in CI")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.write_baseline:
        old = _read_baseline(args.baseline, require_v2=False)
        payload = _baseline_payload(args.root)
        new_paths = {name: set(items) for name, items in payload["files"].items()}
        growth = sorted(
            f"{name}::{item}" for name, items in new_paths.items()
            for item in items - old.get(name, set()))
        if growth and not args.allow_baseline_growth:
            print("BASELINE_GROWTH_REFUSED: a new sensitive path needs explicit review")
            for item in growth:
                print(f"  {item}")
            return 1
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        print(f"BASELINE_WRITTEN: {args.baseline} "
              f"({sum(len(items) for items in new_paths.values())} field paths)")
        return 0
    try:
        result = check(args.root, args.baseline, base=args.base)
    except CheckError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"receipt-secrets REFUSED: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"receipt-secrets PASS: {result['violations']} existing values, "
              f"{result['baseline_entries']} baselined paths, base {result['base']}, 0 new")
    else:
        print("receipt-secrets FAILED: new or changed sensitive values")
        for item in result["new"]:
            print(f"  {item['file']}: {item['field']} ({item['kind']}; {item['reason']})")
        print("Do not edit the baseline to bless a new value without explicit review.")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
