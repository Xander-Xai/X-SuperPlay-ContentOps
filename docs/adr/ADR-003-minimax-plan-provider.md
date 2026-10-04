# ADR-003: MiniMax subscription plan provider

## Status

ACCEPTED (M2.0, 2026-10-04) — speech, image and H3 video all accepted

## Context

Founder purchased MiniMax subscription plan. Requirement: use subscription entitlements for image/voice/video generation. No PAYG.

## Decision

- `billing_mode: subscription`
- `allow_payg: false`
- `allow_credit_pack_fallback: false`
- Transport priority: **official MiniMax CLI (`mmx`, npm `mmx-cli` v1.0.27)** first, then the
  **documented public API** where the CLI has a capability gap. Video needs the latter:
  the CLI exposes no resolution flag and silently drops `--resolution`, always sending `2K`.
  No undocumented or reverse-engineered endpoint is used for generation.
- Billing pre-flight is **fail-closed and runs before every generation**. A Subscription
  Key draws on Credit Packs by design once plan usage is exhausted, so the only provable
  exclusion is a zero Credit Pack balance, observed at run time. Confirmed by video:
  weekly plan usage fell 65% → 58% while all four paid balances stayed at `0.00`.
- **The balance read is `UNDOCUMENTED_FIRST_PARTY_IMPLEMENTATION_DEPENDENCY`.** It is a
  first-party path the official CLI also calls, it is absent from public API documentation,
  and it may change without notice. Research use only unless separately accepted; any
  production use must sit behind a single `BillingGuard` with contract tests and a
  documented migration path. It must not become the permanent production contract by
  default.
- Speech: adapt the MiniMax TTS path that already exists in the **pinned** Easel v0.2.1
  (`multivoice.py --provider minimax`). Do not build a second TTS client.
- Image: ContentOps provider adapter over the official CLI. Pinned Easel has no
  MiniMax image provider.
- H3 video: accepted, scheduled **after** M2 and M3 because it is the most expensive
  modality and consumes weekly quota only.
- Receipts record quota before/after and the billing pre-flight verdict.
- Fallback never silently uses PAYG. A modality without verified entitlement is
  `MANUAL_ONLY` or blocked, never a fake adapter.

## Corrections made during M2.0

An earlier revision recorded H3 as `NOT_ENTITLED` on the strength of the official CLI's
H3 skill, which forbids a *Token Plan* Subscription Key for H3. That claim was an
inference, not evidence, and it was too strong. A real `MiniMax-H3` task on the M Plan
Subscription Key returned HTTP 200 and succeeded. The CLI skill's prohibition does not
apply to M Plan. Before the account test the correct status was `BLOCKED` with reason
`OFFICIAL_DOC_CONFLICT`.

Consequence for the process: when official documentation conflicts, record the conflict
as the finding. Do not resolve it by picking the more restrictive reading and calling it
an entitlement fact.

## Consequences

- All three generation modalities may proceed to implementation (#5 sub-issues).
- Video costs 7 weekly percentage points per 4 s 768P job, so video retries and
  reference-mode testing need an explicit budget.
- Delivered video dimensions are approximate: 9:16 was requested and 768x1344 delivered.
  Composition gates must assert tolerance, not exact ratio.
- H3 emits an audio track even when none is requested, at near-ambient level.
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

- MiniMax changes the balance endpoint shape, or exposes an official credit-balance
  equivalent that replaces the undocumented dependency.
