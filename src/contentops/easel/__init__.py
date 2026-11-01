"""Guarded access to the pinned Easel host.

The package deliberately contains no upstream copy. It owns the policy layer
(what may be reached) and the process lifecycle; upstream Easel remains pinned,
read-only and separately verified.
"""

from .guard import GuardMiddleware, HostGuardError, HostPolicy
from .host import HostError, host_status, serve

__all__ = [
    "GuardMiddleware",
    "HostError",
    "HostGuardError",
    "HostPolicy",
    "host_status",
    "serve",
]
