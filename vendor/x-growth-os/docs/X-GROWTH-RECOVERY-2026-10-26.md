# X Growth Recovery V2 — 2026-10-26

> Status: **active 14-day recovery experiment proposal**, pending owner's review and real X analytics. Applies to this repo's English X V0 workflow. It supersedes daily quantity targets and topic-per-day rotation in older docs. It does **not** claim the algorithm caused lost followers, claim measured lift, or authorize auto-posting.

## 0. Case: what is verified versus missing

**Confirmed by owner:** three posts from 2026-10-26 were manually published and recent follower count declined. Topics: webapp-testing lead capture; XLSX formula range; ComfyUI API JSON. The exact public X status URLs, times, per-post analytics and follower time series are **missing**. The repo's `templates/posts.csv` still lists only 2026-10-25 drafts; `templates/x-metric-snapshots.csv` contains headers only.

**Editorial inspection, not causal proof:** all three posts are source-based, generic failure warnings with a similar structure (risk → tool name → checklist → official link); their audience jobs vary (web QA / spreadsheet finance / image generation API); visual illustrations are source-consistent but not a logged demonstration. There is no evidence that posting three times in one day *caused* lost followers. Other explanations include previous follower quality, churn unrelated to these posts, age/language mix, account status and broader distribution changes.

**Initial judgment:** current bottleneck is audience promise + firsthand proof + distribution learning + missing measurement, not an insufficient number of AI-written drafts. Self-awarded 26/30 editorial scores are not user outcomes and cannot validate performance.

### Source-based constraints (checked 2026-10-26)
- X's published For You pipeline retrieves in-network and out-of-network candidates and predicts viewer-specific actions, including positive and negative signals; public source code is **not** a guarantee of production weights or a recipe to game feed ranking: https://github.com/xai-org/x-algorithm
- X Help's recommendations explanation: https://help.x.com/en/rules-and-policies/recommendations
- X Help's view count may include repeat views: https://help.x.com/en/using-x/view-counts
- X automation and authenticity prohibit unsolicited automated engagement and duplicative posting: https://help.x.com/en/rules-and-policies/x-automation and https://help.x.com/en/rules-and-policies/authenticity
- A news report dated 2026-10-20 describes X's stated interest in predicted reading time and read completion; effect sizes or product availability for this particular account are not verified: https://www.tomsguide.com/ai/elon-musk-just-changed-xs-algorithm-heres-what-could-start-showing-up-in-your-feed

### Native reach-limit verification (not a generic "shadowban" diagnosis)
When current reach looks abnormally low, first inspect X's official [Under the Hood](https://x.com/i/under_the_hood) transparency report **if the logged-in account is eligible and the feature is available**. The pilot shows historical account/post labels that can affect visibility (typically prior-month aggregate data), **not a live ranking score or proof that a specific 2026-10-26 post was suppressed**. If unavailable, record `not_available` rather than `clean`. Keep access, report period and sanitized label summary in the weekly review; do not upload credentials, raw private exports or other users' information to the public repo. X first-party explanation: https://help.x.com/en/business-and-advertising/brand-safety/products-that-protect . Also inspect visible account notices and the X Help reach-limits overview: https://help.x.com/en/rules-and-policies/x-reach-limited .

## 1. Immediate guardrails (next 14 days)

