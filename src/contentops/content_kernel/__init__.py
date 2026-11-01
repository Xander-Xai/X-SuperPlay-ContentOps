"""Consumption-side contract for the Strategy Content Kernel and Content Bundle.

Strategy owns the Bundle template and every routing decision inside it. This
package only checks that a record is intact enough to consume, and never
re-derives a thesis, a lane or a platform choice.
"""

from .bundle import (  # noqa: F401
    CAPABILITIES,
    EVIDENCE_ROLES,
    EXECUTION_PROFILES,
    PRODUCTION_LANES,
    BundleError,
    consumption_summary,
    load_bundle,
    validate_bundle,
)
from .handoff import (  # noqa: F401
    FORMATS,
    GRAPHIC_TEXT,
    HANDOFF_SCHEMA,
    VIDEO,
    HandoffError,
    build_handoff,
    bundle_digest,
    handoff_filename,
    load_bundle_for_handoff,
    write_handoff,
)

__all__ = [
    "CAPABILITIES",
    "EVIDENCE_ROLES",
    "EXECUTION_PROFILES",
    "FORMATS",
    "GRAPHIC_TEXT",
    "HANDOFF_SCHEMA",
    "PRODUCTION_LANES",
    "VIDEO",
    "BundleError",
    "HandoffError",
    "build_handoff",
    "bundle_digest",
    "consumption_summary",
    "handoff_filename",
    "load_bundle",
    "load_bundle_for_handoff",
    "validate_bundle",
    "write_handoff",
]
