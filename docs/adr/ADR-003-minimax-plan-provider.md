# ADR-003: MiniMax subscription plan provider

## Status

ACCEPTED (M2.0, 2026-10-04) — speech and image accepted, H3 video rejected

## Context

Founder purchased MiniMax subscription plan. Requirement: use subscription entitlements for image/voice/video generation. No PAYG.

## Decision

- `billing_mode: subscription`
- `allow_payg: false`
- `allow_credit_pack_fallback: false`
- Transport is the **official MiniMax CLI (`mmx`, npm `mmx-cli`)**, verified at `v1.0.27`.
  No undocumented or reverse-engineered endpoint is used for generation.
- Billing pre-flight is **fail-closed and runs before every generation**. A Subscription
  Key draws on Credit Packs by design once plan usage is exhausted, so the only provable
  exclusion is a zero Credit Pack balance, which must be observed at run time.
- Speech: adapt the MiniMax TTS path that already exists in the **pinned** Easel v0.2.1
  (`multivoice.py --provider minimax`). Do not build a second TTS client.
- Image: ContentOps provider adapter over the official CLI. Pinned Easel has no
  MiniMax image provider.
- H3 video: **rejected for now.** Current official guidance requires a pay-as-you-go or
  credit key for H3, which this policy forbids.
- Receipts record quota before/after and the billing pre-flight verdict.
- Fallback never silently uses PAYG. A modality without verified entitlement is
  `MANUAL_ONLY` or blocked, never a fake adapter.

## Consequences

- Speech and image may proceed to implementation (#5 sub-issues).
- H3 video may not. M4 stays unimplemented until a human resolves entitlement.
- Voice quality has two measured defects to gate: provider output peaks near 0 dB
  (loudness normalisation required) and hyphenated/CamelCase brand tokens are
  mispronounced without a lexicon.
- Image output container is chosen by the provider and does not follow the requested
  file extension, so the image gate must sniff the container.
- `docs/ai-provider-selection.md` stays gitignored.

## Evidence

- `research/providers/minimax-mplan-explore-capability.md` (+ `.zh-CN.md`)
- `research/providers/receipts/minimax-mplan-explore-capability-2026-10-04.sanitized.json`
- `scripts/minimax_capability_probe.py` (research probe, not a production provider)

## Reopen when

- MiniMax confirms H3 access for a Subscription Key, or the Founder explicitly approves
  a pay-as-you-go / credit-pack path.
