# Editorial operations V1

Refs #216. Local advisory planning only.

## Upstream research, 2026-11-26

- [TrendRadar](https://github.com/sansan0/TrendRadar): already pinned at v6.11.0 in runtime/trendradar.lock.json and read by the existing hotspot adapter. Reuse; no second crawler.
- [RSSHub](https://github.com/DIYgod/RSSHub): candidate feeds; verify route rights and availability before live use.
- [Fider](https://github.com/getfider/fider): feedback capture/prioritization pattern.
- [Postiz](https://github.com/gitroomhq/postiz-app) and [PLANKA](https://github.com/plankanban/planka): calendar and queue patterns, no automatic posting.
- [GrowthBook](https://github.com/growthbook/growthbook): experiment design; existing learning tools remain metric authorities.
- [Umami](https://github.com/umami-software/umami): optional owned-site attribution only, not social platform analytics.
- [Streamlit](https://github.com/streamlit/streamlit): candidate UI after real usage.

No external source code copied or live integration verified.

## Run

1. `python scripts/editorial_ops.py init` creates three CSVs in ignored .local/editorial-ops (or --data-dir outside checkout), without overwriting.
2. Fill signals.csv: source URL, topic slug, kind (hotspot/search/comment/issue/job/buyer_request/review/rss), time with timezone and sanitized observation. Use the scoped hotspot import below or enter other observed signals; hotspot is not buyer evidence.
3. Fill peers.csv: observed public case URL, platform, format, hook, lesson and time. Both metric fields blank if unknown. Do not copy peer content.
4. Fill topics.csv: existing account slug/platform allowlist, native format, audience, distinct angle, series slug, hook, CTA, ISO planned date, estimated minutes, risk low/standard/high, reviewer, six manual 0..10 scores. Reviewer is planning attribution, not approval.
5. `python scripts/editorial_ops.py plan` writes editorial-plan.json locally. It contains evidence references, ranked candidate variants, calendar and series counts. Weights are uncalibrated hypotheses, not predicted views. Repeated source URL within a topic counts once; distinct URLs do not prove independent demand. No evidence yields NEEDS_EVIDENCE.
6. Founder manually selects a topic and uses existing content_route.py, signed research, copy and production gates. Publish manually, register real URL using existing tools; use existing learning scripts for actual metrics.

Cost lanes: L1 <=15 min low risk, L2 <=60 min low/standard, L3 otherwise. Planning only; never relaxes safety, copyright or approval gates.

## Scope

Tests: `python tests/test_editorial_ops.py` (synthetic only). Implements manual demand/peer ledgers, scoring, cost lanes, native plans, calendar/series summaries. Does not implement unattended feed collection, multi-user UI, randomized experiments, automated business transfer, DNA overrides, actual publication or real-account acceptance. Follow #216 and #199/#210. Keep raw data local; do not enter private identities or confidential observations.

## Existing router integration and read-only workspace

Export candidates using the existing account-scoped command (write UTF-8 JSON into a local-only directory):

`python scripts/content_route.py candidates --account x-superplay-english --json`

Save that JSON array to .local/editorial-ops/candidates.json, then:

```text
python scripts/editorial_ops.py import-hotspots --input .local/editorial-ops/candidates.json --topic agent --account x-superplay-english
python scripts/editorial_ops.py plan
python scripts/editorial_ops.py dashboard
python scripts/editorial_ops.py handoff --candidate <id> --reviewer Founder --confirm
```

The importer re-derives the existing account-scoped candidate ID using the same hotspot_route.candidate_id_for helper (the original payload does not carry account_id); it rejects wrong-account, rejected or malformed entries, deduplicates by topic/URL, and records only hotspot observations. It does not fetch anything or treat an import as verified buyer demand. Inspect editorial-workspace.html locally (read-only; no server, scripts or network). The handoff writes a JSON argv list for a human to review and execute through the existing topic route. It cannot approve research, generate media or publish. Re-run plan after editing data.

## Variant experiments and local OPC signal

`python scripts/editorial_feedback.py init` creates experiment-links.csv: link actual published content_id + post_url to the existing Strategy experiment_id, exactly one variable (hook/title/cover/cta/duration/visual_style/posting_time), arm a or b. Existing platform-learning snapshots are the sole native metrics source; variant labels never replace discovery source.

```text
python scripts/editorial_feedback.py review --experiment exp --variable hook --platform bilibili --account x-superplay-future-intelligence --format video --topic agent
python scripts/editorial_feedback.py lead --content-id CID --post-url https://example.org/post/1 --category agent --evidence-ref local-1 --reviewer Founder --consent --confirm
```

Use actual IDs and URLs, not these examples. The review reuses same-cohort metric checks, five complete samples per arm, and outputs descriptive observations only. It does not change DNA. The lead command checks an existing published index entry and requires explicit consent/confirmation; it exports a local anonymous reference for OPC review, not a payment or verified buyer demand. Manual transfer only. Native X learning remains unchanged. Tests: python tests/test_editorial_feedback.py.

## RSSHub / FreshRSS standard feed intake

Research: [RSSHub](https://github.com/DIYgod/RSSHub) and [FreshRSS](https://github.com/FreshRSS/FreshRSS) expose standard feed formats; FreshRSS also supports OPML subscription management. Reuse their feed output, not their crawler code. This adapter supports UTF-8 RSS 2.0, Atom and JSON Feed. A local export is the default no-network path; direct HTTPS fetch is explicit, one endpoint, no redirects/auth, bounded payload and timeout. Use only operator-approved public feeds; URLs with queries are deliberately refused to avoid leaking feed tokens. No provider instance or route has been live-verified.

```text
python scripts/editorial_feeds.py --input .local/editorial-ops/feed.xml --source-id rsshub-ai --topic agent
python scripts/editorial_feeds.py --url https://example.org/feed --source-id public-ai --topic agent --confirm
```

The second URL is a placeholder; replace with a real authorized public feed. Only title + public URL are admitted as RSS observations. No full article, buyer-demand classification or claim verification. Deduplicates per topic/URL, emits a local hashed intake receipt and writes the existing signals.csv. No new metric store or publishing action. Test: python tests/test_editorial_feeds.py.

## Peer benchmark and outlier research

Reference: [yt-competitor-outlier-pipeline](https://github.com/svx2027/yt-competitor-outlier-pipeline) uses format-aware peer outlier detection; [youtube-strategy-toolkit](https://github.com/LuxKim/youtube-strategy-toolkit) separates public competitor information and authorized owner analytics. Here we keep the existing peers.csv as the metric source, add context only, and do not collect private or bulk platform data.

```text
python scripts/editorial_peers.py init
python scripts/editorial_peers.py review
```

peer-context.csv links case_id to peer_alias, actual published_at, native metric definition, T+24H/T+72H/T+7D window and organic_paid. Existing peers.csv retains observed_at, source URL, metric_name and metric_value. Same platform/peer/format/metric/definition/window only. Unknown or non-organic excluded; duplicate publications rejected; at least five other posts required for leave-one-out median; ratio >=2 is an uncalibrated research lead, not causal evidence. Outputs peer-review.json; no automatic copying, source research approval or publication. Synthetic tests: python tests/test_editorial_peers.py.

## Explicit native-plan routing

The existing handoff JSON now carries platform, medium, audience, hook, CTA, series and cost lane as editorial notes, not as permission to alter the account DNA. After review, execute the existing topic router through:

```text
python scripts/editorial_ops.py route --candidate <id> --reviewer Founder --confirm
```

This recomputes the current plan, uses the existing process_utils and content_route.py start --mode topic --json (no fetch-evidence flag), records the actual run ID/state, and refuses duplicate attempts. If execution is ambiguous, reconcile the route-<id>.json receipt and existing RouterStore before retrying. No production/approval/publishing permission, no automatic cross-platform rendering. The router may reject an off-profile topic. Synthetic runner tests only; no actual user-account routing claimed.

## Editable local workbench and series review

References: [Edit Flow](https://github.com/Automattic/Edit-Flow), [PLANKA](https://github.com/plankanban/planka), [Postiz](https://github.com/gitroomhq/postiz-app), [Social Dash](https://github.com/cadenburleson/social-dash), and [social-media-skills](https://github.com/social-media-skills/skills). Borrow workflow and reporting patterns only; no new server dependency or auto-posting. Start `python scripts/editorial_workspace.py`, then visit `http://127.0.0.1:8765/` on the same machine. Edit existing candidates' date, minutes, risk, hook, CTA and reviewer; input revision protects stale forms, existing planner validates edits, routed candidates are locked. Single operator only: do not edit CSVs or run other writing commands while editing. Browser writes are loopback-only with Host, Origin and per-process token checks. No remote access, no approval or publication controls. Stop with Ctrl+C. If a process dies with a workspace-edit.lock, reconcile local writes before removing that lock.

Run `python scripts/editorial_series.py init`; fill series-links.csv with content_id, post_url, existing experiment_id and series slug for actual published works. Run `python scripts/editorial_series.py review --experiment exp --platform bilibili --account x-superplay-future-intelligence --format video --topic agent` with the actual cohort and definition. It reuses native platform-learning observations rather than copying metrics. At least five valid rate observations per group, two eligible groups, same account/platform/format/topic/window/definition and experiment. Equal top medians yield no research priority. Review founder effort and confounders. No causal conclusion, no auto-routing or duplicate content; new episodes require new evidence. Tests: `python tests/test_editorial_workspace_series.py` (synthetic fixtures only).

## OPC receiving receipt

The receiving-side implementation is proposed in [OPC-Blueprint PR #212](https://github.com/Xander-Xai/X-SuperPlay-OPC-Blueprint/pull/212). Transfer exact original lead JSON bytes manually through authorized local storage, run OPC `scripts/contentops_review_intake.py`, then return its receipt JSON. ContentOps `python scripts/editorial_feedback.py ack --receipt .local/editorial-ops/returned.json --reviewer Founder --confirm` verifies exact source SHA256 and review-only scope; duplicate receipt is idempotent, altered source or conflicting receipt fails closed. Source URLs must be canonical public HTTPS with no query, credentials or fragments. A matched local receipt is not independently authenticated remote identity, actual contact, paid demand, payment or founder approval. No actual data transferred in this PR. Synthetic tests only.

## Authorized X public observations

Reference: [official X API samples](https://github.com/xdevplatform/samples) and [X lookup docs](https://github.com/xdevplatform/docs/blob/main/x-api/posts/lookup/quickstart.mdx). The new `editorial_x_observe.py` uses fixed `api.x.com/2/tweets` read-only lookup, at most 20 explicitly selected IDs, no pagination or retries, no write scopes or post actions. Set `CONTENTOPS_X_BEARER_TOKEN` in the local environment only if you have authorized API access and accept the provider's quota/cost terms. Run `python scripts/editorial_x_observe.py --post-id 123 --topic agent --confirm` with actual IDs. Or use `--input .local/editorial-ops/x-api-export.json --observed-at <original ISO timestamp>` (no network). Missing metrics stay null, public counts cannot distinguish paid/organic, raw post text is not stored. Reports remain local `x-peer-*.json`, separate from the organic peer baseline. No live credential or actual API observation verified here. Tests: `python tests/test_editorial_x_observe.py`.
