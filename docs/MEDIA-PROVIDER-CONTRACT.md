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

### Retry contract

Retry evidence is **durable**, because the real workflow is two processes:

```
python scripts/synthesize_narration.py ...                        # attempt 1
python scripts/synthesize_narration.py --retry-from <record> ...   # attempt 2
```

An in-memory fingerprint cannot survive that boundary, so an identical attempt 2
used to pass straight through. Instead:

- every attempt writes a sanitised record under `<work-dir>/attempts/`:
  `STARTED` before the provider call, then `SUCCEEDED` or `FAILED`
- attempt 2 requires **all three**: `--retry-reason`, `--retry-from` pointing at
  a record whose provider, modality, `attempt_number` and `FAILED` status all
  validate, and a **changed generation fingerprint**
- the refusal happens **before** the billing gate, so an invalid retry costs no
  quota read and no provider call
- maximum two attempts

A record never contains a credential, a credential fragment, an `Authorization`
header, an account id or a raw provider response.

### Receipt immutability

The generation receipt is written once and never rewritten:

- a cache hit **loads and validates** it, checks the asset hash, and returns the
  **original** generation receipt
- reuse never overwrites `quota_before`, `quota_after`, `attempt` or
  `provider_call`
- reuse is audited separately in an append-only `reuse-events.jsonl`
- a sidecar missing any required provenance field — or carrying a blank voice,
  blank text hash or non-integer attempt — is a **cache miss**. Blanks are never
  filled in to make a cache hit succeed

### Authorisation is pre-generation evidence

`BillingGuard.authorize(modality)` returns the complete verdict and raises when
unsafe. A receipt records **that** verdict, not a later re-evaluation:

| Field | Meaning |
|---|---|
| `billing_guard_verdict` | the decision that authorised the request |
| `quota_before` | observed at authorisation |
| `post_generation_billing_state` | observed afterwards, recorded separately |

A generation may legitimately consume the last of a window, so a post-generation
re-evaluation can report exhaustion. Recording that as the authorisation would
rewrite history and claim a correctly authorised generation was unauthorised.
For the same reason the generation path makes **one** balance read, not a second
authorisation.

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

## Credential binding (B-FINAL-2)

The rule:

```
THE CREDENTIAL AUTHORISED BY BILLINGGUARD
MUST BE
THE CREDENTIAL THE PROVIDER TRANSPORT ACTUALLY USES
```

ContentOps and the official `mmx` CLI each have their own credential discovery.
If the gate resolves `MINIMAX_SUBSCRIPTION_KEY` while `mmx` silently falls back to
`~/.mmx/config.json`, the gate authorises key A while key B does the work. Every
balance check would pass and nothing would reveal it. The reasoning
"the gate said SAFE, so whatever mmx uses is fine" is exactly what is forbidden.

Required behaviour, enforced in `contentops.media.credentials`:

| Requirement | Where |
|---|---|
| Resolve exactly once per invocation | `resolve_credential()` |
| Same value feeds gate and transport | `build_guard(resolved)` + `transport_credential=resolved` |
| Child-only environment, never argv | `child_env_for()` sets `MINIMAX_API_KEY` |
| Ambient/stored credential cannot win | `MINIMAX_SUBSCRIPTION_KEY` is stripped from the child env |
| PAYG / UNKNOWN / ABSENT stop before launch | `CredentialBindingError`, or `BillingBlocked` from the gate |
| Never fall back when unbound | provider raises instead of generating |
| Value never logged or persisted | `key` excluded from `repr`, `str` and `safe_metadata()` |

Resolution order is fixed and recorded in the receipt metadata:
`MINIMAX_SUBSCRIPTION_KEY_ENV` → `MINIMAX_API_KEY_ENV` → `MMX_CONFIG` → `NONE`.
A credential sourced from `MMX_CONFIG` is the last resort and is labelled as such,
because a stored key is the one most likely to drift from what the operator intended.

Only `credential_class` and `credential_source` are ever written to a receipt. The
value is not.

## Cache hit restores provider state (B-FINAL-2)

A provider that starts fresh and finds a valid cache entry must still answer
`receipt()` and `receipt(asset)`. Reconstructing the original receipt without
registering it left a new provider reporting "no receipt available" for an asset
that demonstrably had one.

`_reuse()` therefore registers the reconstructed receipt in memory via
`_remember_receipt()`, which de-duplicates by fingerprint and normalised SHA-256.
`_receipt()` is deliberately not used there: it is the generation path and would
rewrite the immutable sidecar. A cache hit still costs zero billing reads and zero
network calls.

