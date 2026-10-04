#!/usr/bin/env python3
"""Synthesize one narration through the MiniMax M Plan speech provider.

Ops entry point for Issue #19. Business logic lives in
``src/contentops/media/``; this script only wires the CLI, the credential and
the output locations.

What it will not do
-------------------
- generate if the billing source cannot be proven included-plan-only
- print a credential, a credential fragment or an Authorization header
- mark anything ``production_ready``: narration always awaits human review
- silently swap to edge-tts on failure

Usage
-----
```
python scripts/synthesize_narration.py --text "你好，这是测试。" --out-dir .verify-tmp/m2
python scripts/synthesize_narration.py --text-file script.txt --language zh
python scripts/synthesize_narration.py --text "..." --health
```

Credential resolution, in order:
1. ``MINIMAX_SUBSCRIPTION_KEY`` (preferred)
2. ``MINIMAX_API_KEY``
3. the official CLI's own config file, without printing the value

The base URL is asked of the official CLI, so this repository never accumulates
provider endpoint literals.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from process_utils import hidden_run  # noqa: E402

from contentops.media.billing_guard import BillingGuard, classify_credential  # noqa: E402
from contentops.media.contract import BillingBlocked, SpeechRequest  # noqa: E402
from contentops.media.minimax_speech import (  # noqa: E402
    MiniMaxMPlanProvider,
    receipt_to_dict,
    resolve_cli,
)


def resolve_credential() -> str:
    import os

    for name in ("MINIMAX_SUBSCRIPTION_KEY", "MINIMAX_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    config = Path.home() / ".mmx" / "config.json"
    if config.is_file():
        try:
            return str(json.loads(config.read_text(encoding="utf-8")).get("api_key") or "")
        except (json.JSONDecodeError, OSError):
            return ""
    return ""


def resolve_base_url() -> str:
    cli = resolve_cli()
    if not cli:
        return ""
    result = hidden_run([cli, "config", "show", "--output", "json"], timeout=60)
    if result.returncode != 0:
        return ""
    try:
        return str(json.loads(result.stdout or "{}").get("base_url") or "")
    except json.JSONDecodeError:
        return ""


def build_guard() -> BillingGuard:
    return BillingGuard(base_url=resolve_base_url(), credential=resolve_credential())


def recheck(asset: Path, *, language: str) -> int:
    """Re-run QC on an existing asset. No provider request, no quota consumed.

    Useful after a QC rule changes: the measurement is redone on the same audio
    instead of regenerating and paying for it again.
    """
    from contentops.media.asr_backcheck import backcheck_speech
    from contentops.media.audio import measure_audio, technical_qc
    from contentops.media.lexicon import default_en_lexicon, default_zh_lexicon
    from contentops.media.minimax_speech import flatten_for_cli

    if not asset.is_file():
        print(f"[FAIL] no such asset: {asset}", file=sys.stderr)
        return 2

    lexicon = default_zh_lexicon() if language == "zh" else default_en_lexicon()
    text_path = ROOT / "projects/easel-review/script/narration.txt"
    expected = flatten_for_cli(lexicon.spoken_text(
        text_path.read_text(encoding="utf-8").strip()
    )) if text_path.is_file() else ""

    measured = measure_audio(asset)
    technical = technical_qc(asset, expected_sample_rate_hz=32000)
    semantic = (
        backcheck_speech(asset, expected).as_dict()
        if expected
        else {"status": "SKIPPED", "reason": "no reference text available"}
    )
    payload = {
        "asset": str(asset),
        "recheck_only": True,
        "provider_request_made": False,
        "measurements": measured.__dict__,
        "technical_qc": technical,
        "semantic_qc": semantic,
        "approved": bool(technical.get("approved")),
        "human_review": "PENDING_FOUNDER_REVIEW",
        "production_ready": False,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["approved"] else 6


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MiniMax M Plan narration",
        epilog=(
            "credential: set MINIMAX_SUBSCRIPTION_KEY (preferred) or MINIMAX_API_KEY; "
            "if neither is set the official CLI config is read without printing the value. "
            "Only a Subscription Key class is accepted. "
            "on failure edge-tts is never substituted silently: production_ready stays "
            "false and human_review stays PENDING_FOUNDER_REVIEW."
        ),
    )
    parser.add_argument("--text", help="display text to narrate")
    parser.add_argument("--text-file", help="read display text from a file")
    parser.add_argument("--language", default="zh", choices=("zh", "en"))
    parser.add_argument("--voice", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--speed", type=float, default=None)
    parser.add_argument("--out-dir", default=".verify-tmp/narration")
    parser.add_argument("--receipt", default="", help="write the receipt JSON here")
    parser.add_argument("--force", action="store_true",
                        help="regenerate even if a valid asset exists")
    parser.add_argument("--retry-reason", default=None,
                        help="named failure reason; required for attempt 2")
    parser.add_argument("--recheck", default="",
                        help="re-run technical and semantic QC on an existing "
                             "normalised asset; makes no provider request")
    parser.add_argument("--health", action="store_true",
                        help="report transport and billing state, generate nothing")
    args = parser.parse_args()

    if args.recheck:
        return recheck(Path(args.recheck), language=args.language)

    guard = build_guard()
    provider = MiniMaxMPlanProvider(
        guard=guard, work_dir=Path(args.out_dir), cli=resolve_cli()
    )

    if args.health:
        health = provider.health()
        health["guard"] = {
            "verdict": guard.evaluate().verdict,
            "credential_class": classify_credential(resolve_credential()),
        }
        print(json.dumps(health, indent=2, ensure_ascii=False))
        return 0 if health.get("reachable") else 2

    if not args.text and not args.text_file:
        parser.error("one of --text or --text-file is required")

    display_text = args.text
    if args.text_file:
        display_text = Path(args.text_file).read_text(encoding="utf-8").strip()

    if not shutil.which("ffmpeg"):
        print("[FAIL] ffmpeg is required for normalisation and QC", file=sys.stderr)
        return 3

    request = SpeechRequest(
        display_text=display_text,
        language=args.language,
        voice=args.voice,
        model=args.model,
        speed=args.speed,
        force=args.force,
    )

    attempt = 2 if args.retry_reason else 1
    try:
        outcome = provider.synthesize_speech(
            request, retry_reason=args.retry_reason, attempt=attempt
        )
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
        return 4
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "generated": False,
                    "edge_tts_available": bool(shutil.which("edge-tts")),
                    "fallback_policy":
                        "explicit only. A silent swap to edge-tts is forbidden; "
                        "a deliberate fallback must set degraded=true, "
                        "provider=edge-tts and production_ready=false.",
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 5

    payload = receipt_to_dict(outcome.receipt)
    payload["asset"] = {
        "normalized_path": outcome.asset.normalized_path,
        "duration_s": outcome.asset.duration_s,
        "sample_rate_hz": outcome.asset.sample_rate_hz,
        "channels": outcome.asset.channels,
        "codec": outcome.asset.codec,
        "peak_before_db": outcome.asset.peak_before_db,
        "peak_after_db": outcome.asset.peak_after_db,
        "loudness_before": outcome.asset.loudness_before,
        "loudness_after": outcome.asset.loudness_after,
        "approved": outcome.asset.approved,
    }
    payload["reused_cached_asset"] = outcome.reused
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    if args.receipt:
        target = Path(args.receipt)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    if not outcome.asset.approved:
        print("[FAIL] technical QC did not approve the asset", file=sys.stderr)
        return 6
    return 0


if __name__ == "__main__":
    sys.exit(main())