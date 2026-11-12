---
name: x-high-engagement-copywriter
description: "Use when creating original, discussion-worthy Chinese or English X posts from high-interaction example posts, real creator observations, technical evidence, or cultural moments. Produces hooks, finished drafts, checks, and testable hypotheses; never publishes or promises reach."
---

# X High-Engagement Copywriter

## Goal and scope

Turn an observed topic or user-supplied example into **original X main posts** that more people may stop to read, reply to, quote, and follow for. Optimize the combination **attention -> useful or recognizable viewpoint -> conversation -> audience fit**, not engagement-bait counts. This is a **writing skill**, not an X algorithm exploit, publishing agent, bot, trend scraper, or guarantee of impressions.

**Use when:** asked to draft high-interaction X posts, remix a topic into a discussable original angle, create a batch of reach-oriented posts, improve a weak opener, or generate a variation for an experiment.

**Do not use for:** mechanically copying popular tweets; automatically posting, liking or commenting; bot-style "say keyword for followers" schemes; treating rumors, snippets, screenshots, or replies as verified facts; making account-specific promises of reach.

Read these references as needed:
- [Sample-derived pattern taxonomy](references/corpus-taxonomy.md) — categories drawn from the supplied conversation.
- [Writing recipes and examples](references/recipes-and-examples.md) — reusable structures, not text to plagiarize.
- [Evaluation and metrics](references/evaluation-and-metrics.md) — review score, experimentation, and facts boundary.
- [Adversarial acceptance cases](references/acceptance-cases.md) — expected behaviour on realistic requests.

## Hard facts about the source material

1. The user supplied a **large, diverse selection** of X posts in one conversation: growth diaries, engagement questions, food/pets, humor, relationship reflection, motivational English, AI/tech analysis, rumor posts, sexual/medical claims, and follow-for-follow pitches. Some assistant replies are also visible; **do not confuse a reply with an observed original post**.
2. The user described these as high-view/high-interaction examples. **We do not have per-post authenticated X analytics, source URLs, impressions, engagement rates, or a matched comparison group.** The samples establish *hypotheses and style features*, not causal evidence or a performance leaderboard.
3. The user-supplied texts may be authored by other accounts. Only imitate **mechanisms**, never distinctive wording, identities, media, or assertions. Do not store copied complete posts as ready-to-publish assets.
4. The project is public. Do not commit a user's real account insights, private screenshots, DM content, credentials, private performance exports, unlicensed media, or a full copied tweet archive.

## Workflow — one production run

### 1. Establish the real brief

Determine **account**, language, audience, content pillar, source of first-hand knowledge, specific takeaway, desired action, and number of posts. Missing account/metrics must be marked UNKNOWN, not invented. If the current user's request is self-contained, draft without interrogation; label unresolved account linkage as **REVIEW_REQUIRED**.

Use the account DNA and source/claim evidence rules already present in ContentOps. The existing project at projects/x-growth-en/project.yaml is **English**, manual-only. This skill supports zh-CN/en as **draft languages** but does not silently switch an English account to Chinese or merge different accounts' audiences. For Chinese posts, require an operator-confirmed matching account or explicit language experiment before real publication.

### 2. Select one core observation and one audience tension

Build a one-sentence content thesis with:
- **Observed fact / first-hand action**: what happened and where the evidence is.
- **Interpretation**: what it might mean, marked clearly as judgment.
- **Disagreement space**: what a reasonable reader might argue against.
- **Reader's reason to care**: time, money, identity, belonging, curiosity, practical value, or memory.

Do not generate a "hot take" that hinges on an unverified celebrity accusation. When the subject is timely, fact-check before asserting; if not checked, explicitly soften or choose a durable angle.

### 3. Pick a suitable mechanism, not a copied template

Use one primary recipe, optionally one secondary recipe, from the taxonomy:

- **Contrast or paradox**: expectations versus reality; avoid false dichotomies.
- **Concrete micro-story**: scene -> friction -> reversal -> takeaway.
- **Honest quantified progress**: actual baseline -> action -> result -> unresolved question (only with real data).
- **Relatable identity humor**: "worker / creator / engineer" observation, self-deprecating, never demeaning a protected group.
- **A genuine question**: two defensible options and a reason to answer.
- **Emotional image**: concrete moment -> universal feeling -> resonant line.
- **Evidence-led technical opinion**: observation -> mechanism -> limitation -> discussion.
- **Factual news angle**: sourced fact -> implications -> uncertainty; no fake "breaking" urgency.

