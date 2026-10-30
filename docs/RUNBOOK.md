# Runbook

[English](RUNBOOK.md) | [简体中文](RUNBOOK.zh-CN.md)

> Real executable commands. Derived from actual script behavior, not assumptions.
> Last updated: 2026-10-03

## 0. Environment check

```powershell
python scripts/doctor.py
```

Checks: Python ≥3.10, Node ≥22, FFmpeg, ffprobe, git, Easel checkout (v0.2.1), repo layout.

Expected: all OK. If Easel checkout fails, run bootstrap (§1).

## 1. Bootstrap (first time or after cleanup)

```powershell
python scripts/bootstrap.ps1    # Windows
bash scripts/bootstrap.sh       # WSL/Linux
```

If Easel runtime is missing/broken:

```powershell
python scripts/resolve_easel.py --bootstrap
```

Acquisition ladder: git clone (Strategy A) → release archive (Strategy B) → BLOCKED.

## 2. Verify Easel runtime

```powershell
python scripts/verify_easel_runtime.py --resolve-tag
```

Expected: `VERIFIED · 982/982 blobs matched · 0 mismatch / 0 missing / 0 extra`

Offline mode (no network):

```powershell
python scripts/resolve_easel.py --offline
```

Uses recorded provenance in `runtime/easel-runtime.json`.

## 3. Create a new project

```powershell
python scripts\new_project.py --slug my-video --title "My Video Title"
```

Creates: `projects/my-video/` with `project.yaml` and standard subdirs.
Refuses to overwrite existing project.

### 3.1 Which pipeline does this project use?

The account decides. Two accounts, two chains, one command that says which:

```powershell
python scripts\account_route.py projects\easel-fi-audio-first
python scripts\account_route.py projects\easel-1024-proof --json
```

It reads `project.yaml` → `account_slug` → the DNA, and prints the ordered producer
sequence that the account's `evidence.mode` implies, plus the creative skill owners
declared in the same DNA:

| Account | Mode | Pipeline |
|---|---|---|
| `x-superplay-1024` | `EVIDENCE_LED` | `audio_first_plan` → `recording_plan` → `capture_terminal_evidence` → `build_evidence_package` → `qc_video` |
| `x-superplay-future-intelligence` | `EXPLANATORY` | `audio_first_plan` → `build_evidence_package` → `qc_video` |

- Both chains end at the same packager and the same QC. That shared receipt substrate is
  why the gates are common while the producers are not.
- A mode with no declared pipeline is refused (`EVIDENCE_MODE_UNMAPPED`); the router
  never guesses one, and a project with no `account_slug` has no pipeline at all.
- The router says which chain to run. It does not certify the result: that stays with
  `cut_qc` (`account_composition`, `manual_recording_forbidden`, `account_duration`) and
  with a person.

## 4. Prepare source assets

Place real evidence in:

```
projects/my-video/
  sources/
    screenshots/    ← PNG/JPG of GitHub, UI, results
    diagrams/       ← architecture/comparison diagrams
    recordings/     ← screen recordings (optional for V1)
    documents/      ← text excerpts, release notes
```

Author the script:

```
projects/my-video/
  script/
    master.md        ← master script (human-authored or LLM-drafted + corrected)
    storyboard.json  ← per-shot structure with provenance
```

## 5. Run V1 pipeline

> This is the oldest generation of the pipeline and it reads no account DNA. For
> anything that belongs to 1024 or Future Intelligence, resolve the chain first
> (§3.1) and follow the chain it prints; the account's composition, recording and
> duration rules are then enforced by `cut_qc`. Run V1 only for a project whose
> account declares no pipeline, or for the diagnostic fallback engine below.

### Production engine (Easel)

```powershell
python scripts\run_v1.py projects\my-video
```

What it does:
1. Reads `script/storyboard.json` (requires authored storyboard, not built-in lines)
2. Reads `script/master.md` (requires authored script)
3. Resolves pinned Easel runtime via `resolve_easel.py`
4. Generates narration via Easel `tts.py` (edge-tts, zh-CN-YunxiNeural)
5. Runs Easel `auto-short-video/assemble.py` (upstream, unmodified)
6. Burns subtitles via `assemble_easel.py` (Windows path workaround)
7. Outputs `final/easel.mp4`
8. Writes `receipts/build-easel.json`

