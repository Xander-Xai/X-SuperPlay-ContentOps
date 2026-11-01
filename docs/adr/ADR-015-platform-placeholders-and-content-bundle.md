# ADR-015: Platform placeholders, Content Bundle consumption and the Easel boundary

Status: **Accepted — Owner authorization, 2026-11-01**; **D1 superseded by [ADR-016](ADR-016-easel-host-adoption.md) on 2026-11-02**
Date: 2026-11-01
Issue: #100
Related: [ADR-002](ADR-002-contentops-boundaries.md), [ADR-006](ADR-006-upstream-upgrade-policy.md), [ADR-012](ADR-012-convergence-decisions.md), [ADR-014](ADR-014-delivery-validation-hold.md)
Strategy authority: `Xander-Xai/X-SuperPlay-Strategy` — `01-Strategy/Content-Kernel-and-Bundle-Architecture-V1.md` (`68245cc`, 2026-11-01), `90-Templates/content-bundle.yaml`, `03-Execution/Platform-Repository-Registry.yaml`

## Context

A third-party proposal of 2026-11-01 asked ContentOps to become an
"Easel-Based Self-Media Full-Lifecycle Operating System", with Easel's agent,
workbench and publishing as the base and ContentOps as an extension layer.
ADR-014 already recorded the Owner's response to that proposal: a seven-day
hold on new platform production modules, pending real delivery.

An adversarial review of the proposal (14 agents, 161 findings) established
four facts that decide the line:

1. ContentOps's production use of Easel is **two upstream files** —
   `skills/openclaw/auto-short-video/scripts/assemble.py` (composition) and
   `skills/shared/scripts/tts.py` (V1 narration only; M5 uses Windows SAPI).
   It is not a partial adoption of the workbench.
2. Easel v0.2.1 does implement the five lifecycle stages and names seven
   publishing platforms, but its coverage is **6 of Strategy's 9 platforms**.
   CSDN, YouTube and X have no upstream capability; Kuaishou has upstream
   capability but is not in the Strategy portfolio.
3. A platform registry already exists as designed code —
   `contentops.platform-registry/v1`, `src/contentops/platforms/registry.py`,
   `config/registry/platforms.json`, `scripts/platforms.py`,
   `tests/test_platform_registry.py` — on the local, unpushed branch
   `feat/xhs-fa-migration`. A new YAML registry would be the third platform
   surface, and this repository has no PyYAML in CI.
4. Strategy has since published the Content Kernel / Content Bundle contract,
   which makes the Bundle the default production unit and does not name
   ContentOps anywhere in its authority map.

The Owner's direction (2026-11-01) is therefore adopted as a bounded exception
inside ADR-014, not as a replacement for it.

## Decision

### D1 — Easel is the priority-reuse capability system, not the runtime base

> **Superseded 2026-11-02 by ADR-016.** The Owner chose full Easel host
> adoption. This section is retained as history; D2-D8 remain in force.

Easel stays the first place to look for a capability, and its integration is
expected to grow beyond composition over time. This ADR does **not** fix Easel
to `assemble.py` and `tts.py` permanently.

What this ADR fixes is the current **verified** surface: two files. Any further
capability is adopted by a separate evaluation with its own acceptance, and is
never claimed before it runs. Adopting the OpenClaw agent, the web workbench,
`profiles/`, `outputs/` or browser publishing is a separate decision that
requires superseding ADR-002 and revising PRD §6.

### D2 — ContentOps keeps the run, the evidence and the receipt

Easel may produce bytes. ContentOps owns `SourceArtifact`, `ClaimLedger`,
workflow state, `MediaManifest`, receipts, the rights gate and human review.
A capability being available in Easel never transfers any of that ownership.
This restates ADR-002 and does not narrow it.

### D3 — One platform registry, reused and extended

The registry is `config/registry/platforms.json` with schema
`contentops.platform-registry/v1`, read by `src/contentops/platforms/registry.py`
and operated by `scripts/platforms.py`. No second registry, no YAML variant.

