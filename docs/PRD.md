# PRD — X-SuperPlay ContentOps Runtime

[English](PRD.md) | [简体中文](PRD.zh-CN.md)

## 1. Background

X-SuperPlay operates self-media accounts (douyin/xhs/bilibili) producing evidence-first technical video content from real business work. Previous 5 separate platform repos failed to produce stable output. ContentOps consolidates production into one runtime.

## 2. Problem

- No stable video production pipeline → zero published videos
- Voice quality (edge-tts) sounds mechanical → content rejected
- No cross-repo source ingestion → each repo needs custom work
- No MiniMax subscription integration → purchased plan unused
- Documentation contradicts code → decisions on stale facts

## 3. User

Founder (Xander-Xai) — needs high-quality video from real work with minimum manual effort, traceable evidence, and honest quality gates.

## 4. Jobs-to-be-Done

- Convert any business repo's work into a publishable video
- Use MiniMax subscription for voice/image/video generation (when verified)
- Maintain evidence-first integrity (no fabricated claims)
- Produce complete receipts for audit
- Gate on human approval before any publish

## 5. Product Goal

A unified ContentOps Runtime that any Xander-Xai business repo can call to produce high-quality, traceable, publishable video.

## 6. Non-goals (current phase)

- Auto-publishing to any platform
- Comment scraping / ROI agent
- Digital human / AI short drama
- Metrics scraping / winner learning
- n8n / OpenClaw total orchestration
- Database / complex FastAPI

## 7. Current Baseline

- Easel v0.2.1 pinned, content-verified (982/982 blobs)
- Pipeline: Source → Script → Storyboard → Voice → Compose → QC → MP4
- 1 golden sample (easel-review) with real receipts
- Voice: edge-tts (fallback quality, not production-grade)
- 9 tests passing, 0 published videos

## 8. Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | Ingest SourceArtifact from any Xander-Xai business repo |
| FR-2 | Generate master script from evidence (LLM drafts, evidence verifies) |
| FR-3 | Produce structured storyboard with per-shot provenance |
| FR-4 | Generate voice via MiniMax subscription (fallback: edge-tts) |
| FR-5 | Generate images via MiniMax subscription (when needed) |
| FR-6 | Generate video clips via MiniMax subscription (quota-limited) |
| FR-7 | Compose final video via Easel assemble.py (unchanged upstream) |
| FR-8 | Run automated QC (technical + content + factual) |
| FR-9 | Gate on human review (100-point scorecard) |
| FR-10 | Emit complete receipts for every run |

## 9. Non-functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | Windows first-class citizen (paths, PowerShell, UTF-8, FFmpeg) |
| NFR-2 | No secrets in git (test_no_secret_leak) |
| NFR-3 | No PAYG fallback (subscription only) |
| NFR-4 | Idempotent generation (content hash fingerprint) |
| NFR-5 | Quota-aware scheduling (no unlimited retries) |
| NFR-6 | Honest receipts (fallback never reports production_ready) |

## 10. SourceArtifact Contract

See [SOURCE-ARTIFACT-CONTRACT.md](SOURCE-ARTIFACT-CONTRACT.md).

## 11. ContentRun Contract

State machine: SOURCE_CAPTURED → SOURCE_NORMALIZED → EVIDENCE_EXTRACTED → CLAIMS_BOUND → CONTENT_BRIEF_CREATED → MASTER_SCRIPT_CREATED → STORYBOARD_CREATED → ASSET_PLAN_CREATED → MEDIA_ASSETS_READY → VOICE_READY → VIDEO_COMPOSED → TECHNICAL_QC → CONTENT_QC → FACT_QC → HUMAN_REVIEW → PRODUCTION_READY.

## 12. MediaProvider Contract

See [MEDIA-PROVIDER-CONTRACT.md](MEDIA-PROVIDER-CONTRACT.md).

## 13. MiniMax Subscription Requirements

- `billing_mode: subscription`
- `allow_payg: false`
- Capability spike required before implementation (Issue #4)
- Receipts must record quota_before/after
- `MANUAL_ONLY` is a valid status for unsupported modalities

## 14. Easel Integration

- Pinned v0.2.1, release archive, content-verified
- Extension priority: ADAPTER > EXTENSION > CUSTOM SKILL > PATCH > FORK
- No upstream source modification
- Upgrade requires Founder approval + regression suite

## 15. Quality Standard

See [QUALITY-STANDARD.md](QUALITY-STANDARD.md).

## 16. Human Gates

- Automated QC PASS ≠ Production Ready
- Founder Review with 100-point scorecard
- Hard fails block production_ready
- See [ADR-005](adr/ADR-005-human-approval.md)

## 17. Security

- No API keys, cookies, tokens in git
- `.env.example` has names only
- Receipts must redact secrets
- `docs/ai-provider-selection.md` stays gitignored (business strategy)

## 18. Quota / Resource Model

- Video: max N clips per run, max M per day, max R retries per shot
- Image: baseline 50-70% real, 0-20% AI generated
- Voice: subscription quota tracked in receipt

## 19. Error / Fallback Model

- Provider failure → LocalFallbackProvider
- Fallback recorded in receipt with quality_impact
- Fallback never reports `production_ready: true`
- Quota exhaustion → route to real assets, NOT PAYG

## 20. Acceptance Criteria

See [DEVELOPMENT-PLAN.md](DEVELOPMENT-PLAN.md) milestone exit criteria.

## 21. Rollout

M0 → M1 → M2.0 → M2-M4 → M5 → M6

## 22. Kill / Rollback Conditions

- MiniMax subscription doesn't support programmatic API → MANUAL_ONLY
- 3 consecutive E2E failures → HOLD, root-cause
- Founder Review rejects all outputs → STOP, reassess
