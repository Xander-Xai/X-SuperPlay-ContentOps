"""Evidence primitives shared by every production run.

A video's factual claims are only as good as the artifacts they point at, so the
two are kept together: `SourceArtifact` records where a fact came from and under
what permission, `ClaimLedger` binds each claim to a quote that must actually
exist in that artifact.
"""

from .claim_ledger import (  # noqa: F401
    CLAIM_SCHEMA,
    Claim,
    ClaimLedger,
    ClaimLedgerError,
)
from .source_artifact import (  # noqa: F401
    ARTIFACT_SCHEMA,
    EVIDENCE_CAPABLE_PERMISSIONS,
    SourceArtifact,
    SourceArtifactError,
    build_artifacts,
)

__all__ = [
    "ARTIFACT_SCHEMA",
    "CLAIM_SCHEMA",
    "EVIDENCE_CAPABLE_PERMISSIONS",
    "Claim",
    "ClaimLedger",
    "ClaimLedgerError",
    "SourceArtifact",
    "SourceArtifactError",
    "build_artifacts",
]
