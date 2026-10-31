"""Adapter for the HyperFrames ``media-use`` skill.

What this module is
-------------------
A version-pinned **adapter**, not a fork and not a copy. The skill lives outside
this repository (discovered at ``~/.agents/skills/media-use`` by default), and
this module is the only ContentOps code that invokes it:

```
node <skill>/scripts/resolve.mjs --type ... --project ... --json
```

The adapter exists to answer three questions the skill cannot answer for us:

1. **May this run at all?** Every network, provider and paid path is closed by
   default. A closed path raises :class:`MediaUseError` with a code, before a
   child process is spawned.
2. **What did it actually produce?** The CLI's JSON is parsed, then the file it
   names is resolved *inside the project directory*, hashed, and recorded in a
   ``contentops.media-import/v1`` receipt. A path outside the project is refused.
3. **What may the bytes be used for?** Catalog images and audio are
   ``LICENSED_EXTERNAL`` (or ``AUDIO`` with no asset kind). They are never
   evidence-capable, regardless of how convincing a stock photo looks. That is
   enforced by the existing :class:`~contentops.media.image_contract.AssetRegistry`,
   not restated here.

Trust boundary
--------------
The skill's documentation and output are **untrusted external input**. The
adapter never lets them choose a ContentOps policy: type support, path
containment, license requirements and evidence capability are decided here. In
particular the skill records no license field, so an import without an explicit
license is refused rather than defaulted to something convenient.

What is deliberately *not* implemented
--------------------------------------
``voice``, ``video``, ``grade``, ``lut`` and ``recipe`` are not routed. Speech
belongs to ContentOps' own provider layer (MiniMax / edge-tts), video generation
is the M4 H3 path, and grading is a deterministic transform with its own
receipts. Routing them here would create a second, weaker provenance path. They
are reported as :data:`CODE_UNSUPPORTED_TYPE`, not silently ignored.

Windows
-------
Every child process goes through :func:`scripts.process_utils.hidden_run`, with
an argument array and no ``shell=True``. The environment is allow-listed, so a
provider key that happens to be exported in the parent shell is not handed to
the skill.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from process_utils import hidden_run  # noqa: E402

from contentops.media.asset_execution import (  # noqa: E402
    IMPORT_RECEIPT_SUFFIX,
    import_fingerprint,
)
from contentops.media.fingerprint import sha256_file  # noqa: E402
from contentops.media.image_contract import (  # noqa: E402
    AssetKind,
    AssetRegistry,
    EvidenceUse,
    register_asset,
)
from contentops.media.media_envelope import (  # noqa: E402
    HUMAN_REVIEW_PENDING,
    TECHNICAL_NOT_RUN,
    MediaAssetEnvelope,
    MediaModality,
)
from contentops.media.media_validation import IMPORT_SCHEMA  # noqa: E402
from contentops.media.transport import write_sidecar  # noqa: E402

__all__ = [
    "CODE_CLI_FAILED",
    "CODE_CROSS_PROJECT_NOT_AUTHORIZED",
    "CODE_GENERATED_NOT_IMPORTABLE",
    "CODE_HASH_MISMATCH",
    "CODE_LICENSE_MISSING",
    "CODE_NEEDS_HUMAN_ACTION",
    "CODE_NETWORK_NOT_AUTHORIZED",
    "CODE_NODE_UNAVAILABLE",
    "CODE_PATH_ESCAPE",
    "CODE_PAID_NOT_AUTHORIZED",
    "CODE_PROVIDER_NOT_AUTHORIZED",
    "CODE_SKILL_UNAVAILABLE",
    "CODE_TIMEOUT",
    "CODE_UNSUPPORTED_TYPE",
    "DEFAULT_SKILL_DIR",
    "SKILL_COMMIT",
    "SUPPORTED_TYPES",
    "UPSTREAM_COMMIT",
    "UPSTREAM_LICENSE",
    "UPSTREAM_REPOSITORY",
    "ImportedMedia",
    "MediaUseAdapter",
    "MediaUseAuthorization",
    "MediaUseCandidate",
    "MediaUseDoctor",
    "MediaUseError",
    "MediaUseProcessResult",
    "MediaUseResolution",
    "MediaUseStatus",
    "MediaUseVerification",
    "redact_text",
]

# --- upstream provenance ---------------------------------------------------
UPSTREAM_REPOSITORY = "https://github.com/heygen-com/hyperframes"
#: Repository HEAD when this adapter was written. Recorded, not fetched: a
#: receipt that re-resolved ``main`` at read time would name a different code
#: than the one that produced the bytes.
UPSTREAM_COMMIT = "5e4f5aefb58a9996ea5920f008184e9789346871"
#: Last commit that touched ``skills/media-use`` at audit time.
SKILL_COMMIT = "f2358315e59731833334c5d881a7fb5543c22a97"
UPSTREAM_LICENSE = "Apache-2.0"

SKILL_NAME = "media-use"
DEFAULT_SKILL_DIR = Path.home() / ".agents" / "skills" / SKILL_NAME
ENV_SKILL_DIR = "CONTENTOPS_MEDIA_USE_SKILL_DIR"
ENV_NODE = "CONTENTOPS_NODE_BINARY"
RESOLVE_RELATIVE = Path("scripts") / "resolve.mjs"
# The official published HyperFrames CLI declares Node >=22. This is a
# necessary prerequisite, not proof that the CLI dependency tree is trusted.
MIN_NODE_MAJOR = 22

#: Types this adapter routes. Everything else is refused with a reason.
SUPPORTED_TYPES: Tuple[str, ...] = ("image", "icon", "logo", "brand", "bgm", "sfx")

#: Why the un-routed types are un-routed. Kept as data so the refusal message
#: and the capability matrix cannot drift apart.
UNSUPPORTED_TYPE_REASONS: Dict[str, str] = {
    "voice": (
        "speech is owned by ContentOps' provider layer (MiniMax / edge-tts). "
        "Routing it through media-use would create a second TTS path with no "
        "billing guard and no pronunciation lexicon."
    ),
    "video": (
        "generated video is the M4 H3 path, which has its own quota, receipt and "
        "evidence rules. media-use video is credit-billed and is not wired here."
    ),
    "grade": (
        "grading is a deterministic local transform with its own receipt schema; "
        "it is not an asset import."
    ),
    "lut": (
        "LUTs are deterministic colour data consumed by the transform layer, not "
        "a media asset with an evidence role."
    ),
    "recipe": (
        "recipes are workflow bundles, not media, and have no place in a media "
        "manifest."
    ),
}

# Refusal codes. Stable strings, because tests and receipts key on them.
CODE_SKILL_UNAVAILABLE = "SKILL_UNAVAILABLE"
CODE_NODE_UNAVAILABLE = "NODE_UNAVAILABLE"
CODE_UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
CODE_PROVIDER_NOT_AUTHORIZED = "PROVIDER_NOT_AUTHORIZED"
CODE_NETWORK_NOT_AUTHORIZED = "NETWORK_NOT_AUTHORIZED"
CODE_PAID_NOT_AUTHORIZED = "PAID_NOT_AUTHORIZED"
CODE_CROSS_PROJECT_NOT_AUTHORIZED = "CROSS_PROJECT_NOT_AUTHORIZED"
CODE_LICENSE_MISSING = "LICENSE_MISSING"
CODE_PATH_ESCAPE = "PATH_ESCAPE"
CODE_HASH_MISMATCH = "HASH_MISMATCH"
CODE_CLI_FAILED = "CLI_FAILED"
CODE_TIMEOUT = "TIMEOUT"
CODE_GENERATED_NOT_IMPORTABLE = "GENERATED_NOT_IMPORTABLE"
CODE_NEEDS_HUMAN_ACTION = "NEEDS_HUMAN_ACTION"

#: Environment variables the child is allowed to see. Provider keys, cookies,
#: proxy credentials and agent tokens are deliberately absent: a closed paid
#: path must not be re-opened by something exported in the parent shell.
_ENV_ALLOWLIST: Tuple[str, ...] = (
    "PATH",
    "PATHEXT",
    "SystemRoot",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
    "USERNAME",
    "LANG",
    "LC_ALL",
    "NODE_PATH",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "ALL_PROXY",
)

_SECRET_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"(?i)([A-Za-z0-9_]*(?:api[_-]?key|token|secret|password)[A-Za-z0-9_]*)\s*[:=]\s*\S+"), r"\1=***REDACTED***"),
    (re.compile(r"(?i)(bearer)\s+[A-Za-z0-9._\-]{8,}"), r"\1 ***REDACTED***"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "***REDACTED***"),
    (re.compile(r"(?i)(heygen[_-]?api[_-]?key)\s+\S+"), r"\1 ***REDACTED***"),
)


def redact_text(value: str) -> str:
    """Remove credential-shaped substrings from child output.

    Best-effort by design: the receipts are public and a provider refusal often
    echoes the header it rejected. This is a backstop, not a substitute for the
    allow-listed environment that keeps the credential out of the child.
    """
    text = value or ""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _version_tuple(value: Optional[str]) -> Optional[Tuple[int, int, int]]:
    if not value:
        return None
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


class MediaUseError(RuntimeError):
    """A refused or failed media-use operation.

    ``code`` is the machine-readable reason. Callers branch on it; the message is
    for a human and is already redacted.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": False,
            "code": self.code,
            "message": redact_text(str(self)),
            "details": _redact_value(self.details),
        }


