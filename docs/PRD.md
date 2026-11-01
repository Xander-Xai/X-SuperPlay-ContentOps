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

Verified 2026-11-01 on `main` (PR #89):

- Easel v0.2.1 pinned, content-verified (982/982 blobs). Upstream v0.3.0 is
  available but not adopted (skill paths moved; see UPSTREAM-EASEL).
- Two implemented paths: `run_v1.py` (storyboard-driven, edge-tts) and
  `m5_production.py` (evidence-first, local narration). Both compose through the
  pinned Easel adapter.
- Media layer implemented: MiniMax speech/image/H3, media convergence, media-use
  adapter, billing/quota gates, rights gate.
- 31 test suites (704 top-level `test_*` functions plus list-driven and
  unittest-style suites).
- Account-aware content router, account DNA, workflow gates, XHS, X and GZH are
  **unmerged** (PR #49 and other branches).
- Voice: edge-tts (V1) and Windows SAPI (M5); neither is production-grade.
- 0 published videos; every result is `PENDING_FOUNDER_REVIEW`.

## 8. Functional Requirements

| ID | Requirement | Status on this branch |
|---|---|---|
| FR-1 | Ingest SourceArtifact from any Xander-Xai business repo | **partial** — M5 ingests repo docs/locks; cross-repo adapter unmerged |
| FR-2 | Generate master script from evidence (LLM drafts, evidence verifies) | **implemented** for the M5 fixture path; authoring remains editorial |
| FR-3 | Produce structured storyboard with per-shot provenance | **implemented** |
| FR-4 | Generate voice via MiniMax subscription (fallback: edge-tts) | **implemented**, `PENDING_FOUNDER_REVIEW` |
| FR-5 | Generate images via MiniMax subscription | **implemented**, `PENDING_FOUNDER_REVIEW` |
| FR-6 | Generate video clips via MiniMax subscription (quota-limited) | **implemented** (H3 subsets verified), `PENDING_FOUNDER_REVIEW` |
| FR-7 | Compose final video via Easel assemble.py (unchanged upstream) | **implemented** through the adapter |
| FR-8 | Run automated QC (technical + content + factual) | **implemented** technical/evidence; content/fact remain human |
| FR-9 | Gate on human review (100-point scorecard) | **implemented as a gate; never satisfied yet** |
| FR-10 | Emit complete receipts for every run | **implemented** |

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
