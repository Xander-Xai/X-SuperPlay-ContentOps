# MiniMax H3 official reality — verified at M4 implementation time

---
title: MiniMax H3 official reality verification
canonical: false
type: research
status: current
issue: "#22"
milestone: M4
checked_at: "2026-10-05T00:00Z"
---


Sources, all fetched during this milestone rather than recalled:

| What | Where |
|---|---|
| H3 usage guide | `https://platform.minimax.io/docs/guides/video-generation` |
| Create-task API reference | `https://platform.minimax.io/docs/api-reference/video-generation-v2-create` |
| Query-task API reference | `https://platform.minimax.io/docs/api-reference/video-generation-v2-query` |
| Error codes | `https://platform.minimax.io/docs/api-reference/errorcode` |
| Prompt skill repository | `https://github.com/MiniMax-AI/MiniMax-H3` |

An earlier draft cited `https://www.minimax.io/platform/document/guides_video_generation`.
The canonical docset is now `platform.minimax.io/docs/*`, so the path above is used.
`/docs/api-reference/video-generation-t2v` is the **legacy v1** text-to-video API and
is not the H3 endpoint; the H3 surface is the `video-generation-v2-*` group.

## Prompt skill provenance

| Field | Value |
|---|---|
| repository | `MiniMax-AI/MiniMax-H3` (public) |
| default branch | `main` |
| **main commit** | `d21241f0a4b3acbb34c97dae47fa417b7065e438` |
| repo `pushed_at` | `2026-08-15T08:31:17Z` |
| skill path | `skills/h3-prompt-writing/SKILL.md` |
| skill blob SHA | `b6d9b2839384a588763a9c24315225dd8ce19d56` |
| last commit touching skill | `a107547fa669c509b8e6363fe18378d46ab3066c` (2026-08-11) |
| base reference | `references/base-en.txt` blob `40cf586a634d677d6b7107b367cf0ec9621be728` |
| full-reference guide | `references/ref-en.txt` blob `7ae1b2d07d743fd2392258a96449be9e9e322d35` |
| **checked_at** | 2026-10-05 |

The repository is **not vendored**. ContentOps references it and implements a
compiler that follows it.

### Base-mode section order (verified present, in this order)

```
integrated_multimodal_description
overall_soundscape
non_diegetic_music
```

### Ref2VA section order (verified present, monotonically increasing offsets)

```
subject_definitions
summary
retention_analysis
detailed_description
overall_soundscape
non_diegetic_music
```

### Reference label vocabulary (occurrence counts in `ref-en.txt`)

| Label | Mentions |
|---|---|
| `<Subject N>` | 12 |
| `<Picture N>` | 7 |
| `<Video N>` | 11 |
| `<Audio N>` | 15 |

### Alignment templates (verified verbatim in `base-en.txt`)

- **I2VA**: `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.`
- **FL2VA**: `How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.`
- **L2VA**: `How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.`
- **T2VA**: no alignment instruction; begins directly with the three core fields.

`S.SS` is the effective duration to exactly two decimals. `N` is the index of the
actual final shot. Cut syntax verified: `[Shot 2] At 00:03.500, ...` — `[Shot 1]`
carries no timestamp.

### Camera-motion vocabulary (verified)

Motion type: `Zoom In/Out`, `Push In/Pull Out`, `Pan Left/Right`,
`Truck Left/Right`, `Tilt Up/Down`, `Pedestal Up/Down`, `Arc Shot`,
`Tracking Shot`, `Static Shot`, `Shake Slightly/Strongly`, `POV`,
`Roll Clockwise/Counterclockwise`.
Amplitude: `with small amplitude`, `with large amplitude`.
Speed: `at slow speed`, `at fast speed`.

Written as a natural English action inside the shot, never as stacked labels.

### Prompt limit

`SKILL.md`: “Always match the total duration of the description to the requested
video length (4–15 seconds).” The API caps a single `text` item at **7000
characters**.

## API schema — `POST /v2/video_generation`

Server `https://api.minimax.io`, auth `Authorization: Bearer {api_key}`.

Required: `model`, `content`, `resolution`, `duration`. `ratio` is conditionally
required. Response: `{ "task_id": "..." }`.

### Models

| Model ID | Resolution | Duration |
|---|---|---|
| `MiniMax-H3` | `768P`, `2K` | **4–15 s**, integer |
| `MiniMax-H3-Max` | `480P`, `768P` (**no `2K`**, defaults `768P`) | **5–15 s**, integer |

The `resolution` enum is `480P | 768P | 2K`; availability is model-dependent.

### Duration

Integer, required. `MiniMax-H3` accepts 4–15. `MiniMax-H3-Max` accepts 5–15 and
**explicitly does not support 4 seconds**.

### Ratio

Enum: `adaptive`, `21:9`, `16:9`, `4:3`, `1:1`, `3:4`, `9:16`.

| Mode | Ratio rule |
|---|---|
| t2va (text only) | **required, and cannot be `adaptive`** |
| i2va (`first_frame` / `last_frame`) | always `adaptive`; other values are accepted but **ignored** |
| r2va (reference roles) | optional, defaults to `adaptive` |

