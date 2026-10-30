# Content Router

[English](CONTENT-ROUTER.md) | [简体中文](CONTENT-ROUTER.zh-CN.md)

> One entrance for a topic: pick the account, pick the route, get a brief that
> the existing pipeline can pick up.

## What this is

The repository could make a film. It could not answer the two questions that
come first: **who is this for**, and **what is it about**. Those answers
existed in two unrelated places — a hot list nobody had asked for, and
somebody's head — and neither left a record of where the topic came from. A
downstream stage could not tell them apart, so it could not enforce anything
about either.

The content router is the layer between those answers and the pipeline:

```
account ──▶ Account DNA ──▶ route ──▶ topic ──▶ Content Brief ──▶ existing pipeline
             (positioning)   (explicit)  (chosen)   (one contract)   (unchanged)
```

Two routes enter it:

| Route | Where the topic comes from | What the router does |
|---|---|---|
| `HOTSPOT_DISCOVERY` | a hot list, scoped by the account | plans the search, collects, filters, ranks, and **waits for a person to choose** |
| `USER_TOPIC` | the account owner | checks the topic against the account's positioning, keeps their words, and **waits for a person to approve the brief** |

Both produce the same contract, and both end in the same pipeline. There is
one video production engine, not two.

## The route is never inferred

`route_mode` is one of `HOTSPOT_DISCOVERY` or `USER_TOPIC`, and the caller
names it. A call without one is refused with `ROUTE_SELECTION_REQUIRED`. The
router does not decide from the topic, the platform or the account, because
silently choosing a different job than the one asked for is worse than
refusing.

A run stays in its route. If a source is down, the run reports the failure;
it does not go and find a topic by another means.

## The account decides the search

The account DNA is read **before** anything is fetched, and its
`discovery` block is what drives the collection:

| Field | Effect on the search |
|---|---|
| `keywords_positive` | the terms a native-search source is asked for, and the terms a candidate must match |
| `keywords_negative` | terms that reject a candidate before a person sees it |
| `source_allowlist` | the only sources that are contacted. A source that is not on it is not fetched and then discarded — it is never contacted |
| `source_blocklist` | sources the account refuses; a blocklist entry beats an allowlist entry |
| `content_pillars` | which pillar a candidate belongs to, and the shelf it lands on |
| `not_doing` / `excluded` | what the account refuses to make |
| `match_weights` | the ranking, as percentages that sum to 100 |
| `approval_policy` | who approves, and the fact that a person must |

### The anti-invention guarantee

Every keyword carries an `origin` naming the field of the DNA it came from.
`scripts/check_account_dna.py` resolves that citation against the DNA in the
same file, and a keyword whose origin does not resolve **fails the DNA
check**. There is no path by which an unsourced term enters a search.

An English keyword may be declared as a `translation` of a Chinese one — a
translation renders an existing term into another language rather than
asserting a new positioning claim — but the Chinese source term must itself
resolve.

```json
{ "term": "open source", "language": "en",
  "origin": { "kind": "translation", "origin_kind": "pillar_scope",
              "pillar": "AI 新物种", "origin_term": "新 GitHub 项目" } }
```

An account with **no** `discovery` block is refused a hot-list search with
`ACCOUNT_DNA_MISSING`. It is not given a default, and it is not guessed at.
The user-topic route still works for it, because that route needs the
positioning rather than the search terms.

## Sources say what they can do

A hot-list service and a search API are not the same thing, and the registry
does not pretend they are.

| `query_mode` | What it means |
|---|---|
| `NATIVE_SEARCH` | the service accepts a query and returns matches for it. GitHub's search API is the one real example here: the account's terms go into the request. They are OR'd, not AND'd — GitHub ANDs space-separated terms, so asking for all of the account's words at once would ask for a repository that mentions every one of them and find nothing. The exact query is written into the plan, so a reader can see what was asked |
| `LIST_ONLY` | the service publishes a pre-ranked list. The account's terms cannot narrow it, so they are applied **locally after the fetch**. This is a filtered list, not a search |

The search plan states which is which for every source it names. Reading a
popular list and keeping what fits is a legitimate technique; calling it a
search is not.

### Failures are named

A source that fails is recorded and skipped; the others continue.

| Code | Meaning |
|---|---|
| `SOURCE_UNAVAILABLE` | the source could not be reached |
| `SOURCE_TIMEOUT` | it did not answer in time |
| `SOURCE_RATE_LIMITED` | it asked us to slow down |
| `SOURCE_DATA_MALFORMED` | it answered with something unreadable |
| `SOURCE_UNAVAILABLE_STATE` | the local TrendRadar database is absent or off |
| `SOURCE_CREDENTIALS_REQUIRED` | it needs a secret this collector does not hold |

