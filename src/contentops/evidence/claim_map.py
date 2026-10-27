"""The interim Claim Map: the local guard against unsupported video facts.

This is deliberately **not** the Issue #6 Claim Ledger. It is a per-package
document that binds the exact text which appears in narration, captions, labels,
titles, descriptions, cover titles and CTAs to immutable evidence hashes. It is
importable as input when the real ledger exists; it does not pretend to be one.

The rule that makes it useful is exactness. An appearance's text must equal its
claim's text. A caption that quietly rephrases a narration line is a *different*
claim and needs its own binding, because "the same thing, shorter" is exactly
where an unsupported qualifier disappears.

``support_status`` controls what may be asserted:

- ``SUPPORTED`` — it may appear as a fact on any asserted surface;
- ``PARTIAL`` — must state its limitation; it may appear only as a qualified
  statement, never as a bare fact;
- ``BLOCKED`` — it may not appear anywhere, including covers and CTAs.

Generated and diagram visuals are rejected as evidence here, not merely ignored:
a generated image that looks like a terminal is the specific failure this module
exists to stop, and it has no path to support a factual claim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ._common import (
    ContractError,
    fingerprint,
    parse_time_range,
    require,
    require_schema,
    require_sha256,
    require_text,
)

CLAIM_MAP_SCHEMA = "contentops.claim-map/v1"

SUPPORTED = "SUPPORTED"
PARTIAL = "PARTIAL"
BLOCKED = "BLOCKED"
SUPPORT_STATUSES = (SUPPORTED, PARTIAL, BLOCKED)

KINDS = ("runtime", "source", "historical", "judgement", "editorial_transition", "cta")

ABOUT = ("cli", "ui", "source", "data", "product", "judgement", "none")

EVIDENCE_KINDS = (
    "terminal_recording",
    "terminal_screenshot",
    "ui_screenshot",
    "ui_recording",
    "document",
    "data",
)
REJECTED_EVIDENCE_KINDS = ("generated_image", "generated_video", "diagram")

SURFACES = (
    "narration",
    "caption",
    "label",
    "title",
    "description",
    "cover_title",
    "cta",
    "onscreen",
    "transition",
)
ASSERTED_SURFACES = tuple(s for s in SURFACES if s != "transition")

PERMISSION_SCOPES = ("publishable", "internal", "pending")

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")


def _require_id(value: Any, field_name: str) -> str:
    text = require_text(value, field_name)
    require(bool(_ID_RE.match(text)), "INVALID_ID",
            f"{field_name} must match [A-Za-z0-9][A-Za-z0-9._-]{{2,63}}: {text!r}")
    return text


def _validate_evidence(item: Any, claim_id: str, index: int) -> Dict[str, Any]:
    where = f"{claim_id}.evidence[{index}]"
    require(isinstance(item, dict), "INVALID_EVIDENCE", f"{where} must be an object")
    _require_id(item.get("evidence_id"), f"{where}.evidence_id")
    kind = require_text(item.get("kind"), f"{where}.kind")
    require(kind in EVIDENCE_KINDS, "UNSUPPORTED_EVIDENCE_KIND",
            f"{where}.kind {kind!r} cannot support a factual claim; allowed: "
            f"{', '.join(EVIDENCE_KINDS)} (generated and diagram visuals are "
            f"rejected by design)")
    require_sha256(item.get("sha256"), f"{where}.sha256")
    logical = require_text(item.get("logical_path"), f"{where}.logical_path")
    require(logical.startswith(("project://", "repo://")), "NON_LOGICAL_PATH",
            f"{where}.logical_path must be project:// or repo://")
    if item.get("time_range") is not None:
        parse_time_range(item["time_range"], f"{where}.time_range")
    scope = item.get("permission_scope", "publishable")
    require(scope in PERMISSION_SCOPES, "INVALID_PERMISSION_SCOPE",
            f"{where}.permission_scope must be one of {PERMISSION_SCOPES}")
    return {
        "evidence_id": item["evidence_id"],
        "kind": kind,
        "sha256": item["sha256"],
        "logical_path": logical,
        "time_range": item.get("time_range"),
        "permission_scope": scope,
    }


def _validate_appearance(item: Any, claim_id: str, index: int) -> Dict[str, Any]:
    where = f"{claim_id}.appearances[{index}]"
    require(isinstance(item, dict), "INVALID_APPEARANCE", f"{where} must be an object")
    surface = require_text(item.get("surface"), f"{where}.surface")
    require(surface in SURFACES, "UNKNOWN_SURFACE",
            f"{where}.surface {surface!r} is not a known output surface")
    text = require_text(item.get("text"), f"{where}.text")
    if item.get("time_range") is not None:
        parse_time_range(item["time_range"], f"{where}.time_range")
    return {"surface": surface, "text": text, "time_range": item.get("time_range")}


@dataclass
class Claim:
    claim_id: str
    revision: int
    text: str
    kind: str
    assertion_about: str
    support_status: str
    permission_scope: str
    limitation: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    appearances: List[Dict[str, Any]] = field(default_factory=list)

    def validate(self) -> "Claim":
        _require_id(self.claim_id, "claim_id")
        require(isinstance(self.revision, int) and not isinstance(self.revision, bool)
                and self.revision >= 1, "INVALID_REVISION",
                f"{self.claim_id}.revision must be an integer >= 1")
        require_text(self.text, f"{self.claim_id}.text")
        require(self.kind in KINDS, "UNKNOWN_CLAIM_KIND",
                f"{self.claim_id}.kind must be one of {KINDS}")
        require(self.assertion_about in ABOUT, "UNKNOWN_ASSERTION_SUBJECT",
                f"{self.claim_id}.assertion_about must be one of {ABOUT}")
        require(self.support_status in SUPPORT_STATUSES, "INVALID_SUPPORT_STATUS",
                f"{self.claim_id}.support_status must be one of {SUPPORT_STATUSES}")
        require(self.permission_scope in PERMISSION_SCOPES, "INVALID_PERMISSION_SCOPE",
                f"{self.claim_id}.permission_scope must be one of {PERMISSION_SCOPES}")

        seen = set()
        validated_evidence = []
        for index, item in enumerate(self.evidence):
            item = _validate_evidence(item, self.claim_id, index)
            require(item["evidence_id"] not in seen, "DUPLICATE_EVIDENCE_ID",
                    f"{self.claim_id} reuses evidence_id {item['evidence_id']!r}")
            seen.add(item["evidence_id"])
            validated_evidence.append(item)
        self.evidence = validated_evidence

        if self.support_status == SUPPORTED:
            require(self.kind != "judgement", "JUDGEMENT_MARKED_SUPPORTED",
                    f"{self.claim_id} is a judgement and cannot be SUPPORTED as a fact")
            if self.kind not in ("editorial_transition", "cta"):
                # Transitions and CTAs assert no fact, so they need no evidence.
                # Every other SUPPORTED claim must name its support.
                require(bool(self.evidence), "SUPPORTED_WITHOUT_EVIDENCE",
                        f"{self.claim_id} claims SUPPORTED but binds no evidence")
            require(not self.limitation.strip(), "SUPPORTED_WITH_LIMITATION",
                    f"{self.claim_id} is SUPPORTED but states a limitation; use PARTIAL")
        if self.support_status == PARTIAL:
            require(self.limitation.strip(), "PARTIAL_WITHOUT_LIMITATION",
                    f"{self.claim_id} is PARTIAL and must state its limitation")
        if self.support_status == BLOCKED:
            require(not self.appearances, "BLOCKED_CLAIM_APPEARS",
                    f"{self.claim_id} is BLOCKED and cannot appear on any surface")

        if self.assertion_about == "ui":
            require(any(e["kind"].startswith("ui_") for e in self.evidence),
                    "UI_CLAIM_WITHOUT_UI_EVIDENCE",
                    f"{self.claim_id} asserts a UI state but binds no ui_screenshot or "
                    f"ui_recording; terminal output cannot prove a rendered UI")
        if self.assertion_about == "cli":
            require(any(e["kind"].startswith("terminal_") for e in self.evidence),
                    "CLI_CLAIM_WITHOUT_TERMINAL_EVIDENCE",
                    f"{self.claim_id} asserts a CLI outcome but binds no terminal capture")
        if self.assertion_about == "source":
            require(any(e["kind"] == "document" for e in self.evidence),
                    "SOURCE_CLAIM_WITHOUT_DOCUMENT",
                    f"{self.claim_id} asserts source text but binds no document evidence")
        if self.assertion_about == "data":
            require(any(e["kind"] == "data" for e in self.evidence),
                    "DATA_CLAIM_WITHOUT_DATA",
                    f"{self.claim_id} asserts a measurement but binds no data evidence")

        if self.permission_scope == "publishable":
            for item in self.evidence:
                require(item["permission_scope"] == "publishable",
                        "PERMISSION_INCOMPATIBLE",
                        f"{self.claim_id} is publishable but evidence "
                        f"{item['evidence_id']} is {item['permission_scope']}")

        seen_surfaces = set()
        validated_appearances = []
        for index, item in enumerate(self.appearances):
            item = _validate_appearance(item, self.claim_id, index)
            require(item["text"] == self.text, "APPEARANCE_TEXT_CHANGED",
                    f"{self.claim_id} appears on {item['surface']} as "
                    f"{item['text']!r}, but the claim text is {self.text!r}; a "
                    f"different wording is a different claim")
            key = (item["surface"], item["text"])
            require(key not in seen_surfaces, "DUPLICATE_APPEARANCE",
                    f"{self.claim_id} appears twice on {item['surface']}")
            seen_surfaces.add(key)
            if item["surface"] in ASSERTED_SURFACES:
                require(self.support_status == SUPPORTED, "UNSUPPORTED_ASSERTION",
                        f"{self.claim_id} is {self.support_status} but appears on the "
                        f"asserted surface {item['surface']!r}")
            validated_appearances.append(item)
        self.appearances = validated_appearances
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "revision": self.revision,
            "text": self.text,
            "kind": self.kind,
            "assertion_about": self.assertion_about,
            "support_status": self.support_status,
            "permission_scope": self.permission_scope,
            "limitation": self.limitation,
            "evidence": list(self.evidence),
            "appearances": list(self.appearances),
        }


@dataclass
class ClaimMap:
    map_id: str
    package_id: str
    claims: List[Claim] = field(default_factory=list)

    def validate(self) -> "ClaimMap":
        _require_id(self.map_id, "map_id")
        _require_id(self.package_id, "package_id")
        seen = set()
        for index, claim in enumerate(self.claims):
            require(isinstance(claim, Claim), "INVALID_CLAIM",
                    f"claims[{index}] is not a Claim")
            claim.validate()
            require(claim.claim_id not in seen, "DUPLICATE_CLAIM_ID",
                    f"duplicate claim_id {claim.claim_id!r}")
            seen.add(claim.claim_id)
        return self

    def by_id(self, claim_id: str) -> Claim:
        for claim in self.claims:
            if claim.claim_id == claim_id:
                return claim
        raise ContractError("UNKNOWN_CLAIM", f"no claim {claim_id!r} in this map")

    def claim_for(self, surface: str, text: str) -> Claim:
        for claim in self.claims:
            for appearance in claim.appearances:
                if appearance["surface"] == surface and appearance["text"] == text:
                    return claim
        raise ContractError(
            "UNBOUND_SURFACE",
            f"{surface} text {text!r} is not bound to any claim; every factual "
            f"output surface must be claim-mapped",
        )

    def require_publishable(self) -> "ClaimMap":
        for claim in self.claims:
            if claim.permission_scope != "publishable":
                require(not claim.appearances, "NON_PUBLISHABLE_SURFACE",
                        f"{claim.claim_id} is {claim.permission_scope} but appears on "
                        f"a distributable surface")
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": CLAIM_MAP_SCHEMA,
            "map_id": self.map_id,
            "package_id": self.package_id,
            "claims": [claim.to_dict() for claim in self.claims],
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())

    @classmethod
    def from_dict(cls, document: Dict[str, Any]) -> "ClaimMap":
        require_schema(document, CLAIM_MAP_SCHEMA)
        known = {"schema", "map_id", "package_id", "claims"}
        unknown = sorted(set(document) - known)
        require(not unknown, "UNKNOWN_FIELD",
                f"unknown claim-map fields: {', '.join(unknown)}")
        claims = []
        for index, raw in enumerate(document.get("claims") or []):
            require(isinstance(raw, dict), "INVALID_CLAIM",
                    f"claims[{index}] must be an object")
            allowed = {
                "claim_id", "revision", "text", "kind", "assertion_about",
                "support_status", "permission_scope", "limitation", "evidence",
                "appearances",
            }
            extra = sorted(set(raw) - allowed)
            require(not extra, "UNKNOWN_FIELD",
                    f"claims[{index}] has unknown fields: {', '.join(extra)}")
            try:
                claims.append(Claim(
                    claim_id=raw["claim_id"],
                    revision=raw["revision"],
                    text=raw["text"],
                    kind=raw["kind"],
                    assertion_about=raw["assertion_about"],
                    support_status=raw["support_status"],
                    permission_scope=raw["permission_scope"],
                    limitation=raw.get("limitation", ""),
                    evidence=list(raw.get("evidence") or []),
                    appearances=list(raw.get("appearances") or []),
                ))
            except KeyError as exc:
                raise ContractError("MISSING_FIELD",
                                    f"claims[{index}] is missing {exc.args[0]!r}") from None
        return cls(
            map_id=document.get("map_id", ""),
            package_id=document.get("package_id", ""),
            claims=claims,
        ).validate()
