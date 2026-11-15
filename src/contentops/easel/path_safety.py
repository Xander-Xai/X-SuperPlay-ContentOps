"""Fail-closed detection of links and Windows reparse points."""
from __future__ import annotations

import os
import stat
from pathlib import Path


def is_linklike(path: Path) -> bool:
    """Reject symlinks and all Windows reparse points, including junctions.

    ``Path.is_junction`` is not available on every supported Python version.
    Missing paths are not links; inaccessible paths fail closed.
    """
    try:
        info = Path(path).lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", None)
    if os.name == "nt" and attributes is None:
        return True
    return bool((attributes or 0) & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
