"""The editorial-validator seam, intentionally empty in slice S1.

The contract and gate in this package are deterministic: they know stage order,
freshness and digests, but they do not know what a script or a storyboard *is*.
Judging that is the job of the stage validators, which live in the evidence,
media and quality trees that arrive in a later slice (S2/S3).

This module exists now so the gate's shape is stable: ``gate.check_stage``
already accepts validators as an injected ``Sequence[Validator]``, and
``scripts/workflow_gate.py`` looks them up through ``validators_for``. Until S2
lands the validator modules, the registry is empty by design — a stage ``check``
runs the structural half (artifact present, upstream current, digests pinned)
and reports that no editorial validators are wired.

An empty list is the honest answer here, not a silent pass of an editorial
gate: an empty registry means "nothing to judge yet", and the CLI prints that
explicitly. S2 replaces this file with the real registry.
"""

from __future__ import annotations


def validators_for(stage_id: str) -> list:
    """Return the validators a stage runs. Empty until S2 wires the seam.

    ``stage_id`` is accepted and ignored so the call site does not have to
    change when the real registry lands.
    """
    return []
