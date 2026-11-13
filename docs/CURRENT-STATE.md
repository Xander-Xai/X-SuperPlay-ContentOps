# Current State

[English](CURRENT-STATE.md) | [简体中文](CURRENT-STATE.zh-CN.md)

> What runs today. Verified facts only. No aspirations, no stale claims.
>
> Last verified: 2026-11-13 against main @ `9738186` (PR #174 merged); cross-platform extension remains a PR candidate.
> Main contains the X-only local analyzer; this candidate adds cross-platform local metric learning and reviewed Topic routing. No private account data included.

> Facts below describe `main`; deferred or rights-blocked work is labelled as such.
> Sections below the "Layer status" table are historical milestone records;
> they describe how a capability was proven, not what is current.

## Layer status (2026-11-12)

| Layer | Status |
|---|---|
| M5 evidence chain, media contracts, QC, media-use adapter, skill router/authorization | implemented |
| Stable production entry (`scripts/make_content.py`, `scripts/production_gates.py`) | implemented (PR #157); seven fail-closed VIDEO gates (`account`, `copy_review`, `evidence_links`, `asset_sufficiency`, `avatar_bookends`, `style_audio`, `runtime_readiness`) and five GRAPHIC_TEXT gates (`account`, `copy_review`, `evidence_links`, `asset_rights`, `runtime_readiness`); a direct `m5_production.py` / `produce_video.py` run is a diagnostic path |
| Platform registry (`config/registry/platforms.json`, `src/contentops/platforms/`) | implemented on `main` (PR #101, routes added in #141); 9 local entries for 9 Strategy platforms, one `INTEGRATED` (`x`), eight `PLANNED` |
| Video delivery (`scripts/video_deliver.py`) | implemented offline: `plan` / `pack` / `status` / `record`; `dispatch` requires an operator grant. No receipt in this repository records a published URL |
| Graphic delivery (`scripts/platform_delivery.py`, `scripts/graphic_deliver.py`, `src/contentops/platforms/wcs_bridge*`) | implemented offline: packs and draft-only handoff through an external CLI across a process boundary (`wechatsync`). No `PUBLISHED` branch; URL recording is a human action |
| Card and article rendering (`scripts/render_cards.py`, `scripts/render_article.py`) | implemented (PRs #149, #152); validates through the pinned Easel card/gzh skills and writes receipts with `production_ready: false` |
| ASR backcheck gate (`scripts/m5_production.py::stage_asr_backcheck`) | implemented (PR #150); `SKIPPED` without `SILICONFLOW_API_KEY`, blocks human review on a coverage failure, never approves |
| M5 characterization baseline (`scripts/m5_characterize.py`) | implemented (PR #153); `docs/m5-baseline/m5-characterization-2026-11-10.md` fixes slice-1 pass counts for #140 |
| Content Bundle consumption + two-format handoff (`src/contentops/content_kernel/`) | implemented offline; VIDEO and GRAPHIC_TEXT plans, no publication |
| Easel host guard (`src/contentops/easel/`, `scripts/easel_host.py`) | implemented offline (PR #108); `HOST_BLOCKED` on this machine (FastAPI/uvicorn absent), mutations denied |
| Graphic manual package (`src/contentops/graphic/`, `scripts/graphic_package.py`) | implemented offline; stops at `AWAITING_MANUAL_REVIEW`; no delivered package yet |
| Content router, account DNA, brief/script/design stages | S1–S4 on `main` (PRs #114, #118); 15 hotspot sources registered with 1 `NATIVE_SEARCH` (GitHub) and 14 `LIST_ONLY`, opened to both account DNAs in #157; brief→M5 bridge merged, still gate-bound to a human-approved brief |
| X / GZH platform tracks | X manual-only gate (#127); GZH renderer, SDK adapter, workflow runner and a `DRAFT_ONLY` draft path (#145, #152); both verify and never publish, rights unresolved (Issues #51, #56). **The XHS runtime adapter was removed on 2026-11-09** (`src/contentops/xhs/` is empty, `graphic_workflow.py` names gzh/x/video only); only the `xiaohongshu_video` registry row and delivery-channel config remain. Every registry row except `x` stays `PLANNED` |
| Motion workflow (sample gate, handoff, spec) | implemented on `main` (PRs #122–#124); region picking from verifiable source anchors (#142) |
| M5 E2E runs | three real-source runs on `main` (#117, #119), all `PENDING_FOUNDER_REVIEW` |
| MiniMax speech, image, H3 video | implemented; verified subsets recorded below |
| Production ready | **false** for every track |
| Publication count | **0** — no delivery package has a real platform URL |

## Git

> **Git state is re-verified below at 2026-11-12 (read-only documentation
> sync).** Every other section below it is a historical snapshot kept for
> traceability; none of them is the current state.

### Git — verified 2026-11-13 (read-only remote baseline + PR candidate)

| Property | Verified value |
|---|---|
| Default branch | `main` — protected @ `9738186` (read-only GitHub branch query on 2026-11-13) |
| Branch delta | PR #174 candidate adds local-only X learning; NOT merged into main, NOT a platform publication |

The detailed 2026-11-12 snapshot below is retained as a historical record. No claim is made that the branch's X local CSV tool exists on the default branch.

### Git — verified 2026-11-12 (read-only documentation sync)

| Property | Verified value |
|---|---|
| Default branch | `main` — protected @ `c1da6dd` (PR #159, governance registry pass, committed 2026-11-11 19:56Z). Preceding merges: `fed3dd3` (#157 open all 15 hotspot sources) ← `1bcb2fb` (#156) ← `3358158` (#155) ← `bcd5dd1` (#154) |
| Open PRs | **1**: #158 `docs(test): add isolated overseas channel candidate catalog without runtime registration` — documentation and test only, no runtime registration |
| Open issues | **4**: #7 (EPIC), #51 / #56 (OPEN / DEFERRED rights gates), #140 (M5 stage split; slice 1 landed via `e4987fa8`) |
| Remote branches | **3**: `main`, `archive/minimax-wt-snapshot-20261110`, `feat/overseas-channel-candidates-20261111` (PR #158; registry status `active`, review date 2026-12-11) |
| Remote tags | **2**: `archive/converge-a2910c6`, `archive/pr1-pr2-1c127df` — unchanged |
| Branch protection | 3 required checks (`Tests (ubuntu-latest)`, `Tests (windows-latest)`, `Repo policy checks`), `strict=true`, `enforce_admins=true`, 0 approvals, linear history, no force push, no deletion, squash only |
| Local worktrees | **1**: the primary worktree only |
| Stash | **0** |
| CI on `main` | `CI @ c1da6dd = success`; `CI @ fed3dd3 = success` |
| Local policy gates | `check_branch_registry.py --today 2026-11-12` PASS (4 branches, 1 persistent, 0 retire-due); `check_untracked_projects.py` reports 0 untracked projects; `check_governance_ledger.py` PASS after this sync |

This round changed documentation only; no runtime behaviour, registry status or
platform row was touched. The Git rows above were read from the live GitHub API
(commit head, open PR/issue lists, branch list, tag list, protection object,
workflow runs) on 2026-11-12, and the local gates were run on this machine.
The ledger check that ships with the repository remains **offline
internal-consistency only** — it does not query GitHub and is not evidence
about remote state. `docs/PLATFORM-INTEGRATION-STATUS.md` was corrected in the
same pass: it still listed a `xiaohongshu_image` registry row that no longer
exists.

### Git — verified 2026-11-11 (governance round 4)

| Property | Verified value |
|---|---|
| Default branch | `main` — protected @ `bcd5dd1` (PR #154, squash-merged 2026-11-10 15:32Z). Evening chain: `9bb66cee` (#150) → `45a1cfe6` (#151) → `03571275` (#152) → `e4987fa8` (#153) → `bcd5dd18` (#154) |
| Open PRs | **0** — explicit `state=open` query returned `[]`; the 100 most recently updated PRs are all closed |
| Open issues | **4**: #7 (EPIC), #51 / #56 (OPEN / DEFERRED rights gates), #140 (M5 split roadmap; slice 1 landed via #153). #147 closed 2026-11-10 14:52Z |
| Remote branches | **2**: `main` + `archive/minimax-wt-snapshot-20261110` (@`7aef6ae`, deliberate archive of 2,300 uncommitted Huashu lines; registered as `archived`) |
| Remote tags | **2**: `archive/converge-a2910c6`, `archive/pr1-pr2-1c127df` — local and remote SHAs match |
| Branch protection | 3 required checks (`Tests (ubuntu-latest)`, `Tests (windows-latest)`, `Repo policy checks`), `strict=true`, `enforce_admins=true`, linear history, no force push, no deletion, PR required, 0 approvals; squash only, `delete_branch_on_merge=true` |
| Local worktrees | **1**: the primary worktree only. The `pr2-gzh-articles` worktree named in the previous snapshot was removed in the 2026-11-10 drift cleanup |
| Stash | **0** — the pre-slicing snapshot named in the previous snapshot no longer exists |
| CI on `main` | `CI @ bcd5dd1 = success`; `Easel Upstream Watch @ bcd5dd1 = success` |
| Local policy gates | `check_untracked_projects.py` exit=0 after the `test-huashu-local-l141dino` experiment moved into `projects/_local/`; `check_branch_registry.py --today 2026-11-11` PASS |

Round 4 changed no runtime behaviour. It corrected the ledger, registered the
archive branch and this governance branch, retired the stale local
remote-tracking refs, and added an offline ledger-consistency check. The new
check verifies **internal consistency only** (documented SHA/date across both
language mirrors and the branch registry); it does not query GitHub and must
never be read as a verification of live remote state. #51 and #56 stay OPEN /
DEFERRED; the archive branch is retained.

### Git — verified 2026-11-10 evening (merge sequence #141–#150 + governance round 3)

| Property | Verified value |
|---|---|
| Default branch | `main` — protected @ `9bb66cee` (PR #150, squash-merged 2026-11-10 ~21:30); chain this evening: `dbc72bc3` (#139) → #141–#146 (drift slices A–F) → `6efe3763` (#148 registry catch-up) → `c0154c56` (#149 card renderer) → `9bb66cee` (#150 ASR backcheck) |
| Open PRs | **0** |
| Open issues | 5: #7 (EPIC), #51 / #56 (DEFERRED rights), #140 (M5 split roadmap), #147 (drift convergence — body complete; closing with receipt) |
| Remote branches | 2: `main` + `archive/minimax-wt-snapshot-20261110` (deliberate archive of 2,300 lines of uncommitted Huashu work; not an active branch, not in the registry's active list) |
| Remote tags | 2: `archive/converge-a2910c6`, `archive/pr1-pr2-1c127df` (island snapshots, pushed 2026-11-10 evening after living local-only since the A3 archive) |
| Branch protection | unchanged: 3 required checks, squash only, linear history, admin-enforced |
| Local worktrees | 1: `D:/Temp/AI-Agents/claude/pr2-gzh-articles` (692-line GZH article renderer, salvage PR in progress) |
| Stash | 1: pre-slicing snapshot, superseded by #141–#146 pending a content-level diff before drop |
| Session hygiene | AGENTS.md §10 added 2026-11-10 (zero invisible work; archive actions complete only when pushed; registry entries validated locally before commit) |

The evening sequence merged every drift slice from issue #147 plus both island
salvages identified in the A3 audit: the card renderer (#149, from
`archive/pr1-pr2-1c127df`) and the SiliconFlow ASR backcheck gate (#150, from
`archive/converge-a2910c6`; the QC single-verdict rework and the
checkout-guard removal found on that island were deliberately **not** ported).
#148 exists because the registry entries for #142–#146 were stripped from
their branches during a transport outage and re-landed post-merge; its first
CI attempt failed on `check_branch_registry` requiring non-null `expires` —
the rule is now stated in AGENTS.md §10 so the next registry edit starts from
a local validation instead of a red run.

### Git — verified 2026-11-10 (governance execution round 2, after #132 / #135 / #133)

| Property | Verified value |
|---|---|
| Default branch | `main` — protected @ `b6a61536` (PR #133, squash-merged 2026-11-10); previously `87142441` (#135), `60006bc7` (#132), `26618086` (#138), `44665ab1` (#137) |
| Open PRs | **0**. Squash-merged 2026-11-10: #138 (`2661808`), #132 (`60006bc`, Owner human visual review PASS), #135 (`8714244`), #133 (`b6a6153`). The two stacked PRs (#135, #133) were **re-landed from `main`** before merge: main was merged into each branch (fast-forward push, no force), collapsing the diff back to the true delta (4 files / +898−1 and 7 files / +502−12) |
| Open issues | 3: #7, #51, #56 — #51 / #56 are **OPEN / DEFERRED**, not delivered. **#6 CLOSED** (Founder review PASS on the three real-source MP4s; D-1 resolved) |
| Remote branches | 1: `main` only. `chore/governance-guardrails-20261110`, `feat/automatic-video-production`, `feat/jianying-draft-handoff` and `refactor/architecture-adapters-20261109` were **auto-deleted** after their PRs merged (`delete_branch_on_merge: true`); no branch was removed manually |
| Branch protection | required checks `Tests (ubuntu-latest)`, `Tests (windows-latest)`, `Repo policy checks`; PR required (0 approvals); linear history; no force push; no deletion; **`enforce_admins: true` (enabled 2026-11-10, Owner-authorized)**; `/rulesets` = `[]` |
| Merge policy | squash only; `delete_branch_on_merge: true` |
| Local worktrees | 9 (including 2 detached `D:/Temp/ci-m5*`) — audited only, none removed |
| Descoped work | [DEFERRED-WORK.md](DEFERRED-WORK.md) D-2…D-6 unchanged; **D-1 resolved** by the #6 closure above |

`main` remains the only *persistent* branch — the registry
(`config/governance/branch-registry.json`) now lists exactly that state. The
Owner-authorized execution round (2026-11-10 ~16:00–16:59 +08:00) merged
#138 → #132 → #135 → #133 in that order, each after exact-head 3/3 required
checks (update-branch / re-land + fresh CI where `strict: true` required it),
and enabled admin enforcement on the protection rule. **No branch was manually
deleted, no worktree was removed, no issue was closed except #6 with an
evidence comment.**


`scripts/check_branch_registry.py` validates the branch registry offline;
`scripts/check_pr_size.py` reports PR size / coupling metrics from a git log
stream (report-only until an Owner enables `--strict`). Both are wired into
CI and covered by `tests/test_governance_checks.py`. The `main` SHA above
remains a verified time-point snapshot, not a generated field.

### CI coverage note — stacked PRs (institutional exception, now historical)

**Historical (2026-11-10):** the stacked PRs described here (#133, #135) were
re-landed from `main` and merged the same day, so the exception below no longer
applies to any open PR. Retained because the standing policy decision remains
in force.

`main`'s `.github/workflows/ci.yml` uses `pull_request.branches: [main]`, so a
PR whose **base is not `main`** (#133, #135) gets no PR-triggered required checks
from `main`'s workflow. Their "3/3 green" is a **head push run**, not a current
PR check; a same-named job passing on a stacked PR is **not** evidence that
`main`'s protected checks are satisfied. `main`'s push filters also omit
`refactor/**` — #133 carries its own `refactor/**` trigger, which produced its run.

**Decision: do not widen `pull_request.branches` with `feat/**`.** That field
filters base branches; adding it would legitimise feature branches as persistent
baselines. Stacked PRs are a temporary, explicitly registered exception and must
be re-landed from `main`. Every new `tests/test_*.py` must still be registered in
`ci.yml` (`check_repo_policy.check_test_suites_registered_in_ci`). Verified at
`main f7cb2328`: `git merge-tree --write-tree` is clean for #132 (2 behind / 75
ahead), and #134 / #132 add 4 and 12 differently named CI steps with no
collision. #136's review-only handoff layer is now on `main`; #132 does not yet
contain any of its three files, so wiring the render layer to it is a separate,
human-gated change.

### Git — state at the 2026-11-04 verification (historical, superseded above)

| Property | Value |
|---|---|
| Default branch | `main` — protected |
| `main` | `218c91d` |
| Open pull requests at verification | none before PR #131 was opened for this reconciliation |
| Branches at verification | local and remote both carry `main` only; no non-`main` branch exists |
| Main protection | **PROTECTED** — required status checks + PR + no force push + no deletion + linear history (admin enforcement off) |
| Required checks | `Tests (ubuntu-latest)`, `Tests (windows-latest)`, `Repo policy checks` |
| Branch strategy | Issue-scoped short-lived branches, squash merge, auto-delete on merge |
| Recent merges | #129/#130 TrendRadar runtime tier; #127 X editorial workflow; #125 GZH/XHS graphic adapters; #121 GZH adapter; #118 S4 stages; #117/#119 M5 E2E runs |
| Consequence | `main` is the only persistent branch; descoped work lives in [DEFERRED-WORK.md](DEFERRED-WORK.md) and open questions stay on their issues |

## Easel Runtime

| Property | Value |
|---|---|
| Version | v0.2.1 |
| Commit | `3fe2d9904c1619281ef57f81d9ee0b7854998399` |
| Path | `.runtime/easel/` |
| Acquisition | Git clone of the pinned tag, checked out with `core.autocrlf=false` and `core.eol=lf` |
| Verified | 982/982 blob SHA-1 matched upstream tree (`scripts/verify_easel_runtime.py`) |
| Re-verified | 2026-11-01 on this branch: 982 files, 0 missing, 0 mismatch, 0 extra |
| Line endings | A Windows checkout with `core.autocrlf=true` yields **847 blob mismatches** while `resolve_easel.py --offline` still reports `OK`, because that command proves git HEAD, not content. Verify content before trusting the runtime |
| Executed surface | `skills/openclaw/auto-short-video/scripts/assemble.py` (composition) and `skills/shared/scripts/tts.py` (V1 narration only; M5 uses Windows SAPI) |
| Independent cross-check | 2026-10-31 against the official `v0.2.1` release archive: 982 files, 0 missing, 0 mismatch |
| Local extras | `outputs/` and `__pycache__/` only; no tracked file differs from upstream |
| Lock file | `runtime/easel.lock.json` |
| Provenance | `runtime/easel-runtime.json` |
| Upstream stable | v0.3.0 (2026-10-12) — **not adopted**: 158 commits, skills moved from `skills/openclaw/` to `skills/builtin/`, `assemble.py` changed, and the tag was force-replaced upstream |

## TrendRadar Runtime (2026-11-04)

| Property | Value |
|---|---|
| Version | v6.11.0 |
| Commit | `ceabb027fe9bbdafec59dbbfa12cb46c2ba256ce` |
| Repo | `https://github.com/sansan0/TrendRadar` |
| Path | `.runtime/trendradar/v6.11.0/` (gitignored, outside the repository) |
| Acquisition | git clone with full `.git` metadata, checked out on the pinned tag |
| Verified | 2026-11-04: the source tree was diffed against a fresh shallow clone of tag `v6.11.0` — identical except the local config delta below |
| Local config delta | `config/config.yaml`: notification, AI analysis, AI translation and HTML report all off (`config.yaml.orig` kept); the deployment runs as a pure API-free crawl whose output feeds the hotspots adapter |
| Consumed by | `src/contentops/hotspots/adapters.py` (`TrendRadarSqliteAdapter`, read-only) and `scripts/router_schedule.py` (drives `python -m trendradar` through the vendored `.venv`) |
| Run verified | 2026-11-04: one real crawl from the new home exited 0 in 70.8 s and wrote `output/news/2026-11-04.db` (255 rows); the adapter reads it |
| Lock file | `runtime/trendradar.lock.json` |
| Known defect | TrendRadar's own CLI crashes on a GBK console when it prints emoji; `router_schedule._crawl` always injects `PYTHONUTF8=1`, so the scheduled path is unaffected |
| Upgrade stance | do NOT auto-upgrade (pin note); the SQLite adapter was written against the v6.11.0 schema — re-verify before adopting a newer tag |
| Merged in | PR #129 |

## Easel Host (2026-11-02)

The Owner adopted the full Easel system as the production base (ADR-016). This
section records only what was actually run; the workbench/agent surface is not
a verified integration yet.

| Property | Value |
|---|---|
| Entry point | `scripts/easel_host.py status` / `serve` |
| `status` result on this machine | `HOST_BLOCKED` — `HOST_DEPENDENCY_MISSING:fastapi`, `HOST_DEPENDENCY_MISSING:uvicorn` |
| Pin reported | v0.2.1 / `3fe2d99` |
| Runtime bytes | `status --verify-bytes` → `VERIFIED`, 982/982 blobs (run 2026-11-02); `serve` always performs this comparison |
| Bind | `127.0.0.1` only |
| Methods | `GET`, `HEAD`, `OPTIONS` |
| Scopes | `lifespan` passes; websocket scopes are closed before upstream |
| Mutations | denied before upstream: publish, login, credentials, settings, env install, delete |
| Guard tests | `python tests/test_easel_host_guard.py` — 13/13 |
| Host authority | none over approval, publication, provider spend or accounts |
| What was not done | no dependency install, no credential/profile read, no account login, no host process started, no publication |

## Coding-Agent Driver (2026-11-02)

| Property | Value |
|---|---|
| Entry | `scripts/agent_drive.py status` / `plan` / `run` |
| Hosts on this machine | `claude`, `codex`, `opencode` — all present (ADR-017) |
| VIDEO steps | `host-status` → `produce-video` → `qc-video` → `human-review` (`HUMAN_ONLY`) |
| GRAPHIC_TEXT steps | `host-status` → `produce-graphic` → `human-review` (`HUMAN_ONLY`) |
| Authority | no publish, credential, install or approval step; a driver asking for `human-review` is refused |
| Execution | fixed argv, `--execute` required; every run writes `receipts/agent-driver-<step>.json` |
| Host requirement | none — `host-status` is a read step, not a dependency |
| QC binding | `qc-video` runs `qc_video.py --video <slug>.mp4` and requires `receipts/qc-report-<slug>.json`; that report must declare `graded_target: project://final/<slug>.mp4` and the render must still exist |
| QC verdict | a `FAIL`, a non-current report, a report for another render, or a report whose render is gone never completes the step |
| Tests | `python tests/test_agent_driver.py` — 29/29 |

## Content Router and Brief Bridge (2026-11-04)

| Property | Value |
|---|---|
| Entrances | `HOTSPOT_DISCOVERY` (the account DNA plans and ranks the sources) or `USER_TOPIC` (the user's topic is never replaced); entry `scripts/router_e2e.py` |
| Sources | GitHub search is the only server-side query; 13 list-only sources (GitHub Trending, 知乎, 微博, 掘金, V2EX, 36氪, Hacker News, Product Hunt, IT之家, 抖音, 哔哩哔哩, 百度, Solidot) are read and filtered locally; a local TrendRadar database is read-only. A source not on the account's allowlist is never contacted |
| Account DNA | `config/accounts/x-superplay-1024.json` and `x-superplay-future-intelligence.json`; every keyword cites the DNA field it came from, and `scripts/check_account_dna.py` fails a citation that does not resolve |
| Choice | a candidate list is a proposal; the state machine has no edge from `CANDIDATES_READY` to a brief without a person (`select` → `approve`) |
| Draft | `scripts/brief_script.py` writes `script/lines.json`, `claim-map.json`, `storyboard.json`, `master.md` from collected, hashed material only; a thin pack is `DRAFT_CONTENT_INSUFFICIENT`, never padded |
| Bridge | `scripts/brief_to_m5.py` converts the approved draft into `script/script.json`, `script/claims.json` and `sources/source-refs.json`; every placement needs a registered asset, every factual claim needs a stated permission and a quote that occurs in the saved document |
| Copy gate | M5 refuses a brief-driven project (`00_brief/brief.json`) whose final copy is unreviewed or stale; a legacy sample without a brief keeps its historical path |
| Schedule | `scripts/router_schedule.py run` / `status`; `scripts/router_observe.py --report --days 7`; the crawl home defaults to the pinned TrendRadar runtime (`.runtime/trendradar/v6.11.0/`), overridable by `TRENDRADAR_HOME` or `--trendradar-db` |
| Tests | `test_content_router.py` (61), `test_hotspot_sources.py` (51), `test_account_dna.py` (23 on a clean checkout), `test_account_discovery.py` (23), `test_script_draft.py` (13), `test_source_quality.py` (16), `test_account_route.py` (12), `test_brief_to_m5.py` (10) |
| Authority | none over publication, provider spend, approval or credentials; the tests contact no live source |
| Not done | no real A/B sample, no capture, no narration, no render (the layer itself merged in #114) |

## Measured Real-Source Gate (2026-11-04)

| Property | Value |
|---|---|
| Entry | `qc_video.py` → `src/contentops/media/real_source_duration.py` |
| Measurement | union of real visible seconds / measured duration of the rendered file; a shot's interval is its own duration and overlapping intervals are counted once |
| Counts as real | recording, screenshot, document, log and the other capture spellings in `claim_coverage.CAPTURE_SPELLINGS` |
| Does not count | diagrams, cards, generated images/videos, motion renders, stock, and any unknown kind |
| Refusals | `BLOCKED` when the output duration, a shot duration, a shot source, or a real shot's rights record is missing — never silently excluded from the denominator |
| Severity | `FAIL` for a project declaring `account_slug` (A/B); `WARN` for historical samples that predate the rule |
| Legacy | the shot-count `real_source_ratio` is kept as a diagnostic only |
| Tests | `python tests/test_real_source_duration.py` — 13 |
| Not done | no real A/B cut has been measured; the sample storyboards predate per-shot durations and report `BLOCKED`/`WARN` by design |

## GZH Workflow Adapter (2026-11-04)

| Property | Value |
|---|---|
| Entry | `python scripts/gzh_runtime.py status` / `verify` / `plan`; package `src/contentops/gzh/` |
| Runtime | a locally installed GZH workflow root, outside this repository, named by `CONTENTOPS_GZH_ROOT` or `--root` |
| Trust | `runtime/gzh-runtime.lock.json` records the identity (`gzh-thinktank` / `thinktank` / `wechat_article`), the contract-file hashes and the rights status; every recorded byte is re-hashed |
| Refusals | `MISSING_RUNTIME`, `LOCK_MISSING`, `ROOT_INSIDE_REPO`, `HASH_DRIFT`, `IDENTITY_MISMATCH`, `LOCK_PATH_ILLEGAL`, `CONTRACT_INCOMPLETE` |
| Authority | none: `execution_authorized` and `publish_authorized` are always false; `plan` describes the operator operations and never runs them |
| Rights | `UNRESOLVED` (Issue #56): the vendored tree is not redistributed here, and `production_ready` stays false even when every file verifies |
| Registry | `wechat_official_account` remains `PLANNED`: there is no draft, publish path or real local run |
| Tests | `python tests/test_gzh_runtime.py` — 12 on synthetic roots |
| Not done | no GZH article has been produced; no draft, publish, metrics or real workspace run |

## Bundle and Dual-Line Handoff (2026-11-02)

| Property | Value |
|---|---|
| Handoff entry | `scripts/bundle_handoff.py`, `src/contentops/content_kernel/handoff.py` |
| Formats | `VIDEO` (`contentops.copy-to-video/v1`), `GRAPHIC_TEXT` (`contentops.copy-to-graphic/v1`) |
| Tests | `tests/test_bundle_two_formats.py` 14/14; `tests/test_graphic_workflow.py` 14/14; `tests/test_m5_bundle_handoff.py` 5/5 |
| Bundle binding | every handoff records `bundle_path`, `bundle_scope` and `bundle_sha256`; both builders re-read the Bundle and refuse `BUNDLE_CHANGED` / `HANDOFF_UNBOUND` |
| Review binding | video `human-review.json` records the Bundle digest; a changed Bundle revokes a written review with `review_revoked_reason: BUNDLE_CHANGED` |
| Host capability | handoffs accept only `UNVERIFIED`; a caller cannot promote itself with a string |
| Video wiring | `project.yaml` `content_bundle` → `stage_bundle` writes `receipts/bundle-handoff-video.json` before sources |
| Graphic package | `scripts/graphic_package.py` writes `receipts/graphic-package.json` + `graphic-preview.md`, status `AWAITING_MANUAL_REVIEW` |
| Real dual-line sample | `projects/bundle-dual-line/` — one Bundle, `bundle-dual-line-video` MP4 (22.47 s, 1080x1920, h264+AAC, QC `WARN`, `PENDING_FOUNDER_REVIEW`) and `bundle-dual-line-graphic` manual package (`AWAITING_MANUAL_REVIEW`) |
| Sample provider/network | none; Windows SAPI narration + pinned Easel compose; graphic package made no render or draft |
| Publication | not implemented; every handoff/package carries `publish_authorized: false` |

## Pipeline

Two entry points share the pinned Easel composer. Neither publishes.

| Property | `run_v1.py` (V1) | `m5_production.py` (M5) |
|---|---|---|
| Input | authored `storyboard.json` + `master.md` | `project.yaml` `source_refs` + claims |
| Narration | edge-tts (`zh-CN-YunxiNeural`) | Windows SAPI, offline |
| Voice quality | `edge_tts_fallback` — not production-grade | `windows_sapi_offline` — not production-grade |
| Evidence layer | none | `SourceArtifact` + `ClaimLedger` |
| Composition | pinned Easel `assemble.py` via `assemble_easel.run` | same |
| Subtitle handling | `assemble_easel` strips, runs upstream, burns separately | burned from narration timings |
| Production ready | **false** | **false** — `PENDING_FOUNDER_REVIEW` |

Diagnostic engine: `python scripts/run_v1.py <project> --engine fallback`
(ffmpeg-only, never production, never reports `production_ready: true`).

## Delivery Layer (2026-11-12)

The outbound end of the pipeline. It packs and hands over; it never publishes,
and no delivery receipt in this repository records a platform URL.

| Property | Value |
|---|---|
| VIDEO entry | `scripts/video_deliver.py` — `plan` / `pack` / `status` / `dispatch` / `login` / `check` / `record` |
| VIDEO pack | a `06_delivery/` set per platform: title shaped to that platform's limits (the original is kept), mechanical frame-crop thumbnails labelled as crops, and a receipt |
| Uploader result | exit 0 is recorded as `UPLOADER_EXIT_0`. It is never a published claim; `record` is the only path that writes a URL a person actually saw |
| Graphic entry | `scripts/platform_delivery.py` (`list` / `self-test` / `pack` / `dispatch` / `status`) and `scripts/graphic_deliver.py` (one bridge, batched sync per platform) |
| Graphic channels | `config/platforms/graphic-platforms.yaml`: `wechat_article`, `zhihu`, `csdn`, `x`, `juejin`, `toutiao`, `weibo`. `xiaohongshu_image` sits under `excluded` because the platform belongs to the VIDEO line (operator instruction 2026-11-09) |
| External tools | the `wechatsync` CLI and browser bridge live in the gitignored `.runtime/` tree and are invoked across a process boundary. They are never imported into the Apache-2.0 source tree |
| Draft, not publication | every graphic call creates a platform draft. `multichannel` has no `PUBLISHED` branch and `publish` raises without a fully verified authorization |
| Authority | none over publication, account login, metrics or registry status. No `platforms.json` row is upgraded by a delivery run |
| Result here | **0** delivery receipts under `projects/`; the publication count above stays 0 |
| Tests | `test_delivery_gate.py`, `test_video_platforms.py`, `test_platform_registry.py`, `test_platform_status_sync.py`, `test_workflow_contract.py` — all offline |

## Card and GZH Article Rendering (2026-11-12)

| Property | Value |
|---|---|
| Card renderer | `scripts/render_cards.py` → pinned `render_card.py` and `card_audit.py` (density gate); writes `receipts/card-render.json`; exit 4 when a card is blocked or the audit fails |
| Article renderer | `scripts/render_article.py` → pinned `validate_gzh_html.py` and `wrap_preview.py`; writes `receipts/gzh-article.json` |
| Interpreter | `CONTENTOPS_CARD_PYTHON` / `CONTENTOPS_PYTHON`, plus `PLAYWRIGHT_BROWSERS_PATH` for cards. No interpreter is scanned or guessed |
| Sample | `projects/gzh-qc-gap/` — a real article input that stays `BLOCKED` with `validation: NOT_RUN`; no preview was generated |
| Verdict | a PASS is not an approval: both receipts keep `production_ready: false` and `publish_authorized: false` |
| Rights | the `gzh-design` directory is AGPL-3.0 upstream and is not redistributed here; `runtime/gzh-runtime.lock.json` stays `UNRESOLVED` |
| Tests | `test_render_cards.py`, `test_render_articles.py` — hermetic |

## M5 Evidence-First Production Chain (Issue #6) — IMPLEMENTED 2026-10-31

| Property | Value |
|---|---|
| Entry | `python scripts/m5_production.py projects/<slug>` |
| Evidence layer | `src/contentops/evidence/` — `SourceArtifact`, `ClaimLedger` |
| Stages | sources → assets → claims → script → narration → subtitles → storyboard → compose → QC → review |
| First run | `projects/m5-easel-pin` — 4 sources, 4 claims, 3 declared visuals, 7 lines |
| Narration | Windows SAPI, offline, 45.1 s, `voice_quality: windows_sapi_offline` |
| Subtitles | 7 cues burned from the narration timings, coverage 0.963 |
| Composition | pinned Easel, 1080×1920 H.264 + AAC |
| QC | PASS — 19 checks, real-source ratio 1.0 |
| Production ready | **false** — `PENDING_FOUNDER_REVIEW`, scores null |
| Tests | `tests/test_m5_evidence.py` — 18 offline tests |

Composer defect fixed in the same change: ASS subtitle timestamps were written
with three fractional digits, which libass reads as centiseconds, stretching
every cue roughly tenfold and overlapping neighbours. `assemble_easel._srt_to_ass`
now emits centiseconds; verified by rendering the cues on black and by diffing
the burned band against the unburned render.

## Web Workbench

| Property | Value |
|---|---|
| Status | **NOT VERIFIED / not a current doctor check** |
| Current doctor | 7 checks (python, node, ffmpeg, ffprobe, git, easel_checkout, repo_layout) — all OK on 2026-11-01 |
| Impact | Does NOT block the video pipeline (TTS + compose use the stdlib path) |

The earlier "6/7 doctor FAILs" list described a doctor version that checked Web
UI packages and a frontend build. The current `doctor.py` does not run those
checks, so that claim is retired rather than repeated. Web workbench readiness is
unverified, not failed.

## MiniMax

| Property | Value |
|---|---|
| Integration | speech **IMPLEMENTED** (Issue #19), `PENDING_FOUNDER_REVIEW` |
| Image integration | **IMPLEMENTED** (Issue #20, PR #25 merged), `PENDING_FOUNDER_REVIEW` |
| Video integration | **IMPLEMENTED** (Issue #22, PR #26 merged), `PENDING_FOUNDER_REVIEW` |
| Speech transport | official MiniMax CLI `mmx`; pinned Easel path is `EASEL_MPLAN_AUTH_INCOMPATIBLE` |
| Image transport | official MiniMax CLI `mmx` |
| Video transport | **documented public API** `POST /v2/video_generation` — the CLI cannot set resolution |
| Voice cloning | **DOCUMENTED_BUT_NOT_TESTED** (Issue #23), needs a rights-cleared sample |
| Capability spike | **COMPLETE** (Issue #4, 2026-10-04) |
| PAYG allowed | **false** |
| Billing mode | subscription, **verified** |
| Speech | **VERIFIED** — `speech-2.8-hd`, 32 kHz mono WAV |
| Image | **VERIFIED** — `image-01`, 9:16 portrait, seed supported |
| H3 video T2VA | **VERIFIED** — real `MiniMax-H3` 768P 4 s task succeeded on the Subscription Key (M2.0) |
| H3 video I2VA | **VERIFIED** — real reference-image task succeeded 2026-10-05 (M4) |
| H3 Ref2VA / FL2VA / L2VA, H3-Max | **DOCUMENTED_BUT_NOT_TESTED** — implemented and fixture-tested, not exercised live |
| Credit Pack balance | `0.00` observed, re-checked before every generation |
| Balance read dependency | `UNDOCUMENTED_FIRST_PARTY_IMPLEMENTATION_DEPENDENCY`, fail closed |
| H3 duration | integer enum 4-15 (H3), 5-15 (H3 Max); test minimum 4 s / 5 s |
| Evidence | `research/providers/minimax-mplan-explore-capability.md`, `research/providers/minimax-h3-official-reality.md`, `research/providers/minimax-voice-clone-entitlement.md`, `research/providers/receipts/minimax-h3-i2va-reference-2026-10-05.sanitized.json` |

## Golden Samples

| Sample | Source | Status |
|---|---|---|
| `projects/easel-review/` | Easel v0.2.1 runtime evaluation | 1 successful build, QC PASS, awaiting human review |
| `projects/m5-media-use/` | M5 evidence chain with the media-use sample | final MP4, QC WARN, `PENDING_FOUNDER_REVIEW` |
| `projects/m5-easel-pin/` | First M5 evidence-chain run | QC PASS (19 checks), real-source ratio 1.0 |
| `projects/m45-technical-integration/` | M4.5 media convergence | QC WARN, zero provider calls |
| `projects/bundle-dual-line/` | One Content Bundle, two independent outputs | video 22.47 s QC WARN / `PENDING_FOUNDER_REVIEW`; graphic `AWAITING_MANUAL_REVIEW`; 0 publications |

## Tests

| Suite group | Files | Count |
|---|---|---|
| Script smoke | `scripts/test_basic.py` | 10 |
| Media / provider (offline fixtures) | speech, image, H3, convergence, media-use adapter | 432 `test_*` functions |
| M5 evidence + media-use traceability | `test_m5_evidence.py`, `test_m5_*` | 18 + list-driven suites |
| Golden / reproducibility | A/B variants, voice assets, locked inputs | 47 |
| Skill / authorization | router, doctor, execution gate, grants | list-driven suites |
| Skill reference integrity | `tests/test_skill_references.py` | 6 |
| Windows | subprocess, paths | 53 |
| Policy / secrets | gitignore, local-approval, receipt secrets | 19 + list-driven suites |
| **Total** | **not asserted in this document** | 98 suites and 98 named CI steps on 2026-11-12; the authoritative count is read at check time: `git ls-files 'tests/test_*.py' \| wc -l` |

`python scripts/dev_check.py` runs the local gate. CI enumerates every suite as a
named step; a suite without a CI step does not run, and one green run is not
evidence that every suite passed. `ffmpeg` and `Pillow` are installed in CI;
suites that need them report skips when absent.

See [TEST-PLAN.md](TEST-PLAN.md) for the full inventory.

## Known Blockers

1. Voice quality — edge-tts is mechanical and Windows SAPI is offline-flat.
   Neither is production-grade. MiniMax speech is implemented but unapproved.
2. Human Review — no project has an approved `human-review.json`. The tracked
   `projects/easel-review/receipts/human-review.json` records
   `REJECTED_FOUNDER`; other production runs remain `PENDING_FOUNDER_REVIEW`.
3. media-use runtime lock — a clean checkout (and this host today) resolves
   `BLOCKED / MISSING_RUNTIME`. The approved baseline exists; a host lock must be
   generated and trusted before the adapter can run.
4. Rights — the XHS, X and GZH adapters on `main` verify but never execute, and
   the GZH renderer validates only through an AGPL-3.0 upstream skill that is not
   redistributed here. Rights clearance (Issues #51, #56) is the remaining
   blocker rather than missing code.
5. No bound public account — every delivery runner exists, yet eight of nine
   registry rows stay `PLANNED` because no public account is bound and no work
   holds a real platform URL. Delivery code without an account is packaging, not
   publishing.
6. Documentation convergence — this document was restructured on 2026-11-01;
   PRD, DEVELOPMENT-PLAN and TEST-PLAN were updated in the same pass, and the
   Tier-1 set was re-synced on 2026-11-12. The historical requirements are in
   [CONVERGENCE-REQUIREMENTS-2026-11-01.md](CONVERGENCE-REQUIREMENTS-2026-11-01.md).
7. Upstream pins — Easel v0.3.0 and HyperFrames 0.8.225 are available and not
   adopted. See the convergence requirements for the decision.
8. ~~Main branch unprotected~~ — **RESOLVED** (G0.6): main is protected via
   GitHub branch protection.
9. Easel host — `HOST_BLOCKED` on this machine because FastAPI/uvicorn are absent.
   Installing them, using a real account or starting a host requires a separate
   approval after a host-security review (ADR-016). A running host is not a
   publication authorization.
10. ASR backcheck — `SKIPPED` unless `SILICONFLOW_API_KEY` is present, so a run
    without the credential proves nothing about narration accuracy.


## M3 Image Generation (Issue #20) — VERIFIED 2026-10-04

Branch `feat/20-minimax-mplan-image`. One real provider generation was performed.

| Property | Value |
|---|---|
| Transport | official CLI `mmx 1.0.27`, `mmx image generate` |
| Model | `image-01` |
| Requested | 768x1360, seed 42 |
| **Requested extension** | `.png` |
| **Detected container** | **`JPEG`** |
| **Canonical extension** | `.jpg` (bytes preserved, no transcode) |
| Actual dimensions | 768x1360 (confirmed independently by `ffprobe`: `mjpeg`) |
| Aspect ratio | 0.564706 against 9:16 = 0.5625, within the 0.02 tolerance |
| Output SHA-256 | `fb0ee9489df856bc2cd554ab98d34fd73e0737ca733cdd0af6022342512f8e21` |
| Technical QC | PASS — luma stddev 29.97 (floor 6), span 146 (floor 24), decodable |
| `text_contamination_suspected` | `false` (edge density 0.0668, floor 0.18) |
| Billing preflight | `SAFE_INCLUDED_PLAN`, credential class `SUBSCRIPTION` |
| Quota before | 5h 99%, weekly 58% |
| Quota after | 5h 99%, weekly 58% |
| Observed delta | **0 percentage points** on both windows |
| `production_ready` | `false` |
| `human_review` | `PENDING_FOUNDER_REVIEW` |

### The container defect reproduced a second time

The provider returned **JPEG bytes from a `.png` request**, independently
reproducing what M2.0 measured. Had the pipeline trusted the extension, a JPEG
would have been stored as `.png` and handed to every downstream tool that selects
a decoder by suffix. The canonical file is `.jpg`; the receipt records the request
and the reality separately.

### Quota is reported as a delta, never as a price

The plan exposes percentages only. One image moved neither window, so the
observed delta is 0 percentage points. That is **not** a claim that an image
costs nothing, and no per-image cost is derived: MiniMax does not expose exact
units here.

### Evidence boundary

The generated asset was registered as `GENERATED_IMAGE` /
`VISUAL_SUPPORT` with `generated=true`, `evidence_capable=false`. Attempting any
claim-bearing role raises `GeneratedAssetEvidenceError` in code.

### Human review

`.verify-tmp/m3/human-review.json` carries the review fields with **every score
null**. Technical QC passing does not mean production ready.

## M4 H3 Video Generation (Issue #22) — VERIFIED 2026-10-05

Branch `feat/22-minimax-h3-video`. One real provider generation was performed, a
**reference-image** test, because M2.0 proved T2VA with no image content at all.

| Property | Value |
|---|---|
| Transport | documented public API `POST /v2/video_generation`, api schema `v2` |
| Model / mode | `MiniMax-H3`, **I2VA** (first-frame reference) |
| Requested | 4 s, `768P`, ratio `adaptive` (i2va derives the ratio from the input image) |
| Reference | `data:image/jpeg;base64`, 768x1360, 45 800 B, `role: first_frame` |
| Alignment instruction | emitted as the first line, upstream wording verbatim |
| Task created | **exactly 1**, polled to `succeeded`, downloaded once |
| Actual output | h264 / mp4, 768x1344, 24 fps, **4.458 s**, 424 543 B, decodable |
| Aspect | 0.571429 against reference 0.5647 — tolerance, not equality |
| Duration delta | 4.000 requested → 4.458 actual (0.458 s, threshold 1.0 s) |
| Audio | unrequested **AAC** present, exactly as M2.0 measured; `audio_policy=REPLACE` |
| Black / freeze | longest black run 0.0 s, longest freeze run 0.0 s, mean frame diff 0.0131 |
| Output SHA-256 | `b761ea2a69b3ad6181b8a48b93dddefb56edd897867f42a8b160610e74ac249a` |
| Billing preflight | `SAFE_INCLUDED_PLAN`, credential class `SUBSCRIPTION` |
| Quota before | weekly 58% |
| Quota after | weekly **51%** |
| Observed delta | **7 percentage points** weekly, matching the declared `7pp` budget |
| cash / Credit Pack / voucher / owed | `0.00` before **and** after |
| `production_ready` | `false` |
| `human_review` | `PENDING_FOUNDER_REVIEW` |

### The reference path was genuinely unproven

M2.0's receipt contains a single `text` item and **no image content**. So it was
silent on every part of the reference path: whether an `image_url` item is
accepted, whether `role: first_frame` is honoured, whether a `data:` URI is an
accepted URL form, whether the alignment instruction travels with a frame, and
whether I2VA renders at all on this account. The account also resolves to the
regional CN mirror rather than the host the public documentation targets, so
reference handling could plausibly differ. One 4 s call was the cheapest way to
close that gap.

### Quota is reported as a delta, never as a price

7 percentage points is an **observed** delta for one 4 s / 768P job. It is not a
price formula: no per-second, per-clip or credit rate is derived from a percentage.
It is used only to budget tests conservatively. Weekly now stands at **51%**.

### Cache reuse verified against the real artifact

A second run was served from the cache with the transport pointed at an
**unroutable host**, so any network attempt would have failed loudly:

| Property | Value |
|---|---|
| Reused | `true` |
| Provider creates | **0** |
| Provider polls | **0** |
| Billing calls | **0** |
| Original receipt overwritten | `false` |

### Evidence boundary

The shot was registered as `GENERATED_VIDEO` / `VISUAL_SUPPORT` with
`generated=true`, `evidence_capable=false`, and only **after** the immutable
receipt existed. Any claim-bearing role raises `GeneratedAssetEvidenceError`.

### Human review

`<shot>.mp4.human-review.json` carries eleven named review fields with **every
score null**. Automated measurements ride alongside, labelled as measurements.
Observed on the real clip, and recorded as observation rather than scored: the
first frame reproduces the reference faithfully; motion is present and consistent
with the requested slow push; but between the first and last frames the circular
headlamp reads as a filled disc rather than a ring, and one neon sign drifts in
position. Geometry stays coherent with no melting or warping. Whether that drift
is acceptable for a support visual is a human judgement, and it is not this
pipeline's to make.

### Still unverified

Ref2VA reference-video and reference-audio paths, FL2VA, L2VA, and MiniMax-H3-Max
(including its 5 s floor and 480P option) are implemented and fixture-tested but
have not been exercised against the live service.
## M4.5 Media convergence (Issue #27) — IMPLEMENTED 2026-10-05

Branch `feat/27-media-convergence`. **Zero provider calls.** Weekly quota untouched at 51%.

| Property | Value |
|---|---|
| Shared validator | `validate_media_asset(envelope, adapter)` — one common path, three adapters |
| Modality model | `MediaModality` (SPEECH/IMAGE/VIDEO) is **separate** from `AssetKind`; speech carries no `asset_kind` |
| Speech receipt facts | no `schema`, no `generated`/`evidence_capable`, digest in `normalized_sha256`/`raw_sha256` |
| Transform receipt | `contentops.media-transform/v1` — derived assets, source digest, original untouched |
| `AudioPolicy` | `KEEP` reuses the original (no transform); `MUTE`/`REPLACE` produce an audio-free derived asset |
| Capability registry | 10 capabilities resolved by name, no vendor word; only live-proven ones `VERIFIED` |
| Quota policy | explicit operator floors; weekly floor is a **chosen value**, not the observed 7pp delta |
| Scheduler | `ALLOW`/`REUSE_REQUIRED`/`DEFER`/`MANUAL_REQUIRED`/`BLOCKED`, priority evidence → narration → image → video |
| AssetPlanner execution | claim beats resolve only to real material, else `EVIDENCE_ASSET_REQUIRED` |
| Quality gate | `BLOCKED`/`DEGRADED_FALLBACK`/`PENDING_HUMAN_REVIEW`/`PRODUCTION_READY`/`REJECTED` |
| Manifest | `contentops.media-manifest/v1`, deterministic, no timestamp, sole asset list |
| Manifest paths | logical `project://` / `repo://`, resolved at use; absolute paths refused |
| Timeline | `assets` is the inventory, `timeline` is one active asset per placement; composition reads the timeline |
| Derived provenance | `generated` is inherited, never downgraded; `provider_generated_bytes` vs `source_generated` are separate fields |
| H3 reuse | explicit by path and validated; no filesystem discovery |
| QC receipt | `contentops.qc-canonical/v1` — sanitized at a boundary, declares `currency` and `graded_target` |
| Composition | reuses pinned Easel v0.2.1 via `assemble_easel.run`; no second compositor |
| Tests | 97 M4.5 + 85 speech + 84 image + 108 H3, all PASS |

### Two rules the implementation added beyond the plan

- a **provider generation** must declare its modality's schema; a **non-generated**
  asset must not, because nothing's API produced it
- a missing `technical_qc` **fails** a generation but is **not applicable** to an
  import or a transform — no provider ran, so there is nothing to report

### The technical integration is not a production golden

`scripts/m45_media_integration.py` produced one local artifact
(`project://final/m45.mp4`, h264 / 1080x1920 / 18.0 s, `qc_video` **WARN**) proving
`registry → manifest → compose → final QC` with **0** speech, image and video
provider calls.

| Canonical fact | Value |
|---|---|
| Output | `project://final/m45.mp4` |
| QC report | `receipts/qc-report-m45.json` — `overall: WARN`, `currency: CURRENT` |
| `production_ready` | `false` |
| `human_review` | `PENDING_FOUNDER_REVIEW` |
| Provider calls | speech 0 / image 0 / video 0 |
| Timeline | 5 placements, one active asset each |
| Inventory | 7 assets (5 active + 1 superseded + 1 narration) |

Every asset is a deterministic fixture, labelled in its receipt, in the manifest
header and in the integration report. Media binaries are gitignored; the manifest,
receipts and storyboard are committed.

**One QC report, one verdict.** `qc-report-m45.json` is the canonical M4.5 QC report
and is the only one. A second tracked report, `qc-report-final.json`, recorded
`FAIL` because it graded `final/final.mp4` — a file this stage never produces — and
sat beside the real `WARN` reading as an equally current, contradicting result. It
was stale output from an earlier invocation and has been removed.

QC receipts cross a sanitization boundary before being committed
(`contentops.qc_canonical`). `qc_video` is a runtime tool and keeps reporting local
paths, which is correct while it runs; the tracked receipt is rewritten in place as
`contentops.qc-canonical/v1` with logical references and an explicit `currency` plus
`graded_target`. So a reader can tell *what* a verdict is about and *whether it is
current* without inferring either from a filename. A regression test scans the
canonical committed artifacts for host-specific paths.

It does **not** prove real `SourceArtifact` ingestion, `Claim Ledger`
completeness, Founder approval, a production golden, or three consecutive
production builds. `production_ready=false` / `PENDING_FOUNDER_REVIEW`, and no code
path can report otherwise.

### Defects the final review caught in the committed artifacts

Four blockers found by reading the committed receipts rather than the code, all now
fixed with regression tests:

1. **One placement, two shots.** `manifest_to_storyboard` iterated
   `usable_assets()` — an *inventory*, not a timeline. `beat-05` and
   `beat-05-h3-replaced` are both gate-admissible, so both landed on placement
   `beat-05`: the pre-transform native audio played over the narration `REPLACE` was
   meant to guarantee would be the only track. The manifest now carries an explicit
   `timeline` with one `active_asset_id` per placement, and composition reads that.
2. **Generated provenance downgraded.** The derived H3 envelope said
   `asset_kind=GENERATED_VIDEO` with `generated=False`, because the transform receipt
   had overloaded one boolean for "did a provider emit these bytes" and "is this
   content generated". Now refused at construction, in both directions, derived or
   not.
3. **Machine paths in a committed manifest.** Eight `D:\Projects\...` references made
   "deterministic manifest" true on exactly one checkout root — and therefore useless
   as a cache key or review comparison. Paths are now logical.
4. **`--reuse-h3-shot` did nothing.** `main()` parsed it and passed no argument,
   while the provider separately globbed `.verify-tmp/m4`. So a clean clone produced
   fixtures and a workstation with M4 leftovers silently produced real provider
   media — both committed as "the integration". Reuse is now explicit by path and
   validated against the shot's own receipt.

And one found in the **QC receipts**, which the previous pass had not looked at
because the manifest was already clean:

5. **Two current-looking QC verdicts.** `qc-report-m45.json` (WARN, graded
   `final/m45.mp4`) and `qc-report-final.json` (FAIL, graded `final/final.mp4`, which
   nothing here creates) were tracked side by side, both carrying absolute
   `D:\Projects\...` paths. The stale report was removed and the canonical one now
   declares `currency` and `graded_target`.

### Defects the test suite caught during this milestone

Three real bugs in the new code, all found by tests rather than review:

1. `require_evidence_capable` was called unconditionally for generated image, which
   made a support visual **impossible to produce at all** — the capability is
   correctly flagged evidence-incapable, but the check belongs to the claim path
2. The asset-existence check was lost while restructuring the receipt loader, so a
   **missing asset file passed validation**
3. Duplicate `asset_id`s **silently collapsed** in the manifest, because
   `gate_states` is keyed by identifier; now refused

Plus one validation gap: a key-shaped value was only refused in a known field
list, so it could be smuggled through a new field. Now no string value anywhere in
a public receipt may match the provider-key shape.

## HyperFrames media-use integration (Issue #57) — IMPLEMENTED 2026-10-31

Re-verified after owner approval on 2026-10-31. Branch `feat/57-media-use-adapter`.
**Zero provider calls.** The verified runtime was exercised with no network
egress; installation itself is a separate, reviewed preparation step.

| Property | Value |
|---|---|
| Upstream | `heygen-com/hyperframes` @ `5e4f5aefb58a9996ea5920f008184e9789346871` (Apache-2.0) |
| Skill commit | `f2358315e59731833334c5d881a7fb5543c22a97` (`skills/media-use`) |
| Adapter | `src/contentops/media/media_use_adapter.py` — the only module that knows the skill exists |
| CLI | `scripts/media_use_adapter.py` — `status/doctor/candidates/resolve/adopt/ingest/import/verify/demo` |
| New kinds | `AssetKind.LICENSED_EXTERNAL`, `MediaModality.AUDIO` |
| Receipt | `contentops.media-import/v1` with `output_sha256`, `fingerprint`, `generated`, `evidence_capable`, `production_ready`, `human_review`, `license` |
| Evidence | every import is `evidence_capable=false`; generated resolutions are `GENERATED_NOT_IMPORTABLE` |
| Cross-project | blocked unless `allow_cross_project_reuse`; child `HOME` is project-local |
| Runtime trust | two layers: a committed, owner-approved baseline (`runtime/media-use-runtime-baseline.json`, approved 2026-10-31 for offline-only scope) and a host-specific lock (`CONTENTOPS_MEDIA_USE_RUNTIME_LOCK`). A lock is trusted only if it names the approved baseline by digest and every byte matches. A fresh checkout still refuses execution until a machine lock is generated; approving the baseline does not install or trust a host runtime |
| Verified runtime | `hyperframes@0.8.222` (published SRI matched), official Node v22.23.4 on Linux and win-x64 (SHASUMS match), 127-entry lockfile. Package-tree digest `be8e24df…` reproduced independently on both platforms |
| Acceptance | Linux: `TRUSTED_RUNTIME` inside a no-egress namespace, `adopt`/`candidates`/`resolve` through the adapter. Windows: `install` → `lock` → `TRUSTED_RUNTIME` → real CLI. Isolated demo with real Easel compose: `compose` OK, QC `WARN`, `production_ready:false` |
| Install / lock entry point | `scripts/media_use_runtime.py` — `approve`, `install`, `lock`, `verify`, `selfcheck`; approving and lock generation are separate actions |
| Tests | 53 adapter tests PASS; 97 M4.5 convergence tests PASS (re-run 2026-10-31) |
| Pull request | Draft [#64](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/64) |
| Skill Router | **Merged via [#77](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/77)** — `scripts/skill_route.py` and `runtime/skill-registry.json` register `media-use` as a declared capability. #49 remains unmerged; #59 was closed as superseded by #77. The adapter still exposes `status/doctor/candidates/resolve/adopt`; the registry is the routing pointer |

### What the approval does and does not authorize

- The approved baseline authorizes **offline local asset operations** with the
  pinned `hyperframes@0.8.222` runtime: `adopt`, `candidates` and local
  `resolve`.
- It does **not** authorize network providers, paid generation, cross-project
  reuse, automatic publication, production delivery, or any source-media
  licence. A trusted runtime proves *what executed*, never *where an asset came
  from* or *what its licence is*.
- Every imported asset still needs an explicit licence and stays
  `evidence_capable=false`, `production_ready=false`, `human_review=PENDING`.
- The isolated Easel demo ran against a separate verified runtime. It does
  **not** mean the original `.runtime/easel` checkout is healthy or restored.

### Offline end-to-end sample

`python scripts/media_use_adapter.py demo` (exit `0`) produced
`project://final/media-use-demo.mp4` — 1080x1920, h264, 30.0 s, 300,437 bytes.

| Fact | Value |
|---|---|
| Manifest | `receipts/media-manifest.json`, fingerprint `2b01c1cb716723007527a422dff4810b16db1d9b090e61a5f2a5de578a5ba75d` |
| Inventory | 7 assets: 2 real screenshots, 2 licensed images, 1 icon, 1 BGM, 1 bundled SFX |
| Timeline | 2 placements, both `SCREENSHOT`, `real_source_ratio` **1.0** |
| Imported via media-use | 5 records (4 local fixtures labelled `OWNED-FIXTURE-DEMO`, 1 bundled SFX `Pixabay-Content-License`) |
| Gate | every asset `PENDING_HUMAN_REVIEW` |
| Final QC | `overall: WARN` (no FAIL), `currency: NON_CURRENT_DIAGNOSTIC` |
| Provider calls | speech 0 / image 0 / video 0 |
| `production_ready` | `false` |

The two real screenshots come from `projects/easel-review/sources/screenshots/`.
The image/BGM fixtures are deterministic placeholders generated by the demo and
labelled as such in their receipts; they are **not** third-party licensed media.
An image resolve with no local candidate and no network authorization is recorded
as `NEEDS_HUMAN_ACTION` — nothing is downloaded or generated to make the demo look
complete.

The render is a technical integration sample. It has no audio track, no captions
and no Founder approval, and `qc_video` warns about exactly that.

## M5 media-use automation — INTEGRATION_VERIFIED 2026-10-31

Merged to `main` through [#71](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/71).
The rights-gate follow-up is [#76](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/76).
**Zero provider calls; zero network.** The real
`scripts/m5_production.py` entry ran the real `MediaUseAdapter` against the
approved `hyperframes@0.8.222` runtime on Windows.

| Property | Value |
|---|---|
| Entry point | `python scripts/m5_production.py projects/m5-media-use` |
| Runtime | host lock `contentops.media-use-runtime-lock/v2`, state `TRUSTED_RUNTIME`, baseline digest matched |
| Configuration | `projects/m5-media-use/project.yaml` → `media_use.requests` (image, bgm, sfx) |
| Stages run | sources → media_use → assets → claims → script → narration → subtitles → storyboard → Easel compose → QC → review |
| Imported visual | `project://assets/support.png`, SHA-256 `85c4ab5c5368b1ab60a98854ee292529d6b7908be58acfccc1d5f4ed06cddb53`, `evidence_capable=false` |
| Imported BGM | local deterministic tone bed, SHA-256 `1dcb9c7e3708cfc0cc68663642cc9d6b779ff7bd5812fdb6e31e4d74f5b4ee5e` |
| Imported SFX | bundled `sfx_001`, Pixabay Content License, receipt `contentops.media-import/v1` |
| Final artifact | `projects/m5-media-use/final/m5-media-use.mp4` — h264 1080x1920 + AAC 48 kHz stereo, 25.07 s, 505,448 B, SHA-256 `d4915f45f98008e4adbaa52d29beb787ffc437d383f15415780830aeaf33d731` |
| QC | `overall: WARN`, audio stream present, no FAIL |
| Human review | `PENDING_FOUNDER_REVIEW`; `production_ready: false` |
| Composition proof | frames at 1 s, 2 s, 13 s and 14 s show the imported screenshot with the expected burned captions |
| BGM proof | inter-line pause 11.70–12.20 s: −60.9 dB with BGM vs −91.0 dB without (−30.1 dB difference) |
| SFX proof | 6.15–6.28 s: −33.4 dB with SFX vs −60.8 dB without (−27.4 dB difference) |
| Narration preservation | the same voice window measures −26.8 dB in all three renders, so neither track replaced the voice |
| Audio controls | volume, placement and mix verified; per-track fade is **not expressible** in the pinned Easel contract (sample bed has fades baked into the file) |
| Negative acceptance | 11/11 blocked: missing/wrong lock, missing material, hash mismatch, path escape, missing import file, network, paid, unlicensed, duplicate id, legacy project unchanged |
| Rights gate | `src/contentops/media/rights_gate.py` refuses a bare `rights_reviewed` flag; each request needs a matching `assets/<id>.rights.json` review record. Unknown, software and non-commercial licences are refused; synthetic assets are never evidence |
| Committed example | `projects/m5-media-use/`; media binaries and `.media/` stay gitignored, receipts are committed |
| Pull request | Merged [#71](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/71); rights-gate follow-up [#76](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/76) |
| Routing | **MERGED via [#77](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/77)** — `scripts/skill_route.py` and `runtime/skill-registry.json` are on `main`; see *Skill discovery and resolution* below |

`INTEGRATION_VERIFIED` is a statement about this machine and this lock. It is
not `MERGED_TO_MAIN`, and it does not approve the imported material, the voice
track or the video for publication.

## Skill discovery and resolution (Issue #57) — MERGED 2026-10-31

Merged to `main` through [#77](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/77).
The router and registry run on `main` today; this section records what they do
and what remains blocked.

| Property | Value |
|---|---|
| Entry point | `python scripts/skill_route.py` (stdlib only; no process, no network) |
| Discovery | `--sources`, `--list`, `--match`, `--resolve` over repo-owned, Easel and shared skill roots |
| Doctor | `--doctor` — roots, duplicates, permission declarations, rights, unsafe and dangling paths |
| Declared capabilities | `runtime/skill-registry.json`, schema `contentops.skill-registry/v1` |
| Registered capability | `media-use` only, pointing at the merged adapter, runtime baseline, lock verifier and M5 `media_use` stage |
| Resolution verdicts | `RESOLVABLE`, or `BLOCKED` with `UNKNOWN_SKILL`, `DUPLICATE_AMBIGUITY`, `OUT_OF_SCOPE`, `UNVERIFIED_RIGHTS`, `UNAUTHORIZED_PROVIDER`, `SKILL_NOT_INSTALLED`, `MISSING_RUNTIME` |
| Execution authorization | **never granted** by the router; every record carries `execution_authorized: false` |
| media-use with a host runtime lock | `RESOLVABLE` (verified on this host against `runtime/media-use-runtime-baseline.json`) |
| media-use without a lock | `BLOCKED / MISSING_RUNTIME` (the default on a clean checkout) |
| Verdict on this host (2026-11-01) | `BLOCKED / MISSING_RUNTIME` — `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK` is not set here, so the adapter is not executable on this machine |
| Legacy M5 | unchanged — `scripts/m5_production.py` does not import the router; a test asserts it |
| VIDEO track | discovery-only until a catalog root exists on the host |
| GZH track | `BLOCKED` — vendored third-party track, rights unverified, `vendor/` is gitignored |
| X track | `BLOCKED` — verify-only adapter on `main` (PR #127); rights and publication stay manual |
| XHS track | `BLOCKED` — verify-only adapter on `main` (PR #125); rights review open as Issue #51 |
| Tests | `tests/test_skill_doctor.py`, `tests/test_skill_router_capabilities.py`; both registered in CI |
| Pull request | Merged [#77](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/77) |

The router adds no second skill engine and copies no third-party skill. A
declaration is a pointer to code this repository already owns; the adapter, the
runtime lock verifier and the M5 gate keep their own authority.
