#!/usr/bin/env python3
"""Reject new sensitive values in tracked receipts.

Why this exists
---------------
The public repository already contains receipts with raw provider voice IDs,
task/trace IDs and account balances, plus a PAYG key fingerprint. Those cannot be
removed from public history by a new commit. What a new commit *can* do is stop
adding more.

This checker scans tracked JSON receipts for new sensitive values. Existing
violations are recorded in a baseline by file and field path only — never by
value. A violation that is not in the baseline fails the check. Redacting a field
does not update the baseline automatically; `--write-baseline` is explicit and is
never used in CI.

It prints file names, field paths and kinds. It never prints a value.

Usage
-----
    python scripts/check_receipt_secrets.py
    python scripts/check_receipt_secrets.py --json
    python scripts/check_receipt_secrets.py --write-baseline   # explicit maintenance
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from process_utils import hidden_run  # noqa: E402

SCHEMA = "contentops.receipt-exposure-baseline/v1"
DEFAULT_BASELINE = ROOT / "reports" / "audits" / "receipt-exposure-baseline.json"

#: Exactly these key names carry provider identifiers or account money.
ID_KEYS = frozenset({
    "voice_id", "task_id", "trace_id", "file_id", "upload_file_id",
})
#: A fingerprint identifies the exposed credential even though it is not the key.
FINGERPRINT_KEYS = frozenset({"payg_key_fingerprint"})
#: Substrings that identify a credential field, not a hash or an exception name.
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


def _tracked_receipts(root: Path) -> List[Path]:
    result = hidden_run(
        ["git", "ls-files", "-z", "projects", "research/providers/receipts"],
        cwd=str(root), text=False, timeout=60)
    if result.returncode != 0:
        raise SystemExit("cannot list tracked receipts")
    paths = []
    for raw in (result.stdout or b"").split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="replace")
        if not rel.endswith(".json"):
            continue
        path = root / rel
        if path.is_file():
            paths.append(path)
    return sorted(paths)


def _is_redacted(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in REDACTED


def _kind_for(key: str, value: Any) -> str | None:
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


def _walk(value: Any, path: str = "") -> Iterable[Tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            kind = _kind_for(str(key), child)
            if kind:
                yield child_path, kind
            yield from _walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def scan(root: Path = ROOT, paths: Iterable[Path] | None = None
         ) -> List[Tuple[str, str, str]]:
    """Return (file, field, kind) for every sensitive value. No values."""
    violations: List[Tuple[str, str, str]] = []
    files = sorted(Path(item) for item in paths) if paths is not None         else _tracked_receipts(root)
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        for field, kind in _walk(data):
            violations.append((rel, field, kind))
        text = path.read_text(encoding="utf-8", errors="replace")
        if KEY_LIKE.search(text):
            violations.append((rel, "<text>", "credential_value"))
    return sorted(set(violations))


def _load_baseline(path: Path) -> Dict[str, set]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    files = data.get("files") or {}
    return {str(name): set(str(item) for item in items)
            for name, items in files.items()}


def _baseline_payload(violations: Iterable[Tuple[str, str, str]]) -> Dict[str, Any]:
    files: Dict[str, List[str]] = {}
    for rel, field, kind in violations:
        files.setdefault(rel, []).append(f"{field}::{kind}")
    return {
        "schema": SCHEMA,
        "note": "Field paths only. No values, no field contents.",
        "files": {name: sorted(set(items)) for name, items in sorted(files.items())},
    }


def check(root: Path = ROOT, baseline: Path = DEFAULT_BASELINE,
          paths: Iterable[Path] | None = None) -> Dict[str, Any]:
    violations = scan(root, paths=paths)
    known = _load_baseline(baseline)
    new = []
    for rel, field, kind in violations:
        if f"{field}::{kind}" in known.get(rel, set()):
            continue
        new.append({"file": rel, "field": field, "kind": kind})
    return {
        "schema": "contentops.receipt-secret-check/v1",
        "ok": not new,
        "violations": len(violations),
        "baseline_entries": sum(len(items) for items in known.values()),
        "new": new,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.write_baseline:
        violations = scan(args.root)
        payload = _baseline_payload(violations)
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        print(f"BASELINE_WRITTEN: {args.baseline} ({len(violations)} field paths)")
        return 0
    result = check(args.root, args.baseline)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"receipt-secrets PASS: {result['violations']} existing field paths, "
              f"{result['baseline_entries']} baselined, 0 new")
    else:
        print("receipt-secrets FAILED: new sensitive fields in tracked receipts")
        for item in result["new"]:
            print(f"  {item['file']}: {item['field']} ({item['kind']})")
        print("Redact the value and update the baseline only with explicit review.")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
