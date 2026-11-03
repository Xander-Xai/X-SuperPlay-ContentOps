"""Capture Proof: what a recording actually proves, and what it does not.

A recording is not evidence by itself. It becomes evidence when it carries the
things that let a later reader decide whether the filmed result applies to the
claim: the revision, the working-tree state, the environment, the command, the
exit code, the time range, and who approved publication.

``evidence_class`` is the load-bearing field:

``EXECUTED``
    This run executed the declared command in the declared environment. The
    exit code is this run's exit code.
``HISTORICAL``
    The recording shows an earlier receipt or run. It proves what that receipt
    recorded then, not what happens now.
``DOCUMENTED``
    The recording shows configuration or source text. It proves the text, never
    a runtime outcome.

A non-zero exit code is valid, observed evidence. :class:`CaptureProof` never
"fixes" one: a failing command that failed is exactly what the receipt should
say, and rewriting it to 0 would be the fabrication this contract exists to
prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from ._common import (
    ContractError,
    parse_time_range,
    require,
    require_schema,
    require_sha256,
    require_text,
    iso_utc,
    sha256_file,
)

CAPTURE_PROOF_SCHEMA = "contentops.capture-proof/v1"

EVIDENCE_EXECUTED = "EXECUTED"
EVIDENCE_HISTORICAL = "HISTORICAL"
EVIDENCE_DOCUMENTED = "DOCUMENTED"
EVIDENCE_CLASSES = (EVIDENCE_EXECUTED, EVIDENCE_HISTORICAL, EVIDENCE_DOCUMENTED)

SCOPE_PUBLISHABLE = "publishable"
SCOPE_INTERNAL = "internal_review"
SCOPE_RESTRICTED = "restricted"
PERMISSION_SCOPES = (SCOPE_PUBLISHABLE, SCOPE_INTERNAL, SCOPE_RESTRICTED)

LOGICAL_PREFIXES = ("project://", "repo://")


def _validate_working_tree(value: Any) -> str:
    text = require_text(value, "working_tree_state")
    if text == "clean":
        return text
    if text.startswith("dirty:"):
        require_sha256(text[len("dirty:"):], "working_tree_state diff hash")
        return text
    raise ContractError(
        "INVALID_WORKING_TREE",
        "working_tree_state must be 'clean' or 'dirty:<sha256>'",
    )


def _validate_environment(value: Any) -> Dict[str, Any]:
    require(isinstance(value, dict), "MISSING_FIELD",
            "target_environment must be an object")
    require_text(value.get("name"), "target_environment.name")
    digest = value.get("description_digest")
    if digest is not None:
        require_sha256(digest, "target_environment.description_digest")
    return dict(value)


def _validate_command(value: Any) -> Dict[str, Any]:
    require(isinstance(value, dict), "MISSING_FIELD",
            "command must be an object with a redacted display and a hash")
    display = require_text(value.get("display"), "command.display")
    lowered = display.lower()
    for marker in (".env", "api_key", "apikey", "password", "token", "secret",
                   "bearer", "authorization", "sk-"):
        require(marker not in lowered, "SECRET_IN_COMMAND",
                f"command.display appears to contain {marker!r}")
    require_sha256(value.get("sha256"), "command.sha256")
    return dict(value)


def _validate_fixture(value: Any) -> Any:
    if value == "none":
        return value
    require(isinstance(value, dict), "INVALID_FIXTURE",
            "fixture_or_cache must be 'none' or an object")
    require_text(value.get("kind"), "fixture_or_cache.kind")
    if "sha256" in value:
        require_sha256(value["sha256"], "fixture_or_cache.sha256")
    return dict(value)


def _validate_recording(value: Any) -> Dict[str, Any]:
    require(isinstance(value, dict), "MISSING_FIELD",
            "recording must be an object")
    logical = require_text(value.get("logical_path"), "recording.logical_path")
    require(logical.startswith(LOGICAL_PREFIXES), "NON_LOGICAL_PATH",
            "recording.logical_path must be project:// or repo:// so the receipt "
            "stays portable")
    require_sha256(value.get("sha256"), "recording.sha256")
    parse_time_range(value.get("time_range"), "recording.time_range")
    return dict(value)


def _validate_approval(value: Any) -> Dict[str, Any]:
    require(isinstance(value, dict), "MISSING_APPROVAL",
            "publishable capture requires an approval object")
    require_text(value.get("reviewer"), "approval.reviewer")
    iso_utc(value.get("approved_at"), "approval.approved_at")
    return dict(value)


@dataclass
class CaptureProof:
    capture_id: str
    session_id: str
    evidence_class: str
    repository_revision: str
    working_tree_state: str
    target_environment: Dict[str, Any]
    command: Dict[str, Any]
    read_only: bool
    fixture_or_cache: Any
    started_at: str
    finished_at: str
    exit_code: int
    recording: Dict[str, Any]
    permission_scope: str
    transcript_sha256: Optional[str] = None
    approval: Optional[Dict[str, Any]] = None
    notes: list = field(default_factory=list)

    def validate(self) -> "CaptureProof":
        require_text(self.capture_id, "capture_id")
        require_text(self.session_id, "session_id")
        require(self.evidence_class in EVIDENCE_CLASSES, "INVALID_EVIDENCE_CLASS",
                f"evidence_class must be one of {EVIDENCE_CLASSES}")
        require_text(self.repository_revision, "repository_revision")
        _validate_working_tree(self.working_tree_state)
        _validate_environment(self.target_environment)
        _validate_command(self.command)
        require(isinstance(self.read_only, bool), "INVALID_READ_ONLY",
                "read_only must be a boolean")
        _validate_fixture(self.fixture_or_cache)
        started = iso_utc(self.started_at, "started_at")
        finished = iso_utc(self.finished_at, "finished_at")
        require(finished >= started, "INVALID_TIMESTAMP",
                "finished_at is before started_at")
        require(isinstance(self.exit_code, int) and not isinstance(self.exit_code, bool),
                "INVALID_EXIT_CODE", "exit_code must be an integer")
        _validate_recording(self.recording)
        require(self.permission_scope in PERMISSION_SCOPES, "INVALID_PERMISSION_SCOPE",
                f"permission_scope must be one of {PERMISSION_SCOPES}")
        if self.transcript_sha256 is not None:
            require_sha256(self.transcript_sha256, "transcript_sha256")
        if self.permission_scope == SCOPE_PUBLISHABLE:
            require(self.read_only, "PUBLISHABLE_REQUIRES_READ_ONLY",
                    "a publishable capture must declare read_only=true")
            _validate_approval(self.approval)
        elif self.approval is not None:
            _validate_approval(self.approval)
        return self

    def to_dict(self) -> Dict[str, Any]:
        document = {
            "schema": CAPTURE_PROOF_SCHEMA,
            "capture_id": self.capture_id,
            "session_id": self.session_id,
            "evidence_class": self.evidence_class,
            "repository_revision": self.repository_revision,
            "working_tree_state": self.working_tree_state,
            "target_environment": self.target_environment,
            "command": self.command,
            "read_only": self.read_only,
            "fixture_or_cache": self.fixture_or_cache,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "recording": self.recording,
            "permission_scope": self.permission_scope,
            "notes": list(self.notes),
        }
        if self.transcript_sha256 is not None:
            document["transcript_sha256"] = self.transcript_sha256
        if self.approval is not None:
            document["approval"] = self.approval
        return document

    @classmethod
    def from_dict(cls, document: Dict[str, Any]) -> "CaptureProof":
        require_schema(document, CAPTURE_PROOF_SCHEMA)
        known = {
            "schema", "capture_id", "session_id", "evidence_class",
            "repository_revision", "working_tree_state", "target_environment",
            "command", "read_only", "fixture_or_cache", "started_at",
            "finished_at", "exit_code", "recording", "permission_scope",
            "transcript_sha256", "approval", "notes",
        }
        unknown = sorted(set(document) - known)
        require(not unknown, "UNKNOWN_FIELD",
                f"unknown capture-proof fields: {', '.join(unknown)}")
        try:
            proof = cls(
                capture_id=document["capture_id"],
                session_id=document["session_id"],
                evidence_class=document["evidence_class"],
                repository_revision=document["repository_revision"],
                working_tree_state=document["working_tree_state"],
                target_environment=document["target_environment"],
                command=document["command"],
                read_only=document["read_only"],
                fixture_or_cache=document["fixture_or_cache"],
                started_at=document["started_at"],
                finished_at=document["finished_at"],
                exit_code=document["exit_code"],
                recording=document["recording"],
                permission_scope=document["permission_scope"],
                transcript_sha256=document.get("transcript_sha256"),
                approval=document.get("approval"),
                notes=list(document.get("notes") or []),
            )
        except KeyError as exc:
            raise ContractError("MISSING_FIELD",
                                f"capture proof is missing {exc.args[0]!r}") from None
        return proof.validate()

    def verify_recording(self, path) -> str:
        """Check the file on disk is the one this receipt names."""
        actual = sha256_file(Path(path))
        expected = self.recording["sha256"]
        require(actual == expected, "EVIDENCE_SHA_MISMATCH",
                f"recording at {path} has sha256 {actual}, receipt says {expected}")
        return actual