Voice: **edge-tts** (free, no-key, no emotion engine). Marked `edge_tts_fallback`.

### Diagnostic engine (fallback)

```powershell
python scripts\run_v1.py projects\my-video --engine fallback
```

What it does:
1. Uses built-in `DEFAULT_SCRIPT_LINES` (test fixture only)
2. Renders voice via Windows SAPI → espeak → silence
3. Composes 6 shots with ffmpeg
4. Outputs `final/fallback.mp4` (NOT `final.mp4`)
5. Writes `receipts/build-fallback.json`

Voice: Windows SAPI (or silence). Marked `voice_quality: fallback`.
This engine is **diagnostic only** — never reports `production_ready: true`.

## 6. Run QC

```powershell
python scripts\qc_video.py projects\my-video
```

Checks: file existence, size, ffprobe parse, resolution (1080×1920), aspect ratio (9:16),
duration (30–120s), video codec (H.264), audio codec (AAC), audio presence,
script/storyboard existence, real-source ratio (≥70%), source provenance,
voice audibility (volumedetect), subtitle burn detection (multi-frame pixel scan).

Emits: `receipts/qc-report.json` + `qc-report.md`. Status: PASS / WARN / FAIL.

Grade a specific render:

```powershell
python scripts\qc_video.py projects\my-video --video easel
python scripts\qc_video.py projects\my-video --video fallback
```

## 7. Manual publish

V1 does **not** auto-publish. Open `final/easel.mp4`, review, and upload
through each platform's creator UI manually. Record in
`receipts/publish-receipt.md`.

## 8. Failure handling

If `run_v1.py` returns `BLOCKED`:
- Read the `reason` field
- Fix the underlying cause (missing script, missing storyboard, Easel unresolvable)
- Re-run

If `qc_video.py` returns `FAIL`:
- Video is not production-ready
- Common causes: duration out of range, aspect ratio wrong, audio missing,
  script/storyboard missing, real-source ratio < 70%

## 9. Test suite

```powershell
python scripts\run_tests.py                  # every tests/test_*.py, one verdict
python scripts\run_tests.py --list           # names only
python scripts\run_tests.py --only workflow  # substring filter
python scripts\run_tests.py --missing-from .github/workflows/ci.yml   # CI drift guard
python scripts\dev_check.py                  # the gate: policy, docs, i18n, DNA, all suites
```

55 suites (the `tests/test_*.py` files plus `scripts/test_basic.py`). Discovery, not a hand-maintained list: the gate once reported
"ALL CHECKS PASSED" while a migration suite was failing, because nothing called
it. Each suite runs in its own process; a suite that skips itself (missing
ffmpeg or a gitignored fixture) exits 0 and counts as a pass, but a suite that
cannot start is a failure, never a skip.

`scripts\test_basic.py` (9 tests: doctor execution, project creation
idempotency, QC FAIL on missing video, blob SHA-1 verification, path exclusion
symmetry, foreign remote rejection, archive provenance) is one of the suites and
still runs standalone.

`--missing-from` is what keeps CI honest: it parses the workflow's `run:` steps
(comments do not count) and fails when a suite exists but nothing executes it.
Four suites were in that state before 2026-10-28.

## 10. Native narration v2 (A/B/C sample)

Design: `adr/ADR-008-native-narration-v2.md`. The spoken script is checked
against the locked original and the evidence lock, and the three-way version
map (original / spoken / synthesis) is regenerated with `--write`:

```powershell
python scripts\verify_spoken_script.py --write
```

Dry run (fully offline; nothing is transmitted and no balance is read):

```powershell
python scripts\run_ab_sample.py
```

Real run. `--execute` is the explicit switch; every request is wrapped in
before/after plan-quota and balance reads and the run refuses without
`SAFE_INCLUDED_PLAN` on a Subscription-class credential. `--budget-chars` and
`--budget-asr-calls` are hard caps:

