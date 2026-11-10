# M5 characterization baseline — 2026-11-10

- commit: `112800c9fb0a`
- suites: 10, tests: 165, passed: 164, failed: 1
- unparsed suites: 0

| suite | total | passed | failed | exit |
|---|---|---|---|---|
| tests/test_brief_to_m5.py | 13 | 13 | 0 | 0 |
| tests/test_m5_asr_gate.py | 6 | 6 | 0 | 0 |
| tests/test_m5_bundle_handoff.py | 6 | 6 | 0 | 0 |
| tests/test_m5_evidence.py | 19 | 19 | 0 | 0 |
| tests/test_m5_media_traceability.py | 10 | 10 | 0 | 0 |
| tests/test_m5_media_use_workflow.py | 30 | 29 | 1 | 1 |
| tests/test_m5_motion_integration.py | 56 | 56 | 0 | 0 |
| tests/test_motion_build_reliability.py | 3 | 3 | 0 | 0 |
| tests/test_motion_handoff.py | 11 | 11 | 0 | 0 |
| tests/test_motion_sample.py | 11 | 11 | 0 | 0 |

Slice-1 receipt for #140: structural refactor PRs must keep these
suites at the recorded pass counts (or fix a named, reviewed defect).
