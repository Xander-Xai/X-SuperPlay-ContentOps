# M4 — MiniMax H3 subscription video: executable plan (Issue #22)

> Planning document. **Nothing here is implemented.** Prepared 2026-10-04 on
> branch `feat/20-minimax-mplan-image`, corrected before PR #25 merged.
> H3 work starts only after #20 merges.
>
> Superseded claims in the previous revision of this file were wrong and have
> been removed: the PAYG blocker, the claim that no official prompt skill
> exists, and the claim that the `mmx` CLI is the video transport. Corrections
> are recorded below rather than quietly edited away.

---

## 1. Billing: PAYG is FORBIDDEN, and H3 is already proven to work on M Plan

### Corrected policy

```
billing_mode      = subscription
allow_payg        = false
allow_credit_pack = false
credential_class  = SUBSCRIPTION
```

**No Founder PAYG approval is required.** The earlier revision of this document
concluded that H3 was unusable because a doc line said "Pay-as-you-go". That
conclusion was wrong, and the error was mine: I read one line of CLI-oriented
documentation as an entitlement ruling for this account.

### Real account evidence (M2.0, `sk-cp` Subscription Key, MiniMax-H3)

| Observation | Value |
|---|---|
| Credential | `sk-cp` Subscription Key |
| Model | `MiniMax-H3` |
| Duration | 4 s |
| Resolution | 768P |
| Ratio | 9:16 |
| Task created | yes |
| Task succeeded | yes |
| weekly quota | 65% → 58% |
| cash balance | 0 → 0 |
| Credit Pack | 0 → 0 |
| voucher | 0 → 0 |
| owed | 0 → 0 |

M Plan usage absorbed the generation. No paid balance moved.

### Product facts

- **M Plan Explore includes H3 video.**
- M Plan supports model selection via API request / tool configuration.
- A Subscription Key spends **M Plan usage first, then Credit Packs**.
- **Account cash balance is charged only by a Pay-as-you-go API Key.**

That last point is the whole reason `allow_payg = false` is sufficient: as long
as the request carries the `sk-cp` key and never a PAYG key, cash is not touched.

### Video billing rule

`BillingGuard.authorize(modality="video")` requires:

- `credential_class == SUBSCRIPTION`
- `weekly_remaining_percent > 0`
- `cash_balance == 0`
- `credit_balance == 0` (Credit Pack)
- `voucher_balance == 0`
- `owed_amount == 0`

and does **not** require the 5-hour window.

### Why Credit Pack must stay at zero

M Plan **falls through to Credit Packs once included quota is exhausted**. So a
non-zero Credit Pack balance does not mean "the user bought credits"; it means
included entitlement has already run out and the next generation would silently
be billed. ContentOps policy forbids that, so a non-zero Credit Pack balance is
`BLOCKED_BILLING_SOURCE_UNCERTAIN` for **every** modality — not only video.

The same four zero-balance checks already apply to speech and image and are
unchanged. Only the video **quota-window** rule is new.

## 2. OFFICIAL_DOC_CONFLICT — recorded, not deleted, and not called "stale"

The official `mmx` H3 guide currently says to use a Pay-as-you-go / Credit API
key and not to use a Token Plan Subscription Key.

That statement is **kept on the record** because deleting it would hide a real
hazard: an operator who follows it would swap in a PAYG key and start paying
cash.

Why it is not the entitlement authority for this account:

1. the CLI guide explicitly discusses **Token Plan**, a different product family;
2. **M Plan is a newer product family** whose Explore tier explicitly includes H3;
3. this actual M Plan Explore `sk-cp` account has **already succeeded with H3**,
   with every paid balance unchanged.

So the CLI guide is **not the entitlement authority** for an M Plan subscription
account. It is **not** labelled stale, because no source here establishes its
publication date or current status — calling it stale would be a claim I
cannot support.

Practical consequence: `mmx` remains useful for auth, status, quota, research and
diagnostics, but its H3 key guidance must never be followed for this account.

## 3. H3 prompt source — verified upstream, not assumed

The earlier revision claimed no official prompt skill existed. That was wrong.

**Canonical source, fetched and read at plan time:**

