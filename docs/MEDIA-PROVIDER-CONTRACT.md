# Media Provider Contract

> Defines the interface for all media generation providers (MiniMax, future providers).

## Interface

## The provider family

Speech and image are **separate provider ABCs over one set of shared
infrastructure**, not one monolithic class with optional-everywhere signatures.
Forcing three modalities through one signature produces optional arguments rather
than types, and blurs the receipts.

Current implementation:

| ABC | Modality | Declared in | State |
|---|---|---|---|
| `MediaProvider` | narration | `contract.py` | implemented (M2) |
| `ImageProvider` | stills | `image_contract.py` | implemented (M3) |
| `VideoProvider` | generated shots | `video_contract.py` | implemented (M4) |

There is **no `SpeechProvider` class**. `MediaProvider` is the current,
speech-shaped ABC. Renaming it to an explicit `SpeechProvider` is a clean
improvement but is **deferred**: it would churn the M2 speech module and its 85
tests for naming alone, and nothing about M3 or M4 depends on it. M4 introduces
`VideoProvider` beside the existing two without destabilising speech.

Shared provider-family infrastructure:

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

`MediaProvider` also remains the common ancestor so existing speech code keeps
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
        raise CapabilityNotSupported(...)     # video lives on VideoProvider, not here

class ImageProvider:
    def capabilities(self) -> dict
    def health(self) -> dict
    def generate_image(self, ImageRequest) -> ImageAsset
    def receipt(self, asset) -> ImageReceipt

class VideoProvider:                          # M4, Issue #22
    def capabilities(self) -> dict
    def health(self) -> dict
    def generate_video(self, VideoRequest) -> VideoOutcome
    def receipt(self, asset) -> VideoReceipt
