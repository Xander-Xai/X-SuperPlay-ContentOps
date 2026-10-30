# Four X Tutorial References — Editorial & Safety Audit (2026-10-25)

**Purpose:** User-provided exemplars are research inputs, **not instructions to copy, scrape, rehost or execute**. Author quotes, screenshots, audience metrics, performance and earning claims remain attributed. Full original URLs below. Inspect platform rules and current official docs before promoting or running anything.

## Audited sources

| Source, original publication | What the article actually teaches | Useful editorial pattern | Evidence / risk review | Adoption |
|---|---|---|---|---|
| [@noahduck283 — StackChan beginner-to-advanced](https://x.com/noahduck283/status/2113948562354811274), Oct 24 2026, ~17-min X Article | Demonstrates desk voice assistant with StackChan, local gateway routing to Claude Code/Grok, setup, screenshots, checklists and seven common pitfalls | **Outcome demo → actual architecture → exact prerequisites → steps/checks → failure branches → real-life usage**. Give a reader specific verification/rollback after each stage. | Author's voice-response speeds and “no extra API money” are individual claims, not guaranteed: hardware, subscriptions, networking, maintenance and any external API can cost money. Review installer before running and keep sensitive files/agents read-only until explicitly authorized. [Gateway primary repo](https://github.com/justhalfbit/xiaozhi-hub-server) exists; untested locally. | **PATTERN_ADOPTED**; engineering implementation `REPRO_PENDING` |
| [@HytidelLegend — 2026 Xianyu side-business](https://x.com/HytidelLegend/status/2086034016281747894), Aug 8 2026, ~23-min Article | Covers shop setup, listing/search titles, pictures, descriptions, supply/shipping, daily orders, customer service, Feishu tables, monetization context | **End-to-end operations** from setup → acquire → deliver → QA → after-sales → record unit economics. Distinguish AI-enhanced steps from generic ecommerce tutorials. | Includes recommendations for fabricated SKUs, misleading profile/claims, copied material and manipulated transactions (“补单”). **REJECT** those tactics; no faked engagement/orders, deceptive pricing, unlawful resale or identity claims. Fee and profit percentages are time-/store-specific, not validated. AI role in article is secondary. | **STRUCTURE_ONLY / TOPIC_HOLD**; only honest AI workflow versions considered |
| [@AI_Jasonyu — X creator payout guide](https://x.com/AI_Jasonyu/status/2022954721548661130), Feb 15 2026, ~15-min Article | Step-by-step old creator-revenue eligibility, verification, Stripe/Wise, tax, warnings and FAQ | **Prerequisites → account eligibility → annotated screenshots → exception resolution → FAQ → maintaining a change log** for regulated platform systems | **CRITICAL STALE**: X [official Creator Revenue Sharing page](https://help.x.com/en/using-x/creator-revenue-sharing) says applications stopped **Aug 7 2026**, old scheme ended **Sept 7 2026**, replaced by [Original Content Rewards](https://help.x.com/en/using-x/original-content-rewards). Do **not** publish old thresholds as current; **do not adopt instructions to misstate address/income/jurisdiction/tax status or bypass identity/payment checks**. A commenter's tax treaty percentage and 95% success claim aren't proof or individual tax advice. | **FORMAT_ONLY / OLD PROCESS REJECTED**; any new guide starts with current X, Stripe, tax authority primary sources |
| [@Zesee — solo Douyin content and revenue retrospective](https://x.com/Zesee/status/2081295201486663718), Jul 26 2026, ~5-min Article | Author describes >50 videos in ~3 months, 2–3 hours a day, >20 ad projects and >¥30k gross earnings, positioning, choosing trends, Codex/Remotion vs Jianying, pre-publication review, paid traffic | **Specific first-person operating context → actual production pipeline → tool selection by footage type → publish QA → measured iteration → sustainability**. [dbskill](https://github.com/dontbesilent2025/dbskill), [ai-topic-scout](https://github.com/Jingyi-Wu-Richael/ai-topic-scout), [douyin-rule-check](https://github.com/Jingyi-Wu-Richael/douyin-rule-check), [rachel-digital-human-production](https://github.com/Jingyi-Wu-Richael/rachel-digital-human-production) are inspectable source repos. | Earnings/ad counts, follower costs (<¥1) and appearance effects are **author-reported anecdotes**, not audited net profit, causal effectiveness, universal prices or user results. dbskill README shows **CC BY-NC 4.0**; commercial adoption/republication requires rights review. Tool READMEs are not independent benchmark evidence. | **WORKFLOW_ADOPTED / MONEY_CLAIMS_UNVERIFIED** |

**Observation:** Source dates vary substantially (Feb/Aug/Jul/Oct 2026); none of the older posts should be relabeled a past-72-hour news item. The newer voice tutorial is also **not** proof of zero additional cost or safe file-edit permissions.

## What to learn from all four, WITHOUT copying

**Step 0: Show the destination.** Screenshot/capture actual outcome **from a tested run** or clearly label a conceptual demonstration; one precise reader-facing result, not generic “install AI to make money.”

**Step 1: Name the job and owner.** Who is doing what repetitive task, what input/output, what time/error/cost/revenue baseline? If no meaningful AI step and no path to measurable value, route to `general_business_reference_only`, **not** to AI tutorial publishing.

**Step 2: Source full primary implementation.** README plus the *specific* docs/example/source files, current version and license. Popular author's link is a discovery clue, not a replacement for vendor documentation.

**Step 3: Describe an executable learning journey.** Requirements (device/account/API permissions/payment), **full** beginning-to-end operations, checkpoint screenshot or command + actual tested status, 3 common failures, safe recovery and sensible budget.

**Step 4: Calculate the business result honestly.** For efficiency: same sample before/after and human verification time, failure cost, operation/hosting. For monetization: buyer, offer/deliverable, acquisition channel, unit economics, net margin assumptions, customer consent, price experiment. Personal creator revenue claim may be included only as **attributed case**, never sold as a guaranteed return.

**Step 5: Publish two connected artifacts.** Full original 8–15-section guide (if broad end-to-end) with real public accessible URL **and** original English X post or max 3 Thread posts with a topic-specific **real PNG/JPG + ALT**. No copied reference images, false “full guide here” linking to private repository, or visuals implying an untested outcome.

**Step 6: Iterate from real feedback.** Failure fixes, version drift, reader completion rate, actual saving/revenue evidence, platform compliance.

## Specific repo-driven tutorial ideas to research next (NONE of these tested here)

| Candidate | Primary repository | Reader's work result | Verification / limits | Gate |
|---|---|---|---|---|
| AI-assisted creator topic research | [ai-topic-scout](https://github.com/Jingyi-Wu-Richael/ai-topic-scout) | Weekly shortlist with original source/date, usefulness and content angle | Compare minutes per verified idea vs manual and hallucination rate; check license and use case | `RESEARCH` |
| AI video production with permissions | [rachel-digital-human-production](https://github.com/Jingyi-Wu-Richael/rachel-digital-human-production) | 15s preview, human review, full video only after approval | API costs, likeness/voice authorization, safe tokens, quality and time logged | `RESEARCH` |
| Creator content compliance precheck | [douyin-rule-check](https://github.com/Jingyi-Wu-Richael/douyin-rule-check) | Script/thumbnail pre-publish check and issue list | Platform-specific; compare reviewed false positive/negative, current official rules | `RESEARCH` |
| Voice-controlled local AI work | [xiaozhi-hub-server](https://github.com/justhalfbit/xiaozhi-hub-server) | Read-only controlled action on approved sample files | Hardware, gateway security, app auth, cost, actual latency; **explicit permission before file writes** | `REPRO_PENDING` |
| Compliant AI service on Xianyu | [Activepieces](https://github.com/activepieces/activepieces) + first-party terms | Validated document or customer-service workflow with human approval, honest listing | License, platform permitted delivery, real customer consent and invoicing | `HOLD_UNTIL_CUSTOMER_CASE` |
| Monetization eligibility checker | [X Original Content Rewards](https://help.x.com/en/using-x/original-content-rewards) | Verify current eligibility in user's own account and note exact region/legal rules | No account spoofing or tax workarounds; never use retired program's steps | `OFFICIAL_POLICY_REVIEW_ONLY` |

## Why our prior tutorial work missed the mark

The toy causal mask was **correct and tested**, but it was only a micro-experiment, not an end-to-end tutorial teaching how to learn LLMs from GitHub. The revised 13-part guide improved breadth. These four references reveal another missing dimension: **job-to-be-done and real economic value are not yet a hard gate**. Our future Build & Learn must combine credible technology, executable reader outcome and measurable work/commercial result. A tutorial doesn't qualify merely by being long, popular or attractive.

**Source strength tiers:** `official_policy` / `upstream_code_or_docs` / `reproduced_with_logs` / `author_anecdote` / `unverified_or_stale`. Keep **content style lessons** distinct from accepting creators' factual, financial or compliance advice.

No reference X images, copyrighted full text, customer/private data, keys or private platform logs have been copied into this repository.
