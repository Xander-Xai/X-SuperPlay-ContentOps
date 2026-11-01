# ADR-012: Convergence decisions — content layer, skills and upstream pins

[English](ADR-012-convergence-decisions.md) | [简体中文](ADR-012-convergence-decisions.zh-CN.md)

> Status: **Accepted** — Owner authorization, 2026-11-01
> Supersedes nothing. Fills the ADR-011 gap reserved by the unmerged
> `feat/content-router` branch (`ADR-011-single-home-platform-tracks`), so this
> record takes 012 to avoid a numbering collision.
> Evidence: [../CONVERGENCE-REQUIREMENTS-2026-11-01.md](../CONVERGENCE-REQUIREMENTS-2026-11-01.md)

## Context

The audit of 2026-11-01 found the repository describing three different systems
at once: `main`, the working branch (`fix/57-m5-media-fixtures`, 17 commits
ahead), and a set of unmerged branches carrying the account-aware content layer.
Five installed `x-superplay-*` skills describe commands and modules that exist
only on those unmerged branches. Upstream pins sit behind current stable
releases.

Decisions D1–D6 were recorded by the Owner on 2026-11-01. This ADR states them
so that later work has one citation instead of a conversation.

## Decision

### D1 — The content router is the canonical account/brief front-end

`feat/content-router` (PR #49) becomes the front-end that turns a topic into a
brief. The M5 evidence chain stays the production engine. One engine, one brief
contract, one gate vocabulary.

It is **not** merged wholesale. It is merged in slices, each slice carrying its
own tests and each slice landing before the next. The order is:

1. **S1 — workflow core.** `src/contentops/workflow/{contract,gate,validators}.py`
   and `scripts/workflow_gate.py`. This is the deterministic stage gate the
   skills call for, and it has no dependency on account configuration.
2. **S2 — evidence-side validators.** `src/contentops/workflow/{sources,capture_plan}.py`,
   `scripts/workflow_docs.py`, `scripts/recording_plan.py`. These unblock
   `x-superplay-source-research` and `x-superplay-capture-plan`.
3. **S3 — account configuration.** `config/accounts/*` and the router scripts.
4. **S4 — remaining stages.** Brief, script, design, optimisation layers.

Each slice updates `runtime/content-skill-status.json` in the same PR, because
landing code the skills name makes the old record false.

### D2 — The five content skills stay undeclared until their code lands

`runtime/skill-registry.json` gains an entry only when the code the entry
points at exists on the integration branch. A declaration is a pointer to
verified code; pointing it at an unmerged branch makes `RESOLVABLE` a false
statement.

`scripts/check_skill_references.py` enforces this: an unrecorded dangling
reference fails, a recorded reference that has landed fails until the record is
updated, and a skill marked merged whose code is missing fails.

### D3 — Easel stays on v0.2.1

Easel v0.3.0 is not adopted now. The delta is 158 commits and 300 files, all
skills moved from `skills/openclaw/` to `skills/builtin/`,
`auto-short-video/scripts/assemble.py` changed, and the upstream tag was
force-replaced while keeping the version number. A tag that can be replaced is
not a pin.

When it is adopted, it is adopted by **content digest**, not by tag, and it
passes the full upgrade gate: provenance verification, upstream diff analysis,
unit tests, Windows tests, three golden renders, receipt comparison, human
review, Founder approval, lock update.

### D4 — HyperFrames moves to 0.8.225 as a patch release, with a re-pin

The delta is 34 commits with export and CLI fixes. `skills/media-use/SKILL.md`
and its references changed inside it, so the pinned skill commit
(`f2358315e59731833334c5d881a7fb5543c22a97`) must be re-pinned and the
approved baseline and host lock regenerated before the new version is used.

The upgrade is executed with the runtime installation, not before: a pin with no
trusted host lock is a pin nothing runs.

### D5 — Untracked content projects are adopted lazily

`projects/x-superplay-1024`, `projects/easel-fi-audio-first` and
`projects/gzh-thinktank` have no `project.yaml` and no receipts. They stay
local and untracked until they are worked on again. Adoption means
`project.yaml`, a source list, and receipts — not a `git add` of the binaries.

### D6 — Worktrees and branches are audited, reported, and deleted only by name

30+ worktrees exist across `.claude/worktrees` and `D:\Temp\AI-Agents`. The
filesystem policy forbids deleting them as routine cleanup. The audit reports
each one with its owner, branch, age and whether it is referenced; deletion is a
separate, per-item approval.

## Consequences

- Documentation can state what is on a branch without a caveat, because the
  branch layers are now named.
- The five content skills stay honest: they are visible, blocked, and their
  missing dependencies are a CI failure rather than a reading exercise.
- No upstream pin moves without a gate, a digest, and an Owner approval.
- The next substantial code change is the S1 slice, not a new capability.

## Revisit triggers

- PR #49 is rewritten or superseded → re-derive the slice order.
- Easel publishes v0.4.0 or the v0.3.0 tag changes again → re-open D3.
- A host runtime lock is generated for media-use → D4 becomes executable.
- The Owner wants a different account/brief front-end → re-open D1.
