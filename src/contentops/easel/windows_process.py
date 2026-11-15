"""Windows sandbox launcher prototype, hard-disabled pending isolation proof.

This module is not an authorization mechanism. No environment variable, user
input, or local receipt can enable it. Before enabling it, the project must
independently verify the OS boundary and implement a task-specific grant gate.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import subprocess
from ctypes import wintypes
from pathlib import Path
from typing import Any
from uuid import UUID


class WindowsProcessError(RuntimeError):
    pass


def _prepare_windows_candidate(plan: dict[str, Any], timeout_seconds: int) -> tuple:
    """Validate and serialize a launch description without starting a process."""
    if os.name != "nt" or not isinstance(plan, dict):
        raise WindowsProcessError("Windows and a sandbox plan are required")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 1800:
        raise WindowsProcessError("invalid process timeout")
    argv = plan.get("candidate_argv")
    env = plan.get("candidate_environment")
    identity = plan.get("sandbox_identity")
    cwd = plan.get("candidate_cwd")
    if (not isinstance(argv, list) or not argv or any(not isinstance(v, str) or "\0" in v for v in argv)
            or not isinstance(env, dict) or not env or not isinstance(identity, str)
            or not isinstance(cwd, str)):
        raise WindowsProcessError("sandbox launch fields are invalid")
    readonly = plan.get("read_only")
    writable = plan.get("read_write")
    run_id = plan.get("run_id")
    try:
        if not isinstance(run_id, str) or str(UUID(run_id)) != run_id:
            raise ValueError("invalid run ID")
    except ValueError:
        raise WindowsProcessError("sandbox run identity is invalid") from None
    if (not isinstance(readonly, list) or len(readonly) != 2
            or any(not isinstance(v, str) or not Path(v).is_absolute() for v in readonly)
            or writable != [cwd] or not Path(cwd).is_absolute()
            or identity != "ContentOps_Easel_" + run_id.replace("-", "_")):
        raise WindowsProcessError("sandbox paths or identity do not match the plan")
    inputs, package = map(Path, readonly)
    output = Path(cwd)
    expected_argv = [str(package / "node.exe"), "--require", str(inputs / "windows-capture.cjs"),
                     str(package / "openclaw" / "openclaw.mjs"), "agent", "exec", "--message-file",
                     str(inputs / "prompt.txt"), "--cwd", str(output), "--config",
                     str(inputs / "openclaw.json"), "--code-mode", "direct", "--timeout", "120", "--json"]
    if argv != expected_argv:
        raise WindowsProcessError("sandbox command does not match the bound task")
    argv_bytes = json.dumps(argv, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(argv_bytes).hexdigest() != plan.get("candidate_argv_sha256"):
        raise WindowsProcessError("sandbox command digest does not match")
    if any(not isinstance(k, str) or not isinstance(v, str) or not k or "=" in k
           or "\0" in k or "\0" in v for k, v in env.items()):
        raise WindowsProcessError("sandbox environment is invalid")
    allowed_environment = {"SystemRoot", "WINDIR", "PATH", "USERPROFILE", "HOME", "TEMP", "TMP",
                           "OPENCLAW_STATE_DIR", "OPENCLAW_CONFIG_PATH", "NODE_DISABLE_COMPILE_CACHE",
                           "OPENCLAW_NODE_UPDATE_RESPAWNED", "CONTENTOPS_CAPTURE_FILE"}
    if (set(env) != allowed_environment or env["NODE_DISABLE_COMPILE_CACHE"] != "1"
            or env["OPENCLAW_NODE_UPDATE_RESPAWNED"] != "1"
            or any(env[name] != cwd for name in ("USERPROFILE", "HOME", "TEMP", "TMP"))
            or not Path(env["SystemRoot"]).is_absolute()
            or env["WINDIR"] != env["SystemRoot"]
            or env["PATH"] != str(Path(env["SystemRoot"]) / "System32")
            or env["OPENCLAW_STATE_DIR"] != str(output / "openclaw-state")
            or env["OPENCLAW_CONFIG_PATH"] != str(inputs / "openclaw.json")
            or env["CONTENTOPS_CAPTURE_FILE"] != str(output / "agent-result.json")):
        raise WindowsProcessError("sandbox environment does not match the restricted plan")
    try:
        spec = base64.b64decode(plan["spec_base64"], validate=True)
    except (KeyError, TypeError, ValueError):
        raise WindowsProcessError("sandbox specification is invalid") from None
    if len(spec) < 8 or len(spec) > 16 * 1024 * 1024 or spec[4:8] != b"SBOX":
        raise WindowsProcessError("sandbox specification is invalid")
    if hashlib.sha256(spec).hexdigest() != plan.get("spec_sha256"):
        raise WindowsProcessError("sandbox specification digest does not match")
    env_text = "\0".join(f"{key}={env[key]}" for key in sorted(env, key=str.casefold)) + "\0\0"
    env_bytes = env_text.encode("utf-16-le")
    if hashlib.sha256(env_bytes).hexdigest() != plan.get("environment_block_sha256"):
        raise WindowsProcessError("sandbox environment digest does not match")
    return argv, env_bytes, spec, cwd, identity


def review_windows_candidate(plan: dict[str, Any], *, timeout_seconds: int = 120) -> dict[str, Any]:
    """Review launch fields only; this does not establish OS isolation."""
    _prepare_windows_candidate(plan, timeout_seconds)
    return {"status": "LAUNCH_FIELDS_REVIEWED", "isolation": "NOT_VERIFIED",
            "execution": "NOT_AUTHORIZED", "production_ready": False,
            "publish_authorized": False}


def launch_windows_candidate(plan: dict[str, Any], *, timeout_seconds: int = 120) -> dict[str, Any]:
    """Launch a sandbox process only after a future isolation and grant gate."""
    raise WindowsProcessError("Windows launcher disabled: isolation proof and task grant are not implemented")

    # This prototype remains unreachable until the independently verified
    # isolation boundary and a task-specific authorization gate exist.
    argv, env_bytes, spec, cwd, identity = _prepare_windows_candidate(plan, timeout_seconds)

    # Windows SDK structures, using native pointer size for SIZE_T and HANDLE.
    class StartupInfo(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                    ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                    ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                    ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                    ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                    ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                    ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
                    ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
                    ("hStdError", wintypes.HANDLE)]

    class ProcessInformation(ctypes.Structure):
        _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                    ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]

    class BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in
                    ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                     "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    model = ctypes.WinDLL("processmodel.dll", winmode=0x00000800, use_last_error=True)
    create = model.Experimental_CreateProcessInSandbox
    create.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                       wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
                       ctypes.POINTER(StartupInfo), wintypes.LPCWSTR, ctypes.c_void_p,
                       wintypes.DWORD, ctypes.POINTER(ProcessInformation)]
    create.restype = wintypes.BOOL
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateJobObject.restype = wintypes.BOOL
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    def api_error(stage: str) -> WindowsProcessError:
        # Preserve the Windows error number without collecting process output,
        # environment variables, command lines, or credential material.
        return WindowsProcessError(f"{stage} failed (Windows error {ctypes.get_last_error()})")

    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise api_error("create process job")
    info = ProcessInformation()
    assigned = False
    exited = False
    try:
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x00000008 | 0x00002000  # active process / kill on close
        limits.BasicLimitInformation.ActiveProcessLimit = 1
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise api_error("set process job limits")
        startup = StartupInfo()
        startup.cb = ctypes.sizeof(startup)
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
        # A WCHAR-aligned array preserves exactly the UTF-16 bytes whose digest
        # was recorded; create_unicode_buffer would append an extra terminator.
        environment = (ctypes.c_uint16 * (len(env_bytes) // 2)).from_buffer_copy(env_bytes)
        spec_buffer = ctypes.create_string_buffer(spec)
        flags = 0x00000004 | 0x00000400 | 0x08000000  # suspended / Unicode environment / no window
        if not create(argv[0], command, None, None, False, flags, environment, cwd,
                      ctypes.byref(startup), identity, spec_buffer, len(spec), ctypes.byref(info)):
            raise api_error("Windows sandbox process creation")
        if not kernel.AssignProcessToJobObject(job, info.hProcess):
            raise api_error("attach sandbox process to job")
        assigned = True
        if kernel.ResumeThread(info.hThread) == 0xFFFFFFFF:
            raise api_error("resume sandbox process")
        waited = kernel.WaitForSingleObject(info.hProcess, timeout_seconds * 1000)
        if waited == 0x00000102:
            raise WindowsProcessError("sandbox process timed out")
        if waited != 0:
            raise api_error("wait for sandbox process")
        exited = True
        exit_code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code)):
            raise api_error("read sandbox process exit code")
        return {"status": "EXITED_UNVERIFIED", "exit_code": exit_code.value,
                "execution_proven": False, "production_ready": False, "publish_authorized": False}
    finally:
        termination_confirmed = True
        if info.hProcess:
            if not exited:
                if assigned:
                    kernel.TerminateJobObject(job, 1)
                else:
                    kernel.TerminateProcess(info.hProcess, 1)
            # Even if termination reports success, do not claim cleanup until
            # the process handle is signalled. Closing the job remains the
            # kill-on-close fallback for an attached process.
            termination_confirmed = kernel.WaitForSingleObject(info.hProcess, 5000) == 0
        if info.hThread:
            kernel.CloseHandle(info.hThread)
        if info.hProcess:
            kernel.CloseHandle(info.hProcess)
        kernel.CloseHandle(job)
        if not termination_confirmed:
            raise WindowsProcessError("sandbox process termination could not be confirmed")
