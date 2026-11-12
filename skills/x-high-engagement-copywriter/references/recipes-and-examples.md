# Writing mechanisms — grounded in the audited sample ledger

Read [sample-ledger.json](sample-ledger.json) first. S01–S10 are ten directly visible pasted X-post prompts; S11 is available through a previous-turn summary only. The user describes them as high-performing, **but the current files contain no authenticated post-level metrics**. Text examples below are **new synthetic drafts**, not reprints or proven winners.

## Core: pattern + original fact/scene + audience-specific reason to react

A good short post has a stop-scroll **first line**, one concrete **payload** and a natural **finish**. Use disagreement only when it is defensible; do not require a forced question, follow, like or comment.

| Recipe | Source inspiration | Mechanism | Originalizable move |
|---|---|---|---|
| R01 名字+真假反转 | S01/S07 · P01 | authoritative-sounding allegation -> request actual evidence | break news vs board discussion vs official action apart |
| R02 三个画面细节 | S02/S08 · P02 | color/temperature/object -> emotion | write from own photograph or an authorized image |
| R03 极低门槛的互动 | S03 · P03 | 'say keyword -> huge reward' captures attention | **negative example**; create a genuine question, never promise follower rewards |
| R04 生活警醒 | S04 · P04 | disgust/contrast -> one action | add a modest, justified routine rather than spreading panic |
| R05 大胆反差 | S05 · P05 | minimal object vs huge view number | turn exaggerated claim into a debatable, testable hypothesis |
| R06 技术悬念 | S06 · P06 | vanished repo -> surprising mechanism -> next step | link a checked source and explain a limitation, no unsupported exploit claims |
| R07 幸存者反例 | S10 · P07 | single defiant story -> implied rule | expose survivorship bias and discuss what a case cannot prove |
| R08 误区清单 | S09 · P08 | common beliefs -> counterexample -> knowledge gap | distinguish medically established causes from folklore with sources |
| R09 数值反差与轻幽默 | S11 · P09 | human work week vs theoretical 168h machine week | distinguish 24/7 theoretical capacity from actual uptime |

**Select one** primary recipe per post; add at most one secondary. Avoid packaging five posts with the same "哈哈哈", emoji, request for comments, or hook skeleton. A natural finish can be a punchline, a dilemma, a question, or a useful takeaway.

## Four original worked examples (not observed X results)

### A. X growth insight — inspired by S05 (P05)

A:
> 发现一个很扎心的问题：
>
> 当平台有流量时，发张白纸都能让人讨论。
>
> 可我们真正该问的，不是“平台给不给我流量”，而是“看过的人有没有理由回来”。
>
> 你觉得曝光和留住人，哪个更难？

B:
> 我越来越觉得，做 X 最危险的幻觉是：
>
> 把一条帖子的浏览量，当成自己已经有了稳定的读者。
>
> 热度可以偶然来，下一条有人等着看，才是另一回事。

*Test variable: question ending vs declarative ending. Neither states actual X ranking logic.*

### B. Technical curiosity — inspired by S06 (P06)

A:
> 一条技术新闻越像“苹果十几年防线瞬间失效”，我越想先看三件事：
>
> 能访问哪类目录？权限边界在哪里？有没有可复现的代码？
>
> 标题可以十秒钟看完，机制值得慢慢拆。

B:
> 最值得警惕的安全新闻，不是“这个终端终于能装软件了”。
>
> 而是把能用包管理器、能读某个目录、能完整越狱混成一件事。
>
> 三个概念分清了，讨论才真正开始。

*Source verification required before any assertion that a specific exploit works.*

### C. Ordinary scene — inspired by S08 (P02)

A:
> 冬天很容易被一碗小馄饨哄好。
>
> 汤是热的，屋外是冷的，烦恼先在门口站一会儿。
>
> 你们冬天最想吃的那一口是什么？

B:
> 有些美食不用多贵。
>
> 冷天捧着热汤，手先暖了，人就没那么着急了。

*Use an image only if the account has rights. Do not claim to have photographed or tasted a specific meal without evidence.*

### D. English reflection/humor — inspired by S11 (P09)

A:
> 168 hours in a week. That's the *theoretical* 24/7 work schedule for a robotaxi.
>
> Humans spend half their careers just trying to earn a quieter Friday.

B:
> The interesting question isn't whether a robotaxi can run 24/7 on paper.
>
> It's how much of that time it actually spends moving people instead of waiting, charging, or being serviced.

*No assertion of actual 168h commercial uptime. No follower exchange or hollow "who's in?" CTA.*

## Short reply/quote-post module

These source posts originally arrived because the user wanted **replies**, not necessarily new original posts. The corpus consists of *source tweets*; the assistant's generated comments are **not verified to have received X interactions**.

- **REPLY_DRAFT**: read post context, identify claim vs opinion, add one new perspective in 1–3 sentences, then optionally ask one specific low-effort question. Match the source language; for an English reply requested by a Chinese-speaking user, show the Chinese translation **outside** the copy.
- **QUOTE_POST**: state the original's idea in one sentence, add a substantive independent angle; if quoting/attributing, include a source URL when available and rights-compliant.
- **ORIGINAL_POST**: create a fresh observation, premise or scene rather than copying the original's distinctive phrasing.
- **THREAD**: only when the evidence supports multiple distinct steps. A cliffhanger is not permission to invent security details or fake a "part 2".

### Output-mode examples (fictional)

| Source situation | Natural reply direction | New standalone post direction |
|---|---|---|
| S03 keyword-for-followers | light skepticism about instant follower promises | "What kind of connection makes you stay?" with genuine context |
| S04 clothes hygiene warning | "washing first is a simple habit" without invented contaminants | practical consumer habit grounded in personal practice |
| S10 Claude anecdote | survivor bias with friendly humor | rules vs one person's experience, avoiding evasion steps |
| S01/S07 CEO allegation | "let's distinguish rumors from formal announcements" | evidence-minded reflection without inventing an announcement |

## Agent prompt for next time

> Read \`skills/x-high-engagement-copywriter/SKILL.md\`, then \`references/sample-ledger.json\`, \`corpus-taxonomy.md\`, \`recipes-and-examples.md\` and \`evaluation-and-metrics.md\`. For [confirmed account and audience], [language], [ORIGINAL_POST or REPLY_DRAFT], use [user-provided topic or factual source]. Produce 5 **original** distinct candidates with ≥3 different hook types, each containing a real idea after the first line. Never copy a supplied X post, fake a statistic or promise followers. State what is fact vs opinion, choose the best candidate for **human review** based on editorial criteria, and include the one-variable experiment and the existing X metric backfill plan. If a claim is unverified, hold or reframe it.

### Stop conditions

- No authenticated source for breaking rumor/medical claim: HOLD the factual part, not the entire ability to draft a safe question.
- A sample's high performance is self-reported without metrics: no numerical lift claim.
- Existing account language does not match: draft only with account **UNCONFIRMED**; no publish readiness.
- The operator asks to auto-respond or reward keyword engagement: no automation, no invented follower promises.
