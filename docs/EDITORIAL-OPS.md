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

Tests: `python tests/test_editorial_ops.py` (synthetic only). Implements manual demand/peer ledgers, scoring, cost lanes, native plans, calendar/series summaries. Does not implement live feed collection, editable UI, metrics experiments, business handoff, DNA overrides, actual publication or real-account acceptance. Follow #216 and #199/#210. Keep raw data local; do not enter private identities or confidential observations.

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

The importer rejects wrong-account, rejected or malformed entries, deduplicates by topic/URL, and records only hotspot observations. It does not fetch anything or treat an import as verified buyer demand. Inspect editorial-workspace.html locally (read-only; no server, scripts or network). The handoff writes a JSON argv list for a human to review and execute through the existing topic route. It cannot approve research, generate media or publish. Re-run plan after editing data.
