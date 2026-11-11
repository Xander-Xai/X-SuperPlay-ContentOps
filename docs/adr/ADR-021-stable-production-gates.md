# ADR-021: One fail-closed preflight for content production

- Status: proposed (local change, not yet merged)
- Date: 2026-11-12
- Refs: the 2026-11-12 workflow gap audit (`projects/_local/workflow-gap-audit-2026-11-12.md`)

## Context

The repository implements account DNA, evidence-bound copy, copy review,
MiniMax voice clone, H3 bookends, free-stock B-roll and Huashu motion. All of
them are *conditional*: they fire only when `project.yaml` names
`account_slug`, when `motion.backend` is set, when `--narration-provider` is
passed, when `--avatar-provider` is passed, or when an operator remembers to
run `copy_review.py`.

A 2026-11-11 run produced a video and a graphic package by calling
`m5_production.py` / `bundle_handoff.py` / `graphic_package.py` directly. It
never named an account, never asked about material shortfall, never asked for
copy approval and never asked about digital-human bookends. Because
`m5_production._load_narration_profile()`, `_load_digital_presenter_profile()`
and `stage_motion()` all read account DNA through `account_slug`, that single
missing field silently selected Windows SAPI, no avatar and
`motion-stage.json: NOT_CONFIGURED`. The Huashu visual motion gate then
returned a red light. The run was technically successful and substantively
wrong.

`workflow_gate.py:208-213` already states the video contract is not wired into
a single producer. Existing unit tests call `produce_video.produce()` directly,
so adding gates inside `produce()` would break them and would not cover the
other direct entries anyway.

## Decision

Add an EXTENSION (no upstream modification), not a change to any existing
producer:

1. `scripts/production_gates.py` — one contract with seven VIDEO gates:
   `account`, `copy_review`, `evidence_links`, `asset_sufficiency`,
   `avatar_bookends`, `style_audio`, `runtime_readiness`; and five
   GRAPHIC_TEXT gates: `account`, `copy_review`, `evidence_links`,
   `asset_rights`, `runtime_readiness`. `check()` is read-only and fail-closed;
   `require()` raises before a producer is invoked. `runtime_readiness` exists
   because an approved decision is not an executable run: a 2026-11-12
   acceptance run passed every decision gate and then blocked 89 seconds later
   on a missing `SILICONFLOW_API_KEY`.
2. `scripts/make_content.py` — the single stable CLI: `answer`, `check`,
   `status`, `run`. `run` calls `require()` first and then delegates to the
   existing `produce_video.produce()`. It never signs copy review on a human's
   behalf; `copy_review.py --approve` remains the only signature.
3. `answer` writes `receipts/production-intent.json` and idempotently adds
   `account_slug` (plus `motion.backend`) to `project.yaml`, backing up the
   original. `media_use` is deliberately **not** auto-written: enabling it
   requires reviewed rights sidecars, and inventing one would fail the real
   rights gate.
4. The asset-shortfall gate records an explicit decision (`supplement`,
   `local-free`, `minimax-authorized`). Choosing MiniMax records consent but
   does **not** lift ADR-014 or BillingGuard; `check()` still fails closed with
   `BLOCKED_BY_POLICY` and never calls a provider.
5. `scripts/qc_video.py` rejects an ambiguous `--video` target and refuses to
   overwrite a `CURRENT` / `PASS` QC receipt with a degraded FAIL.
6. `produce_video.py` keeps its behaviour unchanged; its docstring now points
   to the stable entry. Direct calls remain a documented diagnostic path.

`account` accepts both DNA slugs and the Bundle treatment roles
(`explorer` → `x-superplay-1024`, `thinktank` →
`x-superplay-future-intelligence`), closing the vocabulary gap that let a
handoff name an account without ever loading its DNA.

## Consequences

- A real production run now has one command and seven explicit human answers.
  Skipping any of them stops the run instead of silently degrading.
- `answer` materialises `sources/source-refs.json` and
  `00_brief/evidence-pack.json`; `m5_production.build()` also ensures the refs
  before the script stage, so the motion planner and the citation column work
  from any entry point. `stage_script` writes one markdown citation (a title
  plus a followable url) per claim.
- `produce_video.py` refuses without an intent (`PRODUCTION_INTENT_MISSING`);
  `--diagnostic` is the explicit escape hatch. `m5_production.py` remains a
  diagnostic path by design and says so in its output contract.
- `--asset-policy minimax-authorized` is refused while ADR-014 holds, so the
  option is no longer a dead end that silently records an unusable consent.
- `copy_fingerprint` additionally covers `draft.md` and `graphic-input.json`
  when present, so a GRAPHIC_TEXT review means something; a video project's
  fingerprint is unchanged.
- `account_slug` makes the already-implemented voice clone, avatar and motion
  capabilities fire automatically from DNA, which also removes the root cause
  of the visual motion red light.
- All outputs keep `production_ready: false` and `publish_authorized: false`.
  A green preflight is not founder approval, a spend authorization or a
  publication permission.
- Existing producers and their tests are unchanged. CI gains
  `tests/test_production_gates.py`.
- Direct `produce_video.py` / `m5_production.py` calls are still possible and
  are **not** gate-checked. A future change should either route them through
  `require()` or mark them explicitly diagnostic in the CLI. This ADR does not
  claim that gap is closed.
- No external service, credential, quota or publication is touched.
