# X Draft #004 — Build-to-sell: proof-of-value beats demos

**Status:** `draft` — **NOT published or scheduled to X**. Needs live status URL.  
**Content ID:** `20261025-004` | **Created:** 2026-10-25 Asia/Shanghai  
**Mode:** `EVERGREEN_DISCUSSION` (not a new release in last 72h)  
**Channel:** X social discourse + independent academic evidence (not a GitHub product announcement).

## Separate X popularity from evidence

- **X discussion signal:** [@levelsio, Oct 11 2026](https://x.com/levelsio/status/2109262337500705094), discussing the rise of "personal software". [XOutlier](https://xoutlier.il.ly/u/levelsio) surfaced approx 1.7M views/5.6K likes in a third-party Oct 24 snapshot. **Not official X API confirmed**. Original X page could not be fetched directly in this tool session; metric provenance is `third_party_snapshot`. Popularity selects a topic but cannot validate whether software is actually "dead".
- **Independent primary research:** [NBER Working Paper 34836, *Firm Data on AI*](https://www.nber.org/papers/w34836), *October 2026 revision* (exact revision day not confirmed). Study reports nearly 9,000 executives across seven countries and states 78% of firms use AI; executives estimate AI raised **annual labor-productivity growth by 0.2% over the previous three years**. Survey self-report, not causal firm experiment. **Do not reuse earlier February/March statistics (69% adoption, smaller geography) as if it were this revision.**
- **GitHub commercial delivery direction (investigation only):** [Activepieces](https://github.com/activepieces/activepieces) documents AI automation and human-in-loop approval; [Docling](https://github.com/docling-project/docling) parses PDFs/tables. These are technical options, **not evidence they saved an actual customer's money**. Both need business-case tests, licensing and maintenance review before recommendation.

## Three original theses, quality screen (subjective; not X algorithm)

| Angle | Claim | Counterargument | Editor score |
|---|---|---|---|
| **A — Show me the outcome (selected)** | Cheap app creation does not establish firm productivity. A builder should sell an auditable, measurable reduction of costly manual exceptions rather than only an agent demo. | Buyer might prefer fixed-price software or staff training; surveys average across firms and do not prove this service is profitable. | **26/30** |
| B — Operations as moat | As app generation becomes easier, connecting legacy data, error handling, approvals and compliance may retain cost/value. | Good horizontal platform vendors may bundle these functions, depressing margins. | 24/30 |
| C — No universal AI ROI | Generic AI adoption metrics do not predict ROI; target a narrower job/process and calculate task-level economics. | Micro-metrics can be gamed and may miss broader innovation benefits. | 23/30 |

Angle A rubrics: novelty 4, primary evidence 5, causal mechanism 4, buyer decision value 5, falsifiable test 4, expressive hook 4. **No performance experiment conducted.**

**Claim types:** [fact] NBER survey numbers and GitHub capabilities within documentation; [X opinion] personal software prediction; [our inference] software construction does not guarantee financial productivity improvement; [unverified business hypothesis] firms may buy measurable exception reduction.

**Commercial minimum test:** One accounts-payable leader with recurring manually triaged invoice exceptions. Baseline for 5 working days: number of exceptions, human minutes/case, resolution time, rework/error count. Pilot flow: consented invoice data → structured parsing and rule-based checks → **human approval for decisions** → reviewable log. Charge only after defining a realistic one-time/recurring fee hypothesis with the buyer; estimate labor, API/compute, setup and maintenance before claiming margin. Re-evaluate over another 5 workdays. **No buyer interest, price or savings is asserted to exist here.**

## Publication-ready English (copy exactly)

```text
AI can generate an app. It cannot guarantee a business outcome.

NBER's revised survey: 78% of firms use AI, but executives report only a 0.2% annual productivity-growth boost.

Sell verified exception reduction, not an agent demo.

https://www.nber.org/papers/w34836
```

- Unicode code-point count with URL literal: **267**.
- Approximate X weighted characters with URL treated as 23: **256**. Use the actual X Composer to confirm because the counter is authoritative for user submission.
- Recommended: **one text-only original post**. A dual-axis infographic with 78% adoption vs 0.2% annual productivity is misleading because these metrics have different denominators/units. The full data explanation lives in the source, so no image is more truthful than a decorative AI visual.
- No hashtags, engagement bait or copied X creator wording.

## 中文翻译

AI 可以生成一款应用，但不能保证企业获得实际经营成果。

NBER 的修订版调查显示：78% 的受访企业在使用 AI，但受访高管报告的 AI 带来的年度生产率增长提升仅约 0.2%。

与其出售一个 AI Agent 演示，不如尝试交付能够验证的业务异常处理工作量下降。

## Publication and verification

1. Visit https://x.com/compose/post on the authenticated account, paste the English text, inspect final X character counter.
2. Confirm NBER source link and claim context, then publish as a **single text-only post**.
3. Record a real `https://x.com/.../status/...` URL in [posts.csv](../templates/posts.csv) and mark `published` **only after live verification**.
4. Save actual weekly numbers from X if available; future follower gains cannot be attributed causally to a single post without further evidence.

**Approval:** needs human review. **Actual X publication, subscriber growth and business demand:** not verified.