No adapter here needs a credential. A failed source never turns into an empty
candidate list presented as a result.

### TrendRadar

TrendRadar runs outside this repository. It is read through a read-only
SQLite URI and is never written to. Four things are handled by name: the
file being absent, the file being locked, the schema having drifted (the
table no longer has a `title` column, so its rows are not read at all), and
duplicated rows (dropped, so one story is not two signals).

## The ranking is the account's

Seven components, each scored 0–10, each weighted by the account's own
percentages, each carrying the sentence explaining it:

| Component | Weight | What it measures |
|---|---|---|
| `profile_relevance` | 30 | how many of the account's declared terms the item matches |
| `evidence_availability` | 20 | whether it links to something the account can open and test |
| `freshness` | 15 | how recent it is, against the run's window |
| `audience_value` | 15 | whether it names one of the account's core audiences |
| `cross_source_signal` | 10 | how many *distinct* sources carry it |
| `originality_potential` | 5 | whether it names an angle the account can test, price or reproduce |
| `non_repetition` | 5 | whether this account has already seen it |

The hot list's own rank is never the sort key. A list's rank is a statement
about popularity among that list's readers, which is a different question
from fit for one account's readers.

**Platform counters are never added together.** A view count on one platform
and a heat index on another are not the same quantity. They are recorded on
the candidate, marked `metrics_comparable: false`, and they do not enter the
score. The one cross-source signal is a count of distinct sources, which is a
fact about coverage rather than a comparison of incompatible scales.

**An item a source gave no date for is not thrown away.** A freshness window
can only exclude what it can date. Such an item is kept, it scores zero on
freshness, and its record says its freshness could not be established — so it
is visibly weaker rather than silently present or silently missing.

## The unified contract

Both routes produce a `contentops.content-intent/v1`:

```json
{
  "schema": "contentops.content-intent/v1",
  "account_id": "x-superplay-1024",
  "account_profile_version": "2026-10-30.1",
  "route_mode": "USER_TOPIC",
  "topic": "…",
  "content_angle": null,
  "source_artifact_refs": [],
  "evidence_status": "verification_required",
  "approval_status": "pending",
  "target_pipeline": "VIDEO",
  "brief_status": "draft",
  "route_context": { "…": "the same keys in both routes" }
}
```

Everything route-specific lives under `route_context`, and its keys are
identical in both modes. A downstream consumer reads
`route_context.candidate_id` without caring whether it is `None` because the
user typed the topic or because a person picked a candidate. That is what
keeps `if route == HOTSPOT` out of the downstream code.

The brief package on disk is `00_brief/brief.json`, and it carries two
documents in the repository's *existing* contracts:

- `candidate` — `contentops.content-candidate/v1`, the topic scored in the
  shape the topic contract already defines;
- `forecast` — `contentops.evidence-feasibility/v1`, which captures the topic
  needs, who produces them, whether they are available, and what to do if
  they are not.

Both are validated with the repository's existing validators before the file
is written. A brief that would not survive those contracts is not written.

## The state machine

One machine, in `contentops.routing.models`, with no force path.

```
ACCOUNT_REQUIRED ─┬─▶ ACCOUNT_DNA_MISSING ─▶ BLOCKED
                  └─▶ ROUTE_SELECTION_REQUIRED
                         ├─▶ SEARCH_PLAN_READY ─▶ CANDIDATES_READY ─▶ TOPIC_SELECTED
                         └─▶ INPUT_REQUIRED ─┬─▶ OUT_OF_PROFILE_REVIEW_REQUIRED
                                            └─▶ EVIDENCE_REQUIRED ─▶ BRIEF_READY
                                                                        │
        APPROVED_FOR_PRODUCTION ◀── AWAITING_HUMAN_APPROVAL ◀──────────┘
```

Four of those states are the point of the whole thing:

- **`CANDIDATES_READY` cannot become a brief.** There is no edge from it to
  `BRIEF_READY`. A topic is chosen by a person, or not at all.
- **`OUT_OF_PROFILE_REVIEW_REQUIRED`** stops a user topic that the account's
  own declaration does not cover. The owner may change the topic or approve
  the exception explicitly; the override is recorded with who and why.
- **`AWAITING_HUMAN_APPROVAL`** is where every brief waits.
- **`BLOCKED` is terminal.** A blocked run is a record of what stopped it.

### What a state is not