- **No quota-driven triple-post days.** Experimental operating ceiling: **3–4 original posts/week/account**, usually ≤1 original/day, rather than daily mandatory or 25–30/month. This is a workload and confounder control, **not** an asserted X algorithm optimum.
- **One account → one audience promise.** Before selecting topics, write the actual account's handle, current bio/pinned post, and whether it is Explorer or Builder. For recovery choose **English-speaking indie AI builders/freelancers shipping useful automations** as a *test ICP* only if it matches the existing account. Do not silently blend Explorer and Builder account mandates. A separate account needs a separate baseline and experiment.
- **Primary lane (2/3 of recovery posts):** real workflow → pain → artifacts/benchmark/failed step → reproduction/decision. **Secondary lane (1/3):** independently analyzed relevant tool update/teardown anchored to *the same buyer/job*. Defer tangential Excel, ComfyUI, LLM theory, generic GitHub star lists unless they serve the same audience or go to the right account.
- **At least one public/permission-cleared firsthand artifact for a post claiming practical results:** code snippet, reproducible command, consented anonymized before/after comparison, permitted screenshot, trace/log with identifiers removed, or live demo. No firsthand artifact? Post can be labeled **SOURCE_ANALYSIS**, but must contain an independent mechanism/counterexample and must **not** say "I tested".
- **Every X post still has one actual topical 16:9 PNG/JPG + English ALT**, per the established owner media gate. Prefer genuine annotated code/output to recurring infographic templates; a conceptual illustration must be labeled conceptual, not performance evidence. No cosmetic fabricated UI.
- **Never mandate source URL inside each 280-char body:** Keep claims traceable in the post record, include link in body when needed for context or verification; otherwise optionally provide the source in one natural, relevant author follow-up (human/manual). There is **no proven universal external-link penalty**; do not use a hidden link trick.
- **Community:** 10–15 minutes per active day reading and *manually* contributing substance to a few relevant conversations; address genuine questions on own posts. No automated likes, follow/unfollow, reply bot, coordinated interactions, scripted browser actions, or mechanical quotas.
- **Stop publishing when the proposed value is generic**, audience mismatch is unresolved, privacy/license unchecked, or the creator cannot substantiate claims. No deleting/reposting low-performing posts as a growth tactic.

## 2. New editorial sequence — value before polish

`AUDIENCE JOB → ORIGINAL EVIDENCE / FIRSTHAND EXPERIMENT → OBSERVABLE RESULT OR HONEST LIMIT → NON-OBVIOUS LESSON → ONE ACTION → HUMAN REVIEW → POST + IMAGE → URL → SNAPSHOTS → DECISION`

