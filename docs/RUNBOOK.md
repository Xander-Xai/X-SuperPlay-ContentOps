# Runbook

[English](RUNBOOK.md) | [简体中文](RUNBOOK.zh-CN.md)

> Real executable commands. Derived from actual script behavior, not assumptions.
> Last updated: 2026-10-31

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

`--skip-compose` stops after the storyboard (no ffmpeg, no Easel) and is what CI
and a fast edit loop use.

Narration is the offline Windows SAPI voice; no network TTS is called. The run
always ends at `PENDING_FOUNDER_REVIEW` with `production_ready: false` — a green
QC is not publishing permission (ADR-005).


### Automatic media-use materials in M5 (offline only)

When the approved PR #64 adapter is installed and a machine runtime lock is
configured, the normal M5 command automatically invokes media-use between the
sources and assets stages. Configure per-project material needs in project.yaml:

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
to support_visual in script/script.json as the asset_id. Then run the normal
command:

~~~powershell
python scripts\m5_production.py projects\my-video
~~~

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

Integration PR: stacked on M5 PR #68; actual external execution also requires
PR #64. Hosted tests use synthetic fixtures and make no provider calls.

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

## 5.2 Graphic manual package

The graphic line produces a reviewable package, not a platform draft:

```powershell
python scripts\graphic_package.py `
  --project projects\my-article `
  --handoff projects\my-article\receipts\bundle-handoff-graphic_text.json `
  --input projects\my-article\graphic-input.json
```

It writes `receipts/graphic-package.json` and `receipts/graphic-preview.md`
with `status: AWAITING_MANUAL_REVIEW` and `publish_authorized: false`. Every
image needs ALT text and a reviewed rights block; a missing right, a path
escape or an undecodable image blocks the package.

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
