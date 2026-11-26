# Runbook

[English](RUNBOOK.md) | [简体中文](RUNBOOK.zh-CN.md)

> Real executable commands. Derived from actual script behavior, not assumptions.
> Last verified: 2026-11-25 — added `scripts/topic_to_m5.py` (TOPIC derivative → M5 script projection) and `tests/test_topic_m5.py` (10/10). The tool was exercised end to end on `agentguide-learning-roadmap`: QC PASS and visual motion gate green (fast_ratio 0.0981). No review, publication or provider spend was granted.
> Last verified: 2026-11-23 — offline checks: graphic workflow 55/55, production gates 39/39, pre-copy regressions 26/26, MiniMax image regression 86/86 and media-use rights 7/7. Two Codex attempts were authorized: the first was blocked by the old parser; the second generated a PNG and project-local generation receipt through the repaired adapter. Quota delta was not reported. This was a temporary workflow smoke project, not an approved article; package, rights/quality review and publication remain pending.
> Last verified: 2026-11-14: X CLI now accepts `--post-format text|image` on `--new` (image is legacy default). A text package has no image/ALT upload step; image-format posts still require genuine PNG/JPEG+ALT. `--package` never posts, and only a human-confirmed X status URL can be recorded by `--mark-published`.
> X policy: Strategy canonical SOP and registered account DNA; source metrics and publishing still require human verification.

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

Which engine is production is a registry fact, so start there:

```text
python scripts/easel_engine.py show
```

Expected (2026-11-15): `active: v0.3.0`, with `v0.2.1` listed as the rollback tree.

Verify the active engine. This compares the tree against the pinned upstream tree
and, for an instance that carries declared tuning, against the overlay record
instead — the strongest proof available, and the method used is reported:

```text
python scripts/easel_engine.py verify v0.3.0
```

Expected: `VERIFIED · matched: 1071 · recorded_at: runtime/easel-runtime-v0.3.0.json`

Offline resolution (no network), with per-engine provenance:

```text
python scripts/resolve_easel.py --offline
python scripts/resolve_easel.py --offline --engine v0.2.1
```

### 2.1 Install another declared engine (never downloads)

```text
python scripts/easel_engine.py install v0.3.0 --from <prepared-tree>
```

Every file is compared with `runtime/easel-workbench-upstream-tree.json` (or the
overlay record, for tuning) before anything is copied, and an existing non-empty
target is refused. A refusal leaves no partial tree.

### 2.2 Move the production engine, and undo it

```text
python scripts/easel_engine.py switch v0.3.0 --dry-run   # report only
python scripts/easel_engine.py switch v0.3.0             # verify, then write
python scripts/easel_engine.py switch v0.2.1             # rollback
```

`switch` verifies the target *before* it writes, then updates
`runtime/easel-pins.json`, re-derives `runtime/easel.lock.json` and appends to
`runtime/easel-engine-switch.json`. A target that is not installed, or that fails
verification, is refused and nothing changes. Then re-render a golden project and
compare its sha256 — the 2026-11-15 switch left `projects/m5-easel-pin` byte-identical.

## 3. Create a new project

```powershell
python scripts\new_project.py --slug my-video --title "My Video Title"
```

Creates: `projects/my-video/` with `project.yaml` and standard subdirs.
Refuses to overwrite existing project.

## 3.1 Video pre-copy research gate (required for VIDEO and shared topics)

VIDEO copy and shared, medium-neutral `TOPIC` packages need a signed research
receipt before copy approval/production. A standalone GRAPHIC_TEXT draft does
not: write the draft first, preserve source links for factual claims, and leave
unverified claims marked for follow-up. See
[PRECOPY-RESEARCH.md](PRECOPY-RESEARCH.md) for the VIDEO/shared-topic contract.

```powershell
python scripts\preresearch.py init --project projects\my-video
python scripts\preresearch.py intent --project projects\my-video
# Verify sources and complete the research artifacts.
python scripts\preresearch.py check --project projects\my-video
python scripts\preresearch.py approve --project projects\my-video `
  --reviewer "Your Name" --opinion "Read the sources" --confirm
```

`check` exits 4 while blocked. VIDEO approvals require a named reviewer,
written opinion and `--confirm`; edits after signing make the receipt `STALE`.
Standalone graphic drafts are not held behind this form.

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

## 4.1 Stable production entry (required for real production)

`produce_video.py` and `m5_production.py` are low-level/diagnostic paths. They
do not require an account, an approved copy, an asset shortfall decision or a
bookend decision. A run that skips those steps still renders, but silently
degrades to Windows SAPI, no digital human and
`receipts/motion-stage.json: NOT_CONFIGURED`.

Use the single stable entry for VIDEO. It asks for the video-specific decisions,
records them, and writes the load-bearing `account_slug` block. GRAPHIC_TEXT uses
the same command but derives the account from the project or Bundle handoff; it
skips narration, motion, avatar, budget and reviewer questions.

```powershell
# VIDEO: answer its production decisions, then review copy separately.
python scripts\make_content.py answer --project projects\my-video --interactive
python scripts\copy_review.py projects\my-video --approve `
  --reviewer "Your Name" --opinion "Reviewed the narration" --confirm
python scripts\make_content.py check --project projects\my-video
python scripts\make_content.py run --project projects\my-video --mode STRICT

# GRAPHIC_TEXT: account is read from project.yaml or the handoff.
python scripts\make_content.py answer --project projects\my-article
python scripts\make_content.py check --project projects\my-article
python scripts\make_content.py run --project projects\my-article --mode STRICT
```