@dataclass(frozen=True)
class MediaUseAuthorization:
    """What a caller has explicitly allowed this run to do.

    Every field defaults to ``False``. There is no "development mode" that opens
    them together, because the one time that flag ships enabled is the time a
    stock search becomes a charge or another project's asset appears in a video.
    """

    allow_network: bool = False
    allow_paid: bool = False
    #: Required whenever ``allow_paid`` is true. A truthy boolean with no budget
    #: is not authorization; it is a hope.
    paid_budget: Optional[str] = None
    allow_cross_project_reuse: bool = False
    allowed_providers: Tuple[str, ...] = ()

    def require_network(self) -> None:
        if not self.allow_network:
            raise MediaUseError(
                CODE_NETWORK_NOT_AUTHORIZED,
                "this run may use the local project and cache only; network "
                "providers were not authorized. Pass allow_network=True after a "
                "human decision, or keep working offline.",
            )

    def require_paid(self) -> None:
        if not self.allow_paid:
            raise MediaUseError(
                CODE_PAID_NOT_AUTHORIZED,
                "this run may not spend money. Paid generation requires explicit "
                "Founder authorization and a budget, neither of which is present.",
            )
        if not (self.paid_budget or "").strip():
            raise MediaUseError(
                CODE_PAID_NOT_AUTHORIZED,
                "allow_paid=True was supplied without paid_budget. A paid run must "
                "state the ceiling it is authorized to spend.",
            )

    def require_cross_project(self) -> None:
        if not self.allow_cross_project_reuse:
            raise MediaUseError(
                CODE_CROSS_PROJECT_NOT_AUTHORIZED,
                "reuse from the shared cache is cross-project reuse and was not "
                "authorized. A project may use its own assets by default; another "
                "project's material needs an explicit decision.",
            )

    def require_provider(self, provider: str) -> None:
        if provider not in self.allowed_providers:
            raise MediaUseError(
                CODE_PROVIDER_NOT_AUTHORIZED,
                f"provider {provider!r} is not in the authorized provider list "
                f"({', '.join(self.allowed_providers) or 'empty'}). Forcing a "
                f"provider is a routing decision a human must make.",
            )


