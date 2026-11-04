"""Manual graphic/text packages.

The package validates copy, image facts and rights, then stops for human review.
It is not a platform publisher and contains no HTML renderer.

``cards`` orchestrates the *upstream* card renderer and density audit; it adds
no drawing code and records measurements, never approval.
"""

from .package import (  # noqa: F401
    PACKAGE_SCHEMA,
    GraphicPackageError,
    build_package,
    load_and_build,
    write_package,
)
from .cards import (  # noqa: F401
    CardRenderError,
    build_receipt,
    parse_audit_output,
    parse_render_output,
    plan as plan_cards,
    run as run_cards,
    write_receipt as write_card_receipt,
)

__all__ = [
    "PACKAGE_SCHEMA",
    "GraphicPackageError",
    "build_package",
    "load_and_build",
    "write_package",
    "CardRenderError",
    "build_receipt",
    "parse_audit_output",
    "parse_render_output",
    "plan_cards",
    "run_cards",
    "write_card_receipt",
]