### content[]

Types: `text`, `image_url`, `video_url`, `audio_url`. Roles: `first_frame`,
`last_frame`, `reference_image`, `reference_video`, `reference_audio`.

Exactly one non-empty `text` item is required in every request; otherwise a
`400 bad_request_error` is returned (`2013`).

**Mutually exclusive**: `reference_image` / `reference_video` / `reference_audio`
and `first_frame` / `last_frame` cannot be mixed in one request.

URL forms: public URL, `mm_file://{file_id}`, or a `data:` URI. Request body
≤ 64 MB; Base64 inflates by roughly 33 %, so a URL is preferred.

### Input limits

| Input | Limits |
|---|---|
| first frame | ≤ 1 |
| last frame | ≤ 1 |
| reference images | ≤ 9; JPG/JPEG/PNG/WEBP/HEIC/HEIF; ≤ 30 MB each; 256–5760 px; aspect 0.4–2.5 |
| reference videos | ≤ 3; MP4/MOV; H.264/H.265, audio AAC/MP3; ≤ 50 MB each; per clip 2–15 s, total ≤ 15 s; 256–5760 px; aspect 0.4–2.5; 23.976–60 fps |
| reference audio | ≤ 3; WAV/MP3; ≤ 15 MB each; per clip 2–15 s, total ≤ 15 s |
| mixed total | ≤ 12 files |
| prompt | ≤ 7000 characters |

### extra (H3-Max only)

`extra.prompt_expansion_mode`: `disabled` | `balanced` | `quality`, default
`balanced`. Undeclared fields are rejected, so ContentOps must not invent keys.

### Poll — `GET /v2/query/video_generation/{task_id}`

```json
{
  "task": {
    "id": "424010985738629",
    "model": "MiniMax-H3",
    "status": "succeeded",
    "created_at": 1785125529,
    "updated_at": 1785125946,
    "content": { "url": "https://.../output.mp4" },
    "resolution": "2K",
    "duration": 5,
    "usage": { "total_seconds": 5, "input_seconds": 0, "output_seconds": 5, "input_image_count": 0 },
    "ratio": "16:9",
    "task_type": "generation",
    "modality": "video"
  }
}
```

The download URL is returned **directly** in `content.url`; there is no
`file_id` exchange on this path.

Recommended poll interval: **10 s**.

### States

Non-terminal: `queued`, `running`.
Terminal: `succeeded`, `failed`, `cancelled`.
`task_type` values seen in the docs: `generation`, `h3_context_ir`,
`regeneration`.

Any state outside this set is **unknown**, and ContentOps fails closed
operationally rather than creating another task.

### Error codes

| HTTP | Meaning |
|---|---|
| 400 | invalid params, e.g. no non-empty `text` item (`2013`) |
| 401 | `authorized_error` — missing/incorrect `Authorization` |
| 402 | `insufficient_balance_error` |
| 422 | `unprocessable_entity_error` — sensitive content (`1026`) |
| 429 | `rate_limit_error` |
| 500 | `server_error` |
| 529 | `overloaded_error` |

## OFFICIAL_DOC_CONFLICT — unchanged and still not the entitlement authority

Both the guide and the create-API page still say: *"To use MiniMax H3 or MiniMax
H3 Max, please select the Pay-as-you-go API."*

That line is **kept on the record**. It addresses the Token Plan era; M Plan is a
newer product family whose Explore tier includes H3; and this account has already
succeeded with H3 using an `sk-cp` Subscription Key with every paid balance
unchanged. It is **not** labelled stale, because nothing establishes its
publication date or status.

Practical rule: an operator must never follow that line for this account, because
swapping in a PAYG key is exactly how cash would start being charged.

## Prior real evidence (M2.0) — do not reproduce

| Property | Value |
|---|---|
| Model | `MiniMax-H3` |
| Mode | T2VA |
| Duration | 4 s |
| Resolution | 768P |
| Ratio | 9:16 |
| Outcome | task created, task succeeded |
| weekly quota | 65% → 58% |
| cash / Credit Pack / voucher / owed | 0 → 0 for all four |

One 4 s / 768P job moved weekly quota by **7 percentage points**. That is an
observed delta for conservative test budgeting, **not** a price formula: no
per-second, per-clip or credit rate is derived from a percentage.

Transport for that run was the **documented public API**, not the CLI.

## Differences from the M3 planning snapshot

| Item | M3 snapshot | Verified now |
|---|---|---|
| `resolution` enum | `768P`, `2K` | `480P`, `768P`, `2K`; H3-Max has **no `2K`** and defaults to `768P` |
| `extra` object | not recorded | exists, H3-Max only, `prompt_expansion_mode` |
| image reference limit | ≤ 9 | ≤ 9 (confirmed) |
| video reference fps | not recorded | 23.976–60 |
| reference URL forms | not recorded | public URL, `mm_file://`, `data:` URI |
| i2va ratio behaviour | “always adaptive” | confirmed; other values accepted but **ignored** |
| mutual exclusion | not recorded | reference roles and frame roles cannot mix |

Nothing found contradicts the M3 snapshot. The additions are recorded above and
are enforced locally before any billing read.
