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
  `main` is `e9303d1`, tree `7b75e4e8` — identical to the vendored tree. The
  imported commit `93645f1` is **not** on that remote.

## Classification

| Class | Meaning |
|---|---|
| `OWNED_AND_CLEARED` | Authored in the private workflow, no third-party source/licence marker, or explicitly described as local methodology in `THIRD_PARTY_NOTICES.md`. |
| `THIRD_PARTY_LICENSE_VERIFIED` | A licence file or declared licence plus a source was found. |
| `RESTRICTED` | A known copyleft/proprietary obligation that needs an owner decision. |
| `RIGHTS_UNKNOWN` | No licence, author or source evidence. Public distribution paused. |

## Matrix

| Skill | Class | Source / author | Version | Licence basis | Usage | Public distribution | Action |
|---|---|---|---|---|---|---|---|
| `agnes-image-21-flash` | OWNED_AND_CLEARED | local adapter; public Agnes API contract | local | notice: local adapter; no upstream code copied | core visual generation route | ALLOWED — owner-authored adapter | keep; API key outside Git |
| `ai-thinktank-workflow` | OWNED_AND_CLEARED | private gzh workflow (Matrix Ops) | local | authored in the private workflow; no third-party marker | canonical workflow skill | ALLOWED — owner copyright asserted | keep |
| `arxiv-search` | RIGHTS_UNKNOWN | no author/source/licence in `SKILL.md` | unknown | none found | optional research; not in registry | HOLD — no licence evidence | exclude from public import or obtain permission |
| `beautiful-mermaid` | THIRD_PARTY_LICENSE_VERIFIED | Alex (LICENSE) | local copy | MIT LICENSE in directory; `package.json` says ISC (discrepancy) | core diagram rendering | ALLOWED with MIT notice | keep LICENSE; resolve ISC/MIT with upstream |
| `content-humanizer` | OWNED_AND_CLEARED | private gzh workflow (Matrix Ops) | local | notice: local rewritten methodology | supporting copy | ALLOWED — owner copyright asserted | keep |
| `content-production` | OWNED_AND_CLEARED | private gzh workflow (Matrix Ops) | local | notice: local rewritten methodology | supporting copy | ALLOWED — owner copyright asserted | keep |
| `content-repurposer` | OWNED_AND_CLEARED | private gzh workflow; generic description | local | notice covers `content-*` as local methodology; note: no upstream marker found | supporting copy | ALLOWED with note | keep; owner may re-review if upstream is identified |
| `content-strategy` | OWNED_AND_CLEARED | private gzh workflow (Matrix Ops) | local | notice: local rewritten methodology | supporting strategy | ALLOWED — owner copyright asserted | keep |
| `deep-research` | RIGHTS_UNKNOWN | no author/source/licence; 13-agent pipeline | unknown | none found | optional research | HOLD — no licence evidence | exclude or obtain permission |
| `exa-web-search-free` | RIGHTS_UNKNOWN | Exa MCP wrapper; no author/licence | unknown | none found | optional search adapter referenced by scripts | HOLD — no licence evidence | exclude or obtain permission; fail closed if absent |
| `excalidraw-diagram` | OWNED_AND_CLEARED | local wrapper around the MIT pack | local | wrapper authored locally; pack is MIT | core diagram route | ALLOWED with pack MIT notice | keep; retain pack licence |
| `excalidraw-skill-pack` | THIRD_PARTY_LICENSE_VERIFIED | Timur Isachenko (LICENSE) | local copy | MIT LICENSE; `package.json` MIT | renderer for diagram route | ALLOWED with MIT notice | keep LICENSE |
| `formula-rendering` | OWNED_AND_CLEARED | local KaTeX pipeline | local | local skill; KaTeX dependency MIT per notice | core formula rendering | ALLOWED — dependency notice required | keep; add KaTeX MIT notice if absent |
| `gzh-article-assets` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | authored in the private workflow | canonical core stage | ALLOWED — owner copyright asserted | keep |
| `gzh-article-format` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | authored in the private workflow | canonical core stage | ALLOWED — owner copyright asserted | keep |
| `gzh-article-orchestrator` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | authored in the private workflow | canonical core stage | ALLOWED — owner copyright asserted | keep |
| `gzh-article-writing` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | authored in the private workflow | canonical core stage | ALLOWED — owner copyright asserted | keep |
| `gzh-design-skill` | **RESTRICTED** | 甲木 (Jiamu) × 摸鱼小李 (Moyu Xiaoli) — LICENSE | local copy | **AGPL-3.0** (full text in directory) | core HTML quality validator | **RESTRICTED** — AGPL obligations; owner decision | keep LICENSE/notice; do not merge until the owner accepts AGPL or replaces the validator |
| `gzh-draft-publisher` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | authored in the private workflow | core publish-to-draft stage | ALLOWED — owner copyright asserted | keep |
| `gzh-editorial-review` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | authored in the private workflow | canonical core stage | ALLOWED — owner copyright asserted | keep |
| `gzh-sticker-assets` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | authored in the private workflow | canonical core stage | ALLOWED — owner copyright asserted | keep |
| `gzh-title-seo` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | authored in the private workflow | canonical core stage | ALLOWED — owner copyright asserted | keep |
| `gzh-topic-research` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | authored in the private workflow | canonical core stage | ALLOWED — owner copyright asserted | keep |
| `gzh-visual-assets` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | authored in the private workflow | core visual assets stage | ALLOWED — owner copyright asserted | keep |
| `gzh-visual-director` | OWNED_AND_CLEARED | private gzh workflow (WeChat Matrix Team) | local | authored in the private workflow | canonical core stage | ALLOWED — owner copyright asserted | keep |
| `khazix-writer` | RIGHTS_UNKNOWN | third-party creator style (数字生命卡兹克) | unknown | none found | optional writing style | HOLD — no permission evidence | exclude or obtain permission |
| `midu-proofread` | RIGHTS_UNKNOWN | calls `api.midu.com`; no author/licence | 1.0.0 | none found | optional proofreading | HOLD — no licence evidence | exclude or obtain permission |
| `obsidian` | RIGHTS_UNKNOWN | obsidian-cli wrapper; homepage help.obsidian.md | 1.0.0 | none found | optional note automation | HOLD — no licence evidence | exclude or obtain permission |
| `opc-conversion-loop` | OWNED_AND_CLEARED | OPC internal methodology | local | no third-party marker; supporting registry entry | supporting strategy | ALLOWED — owner copyright asserted | keep |
| `read-arxiv-paper` | RIGHTS_UNKNOWN | no author/source/licence | unknown | none found | optional research | HOLD — no licence evidence | exclude or obtain permission |
| `source-evidence-layer` | OWNED_AND_CLEARED | local evidence layer | local | no third-party marker; supporting registry entry | supporting evidence | ALLOWED — owner copyright asserted | keep |
| `vision` | RIGHTS_UNKNOWN | multi-provider wrapper (Agnes/Doubao/Qwen/OpenAI) | unknown | none found | supporting visual review | HOLD — no licence evidence | exclude or obtain permission; local `visual_qa` remains |
| `wechat-card-qrcode` | OWNED_AND_CLEARED | WeChat Matrix Team | local | authored in the private workflow | supporting card render | ALLOWED — owner copyright asserted | keep |
| `wechat-cover` | OWNED_AND_CLEARED | WeChat Matrix Team | local | authored in the private workflow | supporting cover | ALLOWED — owner copyright asserted | keep |
| `wechat-publisher` | RIGHTS_UNKNOWN | based on wenyan-cli; no author/licence | 0.1.0 | none found | alternative publisher; core uses `gzh-draft-publisher` | HOLD — no licence evidence | exclude or obtain permission |
| `wechat-seo-optimizer` | OWNED_AND_CLEARED | WeChat Matrix Team | local | authored in the private workflow | canonical core stage | ALLOWED — owner copyright asserted | keep |
| `wechat-svg-interactive` | OWNED_AND_CLEARED | WeChat Matrix Team | local | authored in the private workflow | supporting SVG compatibility | ALLOWED — owner copyright asserted | keep |
| `wechat-tts-audio` | OWNED_AND_CLEARED | WeChat Matrix Team | local | authored in the private workflow | optional audio | ALLOWED — owner copyright asserted | keep |
| `wechat-viral-topic` | RIGHTS_UNKNOWN | third-party “10万+爆款选题” skill; no author/licence | unknown | none found | optional topic research referenced by scripts | HOLD — no licence evidence | exclude or obtain permission; fail closed if absent |
| `wemp-operator` | THIRD_PARTY_LICENSE_VERIFIED | <https://github.com/gaozejie/wemp-operator> | declared MIT | MIT wrapper; no upstream source embedded | optional adapter | ALLOWED with MIT notice | keep |
| `z5-wechat-sop` | THIRD_PARTY_LICENSE_VERIFIED | <https://github.com/Z5Research/Z5-WeChat-SOP> | declared MIT | MIT wrapper; no upstream source embedded | optional adapter | ALLOWED with MIT notice | keep |
| `_archive/aws-wechat-article-assets` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | no third-party marker; deprecated alias | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-article-formatting` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | no third-party marker; deprecated alias | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-article-images` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | no third-party marker; deprecated alias | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-article-main` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | no third-party marker; deprecated alias | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-article-publish` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | no third-party marker; deprecated alias | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-article-review` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | no third-party marker; deprecated alias | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-article-topics` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | no third-party marker; deprecated alias | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-article-writing` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | no third-party marker; deprecated alias | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |
| `_archive/aws-wechat-sticker` | OWNED_AND_CLEARED | private gzh workflow (archived core alias) | local | no third-party marker; deprecated alias | archived, not dispatched | ALLOWED as archive, not dispatched | keep as provenance; never dispatch |

## Result

| Class | Count |
|---|---:|
| `OWNED_AND_CLEARED` | 26 active + 9 archived |
| `THIRD_PARTY_LICENSE_VERIFIED` | 4 |
| `RESTRICTED` | 1 (`gzh-design-skill`, AGPL-3.0) |
| `RIGHTS_UNKNOWN` | 10 |

## Publication hold

**PR #49 must not merge as-is.** Two findings block public release:

1. **AGPL-3.0.** `gzh-design-skill` is the core HTML validator and is licensed
   **AGPL-3.0**, not MIT. The full licence text is present, so the component is
   redistributable under AGPL, but the repository's own licence decision (#11) and
   the AGPL network-use obligations are an owner decision. Do not describe it as
   permissive.
2. **Ten `RIGHTS_UNKNOWN` skills.** `arxiv-search`, `deep-research`,
   `exa-web-search-free`, `khazix-writer`, `midu-proofread`, `obsidian`,
   `read-arxiv-paper`, `vision`, `wechat-publisher`, `wechat-viral-topic`. They
   must be excluded from the public import, replaced, or cleared by the owner.
   Several are optional; removal must fail closed, not silently fall back.

The vendor tree is already on the public PR branch. A new commit that removes
files does **not** remove them from the branch history. A history rewrite or a
repository visibility change requires explicit owner authorisation; this audit
performs neither.

## Corrected provenance

- Remote: private, alive, `main e9303d1`, tree `7b75e4e8` — identical to the
  vendored tree.
- Imported commit: `93645f1` (not on the remote). Its commit identity is lost; its
  tree is preserved.
- Local checkout `D:\Projects\gzh_x未来智能` and local bundle
  `D:\Archives\repos\gzh-thinktank\2026-10-30\gzh-thinktank.bundle`: absent.
- The earlier `MANIFEST.md` claim that the remote was deleted and returned 404 was
  false and has been corrected.
