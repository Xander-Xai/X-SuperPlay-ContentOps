"""The script stage: an approved brief becomes the copy and the storyboard.

The module ``draft`` owns the transformation and its refusals. It is not a text
generator: it cannot invent a fact, a number or a quotation, because there is
no model call in it. Every line it writes is a transition, a statement about
what a cited source says about itself (with the limitation stated), or an
explicit judgement.

See ``draft.py`` for the contract and the reasons.
"""

from .draft import (  # noqa: F401
    DRAFT_SCHEMA,
    LINES_SCHEMA,
    REPORT_FILE,
    Draft,
    ScriptBlocked,
    build,
    check,
    write,
)

__all__ = [
    "DRAFT_SCHEMA",
    "LINES_SCHEMA",
    "REPORT_FILE",
    "Draft",
    "ScriptBlocked",
    "build",
    "check",
    "write",
]
