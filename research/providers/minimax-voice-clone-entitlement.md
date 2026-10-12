---
title: MiniMax M Plan voice cloning entitlement
canonical: false
type: research
status: current
issue: "#23"
checked_at: "2026-10-12"
translation_of: research/providers/minimax-voice-clone-entitlement.md
---

# MiniMax M Plan voice cloning entitlement (Issue #23)

> Research artefact, not canonical design. Canonical capability status lives in
> `docs/MEDIA-PROVIDER-CONTRACT.md` and `docs/CURRENT-STATE.md`.
>
> 中文版： [minimax-voice-clone-entitlement.zh-CN.md](minimax-voice-clone-entitlement.zh-CN.md)

## Result

```
ENTITLEMENT_PRESENT_BUT_API_CLONE_NOT_TESTED
```

Entitlement is no longer an open question. The account **has** voice cloning, and has
already used it: a read-only `POST /v1/get_voice` on 2026-10-12 returned one entry under
`voice_cloning`, and the current documentation states that entries appear there *only
after the voice has been successfully used for speech synthesis*.

What remains untested is narrower and specific: **creating a clone through the public
API with this Subscription Key**. That single billable request has not been sent.

Superseded: the 2026-10-04 result of `DOCUMENTED_BUT_NOT_TESTED`, which was correct at
the time and is kept below for the audit trail.

## What the subscription key can and cannot reach (measured 2026-10-12)

| Host | `POST /v1/get_voice` | Meaning |
|---|---|---|
| CN regional host | HTTP 200, `status_code=0` | the Subscription Key is accepted here |
| International host | HTTP 200, `status_code=2049` | **invalid api key** — this key is not authorised here |

Literal endpoint URLs are deliberately not written here; repository policy keeps them
local-only, and `scripts/check_docs.py` enforces that. The host actually used is resolved
at runtime and recorded in every receipt as `base_url_host`.

Both calls are read-only metadata listings. Neither uploads, clones, synthesises or
spends anything.

The region was resolved from the account's own `~/.mmx/config.json` (`region: cn`), not
assumed. This is the concrete case the H3 transport docstring warns about: *"a key
authorised against one is not evidence about the other."* It is now measured rather
than suspected, and it is why
`src/contentops/media/minimax_voice_clone.py` records `base_url_host` in every receipt.

## An existing clone is already on the account

| Field | Value |
|---|---|
| count under `voice_cloning` | 1 |
| `created_time` | 2026-10-12 |
| `voice_name` | empty |
| `voice_id` shape | MiniMax-generated (`moss_audio_…`), **not** a custom API id |
| `voice_id` sha256 | `9dbdd6e0663bd013dca1059bd790d408190a5c9a353a4351c210020f1c59fc23` |

Three things follow, and the third is the one that costs money if ignored:

1. Clone entitlement is **active**, not merely documented.
2. It was created **outside ContentOps** — no receipt, log or artifact in this
   repository records an upload or clone, and nothing under `.verify-tmp` predates this
   probe. The MiniMax-generated id shape is consistent with creation through the web
   UI rather than the API.
3. **Its provenance is unverified.** No receipt binds it to the Founder's approved
   sample, and it carries no name. Reusing it would be cheaper — but "there is a voice
   here" is not evidence that it is *this person's* voice, and treating an unnamed id as
   the Founder's would be exactly the filename-trust mistake this repository refuses.
   Reuse versus re-clone is a Founder decision, not an engineering one.

## Commercial terms

| Dimension | Value | Basis |
|---|---|---|
| Clone fee | one-time **CNY 9.9** per cloned voice | **FOUNDER_SUPPLIED_ACCOUNT_SPECIFIC_FACT** from direct MiniMax customer service |
| TTS after cloning | M Plan subscription quota | same |
| Target synthesis model | `speech-2.8-hd` | same |
| PAYG TTS | **forbidden** | repository policy |
| Credit Pack TTS fallback | **forbidden** | repository policy |

