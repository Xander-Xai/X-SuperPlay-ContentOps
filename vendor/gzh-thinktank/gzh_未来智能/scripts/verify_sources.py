#!/usr/bin/env python3
"""Fetch and fingerprint external research sources without storing credentials.

A1（对抗审查加固）：来源状态与 content_sha256 不再允许自填。本验证器每次运行
产出两样东西，门禁只信任它们：

1. ``source-snapshots/<source_id>.raw`` —— 真实抓取的原始响应字节（或离线导入
   的快照文件），是“哈希声称的内容”的物理存在；
2. ``source-verification.json`` —— 机器回执：url 规范化值、真实响应哈希、
   快照文件与快照哈希、抓取时间、验证器版本、验证模式。

门禁侧重新计算快照文件的 SHA-256 并与回执、sources.json 双向绑定；任何
“只填 64 位十六进制、没有快照”的来源都会被阻断。

离线模式：``--offline-import <dir>`` 让操作员提供快照文件（如浏览器另存），
验证器只负责指纹化与回执，不联网。离线导入不是免检，快照文件本身必须存在。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFIER_VERSION = "1.2.0"
MAX_SNAPSHOT_BYTES = 2_000_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_kinds() -> set[str]:
    return {"local_artifact", "reproduction", "test-fixture"}


def _external_sources(document: dict) -> list[dict]:
    sources = document.get("sources") if isinstance(document, dict) else None
    if not isinstance(sources, list):
        return []
    return [
        source
        for source in sources
        if isinstance(source, dict) and str(source.get("kind", "external")).lower() not in _local_kinds()
    ]


def _normalize_url(raw: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(raw)
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"
        normalized = urllib.parse.urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))
        return normalized.rstrip("/")
    except ValueError:
        return raw.strip()


def _snapshot_dir(article_dir: Path) -> Path:
    path = article_dir / "source-snapshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_receipt(article_dir: Path, mode: str, records: list[dict]) -> None:
    receipt = {
        "schema_version": 1,
        "contract": "source-verification-v1",
        "verifier": "verify_sources.py",
        "verifier_version": VERIFIER_VERSION,
        "mode": mode,  # online | offline-import
        "verified_at": _now(),
        "sources": records,
    }
    (article_dir / "source-verification.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def verify(article_dir: Path) -> int:
    source_path = article_dir / "sources.json"
    if not source_path.is_file():
        print(f"SOURCE VERIFY BLOCKED: 缺少 {source_path}")
        return 1
    try:
        document = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"SOURCE VERIFY BLOCKED: 无法解析 sources.json：{exc}")
        return 1
    external = _external_sources(document)
    failures: list[str] = []
    records: list[dict] = []
    for source in external:
        source_id = str(source.get("id", "unknown"))
        url = str(source.get("url", "")).strip()
        if not url.startswith(("http://", "https://")):
            failures.append(f"{source_id}: 缺少 HTTP(S) URL")
            continue
        snapshot = _snapshot_dir(article_dir) / f"{source_id}.raw"
        request = urllib.request.Request(url, headers={"User-Agent": "gzh-workflow-source-verifier/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = int(getattr(response, "status", 200) or 200)
                length_header = response.headers.get("Content-Length")
                try:
                    declared_length = int(length_header) if length_header else None
                except (TypeError, ValueError):
                    declared_length = None
                if declared_length is not None and declared_length > MAX_SNAPSHOT_BYTES:
                    failures.append(f"{source_id}: response exceeds {MAX_SNAPSHOT_BYTES} byte snapshot cap; use --offline-import")
                    source["retrieval_status"] = "blocked"
                    source["http_status"] = status
                    continue
                # Read one extra byte so a chunked/unknown-length response
                # cannot silently hash only the first MAX_SNAPSHOT_BYTES.
                body = response.read(MAX_SNAPSHOT_BYTES + 1)
                if len(body) > MAX_SNAPSHOT_BYTES:
                    failures.append(f"{source_id}: response exceeds {MAX_SNAPSHOT_BYTES} byte snapshot cap; use --offline-import")
                    source["retrieval_status"] = "blocked"
                    source["http_status"] = status
                    continue
            if status < 200 or status >= 400:
                failures.append(f"{source_id}: HTTP {status}")
                source["retrieval_status"] = "blocked"
                source["http_status"] = status
                continue
            snapshot.write_bytes(body)
            content_sha256 = hashlib.sha256(body).hexdigest()
            source["retrieval_status"] = "passed"
            source["http_status"] = status
            source["retrieved_at"] = _now()
            source["content_sha256"] = content_sha256
            records.append({
                "id": source_id,
                "url": url,
                "url_normalized": _normalize_url(url),
                "status": "passed",
                "http_status": status,
                "content_sha256": content_sha256,
                "snapshot": f"source-snapshots/{source_id}.raw",
                "snapshot_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                "fetched_at": _now(),
            })
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            source["retrieval_status"] = "blocked"
            failures.append(f"{source_id}: {exc.__class__.__name__}")
    source_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_receipt(article_dir, "online", records)
    if failures:
        print("SOURCE VERIFY BLOCKED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"SOURCE VERIFY PASSED: {len(records)} external sources fingerprinted")
    return 0


def offline_import(article_dir: Path, snapshot_dir: Path) -> int:
    """离线导入：操作员提供 <source_id>.raw 快照文件，验证器只做指纹化与回执。"""
    source_path = article_dir / "sources.json"
    if not source_path.is_file():
        print(f"SOURCE VERIFY BLOCKED: 缺少 {source_path}")
        return 1
    try:
        document = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"SOURCE VERIFY BLOCKED: 无法解析 sources.json：{exc}")
        return 1
    if not snapshot_dir.is_dir():
        print(f"SOURCE VERIFY BLOCKED: 离线快照目录不存在：{snapshot_dir}")
        return 1
    external = _external_sources(document)
    failures: list[str] = []
    records: list[dict] = []
    target = _snapshot_dir(article_dir)
    for source in external:
        source_id = str(source.get("id", "unknown"))
        url = str(source.get("url", "")).strip()
        candidate = snapshot_dir / f"{source_id}.raw"
        if not candidate.is_file():
            failures.append(f"{source_id}: 缺少离线快照文件 {candidate.name}")
            continue
        data = candidate.read_bytes()
        content_sha256 = hashlib.sha256(data).hexdigest()
        target_file = target / f"{source_id}.raw"
        target_file.write_bytes(data)
        source["retrieval_status"] = "passed"
        source["content_sha256"] = content_sha256
        source["http_status"] = int(source.get("http_status") or 200)
        source["retrieved_at"] = _now()
        source["verification_mode"] = "offline-import"
        records.append({
            "id": source_id,
            "url": url,
            "url_normalized": _normalize_url(url),
            "status": "passed",
            "http_status": int(source.get("http_status") or 200),
            "content_sha256": content_sha256,
            "snapshot": f"source-snapshots/{source_id}.raw",
            "snapshot_sha256": hashlib.sha256(target_file.read_bytes()).hexdigest(),
            "fetched_at": _now(),
        })
    source_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_receipt(article_dir, "offline-import", records)
    if failures:
        print("SOURCE VERIFY BLOCKED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"SOURCE VERIFY PASSED (offline-import): {len(records)} external sources fingerprinted")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--offline-import", type=Path, help="从目录导入操作员提供的 <source_id>.raw 快照（不联网）")
    args = parser.parse_args()
    article_dir = args.article.expanduser()
    if not article_dir.is_absolute():
        article_dir = ROOT / article_dir
    if args.offline_import:
        return offline_import(article_dir.resolve(), args.offline_import.expanduser().resolve())
    return verify(article_dir.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
