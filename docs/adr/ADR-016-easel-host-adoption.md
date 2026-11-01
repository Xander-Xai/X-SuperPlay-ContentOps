# ADR-016: Adopt the pinned Easel host as the production base

Status: **Accepted — Owner authorization, 2026-11-02**
Date: 2026-11-02
Issue: [#106](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/106)
Related: [ADR-002](ADR-002-contentops-boundaries.md), [ADR-006](ADR-006-upstream-upgrade-policy.md), [ADR-014](ADR-014-delivery-validation-hold.md), [ADR-015](ADR-015-platform-placeholders-and-content-bundle.md)
Strategy authority: `Xander-Xai/X-SuperPlay-Strategy` — `03-Execution/README.md`, `01-Strategy/Content-Kernel-and-Bundle-Architecture-V1.md`, `90-Templates/content-bundle.yaml`

## Context

ADR-015 D1 recorded a deliberate limit: Easel was the priority-reuse capability
system, but ContentOps did not adopt its agent, workbench, profiles, outputs or
publishing. That limit was written before the Owner's 2026-11-02 decision.

The Owner has now chosen **"接管完整 Easel 系统"** — the full Easel system,
not only its composer. The target is a self-media lifecycle system in which
Easel is the content-production base and ContentOps is its governed extension,
not two unrelated repositories.

The facts that make this a decision rather than an implementation detail:

1. The pinned Easel v0.2.1 host is a real FastAPI/React workbench with an
   OpenClaw agent, 114 skills, account sessions, publishing, analytics and
   settings. Its `web/app.py` binds `0.0.0.0`, allows `CORS *`, and exposes
   credential, environment-install, publish and delete routes.
2. The existing production use is narrow (composition and TTS), but the target
   architecture is not. Pretending the host is already adopted would be false.
3. ADR-014's seven-day hold suspended new platform production modules. The
   Owner's new decision authorizes **architecture and guarded host work**, not
   publication, provider spend or account access.
4. Strategy's Content Bundle is the production unit. It is still marked
   "Proposed" and its handoff is manual, so ContentOps must consume a
   hash-bound reference rather than assume live synchronization.

## Decision

### D1 — Easel is the production base; ContentOps is the governance extension

Easel v0.2.1 remains pinned by `runtime/easel.lock.json` and read-only in
`.runtime/easel/`. Its host, skills and asset surfaces are the base for content
production. ContentOps owns the governed extension: source and claim checks,
rights, workflow state, receipts, QC, human review and delivery authorization.

This **supersedes ADR-015 D1 only**. ADR-015 D2-D8 remain in force: ContentOps
does not surrender the run, the evidence or the receipt, and the platform
registry stays the single machine-readable platform source.

### D2 — The host is served guarded, never as the upstream default

The host may be served only through `src/contentops/easel/`:

- loopback bind (`127.0.0.1`), never `0.0.0.0`;
- read-only allowlist, with unknown routes denied before upstream;
- no mutation, publish, login, credential, environment-install, settings-write,
  delete or session-write route reachable;
- loopback `Host`/`Origin` checks and no wildcard CORS response;
- non-HTTP scopes denied: `lifespan` passes, websockets are closed before
  upstream, unknown scope types are not forwarded;
- the runtime tree is byte-verified against the pinned commit before `serve`;
  an offline or unverifiable tree is `HOST_BYTES_UNVERIFIED`, not a pass;
- `HOST_BLOCKED` when the runtime, pin or dependencies are absent.

`scripts/easel_host.py` is the only entry point. Running upstream `easel web`
or `web/app.py` directly is outside this decision. If the guard cannot sit in
front of every upstream request without modifying upstream, the host stays
blocked and a separate upstream-patch or isolation ADR is required.

### D3 — Host availability is not approval

A running host, a generated file, a QC pass, a package and a platform draft are
four different facts. None of them is `PUBLISHED`, and none replaces a human
review or a publication authorization. The existing rules stand:
`production_ready` stays `false`, `human_review` stays pending until a person
writes it, and publishing stays manual and separately authorized.

### D4 — One registry, with an explicit Easel binding

`config/registry/platforms.json` (`contentops.platform-registry/v1`) remains
the only machine-readable platform registry. Each row may carry an
`easel_capability` block:

- `UPSTREAM_DECLARED` — an upstream skill names the platform; evidence is the
  upstream skill path; `verified_here` is `false` until this repository runs it;
- `ABSENT` — no upstream capability is named.

`UPSTREAM_DECLARED` never raises the platform's local status above `PLANNED`.
Nine Strategy platforms remain in scope; GitHub stays proof infrastructure, not
a publishing row; the four candidates in Strategy PR #18 are not adopted.

### D5 — Two production lines share evidence, not approvals

One Bundle may produce two independent handoffs:

- `VIDEO` → `contentops.copy-to-video/v1`, the existing M5/Easel chain;
- `GRAPHIC_TEXT` → `contentops.copy-to-graphic/v1`, a manual package with its
  own draft, image-rights, layout, QC and delivery stages.

Both carry `bundle_id`, the Bundle digest and the same source/claim mapping.
Changing shared evidence invalidates both lines. Neither line inherits the
other's approval, and the graphic line does not claim an HTML renderer, a
WeChat draft or a platform publication.

Enforcement: a handoff records the Bundle's logical path and digest; the graphic
package builder re-reads the Bundle and refuses a stale handoff
(`BUNDLE_CHANGED`, `HANDOFF_UNBOUND`); the video review records the digest and a
changed Bundle revokes a written review (`review_revoked_reason`). A digest that
is recorded but never re-checked is not an invariant, so neither line keeps one
unexamined.

### D6 — Staged authorization

This ADR authorizes code, offline tests, documentation and a guarded host
status check. It does **not** authorize:

- installing FastAPI, uvicorn, OpenClaw, browsers or other host dependencies;
- reading or migrating existing credentials, profiles, sessions or account data;
- connecting a real account, creating a platform draft or publishing;
- provider spend, paid generation or a new Easel upgrade;
- merging PR #101 or #105, or treating either as approved.

Enabling a real host or account path requires a separate, explicit approval
after this ADR's security acceptance. `HOST_BLOCKED` is the honest default.

## Consequences

- The target architecture now names Easel as the base, so `ARCHITECTURE`,
  `PRD`, `CURRENT-STATE` and `PLATFORM-INTEGRATION-STATUS` must stop describing
  Easel as a two-file composer only. They must still distinguish target from
  verified runtime.
- The guard is the load-bearing safety boundary. A green unit test for the
  guard does not prove the upstream app has no other mutation path; the host
  remains blocked until that review is recorded.
- A Bundle handoff is a plan. The video and graphic lines can each produce a
  reviewable artifact or a recorded blocker; neither can claim the other's
  state.
- ADR-014's delivery acceptance still applies. Architecture work does not
  replace a real publication or a recorded delivery blocker.

## Acceptance

- `python tests/test_easel_host_guard.py` passes and denies publish,
  credential, settings, environment, delete and unknown routes before upstream,
  closes websocket scopes, and refuses an unverified runtime tree.
- `python scripts/easel_host.py status` reports `HOST_BLOCKED` when the pinned
  runtime or dependencies are absent; `--verify-bytes` reports the content
  comparison, and `serve` always performs it.
- One valid Bundle produces separate VIDEO and GRAPHIC_TEXT handoffs; neither
  carries publish authorization, both name their Bundle bytes, and a handoff
  whose Bundle changed is refused.
- `python tests/test_graphic_workflow.py` passes with rights, path, stale-handoff
  and image refusals, and the graphic contract cannot borrow video stage names.
- `python scripts/dev_check.py` and CI pass; documentation states what has
  actually run.

## Re-review

2026-11-08, together with ADR-014. The Owner decisions still open in Issue #100
(D-3 Strategy-side registration, D-4 wording, X execution authority) remain
open.