```powershell
python scripts\run_ab_sample.py --execute
python scripts\run_ab_sample.py --execute --a-mode fresh     # exact-text control (paid)
python scripts\run_ab_sample.py --execute --regenerate S02   # partial regeneration of the C arm
python scripts\run_ab_sample.py --execute --variants N --extra-segment S04 --receipt-suffix term-check
python scripts\run_ab_sample.py --recheck                    # recompute measurements only; no provider, no ASR
```

- A reuses a local excerpt of the existing Golden narration by default (zero
  provider cost); `--a-mode fresh` re-synthesises the control instead.
- The sample receipt and the term-check receipt are separate tracked files; an
  auxiliary run never overwrites the sample receipt.
- Real audio lands under `outputs/` (gitignored). The run stops at Founder
  listening: `production_ready` stays `false` and nothing is published.

## 11. Narration v3 (creator script, director, D/E/F sample)

Design: `adr/ADR-009-narration-v3-creator-director.md`. Validate the creator
script and the director plan and refresh the version map:

```powershell
python scripts\verify_creator_script.py --write
```

Dry run (offline; nothing transmits and no balance is read):

```powershell
python scripts\run_creator_sample.py
```

Real run. `--execute` is the explicit switch; the same Subscription-key-only
resolver, M Plan gate and before/after plan-quota and balance reads as v2
apply, and `--budget-chars` / `--budget-asr-calls` are hard caps:

```powershell
python scripts\run_creator_sample.py --execute
python scripts\run_creator_sample.py --execute --budget-chars 1200 --budget-asr-calls 5
python scripts\run_creator_sample.py --summary-only   # re-render the md receipt; no provider, no ASR
```

Listen blind, then read the key:

- files: `outputs/founder-v3-sample/candidate-1.wav` … `candidate-3.wav`
  (filenames carry no version information);
- key: `listening_key` in
  `projects/easel-enhanced-golden/review/narration-v3-sample-receipt.json`;
- score the six criteria **before** revealing it, in
  `projects/easel-enhanced-golden/review/listening-review-v3.md`.

ASR and CI passing are not naturalness verdicts; `production_ready` stays
`false` until the Founder approves.

## 12. Narration v3 sample video (the narration -> video bridge)

`scripts/build_v3_sample_video.py` turns one already-generated v3 candidate into
a watchable video against the locked evidence. **It makes no provider call.**

```powershell
python scripts\build_v3_sample_video.py --arm E
python scripts\build_v3_sample_video.py --arm D --out-name v3-sample-D
python scripts\build_v3_sample_video.py --arm E --audio outputs\founder-v3-sample\candidate-3.wav
```

- `--arm` resolves the candidate through the sample receipt's `listening_key`;
  the file must hash to that arm's `audio.sha256`, or the build refuses.
- unit -> evidence placement comes from the creator script's
  `source_paragraphs` and the evidence lock. No generated asset is used.
- per-unit durations are measured from the audio. An internal boundary is the
  detected silence whose midpoint is nearest the character-proportional
  expectation; the method is recorded per boundary in the receipt.
- it is a three-unit excerpt (U01, U03, U05) and the candidate audio lives under
  gitignored `outputs/`, so the build is host-local by design.
- output: `projects/easel-enhanced-golden/v3-sample-video/final/v3-sample.mp4`,
  `receipts/v3-sample-video.json`, `receipts/qc-report-v3-sample.{json,md}`.
  `production_ready` stays `false`.

Look options, still with the same audio and no provider call:

```powershell
python scripts\build_v3_sample_video.py --arm E `
  --project projects\easel-enhanced-golden\v3-sample-motion `
  --out-name v3-sample-motion --motion ken-burns --caption-mode phrase
```

- `--motion static` (default) or `ken-burns`. Ken Burns comes from the pinned
  upstream filter and zooms toward the top-left, because that filter sets no
  `x`/`y` expression.
- `--caption-mode sentence` (one cue per unit) or `phrase` (one cue per clause,
  the unit's duration split by character count; fragments under six characters
  merge with a neighbour).
- Build a comparison into its own `--project` so the two receipts do not collide.

