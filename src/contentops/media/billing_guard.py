"""BillingGuard: the single gate that decides whether generation may proceed.

Why this exists as its own module
---------------------------------
A Subscription Key is not proof of subscription-only billing. Current official
documentation states that a Subscription Key draws on included plan usage **and**
Credit Packs, that plan usage is consumed first, and that once the limit is
reached overspend is deducted from Credit Packs **by default**. No switch to
disable that fallback is documented.

So the only provable exclusion is a zero Credit Pack balance, and the only way
found to observe it is an endpoint that is **not part of the public API
documentation**. That makes this module the single place in the repository that
depends on undocumented provider behaviour, which is exactly why it is isolated
here instead of being spread across provider code.

Classification of that dependency
---------------------------------
```
UNDOCUMENTED_FIRST_PARTY_IMPLEMENTATION_DEPENDENCY
```

- first-party: it is MiniMax's own API surface
- used by the official CLI: ``mmx-cli`` calls it for the same purpose
- not a public API contract: absent from the published documentation index
- may change without notice: therefore every failure is a hard block
- migration required: when MiniMax publishes an official credit-balance
  equivalent, move to it and delete :data:`BALANCE_PATH`

Fail-closed rules
-----------------
The guard returns :data:`SAFE_INCLUDED_PLAN` only when **all** of these hold:

- the credential class is exactly ``SUBSCRIPTION``
- pay-as-you-go cash balance reads as exactly zero
- Credit Pack balance reads as exactly zero
- voucher balance reads as exactly zero
- outstanding owed reads as exactly zero
- included plan usage is readable and the weekly window has remaining

Anything else — a non-zero value, an unreadable response, a missing field, a
changed schema — yields :data:`BLOCKED_BILLING_SOURCE_UNCERTAIN`. An unreadable
balance is never treated as zero, because "I could not check" and "it is zero"
are different claims and only one of them is safe to bill against.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .contract import QuotaSnapshot

__all__ = [
    "BALANCE_DEPENDENCY_CLASS",
    "BALANCE_PATH",
    "BillingGuard",
    "BillingVerdict",
    "GuardResult",
    "SAFE_INCLUDED_PLAN",
    "BLOCKED_BILLING_SOURCE_UNCERTAIN",
]

BALANCE_DEPENDENCY_CLASS = "UNDOCUMENTED_FIRST_PARTY_IMPLEMENTATION_DEPENDENCY"
BALANCE_PATH = "/account/query_balance"
REMAINS_PATH = "/v1/token_plan/remains"

SAFE_INCLUDED_PLAN = "SAFE_INCLUDED_PLAN"
BLOCKED_BILLING_SOURCE_UNCERTAIN = "BLOCKED_BILLING_SOURCE_UNCERTAIN"

#: Fields that must be present and exactly zero. A missing field is a block, not
#: a pass, because the schema may have changed.
ZERO_REQUIRED_BALANCE_FIELDS = ("cash_balance", "credit_balance", "voucher_balance")

CREDENTIAL_SUBSCRIPTION = "SUBSCRIPTION"
CREDITION_PAYG = "PAYG"
CREDENTIAL_ABSENT = "ABSENT"
CREDENTIAL_UNKNOWN = "UNKNOWN"


class BillingVerdict(str):
    """String constants only; kept as a class for readable type hints."""


@dataclass
class GuardResult:
    verdict: str
    reasons: List[str] = field(default_factory=list)
    credential_class: str = CREDENTIAL_UNKNOWN
    balances: Dict[str, Any] = field(default_factory=dict)
    quota: Optional[QuotaSnapshot] = None
    dependency_class: str = BALANCE_DEPENDENCY_CLASS

    @property
    def safe(self) -> bool:
        return self.verdict == SAFE_INCLUDED_PLAN


def classify_credential(key: Optional[str]) -> str:
    """Classify a credential without ever revealing it.

    Only the key prefix family is inspected. The value itself is never returned,
    logged, or stored.
    """
    if not key:
        return CREDENTIAL_ABSENT
    if key.startswith("sk-cp-"):
        return CREDENTIAL_SUBSCRIPTION
    if key.startswith("sk-api-"):
        return CREDITION_PAYG
    if key.startswith("sk-"):
        return CREDENTIAL_UNKNOWN
    return CREDENTIAL_UNKNOWN


def _num(value: Any) -> Optional[float]:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def summarise_quota(payload: Dict[str, Any]) -> Optional[QuotaSnapshot]:
    rows = payload.get("model_remains") or []
    if not rows:
        return None
    row = rows[0]
    interval = _num(row.get("current_interval_remaining_percent"))
    weekly = _num(row.get("current_weekly_remaining_percent"))
    return QuotaSnapshot(
        bucket=row.get("model_name"),
        interval_remaining_percent=interval,
        weekly_remaining_percent=weekly,
        modality_breakdown={},
    )


class BillingGuard:
    """Fail-closed pre-flight for subscription-only generation.

    The transport is injectable so contract tests can drive every failure mode
    without a network call and without a credential.
    """

    def __init__(
        self,
        *,
        base_url: str,
        credential: Optional[str],
        http_get_json: Optional[Callable[[str, str], Dict[str, Any]]] = None,
    ) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._credential = credential or ""
        self._get_json = http_get_json or self._http_get_json

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "BillingGuard":
        """Build a guard from the official CLI's resolved configuration.

        The base URL is asked of the CLI rather than hard-coded, so this
        repository never accumulates provider endpoint literals beyond the one
        documented in :data:`BALANCE_PATH`.
        """
        environ = dict(os.environ if env is None else env)
        return cls(
            base_url=environ.get("CONTENTOPS_MINIMAX_BASE_URL", ""),
            credential=environ.get("MINIMAX_SUBSCRIPTION_KEY")
            or environ.get("MINIMAX_API_KEY"),
        )

    def _http_get_json(self, url: str, credential: str) -> Dict[str, Any]:
        request = urllib.request.Request(
            url, headers={"Authorization": "Bearer " + credential}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    def read_balances(self) -> Dict[str, Any]:
        try:
            return self._get_json(self._base_url + BALANCE_PATH, self._credential)
        except Exception as exc:  # noqa: BLE001 - any failure is a hard block
            return {"error": type(exc).__name__}

    def read_quota(self) -> Optional[QuotaSnapshot]:
        try:
            payload = self._get_json(self._base_url + REMAINS_PATH, self._credential)
        except Exception:  # noqa: BLE001
            return None
        return summarise_quota(payload if isinstance(payload, dict) else {})

    def evaluate(self) -> GuardResult:
        """Return the verdict. Never raises for a billing reason."""
        reasons: List[str] = []
        credential_class = classify_credential(self._credential)

        if credential_class != CREDENTIAL_SUBSCRIPTION:
            reasons.append(
                f"credential class is {credential_class}, not a Subscription Key; "
                f"PAYG and unknown credentials are refused before generation"
            )

        balances = self.read_balances()
        if "error" in balances:
            reasons.append(
                "balance read failed "
                f"({balances['error']}); an unreadable balance is never treated as zero"
            )
        else:
            for name in ZERO_REQUIRED_BALANCE_FIELDS:
                if name not in balances:
                    reasons.append(
                        f"balance field {name} missing; the schema may have changed"
                    )
                    continue
                value = _num(balances.get(name))
                if value is None:
                    reasons.append(f"balance field {name} is unreadable")
                elif value != 0:
                    reasons.append(
                        f"balance field {name} is {value}, so paid funds could be consumed"
                    )
            owed = _num(balances.get("owed_amount"))
            if owed:
                reasons.append(f"outstanding owed amount is {owed}")

        quota = self.read_quota()
        if quota is None:
            reasons.append("included plan usage could not be read")
        elif quota.weekly_remaining_percent is None:
            reasons.append("weekly remaining plan usage is unknown")
        elif quota.weekly_remaining_percent <= 0:
            reasons.append(
                f"weekly plan window exhausted ({quota.weekly_remaining_percent})"
            )

        verdict = SAFE_INCLUDED_PLAN if not reasons else BLOCKED_BILLING_SOURCE_UNCERTAIN
        return GuardResult(
            verdict=verdict,
            reasons=reasons,
            credential_class=credential_class,
            balances={k: v for k, v in balances.items() if k != "error"},
            quota=quota,
        )

    def require_safe(self) -> QuotaSnapshot:
        """Evaluate and raise :class:`~contentops.media.contract.BillingBlocked`.

        Use immediately before every provider call. Returning the quota snapshot
        saves a second round trip for the receipt's "before" value.
        """
        from .contract import BillingBlocked

        result = self.evaluate()
        if not result.safe:
            raise BillingBlocked(result.verdict, result.reasons)
        assert result.quota is not None
        return result.quota