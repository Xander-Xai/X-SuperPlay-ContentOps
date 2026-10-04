"""Resolve the provider credential exactly once, and bind that one value.

The invariant this module exists to protect
------------------------------------------
```
THE CREDENTIAL AUTHORISED BY BILLINGGUARD
MUST BE
THE CREDENTIAL THE PROVIDER TRANSPORT ACTUALLY USES
```

The risk it closes
------------------
ContentOps and the official CLI each have their own credential discovery. If
ContentOps resolves ``MINIMAX_SUBSCRIPTION_KEY`` for the billing gate while the
``mmx`` child independently falls back to ``~/.mmx/config.json``, the gate can
authorise key **A** while the provider spends key **B**. Every balance check would
then pass while an unplanned credential did the work. "BillingGuard said SAFE, so
whatever mmx uses is probably fine" is exactly the reasoning this module forbids.

How it is enforced
------------------
1. :func:`resolve_credential` runs **once** per invocation and returns a
   :class:`ResolvedCredential`.
2. The same private value feeds both :class:`~contentops.media.billing_guard.BillingGuard`
   and the child transport.
3. The value is handed to the child through a **child-only environment**, never
   on argv, because argv is observable to anything on the host.
4. If the authorised credential cannot be bound into the child, generation
   **fails**. It never falls back to an ambient or stored credential.

The private value never leaves this module except as the ``key`` attribute, which
is deliberately excluded from ``__repr__``, ``__str__`` and serialisation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = [
    "CREDENTIAL_ABSENT",
    "CREDENTIAL_PAYG",
    "CREDENTIAL_SUBSCRIPTION",
    "CREDENTIAL_UNKNOWN",
    "CredentialBindingError",
    "ResolvedCredential",
    "SOURCE_MMX_CONFIG",
    "SOURCE_NONE",
    "SOURCE_SUBSCRIPTION_ENV",
    "child_env_for",
    "classify_credential",
    "resolve_credential",
]

CREDENTIAL_SUBSCRIPTION = "SUBSCRIPTION"
CREDENTIAL_PAYG = "PAYG"
CREDENTIAL_ABSENT = "ABSENT"
CREDENTIAL_UNKNOWN = "UNKNOWN"

SOURCE_SUBSCRIPTION_ENV = "MINIMAX_SUBSCRIPTION_KEY_ENV"
SOURCE_API_KEY_ENV = "MINIMAX_API_KEY_ENV"
SOURCE_MMX_CONFIG = "MMX_CONFIG"
SOURCE_NONE = "NONE"

#: The variable the official CLI reads. The authorised key is injected here.
CHILD_CREDENTIAL_ENV = "MINIMAX_API_KEY"


class CredentialBindingError(RuntimeError):
    """The authorised credential could not be bound to the transport.

    Raised instead of falling back to an ambient credential. A generation that
    cannot prove which key it used must not happen.
    """


def classify_credential(key: Optional[str]) -> str:
    """Classify a credential by prefix family without revealing it."""
    if not key:
        return CREDENTIAL_ABSENT
    if key.startswith("sk-cp-"):
        return CREDENTIAL_SUBSCRIPTION
    if key.startswith("sk-api-"):
        return CREDENTIAL_PAYG
    if key.startswith("sk-"):
        return CREDENTIAL_UNKNOWN
    return CREDENTIAL_UNKNOWN


@dataclass(frozen=True)
class ResolvedCredential:
    """One resolved credential: a private value plus safe metadata.

    ``key`` never appears in ``repr``, in ``str``, in a receipt, in an attempt
    record or in any exception message.
    """

    key: str = ""
    credential_class: str = CREDENTIAL_ABSENT
    source: str = SOURCE_NONE

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"ResolvedCredential(credential_class={self.credential_class!r}, "
            f"source={self.source!r}, key=<redacted>)"
        )

    __str__ = __repr__

    @property
    def usable(self) -> bool:
        return bool(self.key)

    def safe_metadata(self) -> Dict[str, str]:
        """Metadata that is safe to log, print or persist."""
        return {
            "credential_class": self.credential_class,
            "credential_source": self.source,
        }


def _from_mmx_config() -> tuple:
    config = Path.home() / ".mmx" / "config.json"
    if not config.is_file():
        return "", SOURCE_NONE
    try:
        payload = json.loads(config.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return "", SOURCE_NONE
    if not isinstance(payload, dict):
        return "", SOURCE_NONE
    return str(payload.get("api_key") or ""), SOURCE_MMX_CONFIG


def resolve_credential(env: Optional[Dict[str, str]] = None) -> ResolvedCredential:
    """Resolve the credential once, in a fixed, documented order.

    Order: ``MINIMAX_SUBSCRIPTION_KEY``, then ``MINIMAX_API_KEY``, then the
    official CLI's own config file. Only the first two make ContentOps the
    authority; the config file is the last resort and is recorded as such,
    because a stored credential is the one most likely to drift from what the
    operator intended.
    """
    environ = dict(os.environ if env is None else env)

    subscription = environ.get("MINIMAX_SUBSCRIPTION_KEY", "").strip()
    if subscription:
        return ResolvedCredential(
            key=subscription,
            credential_class=classify_credential(subscription),
            source=SOURCE_SUBSCRIPTION_ENV,
        )

    api_key = environ.get("MINIMAX_API_KEY", "").strip()
    if api_key:
        return ResolvedCredential(
            key=api_key,
            credential_class=classify_credential(api_key),
            source=SOURCE_API_KEY_ENV,
        )

    stored, source = _from_mmx_config()
    if stored:
        return ResolvedCredential(
            key=stored,
            credential_class=classify_credential(stored),
            source=source,
        )

    return ResolvedCredential(
        key="", credential_class=CREDENTIAL_ABSENT, source=SOURCE_NONE
    )


def child_env_for(
    resolved: ResolvedCredential, base_env: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """Build the child-only environment that binds the authorised credential.

    Raises:
        CredentialBindingError: there is no authorised credential to bind. The
            caller must fail rather than let the child discover one on its own.
    """
    if not resolved.usable:
        raise CredentialBindingError(
            "no authorised credential to bind into the provider transport; "
            f"resolved source={resolved.source} class={resolved.credential_class}. "
            "Refusing to let the child fall back to an ambient credential."
        )
    child = dict(os.environ if base_env is None else base_env)
    child[CHILD_CREDENTIAL_ENV] = resolved.key
    # The subscription variable would otherwise shadow nothing but could mislead
    # a future reader into thinking it was the one in force.
    child.pop("MINIMAX_SUBSCRIPTION_KEY", None)
    return child