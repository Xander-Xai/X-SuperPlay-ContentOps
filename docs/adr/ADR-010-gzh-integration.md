# ADR-010: WeChat Official Account workflow via an adapter, not a copy

## Status

SUPERSEDED by [ADR-011](ADR-011-single-home-platform-tracks.md) — the "keep it
external" decision no longer holds because the checkout and its remote are being
retired. The adapter seam and the hard boundaries below are still the contract that
the vendored copy must honour.

## Context

The Future Intelligence account needs a WeChat Official Account (公众号) track. A
separate, working repository already exists for exactly that account:
`D:\Projects\gzh_x未来智能` (HEAD `93645f1`, branch `main`), whose
`gzh_未来智能/workflow-identity.yaml` declares `account_id: thinktank`,
`display_name: X超玩•未来智能` — the same account this repository calls
`x-superplay-future-intelligence`.

That repository is not a script collection. It is a governed workflow:

- a ten-stage ordered gate (`environment_ready → topic_selected → research_complete →
  research_reviewed → draft_complete → content_reviewed → formatted → illustrated →
  final_reviewed → draft_submitted`), enforced by `scripts/workflow_gate.py` with
  per-stage structural and semantic contracts;
- it mints its own receipts (`source-verification.json`, `source-evidence.json`,
  `evidence-provenance.json`, `evidence-lineage.json`, `approval-events.json`,
  `publish-preflight.json`, `publish-receipt.json`) and re-derives them if they
  disagree with the bytes on disk;
- a workspace whose directories are allocated by `scripts/matrix_init.py` and
  registered in `registry/workspace-index.json` under a lock — hand-created article
  directories are rejected;
- 40 skills, its own visual QA stack, and a publish path that ends at a **WeChat
  draft** (`draft/add`) with a `draft/get` read-back, never at public publication;
- no CI, and tests that are per-script (`python scripts/test_workflow_gate.py`).

Its narrative contract is a 2500–5000 character article with at least three H2
sections and at least one image per section. Video is explicitly a **downstream
derivative**: `scripts/media_guard.py` only admits video/short-video/audio after the
article reaches `final_reviewed` or `draft_submitted`.

## Decision

**Keep `gzh_x未来智能` as its own repository. Do not copy its source into
ContentOps, and do not fork it.** Integrate through one adapter boundary, in
ContentOps, that hands *material* across and lets the GZH repository mint every
receipt itself. Make the workflow durable with a cold archive instead of a copy.

### Durability first: the folder may be deleted

The working copy is not a cache of something reproducible. Its history **diverged
from GitHub origin**: `origin/main` is `e9303d1`, the working copy is `93645f1`, and
the four local commits exist on no remote. Deleting the folder today would destroy
them, plus 718 tracked files and 243 MB of vendored skills.

So before any cleanup, the repository is preserved as a verified git bundle outside
both trees:

| Item | Value |
|---|---|
| Archive | `D:\Archives\repos\gzh-thinktank\2026-10-30\gzh-thinktank.bundle` |
| Bytes / SHA-256 | `14,724,716` / `fc6965c076af07d1e6842b06bb11afae760d4315d950545604a041a97e4fb4e7` |
| Commit / tree | `93645f1…` / `7b75e4e8…` |
| Tracked files | 718 |
| Verified at creation | the bundle restores a clone whose HEAD and tree object are identical |

`scripts/gzh_pin.py` records those values and refuses a restored checkout that
disagrees; `tests/test_gzh_pin.py` pins the refusals. Restore is one command:

```powershell
git clone D:\Archives\repos\gzh-thinktank\2026-10-30\gzh-thinktank.bundle D:\Projects\gzh-Future-Intelligence
python scripts\gzh_pin.py --checkout D:\Projects\gzh-Future-Intelligence
```

Credentials (`aws.env`, `.aws-article/`) are gitignored and were never read; they are
re-issued from the WeChat console, not archived.

### Why not copy it in

- 243 MB of tree, of which ~929k lines are vendored skill packs that are already
  re-acquirable; committing that into ContentOps would bloat the repository for no
  gain in durability, since a bundle preserves it exactly.
- Two gate systems in one tree would diverge the first time either changes; the copy
  would need its own migration for every GZH commit, and the receipts would name a
  path that no longer matches.
