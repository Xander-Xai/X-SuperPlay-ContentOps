#!/usr/bin/env python3
"""Generate one H3 shot through the MiniMax M Plan video provider.

Ops entry point for Issue #22. Business logic lives in
``src/contentops/media/``; this script only wires the credential, the transport and
the output locations.

What it will not do
-------------------
- create a second task because polling, downloading or the process failed
- generate if the billing source cannot be proven included-plan-only
- print a credential, a credential fragment or an Authorization header
- print or persist a raw provider task id
- mark anything ``production_ready``: a generated shot always awaits human review
- register a shot whose receipt does not exist
- let a generated shot be registered as evidence

Usage
-----
```
python scripts/generate_h3_shot.py --prompt "a motorcycle in a tunnel" --out-dir .verify-tmp/m4
python scripts/generate_h3_shot.py --shot-file shot.json --mode I2VA --first-frame a.png
python scripts/generate_h3_shot.py --prompt "..." --health
```

The prompt is **compiled** from a ShotPlan rather than sent raw, because the
documented H3 structure (alignment instruction plus three ordered fields, or six
ordered Ref2VA sections) is part of the request. See
``contentops.media.h3_prompt``.
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

from contentops.media.billing_guard import BillingGuard  # noqa: E402
from contentops.media.contract import BillingBlocked  # noqa: E402
from contentops.media.credentials import (  # noqa: E402
    CredentialBindingError,
    resolve_credential,
)
from contentops.media.h3_prompt import H3PromptCompiler, ShotPlan  # noqa: E402
from contentops.media.h3_transport import HttpH3Transport, TransportError  # noqa: E402
from contentops.media.minimax_video import (  # noqa: E402
    DEFAULT_H3_MODEL,
    DEFAULT_RESOLUTION,
    MiniMaxMPlanVideoProvider,
    receipt_to_dict,
)
from contentops.media.video_contract import AudioPolicy, VideoRequest  # noqa: E402
from contentops.media.video_validation import RequestRejected  # noqa: E402

#: Optional override for the billing API base, so a test can point the gate at a
#: local stub instead of contacting the provider. Production leaves it unset.
BASE_URL_ENV_VAR = "CONTENTOPS_MINIMAX_BASE_URL"


def resolve_base_url() -> str:
    override = os.environ.get(BASE_URL_ENV_VAR, "").strip()
    if override:
        return override
    try:
        from contentops.media.transport import resolve_cli  # noqa: PLC0415

        from process_utils import hidden_run  # noqa: PLC0415

        cli = resolve_cli()
        if not cli:
            return ""
        prefix = list(cli) if isinstance(cli, (list, tuple)) else [cli]
        result = hidden_run(prefix + ["config", "show", "--output", "json"], timeout=60)
        if result.returncode != 0:
            return ""
        return str(json.loads(result.stdout or "{}").get("base_url") or "")
    except Exception:  # noqa: BLE001
        return ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prompt", default="", help="what the shot should show")
    parser.add_argument("--shot-file", default="", help="JSON ShotPlan fields")
    parser.add_argument("--out-dir", default=".verify-tmp/m4")
    parser.add_argument("--shot-id", default="shot-1")
    parser.add_argument("--mode", default="T2VA",
                        choices=["T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA"])
    parser.add_argument("--model", default=DEFAULT_H3_MODEL)
    parser.add_argument("--duration", type=int, default=4)
    parser.add_argument("--resolution", default=DEFAULT_RESOLUTION)
    parser.add_argument("--ratio", default="9:16")
    parser.add_argument("--first-frame", default="")
    parser.add_argument("--last-frame", default="")
    parser.add_argument("--reference-image", action="append", default=[])
    parser.add_argument("--reference-video", action="append", default=[])
    parser.add_argument("--reference-audio", action="append", default=[])
    parser.add_argument("--audio-policy", default=AudioPolicy.DEFAULT,
                        choices=list(AudioPolicy.ALL))
    parser.add_argument("--subject", default="")
    parser.add_argument("--environment", default="")
    parser.add_argument("--action", default="")
    parser.add_argument("--camera", default="")
    parser.add_argument("--sound", default="")
    parser.add_argument("--visual-style", default="Live-action, cinematic")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--retry-from", default="")
    parser.add_argument("--retry-reason", default="")
    parser.add_argument("--quota-budget", default="",
                        help="explicit budget for the run, e.g. '7pp'. Mandatory: "
                             "video is the most expensive call ContentOps makes.")
    parser.add_argument("--test-objective", default="",
                        help="what this generation is meant to prove. Mandatory.")
    parser.add_argument("--health", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    overrides = {}
    if args.shot_file:
        overrides = json.loads(Path(args.shot_file).read_text(encoding="utf-8"))

    plan = ShotPlan(
        shot_id=overrides.get("shot_id", args.shot_id),
        purpose=overrides.get("purpose", "support visual"),
        duration=int(overrides.get("duration", args.duration)),
        aspect_ratio=overrides.get("aspect_ratio", args.ratio),
        subject=overrides.get("subject", args.subject or args.prompt),
        environment=overrides.get("environment", args.environment),
        action=overrides.get("action", args.action),
        camera=overrides.get("camera", args.camera),
        sound=overrides.get("sound", args.sound),
        visual_style=overrides.get("visual_style", args.visual_style),
        reference_assets=tuple(overrides.get("reference_assets", ())),
        mode=overrides.get("mode", args.mode),
    )
    # Resolved once: the gate and the HTTP Authorization header share this value.
    resolved = resolve_credential()
    base_url = resolve_base_url()
    guard = BillingGuard(base_url=base_url, credential=resolved.key)
    try:
        # The same resolved base URL the gate checked. This account resolves to the
        # CN endpoint, so defaulting the transport to the international host would
        # send the authorised key to a different account family than the one whose
        # balances were verified as zero.
        transport = HttpH3Transport(credential=resolved.key, base_url=base_url)
    except TransportError as exc:
        print(json.dumps({"status": "BLOCKED", "verdict": "CREDENTIAL_NOT_BOUND",
                          "reasons": [str(exc)], "task_created": False}, indent=2))
        return 7
    provider = MiniMaxMPlanVideoProvider(
        guard=guard,
        work_dir=Path(args.out_dir),
        transport=transport,
        model=args.model,
        transport_credential=resolved,
    )

    # Health runs before any prompt work, so a diagnostic command cannot itself fail
    # for an unrelated reason.
    if args.health:
        print(json.dumps({"health": provider.health(),
                          "capabilities": provider.capabilities()}, indent=2))
        return 0

    compiler = H3PromptCompiler()
    try:
        compiled = compiler.compile(plan)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "BLOCKED", "verdict": "PROMPT_REJECTED",
                          "reasons": [str(exc)], "task_created": False}, indent=2))
        return 2

    request = VideoRequest(
        compiled_prompt=compiled.text,
        mode=plan.mode,
        model=args.model,
        duration_s=plan.duration,
        resolution=args.resolution,
        ratio=args.ratio,
        first_frame=args.first_frame or None,
        last_frame=args.last_frame or None,
        reference_images=tuple(args.reference_image),
        reference_videos=tuple(args.reference_video),
        reference_audio=tuple(args.reference_audio),
        audio_policy=args.audio_policy,
        force=args.force,
    )
    attempt = 2 if args.retry_from else 1
    try:
        outcome = provider.generate_video(
            request,
            retry_reason=args.retry_reason or None,
            attempt=attempt,
            retry_from=Path(args.retry_from) if args.retry_from else None,
            quota_budget=args.quota_budget or None,
            test_objective=args.test_objective or None,
        )
    except RequestRejected as invalid:
        print(json.dumps({"status": "BLOCKED", "verdict": "REQUEST_REJECTED_LOCALLY",
                          "reasons": [str(invalid)], "task_created": False,
                          "billing_call": False}, indent=2, ensure_ascii=False))
        return 2
    except CredentialBindingError as unbound:
        print(json.dumps({"status": "BLOCKED",
                          "verdict": "CREDENTIAL_NOT_BOUND_TO_TRANSPORT",
                          "reasons": [str(unbound)], "task_created": False}, indent=2))
        return 7
    except BillingBlocked as blocked:
        print(json.dumps({"status": "BLOCKED", "verdict": blocked.verdict,
                          "reasons": blocked.reasons, "task_created": False}, indent=2))
        return 7
    except TransportError as transport_error:
        # Explicitly not a retry: the task, if any, already exists.
        print(json.dumps({"status": "RECOVERABLE",
                          "verdict": "TRANSPORT_FAILURE_NO_NEW_TASK",
                          "reasons": [str(transport_error)],
                          "create_count": provider.create_count,
                          "note": "resume by re-running; the same task is polled"},
                         indent=2, ensure_ascii=False))
        return 1
    except RuntimeError as failed:
        print(json.dumps({"status": "FAILED", "reasons": [str(failed)],
                          "create_count": provider.create_count}, indent=2,
                         ensure_ascii=False))
        return 1

    payload = receipt_to_dict(outcome.receipt)
    payload["status"] = "OK"
    payload["reused"] = outcome.reused
    payload["create_count"] = provider.create_count
    payload["prompt_sections"] = compiled.sections
    payload["prompt_alignment_instruction"] = compiled.alignment_instruction
    payload["asset_record"] = {
        "asset_id": record.asset_id,
        "kind": record.kind,
        "generated": record.generated,
        "evidence_capable": record.evidence_capable,
        "evidence_use": record.evidence_use,
    } if (record := (provider.registered_assets() or [None])[-1]) else None
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
