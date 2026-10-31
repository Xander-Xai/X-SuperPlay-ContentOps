# GZH vendored skill licence matrix — 2026-10-31

> Evidence-based audit of `vendor/gzh-thinktank/gzh_未来智能/skills/`. This is not
> a legal opinion. Absence of a licence is recorded as `RIGHTS_UNKNOWN`, not as
> infringement. No third-party content is assumed to belong to the owner merely
> because it was copied from the owner's private repository.

## Scope and method

- 41 active directories: 40 `SKILL.md` files plus the `excalidraw-skill-pack`
  package. 9 archived skills under `_archive/`.
- Read front matter, local `LICENSE`/`COPYING`, `package.json`,
  `THIRD_PARTY_NOTICES.md`, `skills/skill-registry.yaml`, and script references.
- Checked the live private remote `Xander-Xai/gzh-Future-Intelligence`:
  `main` is `e9303d1`, tree `7b75e4e8` — the same full tree object as the imported commit; the vendored copy is a filtered subset. The
  imported commit `93645f1` is **not** on that remote.

## Classification

| Class | Meaning |
|---|---|
| `OWNED_AND_CLEARED` | Git authorship or a file-level original-work record in the owner’s private repository, with no third-party source/licence marker. |
| `OWNER_ATTESTED` | Only the owner’s own statement (e.g. `THIRD_PARTY_NOTICES.md`) supports origin; no independent file-level provenance. Not the same as cleared. |
| `THIRD_PARTY_LICENSE_VERIFIED` | A licence file or declared licence plus a source was found. |
| `RESTRICTED` | A known copyleft/proprietary obligation that needs an owner decision. |
| `RIGHTS_UNKNOWN` | No licence, author or source evidence. Public distribution paused. |

## Matrix

