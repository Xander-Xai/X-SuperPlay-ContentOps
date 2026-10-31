"""ContentOps skill layer: execution authorization.

Discovery and resolution live in ``scripts/skill_route.py``. This package holds
only the decision that turns a resolution plus an explicit grant into an
authorized execution. It deliberately re-checks none of the existing gates: the
registry, the adapter's runtime lock verifier and the M5 stage keep their own
authority.
"""

from .authorization import (  # noqa: F401
    Decision,
    ExecutionGrant,
    ExecutionRequest,
    evaluate,
)

__all__ = [
    "Decision",
    "ExecutionGrant",
    "ExecutionRequest",
    "evaluate",
]