@dataclass(frozen=True)
class MediaUseStatus:
    skill_dir: Optional[str]
    skill_present: bool
    resolve_present: bool
    node_present: bool
    node_version: Optional[str]
    heygen_present: bool
    ffmpeg_present: bool
    ffprobe_present: bool
    resolve_sha256: Optional[str]
    available: bool
    reasons: Tuple[str, ...] = ()
    upstream_repository: str = UPSTREAM_REPOSITORY
    upstream_commit: str = UPSTREAM_COMMIT
    skill_commit: str = SKILL_COMMIT
    upstream_license: str = UPSTREAM_LICENSE

    def as_dict(self) -> Dict[str, Any]:
        return {
            "skill_dir": self.skill_dir,
            "skill_present": self.skill_present,
            "resolve_present": self.resolve_present,
            "node_present": self.node_present,
            "node_version": self.node_version,
            "heygen_present": self.heygen_present,
            "ffmpeg_present": self.ffmpeg_present,
            "ffprobe_present": self.ffprobe_present,
            "resolve_sha256": self.resolve_sha256,
            "available": self.available,
            "reasons": list(self.reasons),
            "upstream_repository": self.upstream_repository,
            "upstream_provenance": "UNVERIFIED",
            "upstream_commit": self.upstream_commit,
            "skill_commit": self.skill_commit,
            "upstream_license": self.upstream_license,
        }


@dataclass(frozen=True)
class MediaUseProcessResult:
    command: Tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "command": list(self.command),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
        }


@dataclass(frozen=True)
class MediaUseCandidate:
    id: str
    type: str
    scope: str
    description: str
    prompt: Optional[str] = None
    provider: Optional[str] = None
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    sha: Optional[str] = None
    path: Optional[str] = None
    score: int = 0

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "MediaUseCandidate":
        return cls(
            id=str(payload.get("id") or ""),
            type=str(payload.get("type") or ""),
            scope=str(payload.get("scope") or ""),
            description=str(payload.get("description") or ""),
            prompt=payload.get("prompt"),
            provider=payload.get("provider"),
            duration=payload.get("duration"),
            width=payload.get("width"),
            height=payload.get("height"),
            sha=payload.get("sha"),
            path=payload.get("path"),
            score=int(payload.get("score") or 0),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "scope": self.scope,
            "description": self.description,
            "prompt": self.prompt,
            "provider": self.provider,
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "sha": self.sha,
            "path": self.path,
            "score": self.score,
        }


@dataclass(frozen=True)
class MediaUseDoctor:
    ok: bool
    checks: Tuple[Dict[str, Any], ...]
    needs_human_action: Tuple[Dict[str, Any], ...]
    status: MediaUseStatus

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": list(self.checks),
            "needs_human_action": list(self.needs_human_action),
            "status": self.status.as_dict(),
        }


@dataclass(frozen=True)
class MediaUseResolution:
    kind: str
    intent: str
    source: str
    record: Dict[str, Any]
    importable: bool
    cross_project: bool = False
    blocked_code: Optional[str] = None
    blocked_reason: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "intent": self.intent,
            "source": self.source,
            "record": _redact_value(dict(self.record)),
            "importable": self.importable,
            "cross_project": self.cross_project,
            "blocked_code": self.blocked_code,
            "blocked_reason": self.blocked_reason,
        }


@dataclass(frozen=True)
class ImportedMedia:
    """One catalog/adopted file registered with a ContentOps provenance receipt."""

    asset_id: str
    modality: str
    asset_kind: Optional[str]
    path: str
    logical_path: str
    sha256: str
    receipt_path: str
    receipt_ref: str
    license: str
    attribution: str
    source_type: str
    reuse_source: str
    envelope: MediaAssetEnvelope
    cross_project: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "modality": self.modality,
            "asset_kind": self.asset_kind,
            "path": self.path,
            "logical_path": self.logical_path,
            "sha256": self.sha256,
            "receipt_path": self.receipt_path,
            "receipt_ref": self.receipt_ref,
            "license": self.license,
            "attribution": self.attribution,
            "source_type": self.source_type,
            "reuse_source": self.reuse_source,
            "cross_project": self.cross_project,
            "envelope": self.envelope.as_dict(),
        }


@dataclass(frozen=True)
class MediaUseVerification:
    path: str
    exists: bool
    digest_matches: bool
    receipt_present: bool
    schema: Optional[str]
    license: Optional[str]
    failures: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.exists and self.digest_matches and self.receipt_present and not self.failures

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "exists": self.exists,
            "digest_matches": self.digest_matches,
            "receipt_present": self.receipt_present,
            "schema": self.schema,
            "license": self.license,
            "failures": list(self.failures),
        }


