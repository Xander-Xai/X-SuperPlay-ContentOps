# ADR-003: MiniMax subscription plan provider

## Status

PROPOSED

## Context

Founder purchased MiniMax subscription plan. Requirement: use subscription entitlements for image/voice/video generation. No PAYG.

## Decision

- `billing_mode: subscription`
- `allow_payg: false`
- Implement `MiniMaxPlanProvider` only after capability spike (Issue #4) verifies programmatic access
- If a modality is not programmatically accessible → `MANUAL_ONLY` (not a fake adapter)
- Receipts record quota_before/after
- Fallback to LocalFallbackProvider (edge-tts) never silently uses PAYG

## Consequences

- Capability spike must complete before M2-M4 implementation
- `MANUAL_ONLY` is a valid, honest status
- No provider endpoint URLs or pricing in public docs
- `docs/ai-provider-selection.md` stays gitignored

## Will become ACCEPTED when

M2.0 capability spike (Issue #4) completes with verified capabilities.
