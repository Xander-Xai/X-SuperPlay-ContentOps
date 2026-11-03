# ADR-018 — Governance closeout: license, descoped tracks and the zero-backlog target

- Status: **Accepted — Owner authorization, 2026-11-04**
- Supersedes: nothing; complements ADR-014 (delivery hold) and ADR-015 (platform placeholders)
- Refs: #6, #11, #15, #51, #56, #94, #100

## Context

After #101, #105, #107, #108, #109 and #110 merged, the repository had zero open
PRs but still carried open issues that were not actually being worked, two
source branches kept only for those issues, and four dirty worktrees. The Owner
asked for a state with **no open PR, no open issue and no non-`main` branch**,
without pretending unfinished work was done.

## Decisions

### D1 — License is Apache-2.0

The repository license is Apache-2.0, matching the Easel upstream. `LICENSE`
contains the standard Apache License 2.0 text. Third-party components that are
not on `main` are not relicensed by this decision.

### D2 — Unfinished tracks are descoped, not completed

Issues #6 (three E2E videos), #51 (XHS migration), #56 (GZH rights audit) and
#94 (S3–S4) are moved to `docs/DEFERRED-WORK.md`. Their branches and worktrees
are archived under `D:\Archives\contentops\2026-11\` and then removed from the
repository. Closing those issues records a scope decision; it does not record
delivery.

### D3 — X execution authority stays manual

Issue #100's outstanding decisions D-3 (Strategy-side registration), D-4 (scope
wording) and X execution authority are recorded here as **deferred, not
granted**. ContentOps gains no X API, posting or metric authority. Publication
remains manual and separately authorized.

### D4 — Upstream watch stops creating issues

The Easel upstream watch writes its report to the workflow job summary and
uploads it as a workflow artifact. It no longer creates or updates a rolling
issue, so #15 can close without the next run recreating it. The watch remains
DETECT → CLASSIFY → REPORT and never upgrades automatically.

### D5 — Zero-backlog target

The repository target after this ADR is: zero open PRs, zero open issues, only
`main` as a branch, and only the primary worktree. A closed item must carry one
of three dispositions: delivered, superseded, or descoped with an archive entry.
A silent closure is not permitted.

## Consequences

- `docs/DEFERRED-WORK.md` is the single home for descoped work; an item leaves it
  only when its reopening condition is met and a new issue/PR records the result.
- The archived bundles are the only copy of the removed branches. The manifest
  records byte counts and SHA-256; every bundle was verified before deletion.
- The `upstream:easel` label remains for manual use, but no automation creates an
  issue with it.
- `production_ready` remains `false` and publication count remains 0. This ADR
  grants no production, provider, credential or publishing authority.
