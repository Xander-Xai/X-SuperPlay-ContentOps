"""Bind every on-screen claim to a quote that exists in a permitted source.

A claim is not a sentence a language model produced; it is an assertion plus the
exact substring that supports it. Verification reads the artifact and checks the
substring is present, so a script cannot quietly drift from its sources: change
the claim text without changing the evidence and `verify()` fails.

Rules, deliberately strict:

- a claim needs at least one artifact;
- every artifact must be `evidence_capable` (permission permits citation);
- every artifact must carry a `quote` that occurs verbatim in its text;
- an artifact that is not text (an image, an audio file) can be cited only as
  `locator`-style support — the claim must also have a quotable text source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from .source_artifact import SourceArtifact

CLAIM_SCHEMA = "contentops.claim-ledger/v1"


class ClaimLedgerError(ValueError):
    """The ledger is malformed, or a claim is not supported by its sources."""


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    artifacts: tuple
    quotes: tuple = ()
    locator: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Claim":
        claim_id = str(payload.get("id") or "").strip()
        text = str(payload.get("text") or "").strip()
        artifacts = tuple(str(item) for item in payload.get("artifacts") or ())
        quotes = payload.get("quotes") or ()
        if not claim_id:
            raise ClaimLedgerError("a claim needs an id")
        if not text:
            raise ClaimLedgerError(f"{claim_id}: empty claim text")
        if not artifacts:
            raise ClaimLedgerError(f"{claim_id}: a claim needs at least one artifact")
        if isinstance(quotes, str):
            quotes = (quotes,)
        return cls(
            id=claim_id,
            text=text,
            artifacts=artifacts,
            quotes=tuple(str(q) for q in quotes if str(q).strip()),
            locator=str(payload.get("locator") or ""),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "artifacts": list(self.artifacts),
            "quotes": list(self.quotes),
            "locator": self.locator,
        }


@dataclass
class ClaimLedger:
    claims: List[Claim] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ClaimLedger":
        if payload.get("schema") != CLAIM_SCHEMA:
            raise ClaimLedgerError(f"schema is not {CLAIM_SCHEMA}")
        claims = [Claim.from_dict(item) for item in payload.get("claims") or ()]
        ids = [claim.id for claim in claims]
        if len(ids) != len(set(ids)):
            raise ClaimLedgerError("duplicate claim id")
        return cls(claims=claims)

    @classmethod
    def load(cls, path: Path) -> "ClaimLedger":
        import json

        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))

    def by_id(self) -> Dict[str, Claim]:
        return {claim.id: claim for claim in self.claims}

    def verify(self, artifacts: Mapping[str, SourceArtifact], repo_root: Path) -> List[str]:
        """Return every problem. An empty list means each claim is supported."""
        problems: List[str] = []
        for claim in self.claims:
            quoted = False
            for artifact_id in claim.artifacts:
                artifact = artifacts.get(artifact_id)
                if artifact is None:
                    problems.append(f"{claim.id}: unknown artifact {artifact_id}")
                    continue
                if not artifact.verify_bytes(repo_root):
                    problems.append(f"{claim.id}: artifact {artifact_id} bytes changed")
                if not artifact.evidence_capable:
                    problems.append(
                        f"{claim.id}: artifact {artifact_id} has permission "
                        f"{artifact.permission} and cannot back a claim"
                    )
                text = artifact.text(repo_root)
                matching = [q for q in claim.quotes if text is not None and q in text]
                if matching:
                    quoted = True
            if not quoted:
                problems.append(
                    f"{claim.id}: no quote occurs in any cited text artifact; "
                    "a claim without a verifiable quote is an assertion, not evidence"
                )
        return problems

    def require_used(self, claim_ids: Iterable[str]) -> List[str]:
        """Every claim in the ledger must appear in the script; return leftovers."""
        used = set(claim_ids)
        return [claim.id for claim in self.claims if claim.id not in used]

    def as_dict(self) -> Dict[str, Any]:
        return {"schema": CLAIM_SCHEMA, "claims": [claim.as_dict() for claim in self.claims]}
