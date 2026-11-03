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
    PROVENANCE,
    REPORT_FILE,
    SPEAK_RATE_ZH,
    Draft,
    ScriptBlocked,
    build,
    check,
    line_seconds,
    topic_provenance,
    write,
)
from .evidence import (  # noqa: F401
    PACK_FILE,
    PACK_SCHEMA,
    EvidenceItem,
    EvidencePack,
    load_pack,
    sufficiency,
)

__all__ = [
    "DRAFT_SCHEMA",
    "LINES_SCHEMA",
    "PACK_FILE",
    "PACK_SCHEMA",
    "PROVENANCE",
    "REPORT_FILE",
    "SPEAK_RATE_ZH",
    "EvidenceItem",
    "EvidencePack",
    "Draft",
    "ScriptBlocked",
    "build",
    "check",
    "line_seconds",
    "load_pack",
    "sufficiency",
    "topic_provenance",
    "write",
]
