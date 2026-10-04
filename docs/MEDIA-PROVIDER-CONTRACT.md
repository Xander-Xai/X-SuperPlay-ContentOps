# Media Provider Contract

> Defines the interface for all media generation providers (MiniMax, future providers).

## Interface

## The provider family

Speech and image are **separate provider ABCs over one set of shared
infrastructure**, not one monolithic class with optional-everywhere signatures.
Forcing three modalities through one signature produces optional arguments rather
than types, and blurs the receipts.

| ABC | Modality | Declared in |
|---|---|---|
| `SpeechProvider` | narration | `contract.py` |
| `ImageProvider` | stills | `image_contract.py` |
| `VideoProvider` | generated shots | Issue #22, not yet declared |

Shared by all of them — one implementation each, never one per modality:

| Shared concern | Canonical owner |
|---|---|
| credential resolution and binding | `credentials.py` (`ResolvedCredential`, `CredentialBinding`) |
| billing gate | `billing_guard.py` (`BillingGuard`) |
| durable retry evidence | `attempts.py` (`GenerationAttemptRecord`) |
| transport helpers, sidecar conventions | `transport.py` |
| provider identity and billing constants | `mplan_identity.py` |
| fingerprint conventions | `fingerprint.py`, `image_fingerprint.py` |
| immutable receipts, reuse events | per-modality provider, shared conventions |

`MediaProvider` remains the common ancestor so existing speech code keeps
working. Its `generate_image` / `generate_video` hooks are **deprecated
cross-modality shortcuts** that raise `CapabilityNotSupported` and say why. A
future `MediaProviderRegistry` may aggregate the family; it is deliberately not
built yet, because with two members a registry is indirection without benefit.

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

    def generate_image(self, ImageRequest) -> ImageAsset: ...   # M3, Issue #20
    def generate_video(self, req) -> Asset:
        raise CapabilityNotSupported(...)     # Issue #22

class ImageProvider:
    def capabilities(self) -> dict
    def health(self) -> dict
    def generate_image(self, ImageRequest) -> ImageAsset
    def receipt(self, asset) -> ImageReceipt
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

---

# M3 — Image (Issue #20)

Canonical owner: `src/contentops/media/` (`image_contract.py`,
`image_container.py`, `image_fingerprint.py`, `image_qc.py`,
`minimax_image.py`, `asset_planner.py`, `text_contamination.py`).
Tests: `tests/test_minimax_image.py` (63 tests).

## The container is sniffed, never assumed

M2.0 measured the real provider returning **JPEG bytes from a `.png` request**.
A pipeline that selects a decoder by suffix would hand a JPEG to every tool that
trusted the name, and the failure would surface far from its cause.

So `detect_image_container(data)` is the only thing allowed to decide a format,
and it decides from magic bytes:

| Container | Signature | Canonical extension |
|---|---|---|
| PNG | `89 50 4E 47 0D 0A 1A 0A` | `.png` |
| JPEG | `FF D8 FF` | `.jpg` |
| WEBP | `RIFF....WEBP` (form type at offset 8) | `.webp` |

`RIFF` alone is not enough — AVI and WAV begin the same way, so the form type is
checked. Unknown, truncated or malformed bytes raise `ImageContainerError`: a
wrong container silently yields a broken asset, whereas an exception stops the run
while the cause is still visible.

## Canonical file policy

Provider bytes are **preserved**. A JPEG returned for a `.png` request is renamed
to `.jpg`; it is never transcoded, because re-encoding would alter the pixels and
destroy the output-hash relationship the receipt depends on.

The receipt records both truths, so a mismatch stays visible instead of being
normalised away:

```
requested_extension = ".png"      what was asked for
detected_container  = "JPEG"      what actually arrived
canonical_extension = ".jpg"      what the file is therefore named
output_sha256       = ...        hash of the preserved bytes
```

## Order of operations

```
validate dimensions   free; a typo must not cost a billing read
build fingerprint
validate retry evidence
resolve the cache     -> a hit needs neither billing nor provider
authorize(modality="image")
write STARTED record  -> survives a crash
mmx image generate
verify the output     -> exit 0 is not semantic success
sniff container, technical QC, write the receipt
```