```

`VideoProvider` is deliberately a separate ABC rather than extra methods on
`MediaProvider`. Video's inputs are genuinely different — it is asynchronous, it
carries references as well as text, it returns an audio track nobody asked for, and
its defining invariant is **how many paid tasks may be created**. That last one
would otherwise live in a boolean argument, where it is easy to set wrong.

Implementation: `src/contentops/media/contract.py`, `image_contract.py`,
`video_contract.py`.
Tests: `tests/test_minimax_speech.py`, `test_minimax_image.py`, `test_minimax_h3.py`.

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
| Image (`ImageProvider`, `MiniMaxMPlanImageProvider`, `image-01`) | `IMPLEMENTED` / M3 | #20 |
| Image human review (composition, artifacts, publish intent) | `PENDING_FOUNDER_REVIEW` | #20 |
| Video | planned | #22 |

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

Generic across providers. No vendor vocabulary, and no `entitlement` /
`token_plan` field: entitlement is expressed as `billing_mode` plus the balance
and quota facts the gate actually checked.

```json
{
  "provider": "...",
  "product": "...",
  "plan": "...",
  "billing_mode": "subscription",
  "payg_allowed": false,
  "credit_pack_allowed": false,
  "credential_class": "SUBSCRIPTION",
  "credential_source": "...",
  "transport": "...",
  "transport_version": "...",
  "model": "...",
  "fingerprint": "hash(provider + product + plan + model + mode + prompt + params)",
  "attempt": 1,
  "retry_reason": null,
  "billing_guard_verdict": "SAFE_INCLUDED_PLAN",
  "billing_guard_reasons": [],
  "quota_before": {},
  "quota_after": {},
  "post_generation_billing_state": {},
  "output_sha256": "...",
  "technical_qc": {},
  "generated": true,
  "evidence_capable": false,
  "production_ready": false,
  "human_review": "PENDING_FOUNDER_REVIEW"
}
```

Worked example for the current provider, using only generic field names:

```json
{
  "provider": "minimax_m_plan",
  "product": "m_plan",
  "plan": "explore",
  "billing_mode": "subscription"
}
```

The credential **class** and **source** are recorded; the credential value is
never written to any receipt, sidecar, attempt record, event log or exception.

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

### The canonical boundary

Exactly three kinds may carry a factual claim:

| Evidence-capable | Why |
|---|---|
| `REAL` | a real recording, photograph or capture |
| `SCREENSHOT` | a real screen capture |
| `SCREEN_RECORDING` | a real screen recording |

Everything else is **support-only**:

| Support-only | What it may do | What it may never do |
|---|---|---|
| `DIAGRAM` | explain architecture, flow, relationship, concept, sequence | witness a benchmark, test result, analytics metric, customer outcome, UI state, source-code fact or production behaviour |
| `GENERATED_IMAGE` | act as hook, cover, concept, metaphor, background, transition | carry any claim |
| `GENERATED_VIDEO` | act as hook, hero, concept, transition, impossible-to-record shot | carry any claim |

`AssetKind.EVIDENCE_CAPABLE` is the **single truth table**. The planner derives
capability from it rather than keeping a second boolean per option, which is
exactly how `DIAGRAM` came to be wrongly marked evidence-capable.

A diagram is a legitimate and useful asset. It simply explains; it does not
prove. When a diagram illustrates a claim, the underlying real source stays
traceable separately through `claim_refs`.

### Intrinsic properties versus usage properties

These are different kinds of fact and are governed differently.

| Intrinsic asset property | Derived from | Overridable |
|---|---|---|
| `kind` | the caller | no |
| `generated` | `kind in AssetKind.GENERATED` | **never** |

| Usage property | Meaning | Overridable |
|---|---|---|
| `evidence_use` | how this asset is used right now | yes, within the boundary |
| `evidence_capable` | whether it is permitted to carry claims | **down only** |

```
GENERATEDNESS IS DERIVED FROM KIND AND CANNOT BE OVERRIDDEN
CALLER MAY REDUCE CAPABILITY
CALLER MAY NEVER ESCALATE CAPABILITY
```

Generated-ness is **provenance**, not policy:

```
GENERATED_IMAGE  -> generated = True
GENERATED_VIDEO  -> generated = True
REAL             -> generated = False
SCREENSHOT       -> generated = False
SCREEN_RECORDING -> generated = False
DIAGRAM          -> generated = False
```

A caller that supplies a conflicting value is **refused, not normalised**. The
conflict means bad caller logic, a bad migration, or an attempt to bypass
provenance, and silently correcting it would hide all three.

This closed a real bypass: `GENERATED_IMAGE + generated=False` skipped the
receipt requirement entirely, so a synthetic asset could register with no
provenance at all. `DIAGRAM + generated=True` was equally wrong, mislabelling
deterministic output as model output.

Note that capability and provenance are independent. `REAL` with
`evidence_capable=False` is legal, because a real asset may be used decoratively.
`REAL` with `generated=True` is not.

### Capability may be lowered, never raised

```
CALLER MAY REDUCE CAPABILITY
CALLER MAY NEVER ESCALATE CAPABILITY
```

```
canonical_capable = kind in AssetKind.EVIDENCE_CAPABLE

evidence_capable is None   -> capable = canonical_capable
evidence_capable is False  -> capable = False
evidence_capable is True   -> raise, unless canonical_capable
```

The previous version trusted the caller's boolean, so
`DIAGRAM + evidence_capable=True + EVIDENCE` registered happily. Any caller could
have promoted a diagram into proof of a benchmark.

A claim-bearing role requires **both** the kind's canonical capability and a
resolved capability of `True`. Checking the caller's flag alone trusts the caller;
checking the kind alone ignores a deliberate downgrade.

### Claim-bearing roles

```
EVIDENCE  CLAIM_SOURCE  BENCHMARK_PROOF  TEST_RESULT
ANALYTICS_PROOF  UI_SCREENSHOT  CUSTOMER_PROOF  SOURCE_CODE_PROOF
```

Every one requires an evidence-capable kind. `DIAGRAM + BENCHMARK_PROOF` fails
even when the caller passes `evidence_capable=True`.

Generated kinds additionally require `generated=True`, `evidence_capable=False` and
a `receipt_ref`. Failure is a domain error (`GeneratedAssetEvidenceError`), not a
warning, raised at the only place an asset enters the system.
`AssetRegistry.assert_evidence_boundary()` re-checks the whole rule set —
provenance, capability, receipt presence and claim-bearing roles — so a bad
direct write, a hand-edited registry file or a migration is still caught. A
record whose `generated` flag disagrees with its `kind` is corrupt regardless of
the role it claims.

## AssetPlanner

```
real factual evidence
    > screenshot / screen recording
    > deterministic diagram (support-only)
    > generated support visual
