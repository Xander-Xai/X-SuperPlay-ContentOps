"""ASGI adapter for the one authorized offline Easel task interface."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs

from .path_safety import is_linklike as _linklike

from .offline_task import (OfflineTaskError, list_profile_summaries, list_account_projects, list_offline_tasks,
                           project_readiness,
                           read_profile_detail,
                           read_offline_failure,
                           read_offline_task_artifacts,
                           read_offline_task_draft,
                           read_offline_task_receipt,
                           run_offline_draft_task)

SUBMIT_PATH = "/api/contentops/draft-task"
EVIDENCE_DRAFT_PATH = "/api/contentops/evidence-draft"
AGENT_WORKSPACE_PATH = "/api/contentops/agent-workspace"
AGENT_PROPOSAL_PATH = "/api/contentops/agent-proposal"
AGENT_APPROVAL_INSPECTION_PATH = "/api/contentops/agent-approval-inspection"
AGENT_CANCEL_PATH = "/api/contentops/agent-cancel"
AGENT_COLLECT_PATH = "/api/contentops/agent-collect"
WINDOWS_SANDBOX_REVIEW_PATH = "/api/contentops/windows-sandbox-review"
PROFILES_PATH = "/api/contentops/profiles"
PROJECTS_PATH = "/api/contentops/projects"
TASKS_PATH = "/api/contentops/draft-tasks"
CONTENTOPS_STATUS_PATH = "/api/contentops/status"
PROFILE_DETAIL_PATH = re.compile(r"^/api/contentops/profiles/([a-z0-9][a-z0-9-]{0,79})$")
READINESS_PATH = "/api/contentops/project-readiness"
SKILL_PATH = "/api/contentops/skills/video-script"
UI_PATH = "/contentops/offline-task"
UI_ASSETS = {
    UI_PATH: ("offline_task.html", "text/html; charset=utf-8",
              "8321fe425d8dfaee4a689da9fe9d5c5d9a7aea3b8a1a8d3f52921203c45832bd"),
    "/contentops/offline-task.js": ("offline_task.js", "text/javascript; charset=utf-8",
                                     "922290ca2b201efe270662bd1c5ed9abc0ec610e8b8f033bc84aa044996a3ff5"),
    "/contentops/offline-task.css": ("offline_task.css", "text/css; charset=utf-8",
                                      "847664d54708ad67d9611b4cf1698c0da7a06aec152f125bf5e4db8bbb618cdf"),
}
STATUS_PATH = re.compile(
    r"^/api/contentops/draft-task/([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12})$"
)
DRAFT_PATH = re.compile(
    r"^/api/contentops/draft-task/([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12})/draft$"
)
ARTIFACTS_PATH = re.compile(
    r"^/api/contentops/draft-task/([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12})/artifacts$"
)
MAX_REQUEST_BYTES = 32_768
REQUEST_FIELDS = {"account", "project", "brief", "idempotency_key"}


def _windows_runtime_candidates(repo_root: Path) -> list[dict]:
    """List local package names for selection, without asserting integrity."""
    projects = Path(repo_root) / "projects"
    found = []
    try:
        if _linklike(projects) or not projects.is_dir():
            return found
        project_paths = [(path, path.name) for path in projects.iterdir()]
        local = projects / "_local"
        if not _linklike(local) and local.is_dir():
            project_paths.extend((path, f"_local/{path.name}") for path in local.iterdir())
        for project, identifier in sorted(project_paths, key=lambda item: item[1]):
            if (not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", project.name)
                    or _linklike(project) or not project.is_dir()):
                continue
            work = project / "work"
            parent = work / "easel-windows-runtime"
            if _linklike(work) or _linklike(parent) or not parent.is_dir():
                continue
            for manifest in sorted(parent.glob("*.json"), key=lambda item: item.name):
                name = manifest.name[:-5]
                package = parent / name
                if (re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", name)
                        and not _linklike(manifest) and manifest.is_file()
                        and not _linklike(package) and package.is_dir()):
                    found.append({"project": identifier, "package": name,
                                  "state": "PRESENT_UNVERIFIED"})
                    if len(found) >= 50:
                        return found
    except OSError:
        pass
    return found


def _header(scope, name: bytes) -> str:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value.decode("latin-1").strip()
    return ""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


async def _body(receive) -> bytes:
    chunks = []
    size = 0
    while True:
        message = await receive()
        if message.get("type") == "http.disconnect":
            raise OfflineTaskError("REQUEST_INTERRUPTED", "request body was interrupted", 400)
        if message.get("type") != "http.request":
            continue
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > MAX_REQUEST_BYTES:
            raise OfflineTaskError("REQUEST_TOO_LARGE", "request body exceeds the 32 KiB limit", 413)
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks)


async def _json_response(send, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    await send({"type": "http.response.start", "status": status, "headers": [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(body)).encode("ascii")),
        (b"cache-control", b"no-store"),
    ]})
    await send({"type": "http.response.body", "body": body})


class OfflineTaskAPI:
    """Handle exact task routes; forward every other allowed request untouched."""

    def __init__(self, app, repo_root: Path) -> None:
        self.app = app
        self.repo_root = Path(repo_root)
        self._windows_plan_busy = False

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method") or "").upper()
        path = str(scope.get("path") or "")
        if method == "POST" and path == SUBMIT_PATH:
            await self._submit(scope, receive, send)
            return
        if method == "POST" and path == EVIDENCE_DRAFT_PATH:
            await self._evidence_draft(scope, receive, send)
            return
        if method == "POST" and path == AGENT_WORKSPACE_PATH:
            await self._prepare_agent(scope, receive, send)
            return
        if method == "POST" and path == AGENT_PROPOSAL_PATH:
            await self._agent_proposal(scope, receive, send)
            return
        if method == "POST" and path == AGENT_APPROVAL_INSPECTION_PATH:
            await self._agent_approval_inspection(scope, receive, send)
            return
        if method == "POST" and path == AGENT_CANCEL_PATH:
            await self._cancel_agent(scope, receive, send)
            return
        if method == "POST" and path == AGENT_COLLECT_PATH:
            await self._collect_agent(scope, receive, send)
            return
        if method == "POST" and path == WINDOWS_SANDBOX_REVIEW_PATH:
            await self._review_windows_sandbox(scope, receive, send)
            return
        if method == "GET" and path == PROFILES_PATH:
            await self._profiles(send)
            return
        if method == "GET" and path == PROJECTS_PATH:
            await self._projects(scope, send)
            return
        if method == "GET" and path == TASKS_PATH:
            await self._task_list(scope, send)
            return
        if method == "GET" and path == CONTENTOPS_STATUS_PATH:
            await _json_response(send, 200, {
                "schema": "contentops.easel-offline-status/v1",
                "mode": "OFFLINE_DRAFTS_ONLY",
                "gateway_status": "NOT_CHECKED",
                "agent_execution": "NOT_AUTHORIZED",
                "network_isolation": "NOT_ESTABLISHED",
                "windows_sandbox": {
                    "platform": "WINDOWS" if sys.platform == "win32" else "OTHER",
                    "spec_generator": "IMPLEMENTED_UNVERIFIED",
                    "flatbuffers": "DISCOVERABLE" if importlib.util.find_spec("flatbuffers") else "MISSING",
                    "runtime_package": "NOT_CHECKED",
                    "execution_route": "EMBEDDED_DIRECT_ONLY",
                    "gateway_route": "NOT_IMPLEMENTED",
                    "runtime_candidates": _windows_runtime_candidates(self.repo_root),
                    "process_launcher": "PROTOTYPE_HARD_DISABLED_UNVERIFIED",
                    "stdout_capture": "NODE_WRITE_ONLY_UNVERIFIED",
                    "isolation_proof": "NOT_ESTABLISHED",
                    "task_authorization": "NOT_GRANTED",
                },
                "production_ready": False,
                "publish_authorized": False,
            })
            return
        match = PROFILE_DETAIL_PATH.fullmatch(path)
        if method == "GET" and match:
            await self._profile_detail(match.group(1), send)
            return
        if method == "GET" and path == READINESS_PATH:
            await self._readiness(scope, send)
            return
        if method == "GET" and path == SKILL_PATH:
            await self._skill(send)
            return
        if method == "GET" and path in UI_ASSETS:
            await self._asset(path, send)
            return
        match = STATUS_PATH.fullmatch(path)
        if method == "GET" and match:
            await self._status(scope, match.group(1), send)
            return
        match = DRAFT_PATH.fullmatch(path)
        if method == "GET" and match:
            await self._draft(scope, match.group(1), send)
            return
        match = ARTIFACTS_PATH.fullmatch(path)
        if method == "GET" and match:
            await self._artifacts(scope, match.group(1), send)
            return
        await self.app(scope, receive, send)

    async def _profiles(self, send) -> None:
        try:
            profiles = await asyncio.to_thread(list_profile_summaries, self.repo_root)
        except OfflineTaskError as exc:
            await _json_response(send, exc.status, {"error": exc.code, "detail": exc.detail})
        except Exception:  # noqa: BLE001 - don't leak filesystem paths
            await _json_response(send, 500, {"error": "PROFILE_LIST_UNAVAILABLE"})
        else:
            await _json_response(send, 200, profiles)

    async def _profile_detail(self, account: str, send) -> None:
        try:
            profile = await asyncio.to_thread(read_profile_detail, self.repo_root, account)
        except OfflineTaskError as exc:
            await _json_response(send, exc.status, {"error": exc.code, "detail": exc.detail})
        except Exception:  # noqa: BLE001 - do not disclose internal paths
            await _json_response(send, 500, {"error": "PROFILE_DETAIL_UNAVAILABLE"})
        else:
            await _json_response(send, 200, profile)

    async def _projects(self, scope, send) -> None:
        try:
            query = parse_qs(scope.get("query_string", b"").decode("ascii"),
                             keep_blank_values=True, strict_parsing=True)
            if set(query) != {"account"} or len(query["account"]) != 1:
                raise OfflineTaskError("REQUEST_SCHEMA_INVALID", "query requires one account")
            result = await asyncio.to_thread(list_account_projects, repo_root=self.repo_root,
                                             account=query["account"][0])
        except OfflineTaskError as exc:
            await _json_response(send, exc.status, {"error": exc.code, "detail": exc.detail})
        except (ValueError, UnicodeDecodeError):
            await _json_response(send, 400, {"error": "REQUEST_INVALID"})
        except Exception:  # noqa: BLE001
            await _json_response(send, 500, {"error": "PROJECT_LIST_UNAVAILABLE"})
        else:
            await _json_response(send, 200, result)

    async def _task_list(self, scope, send) -> None:
        try:
            query = parse_qs(scope.get("query_string", b"").decode("ascii"),
                             keep_blank_values=True, strict_parsing=True)
            if set(query) != {"account", "project"} or any(len(v) != 1 for v in query.values()):
                raise OfflineTaskError("REQUEST_SCHEMA_INVALID", "query requires one account and one project")
            result = await asyncio.to_thread(list_offline_tasks, repo_root=self.repo_root,
                                             account=query["account"][0], project_slug=query["project"][0])
            from .agent_workspace import list_agent_workspaces
            from .windows_sandbox import list_windows_reviews
            agent = await asyncio.to_thread(list_agent_workspaces, repo_root=self.repo_root,
                                            account=query["account"][0], project_slug=query["project"][0])
            result["agent_workspaces"] = agent["workspaces"]
            result["agent_unavailable_count"] = agent["unavailable_count"]
            reviews = await asyncio.to_thread(list_windows_reviews, repo_root=self.repo_root,
                                              account=query["account"][0], project_slug=query["project"][0])
            result["windows_reviews"] = reviews["reviews"]
            result["windows_review_unavailable_count"] = reviews["unavailable_count"]
            script = self.repo_root / "scripts" / "prepare_easel_agent_proposal.py"
            if _linklike(script.parent) or _linklike(script) or not script.is_file():
                raise OfflineTaskError("PROPOSAL_UNAVAILABLE", "proposal implementation unavailable", 503)
            spec = importlib.util.spec_from_file_location("contentops_easel_proposal_list", script)
            if spec is None or spec.loader is None:
                raise OfflineTaskError("PROPOSAL_UNAVAILABLE", "proposal implementation unavailable", 503)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            proposals = await asyncio.to_thread(module.list_proposals, repo_root=self.repo_root,
                                                account=query["account"][0], project_slug=query["project"][0])
            result["agent_proposals"] = proposals["proposals"]
            result["proposal_unavailable_count"] = proposals["unavailable_count"]
        except OfflineTaskError as exc:
            await _json_response(send, exc.status, {"error": exc.code, "detail": exc.detail})
        except (ValueError, UnicodeDecodeError):
            await _json_response(send, 400, {"error": "REQUEST_INVALID"})
        except Exception:  # noqa: BLE001
            await _json_response(send, 500, {"error": "TASK_LIST_UNAVAILABLE"})
        else:
            await _json_response(send, 200, result)

    async def _readiness(self, scope, send) -> None:
        try:
            query = parse_qs(scope.get("query_string", b"").decode("latin-1"),
                             keep_blank_values=True, strict_parsing=True)
            if set(query) != {"account", "project"} or any(len(v) != 1 for v in query.values()):
                raise OfflineTaskError("REQUEST_SCHEMA_INVALID", "query requires one account and one project")
            result = await asyncio.to_thread(project_readiness, repo_root=self.repo_root,
                                             account=query["account"][0], project_slug=query["project"][0])
        except OfflineTaskError as exc:
            await _json_response(send, exc.status, {"error": exc.code, "detail": exc.detail})
        except (ValueError, UnicodeDecodeError):
            await _json_response(send, 400, {"error": "REQUEST_INVALID"})
        except Exception:  # noqa: BLE001 - do not disclose project internals
            await _json_response(send, 500, {"error": "PROJECT_READINESS_UNAVAILABLE"})
        else:
            await _json_response(send, 200, result)

    async def _skill(self, send) -> None:
        """Expose only the declared repository-owned skill, never upstream env readers."""
        root = self.repo_root.resolve(strict=True)
        relative = "extensions/easel-workbench/skills/builtin/video-script/SKILL.md"
        key = "skills/builtin/video-script/SKILL.md"
        try:
            manifest = root / "runtime" / "easel-workbench-overlay.json"
            path = root
            for part in relative.split("/"):
                path = path / part
                if _linklike(path):
                    raise ValueError("linked skill path")
            if (_linklike(manifest) or _linklike(manifest.parent)
                    or not manifest.is_file() or not path.is_file()
                    or not path.resolve(strict=True).is_relative_to(root)):
                raise ValueError("unsafe skill source")
            record = json.loads(manifest.read_text(encoding="utf-8"))
            overlay = record["overlay"]
            if overlay["source_files"][key] != relative:
                raise ValueError("skill source is not declared")
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if len(data) > 262144 or digest != overlay["digests"][key]:
                raise ValueError("skill source digest mismatch")
            content = data.decode("utf-8")
        except (OSError, ValueError, KeyError, TypeError, UnicodeError):
            await _json_response(send, 503, {"error": "SKILL_SOURCE_UNVERIFIED"})
            return
        await _json_response(send, 200, {"skill": "video-script", "sha256": digest,
                                         "content": content,
                                         "source": "repository-owned overlay",
                                         "execution_authorized": False})

    async def _asset(self, path: str, send) -> None:
        filename, content_type, expected_sha = UI_ASSETS[path]
        static_root = Path(__file__).resolve().parent / "static"
        asset_path = static_root / filename
        try:
            if (_linklike(static_root) or _linklike(asset_path)
                    or not asset_path.is_file()
                    or asset_path.resolve(strict=True).parent != static_root.resolve(strict=True)):
                raise OSError("unsafe UI asset")
            content = asset_path.read_bytes()
        except OSError:
            content = b""
        # ``* text=auto`` expands LF to CRLF on a Windows checkout, so hashing the bytes
        # as read makes the pin a property of the machine rather than of the file. Hash the
        # content as git stores it; the bytes served stay exactly as they were read.
        actual_sha = hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()
        if not content or actual_sha != expected_sha:
            await _json_response(send, 503, {"error": "OFFLINE_UI_UNVERIFIED"})
            return
        headers = [
            (b"content-type", content_type.encode("ascii")),
            (b"content-length", str(len(content)).encode("ascii")),
            (b"cache-control", b"no-store"),
            (b"x-content-type-options", b"nosniff"),
        ]
        if path == UI_PATH:
            headers.append((b"content-security-policy",
                            b"default-src 'none'; script-src 'self'; style-src 'self'; "
                            b"connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"))
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": content})

    async def _submit(self, scope, receive, send) -> None:
        content_type = _header(scope, b"content-type").split(";", 1)[0].lower()
        if content_type != "application/json":
            await _json_response(send, 415, {"error": "CONTENT_TYPE_INVALID"})
            return
        try:
            raw = await _body(receive)
            request = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
            if not isinstance(request, dict) or set(request) != REQUEST_FIELDS:
                raise OfflineTaskError("REQUEST_SCHEMA_INVALID",
                                       "required keys: account, project, brief, idempotency_key")
            receipt = await asyncio.to_thread(
                run_offline_draft_task,
                repo_root=self.repo_root,
                account=request["account"],
                project_slug=request["project"],
                brief=request["brief"],
                idempotency_key=request["idempotency_key"],
            )
        except OfflineTaskError as exc:
            payload = {"error": exc.code, "detail": exc.detail}
            if exc.failure_receipt:
                payload["failure_receipt"] = exc.failure_receipt
                payload["failure_record"] = exc.failure_record
            await _json_response(send, exc.status, payload)
        except (UnicodeDecodeError, ValueError):
            await _json_response(send, 400, {"error": "REQUEST_INVALID",
                                              "detail": "body must be UTF-8 JSON"})
        except Exception:  # noqa: BLE001 - do not leak internal paths or exception text
            await _json_response(send, 500, {"error": "TASK_INTERNAL_ERROR"})
        else:
            await _json_response(send, 200, receipt)

    async def _review_windows_sandbox(self, scope, receive, send) -> None:
        from .agent_sandbox import SandboxPlanError

        if _header(scope, b"content-type").split(";", 1)[0].lower() != "application/json":
            await _json_response(send, 415, {"error": "CONTENT_TYPE_INVALID"})
            return
        if self._windows_plan_busy:
            await _json_response(send, 409, {"error": "SANDBOX_REVIEW_BUSY"})
            return
        self._windows_plan_busy = True
        try:
            request = json.loads((await _body(receive)).decode("utf-8"), object_pairs_hook=_unique_object)
            keys = {"account", "project", "run_id", "runtime_project", "package"}
            if not isinstance(request, dict) or set(request) != keys or any(not isinstance(v, str) for v in request.values()):
                raise OfflineTaskError("REQUEST_SCHEMA_INVALID", "account, project, run_id, runtime_project and package are required")
            from .windows_sandbox import review_windows_task
            result = await asyncio.to_thread(review_windows_task, repo_root=self.repo_root,
                                             account=request["account"], project_slug=request["project"],
                                             run_id=request["run_id"], runtime_project=request["runtime_project"],
                                             package_name=request["package"], write_receipt=True)
        except OfflineTaskError as exc:
            await _json_response(send, exc.status, {"error": exc.code, "detail": exc.detail})
        except SandboxPlanError as exc:
            reasons = {
                "Windows sandbox specification requires Windows": "该审查只能在 Windows 上运行。",
                "optional flatbuffers package is not installed": "缺少 flatbuffers 依赖；请先按项目安装流程处理。",
                "workspace is stale, unsafe, or cancelled": "任务输入已过期、不安全或已取消，请重新准备。",
                "workspace changed or was cancelled during review": "审查期间任务发生变化或被取消，请重新准备。",
                "runtime manifest changed during review": "审查期间运行包清单发生变化，请重新审查。",
                "runtime manifest is invalid": "运行包清单格式或绑定无效。",
                "runtime manifest is missing": "所选项目中没有该运行包清单，请先准备运行包。",
                "runtime manifest is unreadable": "运行包清单不可读取。",
                "runtime manifest is too large": "运行包清单超过允许的大小。",
                "invalid package slug": "运行包名称格式无效。",
                "sandbox file differs from its manifest": "运行包或任务文件与清单摘要不一致。",
                "sandbox manifest names missing files": "运行包或任务清单中的文件缺失。",
                "another Windows sandbox review is still running": "已有审查仍在后台运行，请稍后再试。",
            }
            await _json_response(send, 409, {"error": "SANDBOX_REVIEW_BLOCKED",
                                             "detail": reasons.get(str(exc), "任务、运行包或沙箱配置不满足审查条件。")})
        except (UnicodeError, ValueError, OSError):
            await _json_response(send, 409, {"error": "SANDBOX_REVIEW_BLOCKED", "detail": "任务、运行包或沙箱配置不可用"})
        except Exception:
            await _json_response(send, 500, {"error": "SANDBOX_REVIEW_FAILED"})
        else:
            await _json_response(send, 200, result)
        finally:
            self._windows_plan_busy = False

    async def _collect_agent(self, scope, receive, send) -> None:
        from .agent_result import AgentResultError, collect_workspace_result

        if _header(scope, b"content-type").split(";", 1)[0].lower() != "application/json":
            await _json_response(send, 415, {"error": "CONTENT_TYPE_INVALID"})
            return
        try:
            request = json.loads((await _body(receive)).decode("utf-8"), object_pairs_hook=_unique_object)
            if (not isinstance(request, dict) or set(request) != {"account", "project", "run_id", "exit_code"}
                    or type(request["exit_code"]) is not int):
                raise OfflineTaskError("REQUEST_SCHEMA_INVALID", "required keys: account, project, run_id, integer exit_code")
            result = await asyncio.to_thread(collect_workspace_result, repo_root=self.repo_root,
                                             account=request["account"], project_slug=request["project"],
                                             run_id=request["run_id"], exit_code=request["exit_code"])
        except OfflineTaskError as exc:
            await _json_response(send, exc.status, {"error": exc.code, "detail": exc.detail})
        except AgentResultError as exc:
            messages = {
                "candidate result exceeds size limit": "候选输出超过 2 MiB，无法收集。",
                "workspace inputs are stale": "任务输入已过期，请重新准备。",
                "workspace was cancelled": "任务已取消，无法收集结果。",
                "capture record does not match result or exit code": "采集记录与输出或退出状态不一致。",
                "existing candidate receipt does not match": "已有结果回执与本次内容不一致。",
                "existing partial candidate does not match": "已有候选草稿与本次内容不一致。",
            }
            await _json_response(send, 409, {"error": "RESULT_COLLECTION_BLOCKED",
                                             "detail": messages.get(str(exc), "候选结果或其绑定无效，无法收集。")})
        except (UnicodeDecodeError, ValueError):
            await _json_response(send, 400, {"error": "RESULT_INVALID"})
        except Exception:
            await _json_response(send, 500, {"error": "RESULT_COLLECTION_FAILED"})
        else:
            await _json_response(send, 200, result)

    async def _cancel_agent(self, scope, receive, send) -> None:
        if _header(scope, b"content-type").split(";", 1)[0].lower() != "application/json":
            await _json_response(send, 415, {"error": "CONTENT_TYPE_INVALID"})
            return
        try:
            request = json.loads((await _body(receive)).decode("utf-8"), object_pairs_hook=_unique_object)
            if not isinstance(request, dict) or set(request) != {"account", "project", "run_id"}:
                raise OfflineTaskError("REQUEST_SCHEMA_INVALID", "required keys: account, project, run_id")
            from .agent_workspace import cancel_prepared_agent_workspace
            result = await asyncio.to_thread(cancel_prepared_agent_workspace, repo_root=self.repo_root,
                                             account=request["account"], project_slug=request["project"],
                                             run_id=request["run_id"])
        except OfflineTaskError as exc:
            await _json_response(send, exc.status, {"error": exc.code, "detail": exc.detail})
        except (UnicodeDecodeError, ValueError):
            await _json_response(send, 400, {"error": "REQUEST_INVALID"})
        except Exception:
            await _json_response(send, 500, {"error": "CANCELLATION_FAILED"})
        else:
            await _json_response(send, 200, result)

    async def _agent_approval_inspection(self, scope, receive, send) -> None:
        if _header(scope, b"content-type").split(";", 1)[0].lower() != "application/json":
            await _json_response(send, 415, {"error": "CONTENT_TYPE_INVALID"})
            return
        try:
            request = json.loads((await _body(receive)).decode("utf-8"), object_pairs_hook=_unique_object)
            keys = {"account", "project", "run_id", "proposal_sha256"}
            if not isinstance(request, dict) or set(request) != keys or any(not isinstance(v, str) for v in request.values()):
                raise OfflineTaskError("REQUEST_SCHEMA_INVALID", "approval inspection fields must all be strings")
            script = self.repo_root / "scripts" / "inspect_easel_agent_approval.py"
            if _linklike(script.parent) or _linklike(script) or not script.is_file():
                raise OfflineTaskError("APPROVAL_INSPECTION_UNAVAILABLE", "inspection implementation unavailable", 503)
            spec = importlib.util.spec_from_file_location("contentops_easel_approval_inspection", script)
            if spec is None or spec.loader is None:
                raise OfflineTaskError("APPROVAL_INSPECTION_UNAVAILABLE", "inspection implementation unavailable", 503)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            owners = [item.strip() for item in os.environ.get("CONTENTOPS_OWNER_IDENTITIES", "").split(",") if item.strip()]
            result = await asyncio.to_thread(module.inspect, repo_root=self.repo_root, owner_identities=owners,
                account=request["account"], project_slug=request["project"], run_id=request["run_id"],
                proposal_sha256=request["proposal_sha256"])
        except OfflineTaskError as exc:
            await _json_response(send, exc.status, {"error": exc.code, "detail": exc.detail})
        except (UnicodeError, ValueError):
            await _json_response(send, 409, {"error": "APPROVAL_BINDING_INVALID", "detail": "审批记录、任务或申请资料不匹配。"})
        except Exception:
            await _json_response(send, 409, {"error": "APPROVAL_INSPECTION_BLOCKED", "detail": "未找到可核对的审批，或审批来源不满足要求。"})
        else:
            await _json_response(send, 200, result)

    async def _agent_proposal(self, scope, receive, send) -> None:
        if _header(scope, b"content-type").split(";", 1)[0].lower() != "application/json":
            await _json_response(send, 415, {"error": "CONTENT_TYPE_INVALID"})
            return
        try:
            request = json.loads((await _body(receive)).decode("utf-8"), object_pairs_hook=_unique_object)
            keys = {"account", "project", "run_id", "service_mode", "service", "endpoint", "max_cost", "currency"}
            read_keys = {"account", "project", "run_id", "proposal_sha256", "action"}
            reading = isinstance(request, dict) and set(request) == read_keys and request.get("action") == "read"
            if (not isinstance(request, dict)
                    or (not reading and (set(request) not in (keys, keys | {"save"})
                        or any(not isinstance(request[k], str) for k in keys)
                        or ("save" in request and type(request["save"]) is not bool)))
                    or (reading and any(not isinstance(request[k], str) for k in read_keys))):
                raise OfflineTaskError("REQUEST_SCHEMA_INVALID", "proposal fields must all be strings")
            script = self.repo_root / "scripts" / "prepare_easel_agent_proposal.py"
            if _linklike(script.parent) or _linklike(script) or not script.is_file():
                raise OfflineTaskError("PROPOSAL_UNAVAILABLE", "proposal implementation unavailable", 503)
            spec = importlib.util.spec_from_file_location("contentops_easel_proposal", script)
            if spec is None or spec.loader is None:
                raise OfflineTaskError("PROPOSAL_UNAVAILABLE", "proposal implementation unavailable", 503)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if reading:
                result = await asyncio.to_thread(module.read_saved_proposal, repo_root=self.repo_root,
                    account=request["account"], project_slug=request["project"], run_id=request["run_id"],
                    proposal_sha256=request["proposal_sha256"])
            else:
                result = await asyncio.to_thread(module.proposal, repo_root=self.repo_root,
                    account=request["account"], project_slug=request["project"], run_id=request["run_id"],
                    service_mode=request["service_mode"], service=request["service"], endpoint=request["endpoint"],
                    max_cost=request["max_cost"], currency=request["currency"])
                if request.get("save"):
                    result = await asyncio.to_thread(module.save_proposal, result=result,
                                                      project_slug=request["project"], repo_root=self.repo_root)
        except OfflineTaskError as exc:
            await _json_response(send, exc.status, {"error": exc.code, "detail": exc.detail})
        except (UnicodeError, ValueError):
            await _json_response(send, 400, {"error": "PROPOSAL_INVALID", "detail": "任务、服务地址或费用上限无效。"})
        except Exception:
            await _json_response(send, 500, {"error": "PROPOSAL_UNAVAILABLE"})
        else:
            await _json_response(send, 200, result)

    async def _prepare_agent(self, scope, receive, send) -> None:
        if _header(scope, b"content-type").split(";", 1)[0].lower() != "application/json":
            await _json_response(send, 415, {"error": "CONTENT_TYPE_INVALID"})
            return
        try:
            request = json.loads((await _body(receive)).decode("utf-8"), object_pairs_hook=_unique_object)
            if not isinstance(request, dict) or set(request) != {"account", "project", "brief", "idempotency_key"}:
                raise OfflineTaskError("REQUEST_SCHEMA_INVALID", "required keys: account, project, brief, idempotency_key")
            from .agent_workspace import prepare_agent_workspace
            result = await asyncio.to_thread(prepare_agent_workspace, repo_root=self.repo_root,
                                             account=request["account"], project_slug=request["project"],
                                             brief=request["brief"], idempotency_key=request["idempotency_key"])
        except OfflineTaskError as exc:
            await _json_response(send, exc.status, {"error": exc.code, "detail": exc.detail})
        except (UnicodeDecodeError, ValueError):
            await _json_response(send, 400, {"error": "REQUEST_INVALID"})
        except Exception:
            await _json_response(send, 500, {"error": "WORKSPACE_PREPARATION_FAILED"})
        else:
            await _json_response(send, 200, result)

    async def _evidence_draft(self, scope, receive, send) -> None:
        if _header(scope, b"content-type").split(";", 1)[0].lower() != "application/json":
            await _json_response(send, 415, {"error": "CONTENT_TYPE_INVALID"})
            return
        try:
            request = json.loads((await _body(receive)).decode("utf-8"),
                                 object_pairs_hook=_unique_object)
            if not isinstance(request, dict) or set(request) != {"account", "project", "idempotency_key"}:
                raise OfflineTaskError("REQUEST_SCHEMA_INVALID",
                                       "required keys: account, project, idempotency_key")
            receipt = await asyncio.to_thread(
                run_offline_draft_task, repo_root=self.repo_root,
                account=request["account"], project_slug=request["project"],
                idempotency_key=request["idempotency_key"],
                brief="Build from the project's approved Brief and evidence pack.",
                executor="evidence")
        except OfflineTaskError as exc:
            payload = {"error": exc.code, "detail": exc.detail}
            if exc.failure_receipt:
                payload["failure_receipt"] = exc.failure_receipt
                payload["failure_record"] = exc.failure_record
            await _json_response(send, exc.status, payload)
        except (UnicodeDecodeError, ValueError):
            await _json_response(send, 400, {"error": "REQUEST_INVALID"})
        except Exception:  # noqa: BLE001 - do not disclose project internals
            await _json_response(send, 500, {"error": "TASK_INTERNAL_ERROR"})
        else:
            await _json_response(send, 200, receipt)

    async def _status(self, scope, task_id: str, send) -> None:
        try:
            query = parse_qs(scope.get("query_string", b"").decode("latin-1"),
                             keep_blank_values=True, strict_parsing=True)
        except ValueError:
            await _json_response(send, 400, {"error": "REQUEST_INVALID"})
            return
        if (set(query) not in ({"account", "project"}, {"account", "project", "kind"})
                or any(len(v) != 1 for v in query.values())
                or ("kind" in query and query["kind"] not in (["failure"], ["agent"], ["agent-result"], ["windows-review"]))):
            await _json_response(send, 400, {"error": "REQUEST_SCHEMA_INVALID",
                                             "detail": "query requires one account and one project"})
            return
        try:
            kind = query.get("kind", [""])[0]
            if kind == "windows-review":
                from .windows_sandbox import read_windows_review
                reader, identifier = read_windows_review, {"review_id": task_id}
            elif kind == "agent-result":
                from .agent_result import read_unverified_result
                reader, identifier = read_unverified_result, {"attempt_id": task_id}
            elif kind == "agent":
                from .agent_workspace import read_agent_workspace
                reader, identifier = read_agent_workspace, {"run_id": task_id}
            elif kind == "failure":
                reader, identifier = read_offline_failure, {"attempt_id": task_id}
            else:
                reader, identifier = read_offline_task_receipt, {"task_id": task_id}
            receipt = await asyncio.to_thread(
                reader,
                repo_root=self.repo_root,
                account=query["account"][0],
                project_slug=query["project"][0],
                **identifier,
            )
        except OfflineTaskError as exc:
            await _json_response(send, exc.status, {"error": exc.code, "detail": exc.detail})
        except (ValueError, UnicodeDecodeError):
            await _json_response(send, 400, {"error": "REQUEST_INVALID"})
        except Exception:  # noqa: BLE001 - do not leak internal paths or exception text
            await _json_response(send, 500, {"error": "TASK_INTERNAL_ERROR"})
        else:
            await _json_response(send, 200, receipt)

    async def _draft(self, scope, task_id: str, send) -> None:
        try:
            query = parse_qs(scope.get("query_string", b"").decode("latin-1"),
                             keep_blank_values=True, strict_parsing=True)
        except ValueError:
            await _json_response(send, 400, {"error": "REQUEST_INVALID"})
            return
        if set(query) != {"account", "project"} or any(len(v) != 1 for v in query.values()):
            await _json_response(send, 400, {"error": "REQUEST_SCHEMA_INVALID",
                                             "detail": "query requires one account and one project"})
            return
        try:
            draft = await asyncio.to_thread(
                read_offline_task_draft,
                repo_root=self.repo_root,
                account=query["account"][0],
                project_slug=query["project"][0],
                task_id=task_id,
            )
        except OfflineTaskError as exc:
            await _json_response(send, exc.status, {"error": exc.code, "detail": exc.detail})
        except (ValueError, UnicodeDecodeError):
            await _json_response(send, 400, {"error": "REQUEST_INVALID"})
        except Exception:  # noqa: BLE001 - do not leak internal paths or exception text
            await _json_response(send, 500, {"error": "TASK_INTERNAL_ERROR"})
        else:
            await _json_response(send, 200, draft)

    async def _artifacts(self, scope, task_id: str, send) -> None:
        try:
            query = parse_qs(scope.get("query_string", b"").decode("latin-1"),
                             keep_blank_values=True, strict_parsing=True)
            if set(query) != {"account", "project"} or any(len(v) != 1 for v in query.values()):
                raise OfflineTaskError("REQUEST_SCHEMA_INVALID", "query requires one account and one project")
            artifacts = await asyncio.to_thread(
                read_offline_task_artifacts, repo_root=self.repo_root,
                account=query["account"][0], project_slug=query["project"][0], task_id=task_id)
        except OfflineTaskError as exc:
            await _json_response(send, exc.status, {"error": exc.code, "detail": exc.detail})
        except (ValueError, UnicodeDecodeError):
            await _json_response(send, 400, {"error": "REQUEST_INVALID"})
        except Exception:  # noqa: BLE001 - do not disclose project internals
            await _json_response(send, 500, {"error": "TASK_INTERNAL_ERROR"})
        else:
            await _json_response(send, 200, artifacts)
