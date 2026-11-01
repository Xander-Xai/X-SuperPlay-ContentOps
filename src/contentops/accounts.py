"""One place that knows which kind of account a JSON file is.

`config/accounts/*.json` is not a homogeneous directory. Two files describe
video accounts (`contentops.account-dna/v2`): a film length, a composition that
sums to 100, a palette, a generated `easel.yaml`. The X account is a different
kind of thing entirely — a text account with a post-length budget, an image
target and an editorial score, and no renderer at all.

Bending the video schema around it would make the validator assert facts that
are not true (a 9:16 composition, an Easel render, 100% of a film). So there are
two schemas, and this module is the single place that decides which one a file
is. Four call sites glob the directory; three of them only understand video and
would raise `KeyError` on the X account rather than skip it:

    scripts/build_account_variants.py   load_specs() -> reads narrative/visual
    scripts/check_retention.py          run_account() -> reads a video project
    scripts/export_easel_yaml.py        writes projects/<slug>/easel.yaml

They iterate :func:`video_accounts` so the boundary is declared once. A schema
that is neither is reported by the account checker as a failure, not silently
ignored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple

#: A video account: the shape every video producer and validator already reads.
VIDEO_SCHEMA = "contentops.account-dna/v2"
#: A text account: X posts, card images, editorial review. No renderer.
X_SCHEMA = "contentops.x-account/v1"

VIDEO = "video"
X = "x"
UNKNOWN = "unknown"


def accounts_dir(root: Path) -> Path:
    return Path(root) / "config" / "accounts"


def load_account(path: Path) -> Dict[str, Any]:
    """Read one account document. The caller decides what schema it expects."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def account_kind(dna: Dict[str, Any]) -> str:
    """``"video"``, ``"x"``, or ``"unknown"`` for a schema nothing here owns."""
    schema = dna.get("schema")
    if schema == VIDEO_SCHEMA:
        return VIDEO
    if schema == X_SCHEMA:
        return X
    return UNKNOWN


def iter_accounts(directory: Path | None = None, root: Path | None = None) -> Iterator[Tuple[Path, Dict[str, Any]]]:
    """Every account document, whatever its schema, in stable order."""
    base = Path(directory) if directory is not None else accounts_dir(root or Path(__file__).resolve().parents[2])
    for path in sorted(base.glob("*.json")):
        yield path, load_account(path)


def video_accounts(directory: Path | None = None, root: Path | None = None) -> Iterator[Tuple[Path, Dict[str, Any]]]:
    """Only the accounts the video pipeline can actually read.

    This is not a permission check: an unknown schema is skipped here and refused
    by the account checker, so a stray file still fails loudly somewhere.
    """
    for path, dna in iter_accounts(directory, root):
        if account_kind(dna) == VIDEO:
            yield path, dna