```

Capability is derived from `AssetKind.EVIDENCE_CAPABLE`, so the planner cannot
drift from the registry.

`MINIMAX_IMAGE` is for hooks, covers, concepts, metaphors, backgrounds,
transitions and decorative scenes. `DIAGRAM` is for architecture explanations,
flowcharts, concept maps, timelines and deterministic process illustrations; both
register as `VISUAL_SUPPORT`.

A beat that requires evidence resolves only to `REAL`, `SCREENSHOT` or
`SCREEN_RECORDING`. When only support-only options are available the planner
refuses and says that **real or captured material is required**, rather than
reporting merely that a generated image is unavailable. It never degrades.

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

# M4 — Video (Issue #22)

## One task per attempt

Video is billed at **task creation**, so the defining invariant is a count, not a
result:

```
ONE GENERATION ATTEMPT = AT MOST ONE PROVIDER TASK
```

The provider reaches that by making `create_task`, `poll_task` and
`download_result` three separate methods on `H3Transport`. A combined
`generate()` would hide the expensive call inside a retry loop, which is exactly
how a poll timeout turns into a second bill.

Recovery therefore always acts on an **existing** task. A new task is created
**never** because of:

| Situation | Correct action |
|---|---|
| poll timed out | resume polling the same task |
| temporary 5xx while polling | resume polling the same task |
| process restarted | read private state, resume the same task |
| download failed | retry the **same** URL |
| download timed out | retry the same URL |
| disk write failed after generation | re-fetch the same result |
| QC rejected the download | re-fetch the same result first |

Each of those is a **recovery** problem, not a generation reason.

## Lifecycle order

```
validate locally          free; catches every documented rule
build the fingerprint     over the COMPILED prompt, not the raw intent
check the cache           a hit needs no billing and no network
resume private state      an existing task is finished, never replaced
require quota_budget      video is the most expensive call ContentOps makes
require test_objective    a task must have a recorded reason to exist
build the content array   last free step; an encoding failure costs nothing
authorize("video")        subscription-only pre-flight
write a STARTED attempt   durable evidence
CREATE exactly one task   <- the only billable step
persist raw task id       private state, BEFORE the first poll
poll THAT task            to a terminal state
download THAT result      retrying the same URL on failure
QC -> canonical output -> immutable receipt -> review sheet
AssetRegistry.register()  only once the receipt exists
```

`quota_budget` and `test_objective` are checked **after** the cache and the resume
point and **before** the billing gate, so a cache hit or a restart-resume is never
forced to declare a budget it will not spend.

The content array is built **before** the gate, not after. It is the last step
that can fail for a non-billing reason — an unreadable reference, a media type
that cannot be determined, an undocumented role — and consulting the billing
source for a request that will never be sent is pointless. It stays *after* the
cache and the resume point because those are strictly cheaper and send nothing.

## Reference media is detected, never guessed

A reference's declared media type comes from its **content**, never from its file
name. M3 established why, having reproduced it twice against the real provider: a
`.png` request came back as **JPEG bytes**. For an H3 reference the cost of
guessing is higher, because the declared subtype is matched against the bytes, so
`data:image/png` carrying JPEG is a rejection that reads like a generation
problem rather than an encoding one.

- **images** reuse M3's byte sniffer (`image_container.detect_image_container`)
  rather than duplicating its magic-byte logic, so the two cannot drift
- **video and audio** are determined by `ffprobe`, already the sanctioned probe

A mismatch is **recorded, not normalised**: each receipt carries
`reference_media[]` with the role, the detected container, the declared extension
and whether they agreed.

HEIC/HEIF are **not** accepted, even though the documented input set lists them.
No reliable way exists in this environment to verify what a `.heic` file contains
— the local ffmpeg exposes no HEIF demuxer and M3's sniffer deliberately supports
only PNG/JPEG/WEBP — so declaring `image/heic` on the strength of a suffix would be
exactly the behaviour this rule exists to remove. A HEIC reference is refused
locally instead; converting to PNG, JPEG or WEBP resolves it.

Detection happens **once**. The transport consumes the validated descriptor rather
than re-deriving a type, so there is one media truth per reference.

## Task id privacy

The raw provider task id is operationally necessary for resuming a poll, so it
exists — but only in private, gitignored runtime state, written **before** the
first poll. The public receipt stores `task_created: true` plus a per-receipt
salted `task_ref_hash`.

That token is **not recomputable**. Its salt is not persisted, so it cannot be
verified against the raw id afterwards either. It is therefore generated once,
persisted, and reused verbatim. Minting a second token for the same task would
make the attempt record and the receipt look like two different tasks and destroy
the correlation the receipt exists to provide.

`task-state/` is ignored repository-wide (`**/task-state/`) because the provider
accepts any work directory, and `check_repo_policy` **fails CI** if such a file is
ever tracked. Sanitising the directory into a tracked artifact was rejected: a
sanitised copy invites being treated as the recovery handle when it is not one.

`GenerationAttemptRecord.write()` also refuses to persist a record containing a
raw task id, running before every write rather than relying on review.

## Attempt 2 is a second bill

A retry is only permitted when **all** of these hold:

1. attempt 1 is a durable record in state `FAILED` with a terminal provider state
2. a named failure reason is given
3. the generation fingerprint **changed**
4. an explicit new quota budget is given

A running task is not retryable — it is resumed. Poll failures, download failures
and local disk failures are not retryable either, for the same reason. Operational
recovery must not become another bill.

## Receipt convention

| Artifact | Name |
|---|---|
| canonical asset | `<name>.mp4` |
| immutable generation receipt | `<name>.mp4.receipt.json` |
| Founder review sheet | `<name>.mp4.human-review.json` |
| private task state | `<work-dir>/task-state/<fingerprint>.json` |
| durable attempt records | `<work-dir>/attempts/<attempt-id>.json` |
| reuse audit | `<work-dir>/reuse-events.jsonl` |

The receipt is written and verified **before** `AssetRegistry.register()`. A video
whose receipt failed to write is not registered: an asset without provenance is
what the evidence boundary exists to prevent.

A cache hit loads and validates the original receipt and restores provider receipt
state. It never rewrites the original generation receipt.

## Audio policy

H3 returned an unrequested AAC track in both M2.0 and M4, so the track's existence
is normal provider behaviour and must be a decision rather than a surprise:

| Policy | Meaning |
|---|---|
| `KEEP` | use the generated track |
| `MUTE` | keep the file, drop the track |
| `REPLACE` | drop the generated track, substitute deterministic narration |

`REPLACE` is the ContentOps default: narration must stay deterministic, and H3's
native sound must never quietly compete with it. The chosen policy travels on both
the asset and the receipt. Applying it downstream is M4.5 work.

## Technical QC

Measured facts only: container, codec, full decodability, duration, dimensions,
aspect, fps, audio presence, black-frame runs, freeze runs, frame-difference
distribution. It never concludes "cinematic", "beautiful" or "publishable" —
those are human judgements, and a gate that reports them teaches the pipeline to
trust itself.

Duration and aspect use **tolerance**, never equality. Both M2.0 and M4 requested
4.000 s and received **4.458 s**; an equality check would reject correct output.
Requested and actual values are both recorded so the deviation stays visible
instead of being absorbed into a pass.

## Human review

Reference fidelity cannot be automated. Automated QC can prove a file decodes and
does not freeze; it cannot tell whether the subject stayed the same person or
whether the Founder would publish it.

So each generation writes a review sheet with eleven **named** fields —
`subject_fidelity`, `motion_plausibility`, `temporal_artifacts`,
`reference_fidelity`, `first_frame_fidelity`, `last_frame_fidelity`,
`audio_suitability`, `caption_safe_area`, `cross_shot_consistency`,
`overall_quality`, `willingness_to_publish` — every one of them `null`, with
`state` and `decision` both `PENDING_FOUNDER_REVIEW`. Automated measurements ride
alongside, labelled as measurements.

Reference-only fields are marked not-applicable for modes that do not use them, so
a reviewer can tell "not assessed" from "not relevant to this mode".

## Prompt structure

`H3PromptCompiler` implements the current official
`MiniMax-AI/MiniMax-H3` `skills/h3-prompt-writing` skill. The upstream repository is
**not vendored**; the compiler implements the structure it specifies, and the repo,
commit, skill path and `checked_at` travel on every receipt.

Base modes emit an optional alignment instruction as the first line, then one blank
line, then `integrated_multimodal_description`, `overall_soundscape`,
`non_diegetic_music`. Ref2VA emits six sections: `subject_definitions`, `summary`,
`retention_analysis`, `detailed_description`, `overall_soundscape`,
`non_diegetic_music`.

`S.SS` is the effective duration to exactly two decimals. `[Shot 1]` carries no
timestamp; later shots carry a strictly increasing cut time inside the duration.
Field names, section order, reference labels and timing notation are reproduced
exactly, because the model is trained against them: a prompt that renames
`overall_soundscape` is not a stylistic difference, it is a different request.

## Transport

The **documented public API** over HTTPS, not the official CLI:

| Call | Endpoint | Cost |
|---|---|---|
| create | `POST /v2/video_generation` | **the only billable call** |
| poll | `GET /v2/query/video_generation/{task_id}` | free |
| download | the URL returned in `content.url` | free |

The CLI remains useful for `auth`, `status`, `quota` and diagnostics, but it cannot
express the required resolution: it silently drops `--resolution` and always sends
`2K`, so 768P is unreachable through it.

The resolved base URL is passed to **both** the billing gate and the transport. An
account can resolve to the regional CN mirror, and a key authorised against one
host is not evidence about the other.

## Evidence boundary

Unchanged from M3. A generated shot is support-only:

```
kind             GENERATED_VIDEO
generated        true
evidence_capable false
evidence_use     VISUAL_SUPPORT
```

`AssetKind.EVIDENCE_CAPABLE` remains `REAL`, `SCREENSHOT`, `SCREEN_RECORDING`
only. H3 may support a hook, a hero visual, a concept, a metaphor, a transition or
an unrecordable scene. It may never prove a benchmark, a test result, an analytics
metric, a UI state, a customer outcome, source code or a real product demo.
# M4.5 — converged media layer (Issue #27)

## Modality is not asset kind

M2–M4 produced three providers whose receipt schemas agree on almost nothing:

|                          | speech                              | image                  | video                  |
|--------------------------|-------------------------------------|------------------------|------------------------|
| `schema` field           | **absent**                          | `...image-receipt/v1`  | `...video-receipt/v1`  |
| asset digest field       | `normalized_sha256` / `raw_sha256`  | `output_sha256`        | `output_sha256`        |
| `generated`              | **absent**                          | `true`                 | `true`                 |
| `evidence_capable`       | **absent**                          | `false`                | `false`                |
| `AssetKind`              | **none**                            | `GENERATED_IMAGE`      | `GENERATED_VIDEO`      |
| registered in registry   | **never**                           | by the CLI script      | by the provider        |

`MediaModality` (SPEECH / IMAGE / VIDEO) is therefore a dimension **separate** from
`AssetKind`, and a `MediaAssetEnvelope` carries `modality` always and `asset_kind`
optionally — `None` for speech.

`GENERATED_SPEECH` was deliberately **not** invented. It would put a non-visual
into a visual evidence enum, and it would imply narration has an evidence boundary
it does not have. Narration is deterministic and is not proof.

`AssetKind` remains the single owner of the evidence truth table. The converged
layer asks it; it never restates it.

## One validator, three adapters

```
validate_media_asset(envelope, adapter)
        |
        +-- SpeechValidationAdapter
        +-- ImageValidationAdapter
        +-- VideoValidationAdapter
