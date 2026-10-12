"""Decide whether the Founder voice clone may be created — and say why if not.

This is the #34 gate. It runs every check that can be decided **before** the first
byte of the Founder's voice leaves the machine, and it writes a receipt either way.

What it does
------------
1. Resolves the two route credentials separately: ``MINIMAX_CLONE_KEY`` (pay-as-you-go,
   clone only) and the existing Subscription Key (narration only). Absence is an
   answer, not an error.
2. Reads the billing state with the subscription key through :class:`BillingGuard`.
   Read-only; not a generation endpoint.
3. Asks :func:`decide_route` for the verdict, and prints the stop codes.
4. Writes ``founder-voice-route-receipt.json``: credential classes, balances, quota,
   every official citation, and the 168-hour clone lifetime.

What it does not do
-------------------
It does **not** upload, clone or synthesise. It has no code path that reaches
``/v1/files/upload``, ``/v1/voice_clone`` or ``/v1/t2a_v2``. The billable steps live
in :mod:`contentops.media.clone_route`'s caller, and the gate has to be passed first.

Usage
-----
The provider host is **not** committed anywhere in this repository (AGENTS.md
section 8), so supply it locally before running::

    $env:CONTENTOPS_MINIMAX_BASE_URL = "<the CN host from your own account>"
    python scripts/prepare_founder_voice_clone_route.py

With the host unset the script still runs and still refuses: it reports
``HOST_NOT_CONFIGURED`` rather than guessing an endpoint, because the wrong regional
host answers ``2049 invalid api key``, which reads as a broken credential instead of
a misconfigured one.

Exit code ``0`` means the route is authorised. Anything else means it is not, and
the receipt says which of the independent blockers fired.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.billing_guard import BillingGuard  # noqa: E402
from contentops.media.clone_route import (  # noqa: E402
    CLONE_TTL_HOURS,
    ROUTE_AUTHORISED,
    decide_route,
)
from contentops.media.credentials import (  # noqa: E402
    DuplicateCredentialError,
    resolve_two_key_pair,
)

OUT = ROOT / "projects/easel-enhanced-golden/receipts/founder-voice-route-receipt.json"

VOICE_ALIAS = "founder_primary_v1"
PROVIDER_VOICE_ID = "XSuperPlayFounderV1"
SAMPLE_SHA256 = "bb56d052cd637bd8a369f6e37a745c7609de9988ada0fa0827d4d5c59035df8d"


def _measure_billing(tts_key: str) -> Dict[str, Any]:
    """Read balances and plan usage with the subscription key. No generation.

    The credential is passed in rather than resolved here, because the gate has
    already resolved it and the billing proof must authorise with the same secret
    the narration path would use. Re-resolving would make it possible for the two to
    disagree, which is the exact failure :mod:`contentops.media.credentials` exists
    to prevent.
    """
    base_url = ""
    for name in ("CONTENTOPS_MINIMAX_BASE_URL", "MINIMAX_VOICE_CLONE_BASE_URL"):
        base_url = os.environ.get(name, "").strip()
        if base_url:
            break
    if not base_url:
        return {
            "verdict": "HOST_NOT_CONFIGURED",
            "reasons": [
                "CONTENTOPS_MINIMAX_BASE_URL is not set, so no balance could be read. "
                "Endpoint URLs are never committed (AGENTS.md section 8), so this is "
                "supplied locally and an unset host is a hard stop, not a default."
            ],
        }
    guard = BillingGuard(base_url=base_url, credential=tts_key)
    result = guard.evaluate("speech")
    return {
        "verdict": result.verdict,
        "reasons": list(result.reasons),
        "balances": {
            key: value
            for key, value in (result.balances or {}).items()
            if key not in ("base_resp", "balance_alert_switch", "balance_alert_threshold")
        },
        "quota": None
        if result.quota is None
        else {
            "interval_remaining_percent": result.quota.interval_remaining_percent,
            "weekly_remaining_percent": result.quota.weekly_remaining_percent,
            "bucket": result.quota.bucket,
        },
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    print("=== FOUNDER VOICE CLONE ROUTE GATE (read-only) ===")
    print()

    try:
        pair = resolve_two_key_pair()
    except DuplicateCredentialError as exc:
        # Refuse to continue rather than run a one-key route under a two-key name.
        print(f"[STOP] DUPLICATE_ROUTE_KEYS: {exc}")
        return 2

    print("=== CREDENTIALS ===")
    for label, resolved in (("CLONE_KEY", pair.clone), ("TTS_KEY ", pair.tts)):
        print(
            f"  {label} : class={resolved.credential_class:<12} "
            f"source={resolved.source:<24} configured={resolved.usable}"
        )
    print(f"  keys distinct : {pair.safe_metadata()['keys_distinct']}")
    print()

    print("=== BILLING (read-only, subscription key) ===")
    billing = _measure_billing(pair.tts.key)
    print(f"  verdict : {billing['verdict']}")
    for key, value in (billing.get("balances") or {}).items():
        print(f"  {key:<16}: {value}")
    quota = billing.get("quota")
    if quota:
        print(
            f"  quota            : interval {quota['interval_remaining_percent']}% / "
            f"weekly {quota['weekly_remaining_percent']}%"
        )
    for reason in billing["reasons"]:
        print(f"  ! {reason}")
    print()

    decision = decide_route(
        pair,
        billing_verdict=billing["verdict"],
        billing_reasons=billing["reasons"],
        account_verified=None,
        cross_key_verified=None,
    )

    print("=== VERDICT ===")
    print(f"  route       : {decision.route}")
    print(f"  authorised  : {decision.authorised}")
    print(f"  blocked_by  : {', '.join(decision.blocked_by) or '(none)'}")
    for reason in decision.reasons:
        print(f"  - {reason}")
    print()
    print(f"  cloned voices expire after {CLONE_TTL_HOURS}h unless used in a T2A call.")
    print()

    receipt = decision.as_dict()
    receipt["producer"] = "scripts/prepare_founder_voice_clone_route.py"
    receipt["voice_alias"] = VOICE_ALIAS
    receipt["provider_voice_id_hash"] = hashlib.sha256(
        PROVIDER_VOICE_ID.encode("utf-8")
    ).hexdigest()
    receipt["sample_sha256"] = SAMPLE_SHA256
    receipt["measured"] = {
        "billing_verdict": billing["verdict"],
        "billing_reasons": billing["reasons"],
        "balances": billing.get("balances"),
        "quota": billing.get("quota"),
    }
    receipt["calls_performed"] = {
        "upload": 0,
        "clone": 0,
        "tts": 0,
        "billing_reads": 1 if billing["verdict"] != "HOST_NOT_CONFIGURED" else 0,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("wrote", OUT.relative_to(ROOT).as_posix())
    print()

    if decision.authorised:
        print(f"ROUTE {ROUTE_AUTHORISED}. The clone may proceed in one continuous session.")
        return 0
    print("NO SAMPLE WAS TRANSMITTED. No upload, no clone, no synthesis.")
    print(f"NEXT ACTION REQUIRED FROM THE FOUNDER: see {decision.route} above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())