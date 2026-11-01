# ADR-014: Delivery-validation hold — seven days, no architecture expansion

> Status: **Accepted** — Owner authorization, 2026-11-01
> Supersedes nothing. Narrows the *order* of work only; it does not withdraw
> any decision in [ADR-012](ADR-012-convergence-decisions.md).
> Re-review: **2026-11-08**.

## Context

An adversarial review of 2026-11-01 checked a third-party proposal to rebuild
the repository as an eight-module "Creator OS" on Easel v0.3.0. The review's
decisive finding was not about Easel. It was this: the **local workspace** holds
22 rendered MP4s under `projects/*/final/`, while the **repository** tracks
exactly one (`projects/easel-review/final/final.mp4` — the gitignore exception),
and neither holds a single publication artifact: no delivery package, no platform
URL, no approved `human-review.json`. Every `production_ready` value is `false`.

The two counts are recorded separately on purpose. A tracked MP4 is evidence the
pipeline ran; a local MP4 is a candidate that has not been reviewed, delivered or
published. Neither number is a publication count, and neither may be reported as
one.

The proposal's phases, and several earlier plans, would each be marked
"complete" without changing that number. The repository's own
[PRD](../PRD.md) §6 already lists auto-publishing, metrics scraping, a database
and a complex FastAPI as non-goals, and
[ARCHITECTURE](../ARCHITECTURE.md) records that platform publishing stays
manual and human-gated.

The recorded founder diagnosis is *engineering-heavy, shipping-light*, and the
standing rules are `Adopt before Build`, `Ship before Automate`,
`Measure before Optimize`, `Delete before Expand`.

## Decision

**P2 expansion is on hold from 2026-11-01 to 2026-11-07 (Asia/Shanghai).**

### Suspended for the seven days

- New platform production modules.
- A FastAPI bridge service, database, background worker, or web workbench.
- An Easel upgrade. [ADR-012](ADR-012-convergence-decisions.md) D3 stands.
- Non-essential feature expansion of any kind.

### Not suspended — these may and should proceed

- Security work, including credential handling and the exposed-receipt history.
- Restoring the pinned Easel runtime (`scripts/resolve_easel.py --bootstrap`).
- Real delivery acceptance: producing a reviewable package and recording a
  real platform URL.
- The documentation convergence in Issue #96.

### What this ADR does not do

- It does not withdraw ADR-012 D1–D6, does not reorder the S1–S4 slices
  permanently, and does not authorise deleting branches, worktrees or projects.
- It does not change any contract. `contentops.copy-to-video/v1` keeps its name.

## Why an explicit hold rather than a silent reorder

A silent reorder reads as drift to the next agent or contributor, and the
convergence plan in Issue #94 is Owner-authorised. Recording the pause as a
decision with an end date keeps both facts true at once: the plan is intact,
and it is not being executed this week.

## Consequences

- Work started during the hold must produce a delivery artifact or a recorded
  blocker. A week that ends with only documents, modules or tests has failed
  this ADR's intent.
- If the first real publication cannot happen for a quality or rights reason,
  that is a **finding**, not a failure of the hold. Record it and apply the
  7/14-day rule — do not start a new production engine to avoid the decision.
- On 2026-11-08 the Owner decides whether S3/S4 resume, and the hold expires
  whether or not that decision is made.
- Any extension of the hold is a new Owner decision recorded here, not an
  implied continuation.