```

The validator owns only what is common: file existence, receipt existence and
parse, digest agreement, fingerprint, subscription-only billing, targeted
credential and task-privacy invariants, review state, fallback explicitness, and
lineage. Adapters own the differences. One dispatch table sits at a protocol
boundary; the common path has **no** modality branch, and a test enforces that.

Rules the implementation added beyond the original design:

- a **provider generation** must declare its modality's schema
- a **non-generated** asset must **not**, because nothing's API produced it
- a missing `technical_qc` **fails** a generation but is **not applicable** to an
  import or a transform — no provider ran, so there is nothing to report, and
  demanding it would either block honest records or invite a fabricated one

Credential checking is targeted, not an unbounded regex sweep: no string value
anywhere in a public receipt may match the closed provider-key shape, and no
`Authorization` header value may appear. Provider-level sentinel tests remain
authoritative, because they know the actual key.

## Immutability and derived assets

Provider-generated canonical assets are immutable. `AudioPolicy` is applied by
producing a **derived asset** with a `contentops.media-transform/v1` receipt that
names the source digest:

```
shot.mp4 (provider, immutable)
  └─ shot-mute.mp4 / shot-replace.mp4  (derived)
       └─ <name>.transform.json  →  source_asset_sha256, output_sha256, tool, command
            └─ shot.mp4.receipt.json  (untouched)