## 13. Account DNA

The two account identities live in `config/accounts/*.json`. The DNA owns the
brand base, the composition ratios, the caption style, the cover rules and the
narrative template; the one-click prompt for each account sits next to it in
`config/accounts/prompts/`.

Validate the DNA against the brand base and against its own prompt:

```powershell
python scripts\check_account_dna.py
python scripts\check_account_dna.py --json
```

It fails when the schema, the palette, the ratio sum, the motion allow/deny
lists, the caption style, the cover whitespace floor, the recording policy, or
the agreement between a DNA file and its prompt breaks. The check is read-only
and part of `scripts/dev_check.py` and CI.

Rebuild one account variant from the DNA (no provider call; the narration and
cards come from the local `outputs/` tree):

```powershell
python scripts\build_account_variants.py
python scripts\build_account_variants.py --only x-superplay-1024
```

The caption `burn_style` is read from the DNA, not hardcoded in the script, so
changing the caption style is a config change. The variant videos stop at
`PENDING_FOUNDER_REVIEW` and claim no publication URL.

## 14. Evidence capture and the evidence-cut package

Capture only through an approved plan; the plan is the allowlist and it names an
argv, never a shell string:

```powershell
python scripts\capture_terminal_evidence.py projects\easel-evidence-capture\script\capture-plan.json --dry-run
python scripts\capture_terminal_evidence.py projects\easel-evidence-capture\script\capture-plan.json --only CAP-20261028-SKILLROUTE-AUTO
```

- `hold_after_exit_s` keeps the result on screen long enough to read; a capture
  that finishes in under two seconds is not readable evidence.
- A non-ASCII argv is mangled by the `cmd.exe` wrapper, so the plan uses ASCII
  queries (`--match auto-subtitle`, not the Chinese vocabulary).
- Adding a capture to an APPROVED plan is a new approval, not an edit.

Build, grade and bundle one evidence cut:

```powershell
python scripts\build_evidence_package.py projects\easel-1024-proof
python scripts\build_evidence_package.py projects\easel-1024-proof --skip-build
```

It runs, in order: `build_evidence_cut` → `build_evidence_cover` → `cut_qc` →
`write_review_bundle`, and exits non-zero when QC reports FAIL. It never records
a human decision.

- a placement carries `shots`; each view is capped by `target.max_visual_hold_ms`
  and an enlargement must be contained by its context view;
- `cut_qc` now fails a static placement that declares no views, and fails a
  measured frozen run longer than the declared hold;
- captions read `visual.caption_style` from the account DNA, and `_wrap` applies
  Chinese kinsoku.

QC PASS is technical. The cut stays `production_ready: false` until a Founder
score of at least 80 is recorded, and it stays distribution-blocked while any
capture is `internal_review` without a redaction receipt.

## 15. Audio-first cut planning (Build account)

Write the lines, then let the voice decide the timing:

```powershell
python scripts\audio_first_plan.py projects\easel-fi-audio-first
python scripts\build_evidence_package.py projects\easel-fi-audio-first
```

- `audio_first_plan.py` synthesises each line with MiniMax, measures it, writes
  `receipts/audio-first-plan.json` and generates `script/cut-plan.json`. Edit
  `script/lines.json`, never the generated plan; re-run with `--replan` after a
  change (the audio cache is reused, so no second provider call).
- a line needing more than 6.0 s is refused rather than held on one view;
  split the line instead of stretching the picture.
- `build_evidence_package.py` then runs build → cover → QC → review bundle.
- the Build account's gates are `manual_recording_forbidden`,
  `composition_ratio` and `evidence_mode: EXPLANATORY`; its declared composition
  is 70 % vector / 25 % code / 5 % metric within ±8 pp.
- edge-tts needs an external proxy on this machine; without one the planner
  fails closed instead of silently substituting a different voice.

### 15.1 Motion b-roll (HyperFrames)

```powershell
cd projects\easel-fi-audio-first\motion\arch-flow
npx --yes hyperframes@0.8.208 check
npx --yes hyperframes@0.8.208 render . -o ../../work/motion/arch-flow.mp4 -q delivery
```

