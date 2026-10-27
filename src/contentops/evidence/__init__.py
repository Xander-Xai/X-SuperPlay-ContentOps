"""Evidence contracts owned by ContentOps.

``capture``   — what a recording proves and under which conditions;
``redaction`` — how a publishable derivative is linked to its raw source;
``claim_map`` — the interim per-package binding of exact output text to evidence.

The Issue #6 Claim Ledger is a separate, later milestone. Nothing here claims to
replace it.
"""

from .capture import (
    CAPTURE_PROOF_SCHEMA,
    EVIDENCE_CLASSES,
    CaptureProof,
)
from .claim_map import (
    CLAIM_MAP_SCHEMA,
    Claim,
    ClaimMap,
)
from .redaction import (
    REDACTION_SCHEMA,
    RedactionReceipt,
)

__all__ = [
    "CAPTURE_PROOF_SCHEMA",
    "CLAIM_MAP_SCHEMA",
    "EVIDENCE_CLASSES",
    "REDACTION_SCHEMA",
    "CaptureProof",
    "Claim",
    "ClaimMap",
    "RedactionReceipt",
]
