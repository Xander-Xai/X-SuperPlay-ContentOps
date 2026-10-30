#!/usr/bin/env python3
"""Integrity metadata for workflow receipts.

Receipts are public-ish audit artifacts, so they must carry the exact article
snapshot, account slot, producer and a tamper-evident signature.  Production
keys must come from an external file (or, in a future adapter, an external
signer); a raw environment-variable secret is deliberately rejected because
the same local agent can set both the signing and verification environment.
Network-free fixtures use a deterministic test key only when
``WORKFLOW_TEST_MODE=1`` and are marked with a separate test namespace.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PRODUCER = "gzh-workflow-receipt-producer"
SCHEMA_VERSION = 2
SIGNATURE_ALGORITHM = "hmac-sha256"
TEST_KEY = hashlib.sha256(b"gzh-workflow-test-receipt-key-v1").digest()
DERIVED_FIELDS = {"signature", "signed_payload_sha256", "signature_status"}
PRODUCTION_NAMESPACE = "production"
TEST_NAMESPACE = "test-fixture"
PRODUCTION_ISSUER = "external-signer"
TEST_ISSUER = "workflow-test-fixture"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes()) if path.is_file() else ""


def external_key_path() -> Path | None:
    """Return the external production key path without reading its contents.

    Explicit ``WORKFLOW_RECEIPT_SIGNING_KEY_PATH`` wins.  For this single
    local workflow, a fixed path one level outside the project is a safe
    fallback, so callers launched from different working directories do not
    lose the trust root merely because an environment variable was omitted.
    """
    raw_path = os.environ.get("WORKFLOW_RECEIPT_SIGNING_KEY_PATH", "").strip()
    path = Path(raw_path).expanduser().resolve() if raw_path else (ROOT.parent.parent / "workflow-receipt-signing.key").resolve()
    try:
        path.relative_to(ROOT.resolve())
        return None
    except ValueError:
        return path if path.is_file() else None


def _key() -> bytes | None:
    # Test mode is an explicit fixture namespace.  It must never consume a
    # production key supplied by the process environment.
    if os.environ.get("WORKFLOW_TEST_MODE") == "1":
        return TEST_KEY
    # A raw env secret is not an independent trust root: an article-writing
    # agent can set it and immediately verify its own forged receipt.  Keep
    # the variable name for diagnostics/compatibility, but fail closed.
    if os.environ.get("WORKFLOW_RECEIPT_SIGNING_KEY", "").strip():
        return None
    path = external_key_path()
    if path is not None:
        try:
            key = path.read_bytes()
        except OSError:
            return None
        return key if len(key) >= 32 else None
    if os.environ.get("WORKFLOW_TEST_MODE") == "1":
        return TEST_KEY
    return None


def _payload(document: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key not in DERIVED_FIELDS}


def _signature(document: dict[str, Any], key: bytes) -> tuple[str, str]:
    payload = _canonical(_payload(document))
    return _sha256_bytes(payload), hmac.new(key, payload, hashlib.sha256).hexdigest()


def stamp(
    document: dict[str, Any],
    article_dir: Path,
    *,
    receipt_kind: str,
    account_slot: int | str | None,
    env_path: Path | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    """Return a signed, article-bound copy of a receipt document."""

    result = dict(document)
    result.update({
        "schema_version": SCHEMA_VERSION,
        "producer": PRODUCER,
        "receipt_kind": receipt_kind,
        "operation_id": operation_id or str(uuid.uuid4()),
        "article_sha256": sha256_file(article_dir / "article.md"),
        "html_sha256": sha256_file(article_dir / "article.html"),
        "account_slot": int(account_slot) if str(account_slot or "").isdigit() else account_slot,
        "signed_at": datetime.now(timezone.utc).isoformat(),
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "trust_namespace": TEST_NAMESPACE if os.environ.get("WORKFLOW_TEST_MODE") == "1" else PRODUCTION_NAMESPACE,
        "issuer": TEST_ISSUER if os.environ.get("WORKFLOW_TEST_MODE") == "1" else PRODUCTION_ISSUER,
    })
    if env_path is not None and env_path.is_file():
        result["env_sha256"] = sha256_file(env_path)
    key = _key()
    if key is None:
        # Keep the artifact explicit; the gate will fail closed in production.
        result["signature_status"] = "rejected_untrusted_key_source" if os.environ.get("WORKFLOW_RECEIPT_SIGNING_KEY", "").strip() else "missing_external_key"
        result["signed_payload_sha256"] = ""
        result["signature"] = ""
        return result
    payload_hash, signature = _signature(result, key)
    result["signed_payload_sha256"] = payload_hash
    result["signature"] = signature
    result["signature_status"] = "signed"
    return result


def verify(
    document: dict[str, Any],
    article_dir: Path,
    *,
    receipt_kind: str,
    account_slot: int | str | None = None,
    env_path: Path | None = None,
) -> list[str]:
    """Verify producer, article snapshot, slot, and HMAC signature."""

    errors: list[str] = []
    if not isinstance(document, dict):
        return ["回执必须是 JSON 对象"]
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"回执 schema_version 必须是 {SCHEMA_VERSION}")
    if document.get("producer") != PRODUCER:
        errors.append("回执 producer 不是受信工作流生产器")
    if document.get("receipt_kind") != receipt_kind:
        errors.append(f"回执 receipt_kind 必须是 {receipt_kind}")
    namespace = str(document.get("trust_namespace") or "").strip()
    issuer = str(document.get("issuer") or "").strip()
    test_mode = os.environ.get("WORKFLOW_TEST_MODE") == "1"
    if test_mode:
        if namespace != TEST_NAMESPACE or issuer != TEST_ISSUER:
            errors.append("测试模式回执必须使用独立 test-fixture namespace/issuer")
        if str(document.get("target_kind") or "").strip().lower() == "wechat":
            errors.append("测试 namespace 禁止声明 target_kind=wechat；只能生成 mock 回执")
    else:
        if namespace != PRODUCTION_NAMESPACE or issuer != PRODUCTION_ISSUER:
            errors.append("生产回执必须来自 external-signer production namespace")
    if not str(document.get("operation_id") or "").strip():
        errors.append("回执缺少 operation_id")
    if document.get("article_sha256") != sha256_file(article_dir / "article.md"):
        errors.append("回执 article_sha256 与当前 article.md 不一致")
    if document.get("html_sha256") != sha256_file(article_dir / "article.html"):
        errors.append("回执 html_sha256 与当前 article.html 不一致")
    if account_slot is not None:
        try:
            if int(document.get("account_slot")) != int(account_slot):
                errors.append("回执 account_slot 与当前工作流槽位不一致")
        except (TypeError, ValueError):
            errors.append("回执缺少数值 account_slot")
    if env_path is not None and env_path.is_file() and document.get("env_sha256") != sha256_file(env_path):
        errors.append("回执 env_sha256 与当前外部凭证文件不一致")
    key = _key()
    signature = str(document.get("signature") or "")
    payload_hash = str(document.get("signed_payload_sha256") or "")
    if key is None:
        if os.environ.get("WORKFLOW_RECEIPT_SIGNING_KEY", "").strip() and not test_mode:
            errors.append("生产回执禁止使用 WORKFLOW_RECEIPT_SIGNING_KEY；请使用仓库外 WORKFLOW_RECEIPT_SIGNING_KEY_PATH 或外部 signer")
        else:
            errors.append("缺少外部 WORKFLOW_RECEIPT_SIGNING_KEY_PATH；回执不能在生产模式下验签")
    elif not signature or not payload_hash:
        errors.append("回执缺少签名或 signed_payload_sha256")
    else:
        expected_payload_hash, expected_signature = _signature(document, key)
        if payload_hash != expected_payload_hash:
            errors.append("回执 signed_payload_sha256 不匹配")
        if not hmac.compare_digest(signature, expected_signature):
            errors.append("回执 HMAC 签名不匹配")
    return errors
