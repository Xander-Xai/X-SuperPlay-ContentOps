# Easel Capability Inventory

> Reference document. It records what the pinned Easel runtime contains, what this
> repository actually calls, and what has actually run here.
>
> It is **not** an execution grant, **not** a second registry, and **not** a claim
> that a capability is approved for production.

Status: reference snapshot — 2026-11-02; candidate status audited — 2026-11-13
Pin: v0.2.1 / `3fe2d9904c1619281ef57f81d9ee0b7854998399` (`runtime/easel.lock.json`)
Related: [ADR-006](adr/ADR-006-upstream-upgrade-policy.md), [ADR-015](adr/ADR-015-platform-placeholders-and-content-bundle.md),
[ADR-016](adr/ADR-016-easel-host-adoption.md), [ADR-017](adr/ADR-017-coding-agent-driver.md),
[UPSTREAM-EASEL.md](UPSTREAM-EASEL.md), [SKILL-REGISTRY.md](SKILL-REGISTRY.md)

## Branch and evidence status

The inventory below describes the **pinned v0.2.1 runtime plus the `main`
snapshot recorded below**. The v0.3.0 workbench candidate is tracked separately
in the current-candidate audit that follows; it does not change the production
pin or silently update the historical capability rows.

| Fact | Value (snapshot verified 2026-11-04) |
|---|---|
| Branch in that snapshot | `main` at `218c91d` |
| `main` | contains ADR-016, `config/registry/platforms.json`, `src/contentops/content_kernel/` and `src/contentops/graphic/` |
| PR #101 | **merged** 2026-11-02 (`92c41f4`); it carries the platform registry and Bundle code this document inventories |
| ADR-016 approval | The ADR records `Accepted — Owner authorization, 2026-11-02` (commit `8cc4c07`). That is the approval evidence in this repository; no separate approval artifact is linked here. If one is required, it is an open Owner decision. |

A capability described as present is present in `.runtime/easel/` and on `main`.

## Current v0.3.0 candidate audit (2026-11-13)

The candidate is separate from the pinned production runtime:

| Fact | Evidence / status |
|---|---|
| Candidate | `D:\Projects\_worktrees\easel-v030-rebuild-20261113b` |
| Upstream identity | commit `bb3c8ff0463f36c202454d74171682ba6e470cb1`; archive/tree digest `c26fc96a653c0ff25ef3bc7486eee372c81f44e67d5ff2c30f1786c63c7d4ec8` |
| Source and overlay | On 2026-11-13 the candidate verified 1071/1071 baseline blobs and 14 declared tuning/profile files, with no missing, changed, extra or unsafe files. Both account profiles were regenerated from the then-current DNA. Code has since changed; this historical result is not a fresh verification. The preceding `easel-v030-rebuild-20261113` candidate remains separate: it has one task-created extra file whose deletion was blocked by automatic review |
| Frontend | On 2026-11-13 `npm ci` and `npm run build` succeeded with Node 24.16.0/npm 11.13.0; the five dist files and destination were verified and recorded in `runtime/easel-workbench-frontend-build.json`. Current bytes were not rechecked in the subsequent implementation work. The install reported five audit findings (one moderate, three high, one critical); they have not been remediated |
| Offline task adapter | A 2026-11-13 version passed 18 tests and a localhost HTTP task returned its draft and receipt. The adapter has since changed and the current version has not been rerun. Its executor is a deterministic scaffold, not Easel Agent or model execution |
| TTS and shared card scripts | The candidate tree contains `skills/shared/scripts/tts.py` and `render_card.py`. Their presence is discovery only: the existing V1 TTS call selects the production runtime, and the v0.3 browser-based card path remains blocked pending isolation. No v0.3 TTS or card execution is established by this inventory |
| Workbench host | Ambient Python remains `HOST_BLOCKED` on `sse_starlette`; no cleanly isolated upstream Easel host has been served. A separate candidate-local environment served `--offline-tasks-only` on loopback and was stopped after profile selection, draft creation and receipt readback over HTTP. This mode imports no Easel and makes no GitHub call. Browser E2E remains unverified |
| Production runtime | Still v0.2.1 / `3fe2d9904c1619281ef57f81d9ee0b7854998399`; `runtime/easel.lock.json` is unchanged |

These historical checks document one source and frontend rebuild plus an
offline adapter execution. They do not establish that subsequent changes pass,
a second clean-environment rebuild, real Agent isolation, gateway execution,
browser acceptance, production migration, or human/Founder approval.

## Why this file exists

ADR-016 adopts the full Easel system as the production base, but the **verified**
surface is still narrow. Without a written inventory, "Easel is the base" gets
misread as "Easel's capabilities are already integrated".

This file separates five states that are routinely conflated:

| State | Meaning | Evidence required |
|---|---|---|
| `UPSTREAM_DECLARED` | The pinned tree names the capability (SKILL.md, script or route). | the path exists in `.runtime/easel/` |
| `RUNTIME_PRESENT` | The file is present and byte-verified against the pin. | `scripts/verify_easel_runtime.py` |
| `INTEGRATED` | This repository has an adapter or CLI that calls it. | a repo path in this document |
| `EXECUTABLE_VERIFIED` | It was actually run here and produced a receipt or artifact. | a receipt or artifact |
| `PRODUCTION_ALLOWED` | A human approved it for production use. | a written approval |

