# Pre-copy research contract

[English](PRECOPY-RESEARCH.md) | [简体中文](PRECOPY-RESEARCH.zh-CN.md)

> Contract `contentops.precopy-research/v1`. Verified facts only.
>
> Last verified: 2026-11-12 on `main` at `c1da6dd`.

## Why this exists

`AGENTS.md` §1.3 requires **Evidence before Claim**. In practice, the fastest
way to break that rule is to start drafting copy before anyone has read the
repository or checked a source. This contract makes the research phase a
fail-closed gate rather than a good intention: **no copy is authored or
approved until a named human has signed the research package**.

It applies to both production lines before they diverge — `VIDEO`
(`script/master.md`) and `GRAPHIC_TEXT` (`02_draft/draft.md`). It is not a
third production line and not a new account or platform.

Related: [CONTENT-LIFECYCLE-STAGES.md](CONTENT-LIFECYCLE-STAGES.md),
[RUNBOOK.md](RUNBOOK.md), [TEST-PLAN.md](TEST-PLAN.md).

## Contract artifacts

| Artifact | What it must contain | Machine check |
|---|---|---|
| `00_preresearch/content-intent.json` | The router's `contentops.content-intent/v1` document this research serves, copied verbatim | `schema` matches; `route_mode` ∈ {`USER_TOPIC`, `HOTSPOT_DISCOVERY`}; non-empty `topic`, `account_id`, `account_profile_version`; `route_context.topic_origin` consistent with the mode; `HOTSPOT_DISCOVERY` additionally needs `candidate_id` and `search_plan_id` |
| `00_preresearch/project-reading.md` | Which repository files were actually read, and the facts taken from them, with paths/line numbers | headings, minimum length, at least 3 distinct repository paths |
| `00_preresearch/outline.md` | The outline / handbook for this piece, before any final copy exists | at least 3 outline items or headings, minimum length |
| `00_preresearch/evidence-list.json` | Authoritative, followable sources, graded by kind | at least 3 items; each needs `id`, `title`, `kind` (`primary` / `official` / `interpretation`) and a `http(s)://` or `repo://` URL; at least one `primary` or `official` |
| `00_preresearch/boundary.md` | Honest scope: what was verified, what was not, and what this phase does not produce | must state `production_ready: false` and `publish_authorized: false` |
| `receipts/precopy-research.json` | Fingerprint-bound human sign-off | `status: APPROVED`, named `reviewer`, written `opinion`, `approved_at`, `artifacts_sha256` |

The fingerprint is SHA-256 over the five labeled artifact byte strings.
Editing any artifact after signing reports `STALE`; there is no force switch
and no automatic re-approval.

## Where the topic comes from

The research phase does not invent a topic and does not accept a hand-written
one. It consumes the `ContentIntent` the router already produced, which is why
the two entrances converge here rather than in the copy:

| Entrance | `route_mode` | `route_context.topic_origin` | Extra provenance the intent must carry |
|---|---|---|---|
| A topic the user named | `USER_TOPIC` | `USER_INPUT` | — |
| A topic selected from a hotspot sweep | `HOTSPOT_DISCOVERY` | `HOTSPOT_SELECTION` | `candidate_id`, `search_plan_id` |

Both modes emit the same `contentops.content-intent/v1` shape, so nothing
downstream of this gate can tell which entrance was used except by reading
`route_context`. `HOTSPOT_DISCOVERY` carries one extra human decision before
research — `CANDIDATES_READY → TOPIC_SELECTED` — but neither mode may skip
research: both arrive at `EVIDENCE_REQUIRED`, and `BRIEF_READY` is only
reachable through this gate.

The binding is enforced two ways:

- `scripts/preresearch.py intent` copies `00_brief/brief.json`'s `intent`
  object into `00_preresearch/content-intent.json`. There is no other supported
  way to produce that artifact, and it refuses when no brief exists
  (`NO_ROUTED_INTENT`) or when the package is already approved
  (`ALREADY_APPROVED`).
- When `00_brief/brief.json` exists, `check` requires the research copy to
  match it exactly. Re-routing the same project to a different topic therefore
  turns the gate red on its own, without touching the signed receipt.

## Procedure

```powershell
# 1. Scaffold the four written artifacts (never overwrites existing files).
python scripts\preresearch.py init --project projects\my-video

# 2. Bind the intent the router produced for this project.
python scripts\preresearch.py intent --project projects\my-video

# 3. Read the project, verify sources, fill the outline, evidence list and boundary.

# 4. Check the package. Exit 4 means BLOCKED.
python scripts\preresearch.py check --project projects\my-video

# 5. A named human signs. --confirm is mandatory; no --force exists.
python scripts\preresearch.py approve --project projects\my-video `
  --reviewer "Your Name" --opinion "Read the diff and verified the sources" --confirm
```

Only then may copy be written and reviewed:

```powershell
python scripts\copy_review.py projects\my-video --approve `
  --reviewer "Your Name" --opinion "Reviewed the narration" --confirm
python scripts\make_content.py check --project projects\my-video
```

## Where the gate is enforced

| Enforcement point | Behaviour |
|---|---|
| `scripts/production_gates.py` — 8th VIDEO gate, 6th GRAPHIC_TEXT gate | `make_content.py check` / `run`, `produce_video.produce()` via `require`, and the Easel driver's check step all fail closed |
| `scripts/copy_review.py --approve` | refuses to record any copy decision (`APPROVED` or `CHANGES_REQUESTED`) while research is `NOT_STARTED`, `INCOMPLETE`, `AWAITING_APPROVAL`, `STALE` or `INVALID_RECEIPT` |
| `scripts/preresearch.py` | `init` / `intent` / `check` / `status` / `approve`; exit 4 when blocked |

A direct `m5_production.py` / `produce_video.py` invocation remains a
**diagnostic path** and is not gate-checked, exactly as before. This contract
does not change that boundary and does not add a publication step.

## States

| State | Meaning |
|---|---|
| `NOT_STARTED` | every artifact is missing — nothing has been started |
| `INCOMPLETE` | some artifacts are missing, or they fail a content check (unbound intent, empty evidence list, missing boundary declarations, too few repository paths, etc.) |
| `AWAITING_APPROVAL` | artifacts are valid; a named human has not signed yet |
| `INVALID_RECEIPT` | the receipt is not `APPROVED` or lacks a reviewer/opinion |
| `STALE` | an artifact changed after approval; re-check and re-approve |
| `APPROVED` | gate open for copy work only |

## Honesty boundary

- Research approval is **not** copy approval, production approval or
  publication. Both receipts keep `production_ready: false` and
  `publish_authorized: false`.
- The `init` scaffold alone cannot pass: there is no intent yet, the evidence
  list is empty and the reading notes carry `TODO` markers. Placeholder URLs are
  refused.
- Generated images or videos are visual support and never factual evidence.
- Historical projects without a research package now report `NOT_STARTED` (no
  artifacts) or `INCOMPLETE` (partial) at preflight. Run `init`, fill the artifacts, `check`, then `approve` before
  continuing them. No silent grandfathering is applied.

## Verification

`tests/test_precopy_research.py` (25 cases) covers missing artifacts, scaffold
refusal, idempotent `init`, intent binding for both entrances, re-routing
invalidation, evidence and boundary checks, named-reviewer requirements,
fingerprint drift, CLI `init → intent → check → approve`, and the
`copy_review.py` refusal. It is registered in `.github/workflows/ci.yml`.