- repeat per project; `motion/README.md` lists the six clips
- `work/motion/` is ignored; the HTML is the source and the mp4 is reproducible
- after a re-render, run `build_evidence_package.py` again: it re-reads each
  clip's SHA and refuses an asset that changed under the reviewed receipt
- the clips are support visuals (`evidence_capable: false`), never evidence

## 16. Code animation through the external skill

```powershell
$env:PYTHONUTF8 = "1"
python C:\Users\Administrator\.agents\skills\huashu-art-motion\scripts\engine\render.py `
  --spec projects\easel-fi-what-is-agent\motion\specs\p01.json `
  --out  projects\easel-fi-what-is-agent\work\clips\p01.mp4
python scripts\build_code_animation_sample.py projects\easel-fi-what-is-agent
python scripts\qc_video.py projects\easel-fi-what-is-agent --video easel.mp4
```

- use the host Python, not `uv run --with playwright`: the host resolves the
  Playwright Chromium already on this machine, while uv fetches a newer
  Playwright that asks for an absent browser revision
- `PYTHONUTF8=1` is required; the engine reads the spec with the default codec
- the composer places each synthesized line at its placement start, writes the
  SRT from the measured durations, and burns the account DNA caption style
- `qc_video` WARN is expected for a short pure-animation sample; record it, do
  not turn it into a PASS

Package a code-animation sample for review (cover + fingerprint + null-score
review stub):

```powershell
python scripts\package_code_animation_sample.py projects\easel-fi-what-is-agent
```

It renders the cover through the shared card renderer and fails if the
card-design density audit fails. It writes `receipts/cover.json`,
`receipts/review-bundle.json`, `receipts/human-review.json` (every score null)
and `receipts/runtime-receipt.md`. It never records a score.

Cloned voice and a local ambient bed:

```powershell
$env:PYTHONUTF8 = "1"
python scripts\synthesize_narration.py --text "..." --voice founder_primary_v1 `
  --out-dir projects\easel-fi-what-is-agent\assets\voice --receipt projects\easel-fi-what-is-agent\receipts\voice-01.json
python scripts\synthesize_ambient_bed.py --duration 45 --out projects\easel-fi-what-is-agent\work\bgm.wav
python scripts\build_code_animation_sample.py projects\easel-fi-what-is-agent
```

- the clone alias is `founder_primary_v1`; the provider id stays private, only its hash is in the receipt
- the bed is synthesised locally at −24.4 dBFS; the composer refuses a mix with less than 18 dB headroom
- a beat window is `speech + 0.35 s`, not a fixed 4 s, so the narration does not sit in dead air

## 17. Ordered production contract and document gates

New projects opt in; existing projects keep their layout.

```bash
python scripts/workflow_gate.py init    --project projects/<slug> --slug <slug> --account x-superplay-1024
python scripts/workflow_gate.py status  --project projects/<slug>
python scripts/workflow_gate.py check   --project projects/<slug> --stage script
python scripts/workflow_gate.py approve --project projects/<slug> --stage script --reviewer Founder --confirm
```

Validators run automatically: audience lens (`audience`), script rhythm +
duration + technical explainer + copy strategy (`script`), per-claim evidence
coverage (`storyboard`), rights ledger + source candidates (`assets`), visual
route (`compose`), and delivery manifest + publish plan (`delivery`). A change to
an artifact or to any upstream artifact makes the approval stale; there is no
force flag.

### 17.1 Source candidates

Write `source-candidates.json` beside the stage artifacts before acquisition.
The `assets` stage validates it whenever it is present.

```json
{"schema": "contentops.source-candidates/v1", "package_id": "pkg",
 "candidates": [{"candidate_id": "SC-001", "creator": "Example Project",
   "source_url": "https://example.com/x", "license": "public_domain",
   "license_text": "CC0 1.0", "license_url": "https://creativecommons.org/...",
   "capture_date": "2026-10-01", "status": "candidate",
   "score": {"relevance": 9, "evidence": 8, "rights": 10}}]}
