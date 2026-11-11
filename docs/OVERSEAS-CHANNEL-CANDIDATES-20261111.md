# Overseas channel research candidates (2026-11-11)

**Status: proposed / not executable.** The public file `config/registry/channel-candidates.json` is a **non-runtime planning catalog**. It is deliberately separate from `config/registry/platforms.json`, which must remain aligned with Strategy's 14-platform canonical portfolio. No changes to account binding, production flow, distribution or metrics have been made.

| ID | Research priority | Potential content reuse | Runtime status |
|---|---|---|---|
| `threads` | P1 | Human-reviewed X editorial rewritten as native discussion | absent from runtime registry |
| `instagram` | P1 | Rights-cleared Reels / Carousel built from an approved visual asset | absent from runtime registry |
| `facebook` | P2 | Approved Reels / case studies; optional relevant Page / Group discussion | absent from runtime registry |
| `whatsapp` | P3 | Consent-based inquiry/follow-up, not public publishing | private conversion only |
| `line` | P3 | Region-specific consent-based inquiry/follow-up | private conversion only |

## Separation and fail-closed contract

- Canonical runtime registry `config/registry/platforms.json` has **no** Facebook, Instagram or Threads entries. `workflow_routes` refuses these names as `PLATFORM_UNKNOWN`.
- Candidate catalog is not loaded by content routing, publishing, scheduled work, account resolution or metrics collection. The catalog's `PRE_CANONICAL` value is not a runtime platform status.
- No new API integration, OAuth, script, browser action, automated post, follower manipulation, qualified data or observed engagement is claimed.
- WhatsApp and LINE are not content-publishing destinations. Customer data, consent records and revenue remain outside this public repository in appropriately controlled systems.

## Future approval and acceptance

1. Strategy validates the audience hypothesis, account region, rights and a reuse-first platform-native content format; existing Source / Content Bundle evidence remains authoritative.
2. Human operator checks platform-specific publishing, AI/partnership disclosures and rights; do not copy a source post without reworking its packaging.
3. Only after a **separate** Strategy + OPC canonical mirror sync and coverage test review may a channel be registered as a real platform in the runtime registry.
4. Implement a minimal manual publishing package, then retain an actual published URL, account/timezone, source/evidence pointer and real metrics (missing values are `unknown`).
5. Evaluate independent qualified discussion / concrete questions / commercial signals relative to re-editing cost; pause unproductive platforms.
6. Do not promote technical or content activity into OPC revenue, payment or accepted demand.

## Test and review

`python tests/test_platform_registry.py` checks canonical runtime membership, non-runtime candidate structure and `PLATFORM_UNKNOWN` refusal. The separate `python tests/test_platform_status_sync.py` must keep passing without changing the shipped 14-platform Strategy mirror. The repository's CI is the final branch acceptance signal.

Strategy counterpart: `X-SuperPlay-Strategy/03-Execution/Overseas-Channel-Expansion-20261111.md`.
