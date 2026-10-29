---
status: superseded
superseded_by: research/archive/dy1024-skills-2026-10-28/README.md
historical_context: copied contract from the retired dy_x1024 workspace; archived, not routed to
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
date: 2026-10-28
name: broll-production
description: Evidence-first B-roll planning and sourcing for the X•超玩1024 Douyin workflow. Use after the approved script and director material plan exist when the user asks to find, plan, source, match, or place B-roll, cutaways, product footage, GitHub evidence, screenshots, screen recordings, or generated visual gaps. Produces a responsibility- and naming-complete plan first; only acquires after assets_plan approval and only assembles after final assets clearance.
---

# B-roll Production

Use this skill as the B-roll orchestration layer inside the configured
`$env:SENTINEL_PROJECT_ROOT`. It complements the `content-copy-orchestrator`
internal `visual-handoff`; it
does not replace the workflow gate, rights audit, visual route, media delivery,
Remotion, or HyperFrames.

## Hard boundary

The default action is **plan, do not fetch**. Never download stock, capture a page, call a paid generation API, import into an editor, or render a final video during planning. The user must review and approve the `assets_plan` material-plan Gate first. Acquisition then remains subject to the final `assets` clearance Gate before assembly.

The agent narrows choices; it does not make an irreversible final taste decision. It may choose one best candidate for an objective route only after the user has approved the plan. Cultural/meme material is proposed, not silently fetched.

## Inputs

Read these in order:

1. `content.json` and `profiles/profile.json` (must be `account: X•超玩1024`, `platforms: [douyin]`).
2. `04_video/video-script.md` and `04_video/storyboard.csv`.
3. `04_video/director-material-plan.json`; require `status: ready` before sourcing.
4. `04_video/visual-route.json` when present; preserve its route and owner decisions.
5. `01_research/claims.json` when present; link every factual beat to claim IDs or mark it illustrative.
6. `production/video-engine/references/production-contract.md` and `asset-ledger.md`.

Run the deterministic planner:

```powershell
python "$env:SENTINEL_PROJECT_ROOT\skills\broll-production\scripts\broll_plan.py" plan --project <content-package>
```

It writes `04_video/broll-plan.json`, `04_video/broll-plan.md`, and `03_assets/asset-requests.md`. It does not modify `03_assets/asset-ledger.csv` and does not acquire media.

The workflow gate calls this planner automatically when
`workflow_gate.py check --step assets_plan` sees a ready
`director-material-plan.json` and a missing or stale B-roll plan. If the
director plan is not ready, the gate reports that it is waiting.

When `sources-input.json` explicitly enables `screenshot_policy.material_capture`,
the planner also writes a generic `screenshot_capture` section. It only uses
the topic-declared `focus_targets`; it does not infer URLs or selectors from a
topic name. A required capture is automatically executed by
`workflow_gate.py approve --step assets_plan --confirm` after the
`assets_plan` approval with:

```powershell
python "$env:SENTINEL_PROJECT_ROOT\scripts\material_candidates.py" capture-screenshots --project <content-package>
```

The command runs the existing browser capture and visual QC executors, records
their receipts in the material plan, and remains separate from media download,
rights clearance, and ledger promotion.

Record the real plan-stage execution for provenance after the command succeeds:

```powershell
python "$env:SENTINEL_PROJECT_ROOT\scripts\skill_provenance.py" record `
  --project <content-package> `
  --route broll-production --stage assets-plan --status success --execution-mode real `
  --command "python skills/broll-production/scripts/broll_plan.py plan --project <content-package>" `
  --skill-path "$env:SENTINEL_PROJECT_ROOT\skills\broll-production\SKILL.md" `
  --input 04_video/video-script.md --input 04_video/storyboard.csv `
  --output 04_video/broll-plan.json --output 04_video/broll-plan.md --output 03_assets/asset-requests.md `
  --note "Generated review-only B-roll plan; no media acquisition or editor import."