VIDEO has eight gates. GRAPHIC_TEXT checks account binding, source links, image
ALT/rights and graphic runtime; shared-topic lineage is checked when applicable.
A graphic package remains `AWAITING_MANUAL_REVIEW`; these checks do not authorize
a provider call or platform delivery.

- `answer` materialises the evidence pack and source refs from project metadata.
- VIDEO `runtime_readiness` checks only capabilities selected for that run.
- `--asset-policy minimax-authorized` is refused while ADR-014 holds or no
  subscription key exists.
- `produce_video.py` remains diagnostic unless invoked through the stable entry.
- `qc_video.py --video` requires an `.mp4` filename (or `easel` / `fallback`).

## 5. Run V1 pipeline

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

### Evidence-first chain (M5)

```powershell
python scripts\m5_production.py projects\m5-easel-pin
```

Runs sources → assets → claims → script → narration → subtitles → storyboard →
compose → QC → review, writing a receipt per stage. It refuses (`exit 4`,
`state: BLOCKED`) at the first stage that cannot be backed: a source outside the
repo, an asset whose SHA-256 drifted, a claim whose quote is not verbatim in its
source, an undeclared asset, or subtitle coverage below 0.8.

For external visual assets, the rights helper can group only assets with the same source, licence, review scope and modifications. `review_batch()` produces pending batches bound to every asset ID and SHA-256; it does not clear rights. After a named human decision, `apply_batch_decision()` writes the per-asset sidecars and returns the updated manifest, which the caller persists before rerunning M5 `stage_assets`. A changed hash or scope requires a new decision. An assets-stage PASS is not final QC, human acceptance or publication authorization.

`--skip-compose` stops after the storyboard (no ffmpeg, no Easel) and is what CI
and a fast edit loop use.

#### Shared TOPIC derivative → M5 script

When a selected topic was reviewed once as a medium-neutral TOPIC and the VIDEO
child already owns an approved `00_brief/copy-derivative.json`, do not hand-write
`script/script.json`. Use the projector:

~~~powershell
python scripts\topic_to_m5.py projects\my-video --json
python scripts\topic_to_m5.py projects\my-video --check
~~~

