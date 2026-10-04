#!/usr/bin/env python3
"""Generate one image through the MiniMax M Plan image provider.

Ops entry point for Issue #20. Business logic lives in
``src/contentops/media/``; this script only wires the CLI, the credential and the
output locations.

What it will not do
-------------------
- generate if the billing source cannot be proven included-plan-only
- print a credential, a credential fragment or an Authorization header
- mark anything ``production_ready``: a generated image always awaits human review
- let a generated image be registered as evidence
- guess the container from a file extension

Usage
-----
```
python scripts/generate_image.py --prompt "abstract data paths" --out-dir .verify-tmp/m3
python scripts/generate_image.py --prompt "..." --width 768 --height 1360 --seed 42
python scripts/generate_image.py --prompt "..." --health
```

Credential resolution, in order:
1. ``MINIMAX_SUBSCRIPTION_KEY`` (preferred)
2. ``MINIMAX_API_KEY``
3. the official CLI's own config file, without printing the value

The resolved value is used **once**: the same key authorises the billing gate and
is injected into the ``mmx`` child environment. It is never placed on argv.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from process_utils import hidden_run  # noqa: E402

from contentops.media.billing_guard import BillingGuard  # noqa: E402
from contentops.media.credentials import (  # noqa: E402
    CredentialBindingError,
    resolve_credential,
)
from contentops.media.contract import BillingBlocked  # noqa: E402
from contentops.media.image_contract import (  # noqa: E402
    AssetKind,
    AssetRegistry,
    EvidenceUse,
    register_asset,
)
from contentops.media.image_fingerprint import DimensionRejected  # noqa: E402
from contentops.media.minimax_image import (  # noqa: E402
    DEFAULT_IMAGE_MODEL,
    PRIMARY_PORTRAIT_HEIGHT,
    PRIMARY_PORTRAIT_WIDTH,
    MiniMaxMPlanImageProvider,
    receipt_to_dict,
)
from contentops.media.transport import resolve_cli  # noqa: E402


#: Optional override for the billing API base. Normally resolved by asking the
#: official CLI. It exists so a test can point the gate at a local stub instead of
#: contacting the provider; production leaves it unset.
BASE_URL_ENV_VAR = "CONTENTOPS_MINIMAX_BASE_URL"


def resolve_base_url() -> str:
    override = os.environ.get(BASE_URL_ENV_VAR, "").strip()
    if override:
        return override
    cli = resolve_cli()
    if not cli:
        return ""
    prefix = list(cli) if isinstance(cli, (list, tuple)) else [cli]
    result = hidden_run(prefix + ["config", "show", "--output", "json"], timeout=60)
    if result.returncode != 0:
        return ""
    try:
        return str(json.loads(result.stdout or "{}").get("base_url") or "")
    except json.JSONDecodeError:
        return ""


def build_guard(resolved) -> BillingGuard:
    """The gate authorises exactly the credential the transport will use."""
    return BillingGuard(base_url=resolve_base_url(), credential=resolved.key)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prompt", default="", help="what the image should show")
    parser.add_argument(
        "--prompt-file", default="", help="read the prompt from a UTF-8 file"
    )
    parser.add_argument("--out-dir", default=".verify-tmp/m3", help="output directory")
    parser.add_argument("--model", default=DEFAULT_IMAGE_MODEL)
    parser.add_argument("--width", type=int, default=PRIMARY_PORTRAIT_WIDTH)
    parser.add_argument("--height", type=int, default=PRIMARY_PORTRAIT_HEIGHT)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--force", action="store_true", help="regenerate instead of reusing the cache"
    )
    parser.add_argument("--retry-from", default="", help="attempt record of a failed attempt 1")
    parser.add_argument("--retry-reason", default="", help="why attempt 2 differs")
    parser.add_argument(
        "--health", action="store_true", help="report reachability and billing only"
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    prompt = args.prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")

    # Resolved once. The gate and the child transport share this one value, so an
    # ambient ~/.mmx credential can never silently become the key in force.
    resolved = resolve_credential()
    guard = build_guard(resolved)
    provider = MiniMaxMPlanImageProvider(
        guard=guard,
        work_dir=Path(args.out_dir),
        cli=resolve_cli(),
        model=args.model,
        transport_credential=resolved,
    )

    if args.health:
        print(
            json.dumps(
                {"health": provider.health(), "capabilities": provider.capabilities()},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if not prompt.strip():
        print(
            json.dumps(
                {"status": "BLOCKED", "reasons": ["no prompt was supplied"]},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 2

    from contentops.media.image_contract import ImageRequest

    attempt = 2 if args.retry_from else 1
    try:
        outcome = provider.generate_image(
            ImageRequest(
                prompt=prompt,
                model=args.model,
                width=args.width,
                height=args.height,
                seed=args.seed,
                force=args.force,
            ),
            retry_reason=args.retry_reason or None,
            attempt=attempt,
            retry_from=Path(args.retry_from) if args.retry_from else None,
        )
    except CredentialBindingError as unbound:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "verdict": "CREDENTIAL_NOT_BOUND_TO_TRANSPORT",
                    "reasons": [str(unbound)],
                    "generated": False,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 7
    except BillingBlocked as blocked:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "verdict": blocked.verdict,
                    "reasons": blocked.reasons,
                    "generated": False,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 7
    except DimensionRejected as invalid:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "verdict": "DIMENSIONS_REJECTED_LOCALLY",
                    "reasons": [str(invalid)],
                    "generated": False,
                    "provider_call": False,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 2
    except RuntimeError as failed:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "reasons": [str(failed)],
                    "generated": False,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1

    receipt = outcome.receipt
    payload = receipt_to_dict(receipt)
    payload["status"] = "OK"
    payload["reused"] = outcome.reused
    payload["provider_call"] = not outcome.reused
    payload["credential_binding"] = provider.credential_metadata()

    # Register as a support visual. This is the only role a generated image may
    # take, and registering it here means the boundary is enforced by the
    # generator itself, not only by whoever consumes the file later.
    registry = AssetRegistry()
    record = register_asset(
        registry,
        asset_id=f"{receipt.fingerprint[:16]}",
        kind=AssetKind.GENERATED_IMAGE,
        path=receipt.canonical_path,
        evidence_use=EvidenceUse.VISUAL_SUPPORT,
        receipt_ref=str(Path(receipt.canonical_path).name + ".receipt.json"),
        sha256=receipt.output_sha256,
    )
    payload["asset_record"] = {
        "asset_id": record.asset_id,
        "kind": record.kind,
        "generated": record.generated,
        "evidence_capable": record.evidence_capable,
        "evidence_use": record.evidence_use,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())