---
status: superseded
superseded_by: research/archive/dy1024-skills-2026-10-28/README.md
historical_context: copied contract from the retired dy_x1024 workspace; archived, not routed to
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
date: 2026-10-28
name: material-source-research
description: Build a rights-aware, review-gated candidate list for B-roll and visual evidence from an approved script. Use when a content package needs source candidates, Openverse search, source capture metadata, or a handoff to b-roll-production.
---

# Material source research

This is the active dy_1024 material route. It combines the upstream B-Roll
Finder methodology with the local `yt-dlp`/FFmpeg runtime: it discovers source
candidates, fetches explicitly selected sources into a review cache, and
promotes approved files into the canonical B-roll/rights ledger. It never reads
browser cookies, bypasses access controls, or silently clears a source.

## Installed / optional upstream projects

- `skills/b-roll-finder/` — installed upstream B-Roll Finder methodology; its
  beat routing and candidate scoring govern this active route.
- `skills/arkiv/upstream/` — installed Arkiv source tree used to index promoted
  local clips when its local model runtime is healthy.
- `skills/localcaption/upstream/` — installed Localcaption source tree used for
  timed transcripts of acquired sources when its whisper.cpp runtime is healthy.

## Workflow contract

1. Run `scripts/material_candidates.py normalize` with a user-exported JSON
   list, or `openverse` with explicit `--execute` after the user approves a
   search. The default is dry-run and offline.
2. Review `03_assets/source-candidates.json`. Every candidate must retain a
   canonical `source_url`, optional `direct_url`, creator/owner, license text,
   license URL, capture time, and a score breakdown. `status` remains
   `candidate`; it is never `cleared` or `used` here.
3. Run `skills/broll-production/scripts/broll_plan.py plan`. The plan joins
   candidates to beats by `beat_id`, `scene_id`, or `asset_id` and records the
   candidate file fingerprint. The user still selects the final source.
   Initialized content packages automatically record this route when the
   command succeeds; for a manually assembled package, record it with
   `scripts/skill_provenance.py record --route material-source-research
   --stage assets --execution-mode real` so the route remains auditable.
   If the research contract itself requires rendered page evidence, after the
   raw URL capture and `source_snapshot.py`, run
   `scripts/capture_source_screenshots.py --project <project> --focused --require-screenshots --strict`
   followed by `scripts/source_screenshot_visual_qc.py --project <project> --strict`. The visual QC checks
   output dimensions, target occupancy, segmentation continuity, and clipping
   safety; semantic correctness and final-video readability remain human
   review gates. This uses a fresh
   unauthenticated Chromium context, records topic/claim linkage and SHA-256,
   and writes full-page plus anchor-focused screenshots under
   `01_research/snapshots/screenshots/`; it does not promote them into the
   B-roll ledger.
   The B-roll planner also consumes this topic-declared policy through
   `screenshot_policy.material_capture`; when a planned beat matches an
   enabled trigger route, it emits screenshot requests. Execute those
   requests through the material module with
   `python scripts/material_candidates.py capture-screenshots --project <project>`.
   This command is automatic evidence collection only; media selection,
   download, rights clearance, and ledger promotion remain separate gated
   actions.
4. Present and obtain approval for the material-plan Gate before any state-changing
   selection or acquisition:

   ```powershell
   python scripts/workflow_gate.py check --project <project> --step assets_plan
   python scripts/workflow_gate.py approve --project <project> --step assets_plan --reviewer "reviewer" --confirm
   ```

   The plan must already contain automation/human responsibility, human
   confirmation status, canonical filename template, fallback and the locked
   screen-recording requirement. If the plan is not approved, `select`,
   `acquire`, and `promote` are blocked by the route itself.
5. Select and fetch the candidate into the real review cache:

   ```powershell
   python scripts/material_candidates.py select --project <project> `
     --candidate-id <candidate-id> --confirm
   python scripts/material_candidates.py acquire --project <project> `
     --candidate-id <candidate-id> --confirm
   ```

   The command invokes `yt-dlp` for page/video sources or the direct HTTP
   downloader for a direct media URL. It writes under
   `01_research/material-cache/` and records the downloaded SHA-256.
6. After rights review, promote it into the actual B-roll and ledger path:

   ```powershell
   python scripts/material_candidates.py promote --project <project> `
     --candidate-id <candidate-id> --approved-by "reviewer" `
     --approve-rights --confirm
   ```

   Promotion marks the B-roll plan as requiring a frozen-media validation
   receipt. Run it before final assets clearance:

   ```powershell
   python scripts/material_media_validator.py --project <project> --strict
   ```

   The validator proves package-relative path closure, SHA-256, FFprobe facts,
   full decode, and declared timecode bounds. It does not approve rights;
   `asset-ledger.csv` and the rights audit remain authoritative.

   Promotion copies the file to `03_assets/broll/raw/` and `selected/` using
   the plan's canonical filename, updates the B-roll plan and
   `asset-ledger.csv`, runs rights audit and rebuilds the asset index. Human
   confirmation remains pending until the reviewer checks the actual file.
   Run the final assets check/approval only after technical, visual, rights,
   naming and human confirmation fields are complete; this route is the
   primary acquisition path, not a fallback.

   Record the non-automatic visual confirmation after inspecting the promoted
   file, before the final assets Gate:

   ```powershell
   python skills/broll-production/scripts/broll_plan.py confirm --project <project> `
     --beat-id <beat-id> --reviewer "reviewer" --confirm
   ```
7. Enrich the promoted source with the installed project runtimes when their
   local prerequisites are healthy:

   ```powershell
   python scripts/material_candidates.py transcribe --project <project> `
     --candidate-id <candidate-id> --model base --language zh --confirm
   python scripts/material_candidates.py arkiv-index --project <project> `
     --candidate-id <candidate-id> --confirm
   ```

   The first command invokes Localcaption from `skills/localcaption/upstream/`;
   the second invokes Arkiv from `skills/arkiv/upstream/`. Missing whisper.cpp,
   Ollama, or Python dependencies fail the command explicitly and are recorded
   as a prerequisite error—there is no silent substitute.

## Safety boundaries

- No automatic URL downloads, scraping, cookies, login, or anti-bot bypass.
- Openverse results are discovery leads; verify the original license and
  attribution before clearance.
- Cultural/meme material remains user-supplied, as required by the current
  profile.
- Never replace factual evidence with generated imagery. Use concept-motion or
  a real source and record the fact status.
