"""Who the MiniMax M Plan provider is, and what billing it is allowed to do.

Why these constants need one home
---------------------------------
Speech, image and — later — video all run against the same MiniMax M Plan
Explore subscription. They must therefore agree on the provider name, the
product, the plan, the billing mode and the retry cap, because a receipt that
disagreed with its sibling receipt would be unexplainable.

M2 proved these constants inside ``minimax_speech``. M3 needs the same values,
and copying them into the image module would create two places to update and two
chances to drift. They live here instead; both providers import them, and each
still re-exports its own names so existing callers are unaffected.

The values themselves
---------------------
M Plan Explore is a **subscription**. That single fact drives the whole billing
design:

- ``allow_payg`` and ``allow_credit_pack`` are ``False`` and are not
  configuration. They are policy. A key whose prefix says pay-as-you-go must be
  refused before any provider call, because plan entitlement and a paid balance
  are different money and only one of them was budgeted for.
"""

from __future__ import annotations

__all__ = [
    "ALLOW_CREDIT_PACK",
    "ALLOW_PAYG",
    "BILLING_MODE",
    "MAX_ATTEMPTS",
    "PLAN",
    "PRODUCT",
    "PROVIDER_NAME",
]

PROVIDER_NAME = "minimax_m_plan"
PRODUCT = "m_plan"
PLAN = "explore"
BILLING_MODE = "subscription"

#: Hard policy, not a preference. See the module docstring.
ALLOW_PAYG = False
ALLOW_CREDIT_PACK = False

#: Maximum provider generation attempts per asset.
MAX_ATTEMPTS = 2