```

| Policy | Derived asset | Audio in output | Narration required |
|--------|---------------|-----------------|--------------------|
| `KEEP` | **none** — the original is reused | present (recorded) | no |
| `MUTE` | yes | absent | no |
| `REPLACE` | yes | absent | **yes** |

`KEEP` writes nothing: bytes that did not move must not acquire provenance
implying they did. `REPLACE` does not mux narration — composition does, from a
deterministic track, so this step cannot produce a silent mix. Video streams are
**copied** when audio is dropped, never re-encoded, so a mute cannot degrade the
picture.

### A transform changes bytes, not provenance

The transform receipt records three separate facts, not one overloaded boolean:

| Field | Question it answers | `MUTE` on a generated shot |
|---|---|---|
| `provider_generated_bytes` | did *this transform* emit these bytes via an API? | `false` |
| `derived` | did a transform run? | `true` |
| `source_generated` | was the **lineage** generated media? | `true` |

The derived envelope therefore keeps `generated: true`. Generated provenance
survives a local edit: a generated shot with its audio removed is still generated
content, and `MediaAssetEnvelope` refuses to be constructed with a
`GENERATED_*` kind and `generated=False` — in **both** directions, derived or not.
Derivation is recorded by `derived_from`; downgrading `generated` is not a way to
express it.

The original design had a single `generated` field doing all three jobs. It made a
transform receipt say `generated=false` about generated content — the contradiction
this split removes.

## Capability registry

| Capability | Status | Evidence |
|---|---|---|
| `SPEECH/NARRATION` | `VERIFIED` | PR #24 |
| `IMAGE/GENERATED_SUPPORT_VISUAL` | `VERIFIED` | PR #25 |
| `VIDEO/H3_T2VA` | `VERIFIED` | M2.0 real task |
| `VIDEO/H3_I2VA` | `VERIFIED` | M4 real task |
| `VIDEO/H3_FL2VA` / `H3_L2VA` / `H3_REF2VA` / `H3_MAX` | `DOCUMENTED_BUT_NOT_TESTED` | fixtures only |
| `VISUAL/REAL_EVIDENCE` / `VISUAL/DIAGRAM` | `MANUAL_ONLY` | operator / local render |

No vendor word appears in a capability identifier. Registration takes a
**callable**, never a provider object, so the registry cannot retain a credential
or billing state. A `VERIFIED` capability cannot be constructed without citing
evidence, so the table cannot decay into a wish list. An unsupported capability
raises `CapabilityNotSupported` and is never substituted.

Fixture evidence proves how code behaves. It never proves what an account is
entitled to, and the two are not conflated.

## Quota policy is not a cost model

`MediaQuotaPolicy` holds explicit operator values. The weekly floors are **chosen**.
They are not derived from the observed ~7pp H3 delta — that is an input to
conservative budgeting, not a price, because the provider exposes percentages only
and one observation at one clip length and resolution is not a rate.

`QuotaScheduler` takes **one** snapshot for all actions, because all three
modalities share one account plan. Priority is fixed by policy:

1. reusable assets
2. mandatory real or captured evidence
3. narration
4. deterministic local assets
5. generated image support
6. generated video support

Video goes last because it is the most expensive call ContentOps makes and the
least load-bearing for a truthful video. It must never starve narration or the
evidence a claim depends on.

Decisions: `ALLOW` / `REUSE_REQUIRED` / `DEFER` / `MANUAL_REQUIRED` / `BLOCKED`,
each recorded with the policy in force and the observation made.

**A scheduling decision authorises nothing.** Every provider still runs its own
`BillingGuard` immediately before its call, because quota can be spent by something
else in between.

## Evidence-first execution

A claim-bearing beat resolves only to `REAL` / `SCREENSHOT` / `SCREEN_RECORDING`.
If the required material is absent the beat returns `EVIDENCE_ASSET_REQUIRED` — a
structured refusal, not an exception and not a substitute. The locator reports
`MISSING_REAL_ASSET` or `NEEDS_CAPTURE`.

Adopting real material writes a `contentops.media-import/v1` receipt recording
where it came from, its digest, and that no provider was involved. An import with
only a digest would be the weakest link in the chain.

Fallback is a recorded field, never a behaviour. A substitute names what was
requested, what was used, and why; an unnamed swap is refused.

## Converged gate vocabulary

| State | Meaning |
|---|---|
| `BLOCKED` | validation or technical QC failed |
| `DEGRADED_FALLBACK` | technically fine, a declared substitute was used |
| `PENDING_HUMAN_REVIEW` | technically fine, awaiting a person |
| `PRODUCTION_READY` | technically fine **and** a person approved it |
| `REJECTED` | a person looked at it and refused it |

Technical PASS is not approval. The gate cannot reach `PRODUCTION_READY` without a
recorded human decision, and the **validator** refuses a receipt claiming
`production_ready: true` while still `PENDING_FOUNDER_REVIEW` — that
contradiction is how a pipeline comes to believe it cleared its own work.

## Manifest is the single asset list

`contentops.media-manifest/v1` is the only list composition and final QC read.
It is an **index**, not a receipt: modality-specific detail stays in the receipts,
because a manifest that copied every field would be a second source of truth that
could disagree with the first.

Deterministic by construction: assets sorted by `asset_id`, fixed key order, and
**no timestamp in the body**. Timestamps belong in receipts, which already record
when something happened; one in the manifest would make every build differ for no
informational gain. An asset with no gate decision, or a duplicate `asset_id`, is
refused rather than admitted.

### Paths are logical, never local

An asset path in a committed manifest is a **logical reference**:
`project://assets/shot.mp4` (relative to the project) or `repo://docs/x.png`
(relative to the repository). It is resolved to a local path at the point of use.

