# Development Plan

[English](DEVELOPMENT-PLAN.md) | [简体中文](DEVELOPMENT-PLAN.zh-CN.md)

> Milestone-based execution. Each milestone has clear exit criteria.

## M0 — Repository Canonicalization (Issue #2)

**Exit**: docs checker PASS, no contradictory Easel version, no broken links, test_basic PASS.

## M1 — Pipeline Stabilization (Issue #3)

**Exit**: 3 consecutive Easel builds PASS, QC PASS, runtime verification PASS, human review receipt.

## M2.0 — MiniMax Capability Spike (Issue #4)

**Exit**: Capability matrix complete, each modality marked VERIFIED/DOCUMENTED_BUT_NOT_TESTED/NOT_SUPPORTED/MANUAL_ONLY/UNKNOWN.

## M2-M4 — MiniMax Provider Integration (Issue #5)

**M2 (Voice)**: real subscription smoke PASS, receipt PASS, voice human review PASS.
**M3 (Image)**: real image generation, asset receipt, storyboard integration.
**M4 (Video)**: real Hailuo clip (or MANUAL_ONLY), daily quota handling, no PAYG fallback.

## M5 — Cross-repo Source Adapter (Issue #6)

**Exit**: 3 different repos, same ContentRun workflow, no repo-specific code.

## M6 — Full Production E2E (Issue #6)

**Exit**: 3 consecutive publishable videos from 3 different sources, Founder Review.

## Strict Order

M0 → M1 → M2.0 → M2-M4 → M5 → M6. No skipping.
