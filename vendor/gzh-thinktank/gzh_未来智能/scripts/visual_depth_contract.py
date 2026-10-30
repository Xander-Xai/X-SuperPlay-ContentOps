#!/usr/bin/env python3
"""Build the explicit visual-depth fields used by the visual gates.

The renderer may choose a layout, but it must not invent the explanatory
argument.  This helper only derives machine-readable edges from authored
``diagram_data``/labels and binds them to evidence IDs already present in the
article's evidence plan.  Missing claims or evidence remain missing and are
intentionally left for the depth gate to block.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CONTRACT = "visual-depth-contract-v1"


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _evidence_index(article: Path) -> tuple[dict[str, tuple[str, set[str]]], bool]:
    """Return evidence-id -> locator and whether the evidence run passed."""
    plan = _json(article / "evidence-plan.json")
    mapping: dict[str, tuple[str, set[str]]] = {}
    for row in plan.get("sources", []) if isinstance(plan.get("sources"), list) else []:
        if not isinstance(row, dict):
            continue
        for evidence in row.get("evidence", []) if isinstance(row.get("evidence"), list) else []:
            if isinstance(evidence, dict) and str(evidence.get("id") or "").strip():
                mapping[str(evidence["id"]).strip()] = (
                    str(evidence.get("source_locator") or evidence.get("path") or "").strip(),
                    {str(value).strip() for value in evidence.get("claim_ids", []) if str(value).strip()}
                    if isinstance(evidence.get("claim_ids"), list) else set(),
                )
    receipt = _json(article / "source-evidence.json")
    return mapping, str(receipt.get("status") or "").strip().lower() == "passed"


def _claims_passed(article: Path) -> bool:
    verification = _json(article / "claim-verification.json")
    return str(verification.get("status") or "").strip().lower() == "passed"


def _entities_and_edges(unit: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    diagram = unit.get("diagram_data") if isinstance(unit.get("diagram_data"), dict) else {}
    nodes = [item for item in diagram.get("nodes", []) if isinstance(item, dict)]
    entities = [str(item.get("label") or "").strip() for item in nodes if str(item.get("label") or "").strip()]
    ids = [str(item.get("id") or f"n{index}").strip() for index, item in enumerate(nodes)]
    if not entities:
        entities = [str(value).strip() for value in unit.get("expected_elements", []) if str(value).strip()]
        ids = [f"n{index}" for index in range(len(entities))]
    entities = list(dict.fromkeys(entities))[:8]
    if len(entities) < 2:
        return entities, []
    source_edges = [item for item in diagram.get("edges", []) if isinstance(item, dict)]
    edges: list[dict[str, Any]] = []
    for index, edge in enumerate(source_edges):
        source_id = str(edge.get("source") or "").strip()
        target_id = str(edge.get("target") or "").strip()
        if source_id not in ids or target_id not in ids:
            continue
        source = entities[ids.index(source_id)]
        target = entities[ids.index(target_id)]
        edges.append({"source": source, "target": target, "id": str(edge.get("id") or f"edge-{index + 1}")})
    if not edges:
        edges = [{"source": entities[index], "target": entities[index + 1], "id": f"edge-{index + 1}"} for index in range(len(entities) - 1)]
    return entities, edges[:8]


def enrich_unit(unit: dict[str, Any], article: Path) -> dict[str, Any]:
    """Return a copy with explicit reader task, relations and fallback."""
    result = dict(unit)
    claim_ids = [str(value).strip() for value in result.get("claim_ids", []) if str(value).strip()]
    evidence_locator, evidence_passed = _evidence_index(article)
    evidence_ids = []
    for evidence_id, (_locator, bound_claims) in evidence_locator.items():
        # Evidence IDs are already claim-bound in evidence-plan.json.  Keep
        # them only when the unit has a claim binding; never invent a source.
        if claim_ids and (not bound_claims or set(claim_ids) & bound_claims) and evidence_id not in evidence_ids:
            evidence_ids.append(evidence_id)
    evidence_ids = evidence_ids[:12]
    entities, raw_edges = _entities_and_edges(result)
    visual_type = str(result.get("visual_type") or result.get("kind") or "concept").strip().lower()
    layout = str(result.get("layout_archetype") or visual_type).strip()
    if visual_type in {"comparison", "architecture"} or "comparison" in layout:
        relation_type = "contrasts" if "comparison" in layout or visual_type == "comparison" else "contains"
    elif visual_type in {"code", "pseudocode"}:
        relation_type = "implements"
    elif visual_type in {"numeric", "shape", "attention"}:
        relation_type = "transforms"
    elif visual_type == "checklist":
        relation_type = "validates"
    else:
        relation_type = "precedes"
    locator = evidence_locator.get(evidence_ids[0], ("", set()))[0] if evidence_ids else ""
    relations = []
    for index, edge in enumerate(raw_edges):
        relations.append({
            "id": edge["id"],
            "type": relation_type,
            "source": edge["source"],
            "target": edge["target"],
            "evidence_ids": evidence_ids[:3],
            "source_locator": locator,
            "verification_status": "verified" if claim_ids and evidence_ids and evidence_passed and _claims_passed(article) else "pending",
        })
    result.update({
        "depth_contract": CONTRACT,
        "reader_question": f"读者能否根据这张图回答：{result.get('purpose') or result.get('viewer_job') or '本节要点是什么'}？",
        "answer_sentence": str(result.get("purpose") or result.get("viewer_job") or "").strip(),
        "visual_thesis": str(result.get("purpose") or result.get("viewer_job") or "").strip(),
        "entities": entities,
        "relations": relations,
        "evidence_ids": evidence_ids,
        "layout_grammar": layout,
        "must_explain": [relation_type],
        "fallback_backend": "textual-outline",
        "fallback_trigger": "SVG/HTML source or rasterization unavailable",
        "fallback_semantic_equivalence": "same labels, relation types, claim IDs and evidence IDs in a text outline",
    })
    return result


def enrich_contract(article: Path) -> dict[str, Any]:
    path = article / "visual-contract.json"
    document = _json(path)
    units = []
    for unit in document.get("units", []) if isinstance(document.get("units"), list) else []:
        units.append(enrich_unit(unit, article) if isinstance(unit, dict) and str(unit.get("id") or "") != "cover" else unit)
    document["units"] = units
    return document