```

## Workflow

### 1. Interpret the editorial beat

Read the whole script before searching. State what the viewer must understand, then source the point rather than the nearest keyword. A named company may require its actual product action, a quote may require the original post, and a statistic requires the underlying chart or page.

For each beat record:

- exact scene and time range;
- spoken line/subtitle and viewer job;
- related `claim_ids` and `fact_status` (`evidence`, `illustrative`, `reconstructed`, or `opinion`);
- desired B-roll duration, landing offset, framing, safe area, and transition;
- one visual owner; if its source is unavailable the beat is blocked.

### 2. Route to the right source

Use this precedence:

1. user-owned footage, screen recording, documents, product captures, and data;
2. official or directly licensed media;
3. public-domain material with provenance;
4. deterministic charts, diagrams, HTML, Remotion, or HyperFrames;
5. generated imagery/video only for an approved illustrative gap.

Use `references/route-matrix.md` for route triggers, source strategy, scoring, and Douyin cadence. Do not use a generated frame as evidence of a product, UI, code, number, quote, experiment, or news event.

### 3. Build the plan before acquisition

Each plan item must include `source_strategy`, `rights_plan`, `candidate_policy`, responsibility fields, naming fields, and a concrete `asset_id` for any non-card asset. Use `status: requested` or `planned` until a human approves the `assets_plan` material plan; final files remain pending the `assets` clearance Gate. Keep generated media explicit; factual gaps remain blocked until evidence or editable motion is supplied rather than being replaced by a raster substitute.

Default cadence for X•超玩1024 videos follows the selected duration tier: 1 minute (45–75s), 2 minutes (90–150s), 3 minutes (150–210s), 4 minutes (210–270s), or 5 minutes (270–330s). Longer tiers require proportionally more evidence and visual duties; never pad a short idea.

- hook: dense proof or product cutaway in the first 3 seconds;
- body: sparse, precise punctuation around claims and product actions;
- screen recording: at least 25% of the finished video when the topic is a tool or workflow;
- no more than two visual systems and no more than two consecutive generated scenes.

### 4. Get the material-plan Gate approval

Present the plan and the asset request list. The plan approval path is:

```powershell
python "$env:SENTINEL_PROJECT_ROOT\scripts\workflow_gate.py" check --project <content-package> --step assets_plan
python "$env:SENTINEL_PROJECT_ROOT\scripts\workflow_gate.py" approve --project <content-package> --step assets_plan --reviewer "..." --confirm
```

Do not acquire, select, generate, or capture material until this plan approval exists. Every beat must identify `automation_mode`, `automation_owner`, `human_owner`, `human_confirmation_required`, `filename_template`, `expected_filename`, and `naming_check`. If the plan changes, let the existing fingerprint mechanism invalidate downstream approvals.

### 5. Acquire, clear, assemble, verify

After `assets_plan` approval only:

- If the material plan contains `screenshot_capture.required=true`, execute
  the automatic page-evidence capture first with the command above. The final
  `assets` Gate requires its visual QC receipt.
- cluster requests by source and fetch/capture each source once. The primary acquisition route is `material-source-research`: selected candidates are fetched into `01_research/material-cache/` with `yt-dlp`/HTTP, then explicitly promoted into the B-roll folders and ledger. It is an acquisition route, not a renderer;
- cache originals under `03_assets/broll/raw/`, selected clips under `selected/`, proxies under `proxies/`, and contact sheets/QC under `qc/`;
- update the canonical asset ledger, including SHA-256 and source capture date;
- use word-level/SRT timestamps when available; land B-roll just after the spoken trigger, never before;
- default to muted B-roll over narration, full-bleed cover-crop for vertical delivery, and phone-safe subtitles;
- let Remotion own the editable master composition/timeline; let HyperFrames
  provide only its transparent overlay, with OpenChatCut/FCPXML as optional
  interchange helpers;
- render a preview, extract a frame at every B-roll midpoint and join, inspect the contact sheet, and run rights/provenance/QC checks.

The local worker performs the actual timeline insertion. Material acquisition is
performed by `material-source-research`; this worker still never bypasses the plan Gate:

```powershell
# Fetch the selected candidate into the real review cache.
python "$env:SENTINEL_PROJECT_ROOT\scripts\material_candidates.py" acquire `
  --project <content-package> `
  --candidate-id candidate-... --confirm

# After rights confirmation, promote it into the canonical B-roll and ledger.
python "$env:SENTINEL_PROJECT_ROOT\scripts\material_candidates.py" promote `
  --project <content-package> `
  --candidate-id candidate-... --approved-by "..." --approve-rights --confirm
```

After promotion, run the frozen-media validation receipt before final assets
clearance:

```powershell
python "$env:SENTINEL_PROJECT_ROOT\scripts\material_media_validator.py" --project <content-package> --strict
```

The assets Gate consumes `03_assets/media-validation.json` when promotion has
marked validation as required. This validates path closure, SHA-256, FFprobe,
full decode, and timecode bounds; rights remain governed by the canonical
ledger and rights audit.

After technical media validation, build the representative material canary and
visual-lock artifacts:

```powershell
python "$env:SENTINEL_PROJECT_ROOT\scripts\material_canary.py" --project <content-package> --strict
```

This selects opening, information-dense, and late beats deterministically. A
technical pass does not silently approve aesthetics; an explicit human decision
can be recorded only after inspection:

```powershell
python "$env:SENTINEL_PROJECT_ROOT\scripts\material_canary.py" --project <content-package> --decide approved --reviewer "..." --confirm
```

Validate placement contracts and, when available, rendered geometry traces:

```powershell
python "$env:SENTINEL_PROJECT_ROOT\scripts/material_placement_qc.py" --project <content-package> --strict
```

Finally, create the local runtime-plan adapter without installing a second
runtime or bypassing the existing workflow gates:

```powershell
python "$env:SENTINEL_PROJECT_ROOT\scripts/erduo_runtime_adapter.py" --project <content-package> --strict
```

After promotion, confirm the human, rights, technical, and visual fields and approve final assets clearance:

```powershell
python "$env:SENTINEL_PROJECT_ROOT\scripts\workflow_gate.py" check --project <content-package> --step assets
python "$env:SENTINEL_PROJECT_ROOT\scripts\workflow_gate.py" approve --project <content-package> --step assets --reviewer "..." --confirm
```

The visual confirmation is an explicit, non-automatic action after inspecting
the actual promoted file:

```powershell
python "$env:SENTINEL_PROJECT_ROOT\skills\broll-production\scripts\broll_plan.py" confirm `
  --project <content-package> --beat-id broll-scene-01 `
  --reviewer "..." --note "画面、事实边界、构图和命名已检查" --confirm
