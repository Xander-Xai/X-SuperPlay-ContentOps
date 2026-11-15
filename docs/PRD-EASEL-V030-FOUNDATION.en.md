# PRD — Easel v0.3.0 as the Foundation (Workbench)

[English](PRD-EASEL-V030-FOUNDATION.en.md) | [简体中文](PRD-EASEL-V030-FOUNDATION.md)

> Last verified: 2026-11-15 on `main`. Status: **Proposed** — awaiting Founder approval.
> This is a **requirements document**, not a completion report. "Target / planned / not
> executed / pending authorisation" always describe something that has not happened.
> No paragraph here is evidence that the migration was performed.

## 0. Document metadata

| Item | Value |
|---|---|
| Role | The development requirements for "adopt a mature foundation, tune it into our own workbench" |
| Relationship to `PRD.md` | `PRD.md` describes what the runtime is; this document describes **how the foundation moves from v0.2.1 to v0.3.0 and how the workbench becomes the interaction surface**. It does not replace `PRD.md`; it expands §6 (non-goals) and §14 (Easel integration) into executable requirements |
| Current pin | v0.2.1 / `3fe2d9904c1619281ef57f81d9ee0b7854998399` (`runtime/easel.lock.json`, unchanged) |
| Target pin | v0.3.0 / `bb3c8ff0463f36c202454d74171682ba6e470cb1` plus a content digest (see §9) |
| Actions taken by this document | Documentation only: this file, its Chinese primary, and the documentation-gate wiring. **No code change, no pin change, no dependency install, no service started** |
| Approver | Founder (Xander-Xai) |

---

## 1. Background and decision basis

### 1.1 One sentence

For months the project has used Easel as a video composer while its skill library, account
profiles, workbench, agent and publishing channels stayed outside. This PRD turns "replace the
engine first, then replace the cockpit" into acceptance-tested requirements, so the foundation
becomes a real workbench without breaking today's rendering.

### 1.2 Terminology correction (must be in writing, or everything downstream is wrong)

| Informal wording | Fact | Evidence |
|---|---|---|
| "Adopt Easel 3.0" | Upstream has **no 2.x and no 3.0**. The sequence is v0.1.0 → v0.1.1 → v0.2.0 → v0.2.1 → **v0.3.0 (2026-10-12)** | Five tags / five releases upstream; `pyproject.toml` version is 0.3.0; the CHANGELOG top section is 0.3.0 |
| "Clean up 2.0 once 3.0 lands" | "2.0" means the **v0.2.1** pin in this repository, running in `.runtime/easel` | `runtime/easel.lock.json` |
| "The project never adopted the foundation" | It did, narrowly: six upstream scripts are called as subprocesses, and **only one of them actually runs in production** | §2 |

This document uses **v0.2.1 / v0.3.0** only, never "2.0 / 3.0".

### 1.3 Existing decisions (this PRD does not re-decide them)

| Decision | Content | Relation |
|---|---|---|
| ADR-016 D1 (2026-11-02, Owner) | Easel is the production base; ContentOps is the governance extension | This PRD is its execution-level expansion |
| Owner decision, 2026-11-12 | "Run a mature Easel as the base and tune it, instead of continuing to tune the v0.2.1 library" | The direct authority for this PRD |
| ADR-022 D1 (2026-11-13) | v0.3.0 is a workbench candidate only; the production pin does not move | Preserved for M2 |
| ADR-022 D4 | No real Agent execution without verified OS-level isolation | Hard red line here; not relaxed before M3 |
| ADR-012 D3 | v0.3.0 not adopted; adoption runs the full gate and pins by **content digest** | Source of the §9 pin policy |
| ADR-014 | Delivery validation hold | Its conclusion is kept; §11 converts it into tiered authorisation |
| ADR-015 D2–D8 | The platform registry is the only machine-readable source | §11 adds no second registry |

### 1.4 Boundary with `docs/PRD.md`

| `PRD.md` item | Treatment here |
|---|---|
| §6 "Auto-publishing to any platform" is a non-goal | **REOPENED** (authorised, not executed), bounded by the four tiers in §11 |
| §6 "n8n / OpenClaw total orchestration" | **STILL CLOSED**. Skills and an agent are not a transfer of orchestration |
| §6 "Database / complex FastAPI" | **STILL CLOSED**. The workbench ships its own FastAPI host; that is an upstream artifact, not a new service of ours |
| §14 "Executed surface today: two files" | **Not rewritten here.** It is true until M1 lands; only an M1 receipt allows editing it and bumping the date |
| §14 "adopting upstream skills/agent/workbench requires ADR-002 to be superseded" | This PRD only **proposes** new ADRs (§17); it signs nothing |

---

## 2. Current state and gaps

### 2.1 Upstream scripts actually wired (six, all subprocess, never imported)

| # | Upstream path (v0.2.1) | Caller | State | Effects |
|---|---|---|---|---|
| 1 | `skills/openclaw/auto-short-video/scripts/assemble.py` | `scripts/assemble_easel.py` ← `scripts/m5_production.py` | `INTEGRATED` + **real artifact** | local render, no network |
| 2 | `skills/shared/scripts/tts.py` | `scripts/run_v1.py` | `INTEGRATED`, V1 only, CLI closed | edge-tts, network |
| 3 | `skills/shared/scripts/render_card.py` | `scripts/render_cards.py` | `INTEGRATED`, **no real artifact** | local HTML→PNG |
| 4 | `skills/openclaw/card-design/scripts/card_audit.py` | `scripts/render_cards.py` | as above | local density gate |
| 5 | `skills/openclaw/gzh-design/scripts/validate_gzh_html.py` | `scripts/render_article.py` | `INTEGRATED`, **no real artifact** | local validation |
| 6 | `skills/openclaw/gzh-design/scripts/wrap_preview.py` | `scripts/render_article.py` | as above | local wrap |

