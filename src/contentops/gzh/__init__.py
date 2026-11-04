"""The GZH workflow adapter: locate, verify, describe. Never execute.

The vendored GZH tree is not redistributed by this repository (Issue #56), so
this package carries only the seam described in :mod:`contentops.gzh.runtime`.
"""

from .runtime import (  # noqa: F401
    BLOCKED,
    GzhBlocked,
    LOCK_PATH,
    PLAN_SCHEMA,
    REQUIRED_IDENTITY,
    ROOT_ENV,
    SCHEMA,
    STATUS_SCHEMA,
    VERIFIED,
    load_lock,
    locate_root,
    plan,
    status,
    verify,
)

__all__ = [
    "BLOCKED",
    "GzhBlocked",
    "LOCK_PATH",
    "PLAN_SCHEMA",
    "REQUIRED_IDENTITY",
    "ROOT_ENV",
    "SCHEMA",
    "STATUS_SCHEMA",
    "VERIFIED",
    "load_lock",
    "locate_root",
    "plan",
    "status",
    "verify",
]
