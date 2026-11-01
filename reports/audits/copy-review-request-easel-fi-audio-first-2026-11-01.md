# Copy review request — `easel-fi-audio-first` (25 s motion sample)

Date: 2026-11-01

**This is a request for review, not a review.** No decision has been made, no `script-review.json` exists, and nothing here may be treated as approval.

`copy_sha256`: `a8ad8d7cc0384d78a1b6feea0a8bc0fe98ecea4a2968639104984114fba23915`

Approving this exact fingerprint would let the compose stage run. Any edit to the narration, the beats, the claim map, the cut plan or the declared asset digests produces a different fingerprint and requires a new review.

**What the fingerprint binds.** Source inputs: `script/master.md`, `script/*.srt`, `script/lines.json`, `script/script.json`, `script/claims.json`, `script/claim-map.json`, `script/assets.json`, `script/cut-plan.json`, `motion/timeline.json`, and a field subset of `script/storyboard.json`. Not bound, because the pipeline writes them: `script/narration.txt`, `receipts/voice-lines.json`, and the storyboard's own `narration` / `subtitle` / `runtime` keys. Hashing those would expire the review on every rebuild.

**Review status: NOT APPROVED.** This sample is not approved and is not scheduled for approval. Three statements in the copy are recorded below as corrections owed before any approval.


## The copy, as scripted

### P-01-HOOK  (C-FI-01)

> 口播四十四秒，画面不能停四十四秒。

*semantic progress:* the window and the picture are two different lengths

- view `A-MOTION-LEN` 00:00.000-00:02.500 — the narration length draws to 44 s
- view `A-MOTION-LEN` 00:02.500-00:05.000 — 22 view cells pop in under it

### P-02-TRADEOFF  (C-FI-02)

> 画面按语义换，不按口播时长。

*semantic progress:* the tradeoff moves from duration to view changes

- view `A-MOTION-SWAP` 00:00.000-00:02.500 — the placement and its first view
- view `A-MOTION-SWAP` 00:02.500-00:05.000 — V2 and V3 take over by meaning

### P-03-ARCH  (C-FI-03)

> 一个口播窗口，拆成多个取证视图。

*semantic progress:* the placement and its views

- view `A-MOTION-FLOW` 00:00.000-00:02.500 — placement, views and the gate assemble
- view `A-MOTION-FLOW` 00:02.500-00:05.000 — the packet travels the chain

### P-04-ROOTCAUSE  (C-FI-04)

> 旧门禁放过了静态停留，现在换成实测。

*semantic progress:* the old gate trusted a declaration

- view `A-MOTION-CODE` 00:00.000-00:02.500 — the code panel reveals
- view `A-MOTION-CODE` 00:02.500-00:05.000 — the sweep lands on the measured check

### P-05-VERIFY  (C-FI-05)

> 重建后最长冻结一点八秒，质检通过。

*semantic progress:* the measured result and the verdict

- view `A-MOTION-METRIC` 00:00.000-00:02.500 — 1.80 s counts up against the limit
- view `A-MOTION-RESULT` 00:00.000-00:02.500 — the same numbers as a chain

## Declared assets

| id | kind | path | sha256 |
|---|---|---|---|
| A-MOTION-CODE | motion | `project://work/motion/code-sweep.mp4` | `ec992e64a058b96a…` |
| A-MOTION-FLOW | motion | `project://work/motion/arch-flow.mp4` | `b42ed2194fb999d5…` |
| A-MOTION-LEN | motion | `project://work/motion/narration-bar.mp4` | `ee5f3aba2f07de7c…` |
| A-MOTION-METRIC | motion | `project://work/motion/metric-count.mp4` | `9670b1c5180246e7…` |
| A-MOTION-RESULT | motion | `project://work/motion/result-chain.mp4` | `bc57bae456d260bd…` |
| A-MOTION-SWAP | motion | `project://work/motion/view-swap.mp4` | `341898cfa2bcc1e7…` |

## What is **not** in this package

- No caption file in `script/`: this project's captions are produced by the build, so a reviewer is approving the spoken text, not a burned SRT.

- No storyboard: it is generated from the cut plan at compose time.

- No media binaries: they are gitignored and bound by digest instead.

## Known limitations a reviewer should weigh

- `project.yaml` records `status: AUDIO_FIRST_P0` and a `design_deviation` note: this is a 20–30 s P0 loop, not a finished episode.

- The sample is a technique proof about the video-quality defect itself, not an Easel episode.

- Technical QC on the 2026-10-28 build was `PASS` (18 checks). That is not a review of the words.


## Corrections owed before any approval

Recorded from the Owner's review on 2026-11-01. These do not invalidate the
motion work; they make the copy unapprovable until resolved.

| Beat | Finding | What is needed |
|---|---|---|
| `P-01-HOOK` — 「口播四十四秒，画面不能停四十四秒。」 | a 44 s figure appears in a 25 s sample with no statement of what 44 s measures | name the object the 44 s refers to |
| `P-04-ROOTCAUSE` — 「旧门禁放过了静态停留，现在换成实测。」 | the old-gate defect is confirmed, but this does not establish that a production dynamic-quality gate is shipped | separate the capability that exists from the gate that is still planned |
| `P-05-RESULT` — 「重建后最长冻结一点八秒，质检通过。」 | the linked `easel-1024-proof` QC receipt could not be read from the current remote, and the figure is not this 25 s sample's measurement | verify the original receipt and state which object was measured |

Until these are resolved, the state stays `BLOCKED_COPY_REVIEW`. No approval was
recorded, and none should be inferred from this document.
