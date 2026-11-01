"""Stage validators that connect the contract to the editorial gates.

The contract knows stage order and freshness; it does not know what a script or
a storyboard *is*. This module is the seam: it maps a stage id to the concrete
validators that can judge its artifact, so ``workflow_gate.py check`` runs real
checks rather than only "the file exists and parses".

**Slice S2 scope.** Only the validators whose code now exists on ``main`` are
wired here: the source-candidate contract (``assets``) and its cross-document
agreement with the rights ledger. The capture plan, the editorial validators and
the account configuration are later slices (S3/S4); the CLI prints that
explicitly rather than letting a green check read as an editorial pass.

Nothing here mutates an artifact. A validator returns a list of failures; an
empty list means the stage passed that check.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, List

from .sources import validate_candidates as validate_source_candidates
from .sources import validate_ledger_provenance


def _sibling_validator(filename: str, validate: Callable[[Any], List[str]]) -> Any:
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


def validators_for(stage_id: str) -> List[Any]:
    """The validators a stage runs. Unwired stages run none, never a fake pass.

    S2 wires ``assets`` (source candidates + ledger/candidate agreement). The
    capture plan and the remaining stages are wired in S3/S4.
    """
    return {
        "assets": [source_candidates_validator, ledger_provenance_validator],
    }.get(stage_id, [])
