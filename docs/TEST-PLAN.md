# Test Plan

[English](TEST-PLAN.md) | [简体中文](TEST-PLAN.zh-CN.md)

> Authoritative local verification strategy, suite inventory and CI wiring.
>
> Last verified: 2026-11-12 on `main` at `c1da6dd` (98 suites, 98 named CI steps).

## Risk-based local verification

Choose checks from the behavior and risk affected, not the number of files changed. Prefer static inspection first and the smallest directly relevant existing suite. A test not run is **not** a pass. Do not add tests merely because a task has no directly applicable test; add the smallest regression test only when coverage is demonstrably insufficient and behavior warrants it.

| Level | Scope | Local verification |
|---|---|---|
| **L0 — docs/non-behavioral** | Copy, Markdown, comments, non-behavioral explanations | No business unit, integration or E2E tests. Run only directly relevant docs/link/consistency checks; run `check_i18n.py` when bilingual mirrors change. No `doctor.py`, `qc_video.py` or full `dev_check.py`. |
| **L1 — local low-risk code** | Local bug fix/config logic without public-contract change | Static analysis first; at most one directly relevant existing suite when applicable. If none applies, report the static verification performed and the uncovered runtime behavior. No automatic full suite. |
| **L2 — ordinary feature** | New ordinary interface/component, business logic, non-critical media behavior, Bundle/Router/workflow-local changes | Run relevant existing suites, ordinarily 1–3 targeted test commands. Add only the necessary contract check for a cross-module contract. Do not expand to unrelated areas. |
| **L3 — high-risk** | Human approval/execution authorization; provider billing, quota or live calls; media rights/evidence; credentials/access; CI/security gates/public contracts; pinned Easel runtime/upgrades; data corruption, duplicate spend or publication | Run the unit, contract, integration and regression checks needed to cover the affected risk. Preserve fail-closed gates and human approval. Real paid calls, external writes, renders or human review require their separate authorization. The ordinary test budget does not waive a required safety check. |

### Local commands are conditional

- `python scripts/doctor.py`: environment dependencies, runtime, installation or deployment state only.
- `python scripts/qc_video.py <project>`: actual video artifact or video-QC behavior only; do not run as a generic code check.
- `python scripts/test_basic.py`: relevant script entry point or basic behavior only.
- `python scripts/dev_check.py`: complete local gate when preparing a PR; run once for that purpose, not after every small edit.
- `python scripts/dev_check.py --quick` skips **only** repository policy. It still runs subprocess policy, skill references, docs, i18n, `test_basic.py` and `git diff --check`; it is not a targeted or lightweight relevant-tests mode.
- Run `python scripts/check_repo_policy.py` when repository placement/security policy or CI suite wiring is affected.

## Budget, retries and stop conditions

Plan ordinary development verification to consume roughly 20–30% of task effort; this is a planning guideline, not a safety cap. L0 runs no business tests; L1 ordinarily runs at most one targeted test command; L2 ordinarily runs at most three relevant test commands. L3 is determined by affected risk.

Do not repeat a passed command unless subsequent changes could affect its result. On failure, diagnose first and rerun only checks affected by the repair; no blind retries. Do not expand the test matrix without evidence of a gap. If additional verification exceeds the ordinary budget, state the concrete risk it addresses.

Stop when the request is implemented, required directly relevant checks pass, no blocking defect is known, and no critical risk remains. Do not follow a pass with autonomous test expansion, unrelated refactoring or another broad review. Report unrun tests as unrun, never as passing.

## Local work vs PR/CI

Daily local work uses the L0–L3 selection above. Preparing a PR retains the complete existing local gate (`python scripts/dev_check.py`) and the relevant business regression checks. GitHub Actions remains the authoritative full suite: Ubuntu and Windows test jobs plus repo-policy checks, including receipt-secret checks. Do not disable, remove, weaken or bypass CI, required checks, branch protection or safety gates. A successful local targeted run does not imply the full CI matrix passed.

## How suites run and are wired

There is **no pytest**. Each suite is a standalone script, for example:

```bash
python tests/test_m5_evidence.py
python tests/test_media_convergence.py
```

The authoritative current suite list is `git ls-files 'tests/test_*.py'`; a suite counts as CI-covered only when `.github/workflows/ci.yml` names it. CI enumerates suites explicitly. `check_repo_policy.check_test_suites_registered_in_ci` catches an unwired suite.

## Current inventory

Function counts inside a suite are floors, not totals, because list-driven and unittest-style suites define checks differently.