| Skill | Class | Source / author | Version | Licence basis | Usage | Public distribution | Action |
|---|---|---|---|---|---|---|---|
| `agnes-image-21-flash` | OWNED_AND_CLEARED | local adapter; public Agnes API contract | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | core visual generation route | ALLOWED — Git authorship evidence | keep; API key outside Git |
| `ai-thinktank-workflow` | OWNED_AND_CLEARED | private gzh workflow (Matrix Ops) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | canonical workflow skill | ALLOWED — Git authorship evidence | keep |
| `arxiv-search` | THIRD_PARTY_LICENSE_VERIFIED | `langchain-ai/deepagents` (`libs/code/examples/skills/arxiv-search`, MIT) | adapted local copy | MIT; upstream copyright LangChain, Inc. | optional research; not in registry | ALLOWED with MIT notice | keep; notice recorded in `vendor/gzh-thinktank/THIRD_PARTY_NOTICES.md` |
| `beautiful-mermaid` | THIRD_PARTY_LICENSE_VERIFIED | Alex (LICENSE) | local copy | MIT LICENSE in directory; `package.json` says ISC (discrepancy) | core diagram rendering | ALLOWED with MIT notice | keep LICENSE; resolve ISC/MIT with upstream |
| `content-humanizer` | OWNER_ATTESTED | private gzh workflow (Matrix Ops) | local | `THIRD_PARTY_NOTICES.md` owner attestation: local rewritten methodology; no independent file-level provenance | supporting copy | HOLD — owner attestation only; independent evidence required for public release | keep |
| `content-production` | OWNER_ATTESTED | private gzh workflow (Matrix Ops) | local | `THIRD_PARTY_NOTICES.md` owner attestation: local rewritten methodology; no independent file-level provenance | supporting copy | HOLD — owner attestation only; independent evidence required for public release | keep |
| `content-repurposer` | RIGHTS_UNKNOWN | public OpenClaw skill collections; original author not established | 1.1.0 | none found | supporting copy; blocked from dispatch | HOLD — third-party text, no licence | block; obtain permission or replace with a locally written adapter |
| `content-strategy` | OWNER_ATTESTED | private gzh workflow (Matrix Ops) | local | `THIRD_PARTY_NOTICES.md` owner attestation: local rewritten methodology; no independent file-level provenance | supporting strategy | HOLD — owner attestation only; independent evidence required for public release | keep |
| `deep-research` | **RESTRICTED** | `Imbad0202/academic-research-skills` (`deep-research`) | local copy | **CC BY-NC 4.0**; upstream copyright Cheng-I Wu | optional research | BLOCKED — noncommercial licence | block dispatch; obtain commercial permission or remove from the public import |
| `exa-web-search-free` | RIGHTS_UNKNOWN | Exa MCP wrapper; no author/licence | unknown | none found | optional search adapter referenced by scripts | HOLD — no licence evidence | block dispatch; ContentOps route gate rejects it; obtain permission or replace |
| `excalidraw-diagram` | OWNED_AND_CLEARED | local wrapper around the MIT pack | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | core diagram route | ALLOWED — Git authorship evidence | keep; retain pack licence |
| `excalidraw-skill-pack` | THIRD_PARTY_LICENSE_VERIFIED | Timur Isachenko (LICENSE) | local copy | MIT LICENSE; `package.json` MIT | renderer for diagram route | ALLOWED with MIT notice | keep LICENSE |
| `formula-rendering` | OWNED_AND_CLEARED | local KaTeX pipeline | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | core formula rendering | ALLOWED — Git authorship evidence | keep; add KaTeX MIT notice if absent |
| `gzh-article-assets` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | canonical core stage | ALLOWED — Git authorship evidence | keep |
| `gzh-article-format` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | canonical core stage | ALLOWED — Git authorship evidence | keep |
| `gzh-article-orchestrator` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | canonical core stage | ALLOWED — Git authorship evidence | keep |
| `gzh-article-writing` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | canonical core stage | ALLOWED — Git authorship evidence | keep |
| `gzh-design-skill` | **RESTRICTED** | 甲木 (Jiamu) × 摸鱼小李 (Moyu Xiaoli) — LICENSE | local copy | **AGPL-3.0** (full text in directory) | core HTML quality validator | **RESTRICTED** — AGPL obligations; owner decision | keep LICENSE/notice; do not merge until the owner accepts AGPL or replaces the validator |
| `gzh-draft-publisher` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | core publish-to-draft stage | ALLOWED — Git authorship evidence | keep |
| `gzh-editorial-review` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | canonical core stage | ALLOWED — Git authorship evidence | keep |
| `gzh-sticker-assets` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | canonical core stage | ALLOWED — Git authorship evidence | keep |
| `gzh-title-seo` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | canonical core stage | ALLOWED — Git authorship evidence | keep |
| `gzh-topic-research` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | canonical core stage | ALLOWED — Git authorship evidence | keep |
| `gzh-visual-assets` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | core visual assets stage | ALLOWED — Git authorship evidence | keep |
| `gzh-visual-director` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | canonical core stage | ALLOWED — Git authorship evidence | keep |
| `khazix-writer` | THIRD_PARTY_LICENSE_VERIFIED | `KKKKhazix/khazix-skills` (`khazix-writer`, MIT) | adapted local copy | MIT; upstream copyright 数字生命卡兹克 | optional writing style | ALLOWED with MIT notice; no endorsement claim | keep; notice recorded; do not present output as endorsed by the author |
| `midu-proofread` | RIGHTS_UNKNOWN | calls `api.midu.com`; no author/licence | 1.0.0 | none found | optional proofreading | HOLD — no licence evidence | block dispatch; obtain permission or replace |
| `obsidian` | THIRD_PARTY_LICENSE_VERIFIED | `openclaw/openclaw` (`skills/obsidian`, MIT) | adapted local copy | MIT; upstream copyright OpenClaw Foundation | optional note automation | ALLOWED with MIT notice | keep; notice recorded |
| `opc-conversion-loop` | OWNED_AND_CLEARED | OPC internal methodology | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | supporting strategy | ALLOWED — Git authorship evidence | keep |
| `read-arxiv-paper` | THIRD_PARTY_LICENSE_VERIFIED | `karpathy/nanochat` (`.claude/skills/read-arxiv-paper`, MIT) | adapted local copy | MIT; upstream copyright 2025 Andrej Karpathy | optional research | ALLOWED with MIT notice | keep; notice recorded |
| `source-evidence-layer` | OWNED_AND_CLEARED | local evidence layer | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | supporting evidence | ALLOWED — Git authorship evidence | keep |
| `vision` | RIGHTS_UNKNOWN | multi-provider wrapper (Agnes/Doubao/Qwen/OpenAI) | unknown | none found | supporting visual review | HOLD — no licence evidence | block dispatch; owner attestation or licence required; local `visual_qa` remains |
| `wechat-card-qrcode` | OWNED_AND_CLEARED | WeChat Matrix Team | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | supporting card render | ALLOWED — Git authorship evidence | keep |
| `wechat-cover` | OWNED_AND_CLEARED | WeChat Matrix Team | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | supporting cover | ALLOWED — Git authorship evidence | keep |
| `wechat-publisher` | THIRD_PARTY_LICENSE_VERIFIED | `0731coderlee-sudo/wechat-publisher` (MIT); wrapper for `wenyan-cli` (Apache-2.0, not bundled) | 0.1.0 | MIT wrapper; Apache-2.0 dependency not distributed | alternative publisher; core uses `gzh-draft-publisher` | ALLOWED with MIT notice and Apache-2.0 notice if bundled | keep; notice recorded |
| `wechat-seo-optimizer` | OWNED_AND_CLEARED | WeChat Matrix Team | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | canonical core stage | ALLOWED — Git authorship evidence | keep |
| `wechat-svg-interactive` | OWNED_AND_CLEARED | WeChat Matrix Team | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | supporting SVG compatibility | ALLOWED — Git authorship evidence | keep |
| `wechat-tts-audio` | OWNED_AND_CLEARED | WeChat Matrix Team | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | optional audio | ALLOWED — Git authorship evidence | keep |
| `wechat-viral-topic` | RIGHTS_UNKNOWN | third-party “10万+爆款选题” skill; no author/licence | unknown | none found | optional topic research referenced by scripts | HOLD — no licence evidence | block dispatch; ContentOps route gate rejects it; obtain permission or replace |
| `wemp-operator` | THIRD_PARTY_LICENSE_VERIFIED | <https://github.com/gaozejie/wemp-operator> | declared MIT | MIT wrapper; no upstream source embedded | optional adapter | ALLOWED with MIT notice | keep |
| `z5-wechat-sop` | THIRD_PARTY_LICENSE_VERIFIED | <https://github.com/Z5Research/Z5-WeChat-SOP> | declared MIT | MIT wrapper; no upstream source embedded | optional adapter | ALLOWED with MIT notice | keep |
| `_archive/aws-wechat-article-assets` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-article-formatting` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-article-images` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-article-main` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-article-publish` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-article-review` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-article-topics` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-article-writing` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-sticker` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |

## Result

| Class | Count |
|---|---:|
| `OWNED_AND_CLEARED` | 22 active + 9 archived |
| `THIRD_PARTY_LICENSE_VERIFIED` | 9 |
| `RESTRICTED` | 2 (`gzh-design-skill` AGPL-3.0; `deep-research` CC BY-NC 4.0) |
| `OWNER_ATTESTED` | 3 |
| `RIGHTS_UNKNOWN` | 5 |

### Ownership evidence and asset scope

- All five remote commits (`bb52de1`, `5860343`, `96bfe41`, `901aeee`,
  `e9303d1`) are authored by `yandexuanxuan` (now Xander-Xai). A sampled core
  path, `skills/gzh-article-writing/SKILL.md`, resolves to `901aeee` with no
  third-party marker. This is authorship evidence in the owner's private
  repository, not a legal opinion; it is why the core skills are
  `OWNED_AND_CLEARED` rather than `OWNER_ATTESTED`.
- Skill assets: 3 SVG icons, no raster images, PDFs or Office files. Two icons
  belong to owned skills; `wechat-viral-topic/_icon.svg` belongs to a
  rights-unknown skill and is on hold with it. The 2 `.template`, 7 `.mustache`
  and 5 `.html` files belong to the skills whose classification covers them.

## AGPL analysis — `gzh-design-skill`

- **Licence:** AGPL-3.0; full text in `skills/gzh-design-skill/LICENSE`; copyright
  notice names 甲木 (Jiamu) × 摸鱼小李 (Moyu Xiaoli).
- **Use:** `scripts/workflow_gate.py:80` and `scripts/verify_draft_submission.py:32`
  resolve `skills/gzh-design-skill/scripts/validate_gzh_html.py`;
  `scripts/validate_matrix.py` lists the skill as a required path. It is a
  **required HTML validator**, not an optional ornament.