An absolute path is never written. The first committed manifest carried eight
`D:\Projects\...` paths, which made "deterministic manifest" true on exactly one
machine: the fingerprint changed with the checkout root, so it was not a cache key
and not comparable in review. A path outside both roots cannot be expressed
logically, so it is refused rather than written as a machine path.

### The timeline is explicit, and separate from the inventory

`assets` is an **inventory** and `timeline` is the **timeline**. Both are required.

`usable_assets()` answers "may this asset appear"; it does not answer "does this
asset appear here". An AudioPolicy transform keeps its source *and* adds the derived
asset, both claiming placement `beat-05` — and iterating the inventory put
`beat-05` and `beat-05-replaced` on the timeline, so the pre-transform native audio
played over the narration REPLACE was meant to guarantee would be the only track.

So composition reads `active_visual_assets()`, one asset per placement, each with a
recorded `selection_reason` and the `superseded_asset_ids` it displaced. A derived
asset supersedes its source for MUTE/REPLACE; KEEP has no derived asset. Two derived
assets claiming one placement are refused as `AMBIGUOUS_DERIVED_ASSETS` rather than
resolved by a tie-break, because the choice is not derivable from the data.

Refused with a named code, never silently corrected: `DUPLICATE_PLACEMENT`,
`UNKNOWN_ACTIVE_ASSET`, `INADMISSIBLE_ACTIVE_ASSET`, `MISSING_PLACEMENT_ID`,
`ASSET_ACTIVE_IN_TWO_PLACEMENTS`, `AMBIGUOUS_DERIVED_ASSETS`.