Dimensions are validated locally against `[512, 2048]` and multiples of 8. The
official CLI validates them too, but only in second position.

## Billing

Identical to M2, with `modality="image"`: subscription credential class only,
`cash_balance`, `credit_balance`, `voucher_balance` and `owed_amount` all exactly
zero, and both the 5-hour and weekly plan windows above zero. Any missing or
unreadable state is `BLOCKED_BILLING_SOURCE_UNCERTAIN` and makes no provider call.

## Credential binding

One invariant, shared with speech, implemented once in
`contentops.media.credentials.CredentialBinding`:

```
THE CREDENTIAL AUTHORISED BY BILLINGGUARD
MUST BE
THE CREDENTIAL THE mmx CHILD ACTUALLY USES
```

`resolve_credential()` runs once; the same value feeds `BillingGuard` and the
child environment as `MINIMAX_API_KEY`. `--api-key` is never used, because argv
is visible to anything on the host. `MINIMAX_SUBSCRIPTION_KEY` is stripped from
the child environment so a stored `~/.mmx/config.json` cannot silently win. An
unbound provider raises rather than falling back.

## Cache validation

A cache hit requires **all** of: receipt exists, schema valid, fingerprint
matches, SHA-256 matches, sniffed container matches, decoded width and height
match, model matches, seed matches, `generated` is `True` and `evidence_capable`
is `False`. Any mismatch is a **cache miss**. Nothing is filled in with a
default — a missing field means the receipt cannot vouch for the asset.

The generation receipt is immutable. Reuse restores the original receipt,
including its `quota_before`, `quota_after` and attempt number, and appends a
reuse event instead of rewriting provenance.

## Image technical QC

Measured facts only: file exists, non-empty, known container, decodable, actual
width and height, aspect ratio **within tolerance**, not corrupt, not blank, not
near-uniform, and reasonable luminance variance.

A small file is not a QC failure — PNG compresses hard. Truncation is caught by
`verify_output()` (response too small) and by the decode step.

`approved` means *technically sound*. It never means beautiful, on-brand or
publishable; those are human judgements. Automated QC that reports "publishable"
teaches the pipeline to trust itself.

Aspect ratio is compared with tolerance (default 0.02), never exactly: 768x1360
is 0.5647 against 9:16 = 0.5625, which is close enough for a video frame.

## Text contamination

Critical text must not live inside generated imagery — a model asked for "a
benchmark chart" will invent one, and invented glyphs read as data. Critical text
is a deterministic overlay applied later.

`text_contamination_suspected` is an honest *suspicion* signal from edge-density
and band-concentration measurements, never a verdict: it cannot read the text,
and it fires on dense text-free detail. It is recorded and surfaced in review. OCR
is deliberately not introduced for this milestone.

## Evidence integrity hard gate

`AssetRegistry.register()` refuses, in code, to register a generated asset as:

```
EVIDENCE  CLAIM_SOURCE  BENCHMARK_PROOF  TEST_RESULT
ANALYTICS_PROOF  UI_SCREENSHOT  CUSTOMER_PROOF  SOURCE_CODE_PROOF
```

It also refuses a generated asset that declares itself `evidence_capable`, and a
generated asset with no `receipt_ref`. The failure is a domain error
(`GeneratedAssetEvidenceError`), not a warning, and it lives at the only place an
asset enters the system.

## AssetPlanner

```
real factual evidence
    > screenshot / screen recording
    > deterministic diagram
    > generated support visual
```

`MINIMAX_IMAGE` is for hooks, covers, concepts, metaphors, backgrounds,
transitions and decorative scenes. A beat that requires evidence never resolves to
a generated image; when only `MINIMAX_IMAGE` is available, the planner refuses
rather than degrading.

## Transport

Verified present on the host: official CLI `mmx 1.0.27`.

```
mmx image generate --prompt <text> --model image-01
                   --width <px> --height <px> --seed <n>
                   --n 1 --out <path> --quiet --non-interactive
```

`--width`/`--height` are in `[512, 2048]`, multiples of 8, and effective only for
`image-01`. `--out` takes an exact path for a single image. Custom dimensions are
verified locally rather than discovered at request time.