```

- `status` is always `candidate`; a research list that can clear itself has
  nothing left for the ledger to check
- any licence except `owned` needs both `license_text` and `license_url`
- `promotable(document, id)` is the helper you call while promoting: it lists what
  still blocks the decision (unknown or unrecognised licence, missing licence URL,
  a record that is not `candidate`, incomplete score, weighted score under 6.0).
  It advises; the gate enforces the licence agreement, not the floor
- a ledger row may cite `source_candidate_id`; the licence must then agree

Skill side: `x-superplay-source-research` (the contract) is declared on both
account DNAs; `b-roll-finder` (the finding methodology) is declared on
`x-superplay-1024` only, because the Build account's visual gap is illustrations.

Document-only checks:

```bash
python scripts/workflow_docs.py check --kind forecast --input forecast.json
python scripts/workflow_docs.py check --kind rights   --input rights-ledger.json
python scripts/workflow_docs.py check --kind sources  --input source-candidates.json
python scripts/workflow_docs.py score --input candidate.json
python scripts/workflow_docs.py next-id --topic "topic" --root projects
python scripts/workflow_docs.py fingerprint-skill --dir <skill directory>
```

Exit `0` = pass, `1` = refused with named errors, `2` = usage error.

## 18. One cut, three platforms

Douyin, Bilibili and Xiaohongshu do not publish the same frame: the DNA's vertical
cut is 1080x1920, the Bilibili cut is 1920x1080, and Xiaohongshu takes the vertical
film with a 3:4 cover.

```powershell
# grade the master at its own declared frame (not a constant)
python scripts\qc_video.py projects\easel-1024-proof

# plan the other frames without writing anything
python scripts\derive_variants.py projects\easel-1024-proof --dry-run

# derive them, then package (the packager can do it in the same pass)
python scripts\build_evidence_package.py projects\easel-1024-proof --variants
```

- `qc_video` grades against `project.yaml`'s `format`; `--expect 1920x1080` overrides
  it for a file that has no project of its own. The old constant made a horizontal
  cut read as a broken vertical one.
- `derive_variants` converts with the pinned runtime's `reframe.py` (a hand-rolled
  filter chain is not allowed), probes every output, and writes
  `receipts/variants.json` binding the master, each derivative and the tool digest.
- It refuses an ungraded master, a receipt older than the master, and a master whose
  own QC says FAIL — **one FAIL is enough**, a newer PASS from another gate does not
  override it.
- Covers are **reported, never cropped**: `receipts/variants.json` says PRESENT,
  ABSENT or WRONG_FRAME per platform, and the fix is a card rendered at that frame,
  not a crop of the card designed for another one.
- A derivative is technically correct, not content-approved. `production_ready`
  stays false and the master's human review still decides.

## 19. Content router: choosing a topic

The router runs *before* a project exists. It answers "who is this for, and
what is it about", and it writes a brief the pipeline can pick up.

```powershell
# which accounts can be routed, and are they usable
python scripts\content_route.py accounts

# Route A: look for a topic, scoped by the account
python scripts\content_route.py start --account x-superplay-1024 --mode hotspot

# see the plan without fetching anything
python scripts\content_route.py start --account x-superplay-1024 --mode hotspot --plan-only

# Route B: the owner names the topic
python scripts\content_route.py start --account x-superplay-future-intelligence --mode topic `
    --topic "如何使用 LangGraph 开发可靠的 Agent？"

# a person chooses one candidate, by name
python scripts\content_route.py select --candidate CAND-XXXXXXXX --by "Founder"

# where is the run, and what does it need next
python scripts\content_route.py status --run RUN-20261030-XXXXXXXX

# a person approves the brief, and the project is created with it
python scripts\content_route.py approve --run RUN-20261030-XXXXXXXX `
    --reviewer "Founder" --note "值得做" --confirm --project langgraph-reliable-agent
