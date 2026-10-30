# Dual-Source Research SOP — X Signals × GitHub Evidence (2026-10-25)

**Status V0: manual, research-only, human-approved X posting.** X is now an **official source lane** for idea discovery and discourse. GitHub is a separate lane for actual code, Skills and technical mechanisms. A third lane (original research, pricing, benchmarks, primary business disclosures) resolves factual and commercial assertions. Neither popularity nor an LLM's confidence is proof.

## V0 daily flow — no API account required

1. Open X **Top and Latest** or X Advanced Search and discover 3–5 relevant public original posts. Filter for English, AI productivity, credible automation delivery, actual buyers, operating cost, and willingness to pay. Use `from:`, dates, `-is:retweet`, and `url:github.com` if supported in the current search interface. X Top is relevance-personalized, **not a strict global view-count rank**.
2. Record author, exact **permalink**, posted UTC date, original claim and any observable views/likes/reposts/replies, **snapshot time, source URL and provenance**. No blank-to-zero conversion. `verified_x_api`, `visible_on_x`, `third_party_snapshot`, `unverified` are distinct states. A third-party screenshot/count must not be presented as an X API verified count.
3. **High-data qualification** (editorial heuristic, not platform rule): at least **20K observed views OR 200 observed likes**, with named metric source/date; preferred 100K+ views or 1K+ likes, **and** meaningful relevance. For small expert accounts, a substantive primary-use-case can still be retained as `expert_signal`, without calling it viral. Engagement ratio = (likes + reposts + replies)/views only if all four measured for the **same post at comparable times**. Views are **not unique readers**.
4. Open the full original thread, consider objections and context; track edits, sponsorship, giveaways, promotional CTA, bots/copying risks. **Disqualify** misleading financial results, engagement bait, generic "100 tools", unsupported 10x assertions and quote farms even if views are high.
5. Search GitHub/official sources for the mechanism: README **and** specific SKILL.md/Release/PR/commit when asserting an update. Require a task, a plausible repeatable value mechanism, a concrete verification test and nontrivial operating/implementation constraints. **News_72h** requires actual event within current rolling 72h; a viral old post or evergreen repo is explicitly **evergreen**.
6. Build three materially distinct editorial theses: hidden bottleneck, economic trade-off and deliverable/buyer or similar. Cite original X post as **discourse signal**, the technical/academic primary source as **evidence**. Red-team: What would make this wrong? What's the buyer? What is the baseline? What is the maintainer burden? If just retelling the X author's message, reject.
7. Deliver **one original English X post** (default; ≤3 in a thread), fact check X's **weighted** 280-character limit. Original analysis must be significantly different in claim, wording and example from the X post. Attribution/link to original X post remains in the **research card**; include it in final thread only when the post depends on their specific claim. Avoid screenshotting/reposting their image without permission. Follow [visual standard](VISUAL-EDITORIAL-STANDARD.md): **text-only is acceptable**.
8. Manually publish/queue using approved X features. **Only a real X status URL permits `published` status**. Log post and weekly learnings; engagement/follows do not prove an editorial angle caused growth.

### Suggested manual X searches (copy one)

- `("AI automation" OR "agent workflow") (client OR revenue OR ROI) lang:en -is:retweet -is:reply`
- `("Claude Code" OR "AI agent") ("time saved" OR "manual work") lang:en -is:retweet`
- `("small business" OR "invoice" OR "customer support") (automation OR AI) lang:en -is:retweet`
- `(AI OR agents) (cost OR pricing OR reliability) url:github.com lang:en -is:retweet`
- `from:levelsio (software OR SaaS OR automate) -is:retweet`

No claim that all operators work on every X tier; API operators and access must be checked in X official docs.

## X/GitHub open source research and adoption (read-only workflow)