| Field | Value |
|---|---|
| repository | `MiniMax-AI/MiniMax-H3` (public) |
| default branch | `main` |
| exact `main` commit | `d21241f0a4b3acbb34c97dae47fa417b7065e438` |
| skill | `skills/h3-prompt-writing/SKILL.md` |
| skill blob sha | `b6d9b2839384a588763a9c24315225dd8ce19d56` |
| last commit touching the skill | `a107547fa669c509b8e6363fe18378d46ab3066c` (2026-08-11, "docs(h3-prompt-writing): add tips for better results") |
| authoritative references | `skills/h3-prompt-writing/references/base-en.txt`, `references/ref-en.txt` |
| repo `pushed_at` | 2026-08-15T08:31:17Z |
| `checked_at` | 2026-10-04 |

Re-fetch before implementing. **The repo is not vendored**; ContentOps references
the skill and implements a compiler that follows it.

### The skill's own rules

Workflow, per `SKILL.md`: identify the input mode; for base text/keyframe modes
follow `references/base-en.txt`; for full-reference mode follow
`references/ref-en.txt`; **preserve the exact field names, section order, labels
and timing notation**.

### Base modes: T2VA / I2VA / FL2VA / L2VA

Three core fields, in this order:

```
integrated_multimodal_description
overall_soundscape
non_diegetic_music
```

An alignment instruction precedes them as the **first line**, followed by one
blank line. `T2VA` has none and starts directly with the three fields.

| Mode | Alignment instruction |
|---|---|
| T2VA | none |
| I2VA | `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.` |
| FL2VA | `How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.` |
| L2VA | `How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.` |

`S.SS` is the effective duration to **exactly two decimals**; `N` is the index of
the actual final shot.

Recommended body structures:

- I2VA: first-frame anchor → action onset → continuous development → result
- FL2VA: first-frame state → observable intermediate changes → progressively
  narrowing differences → last-frame state
- L2VA: plausible preceding state → explicit action and transition path →
  gradual convergence in the final shot → last-frame landing

### Full-reference mode: Ref2VA

Six sections, in this exact order:

```
subject_definitions
summary
retention_analysis
detailed_description
overall_soundscape
non_diegetic_music
```

Reference labels: `<Subject N>`, `<Picture N>`, `<Video N>`, `<Audio N>`, kept
consistent across every section.

### Notation the compiler must preserve

- **Shots**: `[Shot 1]` carries no timestamp; later shots use a strictly
  increasing cut time inside the duration, e.g. `[Shot 2] At 00:03.500, ...`
- **Camera motion** is motion type + amplitude + speed, written as a natural
  English action inside the shot, never as stacked labels. Closed vocabulary:
  `Zoom In/Out`, `Push In/Pull Out`, `Pan Left/Right`, `Truck Left/Right`,
  `Tilt Up/Down`, `Pedestal Up/Down`, `Arc Shot`, `Tracking Shot`,
  `Static Shot`, `Shake Slightly/Strongly`, `POV`, `Roll Clockwise/Counterclockwise`;
  amplitude `with small amplitude` / `with large amplitude`;
  speed `at slow speed` / `at fast speed`
- **Speakers**: `(S1)`, `(S2)`, compound `(S1,S2)`; dialogue as
  `<d>[English] ...</d>` verbatim, never translated; voiceover uses the exact
  phrase `says in an off-screen voiceover` followed by a statement that the lips
  remain closed; `<scenetrans>` at cut crossings; `<cutoff>` when speech is
  truncated by the end
- **On-screen text** in English double quotation marks, verbatim
- **`overall_soundscape`**: 1–4 English sentences, one paragraph; `N/A` only when
  the user explicitly requests complete silence
- **`non_diegetic_music`**: 1–3 English sentences; `N/A` when there is none
- Rewrite sections in English; dialogue, lyrics and visible scene text keep
  their original language
- Prefer concrete visual and audio detail over abstract words such as
  "cinematic" or "beautiful"; always match the described total duration to the
  requested length (4–15 s)

## 4. `H3PromptCompiler`

`src/contentops/media/h3_prompt.py`. Provider-generic types in, provider-generic
types out; no vendor vocabulary in its interface.

Input: a `ShotPlan` entry. Output: the compiled prompt plus its parts, so the
fingerprint covers **what was actually sent**.

- emit the alignment instruction first, blank line, then the three core fields in
  official order (or the six Ref2VA sections in official order)
- enforce the 7000-character prompt limit locally, before billing
- `compiled_prompt_sha256` feeds the fingerprint, not the raw intent

### ShotPlan

Provider-shaped business logic must not leak in. Fields:

```
shot_id, purpose, duration, aspect_ratio,
subject, environment, action, camera, dialogue, sound, visual_style,
reference_assets, claim_refs
```

Generated video is allowed **only** when `purpose == "support visual"`. It is
forbidden for evidence, benchmark, UI proof, demo proof, analytics proof,
customer proof and test result, reusing the M3 `AssetRegistry` hard gate. **No
second registry.**

## 5. Transport: the documented public H3 API

**The `mmx` CLI is not the H3 generation transport.** The earlier revision said it
was; that was wrong, and it conflicts with M2.0 evidence.

Reason: the official CLI does **not** reliably expose the required 768P
resolution control. M2.0 measured CLI resolution handling as
insufficient/ignored, while the documented public API with the same `sk-cp`
Subscription Key successfully produced 4 s / 768P / 9:16 H3.

So:

```
ContentOps VideoProvider
    → documented public MiniMax H3 API
```

and **not** ContentOps → `mmx video` CLI for actual generation.

The CLI remains useful for `auth` / `status`, `quota`, research and diagnostics
where appropriate.

Underlying documented endpoints, for reference only — ContentOps owns an HTTP
client for these and does **not** shell out to generate:

```
POST /v2/video_generation
GET  /v2/query/video_generation/{task_id}
```

### One task, one poll, one download

1. create **exactly one** task, persist its reference immediately, before polling
2. poll **that same** task to a terminal state: `succeeded` / `failed` / `cancelled`
3. download **that same** result from the URL that task returned
4. **never create a replacement because polling or downloading failed**

Point 4 is the rule that protects the bill and the explanation. A failed poll is a
transport failure, not a generation failure; answering it with a new task doubles
the spend and destroys the ability to say what was paid for. A task still running
is not a failure and is never retried.

## 6. Credential invariant

Unchanged from M2/M3, restated for HTTP:

```
THE CREDENTIAL AUTHORISED BY BILLINGGUARD
MUST BE
THE CREDENTIAL USED BY THE H3 API REQUEST
```

- `resolve_credential()` once → one `ResolvedCredential`
- the same `sk-cp` value feeds `BillingGuard` **and** the H3 `Authorization` header
- never resolve twice, never fall back to an ambient PAYG key, never switch
  credential after the preflight
- never record the literal value anywhere

## 7. Cost policy

The M2.0 observation: one H3 4 s / 768P test moved weekly quota **65% → 58%**,
an observed delta of **7 percentage points**.

This is **not** a cost formula. The provider exposes only coarse percentage
usage, so no per-second price is derived and none may be persisted as one. Use it
only for conservative test budgeting.

| Model | Supported | Test duration |
|---|---|---|
| `MiniMax-H3` | 4–15 s | **4 s** |
| `MiniMax-H3-Max` | 5–15 s | **5 s** |

No 8 s / 10 s / 15 s test when the minimum proves the behaviour. **Production
duration is not constrained by this testing policy.**

## 8. Attempt records and task privacy

Extend `GenerationAttemptRecord`; do not replace it.

Private runtime-only fields: `task_id`, `task_type`, `state`. The raw task id may
exist only in runtime/private attempt state and must never be committed. Public
and persisted-sanitised fields: `task_created`, salted `task_hash`, `status`.

Once `task_created` is true, a poll or download failure must **not** become
"attempt 2". Attempt 2 means a *new generation* with a changed fingerprint, and
requires a terminal FAILED previous task, a named reason, changed input and an
explicit budget.

## 9. Video receipt

Immutable generation receipt `<asset>.mp4.receipt.json`, same rules as M3: written
once, never rewritten on reuse, reuse appended to `reuse-events.jsonl`.

Fields: provider, product, plan, `billing_mode=subscription`,
`payg_allowed=false`, `credit_pack_allowed=false`, `credential_class`, model,
mode, `compiled_prompt_sha256`, reference asset hashes, requested/actual
duration, requested/actual resolution, requested/actual ratio, `task_created`,
salted task hash, preflight verdict, weekly quota before/after, technical QC,
output SHA-256, attempt, retry reason, `generated=true`,
`evidence_capable=false`, `production_ready=false`,
`human_review=PENDING_FOUNDER_REVIEW`.

## 10. Video technical QC

Measured facts only, in the M3 spirit — never "cinematic", "beautiful" or
"publishable":