### 2.2 Foundation capability that is not wired at all

| Area | Upstream size | State here |
|---|---|---|
| Skill library | 114 skill directories | Discovery only (`scripts/skill_route.py` reads front matter and returns `execution_authorized: false`) |
| OpenClaw Agent | `easel/openclaw_*`, `agents/` | Not wired; Windows isolation unverified |
| Gateway | `easel/gateway_*` | Not wired |
| CLI | `easel/cli.py` (chat/doctor/gateway/ping/skill) | Never invoked |
| Workbench host | `web/app.py` | Only behind the loopback read-only guard in `src/contentops/easel/host.py`; currently `HOST_BLOCKED` |
| Publishing channels | `skill-*-upload`, `skill-*-publisher` | Denied by both guard and driver |

### 2.3 Four copies on disk (stated once, clearly)

| Path | Size | Identity | Accepted by resolver |
|---|---|---|---|
| `.runtime/easel` | 996 files | **Production runtime**, v0.2.1 pin `3fe2d99`, clean tree | Yes |
| `D:\Projects\_worktrees\easel-v030-rebuild-20261113b` | — | **v0.3.0 candidate**, 1073 blobs + tree digest + 14 overlay files verified | Only via `resolve_easel_workbench()` |
| `D:\Projects\Easel-Workbench` | — | Earlier snapshot, `profile_status: STALE` | No |
| `Easel/` (in repo) | 2.2 GB | **gitignored legacy shallow clone**, HEAD `4b9c03c` (24 commits after v0.2.1), two uncommitted modifications | No (actively rejected) |

### 2.4 Real artifact evidence (the only complete chain)

| Item | Value |
|---|---|
| Project | `projects/m5-easel-pin` |
| Receipt | `receipts/compose.json`: `status=OK`, `subtitles_burned=true`, `upstream=easel@v0.2.1:skills/openclaw/auto-short-video/scripts/assemble.py` |
| Output | `final/m5-easel-pin.mp4`: h264 1080×1920 + aac, `duration=45.142`, 1,061,877 B |
| QC | `receipts/qc-report-m5-easel-pin.json` PASS (19 checks) |
| Known noise | `qc-report-final.json` in the same directory reads FAIL because of a filename drift; that is not a render failure |

### 2.5 Gaps this PRD closes

| Gap | Now | Target |
|---|---|---|
| Engine version | v0.2.1 (2026-09-24) | v0.3.0 (2026-10-12), 158 commits / 300 files apart |
| Skill layout | `skills/openclaw/` | `skills/builtin/` (breaking upstream rename) |
| Interaction surface | CLI plus a dozen scripts | One workbench page |
| Platform publishing | All nine platforms `PLANNED` (except `x`: `INTEGRATED/MANUAL_ONLY`), zero real publications | Four tiers, full automation as the end state |
| Pin single-source | **Five code literals + three JSON records** | One registry plus derivation |
| Card/article lines | Code without artifacts | Real artifacts and receipts |

---

## 3. User and jobs to be done

| User | JTBD |
|---|---|
| Founder (sole operator) | Move the foundation to v0.3.0 **without interrupting rendering**, and make the capability surface (skills, profiles, workbench) actually usable |
| Founder | Open one page to see drafts, receipts and gate verdicts instead of switching between a dozen scripts |
| Founder | End state: topic to publication without manual shuttling, every step with a receipt |
| Governance (code / CI) | Any "integrated" claim is provable by one command or one receipt |

Definition of success:
1. One command switches engines, another switches back, both leave receipts;
2. The same storyboard renders under both trees, and QC passes in both;
3. The workbench reads drafts, receipts and gate verdicts — but cannot read credentials or publish;
4. Each platform's publishing autonomy is recorded in the registry and traceable to a receipt.

---

## 4. Target architecture

### 4.1 Two layers

