#!/usr/bin/env python3
"""Build and verify a hybrid evidence layer for an article workspace.

The existing ``sources.json`` contract proves that URLs were fetched and
fingerprinted.  This module adds the reader-facing layer the article needs:
trusted-source classification, short verbatim excerpts, screenshots or other
saved evidence, attribution/licence notes, and an automatically generated
reference appendix in ``article.md`` and ``article.html``.

The implementation intentionally uses only the Python standard library.  A
future adapter may import ArchiveBox/Playwright/Trafilatura, but the workflow
must remain auditable when those optional tools are unavailable.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from topic_evidence_isolation import build_topic_binding, validate as validate_topic_evidence
from workflow_security import load_json as strict_load_json


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "hybrid-evidence-v1"
VERSION = "1.2.0"
PLAN_CONTRACT = "hybrid-evidence-plan-v1"
PROVENANCE_CONTRACT = "hybrid-evidence-provenance-v1"
PROVENANCE_VERSION = "1.0.0"
LINEAGE_CONTRACT = "evidence-lineage-v1"
LINEAGE_VERSION = "1.0.0"
LOCAL_KINDS = {"local_artifact", "reproduction", "test-fixture"}
TRUSTED_LEVELS = {
    "official-docs",
    "official-repo",
    "official-api",
    "official-reference",
    "primary-research",
    "peer-reviewed",
    "standard",
    "regulatory",
    "maintainer-source",
}
OFFICIAL_HOST_ALLOWLIST = frozenset({
    "arxiv.org", "www.arxiv.org", "doi.org", "www.doi.org", "openreview.net",
    "acm.org", "dl.acm.org", "ieeexplore.ieee.org", "nature.com", "springer.com",
    "sciencedirect.com", "journals.sagepub.com", "nvidia.com", "developer.nvidia.com",
    "openai.com", "platform.openai.com", "huggingface.co", "github.com",
    "raw.githubusercontent.com", "docs.python.org", "pytorch.org", "tensorflow.org",
    "python.langchain.com", "docs.langchain.com", "docs.trychroma.com", "docs.ragas.io",
    "docs.anthropic.com", "code.claude.com", "docs.n8n.io", "csrc.nist.gov", "nist.gov", "slsa.dev",
    "in-toto.io", "sigstore.dev", "docs.sigstore.dev",
})
PRIMARY_LEVELS = {
    "official-docs",
    "official-repo",
    "official-api",
    "official-reference",
    "primary-research",
    "standard",
    "regulatory",
    "maintainer-source",
}
DEFAULT_POLICY = {
    "minimum_trusted_sources": 3,
    "minimum_primary_sources": 2,
    "minimum_source_domains": 2,
    "minimum_evidence_units_per_source": 1,
    "maximum_excerpt_chars": 420,
    "require_attribution": True,
    "require_reuse_approval_for_embedded_assets": True,
    "require_claim_evidence": True,
    "require_source_verification": True,
    "require_provenance": True,
}
EVIDENCE_KINDS = {"excerpt", "screenshot", "diagram", "code", "snapshot", "pdf"}
MARKDOWN_START = "<!-- HYBRID-EVIDENCE-REFERENCES:START -->"
MARKDOWN_END = "<!-- HYBRID-EVIDENCE-REFERENCES:END -->"
HTML_START = '<section data-hybrid-evidence="v1">'
HTML_END = "</section>"
# The HTML formatter may normalize the generated section (for example by
# moving attributes or wrapping the marker comment in a paragraph).  Keep the
# comments as the stable, reader-facing anchor instead of treating one exact
# opening-tag spelling as the only valid representation.
HTML_MARKER_START = "HYBRID-EVIDENCE-REFERENCES:START"
HTML_MARKER_END = "HYBRID-EVIDENCE-REFERENCES:END"


def _html_has_appendix(text: str) -> bool:
    """Return whether the hybrid-evidence block is present in formatted HTML.

    ``format.py`` is allowed to rewrite harmless tag/attribute details, but it
    must not make a valid appendix look absent.  The generated comments are
    the canonical stable anchors; the exact section tag remains accepted for
    backwards compatibility with pre-format HTML.
    """
    return (
        HTML_START in text
        or (HTML_MARKER_START in text and HTML_MARKER_END in text)
    )


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_text_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return hashlib.sha256(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_datetime(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            value = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_sha256(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "").strip().lower()))


def _json(path: Path) -> Any:
    return strict_load_json(path, default=None)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _source_map(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id", "")).strip(): item
        for item in document.get("sources", [])
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }


def _claims_by_source(document: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for claim in document.get("claims", []):
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("id", "")).strip()
        for source_id in claim.get("source_ids", []) if isinstance(claim.get("source_ids"), list) else []:
            sid = str(source_id).strip()
            if sid and claim_id:
                result.setdefault(sid, []).append(claim_id)
    return result


def _relative_existing(article: Path, raw: str) -> tuple[Path | None, str]:
    raw = str(raw or "").strip().replace("\\", "/")
    if not raw:
        return None, ""
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = article / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(article.resolve())
    except (OSError, ValueError):
        return None, raw
    return resolved, raw


def _relative_file(article: Path, raw: Any) -> tuple[Path | None, str]:
    """Resolve a recorded file path without ever allowing workspace escape."""
    return _relative_existing(article, str(raw or ""))


def _source_verification_map(article: Path) -> dict[str, dict[str, Any]]:
    document = _json(article / "source-verification.json")
    rows = document.get("sources") if isinstance(document, dict) else None
    return {
        str(row.get("id", "")).strip(): row
        for row in rows or []
        if isinstance(row, dict) and str(row.get("id", "")).strip()
    }


def _source_verification_errors(
    article: Path, source: dict[str, Any], verification: dict[str, dict[str, Any]]
) -> list[str]:
    """Cross-check the plan against the physical snapshot receipt.

    A source is not trusted merely because someone typed a 64-character hash
    into ``sources.json``.  The verifier receipt must point at a real snapshot
    whose bytes match both the receipt and the source ledger.
    """
    sid = str(source.get("id", "")).strip() or "<missing-id>"
    record = verification.get(sid)
    if not isinstance(record, dict):
        return [f"来源 {sid} 没有 source-verification.json 回执"]
    errors: list[str] = []
    if record.get("status") != "passed":
        errors.append(f"来源 {sid} 的 source-verification 状态不是 passed")
    source_hash = str(source.get("content_sha256", "")).strip().lower()
    receipt_hash = str(record.get("content_sha256", "")).strip().lower()
    if not _is_sha256(source_hash) or source_hash != receipt_hash:
        errors.append(f"来源 {sid} 的 content_sha256 与 source-verification 不一致")
    snapshot, relative = _relative_file(article, record.get("snapshot", ""))
    if snapshot is None or not snapshot.is_file():
        errors.append(f"来源 {sid} 的验证快照不存在：{record.get('snapshot', '')}")
    else:
        actual = sha256_file(snapshot)
        if not _is_sha256(record.get("snapshot_sha256")) or str(record.get("snapshot_sha256")).lower() != actual:
            errors.append(f"来源 {sid} 的快照哈希与文件不一致：{relative}")
        if receipt_hash and receipt_hash != actual:
            errors.append(f"来源 {sid} 的快照内容与 content_sha256 不一致：{relative}")
    normalized = str(record.get("url_normalized", "")).strip()
    expected_normalized = urllib.parse.urlsplit(str(source.get("url", "")).strip())
    expected_normalized = urllib.parse.urlunsplit((
        expected_normalized.scheme.lower(),
        expected_normalized.netloc.lower(),
        expected_normalized.path or "/",
        "",
        "",
    )).rstrip("/")
    if not normalized or normalized != expected_normalized:
        errors.append(f"来源 {sid} 的 url_normalized 与 sources.json 不一致")
    if _parse_datetime(source.get("retrieved_at")) is None:
        errors.append(f"来源 {sid} 缺少有效 retrieved_at")
    return errors


def _evidence_pack_payload(article: Path, plan: dict[str, Any]) -> dict[str, Any]:
    """Return the content-addressed inputs for the evidence run.

    This is deliberately a small, local attestation rather than an identity
    signature.  It makes a run replayable and detects stale/stitched receipts;
    it does not claim that the operator is a human or that a source is true.
    """
    paths: set[str] = {"sources.json", "source-verification.json", "evidence-plan.json", "topic-contract.yaml"}
    for row in plan.get("sources", []) if isinstance(plan.get("sources"), list) else []:
        if not isinstance(row, dict):
            continue
        for unit in row.get("evidence", []) if isinstance(row.get("evidence"), list) else []:
            if isinstance(unit, dict) and str(unit.get("path", "")).strip():
                paths.add(str(unit["path"]).replace("\\", "/"))
    verification = _json(article / "source-verification.json")
    for row in verification.get("sources", []) if isinstance(verification, dict) else []:
        if isinstance(row, dict) and str(row.get("snapshot", "")).strip():
            paths.add(str(row["snapshot"]).replace("\\", "/"))
    # Local reproductions are materials too.  If they are only named in
    # sources.json, omitting them would let the provenance receipt survive a
    # changed fixture.  Bind them exactly like downloaded snapshots.
    sources_doc = _json(article / "sources.json")
    for row in sources_doc.get("sources", []) if isinstance(sources_doc, dict) else []:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind", "external")).strip().lower()
        if kind in LOCAL_KINDS and str(row.get("path", "")).strip():
            paths.add(str(row["path"]).replace("\\", "/"))
    # After the evidence appendix is appended, bind the final reader-facing
    # documents as products of this run.  Before append they are deliberately
    # absent, so a pre-append audit does not create a self-invalidating receipt.
    article_md = article / "article.md"
    article_html = article / "article.html"
    if article_md.is_file() and MARKDOWN_START in article_md.read_text(encoding="utf-8", errors="replace"):
        paths.add("article.md")
    if article_html.is_file() and _html_has_appendix(article_html.read_text(encoding="utf-8", errors="replace")):
        paths.add("article.html")
    files: list[dict[str, Any]] = []
    for relative in sorted(paths):
        path, normalized = _relative_file(article, relative)
        if path is not None and path.is_file():
            files.append({"path": normalized, "sha256": sha256_file(path), "size": path.stat().st_size})
    payload = {
        "contract": PROVENANCE_CONTRACT,
        "inputs": files,
        "topic_fingerprint": (plan.get("topic_binding") or {}).get("topic_fingerprint", ""),
        "source_ids": sorted(str(row.get("source_id", "")).strip() for row in plan.get("sources", []) if isinstance(row, dict) and str(row.get("source_id", "")).strip()),
        "claim_ids": sorted({str(claim_id).strip() for row in plan.get("sources", []) if isinstance(row, dict) for claim_id in row.get("claim_ids", []) if str(claim_id).strip()}),
    }
    return payload


def _evidence_pack_sha256(article: Path, plan: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(_evidence_pack_payload(article, plan)).encode("utf-8")).hexdigest()


def _write_provenance(article: Path, plan: dict[str, Any]) -> dict[str, Any]:
    payload = _evidence_pack_payload(article, plan)
    pack_sha = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    provenance = {
        "schema_version": 1,
        "contract": PROVENANCE_CONTRACT,
        "verifier": "source_evidence.py",
        "verifier_version": PROVENANCE_VERSION,
        "status": "passed",
        "run_id": pack_sha[:32],
        "generated_at": now(),
        "pack_sha256": pack_sha,
        "topic_fingerprint": payload.get("topic_fingerprint", ""),
        "source_ids": payload.get("source_ids", []),
        "claim_ids": payload.get("claim_ids", []),
        "inputs": payload.get("inputs", []),
        "attestation": "unsigned-local-integrity",
        "identity_authenticated": False,
        "operator_note": "证明本地证据输入与本次审计回执可重放；不证明来源真伪、真人身份或不可抵赖性。",
    }
    _write_json(article / "evidence-provenance.json", provenance)
    return provenance


def _provenance_errors(article: Path, plan: dict[str, Any]) -> list[str]:
    path = article / "evidence-provenance.json"
    provenance = _json(path)
    if not isinstance(provenance, dict):
        return ["缺少 evidence-provenance.json；请先运行 source_evidence.py audit"]
    errors: list[str] = []
    if provenance.get("contract") != PROVENANCE_CONTRACT:
        errors.append(f"evidence-provenance.json contract 必须是 {PROVENANCE_CONTRACT}")
    if provenance.get("status") != "passed":
        errors.append("evidence-provenance.json 的 status 必须是 passed")
    expected = _evidence_pack_sha256(article, plan)
    if str(provenance.get("pack_sha256", "")).strip().lower() != expected:
        errors.append("evidence-provenance.json 的 pack_sha256 与当前证据输入不一致")
    current_topic = (plan.get("topic_binding") or {}).get("topic_fingerprint", "")
    if str(provenance.get("topic_fingerprint", "")).strip() != str(current_topic).strip():
        errors.append("evidence-provenance.json 的 topic_fingerprint 与 evidence-plan 不一致")
    if provenance.get("identity_authenticated") is not False:
        errors.append("evidence-provenance.json 必须明确 identity_authenticated: false")
    return errors


def _appendix_integrity_errors(article: Path) -> list[str]:
    """Verify that the generated appendix still belongs to this receipt.

    Marker-only checks are vulnerable to a hand-written or stale references
    block.  ``append`` records the complete article digests; every subsequent
    ``audit --require-appendix`` must re-check those digests.
    """
    errors: list[str] = []
    receipt = _json(article / "source-evidence.json")
    appendix = receipt.get("appendix") if isinstance(receipt, dict) else None
    if not isinstance(appendix, dict):
        return ["source-evidence.json 缺少 appendix 完整性回执；请重新运行 source_evidence.py append"]
    for name, filename in (("article_markdown_sha256", "article.md"), ("article_html_sha256", "article.html")):
        path = article / filename
        declared = str(appendix.get(name, "")).strip().lower()
        if not path.is_file():
            errors.append(f"篇尾回执要求的文件不存在：{filename}")
            continue
        if not _is_sha256(declared):
            errors.append(f"篇尾回执缺少有效 {name}")
        elif declared != sha256_file(path):
            errors.append(f"篇尾引用资料已漂移：{filename} 的 SHA-256 与 appendix 回执不一致")
    md = (article / "article.md").read_text(encoding="utf-8", errors="replace") if (article / "article.md").is_file() else ""
    html_text = (article / "article.html").read_text(encoding="utf-8", errors="replace") if (article / "article.html").is_file() else ""
    if MARKDOWN_START not in md or MARKDOWN_END not in md:
        errors.append("article.md 缺少自动生成的混合证据参考资料区块")
    if not _html_has_appendix(html_text):
        errors.append("article.html 缺少混合证据参考资料区块")
    return errors


def _write_lineage(article: Path, provenance: dict[str, Any], status: str = "passed") -> dict[str, Any]:
    """Write a small offline lineage receipt inspired by OpenLineage/in-toto.

    This is intentionally unsigned.  It records the run/job and immutable
    input digests without pretending to authenticate an operator or a source.
    """
    inputs = [
        {"namespace": "article", "name": item.get("path", ""), "digest": {"sha256": item.get("sha256", "")}, "role": "material"}
        for item in provenance.get("inputs", [])
        if isinstance(item, dict)
    ]
    outputs = []
    for filename in ("evidence-provenance.json", "topic-evidence-isolation.json"):
        path = article / filename
        if path.is_file():
            outputs.append({"namespace": "article", "name": filename, "digest": {"sha256": sha256_file(path)}, "role": "product"})
    lineage = {
        "schema_version": 1,
        "contract": LINEAGE_CONTRACT,
        "verifier_version": LINEAGE_VERSION,
        "status": status,
        "run": {"run_id": provenance.get("run_id", ""), "started_at": provenance.get("generated_at", ""), "finished_at": now()},
        "job": {"namespace": "gzh-thinktank", "name": "hybrid-evidence-audit", "tool": "scripts/source_evidence.py"},
        "topic_fingerprint": provenance.get("topic_fingerprint", ""),
        "inputs": inputs,
        "outputs": outputs,
        "attestation": "unsigned-local-lineage",
        "identity_authenticated": False,
        "operator_note": "仅记录本地 run/job/material/product 血缘；不证明真人身份、来源真伪或不可抵赖性。",
    }
    _write_json(article / "evidence-lineage.json", lineage)
    return lineage


def classify_source(source: dict[str, Any]) -> tuple[str, bool, str]:
    level = str(source.get("evidence_level", "")).strip().lower()
    parsed = urllib.parse.urlsplit(str(source.get("url", "")).strip())
    host = parsed.hostname.lower().rstrip(".") if parsed.hostname else ""
    declared_host = str(source.get("official_domain") or "").strip().lower().rstrip(".")
    if host and declared_host and declared_host != host:
        return "untrusted", False, f"official_domain={declared_host} does not match url host={host}"
    if level not in TRUSTED_LEVELS:
        return "untrusted", False, "evidence_level is not an allowed trusted level"
    if not host or host not in OFFICIAL_HOST_ALLOWLIST:
        return "untrusted", False, f"url host {host or '<missing>'} is not in the official allowlist"
    if level in PRIMARY_LEVELS:
        return "primary", True, f"evidence_level={level}; official_host={host}"
    return "secondary", True, f"evidence_level={level}; official_host={host}"


def _default_plan(article: Path) -> dict[str, Any]:
    sources_doc = _json(article / "sources.json") or {}
    claims = _claims_by_source(sources_doc)
    rows = []
    for source in sources_doc.get("sources", []) if isinstance(sources_doc.get("sources"), list) else []:
        if not isinstance(source, dict):
            continue
        sid = str(source.get("id", "")).strip()
        if not sid:
            continue
        tier, trusted, reason = classify_source(source)
        rows.append({
            "source_id": sid,
            "tier": tier,
            "trusted": trusted,
            "trust_reason": reason,
            "used_in_article": bool(claims.get(sid)),
            "claim_ids": sorted(set(claims.get(sid, []))),
            "evidence": [],
            "reuse_approved": False,
            "reuse_reason": "",
        })
    return {
        "schema_version": 2,
        "contract": PLAN_CONTRACT,
        "status": "draft",
        "topic_binding": build_topic_binding(article),
        "policy": dict(DEFAULT_POLICY),
        "sources": rows,
        "operator_notes": "每个 evidence 单元必须声明 claim_ids；正文只保留短摘录并标注来源。审计会生成 evidence-provenance.json 供回放。",
    }


def init_plan(article: Path) -> int:
    path = article / "evidence-plan.json"
    if path.exists():
        print(f"EVIDENCE PLAN EXISTS: {path}")
        return 0
    _write_json(path, _default_plan(article))
    print(f"EVIDENCE PLAN INITIALIZED: {path}")
    return 0


def _find_browser(explicit: str | None = None) -> Path | None:
    candidates = [explicit] if explicit else []
    candidates.extend([
        os.environ.get("CHROME_BIN", ""),
        "chrome",
        "msedge",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ])
    for raw in candidates:
        if not raw:
            continue
        found = shutil.which(raw) or raw
        path = Path(found)
        if path.is_file():
            return path.resolve()
    return None


def _update_plan_evidence(article: Path, source_id: str, record: dict[str, Any]) -> None:
    path = article / "evidence-plan.json"
    plan = _json(path) or _default_plan(article)
    for row in plan.get("sources", []):
        if isinstance(row, dict) and str(row.get("source_id", "")).strip() == source_id:
            evidence = row.setdefault("evidence", [])
            evidence = [item for item in evidence if not (isinstance(item, dict) and item.get("path") == record.get("path"))]
            evidence.append(record)
            row["evidence"] = evidence
            row["reuse_approved"] = bool(record.get("reuse_approved", row.get("reuse_approved", False)))
            if record.get("reuse_reason"):
                row["reuse_reason"] = record["reuse_reason"]
            break
    plan["status"] = "draft"
    _write_json(path, plan)


def capture(article: Path, source_id: str, browser: str | None = None, width: int = 1280, height: int = 900) -> int:
    sources_doc = _json(article / "sources.json") or {}
    source = _source_map(sources_doc).get(source_id)
    if not source:
        print(f"EVIDENCE CAPTURE BLOCKED: unknown source_id={source_id}")
        return 1
    url = str(source.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        print(f"EVIDENCE CAPTURE BLOCKED: source {source_id} has no HTTP(S) URL")
        return 1
    executable = _find_browser(browser)
    if executable is None:
        print("EVIDENCE CAPTURE BLOCKED: Chrome/Edge not found; use --offline-import or save a screenshot manually")
        return 1
    output = article / "evidence" / "screenshots" / f"{source_id}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    profile = article / "evidence" / ".chrome-profile"
    command = [
        str(executable), "--headless=new", "--disable-gpu", "--no-sandbox",
        f"--user-data-dir={profile}", "--hide-scrollbars",
        f"--window-size={width},{height}", "--virtual-time-budget=5000",
        f"--screenshot={output}", url,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"EVIDENCE CAPTURE BLOCKED: {exc}")
        return 1
    if result.returncode != 0 or not output.is_file() or output.stat().st_size < 1024:
        detail = (result.stderr or result.stdout or "browser did not produce a screenshot").strip()[-500:]
        print(f"EVIDENCE CAPTURE BLOCKED: {detail}")
        return 1
    try:
        profile.resolve().relative_to((article / "evidence").resolve())
        shutil.rmtree(profile, ignore_errors=True)
    except (OSError, ValueError):
        pass
    record = {
        "id": f"ev-{source_id}-screenshot",
        "kind": "screenshot",
        "path": f"evidence/screenshots/{source_id}.png",
        "claim_ids": sorted(_claims_by_source(sources_doc).get(source_id, [])),
        "source_locator": f"{url}#viewport={width}x{height}",
        "captured_at": now(),
        "sha256": sha256_file(output),
        "license_status": "official-site-terms; attribution required",
        "reuse_approved": False,
        "reuse_reason": "发布前由真人核对站点条款；当前截图先作为证据存档",
    }
    _update_plan_evidence(article, source_id, record)
    print(f"EVIDENCE CAPTURED: {output}")
    return 0


def _validate_plan(
    article: Path,
    require_appendix: bool = False,
    require_provenance: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    sources_doc = _json(article / "sources.json")
    plan = _json(article / "evidence-plan.json")
    if not isinstance(sources_doc, dict):
        return ["sources.json 缺失或无法解析"], {}
    if not isinstance(plan, dict):
        return ["缺少 evidence-plan.json；请先运行 source_evidence.py init"], {}
    if plan.get("contract") != PLAN_CONTRACT:
        errors.append(f"evidence-plan.json contract 必须是 {PLAN_CONTRACT}")
    source_map = _source_map(sources_doc)
    plan_rows = plan.get("sources")
    if not isinstance(plan_rows, list) or not plan_rows:
        errors.append("evidence-plan.json 必须包含 sources 列表")
        plan_rows = []
    policy = dict(DEFAULT_POLICY)
    if isinstance(plan.get("policy"), dict):
        policy.update(plan["policy"])
    try:
        plan_schema = int(plan.get("schema_version", 1))
    except (TypeError, ValueError):
        plan_schema = 0
    if plan_schema < 2:
        errors.append("evidence-plan.json schema_version 必须至少为 2；旧计划需重新初始化")
    plan_source_ids = {
        str(row.get("source_id", "")).strip()
        for row in plan_rows
        if isinstance(row, dict) and str(row.get("source_id", "")).strip()
    }
    source_ids = set(source_map)
    if plan_source_ids != source_ids:
        missing = sorted(source_ids - plan_source_ids)
        unknown = sorted(plan_source_ids - source_ids)
        if missing:
            errors.append(f"evidence-plan.json 漏记 sources.json 来源：{', '.join(missing)}")
        if unknown:
            errors.append(f"evidence-plan.json 含不存在来源：{', '.join(unknown)}")
    verification = _source_verification_map(article)
    claims_doc = sources_doc.get("claims")
    claims = [claim for claim in claims_doc if isinstance(claim, dict)] if isinstance(claims_doc, list) else []
    if not claims:
        errors.append("sources.json 必须包含 claims；混合证据层需要逐主张回链")
    # Fail at the research/evidence gate, not only later at content review:
    # a source id without a concrete ref is not reproducible provenance.
    for claim in claims:
        claim_id = str(claim.get("id") or "<missing-id>").strip()
        locator = claim.get("evidence_locator")
        locators = locator if isinstance(locator, list) else [locator]
        if not locators or any(not isinstance(item, dict) for item in locators):
            errors.append(f"主张 {claim_id} 的 evidence_locator 必须是对象或对象列表")
            continue
        for item in locators:
            if not str(item.get("source_id") or "").strip() or not str(item.get("kind") or "").strip() or not str(item.get("ref") or "").strip():
                errors.append(f"主张 {claim_id} 的 evidence_locator 必须包含 source_id、kind、ref")
    claim_map = {
        str(claim.get("id", "")).strip(): claim
        for claim in claims
        if str(claim.get("id", "")).strip()
    }
    claims_by_source = _claims_by_source(sources_doc)
    evidence_by_claim: dict[str, list[str]] = {}
    seen_evidence_ids: set[str] = set()
    seen_evidence_paths: set[str] = set()
    trusted: list[str] = []
    primary: list[str] = []
    domains: set[str] = set()
    trusted_used: list[str] = []
    primary_used: list[str] = []
    domains_used: set[str] = set()
    used_rows: list[dict[str, Any]] = []
    receipt_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(plan_rows, 1):
        if not isinstance(row, dict):
            errors.append(f"evidence-plan.json 第 {index} 项不是对象")
            continue
        sid = str(row.get("source_id", "")).strip()
        if not sid or sid in seen:
            errors.append(f"evidence-plan.json 第 {index} 项 source_id 缺失或重复")
            continue
        seen.add(sid)
        source = source_map.get(sid)
        if source is None:
            errors.append(f"evidence-plan.json 引用了不存在的来源：{sid}")
            continue
        kind_of_source = str(source.get("kind", "external")).strip().lower()
        if kind_of_source not in LOCAL_KINDS and policy.get("require_source_verification", True):
            errors.extend(_source_verification_errors(article, source, verification))
            retrieved = _parse_datetime(source.get("retrieved_at"))
            try:
                freshness_days = int(source.get("freshness_days"))
            except (TypeError, ValueError):
                freshness_days = 0
            if retrieved is not None and freshness_days > 0:
                age_days = max(0.0, (datetime.now(timezone.utc) - retrieved).total_seconds() / 86400.0)
                if age_days > freshness_days:
                    errors.append(f"来源 {sid} 已超过 freshness_days={freshness_days}，请重新抓取")
        tier, trusted_by_source, reason = classify_source(source)
        if bool(row.get("trusted")) and not trusted_by_source:
            errors.append(f"来源 {sid} 自报 trusted，但不满足可信等级：{source.get('evidence_level', '')}")
        if trusted_by_source:
            trusted.append(sid)
            if tier == "primary":
                primary.append(sid)
            host = urllib.parse.urlsplit(str(source.get("url", ""))).netloc.lower()
            if host:
                domains.add(host)
        used = bool(row.get("used_in_article"))
        if used and trusted_by_source:
            trusted_used.append(sid)
            if tier == "primary":
                primary_used.append(sid)
            host = urllib.parse.urlsplit(str(source.get("url", ""))).netloc.lower()
            if host:
                domains_used.add(host)
        if used:
            used_rows.append(row)
            row_claim_ids = {str(value).strip() for value in row.get("claim_ids", []) if str(value).strip()} if isinstance(row.get("claim_ids"), list) else set()
            expected_claim_ids = set(claims_by_source.get(sid, []))
            if not row_claim_ids:
                errors.append(f"正文来源 {sid} 缺少 claim_ids；来源级证据不能替代主张级回链")
            if not row_claim_ids.issubset(set(claim_map)):
                errors.append(f"来源 {sid} 的 claim_ids 引用了不存在的 claim")
            if expected_claim_ids and not expected_claim_ids.issubset(row_claim_ids):
                errors.append(f"来源 {sid} 的 claim_ids 未覆盖 sources.json 中该来源支持的全部 claim")
        evidence = row.get("evidence")
        if not isinstance(evidence, list):
            evidence = []
        valid_units: list[dict[str, Any]] = []
        for unit_index, unit in enumerate(evidence, 1):
            if not isinstance(unit, dict):
                errors.append(f"来源 {sid} 的 evidence 第 {unit_index} 项不是对象")
                continue
            kind = str(unit.get("kind", "")).strip().lower()
            unit_ok = True
            unit_id = str(unit.get("id", "")).strip()
            if not unit_id:
                errors.append(f"来源 {sid} 的 evidence 第 {unit_index} 项缺少稳定 id")
                unit_ok = False
            elif unit_id in seen_evidence_ids:
                errors.append(f"证据单元 id 重复：{unit_id}")
                unit_ok = False
            else:
                seen_evidence_ids.add(unit_id)
            if kind not in EVIDENCE_KINDS:
                errors.append(f"来源 {sid} 的 evidence kind 无效：{kind}")
                unit_ok = False
            unit_claim_ids = {str(value).strip() for value in unit.get("claim_ids", []) if str(value).strip()} if isinstance(unit.get("claim_ids"), list) else set()
            if policy.get("require_claim_evidence", True) and not unit_claim_ids:
                errors.append(f"来源 {sid} 的证据单元 {unit_id or unit_index} 缺少 claim_ids")
                unit_ok = False
            source_claim_ids = set(claims_by_source.get(sid, []))
            if unit_claim_ids and not unit_claim_ids.issubset(source_claim_ids):
                errors.append(f"来源 {sid} 的证据单元 {unit_id or unit_index} claim_ids 超出该来源支持范围")
                unit_ok = False
            path, relative = _relative_existing(article, unit.get("path", ""))
            if path is None or not path.is_file():
                errors.append(f"来源 {sid} 的证据文件不存在：{unit.get('path', '')}")
                unit_ok = False
                continue
            if relative in seen_evidence_paths:
                errors.append(f"证据文件被多个 evidence 单元复用且无法区分语义：{relative}")
                unit_ok = False
            else:
                seen_evidence_paths.add(relative)
            declared = str(unit.get("sha256", "")).strip().lower()
            actual = sha256_file(path)
            if declared != actual:
                errors.append(f"来源 {sid} 的证据哈希不匹配：{relative}")
                unit_ok = False
            if not str(unit.get("source_locator", "")).strip():
                errors.append(f"来源 {sid} 的证据缺少 source_locator：{relative}")
                unit_ok = False
            if _parse_datetime(unit.get("captured_at")) is None:
                errors.append(f"来源 {sid} 的证据缺少有效 captured_at：{relative}")
                unit_ok = False
            if policy.get("require_attribution") and not str(unit.get("license_status", "")).strip():
                errors.append(f"来源 {sid} 的证据缺少 license_status：{relative}")
                unit_ok = False
            if kind == "excerpt":
                try:
                    text = path.read_text(encoding="utf-8").strip()
                except UnicodeDecodeError:
                    errors.append(f"来源 {sid} 的 excerpt 不是 UTF-8 文本：{relative}")
                    text = ""
                if len(text) > int(policy.get("maximum_excerpt_chars", 420)):
                    errors.append(f"来源 {sid} 的摘录超过 maximum_excerpt_chars：{relative}")
                if not text:
                    errors.append(f"来源 {sid} 的 excerpt 为空：{relative}")
                    unit_ok = False
            if unit_ok:
                normalized_unit = {**unit, "path": relative, "sha256": actual, "claim_ids": sorted(unit_claim_ids)}
                valid_units.append(normalized_unit)
                # Evidence from a source that is not actually used in the
                # article must not satisfy reader-facing claim coverage.
                # Otherwise a hidden/background row can manufacture a clean
                # receipt while the published source set omits the evidence.
                if used:
                    for claim_id in unit_claim_ids:
                        evidence_by_claim.setdefault(claim_id, []).append(unit_id)
        if used and len(valid_units) < int(policy.get("minimum_evidence_units_per_source", 1)):
            errors.append(f"已用于正文的可信来源 {sid} 没有足够证据单元")
        if used and policy.get("require_reuse_approval_for_embedded_assets"):
            embedded = [item for item in valid_units if item.get("kind") in {"screenshot", "diagram", "code", "pdf"}]
            if embedded and row.get("reuse_approved") is not True:
                errors.append(f"来源 {sid} 的嵌入式证据尚未 reuse_approved=true；请真人核对授权后再发布")
        receipt_rows.append({
            "source_id": sid,
            "title": str(source.get("title", "")).strip(),
            "url": str(source.get("url", "")).strip(),
            "retrieved_at": source.get("retrieved_at"),
            "evidence_level": source.get("evidence_level"),
            "tier": tier,
            "trusted": trusted_by_source,
            "trust_reason": reason,
            "used_in_article": used,
            "claim_ids": sorted({str(x).strip() for x in row.get("claim_ids", []) if str(x).strip()}),
            "evidence": valid_units,
            "reuse_approved": row.get("reuse_approved") is True,
            "reuse_reason": str(row.get("reuse_reason", "")).strip(),
        })
    min_trusted = int(policy.get("minimum_trusted_sources", 3))
    min_primary = int(policy.get("minimum_primary_sources", 2))
    min_domains = int(policy.get("minimum_source_domains", 2))
    if len(trusted_used) < min_trusted:
        errors.append(f"正文实际采用的可信信源数量 {len(trusted_used)} 少于最低要求 {min_trusted}")
    if len(primary_used) < min_primary:
        errors.append(f"正文实际采用的一级/一手信源数量 {len(primary_used)} 少于最低要求 {min_primary}")
    if len(domains_used) < min_domains:
        errors.append(f"正文实际采用的信源域名多样性 {len(domains_used)} 少于最低要求 {min_domains}")
    if not used_rows:
        errors.append("evidence-plan.json 没有标记 used_in_article=true 的来源")
    if policy.get("require_claim_evidence", True):
        for claim_id in sorted(claim_map):
            if not evidence_by_claim.get(claim_id):
                errors.append(f"claim {claim_id} 没有任何有效 evidence 单元；不能只证明来源存在")
    if require_appendix:
        errors.extend(_appendix_integrity_errors(article))
    data = {
        "schema_version": 2,
        "contract": CONTRACT,
        "verifier": "source_evidence.py",
        "verifier_version": VERSION,
        "status": "passed" if not errors else "blocked",
        "audited_at": now(),
        "policy": policy,
        "source_count": len(source_map),
        "trusted_source_count": len(trusted),
        "primary_source_count": len(primary),
        "source_domain_count": len(domains),
        "trusted_source_ids": sorted(trusted),
        "primary_source_ids": sorted(primary),
        "source_domains": sorted(domains),
        "used_trusted_source_ids": sorted(trusted_used),
        "used_primary_source_ids": sorted(primary_used),
        "used_source_domains": sorted(domains_used),
        "used_trusted_source_count": len(trusted_used),
        "used_primary_source_count": len(primary_used),
        "used_source_domain_count": len(domains_used),
        "sources": receipt_rows,
        "claim_evidence_coverage": {
            claim_id: sorted(set(unit_ids)) for claim_id, unit_ids in sorted(evidence_by_claim.items())
        },
        "evidence_pack_sha256": _evidence_pack_sha256(article, plan),
        "errors": errors,
    }
    if require_provenance:
        errors.extend(_provenance_errors(article, plan))
        data["errors"] = errors
        data["status"] = "passed" if not errors else "blocked"
    return errors, data


def audit(article: Path, require_appendix: bool = False) -> int:
    # First validate the human-edited plan and physical evidence.  Only after
    # those inputs are clean do we mint a local, content-addressed provenance
    # receipt; this avoids a generated receipt certifying its own bad inputs.
    previous_receipt = _json(article / "source-evidence.json")
    previous_appendix = previous_receipt.get("appendix") if isinstance(previous_receipt, dict) else None
    errors, data = _validate_plan(article, require_appendix=require_appendix, require_provenance=False)
    isolation_errors, isolation_receipt = validate_topic_evidence(article)
    errors.extend(f"topic-evidence-isolation: {error}" for error in isolation_errors)
    data["topic_evidence_isolation"] = {
        "status": isolation_receipt.get("status", "blocked"),
        "receipt": "topic-evidence-isolation.json",
        "matched_source_ids": isolation_receipt.get("matched_source_ids", []),
    }
    data["status"] = "passed" if not errors else "blocked"
    if not errors:
        plan = _json(article / "evidence-plan.json") or {}
        provenance = _write_provenance(article, plan)
        lineage = _write_lineage(article, provenance)
        errors, data = _validate_plan(
            article,
            require_appendix=require_appendix,
            require_provenance=True,
        )
        isolation_errors, isolation_receipt = validate_topic_evidence(article)
        errors.extend(f"topic-evidence-isolation: {error}" for error in isolation_errors)
        data["topic_evidence_isolation"] = {
            "status": isolation_receipt.get("status", "blocked"),
            "receipt": "topic-evidence-isolation.json",
            "matched_source_ids": isolation_receipt.get("matched_source_ids", []),
        }
        data["status"] = "passed" if not errors else "blocked"
        data["errors"] = errors
        data["lineage"] = {"receipt": "evidence-lineage.json", "run_id": lineage.get("run", {}).get("run_id", "")}
    data["errors"] = errors
    # ``audit`` must not erase the append receipt that ``append`` generated;
    # otherwise a second audit silently downgrades the appendix to marker-only
    # validation.  Stale hashes are still rejected on the next require-appendix
    # validation, but the evidence of the last append remains visible.
    if isinstance(previous_appendix, dict):
        data["appendix"] = previous_appendix
    _write_json(article / "source-evidence.json", data)
    _write_json(article / "topic-evidence-isolation.json", isolation_receipt)
    if errors:
        print("HYBRID EVIDENCE BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "HYBRID EVIDENCE PASSED: "
        f"{data['trusted_source_count']} trusted sources / "
        f"{data['source_count']} declared sources / "
        f"{data['source_domain_count']} domains"
    )
    return 0


def _replace_block(text: str, start: str, end: str, block: str) -> str:
    if start == HTML_START:
        # The HTML formatter can wrap our comment markers in a paragraph.
        # Remove only that formatter wrapper before replacing the block so we
        # do not create <p><section>...</section></p> around the appendix.
        text = re.sub(r"<p\b[^>]*>\s*(?=<!--\s*HYBRID-EVIDENCE-REFERENCES:START\s*-->)", "", text, count=1, flags=re.I)
        text = re.sub(r"(<!--\s*HYBRID-EVIDENCE-REFERENCES:END\s*-->)\s*</p>", r"\1", text, count=1, flags=re.I)
    pattern = re.compile(re.escape(start) + r"[\s\S]*?" + re.escape(end), flags=re.M)
    if start == HTML_START and not pattern.search(text):
        pattern = re.compile(r"<!--\s*HYBRID-EVIDENCE-REFERENCES:START\s*-->[\s\S]*?<!--\s*HYBRID-EVIDENCE-REFERENCES:END\s*-->", flags=re.I | re.M)
    if pattern.search(text):
        return pattern.sub(block, text, count=1)
    return text.rstrip() + "\n\n" + block + "\n"


def _write_text_if_changed(path: Path, text: str) -> bool:
    """Write a generated artifact only when its bytes actually changed.

    Evidence append is intentionally idempotent.  Re-running it after a
    successful format must not touch ``article.md``/``article.html`` merely
    because the receipt was refreshed: the format gate uses both content
    digests and the markdown/HTML modification-time ordering.  Avoiding a
    no-op write keeps those contracts stable and makes retries safe.
    """
    try:
        current = path.read_text(encoding="utf-8") if path.is_file() else None
    except OSError:
        current = None
    if current == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def _reference_markdown(receipt: dict[str, Any]) -> str:
    lines = [
        MARKDOWN_START,
        "## 参考资料",
        "",
    ]
    number = 1
    for source in receipt.get("sources", []):
        if not isinstance(source, dict) or not source.get("trusted"):
            continue
        lines.append(f"{number}. [{source.get('title', source.get('source_id', '来源'))}]({source.get('url', '')})")
        number += 1
    lines.extend(["", MARKDOWN_END])
    return "\n".join(lines)


def _reference_html(receipt: dict[str, Any]) -> str:
    esc = html.escape
    leaf = lambda value: f'<span leaf="">{esc(str(value))}</span>'
    parts = [
        HTML_START,
        f'<h2 style="font-size:19px;line-height:1.5;color:#17324D;border-bottom:2px solid #D7B09E;padding-bottom:7px;">{leaf("参考资料")}</h2>',
        '<ol style="padding-left:20px;">',
    ]
    for source in receipt.get("sources", []):
        if not isinstance(source, dict) or not source.get("trusted"):
            continue
        parts.append(f'<li style="margin:8px 0;line-height:1.7;"><a href="{esc(str(source.get("url", "")))}">{leaf(str(source.get("title", source.get("source_id", "来源"))))}</a></li>')
    parts.extend(['</ol>', HTML_END])
    return "".join(parts)


def _sync_image_sources(article: Path, receipt: dict[str, Any]) -> None:
    """Register embedded evidence screenshots in the normal image ledger.

    The visual gate treats every local ``<img>`` as an auditable asset.  A
    screenshot is not generated artwork, but it still needs origin/source/
    license/hash metadata so it cannot bypass the same publication checks.
    """
    path = article / "image-sources.json"
    if not path.is_file():
        return
    document = _json(path)
    if not isinstance(document, dict) or not isinstance(document.get("assets"), list):
        return
    known = {
        str(item.get("path", "")).replace("\\", "/")
        for item in document["assets"]
        if isinstance(item, dict)
    }
    changed = False
    for source in receipt.get("sources", []):
        if not isinstance(source, dict):
            continue
        for unit in source.get("evidence", []):
            if not isinstance(unit, dict) or unit.get("kind") not in {"screenshot", "diagram", "code", "pdf"}:
                continue
            raw = str(unit.get("path", "")).replace("\\", "/")
            if not raw:
                continue
            if raw in known:
                for existing in document["assets"]:
                    if not isinstance(existing, dict) or str(existing.get("path", "")).replace("\\", "/") != raw:
                        continue
                    if existing.get("origin") in {"evidence-capture", "reused"}:
                        existing["origin"] = "reused"
                        existing.update({
                            "source_ref": str(source.get("url", "")),
                            "reuse_reason": str(source.get("reuse_reason", "")) or str(unit.get("reuse_reason", "")),
                            "reuse_approved": bool(source.get("reuse_approved")),
                            "license": str(unit.get("license_status", "")),
                            "sha256": str(unit.get("sha256", "")),
                        })
                        changed = True
                    break
                continue
            document["assets"].append({
                "path": raw,
                "origin": "reused",
                "source": str(source.get("url", "")),
                "license": str(unit.get("license_status", "")),
                "reuse_approved": bool(source.get("reuse_approved")),
                "source_ref": str(source.get("url", "")),
                "reuse_reason": str(source.get("reuse_reason", "")) or str(unit.get("reuse_reason", "")),
                "sha256": str(unit.get("sha256", "")),
                "generation": {
                    "provider": "source-evidence",
                    "model": "browser-capture",
                    "method": "headless-browser-screenshot",
                    "visual_owner": "evidence",
                    "viewer_job": "保留可信信源的真实页面证据",
                    "claim_ids": source.get("claim_ids", []),
                    "fallback": "offline-import",
                    "execution_mode": "reused",
                    "requested_backend": "source-evidence-capture",
                    "execution_backend": "source-evidence-capture",
                    "status": "reused",
                },
            })
            known.add(raw)
            changed = True
    if changed:
        _write_json(path, document)


def append(article: Path) -> int:
    previous_receipt = _json(article / "source-evidence.json")
    errors, receipt = _validate_plan(article, require_appendix=False, require_provenance=True)
    isolation_errors, isolation_receipt = validate_topic_evidence(article)
    errors.extend(f"topic-evidence-isolation: {error}" for error in isolation_errors)
    _write_json(article / "topic-evidence-isolation.json", isolation_receipt)
    receipt["topic_evidence_isolation"] = {
        "status": isolation_receipt.get("status", "blocked"),
        "receipt": "topic-evidence-isolation.json",
        "matched_source_ids": isolation_receipt.get("matched_source_ids", []),
    }
    receipt["status"] = "passed" if not errors else "blocked"
    receipt["errors"] = errors
    if isinstance(previous_receipt, dict) and isinstance(previous_receipt.get("lineage"), dict):
        receipt["lineage"] = previous_receipt["lineage"]
    if errors:
        _write_json(article / "source-evidence.json", receipt)
        print("HYBRID EVIDENCE APPEND BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    receipt["_article_dir"] = str(article)
    md_block = _reference_markdown(receipt)
    html_block = _reference_html(receipt)
    md_path = article / "article.md"
    html_path = article / "article.html"
    if not md_path.is_file() or not html_path.is_file():
        print("HYBRID EVIDENCE APPEND BLOCKED: article.md/article.html 必须先存在")
        return 1
    md_candidate = _replace_block(md_path.read_text(encoding="utf-8"), MARKDOWN_START, MARKDOWN_END, md_block)
    _write_text_if_changed(md_path, md_candidate)
    current_html = html_path.read_text(encoding="utf-8")
    # A formatted article already contains the appendix as marker comments,
    # but the formatter is free to normalize the surrounding tags.  Preserve
    # that canonical formatted HTML; rewriting it with the raw generator block
    # would create a post-format byte drift and invalidate format-report.json.
    # Only replace an exact generator-owned section (or add one when absent).
    if HTML_START in current_html or not _html_has_appendix(current_html):
        html_candidate = _replace_block(current_html, HTML_START, HTML_END, html_block)
        _write_text_if_changed(html_path, html_candidate)
    _sync_image_sources(article, receipt)
    receipt.pop("_article_dir", None)
    receipt["appendix"] = {
        "markdown": MARKDOWN_START,
        "html": 'data-hybrid-evidence="v1"',
        "appended_at": now(),
        "article_markdown_sha256": sha256_file(md_path),
        "article_html_sha256": sha256_file(html_path),
    }
    receipt["status"] = "passed"
    receipt["errors"] = []
    _write_json(article / "source-evidence.json", receipt)
    print(f"HYBRID EVIDENCE APPENDED: {md_path} + {html_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "audit", "append"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--article", required=True, type=Path)
        if name == "audit":
            cmd.add_argument("--require-appendix", action="store_true")
    cap = sub.add_parser("capture")
    cap.add_argument("--article", required=True, type=Path)
    cap.add_argument("--source-id", required=True)
    cap.add_argument("--browser")
    cap.add_argument("--width", type=int, default=1280)
    cap.add_argument("--height", type=int, default=900)
    args = parser.parse_args()
    article = args.article.expanduser()
    if not article.is_absolute():
        article = ROOT / article
    article = article.resolve()
    if args.command == "init":
        return init_plan(article)
    if args.command == "capture":
        return capture(article, args.source_id, args.browser, args.width, args.height)
    if args.command == "audit":
        return audit(article, require_appendix=bool(args.require_appendix))
    return append(article)


if __name__ == "__main__":
    raise SystemExit(main())