```

- `--mode` is required. A run without one is refused with `ROUTE_SELECTION_REQUIRED`;
  the router never infers the route, and a run never changes route when it resumes.
- `start --mode hotspot` writes the plan, collects, filters and ranks, and stops
  at `CANDIDATES_READY`. It does **not** create a project and it does **not** call
  a media generator.
- `select` is the step a person takes. `--by` is required; there is no
  anonymous selection.
- `approve --confirm` is the step a person takes before the brief enters the
  pipeline. `--project <slug>` creates the project with `scripts/new_project.py`
  and puts `00_brief/brief.json` in it, so the episode starts where every other
  episode starts.
- An off-profile topic stops at `OUT_OF_PROFILE_REVIEW_REQUIRED`. The owner
  either changes the topic or re-runs with `--accept-off-profile --note "why"`.
- The pool lives in SQLite under `.local/content-router/` (gitignored).
  `CONTENTOPS_ROUTER_HOME` moves it.
- `--json` on any command prints the same result as JSON.

After the brief exists, the episode continues through the ordinary pipeline.
The copy review (`scripts\copy_review.py <project>`) is still the gate before
anything is rendered.

See [CONTENT-ROUTER.md](CONTENT-ROUTER.md) for the contract and the states.

### 19.1 The acceptance run

`scripts/router_e2e.py` runs both routes end to end and writes one receipt.

```powershell
# both routes, against the real sources
python scripts\router_e2e.py --actor "Founder"

# the topic route only; the hot-list leg is reported as blocked, not faked
python scripts\router_e2e.py --actor "Founder" --offline
```

- It creates its projects under `.verify-tmp\router-e2e\projects\`, not in the
  repository's own `projects\`, so an acceptance run leaves no episode behind.
- **The topic selection and the brief approval are performed by the acceptance
  run**, under the name `--actor` gives. The receipt says so in as many words.
  That is an acceptance run, not a standing approval: the copy review is still
  the gate before anything is rendered.
- It publishes nothing and generates no media.
- When a source is unreachable, the receipt names the failure and the run
  continues without it. `--offline` skips the network entirely and reports the
  hot-list leg as `OFFLINE_BY_REQUEST` rather than filling it with a fixture.
- The acceptance harness approves with `actor_kind="automation"` and
  `allow_automation=True`. A production caller cannot do that by accident: the
  same call without the opt-in is refused with `AUTOMATION_APPROVAL_REFUSED`.

### 19.2 Checking an approval, and handing the brief on

```powershell
# does the approval still match the brief on disk?
python scripts\content_route.py verify --run RUN-20261030-XXXXXXXX

# carry it into the pipeline (writes 00_brief\handoff.json), or check only
python scripts\brief_handoff.py projects\my-episode --dry-run
python scripts\brief_handoff.py projects\my-episode
```

`verify` returns `APPROVAL_STALE` when the brief changed after it was approved.
`brief_handoff.py` refuses the same way, and additionally refuses a `DEGRADED`
evidence forecast with `EVIDENCE_REQUIRED`. Exit code 4 means "not ready".

The next real step is still the script and the copy review:

```powershell
python scripts\audio_first_plan.py projects\my-episode
# {"status": "BLOCKED", "stage": "copy_review", ...}  (exit 4, nothing synthesised)
```

### 19.3 A real TrendRadar database

TrendRadar runs outside this repository (`D:\Software\sansan0\TrendRadar\v6.11.0`).
Point the router at the day it should read:

```powershell
$env:TRENDRADAR_DB_PATH = "D:\Software\sansan0\TrendRadar\v6.11.0\output\news\2026-10-30.db"
python scripts\content_route.py start --account x-superplay-1024 --mode hotspot
```

A directory also works — the newest `news\*.db` is used. The file is opened
read-only and is never written to. A database older than 24 hours is reported
`stale`, and its rows are rejected with `STALE_SOURCE` instead of entering the
pool as new hotspots.

### 19.4 The seven-day observation

```powershell
# one line per account per day, under .local\content-router\observation\
python scripts\router_observe.py --trendradar-db "D:\Software\sansan0\TrendRadar\v6.11.0\output\news\2026-10-30.db"

# the window so far
python scripts\router_observe.py --report --days 7
```

Run it once a day for seven days. The report prints, per source, how often it
answered, how many rows it gave, how often its data was stale, and how many
candidates the account's filter produced. That is the evidence for keeping or
dropping a source from the allowlist — not a single good or bad day.