The CNY 9.9 figure is recorded as an account-specific fact. It is **not** restated as
public MiniMax pricing and no other figure is derived from it.

This supersedes the 2026-10-04 note that the clone call carried "no documented separate
charge". The documentation may still be silent on it; the Founder's account is not, and
account-specific commercial fact outranks documentation silence.

## Endpoint shape (re-read 2026-10-12)

```
POST /v1/files/upload     multipart/form-data, purpose=voice_clone  -> file.file_id
POST /v1/voice_clone      application/json {file_id, voice_id}      -> voice_id
POST /v1/get_voice        application/json {voice_type: voice_cloning}
```

Custom `voice_id` rules: length `[8, 256]`, must start with an English letter, may
contain letters/digits/`-`/`_`, may not end with `-` or `_`, must not duplicate an
existing id. `XSuperPlayFounderV1` satisfies all of them.

Upload rules: `mp3`/`m4a`/`wav`, 10 s to 5 min, at most 20 MB.

Two details that change behaviour rather than merely describing it:

- **`voice_cloning` is only populated after a successful synthesis.** An empty list
  immediately after creating a clone is therefore the expected state, not a failure.
  Code that treated it as failure would report a correct clone as broken.
- **`text` is an optional preview field.** Sending it makes cloning also synthesise,
  which is a second generation event. The clone payload in this repository is
  deliberately `{file_id, voice_id}` and nothing else.

## Transport

The documented public API, using the same resolved Subscription credential as the rest
of ContentOps. The official CLI (`mmx` 1.0.27) still has no clone command — `speech`
offers `synthesize`, `generate`, `transcribe`, `recognize`, `voices` only — so this is
the sanctioned capability-gap route, not a workaround.

The Easel legacy path (`GroupId`, `speech-01`, `api.minimax.chat`) stays classified
`EASEL_MPLAN_AUTH_INCOMPATIBLE` and is not used.

## Still open on #23

- [ ] the one billable `POST /v1/voice_clone` with a Subscription Key, and its status code
- [ ] whether it consumes included plan quota or triggers the one-time fee
- [ ] one full `speech-2.8-hd` narration with the resolved cloned voice

## Superseded 2026-10-04 findings

Kept for the audit trail. The entitlement error code is still `2038` (`无复刻权限，请检查账户认证状态`);
the API still needs no `GroupId`; the 7-day expiry for an unused clone still applies.

```text
DOCUMENTED_BUT_NOT_TESTED
```

No clone was attempted. Two blockers stood in the way, and neither could be cleared
by an agent: the account's real-name verification state was unknown, and no
rights-cleared human voice sample existed in this repository.

## What the current official sources said on 2026-10-04

| Question | Answer | Source |
|---|---|---|
| Is there a programmatic voice-clone API? | Yes, `POST /v1/voice_clone` | current voice-clone API reference |
| Does it need the legacy `GroupId`? | **No.** The current schema has no `GroupId` parameter | same |
| Does the official CLI expose it? | **No.** `mmx speech` offers `synthesize`, `generate`, `transcribe`, `recognize`, `voices` only | `mmx speech --help`, v1.0.27 |
| Is it named in the M Plan tier wording? | **No.** Tiers promise "image and audio generation"; cloning is voice management, not stated | current M Plan FAQ, both regions |
| Is there an entitlement error code? | Yes: **`2038` 无复刻权限，请检查账户认证状态** | voice-clone API reference |
| Is a separate charge documented? | The optional **preview** is billed as T2A at normal T2A pricing. The clone call itself carried no documented separate charge | same |
| Is real-name verification required first? | **Yes.** "使用本接口前，请先完成该账户的企业认证" | same |
| Does the clone expire? | Yes, deleted if not formally used within **7 days** | same |

### Speech entitlement is not clone entitlement