**Hook rule:** One concrete reader problem or result within the first `160 characters. Not automatically "AI can... but..." or "[Brand]'s skill does X". Name the reader/job in the post context. Avoid broad claims like "10x", verified revenue or invented client names.

**Body content:** One distinct original insight. If a reader removes the vendor name and this reads like generic advice, **reject**. A full 2–3-post Thread is allowed *only if* a runnable example/mini-reproduction needs it; not to increase volume.

**Proof ladder for the draft:**
- `P0` primary source read only (cite what source *says*, not what creator achieved).
- `P1` locally run example with exact version, minimal sanitized input/output, log/command and failure modes.
- `P2` same-task baseline vs changed workflow, including human review, errors, cost, and repeatability.
- `P3` qualified external feedback / legitimate buyer pilot with permissions and traceable outcomes. This is not automatic paid demand.

**One-angle content card requires:** account/ICP, source/proof grade, one-sentence falsifiable thesis, why follower would care, exact unique artifact URL/path, format, publication status/URL, and *one* current experiment variable. Editorial quality rubric is advisory; a perfect assistant-awarded score is not evidence.

## 3. Recovery experiment calendar (owner controls publication)

- **Day 0–2 / Audit:** Collect 3 real 2026-10-26 post URLs, actual publish timestamps and T+24h/72h per-post native metrics when reachable; obtain account-level daily follower counts from native analytics or owner logs. Audit bio, pinned post, audience-language fit, account notices/eligibility. Import preceding 10–20 real posts if available. No synthetic rows or fabricated impressions. If fewer than 10 comparable posts, mark `cold_start=true`.
- **Day 3–7 / Experiment A:** Publish 2 posts within one chosen ICP: one original work proof / annotated output; one comparable source analysis. Preserve visual style, approximate posting window, CTA and topic cluster as much as possible. Log engagement and qualified replies. If only 2 samples, verdict `INCONCLUSIVE`.
- **Day 8–14 / Experiment B:** Publish 2 posts within same ICP focusing on a *single* next variable selected from pilot evidence, e.g. hook framing (problem/result) while holding artifact and complexity similar. Keep platform reality in view; this is an **observational micro-test**, not a randomized A/B guarantee.
- **Community check:** Respond manually to meaningful replies and speak with people in the same job niche; capture anonymous problem themes, not unsolicited follower solicitation.
- **14-day review:** Continue only the theme with stronger qualified signal and acceptable time cost; repackage high-signal/low-reach posts; retire high-cost repeated generic templates; do not promise follower recovery by a date.

## 4. Metrics and diagnostic decision tree

Keep *per-post* analytics and *account-level* followers separate. X views are not unique readers. Snapshot **same post ages** (`T+2H / T+24H / T+72H / T+7D`), only if actually observed. Note analytics source and data coverage; `null ≠ 0`.

Compare medians across the **same account, same format, same age window, organic only**. Baseline: ideally ≥10 historical posts; <10 is directional only, never a confident winner. For changes, mark unknown if permissions prevent collection.

| Finding | Interpretation to test | Action |
|---|---|---|
| Impressions down but clicks/qualified feedback stable | distribution or eligibility vs topical demand not yet separated | review native account notices, profile, source quality and comparable historical windows; don't assert shadowban |
| Impressions stable but profile visits low | audience not motivated to learn who wrote it | test subject-specific evidence, stronger personal insight, relevant CTA |
| Profile visits present but follows weak | bio/pinned promise may not match post | align pinned proof, profile bio, recurring series; don't impute follows per post |
| Likes but few relevant replies / artifact requests | lightweight appreciation rather than intended value | add reproducible result or genuinely controversial tradeoff; **not** engagement bait |
| High qualified signals but low reach | valuable niche content with weak packaging | improve first sentence/visual, keep same topic |
| Account follower net down with unknown post attribution | cannot infer which post caused it | compare daily account-level net changes with longer history; avoid causal claim |
| Duplicate-like posts, account notices, hidden content | policy / quality risk | manual X Help and native account diagnostics, follow official appeal route if needed |

**Metrics:**
- `interaction_rate=(likes+reposts+replies+bookmarks)/impressions` only when all component counts genuinely available and denominator >0; otherwise mark partial, don't silently treat unknown as 0.
- `profile_visit_rate=profile_clicks/impressions` when numerator is observed and denominator >0.
- `qualified_signal_rate=unique_relevant_questions_or_requests/impressions` when manually coded and both numerator+denominator are observed, optional per 1k views for readability.
- `follow_conversion=post_attributed_follows/profile_visits` **only if X explicitly reports post-attributed follows**. Otherwise UNKNOWN.
- `account_net_follows=end_followers-start_followers` **on account snapshots**, never allocated to individual posts.
- `founder_minutes_per_qualified_signal=total_creator_minutes/qualified_signals` if signals >0, otherwise unavailable.
- Do not add these rates into one magical algorithm score. Use reach → response → profile → actual account change as a funnel of *observations*, not an attribution model.

## 5. Publishing evidence and data contract

- Owner-reported 2026-10-26 publications without URLs are staged as `reported_published_url_pending`, never labeled verified `published`; resolve status with real public `x.com/.../status/...` link.
- Do not set timestamps or analytics to zero/guesses. Post dates alone are insufficient for precise T+24h windows.
- `templates/posts.csv` is the content index, `templates/x-metric-snapshots.csv` stores append-only age snapshots, `templates/x-account-snapshots.csv` stores account-level follower count/eligibility checks.
- No server-side automations, official API, analytics access or out-of-product posts are claimed to exist.
- `templates/X-RECOVERY-WEEKLY-REVIEW.md` captures source coverage, qualified signals, and a single controlled next experiment.

## 6. Hard acceptance and rollback

Before approving any new content: audience fit; demonstrable reader action; genuinely independent analysis; provenance; rights/PII; accurate image+ALT; length; non-duplicative; actual post URL after publication. If post is untested, label that scope explicitly. Keep source and metric evidence visible to the creator.

On continued follower decline over two weekly comparable observations, first investigate posts/account health and audience alignment; **do not speed up output, buy followers, mass DM or switch all variables at once**. Stop/roll back experiments causing policy/privacy issues immediately. Revisiting frequency or account roles requires evidence and owner judgment.

### Maintainer note
The previous `30% Skills / 30% AI news / 20% monetization / 20% tutorial` was a *content-mix hypothesis*, not a proven optimal schedule; during this recovery sprint, narrow to one reader job first. Likewise daily post production is **suspended as a quota**, not outlawed when excellent source material exists. After 14 days, document the decision and only then revise Strategy's longer-term cadence.
