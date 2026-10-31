# Third-party notices — vendored 公众号 workflow

This notice covers `vendor/gzh-thinktank/gzh_未来智能/`, a filtered, verbatim
import of the private `Xander-Xai/gzh-Future-Intelligence` repository. The
upstream tree also carries its own `THIRD_PARTY_NOTICES.md`; this file records
the distribution obligations that ContentOps must satisfy and does not replace
any licence text inside the vendored skills.

This is an engineering record, not a legal opinion. Rights decisions are in
`config/gzh-skill-rights.json` and
`reports/audits/gzh-skill-license-matrix.md`.

## AGPL-3.0 — `gzh-design-skill`

- Copyright (C) 2026 甲木 (Jiamu) × 摸鱼小李 (Moyu Xiaoli).
- Licence: GNU Affero General Public License v3.0. The full text is at
  `skills/gzh-design-skill/LICENSE`.
- The vendored directory is unmodified. It is invoked as a separate process by
  `scripts/workflow_gate.py` and `scripts/verify_draft_submission.py`; it is not
  linked into ContentOps Python.
- The Corresponding Source is this public repository plus the private upstream
  `https://github.com/Xander-Xai/gzh-Future-Intelligence`. If the workflow is
  operated as a network service, AGPL §13 requires offering this source to
  remote users; the service operator must publish that offer.
- This repository does not relicense the component. Removing it would remove the
  required HTML gate, so it is retained with the licence and source intact.

## MIT — components with a local licence file

The following directories contain the upstream MIT licence; keep the file with
the component.

| Component | Copyright |
|---|---|
| `skills/beautiful-mermaid` | Copyright (c) 2026 Alex |
| `skills/excalidraw-skill-pack` | Copyright (c) 2026 Timur Isachenko |

## MIT — components verified against an upstream repository

These local copies are adapted from, or match, the named MIT project. The MIT
permission notice below applies to each.

| Component | Upstream | Copyright |
|---|---|---|
| `skills/arxiv-search` | `https://github.com/langchain-ai/deepagents` (`libs/code/examples/skills/arxiv-search`) | Copyright (c) LangChain, Inc. |
| `skills/read-arxiv-paper` | `https://github.com/karpathy/nanochat` (`.claude/skills/read-arxiv-paper`) | Copyright (c) 2025 Andrej Karpathy |
| `skills/khazix-writer` | `https://github.com/KKKKhazix/khazix-skills` | Copyright (c) 2026 数字生命卡兹克 |
| `skills/obsidian` | `https://github.com/openclaw/openclaw` (`skills/obsidian`) | Copyright (c) 2026 OpenClaw Foundation |
| `skills/wechat-publisher` | `https://github.com/0731coderlee-sudo/wechat-publisher` | Copyright (c) 2026 Bruce Lee |
| `skills/wemp-operator` | `https://github.com/gaozejie/wemp-operator` | declared MIT; no local licence file |
| `skills/z5-wechat-sop` | `https://github.com/Z5Research/Z5-WeChat-SOP` | declared MIT; no local licence file |

`wechat-publisher` also depends on `wenyan-cli` (Apache-2.0,
`https://github.com/caol64/wenyan-cli`), which is not bundled here. Distributing
a build that includes it must carry the Apache-2.0 notice.

The `khazix-writer` licence permits reuse of the text; it does not grant a right
to present derived writing as endorsed by, or as the work of, 数字生命卡兹克.

### MIT licence text

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## CC BY-NC 4.0 — `deep-research` (blocked for commercial use)

- Upstream: `https://github.com/Imbad0202/academic-research-skills`
  (`deep-research`), Copyright (c) 2026 Cheng-I Wu.
- Licence: Creative Commons Attribution-NonCommercial 4.0 International.
- This component is **not** cleared for commercial use. It is retained only as
  vendored provenance and is blocked from dispatch by
  `config/gzh-skill-rights.json`. Obtain a commercial permission or remove it
  from the public import before enabling it.

## Held — no licence evidence

These components have no author, source or licence evidence that survives
review. They remain in the vendored tree for provenance but are blocked from
dispatch and held from public distribution until cleared:

- `content-repurposer` — identical text appears in public OpenClaw skill
  collections; the original author is not established.
- `exa-web-search-free` — OpenClaw community skill; no upstream licence found.
- `midu-proofread` — Midu API wrapper; no upstream licence found.
- `vision` — local multi-provider wrapper with no author or licence metadata;
  the owner must record an attestation or a licence.
- `wechat-viral-topic` — third-party skill mirrored without a licence; the
  original author is not established.