`feat/xhs-fa-migration` is **not** merged. The registry module, CLI and data
shape were copied after audit; the branch's XHS workflow, publishing and
account identities were not. A new field `strategy_platform` is added so a
local entry that splits one platform (Xiaohongshu video / image) still maps to
exactly one Strategy platform. The field is additive: a v1 file without it
still loads, but a local entry without it fails validation, because a split
entry must never become a second platform.

Ten machine entries, one per local production surface:

| Strategy platform | Local entries |
|---|---|
| douyin | `douyin` |
| xiaohongshu | `xiaohongshu_video`, `xiaohongshu_image` |
| bilibili | `bilibili` |
| wechat_channels | `shipinhao` |
| wechat_official_account | `wechat_article` |
| zhihu | `zhihu` |
| csdn | `csdn` |
| youtube | `youtube` |
| x | `x` |

GitHub is documented in `docs/PLATFORM-INTEGRATION-STATUS.md` and is **not** a
machine entry: it has no pipeline, no account and no publish target, and the
loader would force a false value into a required field.

### D4 — Status is a claim about evidence

`PLANNED` means no platform code exists on this branch. `INTEGRATED` requires
code plus offline tests. `TESTED` requires a real local run. `PILOT_READY`
requires a real platform draft. `PRODUCTION_ACCEPTED` requires a published work
with a receipt. A placeholder may carry no executable code, but it must name
its blocker in `not_claimed`; a `PLANNED` row with no blocker fails the suite.

A general video-render PASS is not evidence that a platform-specific workflow
exists. On this branch that means exactly one row is not `PLANNED`: `x`, which
is ContentOps's own manual-only offline gate.

### D5 — Public registry, public facts only

ContentOps is public; Strategy is private. The registry carries platform ids,
local integration state, capability shape, blockers and public technical
evidence. It carries no private repository names, no account identities, no
portfolio status and no credentials. `config/registry/accounts.json` lists only
`x-superplay-english`, the one account configuration already tracked here.

Removing a file does not undo a historical exposure; that audit is separate
(Issue #56, and the account-config review recorded in `docs/SKILL-REGISTRY.md`).

### D6 — ContentOps consumes the Content Bundle, Strategy owns it

`src/contentops/content_kernel/bundle.py` validates a Bundle before
consumption: identity shape, account treatments, the `baseline | enhanced |
experimental` lane vocabulary, the `default | strict_evidence` execution hint,
asset capability and evidence-role enums, claim binding for `direct_evidence`,
the four fail-closed invariants, and credential-shaped fields.

It does not re-derive a thesis, re-choose a lane, re-route a platform or create
a second kernel. A Bundle is a plan; it is never a publication and never a
receipt.

### D7 — Nine platforms, six Easel-bound

The scope is all nine Strategy platforms. Easel coverage is a per-row fact, not
a scope limit: `douyin`, `xiaohongshu` (both forms), `bilibili`,
`wechat_channels`, `wechat_official_account` and `zhihu` are named upstream;
`csdn`, `youtube` and `x` are native ContentOps work. Kuaishou stays out — it
is an Easel capability the portfolio does not carry.

### D8 — No S3 merge and no early authority migration

Account DNA, the content router and the platform workflows stay in their
S1–S4 order. Missing account configuration is expressed as a blocker reason,
not worked around by a placeholder. Creating a placeholder never completes a
migration, and the existing platform execution repositories keep their
authority until a separate, Owner-approved migration.

## Consequences

- The registry is a contract about **this branch**, so it will look empty next
  to Strategy's portfolio. That is the honest reading and must stay visible.
- Adding a platform means adding a row and its evidence, never a second
  production system.
- Adopting another Easel capability requires a new evaluation and a receipt;
  the ADR does not pre-authorise any of them.
- `docs/PLATFORM-INTEGRATION-STATUS.md` is the human-readable mirror of the
  machine file and must change in the same PR.
- The outstanding Owner decisions (D-3 Strategy-side registration, D-4 scope
  wording, X execution authority) remain open and are listed in Issue #100.