A capability can be `UPSTREAM_DECLARED` + `RUNTIME_PRESENT` and still be
`INTEGRATED: no`. That is the normal case in this repository.

## What is actually called

**Six** upstream scripts are executed. All are invoked as subprocesses; none is
imported as a Python module. (The earlier count of two was written before the
card and article lines landed in PRs #149 and #152; it is corrected here.)

| # | Upstream path | Adapter / caller | State | Effects |
|---|---|---|---|---|
| 1 | `skills/openclaw/auto-short-video/scripts/assemble.py` | `scripts/assemble_easel.py` (also reached from `scripts/m5_production.py`) | `INTEGRATED` + `EXECUTABLE_VERIFIED` | local render; no network |
| 2 | `skills/shared/scripts/tts.py` | `scripts/run_v1.py` | `INTEGRATED` + `EXECUTABLE_VERIFIED` (V1 only) | edge-tts; network |
| 3 | `skills/shared/scripts/render_card.py` | `scripts/render_cards.py`, `scripts/package_code_animation_sample.py` | `INTEGRATED` + `EXECUTABLE_VERIFIED` | local HTML→PNG; no network |
| 4 | `skills/openclaw/card-design/scripts/card_audit.py` | `scripts/render_cards.py`, `scripts/package_code_animation_sample.py` | `INTEGRATED` + `EXECUTABLE_VERIFIED` | local density gate; no network |
| 5 | `skills/openclaw/gzh-design/scripts/validate_gzh_html.py` | `scripts/render_article.py`, `scripts/production_gates.py` | `INTEGRATED` + `EXECUTABLE_VERIFIED` (GZH) | local validation; no network |
| 6 | `skills/openclaw/gzh-design/scripts/wrap_preview.py` | `scripts/render_article.py` | `INTEGRATED` + `EXECUTABLE_VERIFIED` (GZH) | local HTML wrap; no network |

Notes:

- `assemble.py` is run on a storyboard copy with subtitle fields stripped; the
  adapter burns subtitles separately to work around an upstream Windows path bug.
  The upstream file is never modified.
- `tts.py` is used by **V1 only**. M5 narration uses Windows SAPI and does not
  call `tts.py`.
- The card and article scripts (3–6) are pure-local: HTML in, PNG or validated
  HTML out. They carry no network, credential or provider effect.
- One upstream ASGI app (`web/app.py`) is served through
  `src/contentops/easel/host.py` behind `GuardMiddleware`, loopback only. The
  production host requires every module imported by `web/app.py`; a v0.3.0
  workbench additionally requires a verified frontend build manifest. Missing
  source or artifact evidence keeps it `HOST_BLOCKED`. `HOST_READY` is **not**
  publication authority and does **not** mean the OpenClaw agent is isolated.

## Inventory

Legend: U = `UPSTREAM_DECLARED`, R = `RUNTIME_PRESENT`, I = `INTEGRATED`,
E = `EXECUTABLE_VERIFIED`, P = `PRODUCTION_ALLOWED`.

| Capability | Category | Upstream path | U | R | I | E | P | Adapter / evidence | Effects | Blocker / next action |
|---|---|---|---|---|---|---|---|---|---|---|
| Video composition | render | `skills/openclaw/auto-short-video/scripts/assemble.py` | ✔ | ✔ | ✔ | ✔ | ✘ | `scripts/assemble_easel.py` | none | keep as the renderer |
| V1 narration | voice | `skills/shared/scripts/tts.py` | ✔ | ✔ | ✔ | ✔ | ✘ | `scripts/run_v1.py` | network (edge-tts) | V1 only; M5 uses SAPI |
| Card render + density gate | media | `skills/shared/scripts/render_card.py`, `skills/openclaw/card-design/scripts/card_audit.py` | ✔ | ✔ | ✔ | ✔ | ✘ | `scripts/render_cards.py` (PR #149) | none | keep as the card line |
| GZH article validate + wrap | media | `skills/openclaw/gzh-design/scripts/validate_gzh_html.py`, `wrap_preview.py` | ✔ | ✔ | ✔ | ✔ | ✘ | `scripts/render_article.py` (PR #152) | none | keep as the article line |
| Creator workbench | host | `web/app.py` | ✔ | ✔ | ✔ (guard) | ✘ | ✘ | `src/contentops/easel/host.py`; v0.3.0 candidate has a verified frontend manifest and offline task adapter | loopback only | earlier `--workbench` API run used a process without proven credential isolation; exact-allowlist `--workbench` attempt failed byte verification before bind. Exact-allowlist offline-only profile/draft/receipt flow passed and was stopped; browser E2E and real Agent remain gated |
| OpenClaw agent | agent | `easel/openclaw_*`, `openclaw/` | ✔ | ✔ | ✘ | ✘ | ✘ | CLI package metadata: v2026.10.5; no ContentOps execution adapter or active gateway verified | network, account | execution not wired; isolation and one-task authorization remain unverified |
| Gateway | agent | `easel/gateway_*` | ✔ | ✔ | ✘ | ✘ | ✘ | none | network, account | not wired |
| Persona / profile | agent | `easel/persona.py`, `profiles/` | ✔ | ✔ | ✘ | ✘ | ✘ | projection helper: `scripts/easel_profile.py`; candidate offline profile API | none | validated profiles are exposed by the offline API; browser verification pending |
| Skill library | skills | `skills/openclaw/` (114 dirs) | ✔ | ✔ | ✘ | ✘ | ✘ | discovery only via `scripts/skill_route.py` | varies | none registered as executable |
| Shared media scripts | media | `skills/shared/scripts/` (48 files) | ✔ | ✔ | ✘ (46 of 48) | ✘ | ✘ | `tts.py` and `render_card.py` are the integrated ones | varies | evaluate per production bottleneck |
| CLI (`chat/doctor/gateway/ping/skill`) | cli | `easel/cli.py` | ✔ | ✔ | ✘ | ✘ | ✘ | none (`host.py` presence-checks only) | network, account | never invoked |
| Platform publish skills / scripts | publish | `skill-*-upload`, `skill-*-publisher`, `*_publish.py` | ✔ | ✔ | ✘ | ✘ | ✘ | none | network, credentials | denied by guard and driver |
| Image / video / audio / ASR ops | media | `ai_image.py`, `ai_video.py`, `audio_*.py`, `asr.py` | ✔ | ✔ | ✘ | ✘ | ✘ | none | network, paid | evaluate against existing adapters |
| Voice clone / multi-voice | voice | `voice_clone.py`, `multivoice.py` | ✔ | ✔ | ✘ | ✘ | ✘ | none | network, paid, rights | rights-cleared sample required |
| Subtitle / reframe / background / slideshow / beatsync | media | `subtitle_ops.py`, `reframe.py`, `remove_bg.py`, `slideshow.py`, `beatsync.py` | ✔ | ✔ | ✘ | ✘ | ✘ | none | local | evaluate per bottleneck |
| Doc convert / mindmap / card render | media | `doc_convert.py`, `mindmap.py`, `render_card.py` | ✔ | ✔ | ✔ (render_card) | ✔ (render_card) | ✘ | `render_card.py` via `scripts/render_cards.py`; doc_convert/mindmap none | local | render_card integrated; the other two are graphic-line candidates |
| Install / upgrade tooling | ops | `install_tool.py` | ✔ | ✔ | ✘ | ✘ | ✘ | none | installs deps | `install`/`upgrade` are forbidden tokens |

Exact counts are facts about the pinned tree on 2026-11-02: **114** directories
under `skills/openclaw/`, **48** `*.py` files under `skills/shared/scripts/`.
Separately, the runtime verification covers **982 blobs** — files checked against
the pin, not 982 capabilities. Blob count, skill-directory count and shared-script
count are three different measurements and must not be added together.

## Deliberately not integrated

No capability is adopted merely because it exists in the pinned tree. Each
adoption is a separate evaluation with its own acceptance and receipt
(ADR-016 D6). In particular:

- The 114 OpenClaw skills are **not** registered as executable capabilities.
  `runtime/skill-registry.json` declares only `media-use`, and that adapter is
  the HyperFrames `media-use` adapter, not an Easel skill.
- Discovery (`scripts/skill_route.py`) reads SKILL.md front matter and never
  executes anything; every resolution carries `execution_authorized: false`.
- Publishing, login, credential, environment-install, settings-write and delete
  routes are denied before upstream by `src/contentops/easel/guard.py`, and the
  coding-agent driver forbids `publish/login/credential/token/install/upgrade`
  tokens in any step (`src/contentops/easel/driver.py`).

## What this document does not do

- It does not grant execution authority. Authority stays with the adapters,
  runtime locks and grant gate described in [SKILL-REGISTRY.md](SKILL-REGISTRY.md).
- It does not replace `config/registry/platforms.json`. The platform registry
  remains the only machine-readable platform source.
- It does not approve any capability for production. None of the capabilities
  listed here has production authorization (`P = ✘`).

## Verification

Reproduce the facts above on a host with the pinned runtime:

```bash
python scripts/verify_easel_runtime.py --resolve-tag
python scripts/easel_host.py status
python scripts/skill_route.py --doctor
```

Recorded on 2026-11-02: 982/982 blobs verified; host `HOST_ADAPTER_PRESENT /
HOST_BLOCKED`; 114 OpenClaw skill directories; 48 shared scripts. The 982 blob
count is a file-integrity result, not a capability count.

## Next actions (design only)

1. **P1 — capability bridge.** Choose one read-only or purely local skill and run
   discovery → authorization → execution → receipt end to end. Do not run the
   library.
2. **P2 — media reuse evaluation.** Score image, ASR, subtitle, audio, background
   removal and reframe against the implementations this repository already has.
   Reuse only where it replaces a real bottleneck.
3. **P3 — guarded workbench / agent.** Resolve the dependency and security review
   first; then design approved agent tool calls. Publishing and login stay out.
