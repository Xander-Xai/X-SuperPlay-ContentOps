"""Manual graphic/text packages.

The package validates copy, image facts and rights, then stops for human review.
It is not a platform publisher and contains no HTML renderer.
"""

from .package import (  # noqa: F401
    PACKAGE_SCHEMA,
    GraphicPackageError,
    build_package,
    load_and_build,
    write_package,
)

__all__ = [
    "PACKAGE_SCHEMA",
    "GraphicPackageError",
    "build_package",
    "load_and_build",
    "write_package",
]