```text
┌──────────────── Foundation (Easel v0.3.0, read-only baseline + recorded overlay) ───────────────┐
│  Render engines (assemble / cards / article validation)  │  Skill library, 114 dirs            │
│  Account profiles (2 accounts, generated from DNA)       │  Workbench host web/app.py (React)  │
│  Agent harnesses (OpenClaw / Codex / ACP) — isolation unverified, execution denied              │
│  Publishing channels (skill-*-upload / *-publisher) — denied by default, opened per §11 tier    │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
                                     ▲ calls (subprocess / guard proxy)
                                     │ only writable surface: outputs/, generated profiles, recorded overlay
┌──────────────── Governance extension (ContentOps, owned by this repository) ────────────────────┐
│  Evidence layer SourceArtifact / ClaimLedger  │  9 gates (7 VIDEO + 5 GRAPHIC_TEXT)             │
│  M5 production chain, 20+ stages              │  QC (19 checks) / ASR narration backcheck       │
│  Receipt system (receipts/)                   │  Platform specs / packaging / delivery (9 rows) │
│  Asset rights gate / MiniMax provider layer   │  guard / driver / offline task API              │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Three invariants

1. **The foundation's bytes are never modified.** Tuning may only enter files recorded in
   `runtime/easel-workbench-overlay.json` (currently 14: two skill overrides and twelve profile
   files). An unrecorded file that differs from upstream is a failed verification, not tuning.
2. **Governance can veto the foundation.** Insufficient evidence, unresolved rights, QC FAIL or a
   failed gate means nothing the foundation renders may be labelled `production_ready`.
3. **The foundation never publishes by itself.** Publishing is a governance authorisation recorded
   in the platform registry's `autonomy` field.

### 4.3 Who calls whom

| Direction | Form | Note |
|---|---|---|
| Governance → foundation | Subprocess (`hidden_run`) | Keeps the ADAPTER pattern; no upstream source change |
| Governance → workbench host | Guard proxy in `src/contentops/easel/host.py` | Loopback, read-only allowlist, unknown routes fail closed |
| Foundation → governance | **Not allowed.** The foundation may not call back to change state | A renderer cannot issue its own permit |

---

## 5. Scope

| Milestone | Covers | Excludes |
|---|---|---|
| M0 | Pin single-source, dehardcoding paths, one documentation truth | Any runtime behaviour change |
| M1 | Production engine moves to v0.3.0; two roots coexist; receipts carry `engine_id` | Workbench, agent, publishing |
| M2 | Workbench becomes the interaction surface (read-only plus offline task API) | Real Agent execution, publishing |
| M3 | The nine gates attach to the foundation as skill declarations | Real Agent execution (still denied) |
| M4 | Four publishing tiers (a draft-auto → b single-platform grey → c all platforms) | Releasing Douyin (until a separate FULL_AUTO authorisation) |

---

## 6. Non-goals (reconciled with `PRD.md` §6)

| `PRD.md` §6 text | Verdict | Basis |
|---|---|---|
| Auto-publishing to any platform | **REOPENED (authorised, not executed)**, bounded by §11 tiers and per-platform authorisation | this PRD, decision D-C |
| Comment scraping / ROI agent | **STILL CLOSED** | Unrelated to the foundation move |
| Digital human / AI short drama | **STILL CLOSED** | Same |
| Metrics scraping / winner learning | **STILL CLOSED** (`bilibili_metrics` / `wechat_metrics` stay read-only) | Same |
| n8n / OpenClaw total orchestration | **STILL CLOSED**. Agent capability is not a transfer of orchestration | ADR-002, ADR-015 D2–D8 |
| Database / complex FastAPI | **STILL CLOSED**. The upstream FastAPI host is an upstream artifact; we add no service and no database | ADR-016 D2 |

Non-goals introduced here:

- No upstream source modification (no fork, no patch);
- No tag-as-identity (upstream force-replaced a tag once);
- No real Agent execution before M3;
- The `Easel/` legacy clone never enters the production path;
- No loosening a check, and no date bump, to make a gate green.

---

## 7. Functional requirements

Identifier scheme: `FR-<domain>-<nn>`, domains PIN / ENG / GOV / WB / PUB / DOC. Risk levels
follow `docs/TEST-PLAN.md` L0–L3.

### 7.1 PIN — engine identity and single-source

| ID | Requirement | Acceptance signal | Risk | Milestone |
|---|---|---|---|---|
| FR-PIN-01 | Add `runtime/easel-pins.json` as the only pin registry: `active`, `engines{v0.2.1,v0.3.0}`, each with `tag/commit/tree_sha256/layout/root/license/agpl_vendored/role` | File exists and validates against its schema | L3 | M0 |
| FR-PIN-02 | Remove four code literals: `scripts/resolve_easel.py:48`, `scripts/verify_easel_runtime.py:62`, `src/contentops/graphic/articles.py:483`, `src/contentops/easel/agent_workspace.py:24` | `grep -rn "3fe2d99\|bb3c8ff" scripts src` hits only registry reads and test fixtures | L3 | M0 |
| FR-PIN-03 | `runtime/easel.lock.json` becomes a **derived** value (top-level `tag`/`commit` kept, schema unchanged) with a `derived_from` field | `check_docs.py` lock consistency passes | L3 | M0 |
| FR-PIN-04 | Engine identity is `commit` + `tree_sha256`; the tag is a comment and never an identity on its own | `verify_easel_runtime.py --json` reports `VERIFIED` with `tree_sha256` | L3 | M1 |
| FR-PIN-05 | Two roots coexist: `.runtime/easel` (v0.2.1) untouched, new `.runtime/easel-v030`; `--engine` selects explicitly | Both `--engine v0.2.1` and `--engine v0.3.0` report `status=OK` | L3 | M1 |
| FR-PIN-06 | Every render receipt records `easel: {engine_id, tag, commit, tree_sha256, layout, skill_rel}` | `projects/*/receipts/compose.json` carries an `easel.engine` block | L2 | M1 |

### 7.2 ENG — production engine

| ID | Requirement | Acceptance signal | Risk | Milestone |
|---|---|---|---|---|
| FR-ENG-01 | Composition uses v0.3.0 `assemble.py`; subtitles are still generated (SRT→ASS) and burned by us, working around the upstream Windows path bug | `final.mp4` exists + QC PASS + sha256 receipt | L3 | M1 |
| FR-ENG-02 | Skill resolution is driven by the engine's `layout` field instead of a "try openclaw first" order | `src/contentops/easel/skill_paths.py` takes a `layout`; tests cover both layouts | L2 | M1 |
| FR-ENG-03 | The rename blast radius is closed in one change: skill bindings in `config/accounts/*.json`, the eight `easel_capability.evidence` paths in `config/registry/platforms.json`, plus `scripts/m5_production.py` and `scripts/package_code_animation_sample.py` | `grep -rn "skills/openclaw" config scripts src` hits only an explicit v0.2.1-layout branch | L2 | M1 |
| FR-ENG-04 | TTS is **not** migrated: M5 narration stays on Windows SAPI / MiniMax, and the V1 `tts.py` path stays closed | `docs/EASEL-CAPABILITY-INVENTORY.md` states "not migrated" | L0 | M1 |

### 7.3 GOV — governance extension

| ID | Requirement | Acceptance signal | Risk | Milestone |
|---|---|---|---|---|
| FR-GOV-01 | The nine gates attach as skill declarations, not as a second engine | `scripts/skill_route.py` resolves the ContentOps extension entry | L2 | M3 |
| FR-GOV-02 | Receipt schemas are versioned and additive (fields may be added, never removed) | New fields do not break `check_receipt_secrets.py` | L1 | M3 |
| FR-GOV-03 | Under the v0.3.0 path, the asset rights gate and ASR backcheck behave identically (`SKIPPED` still blocks on account-bound projects) | `tests/test_m5_asr_gate.py`, `tests/test_asr_siliconflow.py` and the rights-gate tests pass | L2 | M1 |

### 7.4 WB — cockpit

| ID | Requirement | Acceptance signal | Risk | Milestone |
|---|---|---|---|---|
| FR-WB-01 | Host criteria are not relaxed: `HOST_READY` requires upstream byte verification + overlay verification + frontend build receipt | `python scripts/easel_host.py status --json` | L2 | M2 |
| FR-WB-02 | Offline task API semantics unchanged (three read routes plus one offline write) | One POST/GET read-back of three artifacts with `production_ready:false` and `publish_authorized:false` | L2 | M2 |
| FR-WB-03 | Real Agent execution stays denied until OS-level isolation evidence exists (dedicated workspace, bounded writes, default-deny network, named tool set) | `host_status` blockers include the isolation item | L3 | M2/M3 |
| FR-WB-04 | Frontend build policy gains a toolchain range (today only an exact observation `v24.16.0`, with no upper bound; upstream states 25.x is incompatible) | `runtime/easel-workbench-build-policy.json` carries a range; a mismatch means `HOST_BLOCKED` | L2 | M2 |

### 7.5 PUB — publishing tiers

| ID | Requirement | Acceptance signal | Risk | Milestone |
|---|---|---|---|---|
| FR-PUB-01 | The platform registry gains an orthogonal `autonomy{level,granted_by,granted_at,evidence[],rollback_to}` dimension (schema v2) | `scripts/check_platform_status_sync.py --strict` reports zero mismatches | L3 | M4 |
| FR-PUB-02 | Four tiers `MANUAL → DRAFT_AUTO → GRAY_AUTO → FULL_AUTO`; `delivery_gate.authorize_delivery` returns the matching outcome | Decision receipt carries the tier and reasons | L3 | M4 |
| FR-PUB-03 | Douyin's `UNCONDITIONALLY_REFUSED` survives until that platform receives a separate `FULL_AUTO` authorisation; none of the six refusal rules is deleted | Regression: `authorize_delivery("douyin").outcome == "REFUSED"` | L3 | M4 |

### 7.6 DOC — documentation and gates

| ID | Requirement | Acceptance signal | Risk | Milestone |
|---|---|---|---|---|
| FR-DOC-01 | This document and its English mirror exist as a pair with bidirectional language-switch links | `python scripts/check_i18n.py` exits 0 | L0 | M0 (this PR) |
| FR-DOC-02 | The new document is classified in `config/docs/doc-freshness.json` with a verification date | `python scripts/check_doc_freshness.py` reports 0 stale / 0 error | L0 | M0 (this PR) |
| FR-DOC-03 | `docs/PRD.md` §14 may only be rewritten after M1 lands, with a receipt attached, and its date bumped | The editing PR includes the M1 receipt | L0 | M1 |

---

## 8. Non-functional requirements

| ID | Requirement | How it is decided |
|---|---|---|
| NFR-1 | **No rendering interruption**: at any moment during the switch, at least one tree's `resolve_easel.py` returns `OK` | Run it before and after the switch; both must be OK |
| NFR-2 | Rollback ≤ 1 command, ≤ 5 minutes | The rollback script exists and has a dry-run receipt |
| NFR-3 | Engine reproducibility: same commit + same tree digest → same verdict | `verify_easel_runtime.py --json` `tree_sha256` is stable |
| NFR-4 | Fail closed: a missing or corrupt registry yields `BLOCKED`, never a built-in default commit | A unit test covers "registry missing → BLOCKED" |
| NFR-5 | Disk budget: controlled copies ≤ 4 GB | `du -sh` recorded in the switch receipt |
| NFR-6 | Publishing honesty: a tier that no platform holds may not appear in the registry or the docs | `check_platform_status_sync.py --strict` |
| NFR-7 | Receipt honesty: any degradation or skipped step is recorded, and `production_ready` stays false | Receipt schema check plus human review |
| NFR-8 | Windows remains first-class: path, UTF-8 and hidden-subprocess behaviour unchanged | `tests/test_windows_paths.py` and friends pass |

---

## 9. Version and pin policy

### 9.1 Target engine identity

| Field | Value |
|---|---|
| Repo | `https://github.com/ZJU-REAL/Easel.git` |
| Tag (comment only) | `v0.3.0` (2026-10-12) |
| Commit | `bb3c8ff0463f36c202454d74171682ba6e470cb1` |
| Tree digest | `c26fc96a653c0ff25ef3bc7486eee372c81f44e67d5ff2c30f1786c63c7d4ec8` (method: sha256 over sorted POSIX path + NUL + git blob SHA-1 + LF) |
| Blob count | 1073 (`tree_blob_count` in `runtime/easel-workbench-overlay.json`) |
| Skill root | `skills/builtin` (v0.2.1 used `skills/openclaw`; the 114 directories are the same set) |
| Licence | Apache-2.0 (`LICENSE` sha256 `c71d239d…d0ab4`); **exception**: `skills/builtin/gzh-design/` is vendored **AGPL-3.0** |

### 9.2 Why a digest, not a tag

After releasing v0.3.0, upstream **replaced the tag while keeping the version number**. A tag that
can move is not an identity. Therefore:

- the registry rejects an engine entry that has a tag but no `tree_sha256`;
- `python scripts/check_easel_upstream.py` and `verify_easel_runtime.py --resolve-tag` treat tag
  drift as a **warning**, never as a verdict;
- any receipt that names an engine writes both `commit` and `tree_sha256`.

### 9.3 Rules while two engines coexist

| Rule | Content |
|---|---|
| Default selection | The registry's `active` field |
| Explicit override | `--engine v0.2.1` / `--engine v0.3.0` applies to one command only and does not change `active` |
| Switching | Only through `scripts/easel_engine.py switch <engine>` (new), which writes `runtime/easel-engine-switch.json` |
| Output ownership | New artifacts land in the active tree's `outputs/`; history is not migrated, and `projects/*/final/` remains the delivery truth |
| Retention | The v0.2.1 tree is kept for at least one full release cycle after M2 acceptance, and only then archived per §12 R8 |

---

## 10. Migration path

### 10.1 Milestones

| Milestone | Goal | Entry | Exit (machine-checkable) | Rollback |
|---|---|---|---|---|
| **M0** | Governance and pin convergence, **zero behaviour change** | This PRD approved | `dev_check.py` passes; the pin exists only in the registry; five literals gone | Revert the PR |
| **M1** | **Replace the engine**: v0.3.0 becomes `active` | M0 exit + three golden baseline receipts | `resolve_easel.py` → `engine=v0.3.0`; golden projects render + QC PASS + receipts carry `engine_id` | `easel_engine.py switch v0.2.1` |
| **M2** | **Replace the cockpit**: the workbench takes over the interaction surface, Agent still denied | M1 exit + reproducible frontend build on the target machine | `verify --overlay --frontend-build` VERIFIED; `host status` HOST_READY; one offline task read-back | Stop the host, return to the CLI |
| **M3** | Governance attaches to the foundation | M2 exit | Nine gates resolved as skill entries; a dry run emits gate receipts | Remove the registry entries |
| **M4a** | Draft automation (a human presses the last button) | M3 exit + ADR-025 in force | Platforms at `autonomy=DRAFT_AUTO` produce real drafts plus receipts | Fall back to `MANUAL` |
| **M4b** | Single-platform grey full automation | M4a stable + separate authorisation | One real publication plus a 24h observation record | Fall back to `DRAFT_AUTO` |
| **M4c** | Per-platform progression to full automation | Per-platform authorisation | One authorisation and one publication receipt per platform | That platform drops one tier |

### 10.2 The four mechanisms behind "no rendering interruption"

| Mechanism | How | Where |
|---|---|---|
| Two roots coexist | `.runtime/easel` untouched; v0.3.0 installs into `.runtime/easel-v030`. **No overwrite-in-place** (that would leave both trees unverifiable during the window) | `scripts/resolve_easel.py` candidate table reads the registry `roots` |
| Layout-driven resolution | `resolve_skill_dir(..., layout=...)`; the implicit "openclaw first" order is removed | `src/contentops/easel/skill_paths.py` |
| Receipt anchoring | Receipts record `easel.engine_id`, so "which engine rendered this" is answerable | `scripts/assemble_easel.py`, `scripts/m5_production.py` |
| One-command rollback | Flip the registry `active`, re-derive the lock, write a switch receipt with both engine ids and the re-verification result | `scripts/easel_engine.py` (new) |

### 10.3 Proposed PR sequence

| PR | Content | Risk | Depends on |
|---|---|---|---|
| PR-01 | This PRD (Chinese + English mirror) and documentation-gate wiring. No code, no pin change | L0 | — |
| PR-02 | Add `runtime/easel-pins.json` (registering only v0.2.1 first, `active` unchanged) and the lock derivation note | L2 | — |
| PR-03 | Replace the five literals with registry reads; remove the silent `_FALLBACK_PIN` fallback; add a "no literals" test | L3 | PR-02 |
| PR-04 | Add `layout` to `skill_paths`; adapt `assemble`/`render`; batch-replace the rename blast radius | L2–L3 | PR-03 |
| PR-05 | `docs/UPSTREAM-EASEL.md` pin table and a two-engine section in `docs/CURRENT-STATE.md` | L1 | PR-02 (parallel with PR-04) |
| PR-06 | `scripts/easel_engine.py`, switch receipt and a rollback-drill test | L3 | PR-03 |
| PR-07 | Register v0.3.0 in the registry (`active` still v0.2.1) and `verify --record` | L3 | PR-02 |
| PR-08 | **Flip `active` to v0.3.0**, rerun three goldens, diff receipts | L3 | PR-04/06/07 |
| PR-09 | Workbench takeover: build-policy range, host criteria, offline API read-back | L2 | PR-08 |
| PR-10 | Attach the nine gates as skill declarations | L2 | PR-09 |
| PR-11 | Registry schema v2 with `autonomy`, and the four-tier `delivery_gate` | L3 | PR-10 + ADR-025 |
| PR-12 | First real draft automation (M4a) | L3 | PR-11 + separate authorisation |

**Three non-compressible serialisation points**: PR-08 (flip `active`), PR-11 (`autonomy` in
force), PR-12 (first real external write).

---

## 11. Publishing tier model

### 11.1 Four tiers

| Tier | Meaning | Who may promote | Prerequisite evidence |
|---|---|---|---|
| `MANUAL` | Today: the system produces a delivery package and a receipt; a human publishes and records the URL | — | Default |
| `DRAFT_AUTO` | The system creates a platform draft; a human presses the final publish | Founder | A `draft_only` channel plus one real draft receipt |
| `GRAY_AUTO` | Full automation for one platform, one account, one topic, with a 24h observation window | Founder, separate authorisation | Previous tier stable + rollback plan + observation record |
| `FULL_AUTO` | Full automation | Founder, per platform | Grey observation passed + that platform's risk record |

### 11.2 Hard constraints

1. **No batch promotion**: one authorisation covers exactly one platform.
2. **The Douyin exception stands**: `UNCONDITIONALLY_REFUSED` persists until that platform obtains
   a `FULL_AUTO` authorisation. Its stated reasons (restricted eligible subjects, per-use user
   initiation, prohibition of homogenised content) do not expire because technology improved.
3. **Receipt before tier**: a tier without evidence is not authorised; a registry entry claiming
   `FULL_AUTO` with an empty `evidence[]` must fail `check_platform_status_sync.py`.
4. **Demotion is the fastest path**: any platform-side signal (rate limit, warning, review
   rejection) drops one tier immediately and is recorded. No approval needed to demote.
5. **Status and tier are orthogonal**: `status` (PLANNED…PRODUCTION_ACCEPTED) answers "how far the
   evidence goes"; `autonomy` answers "how far we are allowed to go". Neither is derived from the
   other.

### 11.3 Current baseline (the table is the fact)

| Platform | status | publish_mode | draft_support | easel_capability | autonomy (target) |
|---|---|---|---|---|---|
| douyin | PLANNED | NOT_IMPLEMENTED | NONE | UPSTREAM_DECLARED | MANUAL (refusal kept) |
| bilibili | PLANNED | NOT_IMPLEMENTED | NONE | UPSTREAM_DECLARED | MANUAL |
| xiaohongshu_video | PLANNED | NOT_IMPLEMENTED | NONE | UPSTREAM_DECLARED | MANUAL |
| shipinhao | PLANNED | NOT_IMPLEMENTED | NONE | UPSTREAM_DECLARED | MANUAL |
| wechat_article | PLANNED | **DRAFT_ONLY** | NONE | UPSTREAM_DECLARED | MANUAL → first `DRAFT_AUTO` candidate |
| x | **INTEGRATED** | MANUAL_ONLY | NONE | ABSENT | MANUAL |
| zhihu | PLANNED | NOT_IMPLEMENTED | NONE | UPSTREAM_DECLARED | MANUAL |
| csdn | PLANNED | NOT_IMPLEMENTED | NONE | ABSENT | MANUAL |
| youtube | PLANNED | NOT_IMPLEMENTED | NONE | ABSENT | MANUAL |

Two frequently misread points:
- `wechat_article` is the only platform with `publish_mode: DRAFT_ONLY`, but its `draft_support`
  is `NONE` — **target state and current capability are different things**; M4a must build the
  channel first;
- `x` is the only `INTEGRATED` row, and that integration means "local offline gate":
  `publisher.py` has no branch that returns `PUBLISHED`.

---

## 12. Risks and rollback

| # | Risk | Trigger | Observable signal | Mitigation | Phase |
|---|---|---|---|---|---|
| R1 | **AGPL compliance** | `skills/builtin/gzh-design/` is vendored AGPL-3.0; serving it over a network triggers the source-offer obligation | `grep -r gzh-design` hits the graphic line; `articles.py` already records `upstream_license: AGPL-3.0` | In-process local use only, never in a served distribution path; add a `license_boundary` field; evaluate removing the skill before commercial use | M1 onward |
| R2 | Tag force-replaced again | Upstream replaces the same tag | `--resolve-tag` reports a different commit | Identity is `commit + tree_sha256`; registry rejects entries without a digest | M0/M1 |
| R3 | Node 25.x incompatible | Building the frontend with Node 25 | Build receipt `toolchain.node` mismatch | Build policy gains `>=20 <25`; mismatch means `HOST_BLOCKED` | M2 |
| R4 | Skill rename breaks hardcoded paths | The moment v0.3.0 becomes active | assemble / render / registry evidence fail together | 20+ paths replaced in one change; layout-driven resolution; a residual scanner | M1 |
| R5 | 114 skill descriptions truncated by the context budget | The workbench loads every skill directory at once | The agent "does not know" a skill exists | Declare only the skills in use; extensions go through the registry | M3 |
| R6 | Windows Agent isolation unverified | Reading `HOST_READY` as "executable" | The sandbox prototype refuses unconditionally | Keep ADR-022 D4: no Agent before M3; isolation acceptance is its own gate | M2/M3 |
| R7 | Automated publishing bans the account, irreversibly | Real external writes from M4b on | Platform rate limits, warnings, bans | Move only by the four tiers; single platform, single account grey runs; 24h observation; Douyin keeps its refusal | M4b/M4c |
| R8 | Multiple copies cause disk and resolver confusion | Copying or rebuilding without an explicit target | Three copies exceed 3 GB; the resolver picks the legacy clone | `Easel/` is diffed and then archived (AGENTS §10); the registry lists only controlled roots | M0 |
| R9 | Pin truth drifts | One literal updated, another missed | Docs say A, verification uses B | Single registry + five literals removed + a grep-assertion test | M0 |
| R10 | Hardcoded commit in receipts turns every golden diff red | Rerunning the comparison at M1 | All differences sit in `easel_runtime_commit` | Abstract `engine_id` **before** flipping `active` | M1 |
| R11 | Frontend dependency audit findings (1 critical / 3 high) | The workbench enters the trust boundary | `npm audit`; the build receipt already records the counts | Archive the audit result; do not auto-run `npm audit fix` (it breaks the lockfile digest); accepting the risk needs an ADR note | M2 |
| R12 | `outputs/` artifacts linger across trees | Old artifacts stay in the old root after a switch | The verifier excludes `outputs/` from byte comparison, so nothing fails | The switch receipt lists both trees' outputs; delivery truth stays `projects/*/final/` | M1 |
| R13 | `docs/UPSTREAM-EASEL.md` has no freshness gate | The pin changes and the doc does not | That document sits in the doc-freshness **exempt** list | Move it into `tracks` (`code: runtime/easel-pins.json`) and check the pin table against the registry | M0 |

### Rollback buttons

| Situation | Action | Time |
|---|---|---|
| Rendering breaks after M1 | `easel_engine.py switch v0.2.1`, rerun goldens | ≤ 5 min |
| Host misbehaves after M2 | Stop the host, return to the CLI (host and production are decoupled) | ≤ 2 min |
| Platform-side signal after M4 | Drop that platform's `autonomy` one tier | Immediate |
| Any governance incident | Deny writes on the active engine and re-verify read-only | Immediate |

---

## 13. Acceptance criteria

### M0

| # | Command | Expected |
|---|---|---|
| 1 | `python scripts/check_docs.py` | `All documentation checks passed.` |
| 2 | `python scripts/check_i18n.py` | exit 0, no `MISSING mirror` / `STALE second Chinese copy` |
| 3 | `python scripts/check_doc_freshness.py` | 0 STALE / 0 ERROR |
| 4 | `python scripts/dev_check.py` | every step passes |
| 5 | `grep -rn "3fe2d99" --include=*.py scripts src` | zero business constants (test fixtures and registry reads only) |

### M1

| # | Command | Expected | Receipt |
|---|---|---|---|
| 1 | `python scripts/resolve_easel.py` | `status=OK`, `engine=v0.3.0`, `commit=bb3c8ff…`, with `tree_sha256` | — |
| 2 | `python scripts/verify_easel_runtime.py --runtime .runtime/easel-v030 --commit bb3c8ff… --json --record` | `VERIFIED`, `tree_sha256=c26fc96a…4ec8` | `runtime/easel-runtime.json` |
| 3 | `python scripts/assemble_easel.py projects/m5-easel-pin` | exit 0, an mp4 under `final/` | `receipts/compose.json` with `easel.engine` |
| 4 | `python scripts/qc_video.py projects/m5-easel-pin` | PASS, zero hard fails | `receipts/qc-report-*.json` |
| 5 | `python scripts/resolve_easel.py --engine v0.2.1` | still `status=OK` (rollback tree usable) | — |
| 6 | `python scripts/easel_engine.py switch v0.2.1` then back (new) | both `status=OK`, timings recorded | `runtime/easel-engine-switch.json` |

### M2

| # | Command | Expected |
|---|---|---|
| 1 | `python scripts/verify_easel_runtime.py --overlay --frontend-build --json` | `VERIFIED`, all 14 overlay digests match |
| 2 | `python scripts/easel_host.py status --workbench --json` | `HOST_READY`, `blockers: []` |
| 3 | One offline task POST + GET | profile / draft / receipt readable, both authorisation flags false |
| 4 | An Agent execution request | still `BLOCKED` (regression: D4 intact) |

### M3

| # | Command | Expected |
|---|---|---|
| 1 | `python scripts/skill_route.py` | resolves the ContentOps gate extension |
| 2 | `python scripts/check_skill_references.py` | exit 0 |
| 3 | One dry-run chain (`m5_production.py <project> --skip-compose`) | complete gate receipts, `production_ready:false` |

### M4

| # | Command | Expected |
|---|---|---|
| 1 | `python scripts/check_platform_status_sync.py --strict` | zero mismatches |
| 2 | Registry `autonomy.level` values | `MANUAL` everywhere except authorised platforms |
| 3 | `python -c "from contentops.platforms.delivery_gate import authorize_delivery as a; print(a('douyin').outcome)"` | `REFUSED` |
| 4 | M4a real draft | draft receipt + human confirmation timestamp |
| 5 | M4b grey publication | platform-side success receipt + 24h observation record |

---

## 14. Cadence and collaboration constraints

- One PR sequence per milestone; no mega-commits (AGENTS §9).
- Every new branch is registered in `config/governance/branch-registry.json` with `expires` as a
  review date (not a deletion date); run `python scripts/check_branch_registry.py --today 2026-11-15`
  before committing.
- `main` is protected: three required checks, squash merge, linear history, zero approvals while
  the owner works solo.
- Each milestone ends with a clean `git status --porcelain` (AGENTS §10).

---

## 15. Open decisions (do not guess)

| # | Open item | Owner | How to settle |
|---|---|---|---|
| 1 | Which two projects serve as golden #2 / #3 | Founder | `ls projects/*/receipts/compose.json` plus the existence of `final/*.mp4` |
| 2 | First grey platform for M4b | Founder | Needs a real account; `wechat_article` is the only `DRAFT_ONLY` target |
| 3 | v0.3.0 blob count reconciliation (1073 vs 1071 baseline) | Governance | `verify_easel_runtime.py --overlay --json` `baseline_files` / `overlay_files` |
| 4 | Whether ADR-024 is separate from ADR-023 | Founder | Depends on whether Agent isolation acceptance is its own gate |
| 5 | Archive or delete `Easel/` (2.2 GB) | Founder | Diff the two uncommitted modifications first (AGENTS §10) |
| 6 | Whether to move `docs/UPSTREAM-EASEL.md` out of the exempt list | Governance | Handle inside M0 |
| 7 | Retention deadline for the v0.2.1 tree | Founder | At least one release cycle after M2 acceptance |
| 8 | Long-term retention of gzh-design (AGPL) | Founder + legal | Evaluate before commercial use |
| 9 | Quantified impact of upstream #156 (skill description truncation) | Governance | Measure on the upstream issue |

---

## 16. Traceability matrix

| FR domain | ADRs | Main code / config | Receipts |
|---|---|---|---|
| PIN | ADR-006, ADR-012 D3, ADR-022 D1 | `runtime/easel-pins.json` (new), `runtime/easel.lock.json`, `scripts/resolve_easel.py`, `scripts/verify_easel_runtime.py` | `runtime/easel-engine-switch.json` (new) |
| ENG | ADR-001, ADR-007 | `scripts/assemble_easel.py`, `src/contentops/easel/skill_paths.py`, `scripts/m5_production.py` | `receipts/compose.json`, `receipts/m5-run.json` |
| GOV | ADR-005, ADR-021 | `scripts/production_gates.py`, `runtime/skill-registry.json` | `receipts/production-gates*.json` |
| WB | ADR-016 D2, ADR-022 D2/D3/D4 | `src/contentops/easel/host.py`, `guard.py`, `scripts/easel_host.py` | project-local offline task receipt |
| PUB | ADR-014, ADR-015, ADR-016 D4 | `config/registry/platforms.json`, `src/contentops/platforms/delivery_gate.py` | draft / publication receipts |
| DOC | AGENTS §1 rule 10 | `scripts/check_i18n.py`, `config/docs/doc-freshness.json` | CI check result |

---

## 17. Change log and proposed ADRs

### 17.1 Decision records this document needs (proposed, not signed)

| Proposed ID | Title | Purpose | Supersedes / revises |
|---|---|---|---|
| ADR-023 | Adopt v0.3.0 as the production engine: pin by content digest, two engines coexist | Answers "do we adopt v0.3.0" | Supersedes ADR-012 D3; revises the pin value in ADR-016 D1; narrows ADR-022 D1's "candidate only" |
| ADR-024 | The workbench as interaction surface, and the Agent isolation acceptance gate | Writes the cockpit boundary | Refines ADR-022 D2/D3/D4 without relaxing D4 |
| ADR-025 | Four publishing autonomy tiers and the authorisation flow | Gives automation a lawful path | Supersedes ADR-014; revises the publishing part of ADR-015, keeping D2–D8 |

### 17.2 Implementation progress (M0)

Branch `feat/173-easel-m0-pin`. Everything below is checkable; the command and its
result are named.

| PR | State | Evidence |
|---|---|---|
| PR-01 docs and gate wiring | **done** | `check_i18n.py`, `check_doc_freshness.py`, `check_docs.py` all pass |
| PR-02 pin registry | **done** | `runtime/easel-pins.json`; `active=v0.2.1`, `workbench_engine=v0.3.0`; the v0.3.0 entry carries `tree_sha256` and `installed=false` |
| PR-03 literals removed, fail closed | **done** | four constants now read the registry; `_FALLBACK_PIN` deleted; an unreadable registry yields `BLOCKED / PINS_UNREADABLE`; `tests/test_easel_pins.py` 14/14 |
| PR-05 two-engine docs | **partial** | `docs/UPSTREAM-EASEL.md` now names the registry as the only pin source; the two-engine section in `CURRENT-STATE.md` waits for the M1 switch, because describing an engine that is not active would be fiction |
| PR-04 / 06 / 07 | **not started** | skill layout resolution, the `easel_engine.py` switcher, and registering the v0.3.0 instance |

Pre-existing failures repaired along the way (all four were already red in the
2026-11-13 work, none introduced here):

| Suite | Before | After | Cause |
|---|---|---|---|
| `tests/test_easel_host_guard.py` | 23/27 | **28/28** | three assertions described the old contract: `/api/status` is now denied, the `mutations` value changed, and the offline dependency list gained PyYAML; a regression test now pins the denial |
| `tests/test_easel_workbench_overlay.py` | 45/46 | **46/46** | generated mode now checks DNA freshness, so a fake account cannot project; the test asserts MISMATCH honestly |
| `tests/test_easel_offline_task.py` | 5/18 | **19/19** | fixtures lacked `project.yaml`; POSTs carried no same-origin `Origin`; error-code ordering; an interrupted write now leaves a failure receipt instead of a bare OSError |
| `tests/test_m5_evidence.py` | 21/22 | **22/22** | the workbench-resolver fixture was not a valid overlay |

One code behaviour change, outside the pin but needed to restore the documented
contract: `offline_task.run_offline_draft_task` validates the account's shape
before the project binding, so a non-string account is `ACCOUNT_INVALID` rather
than `PROJECT_ACCOUNT_MISMATCH`.

### 17.3 Change log

| Date | Version | Change |
|---|---|---|
| 2026-11-15 | v0.1 | First version. Status Proposed, awaiting Founder approval. Documentation and documentation-gate wiring only; no code change, no pin change |
| 2026-11-15 | v0.2 | Records M0 landing: single pin registry, four literals removed, fail-closed resolution. Corrects the literal count in FR-PIN-02 (five was wrong: four code constants plus one description of what a screenshot shows, and that one stays) |

---

## Appendix: evidence boundary of this PRD

| Claim | Evidence level |
|---|---|
| The current pin is v0.2.1 / `3fe2d99` | Machine-readable lock file |
| Six upstream scripts are called, one with a real artifact | Code + receipt + a measured mp4 |
| v0.3.0 exists and its tag was force-replaced | Upstream tag/release record + this repository's overlay record |
| 114 skills, 1073 blobs, a tree digest | This repository's overlay record + the verifier |
| Nine platform rows and their statuses | `config/registry/platforms.json` |
| "The workbench runs" / "the Agent executes safely" | **No evidence.** The former is `HOST_BLOCKED`; the latter is forbidden by ADR-022 D4 |

That last row is the most important one here: **when reading this PRD, keep "target" and "already
happened" strictly apart.**