`audio_postconditions` states each active shot's audio outcome — so REPLACE's "no
native track, narration required" is a checkable claim in the receipt rather than an
inference a reviewer has to make.

## Composition reuses the pinned Easel path

```
manifest → thin manifest-to-storyboard translation
         → pinned Easel v0.2.1 (assemble_easel.run)
         → final.mp4
         → qc_video.qc, reading the same manifest-derived storyboard
```

No second compositor was built. Upstream remains unmodified. `qc_video` reads the
storyboard the manifest produced, so the final QC is a check of the manifest rather
than a separate opinion — and the fallback engine keeps its diagnostic-only
semantics and never claims `production_ready`.

### QC receipts cross a sanitization boundary

`qc_video` is a runtime tool. It reads real files, and its report legitimately names
them — `final.mp4 not found at D:\...\final.mp4` is an accurate diagnostic while it
runs. **The runtime result and the committed provenance are different concerns**, so
`contentops.media.qc_canonical` is the boundary between them:

```
qc_video runtime result  (may contain absolute local paths)
        ↓
contentops.qc_canonical  →  tracked qc-report-<target>.json / .md
```

Upstream `qc_video` internals are untouched. The boundary rewrites the file it wrote,
in place, so there is exactly one report per target rather than a raw copy and a
sanitized copy that can disagree. Sanitizing rewrites **paths only** — never a
verdict, never a check result.

