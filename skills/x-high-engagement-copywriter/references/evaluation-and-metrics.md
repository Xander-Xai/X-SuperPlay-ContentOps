# Editorial assessment and actual X metrics

## 1. Two independent judgements

**HARD CHECK (pass / rewrite / hold):** rights and originality; traceable real-person allegations and quotes; sensitive claims; no deceptive engagement rewards or counterfeit urgency; account/language match; review of personal information; no automation. Any fail remains fail regardless of wordcraft score.

**EDITORIAL SCORE:** a pre-publication heuristic, **not an X algorithm score** and not a predicted impression/engagement figure.

| Dimension | Max points | High score means |
|---|---:|---|
| First-line specificity and stopping power | 20 | specific tension/scene, not generic hype |
| Valuable middle | 20 | insight, proof, mechanism, lived detail or genuinely funny turn |
| Originality and non-templated voice | 20 | not copied, not recycled phrasing, sounds like one person |
| Audience relevance | 15 | real point of contact with desired readers |
| Natural discussion/quote potential | 15 | concrete choice, useful disagreement or quotable ending, no forced ask |
| Rhythm and readable language | 10 | clear, concise, accurate native language |
| **Total** | **100** | ≥80 suggests **human editorial review**, never publication, verified reach or revenue |

Editorially grade two different variants for one topic without inventing a winning variant. If an explicit audience, evidence or angle is missing, mark assumptions rather than silently filling with a fake first-person anecdote.

## 2. The claims boundary

| Input kind | What the draft can say | What it cannot say |
|---|---|---|
| User says "I tested X" but gives no receipt | "我的观察/我正在测试" if authorized as the author's own statement | invented duration, counts, proven uplift |
| A screenshot of someone else's follower count | "截图显示..." with author/context only if validated | "我增长了..." or an earnings guarantee |
| Celebrity accusation or politics | confirmed report with source and uncertainty | defamatory "it is proven" or fake official statement |
| Health/sexuality statistics | verified sampling frame, date, population and context | country-level claim from an unknown subgroup |
| Speculative X algorithm theory | "值得测量的假设" | "发帖后20评论必然抬曝光" |
| Fictional comedic setup | unmistakably hypothetical or playful | fake self-reported real event for credibility |

For controversial or novel current news, verification comes **before** a factual draft. If the source is unavailable, draft a timeless editorial question that does not repeat alleged facts as reality; mark UNKNOWN.

## 3. The existing data truth source — never create a shadow ledger

Use only the project's existing indices, with human-approved data and actual URLs:

- projects/x-growth-en/templates/posts.csv — intent, content_id, status, source, and real post URL when known.
- projects/x-growth-en/templates/x-metric-snapshots.csv — post-age-aligned snapshots with impressions, engagements, replies, reposts, bookmarks, profile clicks, link clicks, and eligible attribution only when actually supplied.
- projects/x-growth-en/templates/x-account-snapshots.csv — account-level observations and net-follower context.
- projects/x-growth-en/templates/x-rewards-eligibility-snapshots.csv — account-level creator eligibility, if official evidence exists; **not** a post metric.

A CSV cell left blank means **not observed**, not zero. Never calculate "qualified verified home timeline impressions" from ordinary impressions, or attribute an entire account's net followers to one post. Do not expose private account metrics in public Git.

## 4. Practical experimental design (manual)

1. Set one objective: **reach**, **relevant replies**, **profile curiosity**, or **qualified audience growth** (only if account data exists).
2. Define the audience and one hypothesis, e.g. "specific technical failure hook gets more meaningful replies than broad AI optimism for builder readers".
3. Change **one principal writing variable**: hook, degree of specificity, question vs statement, or opinion vs story. Avoid changing language, media format and publishing window simultaneously if possible.
4. Use different original subjects but compare **within the same topic family**; do not publicly post near-duplicate variants solely to test them.
5. Log published post URL, actual time, source type, post age windows T+24h/T+72h/T+7d, access method and missing fields. Subjective "exposure from replies" is a hypothesis until measured.
6. Compare a series of posts, not a single lucky viral point. The first few observations are exploratory; in a small sample report **INCONCLUSIVE**.
7. Choose CONTINUE, REWRITE, RETEST, or PAUSE based on **your own account's real data**, not rankings in the supplied conversation.

Metrics useful for diagnosis (only when available):
- **Observed engagement rate:** (likes + reposts + replies + bookmarks) / impressions; components overlap as user actions and may not equal X's native engagements. Clearly label a custom denominator.
- **Reply depth:** meaningful on-topic conversations / observed replies; if replies are not manually read, unknown.
- **Profile curiosity:** observed profile clicks / impressions.
- **Follower trend:** account-level change over a fixed window, not per-post causal attribution.
- **Creative efficiency:** drafting + review minutes per accepted original post.
- **Creator eligibility:** strictly the current X policy and Creator Studio's account-level metrics (reverify before use); ordinary impression totals are not interchangeable.

Avoid "views grew X%" unless both baseline and denominator are documented. Avoid fake A/B significance when selection is observational and sample sizes tiny. Strong correlation does not establish a platform ranking rule.

## 5. Reuse loop

After 7–14 days and enough actual published posts, produce one paragraph per tested mechanism:

- Evidence: links, time windows, comparable topic family, access limitations.
- Observation: what moved in which direction and by how much (or unknown).
- Alternatives: news timing, account composition, creative topic, media, language.
- Decision: next single variable; whether to retire a tired hook.
- **Never:** claim "we cracked the algorithm" or "this template always goes viral".

## 6. Launch check (human reviewer)

- [ ] Own insight or authorized source exists; copied wording has been replaced with original content.
- [ ] Every named factual claim, number and quote is supported or clearly identified as opinion/hypothesis.
- [ ] One strong opener; one point; no repeated boilerplate.
- [ ] Written in the selected account's approved language, not silently mixing Chinese/English audiences.
- [ ] Real perspective after hook; no empty rage-bait or exchange-for-follow CTA.
- [ ] Safe and respectful handling of mental health, sexuality, health, ethnicity, gender, and allegations.
- [ ] Copyright/privacy/media permissions reviewed when a picture, video or screenshot is included.
- [ ] Existing X post gate and human review remain pending until performed.
- [ ] Metrics plan is ready, but no post is described as published until real X URL is recorded.
