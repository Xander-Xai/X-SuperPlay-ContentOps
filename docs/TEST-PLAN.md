# Test Plan

[English](TEST-PLAN.md) | [简体中文](TEST-PLAN.zh-CN.md)

> Test strategy, the real suite inventory, and how CI is wired.
>
> Last verified: 2026-11-01 on `main` (PR #89).

## How tests run

There is **no pytest**. Each suite is a standalone script that builds a `TESTS`
list and runs it from `main()`:

```bash
python tests/test_m5_evidence.py
python tests/test_media_convergence.py
```

Run the local gate before a commit:

```bash
python scripts/dev_check.py
```

It runs, in order: repo policy → subprocess policy → skill references → docs →
i18n → `scripts/test_basic.py` → `git diff --check`.

CI enumerates every suite as a named step. **A new `tests/test_*.py` that is not
added to `.github/workflows/ci.yml` never runs**, and a green CI run is then not
evidence. The M4/M4.5 suites were merged unwired once for exactly this reason.

## Current inventory

The inventory is **not asserted in this document**. The authoritative list is
`git ls-files 'tests/test_*.py'`, and a suite counts only when
`.github/workflows/ci.yml` names it. Function counts inside a suite are a floor
rather than a total, because list-driven and unittest-style suites define their
checks differently.

| Suite | File | Count | CI |
|---|---|---|---|
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
| M5 evidence | `tests/test_m5_evidence.py` | 18 | yes |
| M5 media-use workflow | `tests/test_m5_media_use_workflow.py` | list-driven | yes |
| M5 media traceability | `tests/test_m5_media_traceability.py` | list-driven | yes |
| Skill doctor | `tests/test_skill_doctor.py` | list-driven | yes |
| Skill reference integrity | `tests/test_skill_references.py` | 6 | yes |
| Skill router capabilities | `tests/test_skill_router_capabilities.py` | list-driven | yes |
| Skill execution authorization | `tests/test_skill_execution_authorization.py` | list-driven | yes |
| Managed media-use status | `tests/test_skill_execute_status.py` | list-driven | yes |
| Trusted grant source | `tests/test_trusted_grant_source.py` | list-driven | yes |
| Execution gate | `tests/test_execution_gate.py` | list-driven | yes |

Also in CI: `scripts/check_subprocess_policy.py`, `scripts/check_docs.py`,
`scripts/check_i18n.py`, `scripts/check_repo_policy.py`,
`scripts/check_receipt_secrets.py`, `scripts/check_skill_references.py`.

### The media suites never contact a provider

Provider suites drive `tests/fixtures/fake_mmx_cli.py` (and `fake_h3_api.py`) and
inject fake billing transports. CI needs no MiniMax account and spends no quota.
Tests that need `ffmpeg` or `Pillow` report `[skip]` when the tool is absent; CI
installs both and prints an availability line so a skipped suite cannot look
green by accident.

## CI checks

| Job | Contents |
|---|---|
| `Tests (ubuntu-latest)` | every suite above + policy/docs/i18n/whitespace |
| `Tests (windows-latest)` | same matrix |
| `Repo policy checks` | file placement, receipt secrets, subprocess policy, docs, i18n |

## Adding a suite

1. Write `tests/test_<area>.py` with a `TESTS` list and a `main()`.
2. Add a named step to `.github/workflows/ci.yml`.
3. Add the row to this table and to `docs/CURRENT-STATE.md`.
4. Run `python scripts/dev_check.py` and the new suite locally.

Step 2 is enforced: `check_repo_policy.check_test_suites_registered_in_ci` fails
when a `tests/test_*.py` file is not named in the workflow.

## Planned

- Contract tests for cross-repo `SourceArtifact` adapters (needs the unmerged
  content-router layer).
- E2E tests for 3 different sources → 3 final MP4s → QC → human review (M6).
