# Test Plan

[English](TEST-PLAN.md) | [简体中文](TEST-PLAN.zh-CN.md)

## Current Suite

`scripts/test_basic.py` — 9 tests, all PASS:
- doctor.py execution + JSON output
- new_project.py idempotency + structure creation
- qc_video.py FAIL on missing final.mp4
- blob SHA-1 verification (empty blob + hello\n)
- generated-path exclusion symmetry
- resolver rejects foreign remote
- resolver accepts archive via recorded provenance
- resolver blocks archive without provenance

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
