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
- [CROSS-REPO-INTEGRATION.md](CROSS-REPO-INTEGRATION.md) — RepoSourceAdapter, repo registry

## Upstream

- [UPSTREAM-EASEL.md](UPSTREAM-EASEL.md) — Easel pin policy, upgrade process, compatibility matrix

## Milestone plans

- [M4-H3-PLAN.md](M4-H3-PLAN.md) — M4 MiniMax H3 video (Issue #22) — **implemented**
- [M4.5-MEDIA-CONVERGENCE-PLAN.md](M4.5-MEDIA-CONVERGENCE-PLAN.md) — M4.5 media convergence — **next executable phase**

## Governance

- [DEVELOPMENT-STANDARD.md](DEVELOPMENT-STANDARD.md) — Development rules
- [FILE-PLACEMENT-POLICY.md](FILE-PLACEMENT-POLICY.md) — Where files belong
- [GLOSSARY.md](GLOSSARY.md) — High-frequency terminology

## Bilingual Policy

Tier-1 docs have zh-CN mirrors with `.zh-CN.md` suffix. Run `python scripts/check_i18n.py` to verify structural consistency.

## Decisions

- [adr/ADR-001-easel-runtime.md](adr/ADR-001-easel-runtime.md)
- [adr/ADR-002-contentops-boundaries.md](adr/ADR-002-contentops-boundaries.md)
- [adr/ADR-003-minimax-plan-provider.md](adr/ADR-003-minimax-plan-provider.md)
- [adr/ADR-004-cross-repo-source-contract.md](adr/ADR-004-cross-repo-source-contract.md)
- [adr/ADR-005-human-approval.md](adr/ADR-005-human-approval.md)
- [adr/ADR-006-upstream-upgrade-policy.md](adr/ADR-006-upstream-upgrade-policy.md)

## Agent Rules

- [../AGENTS.md](../AGENTS.md) — AI agent execution discipline

## Research

- [../research/README.md](../research/README.md) — Research index and archive

## Audit

- [AUDIT-REPORT.md](AUDIT-REPORT.md) — Repository audit (2026-10-03)
- [audits/windows-subprocess-audit.md](audits/windows-subprocess-audit.md) — Windows console popup audit, classification of every subprocess callsite, and the unified process layer (Issue #16)

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