class MediaUseAdapter:
    """Thin, fail-closed wrapper around the pinned media-use CLI."""

    def __init__(
        self,
        skill_dir: Optional[Path] = None,
        node: Optional[str] = None,
        *,
        timeout: float = 120.0,
        env: Optional[Mapping[str, str]] = None,
        which: Any = None,
    ) -> None:
        if not (1.0 <= float(timeout) <= 600.0):
            raise ValueError(
                f"timeout must be between 1 and 600 seconds, got {timeout!r}. An "
                f"unbounded wait is how a pipeline hangs instead of reporting."
            )
        self.timeout = float(timeout)
        override = skill_dir or os.environ.get(ENV_SKILL_DIR)
        self.skill_dir = Path(override).expanduser() if override else DEFAULT_SKILL_DIR
        self.node = node or os.environ.get(ENV_NODE) or None
        self._which = which or shutil.which
        self._env_override = dict(env or {})
        self._status: Optional[MediaUseStatus] = None

    # -- discovery ---------------------------------------------------------

    @property
    def resolve_script(self) -> Path:
        return self.skill_dir / RESOLVE_RELATIVE

    def status(self, *, refresh: bool = False) -> MediaUseStatus:
        # Re-evaluate on each call; cached success must never hide a later change.
        reasons: List[str] = [
            "DEPENDENCY_UNVERIFIED: the launcher and complete CLI runtime are not verified"
        ]
        skill_present = (self.skill_dir / "SKILL.md").is_file()
        resolve_present = self.resolve_script.is_file()
        if not skill_present:
            reasons.append(
                f"{self.skill_dir} does not contain SKILL.md; the media-use skill "
                f"is not installed there"
            )
        elif not resolve_present:
            reasons.append(f"{self.resolve_script} is missing")

        node = self.node or self._which("node")
        node_present = bool(node)
        node_ok = node_present
        node_version: Optional[str] = None
        if not node_present:
            reasons.append("node is not on PATH; resolve.mjs cannot run")
        else:
            try:
                proc = hidden_run(
                    [node, "--version"], timeout=10, check=False, env=self._child_env()
                )
                node_version = (proc.stdout or "").strip() or None
            except Exception:
                node_version = None
            parsed = _version_tuple(node_version)
            if parsed is None or parsed[0] < MIN_NODE_MAJOR:
                reasons.append(
                    f"node {node_version or 'unknown'} does not satisfy the "
                    f"media-use floor v{MIN_NODE_MAJOR}.0.0"
                )
                node_ok = False

        resolve_sha256 = None
        if resolve_present:
            try:
                resolve_sha256 = sha256_file(self.resolve_script)
            except OSError:
                reasons.append(f"{self.resolve_script} could not be read for hashing")

        self._status = MediaUseStatus(
            skill_dir=str(self.skill_dir),
            skill_present=skill_present,
            resolve_present=resolve_present,
            node_present=node_present,
            node_version=node_version,
            heygen_present=bool(self._which("heygen")),
            ffmpeg_present=bool(self._which("ffmpeg")),
            ffprobe_present=bool(self._which("ffprobe")),
            resolve_sha256=resolve_sha256,
            available=False,
            reasons=tuple(reasons),
        )
        return self._status

    def require_available(self) -> MediaUseStatus:
        status = self.status()
        if status.available:
            return status
        if not status.node_present:
            code = CODE_NODE_UNAVAILABLE
        elif not status.skill_present or not status.resolve_present:
            code = CODE_SKILL_UNAVAILABLE
        else:
            code = "DEPENDENCY_UNVERIFIED"
        raise MediaUseError(
            code,
            "media-use is unavailable: " + "; ".join(status.reasons or ["unknown reason"]),
            details=status.as_dict(),
        )

    # -- child process -----------------------------------------------------

    @staticmethod
    def _sandbox_home(project_dir: Path) -> Path:
        """A project-local HOME, so the skill's global cache cannot leak across projects.

        ``media-use`` keeps a shared cache at ``~/.media``. With the real HOME a
        resolve may silently reuse another project's asset, and an ingest writes
        outside the repository. Pointing HOME/USERPROFILE at a directory inside
        ``<project>/.media`` makes the cache project-scoped and contains the side
        effect. Cross-project reuse is then only reachable by explicitly opting
        back into the real HOME.
        """
        home = Path(project_dir).expanduser().resolve() / ".media" / ".home"
        home.mkdir(parents=True, exist_ok=True)
        return home

    def _child_env(self, *, home: Optional[Path] = None) -> Dict[str, str]:
        env = {
            key: os.environ[key]
            for key in _ENV_ALLOWLIST
            if key in os.environ and os.environ[key]
        }
        env.update({k: v for k, v in self._env_override.items() if v})
        if home is not None:
            # Both spellings, because Node's os.homedir() reads USERPROFILE on
            # Windows and HOME elsewhere.
            env["HOME"] = str(home)
            env["USERPROFILE"] = str(home)
        return env

    @staticmethod
    def _require_trusted_runtime() -> None:
        # Launcher integrity alone cannot verify npx, Bun or the CLI dependency tree.
        raise MediaUseError(
            "DEPENDENCY_UNVERIFIED",
            "media-use execution is blocked until the complete launcher and CLI "
            "dependency tree can be verified without implicit installation",
        )

    def _run(
        self,
        args: Sequence[str],
        *,
        cwd: Optional[Path] = None,
        timeout: Optional[float] = None,
        home: Optional[Path] = None,
    ) -> MediaUseProcessResult:
        if not (self.skill_dir / "SKILL.md").is_file() or not self.resolve_script.is_file():
            raise MediaUseError(CODE_SKILL_UNAVAILABLE, "media-use skill or launcher is missing")
        self._require_trusted_runtime()
        status = self.require_available()
        node = self.node or self._which("node")
        if not node:
            raise MediaUseError(CODE_NODE_UNAVAILABLE, "node disappeared after status")
        command = [str(node), str(self.resolve_script), *[str(arg) for arg in args]]
        try:
            proc = hidden_run(
                command,
                cwd=str(cwd) if cwd else None,
                timeout=timeout or self.timeout,
                check=False,
                env=self._child_env(home=home),
            )
        except Exception as exc:  # subprocess.TimeoutExpired and OSError both land here
            reason = "timed out" if "Timeout" in type(exc).__name__ else "could not start"
            raise MediaUseError(
                CODE_TIMEOUT if "Timeout" in type(exc).__name__ else CODE_NODE_UNAVAILABLE,
                f"media-use CLI {reason} after {timeout or self.timeout}s: {exc}",
                details={"command": command},
            ) from exc
        return MediaUseProcessResult(
            command=tuple(command),
            returncode=int(proc.returncode),
            stdout=redact_text(proc.stdout or ""),
            stderr=redact_text(proc.stderr or ""),
            timed_out=False,
        )

    def _run_json(
        self,
        args: Sequence[str],
        *,
        cwd: Optional[Path] = None,
        timeout: Optional[float] = None,
        home: Optional[Path] = None,
        allow_failure_payload: bool = False,
    ) -> Dict[str, Any]:
        result = self._run(args, cwd=cwd, timeout=timeout, home=home)
        payload: Any = None
        if result.stdout.strip():
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError:
                payload = None
        if not isinstance(payload, dict):
            raise MediaUseError(
                CODE_CLI_FAILED,
                f"media-use CLI did not return a JSON object (exit {result.returncode})",
                details=result.as_dict(),
            )
        if result.returncode != 0 and not allow_failure_payload:
            message = payload.get("error") or result.stderr.strip() or "no error text"
            raise MediaUseError(
                CODE_CLI_FAILED,
                f"media-use CLI failed (exit {result.returncode}): {message}",
                details=result.as_dict(),
            )
        if payload.get("ok") is False and not allow_failure_payload:
            raise MediaUseError(
                CODE_CLI_FAILED,
                f"media-use CLI reported failure: {payload.get('error') or 'no error text'}",
                details=result.as_dict(),
            )
        return payload

    # -- read-only operations ---------------------------------------------

    def doctor(self) -> MediaUseDoctor:
        """Probe local dependencies. Read-only, but it may touch the network.

        The CLI's own doctor exits non-zero when a check fails (``heygen`` is
        absent here), yet still prints the full JSON. That is a *diagnosis*, not a
        failed operation, so the payload is parsed either way and the failed
        checks are surfaced as human actions.
        """
        self.require_available()
        payload = self._run_json(
            ["--doctor", "--json"],
            timeout=min(self.timeout, 120.0),
            allow_failure_payload=True,
        )
        checks = tuple(
            dict(check) for check in (payload.get("checks") or []) if isinstance(check, dict)
        )
        human = tuple(check for check in checks if not check.get("ok") and check.get("fix"))
        return MediaUseDoctor(
            ok=bool(payload.get("ok")),
            checks=checks,
            needs_human_action=human,
            status=self.status(),
        )

    def candidates(
        self,
        kind: str,
        *,
        project_dir: Path,
        intent: str = "",
        consult_global_cache: bool = False,
    ) -> List[MediaUseCandidate]:
        """List reusable assets. No download, no provider call, no mutation.

        Global-cache rows are omitted unless ``consult_global_cache`` is true.
        They are another project's material; listing them is not harmful, but
        returning them from a call that later imports one is how unapproved
        cross-project reuse happens.
        """
        self._require_supported(kind)
        args = [
            "--type",
            kind,
            "--candidates",
            "--project",
            str(Path(project_dir)),
            "--json",
            "--local-only",
        ]
        if intent.strip():
            args.extend(["--intent", intent])
        # When global rows are not wanted, give the child a project-local HOME so
        # the shared ~/.media cache is not even visible. The filter below stays as
        # a second guard for a CLI that reports a global scope anyway.
        home = None if consult_global_cache else self._sandbox_home(project_dir)
        payload = self._run_json(args, home=home)
        candidates: List[MediaUseCandidate] = []
        for item in payload.get("candidates") or []:
            if not isinstance(item, dict):
                continue
            # The CLI treats icon and image as interchangeable for entity hits.
            # A caller asking for `image` must not receive `icon` rows silently.
            if item.get("type") != kind:
                continue
            if item.get("scope") == "global" and not consult_global_cache:
                continue
            candidates.append(MediaUseCandidate.from_payload(item))
        return candidates

    # -- resolve / adopt / ingest -----------------------------------------

    def resolve(
        self,
        kind: str,
        intent: str,
        *,
        project_dir: Path,
        authorization: Optional[MediaUseAuthorization] = None,
        provider: Optional[str] = None,
    ) -> MediaUseResolution:
        """Resolve a need, reusing project material before touching a provider.

        Precedence, and the reason for it:

        1. an exact-type **project** candidate — already inside this project;
        2. a **shared-cache** hit, only with ``allow_cross_project_reuse``;
        3. a **network** search/generation, only with ``allow_network``.

        With no authorization the call returns a structured
        ``NEEDS_HUMAN_ACTION`` result rather than spawning a process that would
        either fail confusingly or reach a provider.
        """
        self._require_supported(kind)
        auth = authorization or MediaUseAuthorization()
        # The upstream resolver can fall back from retrieval to generation and
        # provides no verified enforceable spending ceiling. An authorization
        # flag or a budget string cannot make that safe. Refuse before invoking
        # even the candidate subprocess; callers can request offline reuse instead.
        if auth.allow_network or auth.allow_paid:
            raise MediaUseError(
                CODE_PAID_NOT_AUTHORIZED,
                "network resolution is blocked: upstream cost classification and "
                "a binding budget limit have not been verified",
            )
        if provider:
            auth.require_provider(provider)

        project_candidates = self.candidates(
            kind, project_dir=project_dir, intent=intent, consult_global_cache=False
        )
        if project_candidates:
            top = project_candidates[0]
            record = dict(top.as_dict())
            record["_source"] = "project-candidate"
            return MediaUseResolution(
                kind=kind,
                intent=intent,
                source="project-candidate",
                record=record,
                importable=True,
            )

        if not auth.allow_network:
            # Offline. The child gets a project-local HOME, so the shared ~/.media
            # cache is not visible unless cross-project reuse was authorized.
            # ``--local-only`` still allows the skill's bundled providers (for
            # example bundled SFX) and the project's own manifest to answer the
            # need without a socket.
            home = (
                None
                if auth.allow_cross_project_reuse
                else self._sandbox_home(project_dir)
            )
            args = [
                "--type",
                kind,
                "--intent",
                intent,
                "--project",
                str(Path(project_dir)),
                "--json",
                "--local-only",
            ]
            if provider:
                args.extend(["--provider", provider])
            try:
                payload = self._run_json(args, home=home)
            except MediaUseError as exc:
                if exc.code != CODE_CLI_FAILED:
                    raise
                raise MediaUseError(
                    CODE_NEEDS_HUMAN_ACTION,
                    f"no offline {kind} source could satisfy {intent!r}. Network "
                    f"search was not authorized, so nothing was downloaded or "
                    f"generated. Add an asset to the project, or authorize a "
                    f"network lookup.",
                    details={"kind": kind, "intent": intent, "cli": exc.details},
                ) from exc
            source = str(payload.get("_source") or "")
            cross_project = source in {"reused", "reused-explicit", "cached"} or (
                payload.get("scope") == "global"
            )
            if cross_project and not auth.allow_cross_project_reuse:
                raise MediaUseError(
                    CODE_CROSS_PROJECT_NOT_AUTHORIZED,
                    "media-use returned a shared-cache asset, which is "
                    "cross-project reuse. It was not authorized for this run.",
                    details={"kind": kind, "source": source},
                )
            if source == "generated":
                return self._generated_resolution(kind, intent, payload)
            return MediaUseResolution(
                kind=kind,
                intent=intent,
                source=source or "resolved-local",
                record=payload,
                importable=True,
                cross_project=cross_project,
            )

        auth.require_network()
        args = [
            "--type",
            kind,
            "--intent",
            intent,
            "--project",
            str(Path(project_dir)),
            "--json",
        ]
        if provider:
            args.extend(["--provider", provider])
        payload = self._run_json(args)
        source = str(payload.get("_source") or "")
        cross_project = source in {"reused", "reused-explicit", "cached"}
        if cross_project and not auth.allow_cross_project_reuse:
            raise MediaUseError(
                CODE_CROSS_PROJECT_NOT_AUTHORIZED,
                "media-use returned a shared-cache asset, which is cross-project "
                "reuse. It was not authorized for this run.",
                details={"kind": kind, "source": source},
            )
        if source == "generated":
            return self._generated_resolution(kind, intent, payload)
        return MediaUseResolution(
            kind=kind,
            intent=intent,
            source=source or "resolved",
            record=payload,
            importable=True,
            cross_project=cross_project,
        )

    @staticmethod
    def _generated_resolution(
        kind: str, intent: str, payload: Dict[str, Any]
    ) -> MediaUseResolution:
        return MediaUseResolution(
            kind=kind,
            intent=intent,
            source="generated",
            record=payload,
            importable=False,
            blocked_code=CODE_GENERATED_NOT_IMPORTABLE,
            blocked_reason=(
                "media-use generated these bytes. A generated asset is not a "
                "licensed external asset, and importing it as one would misstate "
                "its origin."
            ),
        )

    def adopt(self, *, project_dir: Path) -> List[Dict[str, Any]]:
        """Register files already under ``<project>/assets`` in the skill manifest."""
        payload = self._run_json(
            ["--adopt", "--project", str(Path(project_dir)), "--json"],
            home=self._sandbox_home(project_dir),
        )
        return [dict(item) for item in (payload.get("assets") or []) if isinstance(item, dict)]

    def ingest(
        self,
        kind: str,
        source: Path,
        *,
        project_dir: Path,
        license: str,
        attribution: str = "",
    ) -> Dict[str, Any]:
        """Freeze a local file into the project through the skill.

        Only a local path is accepted here. A URL would need
        ``allow_network`` and would make the receipt's ``source_uri`` a remote
        reference this adapter cannot verify; the URL path exists in the CLI but
        is not opened by this adapter in v1.

        The license is required **before** the file is copied. Importing first and
        asking later is how an unlicensed asset ends up in a render.
        """
        self._require_supported(kind)
        self._require_license(license)
        source_path = Path(source).expanduser()
        if not source_path.is_file():
            raise MediaUseError(
                CODE_CLI_FAILED,
                f"ingest source is not a local file: {source_path}",
                details={"source": str(source_path)},
            )
        if source_path.stat().st_size == 0:
            raise MediaUseError(
                CODE_CLI_FAILED,
                f"refusing to ingest a 0-byte file: {source_path}",
                details={"source": str(source_path)},
            )
        payload = self._run_json(
            [
                "--type",
                kind,
                "--from",
                str(source_path.resolve()),
                "--project",
                str(Path(project_dir)),
                "--json",
            ],
            # Contained HOME: the skill's best-effort global cache write lands
            # inside this project, not in the operator's shared cache.
            home=self._sandbox_home(project_dir),
        )
        return payload

    # -- provenance --------------------------------------------------------

    def import_record(
        self,
        record: Mapping[str, Any],
        *,
        project_dir: Path,
        kind: str,
        license: str,
        attribution: str = "",
        role: str = "visual_support",
        placement_id: Optional[str] = None,
        registry: Optional[AssetRegistry] = None,
        asset_id_prefix: str = "media-use",
        cross_project: bool = False,
    ) -> ImportedMedia:
        """Turn one media-use record into a registered ContentOps asset.

        The file, not the record, is the source of truth: its path is resolved
        inside the project, its bytes are hashed, and that digest is what the
        receipt carries. A record that names a path outside the project is
        refused.
        """
        self._require_supported(kind)
        self._require_license(license)
        record_kind = record.get("type")
        if record_kind and record_kind != kind:
            raise MediaUseError(CODE_CLI_FAILED, "record type does not match requested kind")
        if record.get("generated") is True or record.get("source") == "generated" or record.get("_source") == "generated":
            raise MediaUseError(CODE_GENERATED_NOT_IMPORTABLE, "generated material cannot be imported as licensed external media")
        project_root = Path(project_dir).expanduser().resolve()
        relative = record.get("path")
        if not isinstance(relative, str) or not relative.strip():
            raise MediaUseError(
                CODE_CLI_FAILED,
                "media-use record carries no path; there is nothing to import",
                details={"record": dict(record)},
            )
        full_path = self._contained_path(project_root, relative)
        if not full_path.is_file():
            raise MediaUseError(
                CODE_CLI_FAILED,
                f"media-use record names a file that does not exist: {relative}",
                details={"record": dict(record)},
            )

        digest = sha256_file(full_path)
        declared_digest = record.get("sha256") or record.get("sha")
        if declared_digest and (not isinstance(declared_digest, str) or declared_digest.lower() != digest):
            raise MediaUseError(CODE_HASH_MISMATCH, "recorded digest does not match the local file")
        asset_id = f"{asset_id_prefix}-{kind}-{digest[:12]}"
        modality, asset_kind = self._modality_for(kind)
        # A project under this repository must still read as project:// so the
        # manifest is portable between checkouts and never carries a drive
        # letter.
        logical_path = "project://" + full_path.relative_to(project_root).as_posix()

        source_type = self._source_type(record)
        reuse_source = str(record.get("_source") or record.get("source") or source_type)
        source_uri = self._safe_source_uri(record, project_root)
        receipt_path = full_path.with_name(full_path.name + IMPORT_RECEIPT_SUFFIX)
        receipt_ref = receipt_path.name
        fingerprint = import_fingerprint(kind, digest)

        receipt: Dict[str, Any] = {
            "schema": IMPORT_SCHEMA,
            "record_type": "media_import",
            "provider": "hyperframes_media_use",
            "product": "hyperframes",
            "upstream_repository": UPSTREAM_REPOSITORY,
            "upstream_commit": None,
            "skill_commit": None,
            "upstream_provenance": "UNVERIFIED",
            "expected_upstream_commit": UPSTREAM_COMMIT,
            "expected_skill_commit": SKILL_COMMIT,
            "upstream_license": UPSTREAM_LICENSE,
            "transport": "media_use_resolve",
            "transport_version": "1",
            "asset_id": asset_id,
            "modality": modality,
            "imported_kind": asset_kind or kind,
            "media_use_id": record.get("id"),
            "media_use_type": record.get("type") or kind,
            "source_type": source_type,
            "source_uri": source_uri,
            "original_asset_path": self._safe_original_path(record, project_root),
            "project_relative_path": full_path.relative_to(project_root).as_posix(),
            "output_sha256": digest,
            "bytes": full_path.stat().st_size,
            "fingerprint": fingerprint,
            "license": license.strip(),
            "attribution": attribution.strip(),
            "generated": False,
            "evidence_capable": False,
            "reuse_source": reuse_source,
            "cross_project_reuse": bool(cross_project),
            "provider_call": False,
            "production_ready": False,
            "human_review": HUMAN_REVIEW_PENDING,
            "note": (
                "External material imported from a local record; upstream "
                "execution provenance has not been verified. It supports a video "
                "evidence_capable is false by construction. No provider was called "
                "by this import."
            ),
        }
        write_sidecar(receipt_path, receipt)

        if registry is not None and modality in MediaModality.VISUAL:
            register_asset(
                registry,
                asset_id=asset_id,
                kind=AssetKind.LICENSED_EXTERNAL,
                path=str(full_path),
                evidence_use=EvidenceUse.VISUAL_SUPPORT,
                sha256=digest,
                receipt_ref=receipt_ref,
                notes={"role": role, "license": license.strip()},
            )

        envelope = MediaAssetEnvelope(
            asset_id=asset_id,
            modality=modality,
            placement_id=placement_id,
            path=logical_path,
            sha256=digest,
            receipt_ref=receipt_ref,
            fingerprint=fingerprint,
            asset_kind=asset_kind,
            generated=False,
            evidence_capable=False,
            evidence_use=EvidenceUse.VISUAL_SUPPORT,
            claim_refs=[],
            technical_status=TECHNICAL_NOT_RUN,
            human_review=HUMAN_REVIEW_PENDING,
            production_ready=False,
        )
        return ImportedMedia(
            asset_id=asset_id,
            modality=modality,
            asset_kind=asset_kind,
            path=str(full_path),
            logical_path=logical_path,
            sha256=digest,
            receipt_path=str(receipt_path),
            receipt_ref=receipt_ref,
            license=license.strip(),
            attribution=attribution.strip(),
            source_type=source_type,
            reuse_source=reuse_source,
            envelope=envelope,
            cross_project=cross_project,
        )

    def verify(
        self,
        *,
        project_dir: Path,
        relative_path: str,
        expected_sha256: Optional[str] = None,
    ) -> MediaUseVerification:
        """Check a recorded file still exists, hashes the same, and keeps a receipt."""
        project_root = Path(project_dir).expanduser().resolve()
        full_path = self._contained_path(project_root, relative_path)
        failures: List[str] = []
        exists = full_path.is_file()
        digest_matches = False
        receipt_present = False
        schema: Optional[str] = None
        license: Optional[str] = None
        if exists:
            observed = sha256_file(full_path)
            receipt_path = full_path.with_name(full_path.name + IMPORT_RECEIPT_SUFFIX)
            receipt_present = receipt_path.is_file()
            recorded: Optional[str] = None
            if receipt_present:
                try:
                    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    failures.append(f"receipt is unreadable: {exc}")
                    payload = {}
                if isinstance(payload, dict):
                    schema = payload.get("schema")
                    license = payload.get("license")
                    value = payload.get("output_sha256")
                    recorded = value if isinstance(value, str) and value.strip() else None
                    if schema != IMPORT_SCHEMA:
                        failures.append(
                            f"receipt schema {schema!r} is not {IMPORT_SCHEMA!r}"
                        )
                    if not (license or "").strip():
                        failures.append("receipt carries no license")
            else:
                failures.append("receipt sidecar is missing")

            # The receipt's own digest is the default expectation. Without it
            # "verify" would only ever confirm that *some* file exists at the
            # path, which is the failure a receipt is supposed to prevent.
            expected = expected_sha256 or recorded
            if not expected:
                failures.append(
                    "receipt records no output_sha256 and no expected digest was "
                    "supplied; there is nothing to verify against"
                )
            else:
                digest_matches = observed == expected
                if not digest_matches:
                    failures.append(
                        f"expected sha256 {expected} but observed {observed}"
                    )
        else:
            failures.append(f"asset file does not exist: {full_path}")
        return MediaUseVerification(
            path=str(full_path),
            exists=exists,
            digest_matches=digest_matches,
            receipt_present=receipt_present,
            schema=schema,
            license=license,
            failures=tuple(failures),
        )

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _modality_for(kind: str) -> Tuple[str, Optional[str]]:
        if kind in ("image", "icon", "logo", "brand"):
            return MediaModality.IMAGE, AssetKind.LICENSED_EXTERNAL
        if kind in ("bgm", "sfx"):
            return MediaModality.AUDIO, None
        raise MediaUseError(
            CODE_UNSUPPORTED_TYPE,
            f"{kind!r} has no ContentOps modality mapping. "
            + UNSUPPORTED_TYPE_REASONS.get(kind, ""),
        )

    @staticmethod
    def _require_supported(kind: str) -> None:
        if kind in SUPPORTED_TYPES:
            return
        reason = UNSUPPORTED_TYPE_REASONS.get(kind)
        if reason:
            raise MediaUseError(CODE_UNSUPPORTED_TYPE, f"{kind!r} is not routed: {reason}")
        raise MediaUseError(
            CODE_UNSUPPORTED_TYPE,
            f"unknown media-use type {kind!r}; supported: {', '.join(SUPPORTED_TYPES)}",
        )

    @staticmethod
    def _require_license(license: str) -> None:
        if not (license or "").strip():
            raise MediaUseError(
                CODE_LICENSE_MISSING,
                "this import has no license. media-use does not record one, so the "
                "caller must state it explicitly. An unlicensed asset is refused "
                "rather than defaulted to something convenient.",
            )

    @staticmethod
    def _contained_path(project_root: Path, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or relative.startswith(("\\\\", "//")):
            raise MediaUseError(
                CODE_PATH_ESCAPE,
                f"media-use named an absolute path ({relative!r}); assets must be "
                f"project-relative",
            )
        if ".." in candidate.parts:
            raise MediaUseError(
                CODE_PATH_ESCAPE,
                f"media-use named a path containing '..' ({relative!r})",
            )
        full = (project_root / candidate).resolve()
        if full != project_root and project_root not in full.parents:
            raise MediaUseError(
                CODE_PATH_ESCAPE,
                f"{relative!r} resolves outside the project directory",
            )
        return full

    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parents[3]

    @staticmethod
    def _source_type(record: Mapping[str, Any]) -> str:
        source = str(record.get("source") or "")
        if source == "existing":
            return "project_existing"
        if source == "ingested":
            return "local_file"
        if record.get("scope") == "project" or record.get("_source") == "project-candidate":
            return "project_existing"
        if record.get("_source") in {"reused", "reused-explicit", "cached"} or record.get(
            "scope"
        ) == "global":
            return "shared_cache"
        if str(record.get("provider") or "").startswith("heygen"):
            return "catalog"
        return source or "media_use_record"

    @staticmethod
    def _safe_source_uri(record: Mapping[str, Any], project_root: Path) -> Optional[str]:
        raw = None
        provenance = record.get("provenance")
        if isinstance(provenance, dict):
            raw = provenance.get("from")
        if not raw:
            return None
        text = str(raw)
        if text.lower().startswith(("http://", "https://")):
            parts = urlsplit(text)
            # A signed catalog URL carries access in its query string. Keep the
            # reference, drop the capability.
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        try:
            path = Path(text).expanduser().resolve()
        except (OSError, ValueError):
            return None
        try:
            return path.relative_to(project_root).as_posix()
        except ValueError:
            # Outside the project: keep only the basename, so a receipt does not
            # publish a machine-local path.
            return path.name

    @staticmethod
    def _safe_original_path(record: Mapping[str, Any], project_root: Path) -> Optional[str]:
        raw = record.get("path")
        if not isinstance(raw, str) or not raw.strip():
            return None
        candidate = Path(raw)
        if candidate.is_absolute():
            return candidate.name
        return candidate.as_posix()
