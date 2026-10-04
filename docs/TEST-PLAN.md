# Test Plan

[English](TEST-PLAN.md) | [简体中文](TEST-PLAN.zh-CN.md)

## Current Suite

| Suite | File | Tests | Platform |
|---|---|---|---|
| Basic | `scripts/test_basic.py` | 9 | Windows + Ubuntu |
| Windows path regression | `tests/test_windows_paths.py` | — | Windows + Ubuntu |
| Windows subprocess regression | `tests/test_windows_subprocess.py` | 47 | Windows + Ubuntu |
| M2 speech regression | `tests/test_minimax_speech.py` | 85 | Windows + Ubuntu |
| M3 image regression | `tests/test_minimax_image.py` | 63 | Windows + Ubuntu |

`scripts/test_basic.py` — 9 tests, all PASS:
- doctor.py execution + JSON output
- new_project.py idempotency + structure creation
- qc_video.py FAIL on missing final.mp4
- blob SHA-1 verification (empty blob + hello\n)
- generated-path exclusion symmetry
- resolver rejects foreign remote
- resolver accepts archive via recorded provenance
- resolver blocks archive without provenance

### The media suites never contact a provider

`test_minimax_speech.py` and `test_minimax_image.py` drive
`tests/fixtures/fake_mmx_cli.py` and inject a fake billing transport, so CI needs
no MiniMax account and spends no quota. Tests that need `ffmpeg` or `Pillow`
report `[skip]` rather than failing when the tool is absent, which is why the
counts above are upper bounds.

## Planned

### Unit Tests (M1)
- SourceArtifact parsing
- Claim binding
- Storyboard schema validation
- Asset registry
- Provider routing
- Quota logic
- Receipt serialization
- Path normalization
- Content hashing
- Fallback rules
- Config parsing

### Contract Tests (M2-M4)
- MiniMax provider: valid/invalid key, quota exhausted, 429, timeout, malformed response, job failed, download failed, duplicate request, retry, process restart, partial asset

### Integration Tests (M5)
- RepoSourceAdapter with 3 different source types
- ContentRun state machine transitions

### E2E Tests (M6)
- 3 different sources → 3 final.mp4s → QC PASS → human review

### Windows-Specific Tests
- Chinese path/text
- PowerShell subprocess
- UTF-8 stdout
- FFmpeg subtitle paths
- Spaces in path