M2.0 established that speech synthesis is covered. The M Plan pages promise "image
and audio generation". They do not mention voice cloning anywhere, and the API
defines a distinct entitlement error for it. Assuming speech coverage implies clone
coverage is exactly the inference this repository refuses to make — so the status
stayed unproven rather than assumed either way.

As of 2026-10-12 that inference is no longer needed: the entitlement is directly
observed, not inferred from speech coverage.

## Why no clone was attempted on 2026-10-04

### Blocker 1 — no rights-cleared voice sample

Cloning requires a recording of a real person's voice. The only audio tracked in
this repository is **synthetic TTS output** of the project's own script
(`projects/easel-review/assets/voice_easel/narration.mp3` and the per-shot files).
Cloning a synthetic voice would be a poor technical test and would have no
rights basis, so it was not attempted.

The prohibition is absolute in this repository: no celebrity, creator, podcaster,
public figure or unknown-dataset speaker.

**Founder action required.** A rights-cleared sample meeting the current official
specification:

| Requirement | Value |
|---|---|
| Formats | `mp3`, `m4a`, `wav` |
| Duration | **at least 10 s**, at most 5 min |
| Size | at most 20 MB |
| Speakers | one speaker only |
| Conditions | clean recording, no music, no overlapping speech |
| Optional prompt clip | under 8 s, with its exact transcript as `prompt_text` |
| Optional ASR check | `text_validation` up to 200 chars, `accuracy` default 0.7 |

`need_noise_reduction` and `need_volume_normalization` exist but default to false,
so a clean recording avoids depending on them.

**Cleared on 2026-10-12.** The Founder supplied a 15 s mono 16 kHz WAV, registered in
the local digital-asset manifest as `voice-reference` with digest `bb56d052…`, and
matching that digest. Audited in
`projects/easel-enhanced-golden/receipts/founder-voice-sample-audit.json`: every
documented requirement passes, no clipping, LRA 1.4 LU, ~8 % silence. It stays a
`LOCAL_PRIVATE_INPUT` and is never committed.

### Blocker 2 — unknown verification state

The API requires personal or enterprise verification before the first call, and
returns `2038` when it is missing. Whether this account is verified cannot be
established without making the call, and making the call is exactly what is being
held back.

**Resolved on 2026-10-12**, indirectly but soundly: an existing clone is present under
`voice_cloning`, so verification has already been satisfied for this account at some
point.

## If a test is later authorised

1. Confirm the credential class is `SUBSCRIPTION`.
2. Confirm the declared one-time fee is within the authorised ceiling (CNY 9.9) and that
   the Founder has confirmed the spend. Note that the clone fee is a *separate
   dimension* from TTS billing: the "all balances exactly zero" rule is correct for
   synthesis and is deliberately **not** applied to this authorised one-time fee.
3. Upload the sample, then create **one** clone. No automatic retry.
4. Record: quota before and after, clone status and `base_resp.status_code`,
   model compatibility, the new `voice_id` as a **hash only**, and the output hash.
   Never the raw sample, the raw `voice_id`, or private identity data.
5. Synthesise **one** full narration with the cloned voice using the locked Golden
   script, subject to the same gate.
6. A `2038` would make this `NOT_ENTITLED`. A successful clone plus a successful
   synthesis with all balances still zero would make it `VERIFIED`.

Implementation: `src/contentops/media/minimax_voice_clone.py` (clone lifecycle only, no
synthesis), prepared by `scripts/prepare_founder_voice_clone.py`, receipts in
`projects/easel-enhanced-golden/receipts/`.

## Transport implication

Voice cloning needs the **documented public API**, because the official CLI has no clone
command. That is consistent with the transport priority already in force: official CLI
first, documented public API for a capability gap, never an undocumented endpoint. The
undocumented balance read would still come only from `BillingGuard`.

For synthesis **with** a cloned voice the question is separate and still open: whether
`mmx speech synthesize --voice <cloned_id>` transports a custom id. That is inspected
from CLI help/schema before any generation, never discovered by generating.
