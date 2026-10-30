#!/usr/bin/env python3
"""Small network-free regression tests for the hybrid evidence contract."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from source_evidence import _appendix_integrity_errors, _validate_plan, _write_lineage, _write_provenance, _write_text_if_changed, classify_source


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_fixture(root: Path, complete: bool) -> None:
    (root / "evidence" / "excerpts").mkdir(parents=True, exist_ok=True)
    (root / "source-snapshots").mkdir(parents=True, exist_ok=True)
    sources = []
    rows = []
    verification_rows = []
    claims = []
    for index, host in enumerate(("docs.python.org", "github.com", "arxiv.org"), 1):
        sid = f"source-{index}"
        path = root / "evidence" / "excerpts" / f"{sid}.md"
        path.write_text(f"Primary evidence excerpt {index}.", encoding="utf-8")
        snapshot = root / "source-snapshots" / f"{sid}.raw"
        snapshot.write_text(f"Snapshot for source {index}", encoding="utf-8")
        snapshot_hash = digest(snapshot)
        sources.append({
            "id": sid,
            "title": f"Primary source {index}",
            "url": f"https://{host}/item/{index}",
            "retrieved_at": "2026-08-10T00:00:00+00:00",
            "kind": "external",
            "evidence_level": "official-docs" if index < 3 else "primary-research",
            "official_source": "official authority",
            "freshness_days": 30,
            "retrieval_status": "passed",
            "http_status": 200,
            "content_sha256": snapshot_hash,
        })
        claims.append({
            "id": f"c{index}",
            "statement": f"Claim {index}",
            "claim_type": "mechanism",
            "as_of": "2026-08-10T00:00:00+00:00",
            "source_ids": [sid],
            "evidence_locator": {"source_id": sid, "kind": "snapshot", "ref": f"https://{host}/item/{index}#snapshot"},
        })
        evidence = [] if not complete and index == 2 else [{
            "id": f"ev-{sid}",
            "kind": "excerpt",
            "path": f"evidence/excerpts/{sid}.md",
            "source_locator": f"https://{host}/item/{index}#excerpt",
            "captured_at": "2026-08-10T00:00:00+00:00",
            "claim_ids": [f"c{index}"],
            "sha256": digest(path),
            "license_status": "short quotation with attribution",
            "reuse_approved": True,
        }]
        rows.append({
            "source_id": sid,
            "tier": "primary",
            "trusted": True,
            "used_in_article": True,
            "claim_ids": [f"c{index}"],
            "evidence": evidence,
            "reuse_approved": True,
            "reuse_reason": "fixture",
        })
        verification_rows.append({
            "id": sid,
            "url": f"https://{host}/item/{index}",
            "url_normalized": f"https://{host}/item/{index}",
            "status": "passed",
            "http_status": 200,
            "content_sha256": snapshot_hash,
            "snapshot": f"source-snapshots/{sid}.raw",
            "snapshot_sha256": snapshot_hash,
            "fetched_at": "2026-08-10T00:00:00+00:00",
        })
    (root / "sources.json").write_text(json.dumps({"sources": sources, "claims": claims}), encoding="utf-8")
    (root / "source-verification.json").write_text(json.dumps({
        "contract": "source-verification-v1",
        "verified_at": "2026-08-10T00:00:00+00:00",
        "sources": verification_rows,
    }), encoding="utf-8")
    (root / "evidence-plan.json").write_text(json.dumps({
        "schema_version": 2,
        "contract": "hybrid-evidence-plan-v1",
        "policy": {
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
        },
        "sources": rows,
    }, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    tier, trusted, reason = classify_source({
        "url": "https://code.claude.com/docs/en/cli-usage",
        "official_domain": "code.claude.com",
        "evidence_level": "official-docs",
    })
    assert (tier, trusted) == ("primary", True), reason
    with tempfile.TemporaryDirectory(prefix="source-evidence-test-") as raw:
        root = Path(raw)
        build_fixture(root, complete=True)
        errors, receipt = _validate_plan(root)
        assert not errors, errors
        assert receipt["trusted_source_count"] == 3
        # Adversarial case: a row can still look complete while its evidence
        # silently stops covering the claim.  The v1.1 contract must reject it.
        plan = json.loads((root / "evidence-plan.json").read_text(encoding="utf-8"))
        plan["sources"][0]["evidence"][0]["claim_ids"] = []
        (root / "evidence-plan.json").write_text(json.dumps(plan), encoding="utf-8")
        errors, _ = _validate_plan(root)
        assert any("缺少 claim_ids" in error or "没有任何有效 evidence" in error for error in errors), errors
        build_fixture(root, complete=True)
        (root / "source-verification.json").unlink()
        errors, _ = _validate_plan(root)
        assert any("source-verification" in error for error in errors), errors
        build_fixture(root, complete=True)
        plan = json.loads((root / "evidence-plan.json").read_text(encoding="utf-8"))
        _write_provenance(root, plan)
        with (root / "evidence/excerpts/source-1.md").open("a", encoding="utf-8") as handle:
            handle.write("stale")
        errors, _ = _validate_plan(root, require_provenance=True)
        assert any("pack_sha256" in error for error in errors), errors
        incomplete = root / "incomplete"
        incomplete.mkdir()
        build_fixture(incomplete, complete=False)
        errors, _ = _validate_plan(incomplete)
        assert any("没有足够证据单元" in error for error in errors), errors

        # Evidence attached to a background source must not satisfy public
        # claim coverage or minimum source counts.
        build_fixture(root, complete=True)
        plan = json.loads((root / "evidence-plan.json").read_text(encoding="utf-8"))
        plan["sources"][0]["used_in_article"] = False
        (root / "evidence-plan.json").write_text(json.dumps(plan), encoding="utf-8")
        errors, receipt = _validate_plan(root)
        assert any("正文实际采用的可信信源数量" in error for error in errors), errors
        assert any("claim c1 没有任何有效 evidence" in error for error in errors), errors
        assert receipt["used_trusted_source_count"] == 2

        # Marker-only appendices are insufficient: detect a post-append edit.
        build_fixture(root, complete=True)
        md = root / "article.md"
        html = root / "article.html"
        md.write_text("# Article\n\n<!-- HYBRID-EVIDENCE-REFERENCES:START -->\nrefs\n<!-- HYBRID-EVIDENCE-REFERENCES:END -->\n", encoding="utf-8")
        html.write_text('<html><body><section data-hybrid-evidence="v1">refs</section></body></html>', encoding="utf-8")
        (root / "source-evidence.json").write_text(json.dumps({
            "appendix": {
                "article_markdown_sha256": digest(md),
                "article_html_sha256": digest(html),
            }
        }), encoding="utf-8")
        assert _appendix_integrity_errors(root) == []
        md.write_text(md.read_text(encoding="utf-8") + "tampered", encoding="utf-8")
        assert any("篇尾引用资料已漂移" in error for error in _appendix_integrity_errors(root))

        # The lineage receipt is replay metadata, not an identity proof.
        build_fixture(root, complete=True)
        plan = json.loads((root / "evidence-plan.json").read_text(encoding="utf-8"))
        provenance = _write_provenance(root, plan)
        lineage = _write_lineage(root, provenance)
        assert lineage["contract"] == "evidence-lineage-v1"
        assert lineage["identity_authenticated"] is False
        assert (root / "evidence-lineage.json").is_file()

        # Re-running an evidence append/refresh must be idempotent.  A no-op
        # write would still advance mtime and make the formatted gate report
        # a false "HTML older than markdown" failure on the next retry.
        stable = root / "stable.txt"
        stable.write_text("same", encoding="utf-8")
        before = stable.stat().st_mtime_ns
        assert _write_text_if_changed(stable, "same") is False
        assert stable.stat().st_mtime_ns == before
        assert _write_text_if_changed(stable, "changed") is True
        assert stable.read_text(encoding="utf-8") == "changed"
    print("SOURCE EVIDENCE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
