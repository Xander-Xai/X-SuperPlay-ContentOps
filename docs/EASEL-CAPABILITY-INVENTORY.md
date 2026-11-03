# Easel Capability Inventory

> Reference document. It records what the pinned Easel runtime contains, what this
> repository actually calls, and what has actually run here.
>
> It is **not** an execution grant, **not** a second registry, and **not** a claim
> that a capability is approved for production.

Status: reference — 2026-11-02
Pin: v0.2.1 / `3fe2d9904c1619281ef57f81d9ee0b7854998399` (`runtime/easel.lock.json`)
Related: [ADR-006](adr/ADR-006-upstream-upgrade-policy.md), [ADR-015](adr/ADR-015-platform-placeholders-and-content-bundle.md),
[ADR-016](adr/ADR-016-easel-host-adoption.md), [ADR-017](adr/ADR-017-coding-agent-driver.md),
[UPSTREAM-EASEL.md](UPSTREAM-EASEL.md), [SKILL-REGISTRY.md](SKILL-REGISTRY.md)

## Branch and evidence status

This document describes the **pinned runtime plus this branch**, not `main`.

| Fact | Value (verified 2026-11-02) |
|---|---|
| Current branch | `feat/106-easel-host-dual-line` |
| `main` | `357a84e` — does **not** contain ADR-016, `config/registry/platforms.json`, `src/contentops/content_kernel/` or `src/contentops/graphic/` |
| PR #101 | **OPEN**, not merged; carries the platform registry and Bundle code this branch reuses |
| ADR-016 approval | The ADR records `Accepted — Owner authorization, 2026-11-02` (commit `8cc4c07`). That is the approval evidence in this repository; no separate approval artifact is linked here. If one is required, it is an open Owner decision. |

A capability described as present is present in `.runtime/easel/` and on this
branch. It is not a statement about `main`.

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

Exactly **two** upstream scripts are executed. Both are invoked as subprocesses;
neither is imported as a Python module.

| # | Upstream path | Adapter / caller | State | Effects |
|---|---|---|---|---|
| 1 | `skills/openclaw/auto-short-video/scripts/assemble.py` | `scripts/assemble_easel.py` | `INTEGRATED` + `EXECUTABLE_VERIFIED` | local render; no network |
| 2 | `skills/shared/scripts/tts.py` | `scripts/run_v1.py` | `INTEGRATED` + `EXECUTABLE_VERIFIED` (V1 only) | edge-tts; network |

Notes:

- `assemble.py` is run on a storyboard copy with subtitle fields stripped; the
  adapter burns subtitles separately to work around an upstream Windows path bug.
  The upstream file is never modified.
- `tts.py` is used by **V1 only**. M5 narration uses Windows SAPI and does not
  call `tts.py`.
- One upstream ASGI app has a **host adapter present**, not a running host:
  `web/app.py` via `src/contentops/easel/host.py`, behind `GuardMiddleware`,
  loopback only. Its state is `HOST_ADAPTER_PRESENT / HOST_BLOCKED` (FastAPI and
  uvicorn absent). The adapter existing does **not** mean the workbench starts,
  and loading is not execution.

## Inventory

Legend: U = `UPSTREAM_DECLARED`, R = `RUNTIME_PRESENT`, I = `INTEGRATED`,
E = `EXECUTABLE_VERIFIED`, P = `PRODUCTION_ALLOWED`.

| Capability | Category | Upstream path | U | R | I | E | P | Adapter / evidence | Effects | Blocker / next action |
|---|---|---|---|---|---|---|---|---|---|---|
| Video composition | render | `skills/openclaw/auto-short-video/scripts/assemble.py` | ✔ | ✔ | ✔ | ✔ | ✘ | `scripts/assemble_easel.py` | none | keep as the renderer |
| V1 narration | voice | `skills/shared/scripts/tts.py` | ✔ | ✔ | ✔ | ✔ | ✘ | `scripts/run_v1.py` | network (edge-tts) | V1 only; M5 uses SAPI |
| Creator workbench | host | `web/app.py` | ✔ | ✔ | ✘ | ✘ | ✘ | `HOST_ADAPTER_PRESENT / HOST_BLOCKED` — `src/contentops/easel/host.py` | loopback only | deps + host-security review |
| OpenClaw agent | agent | `easel/openclaw_*`, `openclaw/` | ✔ | ✔ | ✘ | ✘ | ✘ | none | network, account | not wired; high-priority evaluation |
| Gateway | agent | `easel/gateway_*` | ✔ | ✔ | ✘ | ✘ | ✘ | none | network, account | not wired |
| Persona / profile | agent | `easel/persona.py`, `profiles/` | ✔ | ✔ | ✘ | ✘ | ✘ | none | none | map to Account DNA before use |
| Skill library | skills | `skills/openclaw/` (114 dirs) | ✔ | ✔ | ✘ | ✘ | ✘ | discovery only via `scripts/skill_route.py` | varies | none registered as executable |
| Shared media scripts | media | `skills/shared/scripts/` (48 files) | ✔ | ✔ | ✘ (47 of 48) | ✘ | ✘ | `tts.py` is the only integrated one | varies | evaluate per production bottleneck |
| CLI (`chat/doctor/gateway/ping/skill`) | cli | `easel/cli.py` | ✔ | ✔ | ✘ | ✘ | ✘ | none (`host.py` presence-checks only) | network, account | never invoked |
| Platform publish skills / scripts | publish | `skill-*-upload`, `skill-*-publisher`, `*_publish.py` | ✔ | ✔ | ✘ | ✘ | ✘ | none | network, credentials | denied by guard and driver |
| Image / video / audio / ASR ops | media | `ai_image.py`, `ai_video.py`, `audio_*.py`, `asr.py` | ✔ | ✔ | ✘ | ✘ | ✘ | none | network, paid | evaluate against existing adapters |
| Voice clone / multi-voice | voice | `voice_clone.py`, `multivoice.py` | ✔ | ✔ | ✘ | ✘ | ✘ | none | network, paid, rights | rights-cleared sample required |
| Subtitle / reframe / background / slideshow / beatsync | media | `subtitle_ops.py`, `reframe.py`, `remove_bg.py`, `slideshow.py`, `beatsync.py` | ✔ | ✔ | ✘ | ✘ | ✘ | none | local | evaluate per bottleneck |
| Doc convert / mindmap / card render | media | `doc_convert.py`, `mindmap.py`, `render_card.py` | ✔ | ✔ | ✘ | ✘ | ✘ | none | local | graphic-line candidates |
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
