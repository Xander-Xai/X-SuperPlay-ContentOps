# Media Provider Contract

> Defines the interface for all media generation providers (MiniMax, future providers).

## Interface

Generic on purpose: no vendor vocabulary, no vendor types. Only what is
implemented appears; an unimplemented modality raises `CapabilityNotSupported`
rather than falling back silently.

```python
class MediaProvider:
    def capabilities(self) -> dict:          # what this provider can do
    def health(self) -> dict:                 # reachable? credential CLASS only
    def quota(self) -> QuotaSnapshot:         # remaining included-plan usage

    def synthesize_speech(self, SpeechRequest) -> SpeechAsset: ...

    def receipt(self, asset) -> SpeechReceipt: ...   # full provenance

    def generate_image(self, req) -> Asset:
        raise CapabilityNotSupported(...)     # Issue #20
    def generate_video(self, req) -> Asset:
        raise CapabilityNotSupported(...)     # Issue #22
```

Implementation: `src/contentops/media/contract.py`.
Tests: `tests/test_minimax_speech.py`.

## Provider Implementations

| Provider | Role | Status |
|---|---|---|
| `MiniMaxMPlanProvider` | Subscription speech via the official CLI | IMPLEMENTED (Issue #19), `PENDING_FOUNDER_REVIEW` |
| `LocalFallbackProvider` | edge-tts / ffmpeg fallback | EXISTS (in run_v1.py); explicit only, never silent |
| `ManualImportProvider` | Human-generated assets imported into pipeline | PLANNED |

### MiniMax M Plan speech: transport decision

Transport is the **official MiniMax CLI** (`mmx`, `mmx-cli` v1.0.27), not the
pinned Easel MiniMax path.

Easel was tested first, with a real Subscription Key and no invented values, and
is incompatible: `EASEL_MPLAN_AUTH_INCOMPATIBLE`. Its MiniMax path hard-requires
`MINIMAX_GROUP_ID`, which the current M Plan credential model does not have; it is
also clone-only, so system-voice TTS is unreachable through it; and it defaults to
the legacy host and the `speech-01` model. Full evidence in
[ADR-007](adr/ADR-007-minimax-speech-transport.md).

Easel is not patched, not forked and not modified.

### Billing gate contract

`BillingGuard` is the single implementation of the subscription-only pre-flight, and
it is **modality-aware**. Verified M Plan behaviour is not uniform:

| Modality | 5-hour window | Weekly window |
|---|---|---|
| speech | required | required |
| image | required | required |
| video | not applicable | required |

So every provider call must pass its modality:

```python
self._guard.require_safe(modality="speech")   # M2
self._guard.require_safe(modality="image")    # M3, Issue #20
self._guard.require_safe(modality="video")    # M4, Issue #22
```

An **unknown modality is blocked**, never defaulted. Both defaults are wrong for
somebody: applying the speech rule to video wastes quota, and applying the video
rule to speech under-protects it.

Two further rules:

- Every generation is preceded by a guard call. A **cache hit is not a
  generation**, so the cache is resolved *before* the guard: reuse must need no
  quota, no network and no balance read.
- `cash_balance`, `credit_balance`, `voucher_balance` and `owed_amount` must each
  be present, numeric and exactly zero. A missing field is a schema change and
  blocks; an unreadable balance is never treated as zero.

### Capability status

| Modality | Status | Owner |
|---|---|---|
| Speech (`speech-2.8-hd`, system voices) | `VERIFIED` | #19 |
| Pronunciation lexicon (`pronunciation_dict`, plain-text expansion) | `VERIFIED` | #19 |
| Loudness normalisation | `VERIFIED` | #19 |
| Voice cloning | `DOCUMENTED_BUT_NOT_TESTED` | #23 |
| Image | not implemented here | #20 |
| Video | not implemented here | #22 |

## Capability Matrix

```yaml
provider: minimax_m_plan
plan: explore
billing_mode: subscription
payg_allowed: false
credit_pack_allowed: false
capabilities:
  text: VERIFIED            # M2.0, Issue #4
  image: VERIFIED           # M2.0, Issue #4
  speech: VERIFIED          # M2.0 verified, M2 integrated
  voice_clone: DOCUMENTED_BUT_NOT_TESTED   # Issue #23, needs rights-cleared sample
  video_t2va: VERIFIED      # M2.0, Issue #4
  video_reference_modes: DOCUMENTED_BUT_NOT_TESTED
quotas:
  windows: [5h, weekly]
  buckets_exposed: [general]
  modality_breakdown_exposed: false
video_test_duration:
  MiniMax-H3: 4-15 integer
  MiniMax-H3-Max: 5-15 integer
  effective_test_duration: 4   # provider minimum; see QUALITY-STANDARD
```

## Receipt Schema

```json
{
  "provider": "minimax",
  "entitlement": "token_plan",
  "billing_mode": "subscription",
  "plan": "...",
  "model": "...",
  "request_id": "...",
  "started_at": "...",
  "finished_at": "...",
  "quota_before": {},
  "quota_after": {},
  "output": "path/to/asset",
  "sha256": "...",
  "status": "OK",
  "prompt": "...",
  "input_asset_hash": "...",
  "retries": 0,
  "generation_fingerprint": "hash(prompt + model + input_hash + params)"
}
```

## Rules

- `billing_mode: subscription`, `allow_payg: false`
- Idempotent: same generation fingerprint → reuse, don't re-charge
- Fallback recorded with `quality_impact` and `requires_human_review: true`
- Quota exhaustion → route to real assets, NOT PAYG
