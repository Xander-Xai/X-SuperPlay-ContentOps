# Manual Metrics Review

> Post-publication evidence, imported by hand from the creator's own export.
> No login, no scraping, no estimation.

## Why it works this way

The official figures exist, but only behind a creator session. YouTube lets an
owner export impressions, click-through rate, watch time, average view duration and
audience retention; Douyin's creator centre exposes works, completion and traffic
source data. Both require a login this repository will not perform, and a scraper
would be both fragile and against the terms it depends on.

So the operator exports, drops the file in the project, and this module imports
what is there. A metric that was not exported stays absent. It is never filled
with a plausible number, because a report with invented gaps is worse than a short
report: it looks complete.

## Layout

```text
projects/<slug>/
  metrics/
    exports/
      youtube.csv                 ← the platform's own export, untouched
      report-youtube-2026-11-08.json  ← the small wrapper described below
  receipts/
    metrics-review.json           ← written by the importer
```

## The wrapper format

`contentops.manual-metrics/v1`

| Field | Required | Meaning |
|---|---|---|
| `schema` | yes | exactly `contentops.manual-metrics/v1` |
| `platform` | yes | non-empty string, e.g. `youtube`, `douyin` |
| `work_url` | yes | the published work's URL (http/https, with a host) |
| `export_date` | yes | ISO `YYYY-MM-DD`, the day the export was taken |
| `source_file` | yes | file name under `metrics/exports/` that the numbers came from |
| `source_sha256` | yes | SHA-256 of that file, so a later edit is detectable |
| `metrics` | yes | non-empty object of `metric name -> number` |

```json
{
  "schema": "contentops.manual-metrics/v1",
  "platform": "youtube",
  "work_url": "https://www.youtube.com/watch?v=abc123",
  "export_date": "2026-11-08",
  "source_file": "youtube.csv",
  "source_sha256": "6f42b355...",
  "metrics": {"views": 1200, "ctr": 0.042, "avg_view_duration_s": 38.5}
}
```

Metric names are the operator's mapping of the export's columns. This module does
not guess which column means what — a wrong guess would be indistinguishable from
a real measurement.

## What gets rejected

Every condition is checked and **all** failures are reported at once:

- a missing required field;
- an unrecognised `schema`;
- a `work_url` that is not http(s) with a host;
- an `export_date` that is not ISO;
- a `source_file` outside `metrics/exports/`, or not present;
- a `source_sha256` that does not match the file — the export changed after the
  report was written;
- a metric value that is not a finite number (booleans included);
- an empty `metrics` object.

A rejected export does not hide a valid one: each file is reported separately, and
the valid ones are still imported.

## The receipt

`receipts/metrics-review.json`, `contentops.metrics-review/v1`:

- `imported` — each accepted export with its source hash;
- `rejected` — each refused file and every reason;
- `observations` — factual lines only, e.g.
  `youtube 2026-11-08 https://...: views=1200`;
- `next_variable` — **one** variable worth reporting or watching next round, with
  the basis for choosing it;
- `constraints` — `modifies_script: false`, `modifies_qc: false`,
  `modifies_production_ready: false`.

`next_variable` is chosen deterministically: a metric reported in only some exports
first (the reporting gap breaks later comparison), otherwise the metric with the
widest spread across exports, otherwise the first metric of the single export. It
names a variable. It does not say what to change in the video, and no threshold
from a third-party article is written into code.

## What this cannot do

- It cannot prove the export is genuine. A hash proves the file did not change
  after the wrapper was written, not that the numbers are real.
- It does not reconcile column names across platform export revisions. A renamed
  column surfaces as a missing metric, not as a silent zero.
- It does not feed anything upstream. Metrics describe a published work; they can
  never re-open its QC verdict or make it publishable.
