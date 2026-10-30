#!/usr/bin/env python3
"""Sign and verify approval-event chains with an external integrity key.

This module is intentionally explicit about the security boundary: HMAC
detects tampering when the key and policy are protected, but it does not prove
that a reviewer is human and is not non-repudiation.  Both inputs stay outside
the article/repository and are never copied into public artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVENTS = "approval-events.json"
POLICY_CONTRACT = "approval-signature-policy-v1"
ALGORITHM = "hmac-sha256"
GENESIS = hashlib.sha256(b"gzh-approval-events-genesis-v1").hexdigest()
DERIVED_FIELDS = {"signature", "signed_payload_sha256", "event_hash"}
REQUIRED_POLICY_KEYS = ("contract", "required", "algorithm", "key_ref", "genesis_hash", "expected_head_hash")


class DuplicateKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json_strict(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, DuplicateKey):
        return None


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac(key: bytes, data: bytes) -> str:
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_external(raw: str, article: Path) -> Path | None:
    if not str(raw or "").strip():
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve()
    banned = [ROOT.resolve(), article.resolve()]
    for root in banned:
        try:
            candidate.relative_to(root)
            return None
        except ValueError:
            pass
    return candidate


def _load_key(raw: str, article: Path) -> tuple[bytes | None, str | None]:
    path = _resolve_external(raw, article)
    if path is None or not path.is_file():
        return None, "key file must exist outside article/repository"
    try:
        key = path.read_bytes()
    except OSError:
        return None, "key file cannot be read"
    if len(key) < 32:
        return None, "HMAC key must contain at least 32 bytes"
    return key, None


def _load_policy(raw: str, article: Path) -> tuple[Path | None, dict[str, Any] | None, str | None]:
    path = _resolve_external(raw, article)
    if path is None or not path.is_file():
        return None, None, "signature policy must exist outside article/repository"
    data = _read_json_strict(path)
    if not isinstance(data, dict):
        return path, None, "signature policy is invalid JSON or contains duplicate keys"
    missing = [key for key in REQUIRED_POLICY_KEYS if key not in data]
    if missing:
        return path, None, "signature policy missing: " + ", ".join(missing)
    if data.get("contract") != POLICY_CONTRACT or data.get("algorithm") != ALGORITHM or data.get("required") is not True:
        return path, None, "signature policy contract/algorithm/required invalid"
    if not re.fullmatch(r"[0-9a-f]{64}", str(data.get("genesis_hash", ""))) or data.get("genesis_hash") != GENESIS:
        return path, None, "signature policy genesis_hash invalid"
    if not re.fullmatch(r"[0-9a-f]{64}", str(data.get("expected_head_hash", ""))):
        return path, None, "signature policy expected_head_hash invalid"
    if not str(data.get("key_ref", "")).strip():
        return path, None, "signature policy key_ref missing"
    trusted = data.get("trusted_key_refs")
    if not isinstance(trusted, list) or str(data.get("key_ref")) not in {str(item) for item in trusted}:
        return path, None, "signature policy key_ref is not in trusted_key_refs"
    return path, data, None


def _write_json_atomic(path: Path, value: Any) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def init_policy(policy_raw: str, article: Path, key_ref: str) -> int:
    path = _resolve_external(policy_raw, article)
    if path is None:
        print("SIGNATURE POLICY BLOCKED: policy must be outside article/repository")
        return 1
    if not str(key_ref).strip() or not re.fullmatch(r"[A-Za-z0-9_.:-]+", key_ref):
        print("SIGNATURE POLICY BLOCKED: key_ref contains invalid characters")
        return 1
    policy = {
        "schema_version": 1,
        "contract": POLICY_CONTRACT,
        "required": True,
        "algorithm": ALGORITHM,
        "key_ref": key_ref,
        "trusted_key_refs": [key_ref],
        "genesis_hash": GENESIS,
        "expected_head_hash": GENESIS,
        "created_at": _now(),
        "updated_at": _now(),
        "migration": None,
        "identity_note": "HMAC integrity only; does not authenticate a human or provide non-repudiation",
    }
    if path.exists():
        print("SIGNATURE POLICY BLOCKED: refusing to overwrite existing policy")
        return 1
    _write_json_atomic(path, policy)
    print("SIGNATURE POLICY CREATED: external policy initialized")
    return 0


def _load_events(article: Path) -> tuple[Path, list[dict[str, Any]] | None, str | None]:
    path = article / EVENTS
    data = _read_json_strict(path)
    if not isinstance(data, list):
        return path, None, "approval-events.json must be a JSON array without duplicate keys"
    if not data:
        return path, None, "approval-events.json cannot be empty for a required signature chain"
    if any(not isinstance(item, dict) for item in data):
        return path, None, "approval-events.json contains a non-object event"
    return path, data, None


def _safe_scope_path(article: Path, raw: Any) -> Path | None:
    text = str(raw or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or re.match(r"^[A-Za-z]:", text) or "\x00" in text:
        return None
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return None
    path = (article / "/".join(parts)).resolve()
    try:
        path.relative_to(article.resolve())
    except ValueError:
        return None
    return path


def _scope_errors(article: Path, event: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    scopes = event.get("scope")
    hashes = event.get("scope_sha256")
    if not isinstance(scopes, list) or not scopes or not isinstance(hashes, dict):
        return [f"event {event.get('event_id', '<missing>')}: scope/scope_sha256 invalid"]
    if set(str(item) for item in scopes) != set(str(key) for key in hashes):
        errors.append(f"event {event.get('event_id', '<missing>')}: scope and scope_sha256 keys differ")
    for raw in scopes:
        path = _safe_scope_path(article, raw)
        key = str(raw)
        expected = str(hashes.get(key, "")).lower()
        if path is None or not path.is_file():
            errors.append(f"event {event.get('event_id', '<missing>')}: unsafe/missing scope path {key}")
        elif not re.fullmatch(r"[0-9a-f]{64}", expected) or _sha256_bytes(path.read_bytes()) != expected:
            errors.append(f"event {event.get('event_id', '<missing>')}: scope hash mismatch {key}")
    return errors


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if key not in DERIVED_FIELDS}


def _event_hash(event: dict[str, Any]) -> str:
    return _sha256_bytes(_canonical({key: value for key, value in event.items() if key != "event_hash"}))


def _verify_chain(article: Path, events: list[dict[str, Any]], policy: dict[str, Any], key: bytes, expected_head: str | None = None) -> tuple[list[str], str]:
    errors: list[str] = []
    seen: set[str] = set()
    previous = str(policy["genesis_hash"])
    head = previous
    for index, event in enumerate(events):
        event_id = str(event.get("event_id", "")).strip()
        if not event_id:
            errors.append(f"event[{index}] missing event_id")
        elif event_id in seen:
            errors.append(f"duplicate event_id: {event_id}")
        seen.add(event_id)
        if event.get("signature_alg") != ALGORITHM or event.get("key_ref") != policy.get("key_ref"):
            errors.append(f"event {event_id or index}: algorithm/key_ref mismatch")
        if event.get("prev_event_hash") != previous:
            errors.append(f"event {event_id or index}: chain ordering/truncation mismatch")
        payload = _payload(event)
        payload_bytes = _canonical(payload)
        digest = _sha256_bytes(payload_bytes)
        signature = str(event.get("signature", "")).lower()
        if event.get("signed_payload_sha256") != digest:
            errors.append(f"event {event_id or index}: signed_payload_sha256 mismatch")
        if not re.fullmatch(r"[0-9a-f]{64}", signature) or not hmac.compare_digest(signature, _hmac(key, payload_bytes)):
            errors.append(f"event {event_id or index}: signature mismatch")
        errors.extend(_scope_errors(article, event))
        if event.get("schema_version") != 2:
            errors.append(f"event {event_id or index}: schema_version must be 2 when signed")
        head = _event_hash(event)
        previous = head
    wanted = expected_head if expected_head is not None else str(policy.get("expected_head_hash", ""))
    if head != wanted:
        errors.append("signature chain head does not match protected policy expected_head_hash")
    return errors, head


def verify_events(article: Path, policy_raw: str, key_raw: str) -> list[str]:
    _, policy, policy_error = _load_policy(policy_raw, article)
    if policy_error or policy is None:
        return [policy_error or "invalid signature policy"]
    key, key_error = _load_key(key_raw, article)
    if key_error or key is None:
        return [key_error or "invalid signing key"]
    _, events, events_error = _load_events(article)
    if events_error or events is None:
        return [events_error or "invalid approval events"]
    errors, _ = _verify_chain(article, events, policy, key)
    return errors


def sign_events(article: Path, policy_raw: str, key_raw: str, migrate: bool = False) -> int:
    policy_path, policy, policy_error = _load_policy(policy_raw, article)
    if policy_error or policy is None or policy_path is None:
        print(f"SIGNATURE BLOCKED: {policy_error or 'invalid signature policy'}")
        return 1
    key, key_error = _load_key(key_raw, article)
    if key_error or key is None:
        print(f"SIGNATURE BLOCKED: {key_error or 'invalid signing key'}")
        return 1
    events_path, events, events_error = _load_events(article)
    if events_error or events is None:
        print(f"SIGNATURE BLOCKED: {events_error or 'invalid approval events'}")
        return 1
    signed = [bool(item.get("signature")) for item in events]
    first_unsigned = next((index for index, value in enumerate(signed) if not value), None)
    if first_unsigned is None:
        errors = verify_events(article, policy_raw, key_raw)
        if errors:
            print("SIGNATURE BLOCKED:")
            for error in errors:
                print(f"- {error}")
            return 1
        print("SIGNATURE ALREADY VALID: no changes")
        return 0
    if any(signed[index] for index in range(first_unsigned, len(events))):
        print("SIGNATURE BLOCKED: signed and unsigned events are interleaved")
        return 1
    if first_unsigned == 0:
        if not migrate:
            print("SIGNATURE BLOCKED: legacy unsigned events require explicit --migrate")
            return 1
        if str(policy.get("expected_head_hash")) != str(policy.get("genesis_hash")):
            print("SIGNATURE BLOCKED: policy head is not genesis; refusing implicit legacy migration")
            return 1
    else:
        prefix_errors, prefix_head = _verify_chain(article, events[:first_unsigned], policy, key, expected_head=str(policy.get("expected_head_hash")))
        if prefix_errors:
            print("SIGNATURE BLOCKED: existing signed prefix invalid")
            for error in prefix_errors:
                print(f"- {error}")
            return 1
        if prefix_head != str(policy.get("expected_head_hash")):
            print("SIGNATURE BLOCKED: policy head does not match signed prefix")
            return 1
    previous = str(policy["genesis_hash"]) if first_unsigned == 0 else _event_hash(events[first_unsigned - 1])
    for event in events[first_unsigned:]:
        event.pop("signature", None)
        event.pop("signed_payload_sha256", None)
        event.pop("event_hash", None)
        event["schema_version"] = 2
        event["signature_alg"] = ALGORITHM
        event["key_ref"] = str(policy["key_ref"])
        event["prev_event_hash"] = previous
        payload_bytes = _canonical(_payload(event))
        event["signed_payload_sha256"] = _sha256_bytes(payload_bytes)
        event["signature"] = _hmac(key, payload_bytes)
        previous = _event_hash(event)
        event["event_hash"] = previous
    _write_json_atomic(events_path, events)
    policy["expected_head_hash"] = previous
    policy["updated_at"] = _now()
    if first_unsigned == 0:
        policy["migration"] = {"mode": "legacy-unsigned-explicit", "migrated_at": _now(), "event_count": len(events)}
    _write_json_atomic(policy_path, policy)
    print(f"SIGNATURE APPLIED: {len(events) - first_unsigned} events; HMAC integrity chain updated")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--article", required=True, type=Path)
    init.add_argument("--policy", required=True)
    init.add_argument("--key-ref", required=True)
    for name in ("sign", "verify"):
        item = sub.add_parser(name)
        item.add_argument("--article", required=True, type=Path)
        item.add_argument("--policy", required=True)
        item.add_argument("--key-file", required=True)
        if name == "sign":
            item.add_argument("--migrate", action="store_true", help="显式迁移已有未签名事件")
    args = parser.parse_args()
    article = args.article.expanduser()
    if not article.is_absolute():
        article = ROOT / article
    article = article.resolve()
    if args.command == "init":
        return init_policy(args.policy, article, args.key_ref)
    if args.command == "sign":
        return sign_events(article, args.policy, args.key_file, bool(args.migrate))
    errors = verify_events(article, args.policy, args.key_file)
    if errors:
        print("SIGNATURE VERIFY BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("SIGNATURE VERIFY PASSED: chain, policy, scopes and event hashes match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