container, codec, decodability; duration tolerance; width, height; aspect
tolerance; fps; **audio stream presence**; **black-frame detection**;
**freeze/stall detection**; frame-difference distribution.

### Delivered output differs from requested — the numbers

M2.0 requested 4 s / `768P` / `9:16`. Delivered:

| Property | Requested | Delivered |
|---|---|---|
| duration | 4 s | **4.458 s** |
| resolution | 768P, 9:16 | **768x1344** (0.5714, not 0.5625) |
| codec | — | h264 |
| fps | — | 24 |
| audio | not requested | **AAC present** |

Every one of those is a reason the gates use **tolerance** and not equality:
duration, aspect ratio, and audio-track presence all need an explicit policy
rather than an assumption that the provider returns what was asked.

### Unexpected audio is expected

M2.0 real H3 output contained **AAC audio even though audio was not requested**.
Audio behaviour must therefore be explicit, never incidental.

Composition policy, deterministic and recorded in the receipt and shot decision:

- generated audio `KEEP`
- generated audio `MUTE`
- generated audio `REPLACE`

Default must be fixed and recorded. Silent mixing of generated H3 audio with
MiniMax narration is forbidden.

### Reference fidelity is human work

For I2VA / FL2VA / L2VA / Ref2VA, human review covers reference identity, subject
consistency, motion fidelity, first-frame fidelity, last-frame fidelity and
temporal deformation. Automated checks never approve this.

## 11. Provider family

One provider-generic family over shared infrastructure:

```
SpeechProvider   ImageProvider   VideoProvider
```

Shared: `ResolvedCredential`, `CredentialBinding`, `BillingGuard`,
`GenerationAttemptRecord`, transport helpers, fingerprint conventions, immutable
receipts, reuse-event conventions, provider identity.

`ImageProvider` already exists (`image_contract.py`). `VideoProvider` lands in
#22. Future orchestration may aggregate them through a `MediaProviderRegistry`.

`contract.py` previously claimed that image and video were unimplemented
"on purpose" for #19. That is now wrong and has been corrected: speech and image
are separate provider ABCs sharing infrastructure, not one monolithic class.

## 12. Test plan

`tests/test_minimax_h3.py`. No real H3 request in CI; mocked HTTP / fixture API.

Five prompt modes; field ordering; alignment-instruction placement; `S.SS` two-decimal
format; duration validation (H3 4–15, H3 Max 5–15, integers); input and reference
limits; subscription credential binding; PAYG blocked; weekly-only quota rule;
paid-balance rule including non-zero Credit Pack; **one** task creation; poll same
task; download same task; poll timeout does not recreate; download failure does not
recreate; terminal failure recorded; durable retry; immutable receipt; cache before
billing; secret sanitation; black frame; freeze; audio detection; aspect tolerance;
GENERATED_VIDEO evidence rejection; zero Windows popups.

## 13. Real generation budget

The M2.0 T2VA 4 s smoke **already proves** basic H3 T2VA transport. Do not
regenerate it merely to prove the same thing again.

New real generations exist only for capabilities not yet proven. Reference modes
are expensive: implement I2VA / FL2VA / L2VA / Ref2VA first against fixture and
schema tests, then spend the **minimum** necessary — preferred budget is one
reference-image test, and at most one reference-video test if #22 acceptance
actually requires it, each at provider minimum duration.

Before any task creation, record:

```
TEST_OBJECTIVE, MODEL, DURATION, RESOLUTION, EXPECTED_QUOTA_BUDGET
```

## 14. Definition of done

- [ ] M Plan Subscription preflight proven `SAFE_INCLUDED_PLAN`
- [ ] all paid balances zero, including Credit Pack
- [ ] weekly quota budget approved for the test run
- [ ] exact `sk-cp` credential binding preserved into the H3 request
- [ ] `H3PromptCompiler` covering all five modes, field order verified against the skill
- [ ] `modality="video"` weekly-only rule with tests
- [ ] one-task / poll-same / download-same, proven by test
- [ ] task privacy: raw id never committed, salted hash in the receipt
- [ ] video receipt immutable, reuse-safe
- [ ] video QC: black frame, freeze, audio detection, aspect tolerance
- [ ] GENERATED_VIDEO cannot be evidence
- [ ] smallest new real smoke approved by the test plan, receipt written
- [ ] M2 (85) and M3 (63) suites still green
- [ ] all local gates and exact-head CI green