Every canonical report declares its own currency, so a stale result can never read as
current:

| Field | Meaning |
|---|---|
| `currency` | `CURRENT`, or `NON_CURRENT_DIAGNOSTIC` |
| `graded_target` | the logical reference actually graded, e.g. `project://final/m45.mp4` |
| `non_current_reason` | **required** when currency is not `CURRENT` |

A non-current report with no stated reason is refused, because an unexplained stale
verdict is indistinguishable from a real one. Two tracked reports once sat side by
side — one `WARN` on `final/m45.mp4`, one `FAIL` on `final/final.mp4`, a file this
stage never produces. The stale one was removed; `qc-report-m45.json` is the single
canonical M4.5 QC report.

A regression test scans the canonical committed artifacts
(`media-manifest.json`, `m45-integration.json`, `qc-report-m45.{json,md}`,
`storyboard.json`) for host-specific paths — Windows drive and UNC paths, POSIX and
macOS home directories, mounted volumes — and fails on any hit.

## The technical integration, and what it is not

`scripts/m45_media_integration.py` produces one local, fixture-driven artifact
(`project://final/m45.mp4`) proving `registry → manifest → compose → final QC`
with **zero provider calls**. Weekly quota is untouched.

Every asset is a deterministic fixture, labelled as such in its receipt, in the
manifest header and in the integration report. Media binaries are gitignored; the
manifest, receipts and storyboard are committed.

**H3 reuse is explicit, and never discovered.** `--reuse-h3-shot PATH` reuses a real
shot instead of generating a fixture; omitting it means fixtures, always. There is no
filesystem scan. The previous version globbed `.verify-tmp/m4` for any
`*.mp4.receipt.json`, so a clean clone produced fixtures while a workstation with M4
leftovers silently produced real provider media — and both runs were committed as
"the integration". A run's meaning must be a function of its arguments.

Reuse is validated, not trusted: both the shot and its receipt must exist, the
receipt must be a real `contentops.video-receipt/v1` generation receipt, and its
`output_sha256` must match the file. A shot with no receipt is refused — otherwise
an unexplained file enters a committed run. `h3_shot_source` in the report states
which of `fixture_generated` / `explicit_reuse` was used, so it never has to be
inferred from which artifacts happen to be present.

It does **not** prove real `SourceArtifact` ingestion, `Claim Ledger`
completeness, Founder approval, a production golden, or three consecutive
production builds. The output is `production_ready=false` /
`PENDING_FOUNDER_REVIEW`, and nothing in the code path can report otherwise.
