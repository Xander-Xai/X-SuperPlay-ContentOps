# Narration v3 diagnosis — read-only review of PR #44/#45 artifacts

Date: 2026-10-14 · Issue: #34 · Status: **read-only** (no code changed by this document)

The Founder's listening verdict on the v2 round: tests pass, but the voice still
sounds mechanical and the emotion/rhythm do not follow the content. This document
separates what the committed artifacts can *prove* from what only listening can
settle, and maps each finding to a v3 countermeasure (D/E/F).

## A. Code-provable findings

### A1. The spoken script is the original with punctuation, not a creator script

Measured over `projects/easel-enhanced-golden/script/narration-spoken.json` vs
`projects/easel-review/script/narration.txt`:

| Measure | Value |
|---|---|
| Character-level similarity (spoken vs original) | **0.969** |
| Segments byte-identical to a single original paragraph | S01, S07 (ratio 1.000); S02 0.964, S03 0.977, S06 0.963 |
| Segments that are splits of one paragraph | S04+S05 split paragraph 4 |
| Narrative order | original order kept; conclusion appears only at the end |
| Added connectives | one ("而是" in S03); no hook, no callback, no value framing |

So "口播稿" v2 was a re-punctuated transcript of the written text. It kept every
fact (that was its job) but brought none of the spoken-register changes the
creator stage is supposed to bring: no conclusion-first hook, no listener
question, no de-jargoned phrasing.

### A2. `calm` was mechanically the majority emotion — 71%

`c_emotion` across the seven segments: `calm` on S01, S03, S05, S06, S07;
auto on S02, S04 only. That is **5 of 7 segments (71%)**, and the two auto units
are exactly the two carrying numbers. The platform's documented auto-detection
was bypassed for the segments where delivery matters most (the hook, the turn,
the conclusion) and replaced with the flattest documented value. Root cause:
the v2 experiment treated `calm` as a safe default rather than a directed
choice, and no rule forbade a majority default.

### A3. Pauses are fixed values applied mechanically

12 `<#x#>` markers across 7 segments, using only two durations: **0.3 s × 8 and
0.4 s × 4**. Marker count per segment 1–3, placed at clause ends with no
variation by intent (a reveal, a list boundary and a list closure all got the
same 0.3 s). The B arm inherited the identical pattern.

### A4. The C arm sliced at paragraph boundaries; joins are audibly longer

C generated each paragraph as its own provider request (3 requests in the
sample; the full script would be 7). Each request is context-free by API
design, so prosody restarts at every segment boundary. Measured in the receipt:

| | Value |
|---|---|
| Join silences (C) | 0.84 s and 0.75 s at the two boundaries |
| Internal sentence pauses (C) | 0.41–0.65 s |
| A single-sentence-only A excerpt | 0.4–0.6 s sentence pauses, no paragraph structure |

The joins are therefore *longer* than any sentence pause — a structural tell in
the audio, on top of the prosody reset.

### A5. Why the test suite cannot see any of this

| Test family | What it asserts | Why naturalness is invisible to it |
|---|---|---|
| `test_spoken_script` | digests, digits, protected phrases, marker syntax, roles | syntactic invariants only; a flat script and a lively script pass identically |
| `test_t2a_segments` | fingerprints, cache, joins, budget arithmetic | the join is verified as *sample-exact*, which says nothing about how it sounds |
| `test_ab_sample_policy` + receipts | credential binding, plan-only billing, budgets | money, not delivery |
| ASR backcheck | missing/mangled tokens | by design a DETECTOR; can never approve quality (its own docstring says so) |
| `technical_qc` | loudness, clipping, silence/pauses presence | measures levels, not prosody or intent |

The v2 round explicitly wrote "technical QC does not replace listening" into
every receipt; the Founder listened, and the verdict is what the tests could
not contradict. Passing CI was necessary and insufficient — exactly as stated.

### A6. What the artifacts deliberately do NOT show

The receipts contain no claim that the audio is natural or approved:
`human_review: PENDING_FOUNDER_REVIEW`, `production_ready: false` in every v2
receipt. The failure is a *quality* verdict on an honestly-pending artifact,
not a claim that turned out to be false.

## B. Listening-dependent questions (cannot be decided from code)

1. **Timbre vs delivery.** B (auto emotion, single request) was heard as
   mechanical too. If the new copy + no fixed pauses still sounds mechanical on
   the cloned voice, the remaining variable is the voice's own timbre; if the
   preset-voice arm sounds natural, the timbre of the clone is implicated.
2. **How much emotion is too much.** Whether a documented explicit emotion on
   the turn ("surprised") reads as intended or as overacting — only ears can
   say.
3. **Join perception.** Whether the C-style joins read as "resets"; the numbers
   show the lengths, not the perception.
4. **Voice similarity.** Whether `founder_primary_v1` sounds like the Founder
   enough to keep, independent of naturalness.

## C. v3 countermeasures (mapped to phases)

| Finding | Countermeasure |
|---|---|
| A1 written register | **CreatorScriptEditor**: conclusion-first hook, listener questions, de-jargoned clauses, value framing, natural ending; facts/versions/counts/conclusions mapped and checked |
| A2/A3 fixed calm + fixed pauses | **NarrationDirector**: per-unit intent metadata; auto-emotion default; explicit emotion only with justification, `calm` can never be a majority; pause durations 0.2–0.5 s by intent, capped per unit |
| A4 paragraph slicing | Director **synthesis groups** by narrative intent (fewer requests), single-unit groups only when a justified control differs |
| B questions 1–4 | **D** new copy + cloned voice + auto; **E** same + director control; **F** same + subscription-confirmed preset voice — a 20 s hidden-label listening set |

Budget and boundaries for the v3 run: M Plan Subscription Key only (existing
BillingGuard + before/after reads), hard caps (`--budget-chars`/`--budget-asr-calls`),
~20 s sample, **no re-clone, no top-up, no publish, no full-narration run**.
Sign-off stays with the Founder: hidden-label listening, six criteria, failure
positions recorded in `listening-review-v3.md`.