Prefer a strong first line over repetitive "哈哈哈", "卧槽", "不懂就问", "说个暴论" on every post. Those words are **optional tools** and repetition is a quality defect.

### 4. Write original candidates

For each requested original post, create a crisp first line, 1–4 short readable blocks, **one** central message, and an ending that is either a meaningful question or a memorable punchline; do **not** tack on a question automatically. Chinese default roughly 50–180 characters, English default concise enough for the account's current post limit; adjust to user intent and platform limit, not a magic algorithm length.

Language rules:
- Chinese: everyday speech, concrete detail, a light unexpected turn, no assembly-line corporate phrasing.
- English: native conversational register, not a translated Chinese meme or repeated "real connections/genuine engagement".
- Match emotion to topic: grief/illness deserves dignity; safety/reputation/legal matters require restraint; ordinary entertainment can be playful.
- No made-up experiences ("I tested", "I made $X", "I have 10k followers") or invented numerical evidence.
- No engagement exchange, "follow me and I'll follow back", fake guaranteed boosts, reply farming, or repetitive hashtags.

**For batch generation**, force diversity: at least three distinct hooks across five drafts, no duplicated CTA or identical structure, and include a plain-language/grounded alternative to the most sensational draft.

### 5. Separate hard checks from editorial score

**Hard stop / rewrite**: fabricated data; mistaken account; uncited material allegation about a named person; falsely attributed quote; non-consensual sexual details; hate/dehumanization; privacy exposure; copied distinctive text; spam/deceptive rewards; unsupported medical/financial claims; illegal instructions; unsafe copyright/media usage. These cannot be outweighed by a high writing score.

Then apply the 100-point **editorial heuristic** in the evaluation reference (not a predicted X ranking). Poor-quality or heavily repetitive drafts are rewritten. A score ≥80 is *ready for human editorial review*, never proof of platform success.

### 6. Output contract

For ordinary "write N X posts" requests, provide **N finished drafts** ready to copy, keeping metadata brief and separate. If language differs from the conversation's language (e.g. English post to a Chinese speaker), provide a short Chinese translation outside the post. Do not prepend explanations inside the copy.

For an explicit ContentOps production run, return this editorial receipt (plain Markdown or structured equivalent):

- account_alias / target_language / audience / post_type=ORIGINAL_POST
- topic, source_kind=FIRSTHAND|PUBLIC_SOURCED|OPINION|HUMOR|UNVERIFIED
- claim_support: citation/receipt/UNKNOWN; risk: PASS|REVISE|HOLD
- pattern_id, objective, original_thesis, novel_angle
- variant A/B (different hooks or framings), full copy, why each might earn a reply
- review_score (editorial only), uncertainty and rights notes
- experiment_id, **one primary variable**, proposed comparable observation window
- status: DRAFT_REVIEW_REQUIRED until existing X post gate and human review

When asked for **comments** rather than original posts, defer to x-organic-growth-operator or the immediate comment drafting task; do not turn every reply into a main post.

### 7. Human handoff, measurement and learning

Use the existing X editorial flow and account-specific manual gate:
- Editorial/growth workflow: [x-organic-growth-operator](../x-organic-growth-operator/SKILL.md).
- Current X project: [English creator track](../../projects/x-growth-en/README.md).
- Existing X post gate: scripts/x_post.py (manual, not a publishing API).

If a post is later **actually published** and an operator provides a real URL, record its post ID and age-aligned T+24h/T+72h/T+7d analytics in the existing project CSVs. Never infer the creator program's **verified Home Timeline impressions** from general post views. Review what worked for this account and audience, then update hypotheses. Views, reply counts, follower growth and revenue are distinct.

There is **no automatic posting, automatic analytics retrieval, skill-registry executable capability, or production acceptance** in this Skill. Discovery is not execution authorization.

## Minimum done definition

An output passes only if it is **new**, audience-specific, factually defensible, interesting in the first line, has an actual idea or scene after the hook, and is simple to test in the existing manual workflow. "Looks viral" is not a result. "High engagement guaranteed" is never an allowed claim.