- **Modification:** the vendored directory is verbatim; no local patch is
  recorded. If it is modified, AGPL §5 requires the modified source; the source is
  present in the same directory.
- **Composition boundary:** it is a separate skill directory invoked by path, not
  imported into ContentOps Python. The repository itself does not expose the
  validator as a network service. If the workflow is operated as a service, AGPL
  §13 (source offer for a network service) attaches to the validator and any
  modified version.
- **Decision:** public redistribution is permitted under AGPL with the licence and
  source, but it is **not permissive** and cannot be relicensed by this repository.
  Removing it would make the HTML gate fail; no compliant replacement with equal
  regression tests exists. Keep it, fail closed if absent, and require the owner
  to accept AGPL or fund a replacement.

### Licence scope notes

- **`beautiful-mermaid`** — the directory's `LICENSE` is MIT (Copyright Alex);
  `package.json` says ISC. Both are permissive, but they are not the same
  statement. Treat the LICENSE text as the file-level grant for the vendored
  directory, preserve it verbatim, and ask upstream to reconcile the metadata.
  Do not add an ISC claim or relicense the directory.
- **`excalidraw-skill-pack`** — MIT LICENSE (Timur Isachenko) and `package.json`
  MIT; keep the notice.
- **`wemp-operator` / `z5-wechat-sop`** — MIT wrappers; no upstream source is
  embedded. Keep the declared MIT notices.
- **`gzh-design-skill`** — AGPL-3.0; see the boundary analysis above. It is a
  separate invoked component, not linked into ContentOps Python; network-service
  operation would trigger AGPL §13.
- **`OWNER_ATTESTED`** — the repository's own notice is not independent
  provenance. Those four components are on public hold until the owner provides
  file-level evidence or a legal sign-off.

## Per-skill resolution

The ten original `RIGHTS_UNKNOWN` entries were rechecked against public upstream
repositories and their licence files. Six now have a verified licence, one has a
known restrictive licence, and three remain unknown. A fourth unknown was added
from the `OWNER_ATTESTED` group.

| Skill | Resolution | Evidence | Dispatch | Public distribution |
|---|---|---|---|---|
| `arxiv-search` | MIT | `langchain-ai/deepagents`, `libs/code/examples/skills/arxiv-search`; repo licence MIT; local file adapted | allowed | allowed with notice |
| `deep-research` | CC BY-NC 4.0 | `Imbad0202/academic-research-skills`, `deep-research`; LICENSE is CC BY-NC 4.0, copyright Cheng-I Wu | **blocked** | **blocked** (noncommercial) |
| `exa-web-search-free` | unknown | OpenClaw community copies; no upstream licence found | **blocked** | hold |
| `khazix-writer` | MIT | `KKKKhazix/khazix-skills`, `khazix-writer`; repo licence MIT | allowed | allowed with notice; no endorsement claim |
| `midu-proofread` | unknown | Midu API wrapper; no upstream licence found | **blocked** | hold |
| `obsidian` | MIT | `openclaw/openclaw`, `skills/obsidian`; repo licence MIT | allowed | allowed with notice |
| `read-arxiv-paper` | MIT | `karpathy/nanochat`, `.claude/skills/read-arxiv-paper`; repo licence MIT | allowed | allowed with notice |
| `vision` | unknown | local multi-provider wrapper; no author or licence metadata | **blocked** | hold |
| `wechat-publisher` | MIT wrapper | `0731coderlee-sudo/wechat-publisher`; repo licence MIT; `wenyan-cli` is Apache-2.0 and not bundled | allowed | allowed with notices |
| `wechat-viral-topic` | unknown | mirrored without a licence; original author not established | **blocked** | hold |
| `content-repurposer` | unknown (was `OWNER_ATTESTED`) | identical `Stop reformatting. Start publishing.` text appears in public OpenClaw skill collections; the private repo commit is the initial import only | **blocked** | hold |

The remaining five unknowns are `content-repurposer`, `exa-web-search-free`,
`midu-proofread`, `vision` and `wechat-viral-topic`. None is a canonical
required stage. `exa-web-search-free` and `wechat-viral-topic` are allowed
values in the vendored `scripts/route_content.py:122-123`; the ContentOps gate
therefore rejects a `routing.yaml` that selects them before the workflow runs.
The other three are unreferenced or optional.