| Project | What was checked | V0 decision | Future gate |
|---|---|---|---|
| [trailofbits/skills-curated X Research](https://github.com/trailofbits/skills-curated/blob/main/plugins/x-research/skills/x-research/SKILL.md) | X API v2 keyword searches, `--sort likes/impressions`, min filters, watchlists, thread reading, cache/cost estimates | **Adopt research pattern**, **do not install**: requires X bearer key, Python/uv and cost | Only if manual sourcing costs >30 min/day and user explicitly accepts API charges; first test read-only, dry-run/cost cap |
| [xdevplatform/docs Search Posts](https://github.com/xdevplatform/docs/blob/main/x-api/posts/search/introduction.mdx) | Official recent 7d/full-archive API, query operators and authorization | **Reference standard**; not an enabled connection | Check official pricing, access tier and metrics availability before enabling |
| [xdevplatform/docs Post Lookup](https://github.com/xdevplatform/docs/blob/main/x-api/posts/lookup/introduction.mdx) | Lookup by ID, post status/edit history and public engagement fields | **Reference standard** for verifying X metrics | Explicitly authorized read-only API only |
| [Desearch-ai/x-monitor](https://github.com/Desearch-ai/x-monitor) | Watchlist buckets/lanes, seen-ID dedupe, 24h rolling cache, dry-run | **Borrow state and tagging**, no deployment | Uses Desearch credentials, external APIs, Discord/Feishu; check license and data handling |
| [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills/blob/main/skills/social/references/x-algorithm.md) | Distinguishes algorithm structure from unverified/old numeric weights | **Borrow caution about measured versus inferred reach**, never promise ranking advantage | Verify against [xai-org/x-algorithm](https://github.com/xai-org/x-algorithm) when needed |
| [langchain-ai/social-media-agent](https://github.com/langchain-ai/social-media-agent) | Draft, edit and approve before publishing | **Already adopted** in URL→X prompt | No full stack installation |
| [TwitterAPIs/twitterapis-mcp](https://github.com/TwitterAPIs/twitterapis-mcp) | Third-party account session / cookie or login credentials, paid wrapper, write tools | **Do not integrate now**: account credential, ToS, third-party data/cost risks | Requires explicit user security/legal review; prefer official X API |
| [jeremyknows/x-master](https://github.com/jeremyknows/x-master) | Bundled tools and unverified numerical "algorithm multipliers" | **Reject growth-number claims**; not adopt master routing | Only independently verified facts may be cited |
| [altansaid/ai-social-engagement-engine](https://github.com/altansaid/ai-social-engagement-engine) | Keyword-targeted automatic response workflow | **Reject automated unsolicited engagement** | Human-authentic discussion only |

No repo above was installed or run, and **no X OAuth/API bearer credentials were supplied**. These findings are source-level architecture reviews, not reliability endorsements.

## X case review — high engagement is the *topic signal*, not proof

**Candidate X-001:** [@levelsio, Oct 11 2026, "Software is dead… personal software"](https://x.com/levelsio/status/2109262337500705094). The [XOutlier public cached account page](https://xoutlier.il.ly/u/levelsio) showed approx **1.7M views, 5.6K likes** in a snapshot surfaced Oct 24, 2026 (secondary metrics, not directly confirmed against X API in this session). **Status: `third_party_snapshot`, `evergreen`, `editorial_signal_only`.** The popularity is real evidence of discussion interest *if the cache is accurate*, but the proposition "software is dead" is an opinion, not technical fact.

**Cross-check (separate primary evidence):** [NBER, Firm Data on AI, October 2026 revision](https://www.nber.org/papers/w34836) reports **78%** of surveyed firms use AI and executives estimate a **0.2% annual labor-productivity-growth boost over the previous three years**. This is an executive-reported estimate across the surveyed firms, not a randomized AI automation test. Do **not** mix this latest October revision with the older February/March version of the same paper, which used a smaller international sample and different numbers.

**Original editorial angle:** software generation may be getting cheaper, but integration, measurable exception handling, accountability and maintenance still matter. **Monetization is a hypothesis**: an owner of finance operations might pay for fewer manual invoice exceptions, supported by weekly before/after measures and an approval trail. Buyer demand/pricing **unverified**. The original viral author's sentence must not be republished verbatim.

**Reject examples:** An X video saying it generates 10M views/month without analytics provenance is not verified revenue; an engagement-bait list of 50 AI tools with thousands of likes but no actual repeatable workflow does not pass the productivity gate.

## Metric record and copyright safeguards

Use [x-source-candidates.csv](../templates/x-source-candidates.csv): if views unavailable, `views` blank, `metric_provenance=unverified`. Never say `high_data_verified` when the only numbers came from an index or scraping mirror; post-level view counts move over time and are not unique users. Preserve the **URL and limited summary**, not large copied threads or their images. Prefer synthesizing original thought, adding source links and new tests rather than copy/pasting a viral post.

**References:** https://help.x.com/en/using-x/x-search ; https://help.x.com/en/using-x/top-search-results-faqs ; https://help.x.com/en/using-x/view-counts ; https://help.x.com/en/rules-and-policies/x-automation

**Next step:** run the daily prompt and publish one eligible original insight, no automation purchase.