A brief that says `evidence_status: verified` means the evidence *paths* were
recorded. It does not mean the claims inside them are true, and it does not
mean the video is good. The copy review, downstream and unchanged, is still
what stands between a script and a render. This router is a second gate at a
different point — before production, not before rendering — and it grants no
publishing or paid-media authority of its own.

## The commands

```bash
python scripts/content_route.py accounts
python scripts/content_route.py sources
python scripts/content_route.py start --account x-superplay-1024 --mode hotspot
python scripts/content_route.py start --account x-superplay-1024 --mode topic \
    --topic "如何使用 LangGraph 开发可靠的 Agent？"
python scripts/content_route.py candidates --account x-superplay-1024
python scripts/content_route.py select --candidate CAND-XXXX --by "Founder"
python scripts/content_route.py status --run RUN-XXXX
python scripts/content_route.py resume --run RUN-XXXX
python scripts/content_route.py approve --run RUN-XXXX --reviewer "Founder" --confirm \
    --project my-episode
```

`accounts` lists the accounts and whether each can be routed. `sources` lists
the source catalog and what each source can actually do — the list the
account's allowlist is drawn from.

`--json` on any command prints the same result as JSON. `approve --project`
creates the project with the repository's own scaffolder
(`scripts/new_project.py`) and puts the brief package in it, so the episode
starts where every other episode starts.

### A hotspot run, as it happens

```
选择账号：AI 技术视频账号 (x-superplay-1024)
选择模式：热点发现

已加载账号定位版本 2026-10-30.1
已生成精准检索计划：9 个来源，0 个来源被拒绝，1 个来源接受服务端查询
采集与筛选完成：抓取 18 条，拒绝 9 条，候选 7 条

候选选题：
1. 用 LangGraph 做多步骤工作流，失败重试怎么设计
2. langchain-ai/langgraph
…

请选择一个候选：content route select --candidate CAND-XXXX --by "Founder"
```

### A topic run, as it happens

```
选择账号：AI 技术视频账号 (x-superplay-future-intelligence)
选择模式：指定主题

输入主题：如何使用 LangGraph 开发可靠的 Agent？
进行账号定位检查…ALIGNED（匹配账号声明词 3 个）
生成 Content Brief…等待人工审核。

content route approve --run RUN-XXXX --reviewer "Founder" --confirm
```

## Where the state lives

The candidate pool and the run trail are stored per account in SQLite, under
`.local/content-router/` — which the repository already ignores, because a
pool of another account's candidate titles is runtime state and not source.
`CONTENTOPS_ROUTER_HOME` moves the whole directory.

Every read and write of a candidate carries the account id. Two accounts
share a database file and share nothing else: a candidate id is derived from
the account as well as the title, so the same story surfacing for two
accounts produces two candidates and neither can select the other's.

The run record keeps the profile version the run searched against. When the
account's profile changes, new runs carry the new version and old runs keep
the version they actually used.

## What this does not do

- It does not choose a topic for you. It proposes; a person decides.
- It does not publish, and it does not reach a media generator. The router
  produces a brief and stops.
- It does not claim native full-text search where a service only publishes a
  list. Every source states which it is.
- It does not add platform heat numbers to each other.
- It does not invent an account's positioning. An account with no discovery
  block gets `ACCOUNT_DNA_MISSING`, not a default.
- It does not switch a run's route. A source being down is a reason to report
  a failure, not to go and do something else.

## Where the code is

| Path | What it owns |
|---|---|
| `src/contentops/routing/models.py` | the unified contract and the state machine |
| `src/contentops/routing/account_profile.py` | resolving the DNA, and the origin check |
| `src/contentops/routing/hotspot_route.py` | Route A: plan, collect, filter, rank |
| `src/contentops/routing/user_topic_route.py` | Route B: the user's topic and its alignment |
| `src/contentops/routing/brief.py` | the brief package and its two existing contracts |
| `src/contentops/routing/router.py` | the entry point both routes are reached through |
| `src/contentops/hotspots/source_registry.py` | the source catalog and its capabilities |
| `src/contentops/hotspots/query_planner.py` | the written search plan |
| `src/contentops/hotspots/adapters.py` | reading each source, and failing by name |
| `src/contentops/hotspots/ranking.py` | the account-weighted score |
| `src/contentops/hotspots/dedup.py` | one story seen in two places |
| `src/contentops/hotspots/storage.py` | the per-account pool and the trail |
| `scripts/content_route.py` | the command line |

Tests: `tests/test_content_router.py`, `tests/test_hotspot_sources.py`,
`tests/test_account_discovery.py`. All three run offline.

See [CURRENT-STATE.md](CURRENT-STATE.md) for what was verified and when, and
[RUNBOOK.md](RUNBOOK.md) for the commands in context.
