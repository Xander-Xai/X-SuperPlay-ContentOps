"""M5 source and claim evidence stages (Issue #140, behavior-preserving slice).

M5's public stage functions remain in scripts/m5_production.py for compatibility.
Dependencies are explicit so the same repository root, errors, file writer,
source builder and claim ledger are used without a second evidence system.
No media execution, network access, or publication authority lives here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

SOURCE_REFS_SCHEMA = "contentops.m5-source-refs/v1"


def declared_source_refs(project: Path, config: Dict[str, Any], *, blocked_error: type[Exception]) -> List[Dict[str, Any]]:
    """``project.yaml`` refs plus the refs the brief bridge wrote.

    The bridge cannot edit YAML safely, so it writes the evidence it converted
    to ``sources/source-refs.json``. Both lists are one contract: the ids must
    still be unique, which ``build_artifacts`` enforces.
    """
    refs = list(config.get("source_refs") or [])
    sidecar = project / "sources" / "source-refs.json"
    if sidecar.is_file():
        document = json.loads(sidecar.read_text(encoding="utf-8"))
        if document.get("schema") != SOURCE_REFS_SCHEMA:
            raise blocked_error(
                f"sources/source-refs.json schema is not {SOURCE_REFS_SCHEMA}")
        extra = document.get("refs")
        if not isinstance(extra, list):
            raise blocked_error("sources/source-refs.json refs must be a list")
        refs.extend(extra)

    # The YAML is the project's QC-facing index while the bridge sidecar is the
    # immutable evidence payload. Existing projects may legitimately mirror the
    # same evidence row in both places. Collapse byte-for-byte equivalent
    # declarations by ID; keep conflicting declarations fail-closed.
    unique: Dict[str, Dict[str, Any]] = {}
    for ref in refs:
        if not isinstance(ref, dict) or not ref.get("id"):
            raise blocked_error("source refs must be objects with an id")
        source_id = str(ref["id"])
        prior = unique.get(source_id)
        if prior is None:
            unique[source_id] = ref
            continue
        if prior != ref:
            raise blocked_error(f"conflicting duplicate source id: {source_id}")
    return list(unique.values())

def stage_sources(project: Path, config: Dict[str, Any], *, repo_root: Path,
                  source_ref_resolver: Any, artifact_builder: Any,
                  write_json: Any) -> Dict[str, Any]:
    artifacts = artifact_builder(source_ref_resolver(project, config), repo_root=repo_root)
    payload = {
        "schema": "contentops.m5-sources/v1",
        "artifacts": [a.as_dict() for a in artifacts.values()],
    }
    write_json(project / "receipts" / "source-artifacts.json", payload)
    return {"artifacts": artifacts, "count": len(artifacts)}

def stage_claims(project: Path, artifacts: Dict[str, Any], *, repo_root: Path,
                 blocked_error: type[Exception], ledger_type: Any,
                 write_json: Any) -> Dict[str, Any]:
    ledger_path = project / "script" / "claims.json"
    if not ledger_path.is_file():
        raise blocked_error("script/claims.json is missing")
    ledger = ledger_type.load(ledger_path)
    problems = ledger.verify(artifacts, repo_root)
    payload = {
        "schema": "contentops.claim-verification/v1",
        "ok": not problems,
        "problems": problems,
        "claims": len(ledger.claims),
    }
    write_json(project / "receipts" / "claim-verification.json", payload)
    if problems:
        raise blocked_error("claims are not supported: " + "; ".join(problems[:4]))
    return {"ledger": ledger, "count": len(ledger.claims)}
