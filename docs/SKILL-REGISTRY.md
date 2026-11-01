# Skill Registry and Doctor

[English](SKILL-REGISTRY.md) | [简体中文](SKILL-REGISTRY.zh-CN.md)

> One resolver, three questions: what exists, which copy wins, and what may it
> be handed to. The router never executes a skill.

## Entry point

`scripts/skill_route.py` is the only resolver. It is stdlib-only, reads front
matter and declared data, and never spawns a process or opens a network
connection.

| Command | Answer |
|---|---|
| `python scripts/skill_route.py --sources` | every declared catalog root, its rights posture, present or absent |
| `python scripts/skill_route.py --list` | every deduplicated skill |
| `python scripts/skill_route.py --match "<deliverable>"` | ranked candidates |
| `python scripts/skill_route.py --resolve <name>` | every exact copy, or a capability verdict |
| `python scripts/skill_route.py --capabilities` | every declared capability and its verdict |
| `python scripts/skill_route.py --doctor` | roots, duplicates, permissions, rights and unsafe paths |

Add `--json` for a machine-readable record. `--resolve` accepts `--account`,
`--pipeline` and `--stage` to scope a capability resolution.

## Two questions that must not be merged

| Question | Layer | Who answers |
|---|---|---|
| What exists on this host? | discovery | `skill_route.py --list/--sources/--match` |
| May this be handed to an adapter? | resolution | `skill_route.py --resolve`, against `runtime/skill-registry.json` |
| May it actually run? | execution | the adapter, the runtime lock verifier and the M5 gate |

Discovery alone never promotes a skill to executable. A declaration in the
registry never grants execution either: the router's verdict is `RESOLVABLE`,
and the returned record always carries `execution_authorized: false`.

Two fields are easy to misread and are named accordingly:

- `provider.path_permitted` means the capability's provider path is permitted by
  declared policy. It is not named `authorized`, because that word would read as
  an execution grant from the caller.
- `accounts: ["*"]` is a routing wildcard. It matches any requested account; it
  is not permission to execute on, or across, accounts.

## Catalog roots

| Priority | Root | Track | Rights posture |
|---:|---|---|---|
| 1 | `.runtime/easel/skills/openclaw` | pinned Easel runtime | external-pinned |
| 2 | `Easel/skills/openclaw` | working Easel checkout | external-checkout |
| 3 | `vendor/gzh-thinktank/gzh_未来智能/skills` | locally vendored 公众号 | unverified-vendor |
| — | `~/.agents/skills` | shared store, resolved separately | operator-controlled |

A name in more than one root is indexed once, from the earliest root. The later
copy is reported as `shadowed`; `--doctor` counts every collision.

`vendor/` is gitignored. Third-party vendor material is a local operator
resource, never a redistribution grant, and must not enter the public
repository.

## Declared capabilities

`runtime/skill-registry.json` (schema `contentops.skill-registry/v1`) is a
pointer table. Each entry records:

| Field | Meaning |
|---|---|
| `id`, `name` | the exact identifiers `--resolve` matches |
| `discovery` | where the skill directory is expected (`shared` or `catalog`) |
| `source` | publisher, upstream package, version, source commit |
| `canonical_path` | the repository code that owns the integration |
| `license` | declared licence status and SPDX id; never a clearance |
| `rights` | verification status, scope and evidence |
| `accounts`, `pipelines`, `stages` | the scope this capability may serve; `accounts: ["*"]` matches any requested account **for routing only** |
| `contract` | input, output and receipt schema |
| `provider` | `path_permitted` plus the network, paid and cross-project-reuse flags; none of them is an execution authorization |
| `runtime` | dependency, approved baseline, lock environment variable, verifier |
| `verification` | status, scope and evidence |
| `execution` | adapter and M5 stage; `authorizes_execution: false` |

Undeclared tracks are deliberately absent. Resolving one returns
`UNKNOWN_SKILL`, which is the honest answer, not a gap to paper over.

## Resolution rules

| Condition | Reason code | Verdict |
|---|---|---|
| no declaration matches the exact name | `UNKNOWN_SKILL` | BLOCKED |
| more than one declaration matches | `DUPLICATE_AMBIGUITY` | BLOCKED |
| requested account/pipeline/stage is not declared | `OUT_OF_SCOPE` | BLOCKED |
| rights are not verified, or the licence is restricted | `UNVERIFIED_RIGHTS` | BLOCKED |
| provider path is not permitted, or network/paid/reuse is declared | `UNAUTHORIZED_PROVIDER` | BLOCKED |
| the skill directory is not installed | `SKILL_NOT_INSTALLED` | BLOCKED |
| the approved baseline or runtime lock is absent | `MISSING_RUNTIME` | BLOCKED |
| exactly one match, rights verified, provider path permitted, runtime ready | `RESOLVABLE` | RESOLVABLE |

Order matters: ambiguity, scope, rights and provider are decided before runtime
presence, so a blocked capability never looks runnable just because a runtime
happens to be installed. A permission field in a skill's front matter is
recorded, never treated as an authorization.

## Execution authorization

Resolution ends where authorization begins. `RESOLVABLE` means "hand this to an
adapter", not "run it". The separate decision lives in ADR-009 and in
`src/contentops/skills/authorization.py`:

```
DISCOVERED -> RESOLVABLE -> EXECUTION_REQUESTED -> AUTHORIZED -> EXECUTED
```

A caller must present a grant bound to the exact skill version, account, pipeline,
stage, operations, subject and budget, with an expiry and a revocation state. Every
blocked path returns `execution_authorized: false`. The adapter's runtime lock
verifier and the M5 `rights_reviewed` gate are unchanged and remain the authority
for their own questions. See
[ADR-009](adr/ADR-009-skill-execution-authorization.md).

Where the grant comes from, and how it is spent, is ADR-010:

| Piece | Where |
|---|---|
| approval record | `projects/<slug>/receipts/skill-execution-approval.json`, `purpose: skill_execution` |
| optional evidence | `receipts/human-review.json`, digest-checked but never authorizing |
| issuer allow-list | `CONTENTOPS_OWNER_IDENTITIES` (unset trusts nobody) |
| executing subject | `CONTENTOPS_EXECUTION_SUBJECT` (a declared label, not authentication) |
| atomic spend | `receipts/grants/<approval_id>/use-NNNN.json` created with `O_EXCL` |
| request dedupe | `receipts/grants/<approval_id>/request-<hash>.json` created with `O_EXCL` |
| managed entry | `python scripts/skill_execute.py <project> --account <one> --operation status\|doctor` |
| receipt | `receipts/executions/<approval_id>-use-NNNN.json`, exclusive, sanitized |

A video review (`human-review.json`) is **not** an execution approval and cannot be
upgraded into one. Every scope field is read from the single approval record, so
there is no derived copy to drift. `approval_id` must be one safe path component;
traversal, symlink escapes and Windows device names are refused, not sanitised.
Consumption is atomic on one local filesystem; a spent use is permanent.


`scripts/m5_production.py` does not import any of this, so the verified M5 chain
keeps its existing trust boundary. Making authorization mandatory inside M5 is a
separate Owner-approved migration. See
[ADR-010](adr/ADR-010-trusted-grant-execution-gate.md).

## media-use

| Field | Value |
|---|---|
| id | `media-use` |
| source | `hyperframes@0.8.222`, commit `f2358315e59731833334c5d881a7fb5543c22a97` |
| canonical path | `src/contentops/media/media_use_adapter.py` |
| scope | accounts `*`, pipeline `M5`, stage `media_use` |
| runtime | approved baseline `runtime/media-use-runtime-baseline.json`, lock env `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK` |
| verification | `VERIFIED`, offline local-only, integration acceptance |
| evidence | `reports/audits/contentops-pr71-media-use-final-audit-2026-10-31.md` |

The registration reuses the merged adapter, runtime baseline, lock verifier and
M5 `media_use` stage. It adds no second manifest and changes no accepted
media-use behaviour. The handoff is declared only:

```
Skill Discovery -> Skill Resolution -> Permission Gate -> Existing Adapter -> M5
```

`scripts/m5_production.py` does not import the router. Legacy M5 runs with no
router installed, and a test asserts that independence.

## Content-production skills (not declared)

Five skills are installed in the shared store for the X•超玩1024 workflow:

- `x-superplay-copy-orchestrator`
- `x-superplay-source-research`
- `x-superplay-capture-plan`
- `x-superplay-broll-production`
- `x-superplay-design-direction`

They are **not declared capabilities**, and the router does not treat them as
runnable. Their bodies reference the account-aware content-router layer:

| Referenced code | Exists on this branch? | Exists on `feat/content-router` (PR #49)? |
|---|---|---|
| `scripts/workflow_gate.py` | no | yes |
| `scripts/workflow_docs.py` | no | yes |
| `scripts/recording_plan.py` | no | yes |
| `src/contentops/workflow/*` | no | yes |
| `scripts/design_router.py` | no | **no** |

The first four are blocked only on the merge. `design_router.py` is referenced by
`x-superplay-design-direction` and does not exist on any branch inspected on
2026-11-01, so that skill needs an edit as well as a merge.

A declaration may be added only after the code it points at exists on the
integration branch. Declaring a pointer to an unmerged branch would make
`RESOLVABLE` a false statement, which is the failure this registry exists to
prevent. Until then the skills are discovery-visible and resolution-blocked.

The record of what these skills actually reference lives in
`runtime/content-skill-status.json`, and
`python scripts/check_skill_references.py` fails when that record stops
matching this checkout: an unrecorded dangling reference, a recorded reference
that has landed, or a skill marked merged whose code is missing.

## Track status

| Track | Status | Why |
|---|---|---|
| VIDEO (Easel) | discovery-only until a catalog root exists on the host | no vendor content in the public repository |
| Content production (`x-superplay-*`) | discovered in the shared store, **not declared** | their code lives on the unmerged `feat/content-router` branch; `design_router.py` is absent there too |
| GZH | BLOCKED | vendored third-party track, rights unverified, not redistributed |
| X | BLOCKED | platform track is unmerged (`feat/47-x-platform-track`, PR #50) |
| XHS | BLOCKED | migration is unmerged and under rights review; no catalog root |

## Boundary

`--doctor` reports structure, licences, permission declarations and unsafe
paths. It does not clear rights, does not grant permission and does not
authorize execution. Issue #57 stays open until execution authorization is a
separate, reviewed decision.