It reads the reviewed derivative and the CREATED_BY_OWNER visual cards registered
in `sources/assets.json`, then writes **only** `script/script.json`. It splits
long segments into <= 28-character lines so each narrated Huashu shot stays under
8 seconds, keeps every spoken character byte-for-byte (caption == narration and
each segment's pieces rejoin to the reviewed text), covers every `claim_refs`,
uses the camera-push grammar (`evidence_zoom`) that passes the film gate, and
rotates cards and focus rectangles so adjacent shots never reuse the same source.
`--check` validates an existing script against all of those invariants; neither
mode signs a review or grants publication.

Two prerequisites are deliberately not automated: an approved copy derivative,
and authored visual cards registered as `CREATED_BY_OWNER` real bitmaps. LICENSED
source screenshots stay evidence and are never used as Huashu visual sources, so
a project with no authored cards is blocked with `NO_VISUAL_CARDS`. For an
explainers-style video, generate the cards with the project's own card generator
before running this tool, then register them in `sources/assets.json` with
matching SHA-256 and `evidence_capable: false`.

#### Archiving a finished run

M5 registers each rendered Huashu shot as a `huashu-*` asset in
`sources/assets.json`. Those entries point at files under
`assets/generated/huashu/`. When moving a finished project, copy the generated
shot files together with the manifest: a manifest that declares a `huashu-*`
asset whose `repo_path` no longer exists is an orphan, and the assets stage
blocks the next run with `file missing` before any re-render can happen. If the
generated shots are intentionally not carried over, remove their declarations
from `sources/assets.json` so the next run regenerates them cleanly. Keep the
final MP4 and its receipts either way.

#### Motion skills: hybrid planning, not one account backend

The repository ships five render backends: `huashu-art-motion` and
`huashu-motion` (local, non-paid, rendered through M5's own adapter) and the clip
renderers `remotion`, `motion-canvas` and `manim` (through `animation_render.py`).
Remotion additionally declares thirteen pinned skill packages. A shot kind states
which backends can draw it in `SHOT_COMPATIBILITY`; the film then uses a mix.

Plan the mix before production:

~~~powershell
python scripts\plan_motion.py projects\my-video --json
~~~

This probes each backend through its real readiness path — Huashu through the M5
adapter preflight, clip renderers through `animation_render.preflight` — and
writes `receipts/motion-orchestration.json` with one backend per shot. This is a
**planning receipt** and is harmless: it never blocks the ordinary Huashu
auto-plan. Only READY backends are chosen; an explicit per-shot backend is never
replaced, a declared default is a preference rather than a forced single backend,
and an unclassified shot with no ready fallback is BLOCKED instead of becoming a
still.

To actually render the mix, materialize the shot that has an honest clip spec:

~~~powershell
python scripts\plan_motion.py projects\my-video --materialize
~~~

This writes `motion/orchestrated-plan.json`, a **clip overlay** naming only shots
that can be given a contract-valid, claim-free spec (currently editorial
title cards on Remotion). The next M5 run authors every Huashu spec from the
measured narration duration, then applies the overlay to switch the named shots
to their clip backend; the rest stay on Huashu. Leave `motion.shot_plan` unset —
pointing it at the overlay would skip the auto-plan and leave Huashu shots with
no authored spec. Only a materialized receipt is enforced: a mismatched backend
then BLOCKS instead of degrading. A mixed run is reported as `hybrid`; it remains
a technical draft with `production_ready: false` until human review.

#### Narration default: MiniMax founder clone

Both video account DNAs declare `provider_hint: minimax_m_plan/speech-2.8-hd`
with `voice_alias: founder_primary_v1`, and `make_content.py answer` now uses the
founder clone as its default in both interactive and scripted runs. Pass
`--narration sapi` explicitly for an offline diagnostic voice; SAPI is never a
silent fallback after a clone failure. The clone path needs a MiniMax
subscription or API key in the environment or `.env`; `runtime_readiness` checks
for either name before any paid call. A `MINIMAX_CLONE_KEY` alone is the
pay-as-you-go clone route and does not satisfy that billing gate. A passing gate
is permission to attempt the call, not evidence that a clone was synthesized.
The run always ends at `PENDING_FOUNDER_REVIEW` with `production_ready: false` —
a green QC is not publishing permission (ADR-005).

The `asr_backcheck` stage transcribes the narration and compares it with the
spoken script. With no `SILICONFLOW_API_KEY` it reports `SKIPPED` — that is not a
pass. A coverage failure blocks human review; a pass never approves anything. See
[ASR-BACKCHECK.md](ASR-BACKCHECK.md) for the model id, endpoint override and the
comparison rules.

To explicitly import a local folder of images or videos for a preview, pass
`--assets`:

~~~powershell
python scripts\m5_production.py projects\my-video --assets D:\media\selected-for-preview
~~~

M5 copies supported files into `assets/imported/user/`, records their hashes in
`sources/assets.json`, and writes `receipts/user-assets-import.json`. Video
imports retain the source clip, record its codec, duration, dimensions, frame
rate and audio presence, and extract start, middle and end review frames. The
receipt also points to `receipts/user-assets-contact-sheet.jpg`. These assets
are `USER_PROVIDED_LOCAL` with `LOCAL_PREVIEW_ONLY` scope: selection does not
grant distribution rights or make an asset factual evidence. Use a separate
rights review before distribution, and keep factual claims bound to their
independent source artifacts. The option imports media; it does not rewrite
script asset IDs or approve publication.


### Automatic media-use materials in M5 (offline only)

With the approved adapter and a verified machine runtime lock configured, the
M5 stage can invoke media-use between the sources and assets stages. Configure
per-project material needs in project.yaml:

~~~yaml
media_use:
  enabled: true
  mode: local-only
  requests:
    - id: support_visual
      kind: image
      intent: local support image
      rights:
        license_id: OWNED-BY-OPERATOR
        source_url: OWNED
        reviewed_by: <reviewer>
        reviewed_at: "2026-10-31"
        review_evidence: assets/support.rights.json
        attribution: project owner
        synthetic: false
~~~

A bare `rights_reviewed: true` is refused. Each request needs a review sidecar
(`assets/<id>.rights.json`, schema `contentops.media-rights-review/v1`) whose
licence, source URL, reviewer, date and attribution match the request exactly.
Software licences and non-commercial licences cannot license media; synthetic
assets are never evidence.

Place a rights-cleared candidate in the project's assets/ directory and refer
to support_visual in script/script.json as the asset_id. For diagnostics only,
the direct M5 command is:

~~~powershell
python scripts\m5_production.py projects\my-video
~~~

For production, use the gated `make_content.py` entry instead. Direct M5 is a
diagnostic path and does not establish that the production gates passed.

No separate media_use_adapter.py command is needed. M5 automatically adopts
project-local assets, resolves them offline via the approved adapter, imports
them with provenance sidecars and verifies SHA-256 before passing them to
existing M5 asset validation, storyboard, compose and QC. Already declared
assets in sources/assets.json take precedence; unfulfilled needs block rather
than silently accessing a network or paid provider.

The stage creates receipts/media-use-stage.json plus the adapter's per-file
import receipt. Licensed external visuals are visual support only and may
not become factual evidence. This version supports image/icon/logo placement and
BGM/SFX support tracks; audio never becomes evidence.
Projects without media_use.enabled=true behave as before.

The adapter was merged through PR #71. A verified host lock and the applicable
asset rights are still required; hosted tests use synthetic fixtures and make no
provider calls.

## 5.1 Bundle handoff and dual lines

Optional: bind a project to a Strategy Content Bundle in `project.yaml`:

```yaml
content_bundle:
  path: bundle.json          # relative to the project, or to the repo root
  account: explorer          # explorer | thinktank
  platform: x                # optional delivery placeholder
  source_map:
    SRC-20261102-001: SRC-RUNTIME-001
```

The M5 run writes `receipts/bundle-handoff-video.json` before the sources stage.
A missing/mismatched source map blocks the run; a `PLANNED` platform records a
delivery blocker but does not block video production.

Every handoff records the Bundle's logical path, scope and SHA-256, and both
line builders re-check it: a handoff whose Bundle changed is refused with
`BUNDLE_CHANGED`, and a handoff that names no Bundle is refused with
`HANDOFF_UNBOUND`. Rebuild the handoff after editing a Bundle. The Bundle must
live inside the project or the repository, so a file copied from a Strategy
checkout is recorded by a relative path, never an absolute one.

Standalone handoff (no production, no publication):

```powershell
python scripts\bundle_handoff.py projects\my-video\bundle.json `
  --account explorer --format VIDEO --project-slug my-video `
  --source-map SRC-20261102-001=SRC-RUNTIME-001 --out-project projects\my-video

python scripts\bundle_handoff.py projects\my-video\bundle.json `
  --account explorer --format GRAPHIC_TEXT --project-slug my-article `
  --platform wechat_article --out-project projects\my-article
```

## 5.2 Graphic image generation and manual package

### Normal use: tell the assistant what to make

Give the article/topic and target platform; the assistant should reuse the open
project, account and Bundle, then draft first. **The working copy is the one
routine human review point.** After that review, the assistant continues with
images, layout, automated stage checks and the offline package without asking you
to approve the brief, outline, image placement, layout or QC separately. A real
provider call still needs your explicit provider/count authorization. Unverifiable
rights mean excluding or blocking that asset, never inventing approval. Creating
a platform draft still needs separate explicit authorization; this workflow never
publishes.

Record the working-copy decision once after review (or edit `draft.md` directly):

```powershell
python scripts\copy_review.py projects\my-article --approve `
  --reviewer "Reviewer" --opinion "Reviewed the graphic working draft" --confirm
```

### CLI reference (optional)

The graphic line can create a reviewable package, not a platform draft. Package
creation remains separate from image generation:

```powershell
python scripts\graphic_package.py `
  --project projects\my-article `
  --handoff projects\my-article\receipts\bundle-handoff-graphic_text.json `
  --input projects\my-article\graphic-input.json
```

Only these three image methods are selectable for new packages:

| Method | Route | Boundary |
|---|---|---|
| `codex_imagegen` | Codex CLI's native `image_gen` tool | One image per run; no API, browser, MCP or fallback. Actual dimensions are recorded; 16:9 aspect is required, not a guaranteed exact pixel size. |
| `ian_xiaohei_codex` | Host invokes `ian-xiaohei-illustrations` for shot list/prompts, then the same Codex native `image_gen` route | The CLI does not invoke the Skill. Its JSON output must bind each shot to the current article hash. |
| `minimax_subscription` | Existing `image-01` provider via `generate_image.py` and `BillingGuard` | Subscription only; PAYG and Credit Pack remain blocked. Default is 1024×576; width/height must satisfy the provider contract and be 16:9. Provider cache and transient sidecars stay under the selected scratch root; the project receives unique image/summary receipts. |

For comic-style explainers, the host should consult the pinned GitHub
[comic-explainer-illustration skill](https://github.com/chujianyun/awesome-gpt-image2-ppt-skills/blob/aa5fec05a1d1991d7653ed31c0407d513d0fa6d3/comic-explainer-illustration/SKILL.md)
as a prompt/storyboard aid before saving the prompt file. Use its 16:9, concise
visual-storytelling approach, preserving account DNA and character contracts;
do not force four panels or import its default characters. The resulting prompt
file is backend-neutral and is consumed by either `codex_imagegen` or
`minimax_subscription` on that selected route. With `ian_xiaohei_codex`, apply it
only as an optional prompt-shaping aid after Ian's shot/prompt output. This is
not another provider or CLI method. The reviewed GitHub revision has no declared
`LICENSE`/`COPYING`, so do not vendor its text or scripts into this repository.

The image-generation command accepts one prompt/shot per run. A plan-only call
makes no provider request. Real generation requires **both** `--execute` and
`--authorize-provider-usage`; each run permits one attempt and never retries or
switches methods. All execution methods require an operator-selected scratch root
under `D:\Temp\AI-Agents\<agent>\<task>`; Codex creates a unique run folder,
while MiniMax keeps its provider cache and sidecars there:

```powershell
python scripts\graphic_generate.py `
  --method codex_imagegen --project projects\my-article --asset-id shot-01 `
  --prompt-file 03_images\prompts\shot-01.md `
  --scratch-root "D:\Temp\AI-Agents\<agent>\<task>" `
  --execute --authorize-provider-usage
```

The wrapper runs `codex exec --ephemeral --sandbox workspace-write` with
`--ignore-user-config` and feeds the prompt over stdin. It accepts either a
completed native image-generation event bound to one fresh image, or a completed
Codex thread (`thread.started` + `turn.completed`) with exactly one image in that
new thread's `CODEX_HOME\generated_images\<thread_id>` directory. Missing,
ambiguous or stale output, path mismatches, and incomplete threads block the run.
It does not persist the Codex conversation. Codex did not report the quota delta
in the observed live attempt; the wrapper records it as unknown when unreported.
The model/version and exact requested pixel size are not assumed when the CLI
does not report them.

MiniMax uses the same authorization flags and the existing guarded provider:

```powershell
python scripts\graphic_generate.py `
  --method minimax_subscription --project projects\my-article --asset-id shot-01 `
  --prompt-file 03_images\prompts\shot-01.md `
  --scratch-root "D:\Temp\AI-Agents\<agent>\<task>" `
  --width 1024 --height 576 `
  --execute --authorize-provider-usage
```

For `ian_xiaohei_codex`, first prepare the read-only, article-hash-bound handoff:

```powershell
python scripts\graphic_workflow.py plan `
  --workflow x --project projects\my-article --article 02_draft\draft.md `
  --illustration-skill ian-xiaohei-illustrations --json
```

The host invokes the selected Skill and saves its shot list as
`contentops.ian-illustration-result/v1` under the project, preserving the exact
article path/hash returned by the handoff. Then generate one selected shot:

```powershell
python scripts\graphic_generate.py `
  --method ian_xiaohei_codex --project projects\my-article `
  --article 02_draft\draft.md --skill-output receipts\ian-skill-result.json `
  --asset-id shot-01 --scratch-root "D:\Temp\AI-Agents\<agent>\<task>" `
  --execute --authorize-provider-usage
```

Generation writes a real image plus a project-local generation receipt with the
method, prompt hash, file hash, format, dimensions and non-evidence flags. It
returns `GENERATED_PENDING_REVIEW`; it does not approve AIGC disclosure, rights,
quality or publication. Add each output to `graphic-input.json` with the returned
`path`, `asset_id`, ALT text and `generation` receipt reference. Remote outputs
also need a separate, named rights review tied to the exact generation ID and
asset SHA-256. Use `license_id: GENERATED-REMOTE-REVIEWED`, the applicable
provider terms URL, a terms effective date, specific `permitted_use`, and a
narrow `review_scope`. This is an operator review record, not a warranty or
legal conclusion. `OWNED-GENERATED-LOCAL` is not valid for remote outputs, and
this remote-generated class is not enabled in the M5 rights gate.

The package command verifies that working-copy receipt, then materialises all
stages and runs their structural and quality checks automatically. Routine stages
record machine checks only; they do not request separate human approvals. The
package does not create a platform draft or publish, and `publish_authorized`
remains false. Generated images are support visuals only, never factual evidence.
Rights evidence and provider-spend authorization retain their own safety checks.

`manual_chatgpt_web`, generic `api`, and `local_svg_html` are retired from new
packages; no silent substitution occurs. Historical receipts retain their
original method values and remain verifiable. Offline contract tests passed. The first live Codex attempt was blocked by the old event parser. A second, separately authorized smoke run passed the repaired adapter and wrote a temporary project-local image and generation receipt. It did not package an approved article or complete rights/quality review.

Official references: [Codex non-interactive mode / JSONL events](https://developers.openai.com/codex/non-interactive-mode), [Codex image-generation tool](https://github.com/openai/codex/blob/main/codex-rs/ext/image-generation/src/tool.rs), [Codex imagegen sample](https://github.com/openai/codex/blob/main/codex-rs/skills/src/assets/samples/imagegen/SKILL.md), [MiniMax CLI](https://platform.minimax.io/docs/m-plan/minimax-cli), [MiniMax image-01 dimensions](https://platform.minimax.cn/docs/api-reference/image-generation-t2i), [OpenAI Terms of Use](https://openai.com/policies/terms-of-use/), [MiniMax Terms of Service](https://platform.minimax.io/protocol/terms-of-service).

## 5.3 Guarded Easel host

Status only; it does not start a server or install dependencies:

```powershell
python scripts\easel_host.py status
python scripts\easel_host.py status --verify-bytes
```

`--verify-bytes` adds the content comparison: it hashes the runtime tree the way
git does and compares it with the pinned commit through `gh`. It needs network
and `gh`; without them the result is `HOST_BYTES_UNVERIFIED`, which is not a
pass. `serve` always performs this comparison, so an offline or modified tree
cannot start.

`HOST_BLOCKED` is the expected result until FastAPI/uvicorn are present and a
host-security review is recorded. `serve` binds `127.0.0.1`, denies every
mutation, and closes websocket scopes before upstream; do **not** run upstream
`easel web` or `web/app.py` directly. See ADR-016.

## 5.4 Coding-agent driver

A coding agent (Claude Code, Codex CLI, OpenCode) can drive the pipeline without
the web host. It asks for a plan, runs one step, and reads the receipt:

```powershell
python scripts\agent_drive.py status
python scripts\agent_drive.py plan --project projects\my-video --json
python scripts\agent_drive.py run --project projects\my-video --step produce-video --execute
```

The plan fixes the argv; the agent picks a step id, never a command. `run`
without `--execute` only prints what it would run. Every execution writes
`receipts/agent-driver-<step>.json` with the return code, bounded output and
`publish_authorized: false`.

`human-review` is listed with `authority: HUMAN_ONLY` and is refused if a driver
tries to run it. There is no publish, credential or install step at all. The
driver does not need FastAPI, uvicorn or a running host; `host-status` is a read
step only so the agent can report the host state.

## 5.5 Brief-driven copy review

After the Brief-to-M5 bridge has written the final script and storyboard, check
or record the human copy review before running M5:

```powershell
python scripts\copy_review.py projects\my-episode --check
python scripts\copy_review.py projects\my-episode --approve `
  --reviewer "Your Name" --opinion "Reviewed the final narration" --confirm
python scripts\copy_review.py projects\my-episode --request-changes `
  --reviewer "Your Name" --opinion "Add the missing source citation" --confirm
```

A decision requires a named reviewer, written rationale and `--confirm`. The
receipt is bound to the current copy fingerprint. Changes to spoken copy,
captions, line-level claim bindings, storyboard or declared assets make an earlier
approval stale. Adding or correcting evidence metadata in `script/claims.json`
alone does not change the reviewed copy. When `script/script.json` is a strict
text-and-claim projection of the reviewed VIDEO derivative, it does not trigger a
second review; any mismatch remains fingerprinted and stale. M5 writes source
links to `receipts/script-citations.json` and never overwrites an existing
`script/master.md`; a mismatch between narration and the creator master blocks.
This command records a decision only: it does not edit copy, run M5 or publish.

## 5.6 Render cards and the GZH article

Both renderers call a pinned Easel skill and write a receipt. Neither is an
approval.

```powershell
python scripts\render_cards.py   projects\my-note
python scripts\render_article.py projects\my-article
```

- `render_cards.py` renders HTML → PNG and runs the card density audit. Exit 4
  means blocked or the audit failed. It needs a Playwright build whose Chromium
  is actually installed; set `CONTENTOPS_CARD_PYTHON` and
  `PLAYWRIGHT_BROWSERS_PATH`.
- `render_article.py` validates the article HTML and wraps a browser preview.
  Exit 4 means blocked or validation failed. It uses `CONTENTOPS_PYTHON` or the
  current interpreter and never scans for one.
- Receipts: `receipts/card-render.json` and `receipts/gzh-article.json`. Both
  keep `production_ready: false` and `publish_authorized: false`.
- Neither command starts a host, calls an agent or touches the network.

## 5.7 Delivery packs (video and graphic)

Packaging is offline. Nothing here publishes: an uploader exit 0 is recorded as
`UPLOADER_EXIT_0`, and only a URL a person actually saw is recorded as a URL.

Before packing, ask what each platform the account declares actually wants. The plan names
the shape, the limits, and which platforms need a second cut; a platform the account never
declared is refused rather than skipped.

```powershell
python scripts\platform_adapt.py plan --project projects\my-video
python scripts\platform_adapt.py plan --project projects\my-video --platform bilibili --json
```

```powershell
python scripts\video_deliver.py plan   --project projects\my-video
python scripts\video_deliver.py pack   --project projects\my-video --thumbnails
python scripts\video_deliver.py status --project projects\my-video
python scripts\video_deliver.py record --project projects\my-video --platform douyin --url <real-url>
python scripts\platform_delivery.py list
python scripts\platform_delivery.py pack --package <path-to-reviewed-graphic-package.json>
python scripts\graphic_deliver.py --package <path-to-reviewed-graphic-package.json> --all --confirm-draft-write
```

- `dispatch` runs an external uploader and requires `--execute` **and** an
  operator grant (`--grant`); without both it prints the argv it would run.
- `graphic_deliver.py` keeps one bridge process alive for the whole batch and
  counts a platform as delivered only when the CLI printed `✓` **and** a URL came
  back. Every call creates a draft.
- The uploaders and the `wechatsync` bridge live in the gitignored `.runtime/`
  tree and are invoked across a process boundary; they are never imported.

## 5.8 GZH workflow status

```powershell
python scripts\gzh_workflow_run.py --workflow <gzh-workspace> --article <article-dir>
python scripts\gzh_runtime.py status
```

`gzh_workflow_run.py` runs the read-only chain (runtime deps → identity → matrix
validation → clean-room hygiene → SDK adapter self-test → the 10 gate checks)
and writes a status receipt. It never advances a gate and reports a blocked gate
with its real error count. `gzh_runtime.py` stays `VERIFY_ONLY`:
`execution_authorized` and `publish_authorized` are always false.

## 6. Run QC

```powershell
python scripts\qc_video.py projects\my-video
```

Checks: file existence, size, ffprobe parse, resolution (1080×1920), aspect ratio (9:16),
duration (30–120s by default; Future Intelligence uses its account-specific 30–300s range), video codec (H.264), audio codec (AAC), audio presence,
script/storyboard existence, real-source ratio (≥70%), source provenance,
voice audibility (volumedetect), subtitle burn detection (multi-frame pixel scan).

Emits: `receipts/qc-report.json` + `qc-report.md`. Status: PASS / WARN / FAIL.

Grade a specific render:

```powershell
python scripts\qc_video.py projects\my-video --video easel
python scripts\qc_video.py projects\my-video --video fallback
```

## 7. Manual publish

V1 does **not** auto-publish, and neither does the delivery layer. Open the
render in `final/` — the V1 engine writes `final/easel.mp4` (plus
`final/fallback.mp4` when the diagnostic engine ran), and the gated production
path (`make_content.py` → `produce_video.py` / `m5_production.py`) writes
`final/<slug>.mp4`. Review it, then either upload through each platform's
creator UI yourself and run
`video_deliver.py record --platform <id> --url <real-url>`, or run
`video_deliver.py dispatch` with an operator grant and record the URL afterwards.
`video_deliver.py pack` accepts the first non-`before` `*.mp4` in `final/`, so it
does not depend on the file name. A tool exit is not a publication; the URL is.

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
python scripts\dev_check.py          # the gate: repo policy, subprocess policy,
                                    # skill references, docs, i18n, smoke tests, whitespace
python scripts\test_basic.py        # script-level smoke suite on its own
python tests\test_m5_evidence.py    # one suite
```

The smoke suite covers: doctor execution, project creation idempotency, QC FAIL
on missing video, blob SHA-1 verification, path exclusion symmetry, foreign
remote rejection, archive provenance acceptance/rejection.

## 10. Skill reference integrity

```powershell
python scripts\check_skill_references.py
python scripts\check_skill_references.py --json
```

Five installed content skills name code that lives on an unmerged branch.
`runtime/content-skill-status.json` records every such path, and this check
fails when the record stops matching this checkout: an unrecorded dangling
reference, a recorded reference that has landed, or a skill marked merged whose
code is missing. On a host without the shared skill store (CI) the reference
scan is skipped and only the record-versus-branch checks run.

A failure here means the record needs updating — and, when a layer has landed,
that the capability may now be declared in `runtime/skill-registry.json`.

## 10. media-use assets (optional)

Requires the pinned skill at `~/.agents/skills/media-use` and Node ≥ 22 (the
official HyperFrames CLI floor). **No network, paid provider, cross-project
reuse or automatic publication is authorized by default.** A trusted runtime
proves what executed; it does not grant a licence for any discovered media.

```powershell
python scripts\media_use_adapter.py status
python scripts\media_use_adapter.py doctor

# Look, then resolve. A project candidate is reused before any provider.
python scripts\media_use_adapter.py candidates --type image --project projects\<slug>
python scripts\media_use_adapter.py resolve --type sfx --intent "soft transition" --project projects\<slug>

# Register files already under <project>\assets, then import one by id.
python scripts\media_use_adapter.py adopt --project projects\<slug>
python scripts\media_use_adapter.py import --type image --record-id img_001 `
  --license "CC-BY-4.0" --attribution "..." --project projects\<slug>

python scripts\media_use_adapter.py verify --project projects\<slug> --path assets\pic.png

# Offline end-to-end sample: fixtures + real screenshots + bundled SFX.
python scripts\media_use_adapter.py demo --project projects\media-use-demo
```

Exit codes: `0` completed, `2` usage, `5` BLOCKED / a human decision is needed,
`1` unexpected failure. Authorization flags (`--allow-network`,
`--allow-paid --budget`, `--allow-cross-project`, `--allowed-provider`) are
explicit and off by default.

`import` refuses an empty `--license`. media-use records carry no licence field,
so the licence is a human decision and is never defaulted.

### Runtime trust (required before any external call)

Two layers are required, and neither replaces the other:

- `runtime/media-use-runtime-baseline.json` — committed and owner-approved
  (2026-10-31, offline-only scope). Approval is a human decision recorded in the
  file; it does not install a runtime.
- a machine lock produced here — host-specific paths, node hash, per-file hashes
  and the approved baseline's digest — pointed at by
  `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK`. Never committed.

A fresh checkout still refuses execution until a machine lock exists. When the
baseline's approval record changes, the baseline file digest changes too, so a
previously generated lock no longer matches: regenerate the lock after any
approval change. Do not edit a lock to make it match a new baseline.

Prepare a host once:

```powershell
# 1. a human approves the committed baseline after reviewing its evidence
python scripts\media_use_runtime.py approve --approved-by "Your Name"

# 2. install the approved release (the only step that needs the network)
python scripts\media_use_runtime.py install --runtime-dir D:\Data\contentops-media-use --node D:\Toolchains\node\node.exe

# 3. hash the tree into a machine lock and verify it against the baseline
python scripts\media_use_runtime.py lock --runtime-dir D:\Data\contentops-media-use --node D:\Toolchains\node\node.exe --out D:\Data\contentops-media-use\runtime-lock.json

# 4. run local, offline operations through the production adapter
python scripts\media_use_runtime.py selfcheck --lock D:\Data\contentops-media-use\runtime-lock.json --project projects\demo
```

```powershell
$env:CONTENTOPS_MEDIA_USE_RUNTIME_LOCK = "D:\Data\contentops-media-use\runtime-lock.json"
python scripts\media_use_adapter.py status
```

`install` copies the committed `runtime/media-use-package-lock.json` and runs
`npm ci --ignore-scripts`; its SHA-256 must equal the baseline's
`dependency_lock_sha256`, so a different dependency tree is refused.

`status` re-hashes the tree on every call and reports one of `TRUSTED_RUNTIME`,
`RUNTIME_MISSING`, `INTEGRITY_MISMATCH`, `VERSION_MISMATCH`,
`BASELINE_MISMATCH` or `DEPENDENCY_UNVERIFIED`. Regenerating a lock never
approves a release. Without a trusted lock, local project imports still work and
every external call is refused.

### Upgrade or roll back HyperFrames

Upgrading is an explicit, reviewed change; the adapter never auto-updates.

1. Update `runtime/media-use-runtime-baseline.json` with the new version,
   published SRI, dependency-lock digest and package-tree digest.
2. A human reviews the evidence and runs
   `python scripts\media_use_runtime.py approve --approved-by "<name>"`.
3. Install into a **new** runtime directory (do not overwrite the trusted one),
   then `lock` and `verify` it.
4. Run `selfcheck` offline, then `tests/test_media_use_adapter.py` and
   `tests/test_media_convergence.py`.
5. Point `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK` at the new lock.

Rollback: keep the previous runtime directory and its lock. Point the environment
variable back and verify it reports `TRUSTED_RUNTIME` against the baseline it was
produced from. Never hand-edit a lock or the per-file hashes.

### Automatic media sourcing in M5

Declare the needs once in `projects/<slug>/project.yaml`; the main entry then
resolves them with no separate media-use invocation:

```yaml
media_use:
  enabled: true
  mode: local-only
  requests:
    - {id: hero, kind: image, intent: "...", rights: {license_id: OWNED-BY-OPERATOR, source_url: OWNED, reviewed_by: me, reviewed_at: "2026-10-31", review_evidence: assets/hero.rights.json, attribution: "owner capture", synthetic: false}}
    - {id: bed, kind: bgm, intent: "...", volume: 0.18, rights: {license_id: OWNED-GENERATED-LOCAL, source_url: GENERATED, reviewed_by: me, reviewed_at: "2026-10-31", review_evidence: assets/bed.rights.json, attribution: "generated tone", synthetic: true}}
    - {id: click, kind: sfx, intent: "...", at: 6.15, volume: 0.55, rights: {license_id: Pixabay-Content-License, source_url: "https://pixabay.com/sound-effects/", reviewed_by: me, reviewed_at: "2026-10-31", review_evidence: assets/click.rights.json, attribution: "Pixabay", synthetic: false}}
```

```powershell
$env:CONTENTOPS_MEDIA_USE_RUNTIME_LOCK = "<verified lock for this host>"
python scripts\m5_production.py projects\m5-media-use
```

`stage_media_use` runs `adopt → resolve → import_record → verify` before the
asset gate. Visual imports are checked against `sources/assets.json`; BGM and SFX
are written to `script/storyboard.json` (`bgm`, `bgm_volume`, `sfx[].at`,
`sfx[].volume`) and mixed under the narration by the pinned Easel assembler.
`at` must fall inside the narration timeline, and a duplicate placement is
refused. No provider is called. A missing or mismatched runtime lock stops the
run with exit code `4` / `BLOCKED`. A project whose `project.yaml` has no
`media_use` block keeps its previous behaviour exactly.

### Isolated Easel demo is not the original runtime

The media-use demo composes through a separate, verified Easel runtime. A
successful demo and QC `WARN` do **not** mean the original `.runtime/easel`
checkout is healthy or restored; that remains a separate integrity question.
