---
status: experiment
canonical: false
issue: "#34"
date: 2026-10-28
---

# dy_x1024 design-layer archive

The source workspace `D:\Projects\dy_x1024` is being retired. This directory is
the deletion-safe copy of the parts that were judged portable: stdlib logic,
declarative config, JSON schemas and operating documents.

It is an **archive, not a dependency**. Nothing in `src/`, `scripts/` or CI
imports from here. When a capability is ported it is reimplemented under
`src/contentops/` with its own tests; the archived file is kept only as the
reference for what was meant.

Archived Python sits outside `scripts/check_subprocess_policy.py`'s scan
(`EXCLUDED_PREFIXES` carries `research/vendor/`). That rule exists so a shipped
process cannot open a hidden window; nothing here is imported, executed or
shipped, and rewriting retired upstream code to satisfy it would produce noise
rather than a guarantee. Porting still means rewriting under `src/contentops/`,
which is scanned.

## Provenance

| Property | Value |
|---|---|
| Source repository | `D:\Projects\dy_x1024\dy_1024` |
| Commit | `a5952a44dbf47d44c1a4bf475e3653b542c25ac1` |
| Commit date | 2026-09-30 |
| Account | X•超玩1024 (`douyin-sentinel-v1`) |
| Authorship | first-party, authored for the same account |
| Third-party code | **not archived here**; third-party skills go to the shared skill store with their licences |

## What is here

| Directory | Contents | Why kept |
|---|---|---|
| `scripts/` | design-layer gates and planners (topics, candidate scoring, copy routing, teaching/naturalness/creative QC, rights, platform policy, provenance, naming, delivery, visual route, manifest hashing) | the logic is stdlib and provider-free |
| `adapters/publish/` | publish plan and feedback adapter | the publish/feedback *contract*, not the platform runtime |
| `configs/` | positioning, taxonomy, narrative, copy evidence, topic selection, naming, brand voice, platform policies | declarative rules the pipeline reads |
| `schemas/` | 51 JSON Schemas | machine contracts for the hand-offs |
| `profiles/` | account profile, visual routing rules, motion template registry | account-level defaults |
| `docs/` | audience OS, task-driven workflow, human-operation gate, improvement loop, Douyin operator workflow | the reasoning behind the gates |

## What is deliberately excluded

| Excluded | Reason |
|---|---|
| `adapters/model/*`, `adapters/image/*` | ChatGPT bridge / Codex image / local H3 ComfyUI providers — replaced by MiniMax subscription APIs |
| `scripts/h3_comfyui_runtime.py`, `h3_comfyui_*`, `funasr_*`, `openchatcut_*`, `remotion_*` | local GPU, local ASR, local editor, second compositor |
| `scripts/gflow_*`, `gemini` web paths | paid credits or a human-visible browser session |
| `skills/` (52 directories) | third-party or heavy; selected text-only skills were copied to `C:\Users\Administrator\.agents\skills` instead, with licences |
| `production/`, `runtime/`, `state/`, `.remotion/` | run artefacts and local state, not design |
| `docs/audits/`, `docs/superpowers/` | historical audit narrative, superseded by the current code |

## Port status

| Capability | Status | Destination |
|---|---|---|
| Stage contract + check/approve gate | **ported** | `src/contentops/workflow/{contract,gate}.py` |
| Quality report (one verdict) | **ported** | `src/contentops/quality/report.py` |
| Script rhythm / naturalness (shape half) | **ported** | `src/contentops/quality/script_rhythm.py` |
| Subtitle QC | **ported** | `src/contentops/quality/subtitle.py` |
| Per-claim evidence coverage | **ported** | `src/contentops/media/claim_coverage.py` |
| Audience Lens v3 | **ported** | `src/contentops/workflow/audience.py` |
| Duration policy | **ported** | `src/contentops/workflow/duration.py` |
| Topic backlog + candidate scoring | **ported** | `src/contentops/workflow/topics.py` |
| Human-operation / evidence feasibility forecast | **ported** | `src/contentops/workflow/human_forecast.py` |
| Platform safe-publishing policy | **ported** | `src/contentops/workflow/platform.py` |
| Rights audit | **ported** | `src/contentops/workflow/rights.py` |
| Workflow improvement log | **ported** | `src/contentops/workflow/improvement.py` |
| Skill provenance / execution binding | **ported** | `src/contentops/workflow/provenance.py` |
| Publish plan + feedback / metrics import | **ported** | `src/contentops/workflow/{platform,feedback}.py` |
| Production naming policy | **ported** | `src/contentops/workflow/naming.py` |
| Delivery package | **ported** | `src/contentops/workflow/delivery.py` |
| Semantic visual route | **ported** | `src/contentops/workflow/visual_route.py` |
| Teaching / creative QC slices | pending | `.../scripts/{teaching_qc,creative_qc}.py` |
| Copy strategy / adaptive router | **ported (core)** | `src/contentops/workflow/copy_strategy.py`; adaptive router still pending |
| Copy evidence policy | pending | `.../scripts/copy_evidence_contract.py` |
| Content taxonomy + topic selection policy | pending | `.../configs/{content-taxonomy,topic-selection-policy}.json` |

"pending" means the source is preserved and the port is a known, scoped task.
It does **not** mean the capability is active.
