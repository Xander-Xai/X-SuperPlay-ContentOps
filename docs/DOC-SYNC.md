# Documentation Sync

[English](DOC-SYNC.md) | [简体中文](DOC-SYNC.zh-CN.md)

> Last verified: 2026-11-12 on `main` at `c1da6dd`.

> How this repository keeps its documents from lying. The rule is mechanical, not
> aspirational: a tracked doc carries the date it was verified against, and CI
> fails when the code it describes moved after that date.

## Why this exists

Documents rot silently. Nothing crashes when a status table keeps describing last
month's architecture, so the stale page survives every test and every review. The
2026-11-12 sync found the README still describing 公众号 and 小红书 as
"verify-only, no delivery layer" while `video_deliver.py` and
`platform_delivery.py` had been on `main` for days. No check failed. A reader
would simply have believed the old page.

A policy that says "keep the docs current" is not a mechanism. A date plus a
failing check is.

## The contract

Every tracked doc carries one verification line near the top:

```markdown
> Last verified: 2026-11-12 on `main` at `c1da6dd`.
```

Accepted forms (the checker matches these, in either language):

| Form | Example |
|---|---|
| `Last verified:` / `最后验证：` | `> Last verified: 2026-11-12 …` |
| `Status verified:` / `状态验证：` | `> Status verified: 2026-11-12 on main` |
| `Last updated:` / `最后更新：` | `> Last updated: 2026-11-12` |
| `Last reviewed:` / `最后复核：` | `> Last reviewed: 2026-11-12` |
| `Last regenerated …:` | `> Last regenerated from the registry: 2026-11-12` |

The line means: **the facts in this file were checked against the code at this
commit on this date.** It is not a build stamp and not a touch counter. Bumping
it without reading the diff is the one thing that makes the mechanism worthless.

## What is tracked

The authority is [`config/docs/doc-freshness.json`](../config/docs/doc-freshness.json);
this section explains the shape, it does not duplicate the globs.

| Doc | Covers |
|---|---|
| `README.md` / `README.en.md` | Repository status table, entry points |
| `docs/CURRENT-STATE.md` | What runs today, dated Git snapshots |
| `docs/PLATFORM-INTEGRATION-STATUS.md` | Registry rows, per-platform blockers |
| `docs/DEVELOPMENT-PLAN.md` | Milestone status and exit criteria |
| `docs/TEST-PLAN.md` | Suite inventory and CI wiring |
| `docs/RUNBOOK.md` | Executable commands |
| `docs/ARCHITECTURE.md` | Boundaries, component map, rules |
| `docs/PRD.md` | Functional requirement states |
| `docs/QUALITY-STANDARD.md` | Gate definitions |
| `docs/ASR-BACKCHECK.md` | The narration ASR gate |
| `docs/DOC-SYNC.md` | This mechanism |

Exempt, with a reason recorded in the config: ADRs (immutable decisions — a change
is a new ADR), dated audit snapshots, the glossary, and `docs/INDEX.md` (navigation
only; index coverage is enforced by `check_repo_policy.check_index_tracking`).

Adding a Tier-1 doc means classifying it in the config in the same change. The
checker refuses an unclassified Tier-1 doc.

## Triggers

Run the sync when any of these happen:

1. A merge to `main` touches a path mapped to a tracked doc.
2. A capability, platform row, gate or receipt changes state.
3. A Tier-1 doc is added, renamed or removed.
4. An ADR is accepted, superseded or contradicted by the code.
5. A provider fact changes (model id, endpoint, quota, pin).

## Procedure

1. **Read the diff, not the conclusion.**
   `git log --oneline <doc-date>..HEAD -- <mapped paths>`, then `git show --stat`
   on the interesting commits.
2. **Verify remote claims against the live remote.** Branch, PR, issue, tag and
   protection facts come from `gh`, never from a local lock or a previous
   snapshot. A local check proves internal consistency only.
3. **Change the facts.** Delete rows that no longer apply instead of explaining
   them away; a shorter truthful table beats a long hedged one.
4. **Bump the date in the primary and the mirror in the same change.** The checker
   fails when a pair disagrees, so a half-updated pair cannot ship.
5. **Run the gates:**
   ```bash
   python scripts/check_doc_freshness.py
   python scripts/check_i18n.py
   python scripts/check_docs.py
   python scripts/check_governance_ledger.py
   ```
6. **Cite the evidence** you used (PR number, receipt path, commit, URL). A claim
   without a pointer is the next stale row.
7. **Land it through a PR.** `main` is protected; there is no direct push.

## Honesty rules

- **Runtime reality beats documentation.** Receipt > current code > machine-readable
  lock/config > current ADR > CURRENT-STATE > RUNBOOK > old plan.
- **A status rises only with a receipt.** Code that exists raises nothing: no
  registry row moves, no `production_ready` flips, no publication is implied.
- **Say "not verified" instead of guessing.** An untested path is described as
  untested, even when the code looks finished.
- **Degradation is recorded, not smoothed.** Fallbacks and skips (`SKIPPED`,
  `HOST_BLOCKED`, `NOT_RUN`) appear in the doc as they appear in the receipt.
- **Dates are claims too.** A verification date older than the code it describes
  is a failed claim, whether or not anyone reads it.

## Machine checks

| Command | Catches |
|---|---|
| `python scripts/check_doc_freshness.py` | mapped code changed after the doc's date; pair dates disagree; a date more than one day ahead of the UTC runner (one day is allowed because authors date in local time); unclassified Tier-1 doc |
| `python scripts/check_i18n.py` | missing mirror, missing front matter, broken or one-way language switch, duplicate Chinese README |
| `python scripts/check_docs.py` | broken internal links, canonical files missing, stale pin references, secrets |
| `python scripts/check_governance_ledger.py` | CURRENT-STATE EN/ZH/registry date-and-SHA drift (offline) |

`check_doc_freshness.py` runs in `dev_check.py` and in the CI `Repo policy checks`
job. It needs git history, so CI checks out with `fetch-depth: 0`.

Report-only mode exists for local exploration:

```bash
python scripts/check_doc_freshness.py --report-only
python scripts/check_doc_freshness.py --json
```

Report-only never replaces the gate in CI. A stale doc that nobody fixes is the
default outcome otherwise.

## When the check fails

A `STALE` row is not noise and the date is not the fix. Choose one, explicitly:

- **Update the doc.** The normal case: read the diff and correct the facts.
- **Retire the claim.** If the section no longer describes the system, delete it.
- **Re-scope the track.** If the doc genuinely does not depend on that path, edit
  `config/docs/doc-freshness.json` and say why in the PR.

Never bump the date to silence the check. A green gate over an unread diff is
worse than a red one, because it moves the lie into the machine-checked column.

## Cadence

- **Per change:** the gate above, as part of the PR.
- **Monthly:** a full re-read of the Tier-1 set against the live GitHub state —
  the 2026-11-12 pass (issues, PRs, branches, tags, protection, CI, suite count)
  is the template.
- **Quarterly:** delete documents that no longer earn their place. Delete before
  Expand.
