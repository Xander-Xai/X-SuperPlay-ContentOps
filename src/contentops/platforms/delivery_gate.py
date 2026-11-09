"""Whether a packed graphic draft may be handed to an external delivery tool.

Why this is a separate module
-----------------------------
Packing a draft is local and reversible. Handing it to a browser bridge is
neither: the bridge types into a logged-in session and creates a real platform
draft. ``scripts/graphic_deliver.py`` used to print ``NOTE hard blockers present
(仍会尝试投递)`` and then deliver anyway — validation was advisory, so the only
thing standing between a failing draft and a platform was a human reading the
log. This module makes validation a precondition instead of a comment.

What it governs, and what it deliberately does not
--------------------------------------------------
It governs the hand-off to a channel that can create a **draft**. It is not a
publication authority: no branch here authorises a mass send, an API publish or
a direct post.

The registry's ``publish_mode: NOT_IMPLEMENTED`` is a claim that *this
repository* implements no platform publication API. It is not a claim that no
draft channel exists — ``config/platforms/graphic-platforms.yaml`` declares those
channels explicitly, and the CSDN bridge has created real drafts. So the gate
reads the channel declaration for draft capability and reads ``publish_mode``
only to refuse publication modes.

The rules, in order of severity
-------------------------------
1. an unregistered platform is refused — the registry is the only list;
2. a draft with hard blockers is refused — delivery consumes validation, it
   never replaces it;
3. a draft asserting ``publish_authorized: true`` is refused — that is a founder
   decision recorded elsewhere, never something a draft may assert;
4. Douyin is refused unconditionally: delegated publishing is not integrated and
   its official terms add subject eligibility, per-account authorisation,
   user-initiated action and an anti-homogenisation rule this pipeline cannot
   satisfy;
5. any mode other than ``draft`` is refused — a mass send is a different action
   with a different consequence;
6. a platform with no draft-capable channel is refused, naming the channels it
   does have.

A refusal is not an error. It is the recorded answer, with reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import graphic_specs

__all__ = [
    "DRAFT_ONLY",
    "REFUSED",
    "Decision",
    "authorize_delivery",
]

DRAFT_ONLY = "DRAFT_ONLY"
REFUSED = "REFUSED"

#: Platforms whose delegated publishing may never be handed to a tool here.
UNCONDITIONALLY_REFUSED = {
    "douyin": (
        "DOUYIN_DELEGATED_PUBLISHING_NOT_INTEGRATED: the official interface is "
        "limited to authorised government, media and enterprise subjects, requires "
        "per-use user initiation, and prohibits homogenised content; this pipeline "
        "cannot satisfy those conditions"
    ),
}


@dataclass(frozen=True)
class Decision:
    """The recorded answer, never a bare boolean."""

    platform_id: str
    outcome: str
    reasons: tuple[str, ...] = field(default_factory=tuple)
    required_conditions: tuple[str, ...] = field(default_factory=tuple)
    channel: str = ""

    @property
    def allowed(self) -> bool:
        return self.outcome != REFUSED

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform_id": self.platform_id,
            "outcome": self.outcome,
            "reasons": list(self.reasons),
            "required_conditions": list(self.required_conditions),
            "channel": self.channel,
        }


def _draft_channel(platform_id: str) -> dict[str, Any] | None:
    """The first declared channel that can create a draft."""
    for channel in graphic_specs.channels(platform_id):
        if channel.get("draft_only"):
            return channel
    return None


def authorize_delivery(
    platform_id: str,
    *,
    blockers: list[str] | tuple[str, ...] = (),
    publish_authorized_claim: bool = False,
    mode: str = "draft",
) -> Decision:
    """Decide whether one packed draft may go to a delivery channel."""
    policy = UNCONDITIONALLY_REFUSED.get(platform_id)
    if policy:
        # Checked before registry membership on purpose: Douyin is not a graphic
        # platform at all, so reporting "unknown platform" would hide the real
        # reason and invite someone to "fix" it by adding a spec row.
        return Decision(platform_id, REFUSED, (policy,))

    try:
        registered = platform_id in graphic_specs.platform_ids()
    except graphic_specs.SpecError:
        registered = False

    if not registered:
        return Decision(platform_id, REFUSED, ("UNKNOWN_PLATFORM: 不在平台规格表内",))

    if str(mode).lower() != "draft":
        return Decision(
            platform_id, REFUSED,
            (f"MODE_NOT_AUTHORIZED: 只允许草稿边界，收到 {mode!r}；群发/直发是另一种动作",),
            ("mode=draft",),
        )

    if publish_authorized_claim:
        return Decision(
            platform_id, REFUSED,
            ("DRAFT_ASSERTS_AUTHORIZATION: publish_authorized 只能由创始人决定，草稿本身无权声明",),
        )

    if blockers:
        return Decision(
            platform_id, REFUSED,
            (f"DRAFT_HAS_HARD_BLOCKERS: {len(blockers)} 项未解决 — " + "; ".join(str(b) for b in blockers),),
            ("resolve-core-blockers",),
        )

    channel = _draft_channel(platform_id)
    if channel is None:
        available = [str(c.get("id")) for c in graphic_specs.channels(platform_id)]
        return Decision(
            platform_id, REFUSED,
            (f"NO_DRAFT_CHANNEL: 该平台没有 draft_only 通道；已声明 {available or '无'}",),
        )

    return Decision(platform_id, DRAFT_ONLY, ("DRAFT_BOUNDARY: 仅创建平台草稿",), (), str(channel.get("id")))