- GZH's gates already refuse foreign receipts. Copying would create a tree that looks
  authoritative but whose `workflow_gate.py` still has to be the one that runs.
- ContentOps' own rule rejects a sixth production system. This is the same failure in
  a different costume.

### Why not fork

A fork is a source edit with no upstream. GZH is not upstream in the ADAPTER >
EXTENSION > CUSTOM SKILL > UPSTREAM PATCH > FORK sense — it is a sibling repository
owned by the same person, and its history is the record of its gates.

### The one seam

`ContentOps research → GZH topic_selected / research_complete → hand back at
research_reviewed`.

ContentOps owns what it already owns: the topic, the sources, the claims and the
evidence ledger. GZH owns everything WeChat-specific from `draft_complete` onward.
The adapter writes only the files GZH expects as *input*, then invokes GZH's own
scripts to mint receipts and advance two stages.

The adapter must write, in the GZH article workspace:

| Stage | Files |
|---|---|
| workspace | created by `route_content.py --topic-mode user_material` + `matrix_init.py`; never by hand |
| `topic_selected` | `topic-card.md`, `topic-contract.yaml`, `topic-cluster.md`, `content-brief.yaml`, `seo-report.json`, `cta-contract.json` |
| `research_complete` | `research.md`, `sources.json`, `source-snapshots/*.raw`, `evidence/*`, `evidence-plan.json` |
| `research_reviewed` | `source-review.json` |

and must invoke `verify_sources.py`, `source_evidence.py audit`, `source_review.py`
and `workflow_gate.py --advance` rather than writing their outputs.

### Hard boundaries

1. **Credentials never cross.** `aws.env` and the WeChat AppID/AppSecret stay outside
   both repositories. ContentOps must never read them; GZH reads them through
   `publish_preflight.py --env <path outside the repo>`.
2. **No foreign receipts.** ContentOps must not write `source-verification.json`,
   `evidence-lineage.json`, `approval-events.json` or any `publish-*` file. GZH
   re-derives and rejects them.
3. **No video upstream.** A ContentOps film is not an input to a GZH article. If a
   video is wanted for 公众号, it is produced *after* `final_reviewed`, under
   `media_guard.py`.
4. **No copying of GZH's skills into ContentOps.** Where a skill name collides
   (`gzh-design`, `wechat-publisher`, `card-design`), the account's own repository
   wins for its own stage, and ContentOps keeps the Easel runtime's copy for video.
5. **Pin the archive, not a branch.** `scripts/gzh_pin.py` binds the commit, tree,
   tracked file count and bundle digest. A restored checkout that disagrees is
   refused — the same discipline as the Easel runtime, whose 981/982 state is the
   cautionary example. Cloning upstream does **not** reproduce this history.

## Consequences

- A 公众号 track exists in ContentOps as *routing and receipts*, not as a second
  implementation.
- The adapter is a new, testable surface that fails closed when the GZH repository is
  absent (it lives outside this repo and will not exist on CI or another machine).
- The two repositories must agree on one identity: `thinktank` ↔
  `x-superplay-future-intelligence`. A mapping file, checked by both sides, is
  required; neither repository may silently rename the account.
- ContentOps gains no WeChat publishing capability of its own. That remains GZH's
  `create_draft` + read-back path, and it stays draft-only.

## Open questions

1. Is the 公众号 article the upstream or the downstream of the video? GZH's design
   says article-first; the current ContentOps habit is video-first. One of them has to
   give, and it is an account decision.
2. Who authors the article body? The adapter can carry topic + sources + claims, but
   GZH's `draft_complete` contract is a human-scale 2500–5000 character article.
3. Does the account want the 公众号 track to run on the same cadence as the video
   tracks, or only when an episode has enough written depth?
4. **Should the four local commits be pushed to a remote the Founder controls?**
   They are not on `origin`. Pushing would make the GitHub repository the durable
   home instead of (or as well as) the bundle — but it is an outward-facing action on
   a divergent history, so it needs an explicit decision, not an inference. Until
   then the bundle is the only complete copy.

## Not decided here

Nothing in this ADR changes any existing gate. The ContentOps platform work in
`derive_variants.py` and the aspect-aware `qc_video.py` is independent of it.
