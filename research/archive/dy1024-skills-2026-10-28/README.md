---
status: superseded
superseded_by: C:\Users\Administrator\.agents\skills (adopted skills) and src/contentops/workflow/sources.py (adopted contract)
historical_context: index for the archived dy_x1024 skill contracts
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
date: 2026-10-28
---

# dy1024 skill archive

Source: `D:\Projects\dy_x1024\dy_1024\skills`, HEAD
`a5952a44dbf47d44c1a4bf475e3653b542c25ac1` (2026-09-30). The workspace is due to
be deleted, so this directory preserves the **contracts** of the skills that
matter to this pipeline.

This is an archive, not a dependency. Nothing here is imported, executed or
routed to. Runnable copies live in the shared skill store
(`C:\Users\Administrator\.agents\skills`) and are declared in
`config/accounts/*.json`.

## What was copied

Text files only (`.md`, `.json`, `.yaml`, `.yml`, `.txt`, `.csv`), each ≤200 KB,
excluding `.git`, `node_modules`, `.venv`, `__pycache__`, `media_outputs`,
`.webapp`, `upstream` and `tests`. 93 markdown files plus data files, 30 skills.

| Skill | Why it is worth keeping |
|---|---|
| content-copy-orchestrator | origin of `x-superplay-copy-orchestrator`; evidence-first copy, audience lens, human-voice contract |
| content-production | topic → publishable piece pipeline |
| content-repurposer, content-repurposing | cross-platform atomization (unused today; this repo is Douyin-only) |
| broll-production | origin of `x-superplay-broll-production` |
| material-source-research | the candidate-rights contract now implemented in `src/contentops/workflow/sources.py` |
| media-delivery | review-gated vertical delivery package |
| model-media-runtime, runtime-media | local worker routing for speech, ASR, avatar and timeline |
| model-selector, prompt-translator | cross-model selection and a 110-case prompt translation matrix |
| script-to-tts | per-model TTS script reshaping |
| seedance-2.0-director | Seedance prompt grammar (provider not adopted) |
| social-content | scheduling and optimisation guidance |
| video-workspace-conventions | lifecycle phases, folder layout, naming |
| clean-talking-video | Chinese talking-head cut with an exactly matching SRT |
| manim-video | Manim CE production pipeline for technical animation |
| videocut-剪口播, videocut-高清化 | Chinese talking-head cutting and 2-pass upscale |
| generative-media-guidance | image / image-to-video prompt constraints |
| jacky-hook, jacky-de-ai, jacky-opc | hook question framework, AI-flavour rewrite, creation loop |
| design-direction | origin of `x-superplay-design-direction`; anti-fatigue rules |
| cs-board-whiteboard | SRT-driven whiteboard annotation contract |
| creator-cockpit | operator cockpit notes |
| auto-editor, -effects, -export, -transcribe | silence/motion cutting and editor-export contracts for the `auto-editor` CLI |

## What was not copied, and why

| Omitted | Reason |
|---|---|
| `b-roll-finder` (Louise de Sadeleer, MIT) | adopted **verbatim** into the shared store at `.agents\skills\b-roll-finder`, licence included; duplicating it here would add nothing |
| `manim`, `remotion*`, `hyperframes*`, `video-shotcraft`, `ian-xiaohei-*`, `Jacky-motion`, `cs-board`, `imagegen`, `playwright`, `arkiv`, `localcaption`, `deep-research`, `Generative-Media-Skills`, `douyin-creator-scraping` | third-party trees or very large doc bundles; several already exist upstream or in the shared store. Archiving them would redistribute code whose licence is not ours to relicense. Resolve them from their own upstreams if needed. |
| every `scripts/` directory | the scripts import the retired `dy_1024` layout (`SENTINEL_PROJECT_ROOT`, `skills/broll-production/scripts`, `scripts/material_candidates.py`). A copied script that cannot run is worse than a recorded contract. |
| `hyperframes-animation` (827 KB), `remotion` (697 KB), `remotion-best-practices` (353 KB) | documentation bundles for stacks already installed or already in the shared store |

## Adoption decisions

| Skill | Decision | Wiring |
|---|---|---|
| `b-roll-finder` | **adopt** (shared store; front-matter `name` normalised to `b-roll-finder`) | `skill_route` step `broll_finder`, account `x-superplay-1024` |
| `material-source-research` | **adapt** into `x-superplay-source-research`; the contract became code | `skill_route` step `source_research` on both accounts; validator in the `assets` stage |
| `clean-talking-video` | **hold** — needs an ASR provider key (DashScope or local Qwen3-ASR) outside the MiniMax subscription boundary; status `MANUAL_ONLY` until a provider decision exists | archived only |
| `manim-video` | **hold** — requires Manim CE + LaTeX, neither installed; adopting it would create a skill that cannot render | archived only |
| `auto-editor*` | **hold** — external CLI not installed | archived only |
| `model-selector`, `prompt-translator`, `seedance-2.0-director` | **reject for now** — they recommend or target providers outside the MiniMax-only, `allow_payg: false` boundary | archived only |
| `douyin-creator-scraping` | **reject** — scraping path, and no capability gap it fills | not copied |
| `creator-cockpit`, `content-production`, `content-repurposer`, `social-content` | **hold** — generic content marketing; no pipeline stage needs them today | archived only |

"Hold" means the contract is preserved and nothing is claimed about it. None of
these is routed to, and none is described as active anywhere in this repository.
Two files are worth reading first: `jacky-hook/SKILL.md` (the four question
types a hook can open with) and `model-media-runtime/SKILL.md` (the local
speech/ASR/avatar worker map, including MiniMax H3 Ref2VA).

## Front matter

Every markdown file carries an added front-matter block (`status: superseded`,
`superseded_by`, `historical_context`, `source`). The bodies are otherwise the
upstream text, so links that pointed at the retired workspace's tree are dead
by design; this directory lives under `research/archive/`, which the docs link
checker skips.