```

Only then assemble:

```powershell
# Copy a source that has already been cleared into raw/ and selected/ when
# importing a separately captured local file (the material route is preferred
# for discovered candidates).
python "$env:SENTINEL_PROJECT_ROOT\skills\broll-production\scripts\broll_execute.py" prepare `
  --project <content-package> `
  --asset broll-scene-01=D:\approved-media\github-demo.mp4

# Overlay selected B-roll on the generated/base video, preserve base narration,
# and emit 08_exports/preview/preview-broll.mp4 plus midpoint QC frames.
python "$env:SENTINEL_PROJECT_ROOT\skills\broll-production\scripts\broll_execute.py" assemble `
  --project <content-package> `
  --input 08_exports\preview\preview.mp4
```

`prepare` records `acquisition.local_path` and SHA-256 in the plan after checking
that the matching ledger row is already `cleared`/`used`. `assemble` requires
`workflow.steps.assets_plan.status=approved`, `workflow.steps.assets.status=approved`, intact plan/clearance fingerprints, and a
cleared/used ledger row for every non-skipped beat. B-roll is muted by
default and the base video's audio stream is retained. Its output is a real
FFmpeg-composed MP4, not a plan placeholder.

If one acquisition method fails, switch source/method once; after the second failure drop the beat and record the reason. Do not repeatedly retry or pad the edit with inaccurate footage.

## Output contract

The plan must expose:

- `schema_version`, `content_id`, `account`, `platform`, `status`, `generated_at`;
- `material_contract_version` and `screen_recording_requirement` (a human-owned `product-ui` beat when a claim requires direct screen evidence; no global ratio);
- `input_fingerprints` for the script, storyboard, director plan, visual route, and claims files that existed;
- `beats[]` with `scene_id`, `time_in`, `time_out`, `viewer_job`, `claim_ids`, `route`, `visual_owner`, `source_strategy`, `rights_plan`, `fact_status`, `placement`, `requires_acquisition`, `automation_mode`, `automation_owner`, `human_owner`, `human_confirmation_required`, `human_confirmation_status`, `filename_template`, `expected_filename`, `naming_check`, and `status`;
- an explicit plan `approval` object that is `null` until the `assets_plan` workflow gate approves the plan; final asset approval is recorded separately in `workflow.steps.assets`;
- `notes` that distinguish a plan from acquired/cleared media.

The execution manifest, if used, should contain `local_path`, `source_url`, `creator_or_owner`, `license`, `capture_date`, `sha256`, `timecode_in`, `timecode_out`, `edit_notes`, and `approval_status`. Keep those fields aligned with `03_assets/asset-ledger.csv`; the ledger remains authoritative for rights.

## Validation

```powershell
python "$env:SENTINEL_PROJECT_ROOT\skills\broll-production\scripts\broll_plan.py" validate --project <content-package>
python "$env:SENTINEL_PROJECT_ROOT\scripts\rights_audit.py" --project <content-package>
python "$env:SENTINEL_PROJECT_ROOT\scripts\skill_catalog.py" --isolated --skill-root "$env:SENTINEL_PROJECT_ROOT\skills" --strict
```

Validation must fail for missing viewer jobs, claim linkage, source strategy, rights plan, responsibility or naming fields, invalid route/owner pairs, premature `cleared/used` records, an empty candidate manifest when validation is requested, or a plan whose input fingerprints no longer match. `source-collector` and `rights-audit` are internal route/script capabilities; they do not replace the two workflow gates.

## Related skills

- `content-copy-orchestrator` / `visual-handoff`: create the evidence-first scene/material contract before this skill.
- `visual-route`: select the visual representation and motion owner.
- `media-use` / `media-delivery`: acquire, transform, import, assemble, and deliver after approval.
- `rights-audit`: verify the canonical ledger.
- `hyperframes` / `remotion`: render only the explicitly assigned motion owner.
- `content-copy-orchestrator` / `multi-shot-adapter`: use only when an approved illustrative multi-shot generation gap remains.