| Suite | File | Count | CI |
|---|---|---:|---|
| Script smoke | `scripts/test_basic.py` | 10 | yes |
| Windows subprocess | `tests/test_windows_subprocess.py` | 47 | yes |
| Windows paths | `tests/test_windows_paths.py` | 6 | yes |
| M2 speech | `tests/test_minimax_speech.py` | 86 | yes |
| M2.1 voice clone | `tests/test_minimax_voice_clone.py` | 41 | yes |
| M2.2 clone route | `tests/test_minimax_clone_route.py` | 23 | yes |
| M2.2 voucher activation | `tests/test_voucher_activation.py` | 9 | yes |
| Cash activation recovery | `tests/test_cash_activation_recovery.py` | 20 | yes |
| Native T2A adapter | `tests/test_minimax_native_tts.py` | 13 | yes |
| Host-binding audit | `tests/test_host_binding_audit.py` | 9 | yes |
| M3 image | `tests/test_minimax_image.py` | 85 | yes |
| M4 H3 video | `tests/test_minimax_h3.py` | 108 | yes |
| M4.5 media convergence | `tests/test_media_convergence.py` | 97 | yes |
| media-use adapter | `tests/test_media_use_adapter.py` | 56 | yes |
| M4.6 enhanced golden | `tests/test_enhanced_golden.py` | 18 | yes |
| Golden A/B variants | `tests/test_golden_variant_ab.py` | 13 | yes |
| Golden voice assets | `tests/test_golden_voice_assets.py` | 10 | yes |
| Golden clean-checkout rebuild | `tests/test_golden_voice_rebuildability.py` | 6 | yes |
| Locked input reproducibility | `tests/test_locked_input_reproducibility.py` | 10 | yes |
| Source-evidence gitignore | `tests/test_gitignore_evidence_policy.py` | 14 | yes |
| Local-approval gitignore | `tests/test_local_approval_gitignore.py` | 5 | yes |
| M5 evidence | `tests/test_m5_evidence.py` | 19 | yes |
| GitHub repository source adapter | `tests/test_repo_source_adapter.py` | 3 | yes |
| Stable production gates | `tests/test_production_gates.py` | 30 | yes |
| Content router | `tests/test_content_router.py` | 63 | yes |
| Hotspot sources | `tests/test_hotspot_sources.py` | 51 | yes |
| Account DNA | `tests/test_account_dna.py` | 37 | yes |
| Account discovery | `tests/test_account_discovery.py` | 23 | yes |
| Script draft | `tests/test_script_draft.py` | 20 | yes |
| Source quality | `tests/test_source_quality.py` | 21 | yes |
| Account route | `tests/test_account_route.py` | 12 | yes |
| Brief → M5 bridge | `tests/test_brief_to_m5.py` | 13 | yes |
| Real-source duration gate | `tests/test_real_source_duration.py` | 17 | yes |
| Card renderer | `tests/test_render_cards.py` | 18 | yes |
| GZH article renderer | `tests/test_render_articles.py` | 35 | yes |
| GZH runtime adapter | `tests/test_gzh_runtime.py` | 13 | yes |
| ASR transport (SiliconFlow) | `tests/test_asr_siliconflow.py` | 14 | yes |
| M5 ASR gate | `tests/test_m5_asr_gate.py` | 6 | yes |
| WeChat draft | `tests/test_wechat_draft.py` | 15 | yes |
| WeChat metrics | `tests/test_wechat_metrics.py` | 11 | yes |
| SAU login | `tests/test_sau_login.py` | 9 | yes |
| Delivery gate | `tests/test_delivery_gate.py` | 7 | yes |
| Video platforms | `tests/test_video_platforms.py` | 30 | yes |
| Platform status sync | `tests/test_platform_status_sync.py` | 9 | yes |
| Workflow contract | `tests/test_workflow_contract.py` | 8 | yes |
| Workflow gate | `tests/test_workflow_gate.py` | 11 | yes |
| Publish backfill | `tests/test_publish_backfill.py` | 13 | yes |
| Governance checks | `tests/test_governance_checks.py` | 16 | yes |
| Governance ledger | `tests/test_governance_ledger.py` | list-driven | yes |
| M5 motion integration | `tests/test_m5_motion_integration.py` | 65 | yes |
| M5 media-use workflow | `tests/test_m5_media_use_workflow.py` | list-driven | yes |
| M5 media traceability | `tests/test_m5_media_traceability.py` | list-driven | yes |
| Platform registry | `tests/test_platform_registry.py` | 22 | yes |
| Content Bundle contract | `tests/test_content_bundle_contract.py` | 13 | yes |
| Easel host guard | `tests/test_easel_host_guard.py` | 13 | yes |
| Bundle two-format handoff | `tests/test_bundle_two_formats.py` | 14 | yes |
| Graphic workflow | `tests/test_graphic_workflow.py` | 14 | yes |
| M5 Bundle handoff | `tests/test_m5_bundle_handoff.py` | 5 | yes |
| Coding-agent driver | `tests/test_agent_driver.py` | 29 | yes |
| Skill doctor | `tests/test_skill_doctor.py` | list-driven | yes |
| Skill reference integrity | `tests/test_skill_references.py` | 6 | yes |
| Skill router capabilities | `tests/test_skill_router_capabilities.py` | list-driven | yes |
| Skill execution authorization | `tests/test_skill_execution_authorization.py` | list-driven | yes |
| Managed media-use status | `tests/test_skill_execute_status.py` | list-driven | yes |
| Trusted grant source | `tests/test_trusted_grant_source.py` | list-driven | yes |
| Execution gate | `tests/test_execution_gate.py` | list-driven | yes |

The CI workflow also runs policy, docs, i18n, whitespace, subprocess and receipt-secret checks. Media provider suites use fake transports; they do not call a provider. Suites that require `ffmpeg`, `Pillow`, media-use runtime or ignored artifacts may skip locally; inspect availability/skip output. CI installs `Pillow` and ffmpeg and reports availability.

## Adding a suite

1. Add `tests/test_<area>.py` only when a demonstrated coverage gap justifies it; use the repository's standalone-script pattern.
2. Add a named step to `.github/workflows/ci.yml`.
3. Update this inventory and `docs/CURRENT-STATE.md` when its verified facts change.
4. Run the new suite and full PR gate when preparing the PR, not after every intermediate edit.

## Planned

- Contract tests for additional cross-repo `SourceArtifact` adapters; the router
  layer and one GitHub adapter are already on `main`.
- A regression suite for the publication path once a real platform URL exists —
  there is nothing to assert against before that.

The inventory above is a floor, not a complete enumeration: 98 suites were
tracked on 2026-11-12, and `git ls-files 'tests/test_*.py'` is the authority.
