"""Stage validators that connect the contract to the editorial gates.

The contract knows stage order and freshness; it does not know what a script or
a storyboard *is*. This module is the seam: it maps a stage id to the concrete
validators that can judge its artifact, so `workflow_gate.py check` runs real
checks rather than only "the file exists and parses".

Nothing here mutates an artifact. A validator returns a list of failures; an
empty list means the stage passed that check.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from contentops.evidence.claim_map import ClaimMap
from contentops.media.claim_coverage import validate_claim_coverage
from contentops.media.cut_plan import CutPlan
from contentops.quality.script_rhythm import validate_script_rhythm
from contentops.quality.naturalness import validate_naturalness
from contentops.quality.technical_explainer import validate_script_file as validate_technical_explainer
from contentops.workflow.audience import validate_audience_insight
from contentops.workflow.capture_plan import validate_capture_plan
from contentops.workflow.copy_strategy import validate_strategy as validate_copy_strategy
from contentops.workflow.delivery import validate_manifest as validate_delivery_manifest
from contentops.workflow.duration import validate_script_duration
from contentops.workflow.human_forecast import validate_forecast as validate_evidence_forecast
from contentops.workflow.platform import validate_plan as validate_publish_plan
from contentops.workflow.rights import validate_ledger as validate_rights_ledger
from contentops.workflow.sources import (
    validate_candidates as validate_source_candidates,
    validate_ledger_provenance,
)
from contentops.workflow.topics import validate_candidate as validate_content_candidate
from contentops.workflow.visual_route import validate_route as validate_visual_route


def script_rhythm_validator(path: Path) -> List[str]:
    return validate_script_rhythm(path)


def script_duration_validator(path: Path) -> List[str]:
    return validate_script_duration(path)


def audience_validator(path: Path) -> List[str]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"audience insight unreadable: {exc}"]
    return validate_audience_insight(document)


def _sibling_validator(filename: str, validate) -> Any:
    """Validate a sibling document when it is present; not applicable otherwise."""
    def validator(path: Path) -> List[str]:
        sibling = Path(path).with_name(filename)
        if not sibling.is_file():
            return []
        try:
            document = json.loads(sibling.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return [f"{filename} unreadable: {exc}"]
        return validate(document)
    validator.__name__ = f"{filename}_validator"
    return validator


rights_validator = _sibling_validator("rights-ledger.json", validate_rights_ledger)
source_candidates_validator = _sibling_validator("source-candidates.json",
                                                 validate_source_candidates)


def ledger_provenance_validator(path: Path) -> List[str]:
    """A ledger row that cites a candidate must agree with that candidate.

    This is the cross-document half of the source-candidate contract: the
    ledger and the candidate list each pass on their own, and still contradict
    each other. It runs only when both siblings exist — a package with no
    research candidate list has nothing to reconcile.
    """
    path = Path(path)
    ledger_path = path.with_name("rights-ledger.json")
    candidates_path = path.with_name("source-candidates.json")
    if not ledger_path.is_file() or not candidates_path.is_file():
        return []
    documents = []
    for source in (ledger_path, candidates_path):
        try:
            documents.append(json.loads(source.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return [f"{source.name} unreadable: {exc}"]
    return validate_ledger_provenance(documents[0], documents[1])
publish_plan_validator = _sibling_validator("publish-plan.json", validate_publish_plan)
candidate_validator = _sibling_validator("candidate.json", validate_content_candidate)
forecast_validator = _sibling_validator("forecast.json", validate_evidence_forecast)
copy_strategy_validator = _sibling_validator("copy-strategy.json", validate_copy_strategy)
visual_route_validator = _sibling_validator("visual-route.json", validate_visual_route)
naturalness_validator = _sibling_validator("naturalness.json", validate_naturalness)
capture_plan_validator = _sibling_validator("capture-plan.json", validate_capture_plan)


def technical_explainer_validator(path: Path) -> List[str]:
    return validate_technical_explainer(path)


def delivery_manifest_validator(path: Path) -> List[str]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"delivery manifest unreadable: {exc}"]
    return validate_delivery_manifest(document)


def claim_coverage_validator(path: Path) -> List[str]:
    """A cut plan must be backed by its claim map, and by real captures.

    ``claim-map.json`` and ``assets.json`` are read from the cut plan's own
    directory. Keeping them siblings means one canonical location per package
    and no search path to guess.
    """
    path = Path(path)
    try:
        cut_plan = CutPlan.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"cut plan unreadable: {exc}"]
    except Exception as exc:  # ContractError from CutPlan.from_dict
        return [f"cut plan invalid: {exc}"]

    map_path = path.with_name("claim-map.json")
    if not map_path.is_file():
        return [f"claim-map.json missing beside {path.name}"]
    try:
        claim_map = ClaimMap.from_dict(json.loads(map_path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"claim map unreadable: {exc}"]
    except Exception as exc:
        return [f"claim map invalid: {exc}"]

    assets: Dict[str, Dict[str, Any]] | None = None
    assets_path = path.with_name("assets.json")
    if assets_path.is_file():
        try:
            document = json.loads(assets_path.read_text(encoding="utf-8"))
            assets = document.get("assets") if isinstance(document, dict) else None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return [f"asset map unreadable: {exc}"]
        if not isinstance(assets, dict):
            return ["asset map has no 'assets' object"]
    return validate_claim_coverage(cut_plan, claim_map, assets).errors


def validators_for(stage_id: str) -> List[Any]:
    """The validators a stage runs. Unknown stages run none, never a fake pass."""
    return {
        "brief": [candidate_validator, forecast_validator],
        "audience": [audience_validator],
        "script": [script_rhythm_validator, script_duration_validator,
                   technical_explainer_validator, copy_strategy_validator,
                   naturalness_validator],
        "storyboard": [claim_coverage_validator, capture_plan_validator],
        "assets": [rights_validator, source_candidates_validator,
                   ledger_provenance_validator],
        "compose": [visual_route_validator],
        "delivery": [delivery_manifest_validator, publish_plan_validator],
    }.get(stage_id, [])
