"""Guarded access to the pinned Easel host.

The package deliberately contains no upstream copy. It owns the policy layer
(what may be reached) and the process lifecycle; upstream Easel remains pinned,
read-only and separately verified.
"""

from .driver import (
    DriverError,
    build_plan,
    detect_hosts,
    next_step,
    run_step,
)
from .guard import GuardMiddleware, HostGuardError, HostPolicy
from .host import HostError, host_status, serve

__all__ = [
    "DriverError",
    "GuardMiddleware",
    "HostError",
    "HostGuardError",
    "HostPolicy",
    "build_plan",
    "detect_hosts",
    "host_status",
    "next_step",
    "run_step",
    "serve",
]
