"""Bilibili public metrics, read through the official-shaped public API.

Why this module exists
----------------------
``config/registry/platforms.json`` marks every platform row ``metrics: NONE``
and the post-publication numbers were reachable only by hand. This module is
the first automatic ingestion channel, and it deliberately reads the *public*
video statistics — the same counters any visitor sees under a video — through
the public API wrapped by ``Nemo2011/bilibili-api`` (MIT, pinned by install).
It never logs in, never touches the creator centre and never scrapes: creator
-side numbers stay on the manual export path (``contentops.manual_metrics``).

Transport-free by construction
------------------------------
This module never imports ``bilibili_api``, never opens a socket. It shapes and
decides; ``scripts/bilibili_metrics.py`` owns the import and the await, lazily,
only under ``--execute``.

Account DNA is the gate
-----------------------
A bilibili fetch is only allowed for an account whose DNA lists ``bilibili``
in ``platforms``. The current 1024 account lists douyin and xiaohongshu, so a
fetch for it is refused before anything else happens — one account's numbers
must never be attributed to another.

BV resolution mirrors the ``--tid`` chain
----------------------------------------
CLI ``--bvid`` wins, then ``project.yaml`` (``bilibili_bvid`` or
``target.bilibili_bvid``), then the account DNA (``bilibili_bvid`` or
``platform_bilibili_bvid``). The winning layer is recorded in the receipt. If
no layer carries a BV the fetch is blocked — inventing a BV would fetch some
stranger's numbers and present them as ours.

What a receipt may and may not claim
------------------------------------
A receipt records the public counters and nothing else. It states
``modifies_script``, ``modifies_qc`` and ``modifies_production_ready`` as
false: post-publication evidence informs the next round's decision, it never
edits the artefact that produced it. A BV that came from the CLI rather than
the project or the DNA is stamped ``TRANSPORT_SMOKE`` — useful to prove the
pipe works, wrong to read as account performance.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "METRIC_KEYS",
    "MODE_ACCOUNT_DELIVERY",
    "MODE_TRANSPORT_SMOKE",
    "RECEIPT_SCHEMA",
    "bvid_source_layer",
    "build_receipt",
    "dna_allows",
    "resolve_bvid",
    "shape_video_stats",
    "validate_bvid",
]

PLATFORM = "bilibili"
RECEIPT_SCHEMA = "contentops.bilibili-metrics/v1"
MODE_ACCOUNT_DELIVERY = "ACCOUNT_DELIVERY"
MODE_TRANSPORT_SMOKE = "TRANSPORT_SMOKE"

#: Counters the public video info exposes and this line records. A counter the
#: API does not return stays missing — no zero-fill.
METRIC_KEYS = ("view", "danmaku", "reply", "favorite", "coin", "share", "like")

_BVID = re.compile(r"^BV[0-9A-Za-z]{10}$")


def dna_allows(dna: Dict[str, Any]) -> Tuple[bool, str]:
    """Only an account whose DNA lists ``bilibili`` may fetch bilibili metrics."""
    platforms = dna.get("platforms") or []
    names = {str(p).strip().lower() for p in platforms if isinstance(p, str)}
    if "bilibili" in names:
        return True, "dna.platforms lists bilibili"
    return False, (
        "dna.platforms = "
        + (", ".join(sorted(names)) if names else "(empty)")
        + "; bilibili metrics are refused for this account"
    )


def validate_bvid(bvid: str) -> Optional[str]:
    """A reason string when the BV is malformed, else ``None``."""
    value = str(bvid or "").strip()
    if not value:
        return "bvid is empty"
    if not _BVID.match(value):
        return (
            "bvid is malformed: expected BV + 10 alphanumerics, got "
            + (value if len(value) <= 40 else value[:40] + "…")
        )
    return None


def bvid_source_layer(cli_bvid: str, project_cfg: Dict[str, Any], dna: Dict[str, Any]) -> Tuple[str, str, str]:
    """Resolve the BV and name the layer it came from.

    Returns ``(bvid, source, reason)``. ``source`` is one of
    ``cli``, ``project``, ``dna`` or ``"none"``; ``reason`` explains a
    ``"none"`` result. The CLI layer is recorded as a transport smoke, the
    project and DNA layers as account delivery — that distinction is the
    whole point of keeping the layers apart.
    """
    cli_value = str(cli_bvid or "").strip()
    if cli_value:
        return cli_value, "cli", "bvid came from the command line"

    for path in ("bilibili_bvid",):
        value = str(project_cfg.get(path) or "").strip()
        if value:
            return value, "project", f"bvid came from project.{path}"
    target = project_cfg.get("target") or {}
    if isinstance(target, dict):
        value = str(target.get("bilibili_bvid") or "").strip()
        if value:
            return value, "project", "bvid came from project.target.bilibili_bvid"

    for path in ("bilibili_bvid", "platform_bilibili_bvid"):
        value = str(dna.get(path) or "").strip()
        if value:
            return value, "dna", f"bvid came from dna.{path}"

    return "", "none", (
        "no BV anywhere: pass --bvid, or write bilibili_bvid into "
        "project.yaml, or into the account DNA"
    )


def resolve_bvid(
    cli_bvid: str, project_cfg: Dict[str, Any], dna: Dict[str, Any]
) -> Tuple[str, str, str, List[str]]:
    """Full resolution: layer, blockers, format validation.

    Returns ``(bvid, source, reason, blockers)``. A CLI or project or DNA BV
    that fails format validation produces a blocker — the pipeline stops
    instead of fetching whatever the malformed string happens to match.
    """
    bvid, source, reason = bvid_source_layer(cli_bvid, project_cfg, dna)
    blockers: List[str] = []
    if source == "none":
        blockers.append(reason)
        return "", source, reason, blockers
    problem = validate_bvid(bvid)
    if problem:
        blockers.append(f"bvid from {source}: {problem}")
    return bvid, source, reason, blockers


def shape_video_stats(stat: Dict[str, Any]) -> Tuple[Dict[str, int], List[str]]:
    """Pick the public counters out of the API response.

    A key the response omits stays missing. A non-integer value is refused and
    named — a number that arrived as a string or a float could be a schema
    change, and silently coercing it would hide that.
    """
    metrics: Dict[str, int] = {}
    problems: List[str] = []
    for key in METRIC_KEYS:
        if key not in stat:
            continue
        value = stat[key]
        if isinstance(value, bool) or not isinstance(value, int):
            problems.append(f"stat.{key} is {type(value).__name__}, expected int")
            continue
        if value < 0:
            problems.append(f"stat.{key} is negative")
            continue
        metrics[key] = value
    return metrics, problems


def build_receipt(
    account_slug: str,
    bvid: str,
    bvid_source: str,
    metrics: Dict[str, int],
    fetched_at: str,
    title: str = "",
    problems: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """The receipt: what was read, from where, and what it must not touch."""
    mode = MODE_TRANSPORT_SMOKE if bvid_source == "cli" else MODE_ACCOUNT_DELIVERY
    receipt: Dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "platform": PLATFORM,
        "channel": "api_public",
        "account_slug": str(account_slug or ""),
        "bvid": bvid,
        "bvid_source": bvid_source,
        "mode": mode,
        "fetched_at": fetched_at,
        "metrics": dict(metrics),
        "upstream": {
            "project": "Nemo2011/bilibili-api",
            "license": "MIT",
            "note": "public video info; no login, no creator centre, no scraping",
        },
        "modifies_script": False,
        "modifies_qc": False,
        "modifies_production_ready": False,
    }
    if title:
        receipt["title"] = str(title)
    if problems:
        receipt["issues"] = list(problems)
    return receipt
