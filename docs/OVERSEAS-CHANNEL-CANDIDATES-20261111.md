# Overseas channel candidate registry (2026-11-11)

**Status: metadata only / disabled. This document does not authorize production, account access, distribution, analytics, or publishing.**

## Scope

The existing ContentOps platform registry has three **pre-canonical** candidate rows:

| ID | Future content reuse | Current pipeline | Account | Publication | Metrics |
|---|---|---|---|---|---|
| `threads` | Source-verified X text → native discussion rewrite | `CANDIDATE_NOT_ROUTED` | none | `NOT_IMPLEMENTED` | `NONE` |
| `instagram` | Approved vertical video / Carousel | `CANDIDATE_NOT_ROUTED` | none | `NOT_IMPLEMENTED` | `NONE` |
| `facebook` | Approved Reels / business case / Page/Group post | `CANDIDATE_NOT_ROUTED` | none | `NOT_IMPLEMENTED` | `NONE` |

All three are `PLANNED`, `manual_review=true`, `owner=""`, with no credentials, public account binding or implementation. They are **not** part of the Strategy canonical 14-platform portfolio or its operating quota, do not claim `INTEGRATED`, and must not appear as runnable `VIDEO` or `X_EDITORIAL` pipelines. No API and no automatic metrics/publishing functionality is introduced.

WhatsApp and LINE are prospective **private conversion touchpoints**. They are intentionally absent from `config/registry/platforms.json` because this registry is for content distribution rather than customer conversations. The commercial source of truth and consent-based lead handling belong outside ContentOps.

## Proposed future intake

1. Strategy approves a specific experimental objective, account/territory fit and native platform Playbook.
2. Human-reviewed Content Bundle is checked for claim evidence, rights, AIGC/partnership labels and target-language adaptation.
3. Produce an **offline** native package through a future adapter (not implemented by this change).
4. Human operator manually publishes, then records an actual public URL and timezone-specific timestamp. Never manufacture a receipt.
5. Store real metric snapshots when available; absent values are `unknown`, never inferred from source platforms.
6. Evaluate qualified interaction and extra editing time before adding a live adapter. Any canonical portfolio change requires Strategy + OPC mirror synchronization and independent review.

## Explicit non-goals

- No new posting API, OAuth scope, social scraping, automated replies, unsolicited direct messages or background scheduling.
- No new video production pipeline, duplicated account DNA, paid provider calls, or automatic engagement behavior.
- No claimed account eligibility, payouts, audience growth, or published post.
- No change to X manual-only flow, YouTube planned status or the existing 14 canonical platform IDs.

## Validation

`python tests/test_platform_registry.py` covers disabled candidates, no executable commands, no publication authority, account isolation and complete registry integrity. In PR CI, run the standard repository checks as configured. The branch itself is not evidence of runtime success.

Strategy design reference: `X-SuperPlay-Strategy/03-Execution/Overseas-Channel-Expansion-20261111.md`.
