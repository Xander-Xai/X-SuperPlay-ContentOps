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
| `arxiv-search` | RIGHTS_UNKNOWN | no author/source/licence in `SKILL.md` | unknown | none found | optional research; not in registry | HOLD — no licence evidence | exclude from public import or obtain permission |
| `beautiful-mermaid` | THIRD_PARTY_LICENSE_VERIFIED | Alex (LICENSE) | local copy | MIT LICENSE in directory; `package.json` says ISC (discrepancy) | core diagram rendering | ALLOWED with MIT notice | keep LICENSE; resolve ISC/MIT with upstream |
| `content-humanizer` | OWNER_ATTESTED | private gzh workflow (Matrix Ops) | local | `THIRD_PARTY_NOTICES.md` owner attestation: local rewritten methodology; no independent file-level provenance | supporting copy | HOLD — owner attestation only; independent evidence required for public release | keep |
| `content-production` | OWNER_ATTESTED | private gzh workflow (Matrix Ops) | local | `THIRD_PARTY_NOTICES.md` owner attestation: local rewritten methodology; no independent file-level provenance | supporting copy | HOLD — owner attestation only; independent evidence required for public release | keep |
| `content-repurposer` | OWNER_ATTESTED | private gzh workflow; generic description | local | `THIRD_PARTY_NOTICES.md` owner attestation: local rewritten methodology; no independent file-level provenance | supporting copy | HOLD — owner attestation only; independent evidence required for public release | keep; owner may re-review if upstream is identified |
| `content-strategy` | OWNER_ATTESTED | private gzh workflow (Matrix Ops) | local | `THIRD_PARTY_NOTICES.md` owner attestation: local rewritten methodology; no independent file-level provenance | supporting strategy | HOLD — owner attestation only; independent evidence required for public release | keep |
| `deep-research` | RIGHTS_UNKNOWN | no author/source/licence; 13-agent pipeline | unknown | none found | optional research | HOLD — no licence evidence | exclude or obtain permission |
| `exa-web-search-free` | RIGHTS_UNKNOWN | Exa MCP wrapper; no author/licence | unknown | none found | optional search adapter referenced by scripts | HOLD — no licence evidence | exclude or obtain permission; fail closed if absent |
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
| `khazix-writer` | RIGHTS_UNKNOWN | third-party creator style (数字生命卡兹克) | unknown | none found | optional writing style | HOLD — no permission evidence | exclude or obtain permission |
| `midu-proofread` | RIGHTS_UNKNOWN | calls `api.midu.com`; no author/licence | 1.0.0 | none found | optional proofreading | HOLD — no licence evidence | exclude or obtain permission |
| `obsidian` | RIGHTS_UNKNOWN | obsidian-cli wrapper; homepage help.obsidian.md | 1.0.0 | none found | optional note automation | HOLD — no licence evidence | exclude or obtain permission |
| `opc-conversion-loop` | OWNED_AND_CLEARED | OPC internal methodology | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | supporting strategy | ALLOWED — Git authorship evidence | keep |
| `read-arxiv-paper` | RIGHTS_UNKNOWN | no author/source/licence | unknown | none found | optional research | HOLD — no licence evidence | exclude or obtain permission |
| `source-evidence-layer` | OWNED_AND_CLEARED | local evidence layer | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | supporting evidence | ALLOWED — Git authorship evidence | keep |
| `vision` | RIGHTS_UNKNOWN | multi-provider wrapper (Agnes/Doubao/Qwen/OpenAI) | unknown | none found | supporting visual review | HOLD — no licence evidence | exclude or obtain permission; local `visual_qa` remains |
| `wechat-card-qrcode` | OWNED_AND_CLEARED | WeChat Matrix Team | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | supporting card render | ALLOWED — Git authorship evidence | keep |
| `wechat-cover` | OWNED_AND_CLEARED | WeChat Matrix Team | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | supporting cover | ALLOWED — Git authorship evidence | keep |
| `wechat-publisher` | RIGHTS_UNKNOWN | based on wenyan-cli; no author/licence | 0.1.0 | none found | alternative publisher; core uses `gzh-draft-publisher` | HOLD — no licence evidence | exclude or obtain permission |
| `wechat-seo-optimizer` | OWNED_AND_CLEARED | WeChat Matrix Team | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | canonical core stage | ALLOWED — Git authorship evidence | keep |
| `wechat-svg-interactive` | OWNED_AND_CLEARED | WeChat Matrix Team | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | supporting SVG compatibility | ALLOWED — Git authorship evidence | keep |
| `wechat-tts-audio` | OWNED_AND_CLEARED | WeChat Matrix Team | local | Git author yandexuanxuan/Xander-Xai in the private repo; no third-party marker | optional audio | ALLOWED — Git authorship evidence | keep |
| `wechat-viral-topic` | RIGHTS_UNKNOWN | third-party “10万+爆款选题” skill; no author/licence | unknown | none found | optional topic research referenced by scripts | HOLD — no licence evidence | exclude or obtain permission; fail closed if absent |
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
| `THIRD_PARTY_LICENSE_VERIFIED` | 4 |
| `RESTRICTED` | 1 (`gzh-design-skill`, AGPL-3.0) |
| `OWNER_ATTESTED` | 4 |
| `RIGHTS_UNKNOWN` | 10 |

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

## Call-chain analysis — `RIGHTS_UNKNOWN`

| Skill | Call site | If absent | Failure mode |
|---|---|---|---|
| `arxiv-search` | none found | unused | safe to exclude |
| `deep-research` | `skills/skill-registry.yaml:159` optional | only fails when explicitly requested | must resolve to `BLOCKED`, never a fallback |
| `exa-web-search-free` | `scripts/route_content.py:123` allowed `selected_skill` | hotspot route could name a missing skill | remove from the allowed set or reject the route |
| `khazix-writer` | none found | unused | safe to exclude |
| `midu-proofread` | none found | unused | safe to exclude |
| `obsidian` | none found | unused | safe to exclude |
| `read-arxiv-paper` | none found | unused | safe to exclude |
| `vision` | no skill-path reference; `vision-review.json` is a local artifact | unused as a skill | safe to exclude; local visual QA remains |
| `wechat-publisher` | `scripts/test_post_publish_registry.py:11`, `skill-registry.yaml:225` | only the fallback publisher fails | core uses `gzh-draft-publisher`; requested fallback must `BLOCKED` |
| `wechat-viral-topic` | `scripts/route_content.py:122` allowed `selected_skill` | a hotspot route could name a missing skill | remove from the allowed set or reject the route |

None of the ten is a canonical required stage. Two are allowed values in
`route_content.py`; excluding them requires updating that allowlist so the route
fails closed instead of selecting a missing skill. The other eight are
unreferenced or optional.

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

- Remote: private, alive, `main e9303d1`, tree `7b75e4e8` — the same full tree
  object as the imported commit; the vendored copy is a filtered subset.
- Imported commit: `93645f1` (not on the remote). Its commit identity is lost; its
  tree is preserved.
- Local checkout `D:\Projects\gzh_x未来智能` and local bundle
  `D:\Archives\repos\gzh-thinktank\2026-10-30\gzh-thinktank.bundle`: absent.
- The earlier `MANIFEST.md` claim that the remote was deleted and returned 404 was
  false and has been corrected.