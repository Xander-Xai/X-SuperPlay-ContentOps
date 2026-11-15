"""Bounded supervision for a future authorized Agent process.

This module never starts a process and does not grant permission or establish
isolation. Its caller must create a dedicated POSIX session, suppress stderr,
and satisfy the existing execution gate and independent isolation checks first.
"""
from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time
from typing import Any

from .agent_result import MAX_RESULT_BYTES


class AgentProcessError(ValueError):
    pass


def supervise_started_process(process: subprocess.Popen, *, timeout_seconds: float) -> dict[str, Any]:
    """Collect bounded stdout from an already-started, dedicated-session child.

    On timeout or excessive output, stop only the child's own process group.
    Raw stderr is never collected. Results carry no execution provenance and
    must be bound to the authorized run by the future caller.
    """
    if os.name != "posix" or not isinstance(process, subprocess.Popen) or process.stdout is None:
        raise AgentProcessError("a POSIX child with captured stdout is required")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 1800:
        raise AgentProcessError("timeout must be between zero and 1800 seconds")
    if process.poll() is None:
        try:
            if os.getpgid(process.pid) != process.pid:
                raise AgentProcessError("child is not the leader of a dedicated process group")
        except ProcessLookupError:
            pass
    fd = process.stdout.fileno()
    os.set_blocking(fd, False)
    selector = selectors.DefaultSelector()
    selector.register(fd, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout_seconds
    chunks = []
    size = 0
    failure = None
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "TIMEOUT"
                break
            for key, _ in selector.select(min(remaining, 0.5)):
                try:
                    data = os.read(key.fd, min(65536, MAX_RESULT_BYTES + 1 - size))
                except BlockingIOError:
                    continue
                if not data:
                    selector.unregister(key.fd)
                    break
                size += len(data)
                if size > MAX_RESULT_BYTES:
                    failure = "OUTPUT_LIMIT"
                    break
                chunks.append(data)
            if failure:
                break
        if failure is None:
            try:
                code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                failure = "TIMEOUT"
        if failure:
            orphaned_pipe = process.poll() is not None and bool(selector.get_map())
            if process.poll() is None:
                try:
                    if os.getpgid(process.pid) == process.pid:
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                return {"status": "TERMINATION_UNCONFIRMED", "reason": failure,
                        "stdout": None, "exit_code": None, "execution_proven": False}
            if orphaned_pipe:
                return {"status": "TERMINATION_UNCONFIRMED", "reason": failure,
                        "stdout": None, "exit_code": process.returncode, "execution_proven": False}
            return {"status": "FAILED", "reason": failure, "stdout": None,
                    "exit_code": process.returncode, "execution_proven": False}
        return {"status": "EXITED", "reason": None, "stdout": b"".join(chunks),
                "exit_code": code, "execution_proven": False}
    finally:
        selector.close()
        process.stdout.close()
