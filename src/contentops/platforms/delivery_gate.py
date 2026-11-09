"""Whether a packed draft may leave the repository.

Why this is a separate module
-----------------------------
Packing a draft is local and reversible. Handing it to an external delivery tool
is neither. The two used to be decided in different places — the packer checked
things, the dispatcher did not — so a draft could be produced honestly and then
pushed by a code path that only looked at whether the file existed.

This module is the single answer to one question: *may this draft be handed to a
delivery tool, and if so, how far?* It reads the one registry and the adapter's
own validation; it does not re-derive platform capability.

The rules, in order of severity
-------------------------------
1. an unregistered platform is refused — the registry is the only list;
2. a draft without the adapter's validation result is refused — delivery
   consumes validation, it never replaces it;
3. a draft claiming ``publish_authorized: true`` is refused — that flag is a
   founder decision recorded elsewhere, never something a draft may assert;
4. a platform whose registry row says delivery is not implemented refuses every
   external handoff, no matter what a local script can technically do;
5. Douyin is refused unconditionally: delegated publishing is not integrated, and
   its official terms add subject eligibility, per-account authorization,
   user-initiated action and an anti-homogenisation rule that this pipeline
   cannot satisfy;
6. WeChat may only reach its draft boundary. Any request whose mode is not
   ``draft`` — a mass send, for instance — is refused.

A refusal is not an error. It is the recorded answer, with reasons, so an
operator can see which condition is unmet instead of guessing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

__all__ = [
    "DRAFT_ONLY",
    "REFUSED",
    "DeliveryDecision",
    "authorize_delivery",
    "load_registry_rows",
]

DRAFT_ONLY = "DRAFT_ONLY"
REFUSED = "REFUSED"

#: Platforms that may never be handed to a delivery tool in this repository.
UNCONDITIONALLY_REFUSED = {
    "douyin": (
        "DOUYIN_DELEGATED_PUBLISHING_NOT_INTEGRATED: the official interface is "
        "limited to authorized government, media and enterprise subjects, requires "
        "per-use user initiation, and prohibits homogenised content; this pipeline "
        "cannot satisfy those conditions"
    ),
}

#: Registry values that mean "no external handoff is possible yet".
NO_DELIVERY_MODES = {"NOT_IMPLEMENTED", ""}
NO_DRAFT_SUPPORT = {"NONE", ""}


@dataclass(frozen=True)
class DeliveryDecision:
    """The recorded answer, never a bare boolean."""

    platform_id: Optional[str]
    outcome: str
    reasons: Tuple[str, ...] = field(default_factory=tuple)
    required_conditions: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def allowed(self) -> bool:
        return self.outcome != REFUSED

    @property
    def may_publish(self) -> bool:
        return False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "platform_id": self.platform_id,
            "outcome": self.outcome,
            "allowed": self.allowed,
            "may_publish": False,
            "reasons": list(self.reasons),
            "required_conditions": list(self.required_conditions),
        }


def load_registry_rows(root: Path) -> List[Dict[str, Any]]:
    """Read the single platform registry. No second list is consulted."""
    path = Path(root) / "config" / "registry" / "platforms.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("platforms")
    if not isinstance(rows, list):
        raise ValueError("platforms.json has no 'platforms' list")
    return [row for row in rows if isinstance(row, dict)]


def _refuse(platform_id: Optional[str], *reasons: str,
            required: Iterable[str] = ()) -> DeliveryDecision:
    return DeliveryDecision(
        platform_id=platform_id,
        outcome=REFUSED,
        reasons=tuple(reasons),
        required_conditions=tuple(required),
    )


def authorize_delivery(
    draft: Dict[str, Any],
    *,
    registry_rows: List[Dict[str, Any]],
    mode: str = "draft",
) -> DeliveryDecision:
    """Decide how far a packed draft may travel.

    Args:
        draft: the packed draft. Must carry ``platform_id``, the adapter's
            ``validation`` result, and ``publish_authorized``.
        registry_rows: rows from the single registry.
        mode: what the caller intends to do — ``draft`` (create a platform
            draft) or anything else, which is treated as publishing.
    """
    if not isinstance(draft, dict):
        return _refuse(None, "DRAFT_NOT_AN_OBJECT")

    platform_id = draft.get("platform_id")
    if not isinstance(platform_id, str) or not platform_id.strip():
        return _refuse(None, "PLATFORM_ID_MISSING")

    if platform_id in UNCONDITIONALLY_REFUSED:
        return _refuse(platform_id, UNCONDITIONALLY_REFUSED[platform_id])

    row = next((r for r in registry_rows if r.get("platform_id") == platform_id), None)
    if row is None:
        return _refuse(
            platform_id, "PLATFORM_NOT_IN_REGISTRY",
            required=("register the platform in config/registry/platforms.json",))

    if draft.get("publish_authorized") is True:
        return _refuse(
            platform_id, "DRAFT_ASSERTS_PUBLISH_AUTHORIZATION",
            required=("publish_authorized must come from founder review, never a draft",))

    validation = draft.get("validation")
    if not isinstance(validation, dict):
        return _refuse(
            platform_id, "MISSING_ADAPTER_VALIDATION",
            required=("run the platform adapter's validate() and carry its result",))
    if validation.get("ok") is not True:
        return _refuse(
            platform_id, "ADAPTER_VALIDATION_FAILED",
            required=tuple(str(e) for e in (validation.get("errors") or [])) or
                     ("adapter validation must pass before delivery",))

    rights = draft.get("rights")
    if not isinstance(rights, dict) or rights.get("cleared") is not True:
        return _refuse(
            platform_id, "RIGHTS_NOT_CLEARED",
            required=("record rights clearance for every asset in the draft",))

    publish_mode = str(row.get("publish_mode") or "")
    draft_support = str(row.get("draft_support") or "")
    if publish_mode in NO_DELIVERY_MODES and draft_support in NO_DRAFT_SUPPORT:
        return _refuse(
            platform_id,
            f"PLATFORM_DELIVERY_NOT_IMPLEMENTED: registry says publish_mode={publish_mode!r}, "
            f"draft_support={draft_support!r}",
            required=("a real adapter with verified evidence must upgrade the registry row first",))

    if platform_id == "wechat_article" and mode != "draft":
        return _refuse(
            platform_id, "WECHAT_MASS_SEND_REFUSED",
            required=("WeChat delivery stops at its draft boundary",))

    if mode != "draft":
        return _refuse(
            platform_id, "PUBLISHING_NOT_INTEGRATED",
            required=("delivery stops at the draft boundary; publishing stays manual",))

    if draft_support in NO_DRAFT_SUPPORT:
        return _refuse(
            platform_id, "PLATFORM_HAS_NO_DRAFT_SUPPORT",
            required=("draft_support must be verified before a draft is created",))

    return DeliveryDecision(platform_id=platform_id, outcome=DRAFT_ONLY)
