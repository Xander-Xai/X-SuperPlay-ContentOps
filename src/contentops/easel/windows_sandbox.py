"""Build a review-only Windows AppContainer specification; never launch it.

The experimental SBOX layout is pinned to Microsoft MXC commit
c47ab4f1db7215ca7305ba32a0996ea243806b76, BaseContainerSpecification.fbs
SHA-256 e1e9ae9217638ee9f702ec1742c560952e3aad30afd41cd12f5f6737c3290059.
Creating a specification does not prove that Windows enforces it or authorize
running an Agent. No ACLs, profiles, processes, or network settings are changed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import struct
import threading
import uuid
from pathlib import Path
from subprocess import list2cmdline
from typing import Any

from .agent_sandbox import SandboxPlanError, _ordinary
from .path_safety import is_linklike

SCHEMA_SOURCE_COMMIT = "c47ab4f1db7215ca7305ba32a0996ea243806b76"
SCHEMA_SOURCE_SHA256 = "e1e9ae9217638ee9f702ec1742c560952e3aad30afd41cd12f5f6737c3290059"
_REVIEW_LOCK = threading.Lock()


def review_windows_task(*, repo_root: Path, account: str, project_slug: str,
                        run_id: str, runtime_project: str, package_name: str,
                        write_receipt: bool = False) -> dict[str, Any]:
    """Build a plan summary; optionally write a project receipt, never start an Agent."""
    if not _REVIEW_LOCK.acquire(blocking=False):
        raise SandboxPlanError("another Windows sandbox review is still running")
    try:
        return _review_windows_task(repo_root=repo_root, account=account, project_slug=project_slug,
                                    run_id=run_id, runtime_project=runtime_project,
                                    package_name=package_name, write_receipt=write_receipt)
    finally:
        _REVIEW_LOCK.release()


def _review_windows_task(*, repo_root: Path, account: str, project_slug: str,
                         run_id: str, runtime_project: str, package_name: str,
                         write_receipt: bool) -> dict[str, Any]:
    from .agent_workspace import read_agent_workspace
    from .offline_task import OfflineTaskError, _ensure_child_dir, _project_file, _safe_project

    if not isinstance(package_name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", package_name):
        raise SandboxPlanError("invalid package slug")
    repo = Path(repo_root).resolve(strict=True)
    project, _ = _safe_project(repo, project_slug)
    package_project, _ = _safe_project(repo, runtime_project)
    state = read_agent_workspace(repo_root=repo, account=account, project_slug=project_slug, run_id=run_id)
    if state.get("input_state") != "CURRENT" or state.get("preparation") != "PREPARED":
        raise SandboxPlanError("workspace is stale, unsafe, or cancelled")
    relative = f"work/easel-windows-runtime/{package_name}"
    try:
        manifest_path = _project_file(package_project, relative + ".json")
    except OfflineTaskError as exc:
        if exc.code == "PROJECT_INPUT_MISSING":
            raise SandboxPlanError("runtime manifest is missing") from None
        raise
    with manifest_path.open("rb") as stream:
        raw = stream.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        raise SandboxPlanError("runtime manifest is too large")
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise SandboxPlanError("runtime manifest is unreadable") from None
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != "contentops.easel-windows-runtime-package/v1"
            or manifest.get("package") != relative or not isinstance(manifest.get("files"), dict)):
        raise SandboxPlanError("runtime manifest is invalid")
    plan = build_windows_sandbox_spec(
        workspace=project / "work" / "easel-agent-workspaces" / run_id,
        runtime=package_project / relative, runtime_files=manifest["files"],
        runtime_base=package_project / "work" / "easel-windows-runtime")
    from .windows_process import WindowsProcessError, review_windows_candidate
    try:
        launch_review = review_windows_candidate(plan)
    except WindowsProcessError as exc:
        raise SandboxPlanError("sandbox launch fields are invalid") from exc
    current = read_agent_workspace(repo_root=repo, account=account, project_slug=project_slug, run_id=run_id)
    if current.get("input_state") != "CURRENT" or current.get("preparation") != "PREPARED":
        raise SandboxPlanError("workspace changed or was cancelled during review")
    manifest_path = _project_file(package_project, relative + ".json")
    with manifest_path.open("rb") as stream:
        if stream.read(16 * 1024 * 1024 + 1) != raw:
            raise SandboxPlanError("runtime manifest changed during review")
    result = {"schema": "contentops.easel-windows-sandbox-review/v1", "run_id": run_id,
            "project": project_slug, "account": account, "runtime_project": runtime_project,
            "package": package_name, "manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "launch_fields": launch_review["status"],
            "spec_sha256": plan["spec_sha256"], "candidate_argv_sha256": plan["candidate_argv_sha256"],
            "environment_block_sha256": plan["environment_block_sha256"],
            "openclaw_version": plan["openclaw_version"], "status": "REVIEW_ONLY",
            "execution_route": plan["execution_route"], "gateway_route": plan["gateway_route"],
            "isolation": "NOT_VERIFIED", "execution": "NOT_AUTHORIZED",
            "production_ready": False, "publish_authorized": False}
    if write_receipt:
        receipts = _ensure_child_dir(project, "receipts")
        receipt_path = receipts / f"easel-windows-review-{uuid.uuid4()}.json"
        with receipt_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        result["receipt"] = receipt_path.relative_to(project).as_posix()
    return result


def read_windows_review(*, repo_root: Path, account: str, project_slug: str,
                        review_id: str) -> dict[str, Any]:
    """Read one historical, project-bound review without claiming freshness."""
    from .offline_task import OfflineTaskError, _project_file, _require_project_account, _safe_project

    try:
        if not isinstance(review_id, str) or str(uuid.UUID(review_id)) != review_id:
            raise ValueError("invalid review ID")
    except ValueError:
        raise OfflineTaskError("TASK_ID_INVALID", "review ID must be a canonical UUID") from None
    repo = Path(repo_root).resolve(strict=True)
    project, _ = _safe_project(repo, project_slug)
    _require_project_account(project, account)
    path = _project_file(project, f"receipts/easel-windows-review-{review_id}.json")
    try:
        if path.stat().st_size > 65536:
            raise ValueError("receipt too large")
        value = json.loads(path.read_text(encoding="utf-8"))
        hashes = ("manifest_sha256", "spec_sha256", "candidate_argv_sha256", "environment_block_sha256")
        if (not isinstance(value, dict) or value.get("schema") != "contentops.easel-windows-sandbox-review/v1"
                or value.get("account") != account or value.get("project") != project_slug
                or value.get("status") != "REVIEW_ONLY" or value.get("isolation") != "NOT_VERIFIED"
                or value.get("execution") != "NOT_AUTHORIZED" or value.get("production_ready") is not False
                or value.get("publish_authorized") is not False
                or value.get("execution_route", "NOT_RECORDED") not in {"NOT_RECORDED", "EMBEDDED_DIRECT_ONLY"}
                or value.get("gateway_route", "NOT_RECORDED") not in {"NOT_RECORDED", "NOT_IMPLEMENTED"}
                or value.get("launch_fields", "NOT_RECORDED") not in {"NOT_RECORDED", "LAUNCH_FIELDS_REVIEWED"}
                or any(not isinstance(value.get(k), str) or not re.fullmatch(r"[0-9a-f]{64}", value[k]) for k in hashes)
                or not isinstance(value.get("runtime_project"), str)
                or not re.fullmatch(r"(?:_local/)?[a-z0-9][a-z0-9-]{0,79}", value["runtime_project"])
                or not isinstance(value.get("package"), str)
                or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", value["package"])
                or not isinstance(value.get("openclaw_version"), str)
                or not re.fullmatch(r"[0-9A-Za-z.+-]{1,80}", value["openclaw_version"])
                or not isinstance(value.get("run_id"), str)
                or str(uuid.UUID(value.get("run_id", ""))) != value["run_id"]):
            raise ValueError("receipt binding invalid")
    except (OSError, UnicodeError, TypeError, ValueError, KeyError):
        raise OfflineTaskError("TASK_RECEIPT_INVALID", "Windows review receipt is invalid", 409) from None
    keys = ("schema", "run_id", "project", "account", "runtime_project", "package", *hashes,
            "openclaw_version", "status", "isolation", "execution", "production_ready", "publish_authorized")
    return {**{key: value[key] for key in keys},
            "launch_fields": value.get("launch_fields", "NOT_RECORDED"),
            "execution_route": value.get("execution_route", "NOT_RECORDED"),
            "gateway_route": value.get("gateway_route", "NOT_RECORDED"),
            "review_id": review_id, "current_state": "NOT_CHECKED"}


def list_windows_reviews(*, repo_root: Path, account: str, project_slug: str) -> dict[str, Any]:
    """List up to 50 review receipts; reading one checks its project binding."""
    from .offline_task import OfflineTaskError, _linklike, _require_project_account, _safe_project

    repo = Path(repo_root).resolve(strict=True)
    project, _ = _safe_project(repo, project_slug)
    _require_project_account(project, account)
    receipts = project / "receipts"
    if _linklike(receipts):
        raise OfflineTaskError("PROJECT_UNSAFE", "receipts directory is linked", 403)
    if not receipts.exists():
        return {"reviews": [], "unavailable_count": 0}
    if not receipts.is_dir() or receipts.resolve(strict=True).parent != project:
        raise OfflineTaskError("PROJECT_UNSAFE", "receipts directory is unsafe", 403)
    candidates = []
    for path in receipts.glob("easel-windows-review-*.json"):
        review_id = path.name.removeprefix("easel-windows-review-").removesuffix(".json")
        try:
            if str(uuid.UUID(review_id)) == review_id and not _linklike(path) and path.is_file():
                candidates.append((path.stat().st_mtime_ns, review_id))
        except (OSError, ValueError):
            continue
    rows = []
    unavailable = 0
    for _, review_id in sorted(candidates, reverse=True)[:50]:
        try:
            value = read_windows_review(repo_root=repo, account=account, project_slug=project_slug, review_id=review_id)
            rows.append({"review_id": review_id, "run_id": value["run_id"]})
        except (OfflineTaskError, OSError):
            unavailable += 1
    return {"reviews": rows, "unavailable_count": unavailable}


def _extended_windows_path(path: Path) -> Path:
    """Use extended-length paths after the caller has validated the root."""
    value = str(path)
    if os.name != "nt" or value.startswith("\\\\?\\"):
        return path
    if value.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + value[2:])
    return Path("\\\\?\\" + value)


def _verify_files(base: Path, expected: dict[str, str]) -> None:
    if not isinstance(expected, dict) or not expected:
        raise SandboxPlanError("a complete file digest manifest is required")
    seen = set()
    total = 0
    base = _extended_windows_path(base)

    def fail_walk(error: OSError) -> None:
        raise error

    def entries():
        for directory, directories, names in os.walk(base, followlinks=False, onerror=fail_walk):
            for name in directories + names:
                yield Path(directory) / name

    for path in entries():
        if is_linklike(path):
            raise SandboxPlanError("sandbox inputs cannot contain links")
        if path.is_dir():
            continue
        if not path.is_file():
            raise SandboxPlanError("sandbox inputs must contain regular files")
        relative = path.relative_to(base).as_posix()
        parts = path.relative_to(base).parts
        if any(part.casefold() in {".git", ".ssh", ".aws", ".openclaw", ".easel-browser-profiles",
                                   "credentials.json", "auth-profiles.json",
                                   "cookies.sqlite", "token.json", "browser-profiles"}
               or part.casefold().startswith(".env") for part in parts):
            raise SandboxPlanError("sandbox package contains a prohibited credential or session path")
        if ({"sessions", "credentials", "cookies"} & {part.casefold() for part in parts}
                and path.suffix.casefold() not in {".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".map"}):
            raise SandboxPlanError("sandbox package contains credential or session data")
        total += path.stat().st_size
        if total > 2 * 1024 * 1024 * 1024 or len(seen) >= 100_000:
            raise SandboxPlanError("sandbox package exceeds its size limit")
        digest = expected.get(relative)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SandboxPlanError("sandbox file is missing from its manifest")
        sha = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                sha.update(block)
        if sha.hexdigest() != digest:
            raise SandboxPlanError("sandbox file differs from its manifest")
        seen.add(relative)
    if seen != set(expected):
        raise SandboxPlanError("sandbox manifest names missing files")


def build_windows_sandbox_spec(*, workspace: Path, runtime: Path,
                               runtime_files: dict[str, str],
                               runtime_base: Path | None = None) -> dict[str, Any]:
    """Produce a non-executable, review-only SBOX configuration and digest."""
    if os.name != "nt":
        raise SandboxPlanError("Windows sandbox specification requires Windows")
    try:
        import flatbuffers
    except ImportError:
        raise SandboxPlanError("optional flatbuffers package is not installed") from None
    work = _ordinary(Path(workspace), directory=True)
    package = _ordinary(Path(runtime), directory=True)
    inputs = _ordinary(work / "input", directory=True)
    output = _ordinary(work / "output", directory=True)
    manifest_path = _ordinary(work / "workspace.json", directory=False)
    runtime_base = _ordinary(Path(runtime_base), directory=True) if runtime_base else work.parent.parent / "easel-windows-runtime"
    if (not package.is_relative_to(runtime_base)
            or package == runtime_base
            or work == package or work in package.parents or package in work.parents
            or inputs == output or inputs in output.parents or output in inputs.parents):
        raise SandboxPlanError("runtime must be a separate, explicitly selected runtime package")
    cancelled = work / "cancel.json"
    if cancelled.exists() or is_linklike(cancelled):
        raise SandboxPlanError("prepared workspace is cancelled or unsafe")
    try:
        record = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise SandboxPlanError("workspace manifest is unreadable") from None
    if not isinstance(record, dict) or record.get("schema") != "contentops.easel-agent-workspace/v1":
        raise SandboxPlanError("workspace manifest is invalid")
    if (not isinstance(record.get("input_sha256"), dict)
            or not {"prompt.txt", "openclaw.json", "windows-capture.cjs"}.issubset(record["input_sha256"])):
        raise SandboxPlanError("workspace prompt, configuration, or capture source is missing")
    if not isinstance(runtime_files, dict) or not {"node.exe", "openclaw/openclaw.mjs"}.issubset(runtime_files):
        raise SandboxPlanError("Windows runtime entry points are missing from the manifest")
    _verify_files(inputs, record.get("input_sha256"))
    _verify_files(package, runtime_files)
    prefix = "openclaw/node_modules/@openclaw/fs-safe-win32-x64-msvc/"
    native = [name for name in runtime_files if name.startswith(prefix) and name.endswith(".node")]
    if len(native) != 1:
        raise SandboxPlanError("exactly one Windows x64 fs-safe native module is required")
    try:
        metadata = []
        for rel in ("openclaw/package.json", "openclaw/node_modules/@openclaw/fs-safe/package.json", prefix + "package.json"):
            path = _extended_windows_path(package).joinpath(*rel.split("/"))
            if path.stat().st_size > 1024 * 1024:
                raise ValueError("metadata too large")
            metadata.append(json.loads(path.read_text(encoding="utf-8")))
        if (not all(isinstance(item, dict) for item in metadata)
                or [item.get("name") for item in metadata] != ["openclaw", "@openclaw/fs-safe", "@openclaw/fs-safe-win32-x64-msvc"]
                or not isinstance(metadata[0].get("version"), str)
                or not isinstance(metadata[1].get("version"), str)
                or metadata[1]["version"] != metadata[2].get("version")):
            raise ValueError("runtime metadata mismatch")
        for rel in ("node.exe", native[0]):
            with _extended_windows_path(package).joinpath(*rel.split("/")).open("rb") as stream:
                dos = stream.read(64)
                if len(dos) != 64 or dos[:2] != b"MZ":
                    raise ValueError("invalid PE header")
                offset = struct.unpack_from("<I", dos, 0x3C)[0]
                if offset > 16 * 1024 * 1024:
                    raise ValueError("invalid PE offset")
                stream.seek(offset)
                header = stream.read(6)
                if len(header) != 6 or header[:4] != b"PE\0\0" or struct.unpack_from("<H", header, 4)[0] != 0x8664:
                    raise ValueError("not Windows x64")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, struct.error):
        raise SandboxPlanError("Windows runtime metadata or binary format is invalid") from None
    if any(output.iterdir()):
        raise SandboxPlanError("workspace output must be empty for a new run")
    builder = flatbuffers.Builder(1024)
    version = builder.CreateString("0.1.0")

    def path_vector(paths: list[Path]) -> int:
        offsets = [builder.CreateString(str(path)) for path in paths]
        builder.StartVector(4, len(offsets), 4)
        for offset in reversed(offsets):
            builder.PrependUOffsetTRelative(offset)
        return builder.EndVector()

    writable = path_vector([output])
    readonly = path_vector([inputs, package])
    # Pinned schema: NetworkPolicy.egress -> endpoint_policy whose default
    # action is deny, with no allow or deny exceptions. This requests an
    # additional default-deny policy; it does not prove OS enforcement.
    builder.StartObject(3)
    egress = builder.EndObject()
    builder.StartObject(3)
    builder.PrependUOffsetTRelativeSlot(1, egress, 0)
    network_policy = builder.EndObject()
    # Slots follow the pinned Microsoft schema. Slot 2 is deprecated but
    # retained in the wire layout; no network capabilities are granted.
    builder.StartObject(12)
    builder.PrependUOffsetTRelativeSlot(0, version, 0)
    builder.PrependBoolSlot(1, True, False)
    builder.PrependBoolSlot(3, True, False)
    builder.PrependUint64Slot(4, 0xFF, 0)
    builder.PrependBoolSlot(5, True, False)
    builder.PrependUOffsetTRelativeSlot(7, writable, 0)
    builder.PrependUOffsetTRelativeSlot(8, readonly, 0)
    builder.PrependUOffsetTRelativeSlot(9, network_policy, 0)
    spec = builder.EndObject()
    builder.Finish(spec, file_identifier=b"SBOX")
    payload = bytes(builder.Output())
    # Review-only launch description. It is not passed to CreateProcess and
    # does not include provider credentials or authorize network access.
    # Windows uses the original absolute paths named in this SBOX spec; Linux
    # /input and /output mount aliases do not exist here.
    argv = [str(package / "node.exe"), "--require", str(inputs / "windows-capture.cjs"),
            str(package / "openclaw" / "openclaw.mjs"),
            "agent", "exec", "--message-file", str(inputs / "prompt.txt"),
            "--cwd", str(output), "--config", str(inputs / "openclaw.json"),
            "--code-mode", "direct", "--timeout", "120", "--json"]
    argv_bytes = json.dumps(argv, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    if not system_root.is_absolute() or not system_root.is_dir():
        raise SandboxPlanError("Windows system directory is unavailable")
    environment = {"SystemRoot": str(system_root), "WINDIR": str(system_root),
                   "PATH": str(system_root / "System32"), "USERPROFILE": str(output),
                   "HOME": str(output), "TEMP": str(output), "TMP": str(output),
                   "OPENCLAW_STATE_DIR": str(output / "openclaw-state"),
                   "OPENCLAW_CONFIG_PATH": str(inputs / "openclaw.json"),
                   # Avoid known OpenClaw launcher respawns: unsupported Node
                   # should fail admission instead of finding another runtime.
                   "NODE_DISABLE_COMPILE_CACHE": "1",
                   "OPENCLAW_NODE_UPDATE_RESPAWNED": "1",
                   "CONTENTOPS_CAPTURE_FILE": str(output / "agent-result.json")}
    # CreateProcessInSandbox requires an explicit, double-NUL-terminated UTF-16
    # environment and CREATE_UNICODE_ENVIRONMENT; a null environment would
    # inherit the caller's secrets. This is serialized for review only.
    environment_block = ("\0".join(f"{key}={environment[key]}"
                                   for key in sorted(environment, key=str.casefold)) + "\0\0").encode("utf-16-le")
    run_id = record.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", run_id):
        raise SandboxPlanError("workspace run identity is invalid")
    return {"schema": "contentops.easel-windows-sandbox-spec/v1",
            "run_id": record.get("run_id"), "spec_base64": base64.b64encode(payload).decode("ascii"),
            "spec_sha256": hashlib.sha256(payload).hexdigest(),
            "openclaw_version": metadata[0]["version"], "fs_safe_version": metadata[1]["version"],
            "schema_source_commit": SCHEMA_SOURCE_COMMIT, "schema_source_sha256": SCHEMA_SOURCE_SHA256,
            "read_only": [str(inputs), str(package)], "read_write": [str(output)],
            "network_capabilities": [], "network_policy": "EGRESS_DENY_REQUESTED_NOT_VERIFIED",
            "environment": "EXPLICIT_REVIEW_ONLY",
            "candidate_argv": argv, "candidate_cwd": str(output),
            "candidate_argv_sha256": hashlib.sha256(argv_bytes).hexdigest(),
            "candidate_environment": environment,
            "candidate_command_line": list2cmdline(argv),
            "sandbox_identity": "ContentOps_Easel_" + run_id.replace("-", "_"),
            "environment_block_sha256": hashlib.sha256(environment_block).hexdigest(),
            "environment_block_size": len(environment_block),
            "creation_flags_required": ["CREATE_UNICODE_ENVIRONMENT", "CREATE_NO_WINDOW"],
            "inherit_handles": False,
            "stdout_capture": "NODE_WRITE_ONLY_UNVERIFIED", "provider_access": "NOT_CONFIGURED",
            "execution_route": "EMBEDDED_DIRECT_ONLY", "gateway_route": "NOT_IMPLEMENTED",
            "subprocess_restriction": "NOT_ESTABLISHED", "isolation": "NOT_VERIFIED",
            "execution": "NOT_AUTHORIZED", "production_ready": False, "publish_authorized": False}
