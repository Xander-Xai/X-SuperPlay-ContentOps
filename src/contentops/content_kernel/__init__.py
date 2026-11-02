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

__all__ = [
    "CAPABILITIES",
    "EVIDENCE_ROLES",
    "EXECUTION_PROFILES",
    "PRODUCTION_LANES",
    "BundleError",
    "consumption_summary",
    "load_bundle",
    "validate_bundle",
]
