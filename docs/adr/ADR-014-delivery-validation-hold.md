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

### Owner limited-scope authorization (2026-11-01)

Recorded here, in this ADR, because a hold may only be narrowed by an Owner
decision — never by a new ADR written by the agent that wants to proceed.
Source: the Owner's instruction to the coding agent on 2026-11-01, issued after
an adversarial review of a second Easel-first proposal.

The following work is authorized **inside the hold window**, and nothing else:

1. Reuse and extend the existing `contentops.platform-registry/v1`
   (`config/registry/platforms.json`, `src/contentops/platforms/registry.py`,
   `scripts/platforms.py`) so all nine Strategy platforms plus GitHub are
   represented, with truthful `PLANNED`/`INTEGRATED` states and named blockers.
2. Record the target architecture boundary and the Easel positioning in
   [ADR-015](ADR-015-platform-placeholders-and-content-bundle.md).
3. Add the minimal Content Bundle consumption contract
   (`src/contentops/content_kernel/bundle.py`) that validates a Strategy
   Bundle before use.

Still suspended during the window: new platform production workflows, an Easel
upgrade, gateway/Web UI/FastAPI/database/queue, automatic publishing or
commenting, bulk graphic-line development, authority migration, and unrelated
module expansion.

This authorization does **not** retire the delivery requirement below. The week
must still end with a real delivery acceptance or a recorded blocker. A
placeholder registry is explicitly **not** delivery, and completing it must not
be reported as completing the hold.

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

## Owner limited-scope authorization #2 (2026-11-01) — video quality remediation

Recorded here because a hold may only be narrowed by an Owner decision, never by
a new ADR written by the agent that wants to proceed.

Source: the Owner's scoped correction-and-execution directive delivered to the
coding agent on 2026-11-01, following the Founder rejection of
`projects/easel-review/final/easel.mp4` (62.0 s, 1080x1920, SHA-256
`e3b029ef4fc033f9164cd84344d8fd834c6fcc78e932566835248307cc0e882f`).

### Authorized inside the hold window, and nothing else

1. **Historical capability recovery and minimal Motion integration** — limited to
   the capabilities named in the audit's remediation plan: the Motion drivers
   stranded on `fix/49-skill-route-ci`, a single entry-point correction in each
   production path, an optional narration-provider path, the visual quality gate,
   and one remediation sample. No second compositor, no new platform module.
2. **One read-only voice list/status check.** No clone, no first activation, no
   TTS synthesis, no top-up, no paid retry. An unsafe or exposed credential
   leaves the check `BLOCKED`; it does not authorise a workaround.
3. **`projects/easel-fi-audio-first` approved for intake** as a governed
   technical sample. This is not production readiness and not publication.
4. **`huashu-art-motion` approved for controlled capability registration**,
   subject to real source, licence, Windows patch, runtime and per-asset rights
   verification. Registration grants no execution authority.

### Not authorized

New MiniMax generation requests, paid digital-human experiments, publication, and
merging any pull request.

### Acceptance for this exception

- the rejected video has a non-overwritable receipt bound to its SHA-256;
- the existing 25 s Motion sample is reproduced under governance, not rebuilt;
- narration can enter the video chain only within the authorisation above;
- a new sample carries real dynamic narrative rather than stills switching;
- fact, rights, technical and visual gates pass;
- the Founder watches the new cut and decides.

Everything else in this ADR remains in force, including the 2026-11-08 re-review.

### Owner limited-scope authorization #3 (2026-11-02) — guarded Easel host

Recorded here because a hold may only be narrowed by an Owner decision.

Source: the Owner's 2026-11-02 directive to adopt the full Easel system as the
production base, recorded in [ADR-016](ADR-016-easel-host-adoption.md).

Authorized inside the hold window, and nothing else:

1. Architecture records that supersede ADR-015 D1.
2. A loopback-only, deny-by-default guard around the pinned Easel ASGI host,
   plus offline tests and a status command.
3. A Bundle-to-video and Bundle-to-graphic handoff, and a manual graphic
   package that stops at human review.

Not authorized: installing host dependencies, reading credentials or profiles,
connecting accounts, platform drafts, publishing, provider spend, an Easel
upgrade, or merging any pull request. `HOST_BLOCKED` remains the default until
a real host-security review and separate approval.

### Merge coordination

This section was written on a branch cut from `origin/main`. PR #101 adds a
different section to this same file. When the two meet, **keep both sections**;
neither one supersedes the other, and dropping either loses an Owner decision.
