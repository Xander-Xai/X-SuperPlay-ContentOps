# Documentation Index

[English](INDEX.md) | [简体中文](INDEX.zh-CN.md)

> Single navigation hub. One fact, one owner. Other docs link, never duplicate.

## Quick Start

1. [README.md](../README.md) — What this repo is, why it exists, status, quick start
2. [CURRENT-STATE.md](CURRENT-STATE.md) — What runs today (verified facts only)
3. [ARCHITECTURE.md](ARCHITECTURE.md) — System boundaries and component diagram
4. [PRD.md](PRD.md) — Product requirements and acceptance criteria
5. [RUNBOOK.md](RUNBOOK.md) — Real executable commands (derived from code)
6. [DEVELOPMENT-PLAN.md](DEVELOPMENT-PLAN.md) — M0–M6 milestones
7. [QUALITY-STANDARD.md](QUALITY-STANDARD.md) — Video/content/fact quality gates
8. [TEST-PLAN.md](TEST-PLAN.md) — Test strategy and coverage

## Contracts

- [SOURCE-ARTIFACT-CONTRACT.md](SOURCE-ARTIFACT-CONTRACT.md) — SourceArtifact schema
- [MEDIA-PROVIDER-CONTRACT.md](MEDIA-PROVIDER-CONTRACT.md) — MediaProvider interface
- [PLATFORM-INTEGRATION-STATUS.md](PLATFORM-INTEGRATION-STATUS.md) — What this branch can do per platform; GitHub as proof infrastructure; Easel coverage
- [EASEL-CAPABILITY-INVENTORY.md](EASEL-CAPABILITY-INVENTORY.md) — Upstream-declared vs integrated vs executable vs production-allowed Easel capabilities
- [PLATFORM-ADAPTER-CONTRACT.md](PLATFORM-ADAPTER-CONTRACT.md) — Delivery-layer adapter interface; no second registry, no second production engine
- [CONTENT-LIFECYCLE-STAGES.md](CONTENT-LIFECYCLE-STAGES.md) — Ordered lifecycle stages, owners, current state and receipts
- [ASR-BACKCHECK.md](ASR-BACKCHECK.md) — The narration ASR gate: a detector that can report a problem, never approve a video
- [MOTION-WORKFLOW-SPEC.md](MOTION-WORKFLOW-SPEC.md) — Dual-account video workflow contracts: sample gate, motion handoff, real-source duration, router → M5
- [adr/ADR-008-media-use-adapter.md](adr/ADR-008-media-use-adapter.md) — HyperFrames `media-use` integration: pinned adapter, not a fork
- [CROSS-REPO-INTEGRATION.md](CROSS-REPO-INTEGRATION.md) — RepoSourceAdapter, repo registry

## Upstream

- [UPSTREAM-EASEL.md](UPSTREAM-EASEL.md) — Easel pin policy, upgrade process, compatibility matrix
- TrendRadar pin: `runtime/trendradar.lock.json` (v6.11.0, commit `ceabb027`), vendored at `.runtime/trendradar/v6.11.0/`, recorded in `docs/CURRENT-STATE.md` — no dedicated policy doc yet

## Milestone plans