### Call sites

| Skill | Call site | Behavior when absent or blocked |
|---|---|---|
| `deep-research` | `skills/skill-registry.yaml:159` optional | must resolve to `BLOCKED`, never a fallback |
| `exa-web-search-free` | vendored `scripts/route_content.py:123` allowed value | ContentOps route gate rejects; do not silently fall back |
| `vision` | `workspace_hygiene.py` manifest prefix and `validate_matrix.py:51` | presence is required for the manifest, not a dispatch; the reviewer script remains local |
| `wechat-publisher` | `scripts/test_post_publish_registry.py:11`, `skill-registry.yaml:225` | fallback publisher only; core uses `gzh-draft-publisher` |
| `wechat-viral-topic` | vendored `scripts/route_content.py:122` allowed value | ContentOps route gate rejects |

## `OWNER_ATTESTED` verification

The four original `OWNER_ATTESTED` entries were checked against the private
repository history and public copies.

| Skill | Finding | Decision |
|---|---|---|
| `content-humanizer` | `author: Matrix Ops`; account-specific Chinese content; private commit `bb52de1` is the initial import; no public duplicate found for its title | retain `OWNER_ATTESTED`; internal use allowed; public release still held for file-level evidence or legal sign-off |
| `content-production` | same pattern; account-specific workflow and gate names | retain `OWNER_ATTESTED`; same hold |
| `content-strategy` | same pattern; account-specific topic contract | retain `OWNER_ATTESTED`; same hold |
| `content-repurposer` | English marketing copy; identical text in multiple public OpenClaw collections; private commit only records the import, not authorship | **downgraded to `RIGHTS_UNKNOWN`**; dispatch blocked |

Git authorship in the private repository is evidence that the owner imported the
file, not that the owner wrote it. That distinction is why three remain
attested rather than cleared, and why `content-repurposer` is no longer
attested at all.

## AGPL-3.0 plan — `gzh-design-skill`

The validator is a required gate, not an ornament. Removing it would disable the
HTML quality check, which the governance rules forbid.

| Option | Assessment |
|---|---|
| **A. Retain and comply (chosen)** | Keep the directory, `LICENSE` and source verbatim; add the notice in `vendor/gzh-thinktank/THIRD_PARTY_NOTICES.md`; state that it is a separate process, not linked into ContentOps Python; if operated as a network service, publish the §13 source offer. Public distribution is permitted under AGPL. |
| B. Replace with an independently written validator | Would remove the AGPL obligation but needs a new validator with equivalent regression tests; not available in this round. |
| C. Obtain a commercial/alternative licence | Requires the authors’ agreement; no evidence of one. |

Option A preserves the HTML gate and is the only option executable now. It is
not a permissive licence and does not relicense ContentOps. The owner must still
accept the AGPL obligation, or fund option B.

## Publication hold

**PR #49 must not merge as-is.** Two findings block public release:

1. **AGPL-3.0.** `gzh-design-skill` is retained under option A above. The
   repository's own licence decision (#11) and the §13 network-service obligation
   need explicit owner acceptance.
2. **Five `RIGHTS_UNKNOWN` skills.** `content-repurposer`,
   `exa-web-search-free`, `midu-proofread`, `vision` and `wechat-viral-topic`
   must be excluded from dispatch, replaced, or cleared by the owner. The
   ContentOps gate blocks dispatch now; public distribution remains held.

`deep-research` is a separate blocker: its CC BY-NC 4.0 licence forbids the
commercial use this account may make of it.

The vendor tree is already on the public PR branch. A new commit that removes
files does **not** remove them from branch history. A history rewrite or a
repository visibility change requires explicit owner authorisation; this audit
performs neither.

## Corrected provenance

- Remote: private, alive, `main e9303d1`, tree `7b75e4e8` — the same full tree
  object as the imported commit; the vendored copy is a filtered subset.
- Imported commit: `93645f1` (not on the remote). Its commit identity is lost; its
  tree is preserved.
- Local checkout `D:\Projects\gzh_x未来智能` and local bundle
  `D:\Archives\repos\gzh-thinktank\2026-10-30\gzh-thinktank.bundle`: absent.
- The earlier `MANIFEST.md` claim that the remote was deleted and returned 404 was
  false and has been corrected.