- [CONVERGENCE-REQUIREMENTS-2026-11-01.md](CONVERGENCE-REQUIREMENTS-2026-11-01.md) — docs / skills / branch / upstream-pin convergence — **accepted 2026-11-01; steps 3–5 landed later**
- [M4-H3-PLAN.md](M4-H3-PLAN.md) — M4 MiniMax H3 video (Issue #22) — **implemented**
- [M4.5-MEDIA-CONVERGENCE-PLAN.md](M4.5-MEDIA-CONVERGENCE-PLAN.md) — M4.5 media convergence (Issue #27) — **implemented**
- [ENHANCED-GOLDEN-PLAN.md](ENHANCED-GOLDEN-PLAN.md) — Enhanced Golden A/B/C/D — **next executable phase after convergence**
- [m5-baseline/m5-characterization-2026-11-10.md](m5-baseline/m5-characterization-2026-11-10.md) — pass counts a structural M5 refactor must preserve (slice 1 of #140)

## Governance

- [DEVELOPMENT-STANDARD.md](DEVELOPMENT-STANDARD.md) — Development rules
- [FILE-PLACEMENT-POLICY.md](FILE-PLACEMENT-POLICY.md) — Where files belong
- [GLOSSARY.md](GLOSSARY.md) — High-frequency terminology
- [SKILL-REGISTRY.md](SKILL-REGISTRY.md) — Skill discovery, declared capabilities, resolution verdicts and the doctor
- [DEFERRED-WORK.md](DEFERRED-WORK.md) — descoped work, archive locations and reopening conditions
- [DOC-SYNC.md](DOC-SYNC.md) — Documentation freshness: contract, triggers, procedure and the machine check
- [governance/ARCHIVE-SALVAGE-LEDGER.md](governance/ARCHIVE-SALVAGE-LEDGER.md) — archive snapshot vs `main`, path+blob

## Bilingual Policy

Tier-1 docs have zh-CN mirrors with `.zh-CN.md` suffix. **README is the exception
(2026-11-12):** `README.md` is the Chinese original and `README.en.md` is the
English mirror, because the repository's primary readers are Chinese-speaking.
Every other Tier-1 doc stays English-primary.

Run `python scripts/check_i18n.py` to verify structural consistency in either
direction, and `python scripts/check_doc_freshness.py` to verify that each
tracked doc was checked against the code it describes (see [DOC-SYNC.md](DOC-SYNC.md)).

## Decisions

- [adr/ADR-001-easel-runtime.md](adr/ADR-001-easel-runtime.md)
- [adr/ADR-002-contentops-boundaries.md](adr/ADR-002-contentops-boundaries.md)
- [adr/ADR-003-minimax-plan-provider.md](adr/ADR-003-minimax-plan-provider.md)
- [adr/ADR-004-cross-repo-source-contract.md](adr/ADR-004-cross-repo-source-contract.md)
- [adr/ADR-005-human-approval.md](adr/ADR-005-human-approval.md)
- [adr/ADR-006-upstream-upgrade-policy.md](adr/ADR-006-upstream-upgrade-policy.md)
- [adr/ADR-007-m5-evidence-production-chain.md](adr/ADR-007-m5-evidence-production-chain.md)
- [adr/ADR-007-minimax-speech-transport.md](adr/ADR-007-minimax-speech-transport.md) — numbering collision with the M5 ADR; both records exist
- [adr/ADR-008-media-use-adapter.md](adr/ADR-008-media-use-adapter.md)
- [adr/ADR-009-skill-execution-authorization.md](adr/ADR-009-skill-execution-authorization.md)
- [adr/ADR-010-trusted-grant-execution-gate.md](adr/ADR-010-trusted-grant-execution-gate.md)
- [adr/ADR-012-convergence-decisions.md](adr/ADR-012-convergence-decisions.md) — convergence decisions D1–D6 (2026-11-01). ADR-011 is reserved by the unmerged `feat/content-router` branch
- [adr/ADR-013-media-use-mutating-authorization-proposal.md](adr/ADR-013-media-use-mutating-authorization-proposal.md) — **Proposed only**: write-verb authorization and idempotency (no execution change)
- [adr/ADR-014-delivery-validation-hold.md](adr/ADR-014-delivery-validation-hold.md) — seven-day hold on P2 expansion (2026-11-01 → 2026-11-07) so a first real delivery lands
- [adr/ADR-015-platform-placeholders-and-content-bundle.md](adr/ADR-015-platform-placeholders-and-content-bundle.md) — nine-platform placeholders, one reused registry, Content Bundle consumption and the Easel capability boundary; D1 superseded by ADR-016
- [adr/ADR-016-easel-host-adoption.md](adr/ADR-016-easel-host-adoption.md) — Owner adopts the pinned Easel host, guarded loopback/read-only, and the two-line handoff
- [adr/ADR-017-coding-agent-driver.md](adr/ADR-017-coding-agent-driver.md) — a coding agent is a supported driver through a fixed step plan, with no new publication or approval authority
- [adr/ADR-018-governance-closeout-scope.md](adr/ADR-018-governance-closeout-scope.md) — Apache-2.0 license, descoped unfinished tracks, manual X authority, artifact-based upstream watch and the zero-backlog target
- [adr/ADR-019-receipt-history-exposure.md](adr/ADR-019-receipt-history-exposure.md) — rotate the PAYG key, accept the already-public balances/voice IDs/fingerprints, and keep guarding new receipts
- [adr/ADR-020-read-only-scene-analysis-adapter.md](adr/ADR-020-read-only-scene-analysis-adapter.md) — read-only scene analysis adapter: pilot boundary, no mutation authority
- [adr/ADR-021-stable-production-gates.md](adr/ADR-021-stable-production-gates.md) — one stable production entry with fail-closed VIDEO and GRAPHIC_TEXT gate sets

## Agent Rules

- [../AGENTS.md](../AGENTS.md) — AI agent execution discipline

## Research

- [../research/README.md](../research/README.md) — Research index and archive

## Audit

- [AUDIT-REPORT.md](AUDIT-REPORT.md) — Repository audit (2026-10-03)
- [ARCHITECTURE-AUDIT-2026-11-10.md](ARCHITECTURE-AUDIT-2026-11-10.md) — Start-to-finish subsystem map, cross-checked against the tree (2026-11-10)
- [governance/ARCHIVE-SALVAGE-LEDGER.md](governance/ARCHIVE-SALVAGE-LEDGER.md) — Three-state path+blob comparison of the archive snapshot against `main` (2026-11-11)
- [audits/windows-subprocess-audit.md](audits/windows-subprocess-audit.md) — Windows console popup audit, classification of every subprocess callsite, and the unified process layer (Issue #16)
- [../reports/audits/github-governance-2026-10-31.md](../reports/audits/github-governance-2026-10-31.md) — GitHub governance execution: PR/Issue/Branch/CI/security review and the merge of PR #48 (2026-10-31)
- [../reports/audits/contentops-phase2-security-and-unblock-2026-10-31.md](../reports/audits/contentops-phase2-security-and-unblock-2026-10-31.md) — Phase-2 security, third-party rights and PR-unblock audit (2026-10-31)
- [../reports/audits/contentops-phase3-p0-convergence-2026-10-31.md](../reports/audits/contentops-phase3-p0-convergence-2026-10-31.md) — Phase-3 P0 convergence and stack unlock (2026-10-31)
- [../reports/audits/contentops-pr71-media-use-final-audit-2026-10-31.md](../reports/audits/contentops-pr71-media-use-final-audit-2026-10-31.md) — PR #71 media-use integration: security, licence, code, E2E and merge-gate audit (2026-10-31)
- [../reports/audits/media-use-premerge-convergence-2026-11-01.md](../reports/audits/media-use-premerge-convergence-2026-11-01.md) — Current PR #86/#89 pre-merge facts, integration gates and release boundaries
- [../reports/audits/contentops-phase4-delivery-unlock-2026-10-31.md](../reports/audits/contentops-phase4-delivery-unlock-2026-10-31.md) — Phase-4 delivery unlock: #62 merge prep, combined M5 acceptance, #49 order, Owner decisions (2026-10-31)
- [../reports/audits/contentops-phase5-integration-convergence-2026-10-31.md](../reports/audits/contentops-phase5-integration-convergence-2026-10-31.md) — Phase-5 integration convergence: #71 overlap, recommended route, rights gate, #62 re-review (2026-10-31)
- [../reports/audits/worktree-and-branch-audit-2026-11-01.md](../reports/audits/worktree-and-branch-audit-2026-11-01.md) — worktree and branch inventory, classification and cleanup order (2026-11-01)
- [../reports/audits/github-governance-2026-11-03.md](../reports/audits/github-governance-2026-11-03.md) — PR, issue and branch governance pass; delete candidates awaiting named Owner approval (2026-11-03)
- [../reports/audits/github-governance-closeout-2026-11-04.md](../reports/audits/github-governance-closeout-2026-11-04.md) — zero-backlog closeout: license, descoped tracks, archived branches and final verification (2026-11-04)
- [../reports/audits/rights-audit-2026-11-04.md](../reports/audits/rights-audit-2026-11-04.md) — GZH/XHS license matrices and public receipt exposure; decisions still required (2026-11-04)

## Fact Priority

```
REAL EXECUTION RECEIPT
> CURRENT CODE
> MACHINE-READABLE LOCK / CONFIG
> CURRENT ADR
> CURRENT-STATE
> RUNBOOK
> RESEARCH
> OLD PLAN
```
