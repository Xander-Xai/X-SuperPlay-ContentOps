# Rights and Receipt Exposure Audit — 2026-11-04

> Read-only audit of the archived GZH and XHS trees and of the receipts already
> on the public `main`. **No issue was closed by this report.** It corrects two
> earlier claims and records the decisions that are still required.

## 1. Scope and method

| Item | Method |
|---|---|
| GZH tree | detached checkout of `feat/content-router@5eb0bd4`; the archived `gzh-thinktank.tar.gz` working copy was also extracted |
| XHS tree | detached checkout of `feat/xhs-fa-migration@cfb7ee4` |
| Receipts | `projects/easel-enhanced-golden/receipts/founder-voice-*.json` on `main` |
| Secret scan | credential-shaped patterns (`sk-`, `ghp_`, `AKIA`, `xox`, private-key headers, JWT) over both trees and the receipt set; `scripts/check_receipt_secrets.py` |
| Values | **never printed**; only paths, types and lengths were recorded |

The extracted trees and the archived branches are untrusted data. They were
inspected read-only and no code from them was executed.

## 2. GZH tree — rights findings

| Class | Count |
|---|---:|
| `SKILL.md` entries | 50 |
| of which under `_archive/` | 9 |
| No license declaration and no license file | **45** |
| Declared `license: MIT` | 3 (`beautiful-mermaid`, `wemp-operator`, `z5-wechat-sop`) |
| MIT `LICENSE` file | 1 (`excalidraw-skill-pack`) |
| **AGPL-3.0** `LICENSE` file | 1 (`gzh-design-skill`) |
| Root `LICENSE` | none |

**Conclusion:** 45 of 50 bundled skills have no demonstrable license. The tree
cannot be redistributed from the public repository without per-skill clearance.
One AGPL-3.0 skill is a copyleft outlier even among the licensed subset.

### Provenance correction

`vendor/gzh-thinktank/MANIFEST.md` claims the original remote, checkout and
archive were deleted and that the vendored directory is "the only copy". Issue
#56 already recorded a private `Xander-Xai/gzh-Future-Intelligence` repository
that remains accessible. The "only copy" claim is therefore **overbroad and
must be corrected** before any future use. The bundle and this archive remain
the local evidence, not proof of sole custody.

## 3. XHS tree — rights findings

| Class | Count |
|---|---:|
| `SKILL.md` entries under `vendor/xhs-fa` | 47 |
| Covered by the root **Apache-2.0** `LICENSE` | 40 |
| Declared `license: MIT` | 5 |
| MIT `LICENSE` file | 1 (`humanizer-zh`) |
| **AGPL-3.0** `LICENSE` file | 1 (`guizang-social-card-skill`) |

**Correction:** the earlier "34/45 skills without an explicit license" claim
was inaccurate. The vendor root carries an Apache-2.0 `LICENSE`, and 40 skills
inherit it. The remaining questions are (a) whether that root license's scope
genuinely covers every sub-skill, and (b) the single AGPL-3.0 exception.

**Consequence:** a rights-cleared XHS subset is plausibly achievable by
excluding the AGPL skill, verifying the root license scope and preserving the
MIT notices. That is real work, not a descope.

## 4. Public receipt exposure

`main` tracks eight `founder-voice-*.json` receipts. They contain:

| Field class | Occurrences |
|---|---:|
| Account / cash / credit / voucher balances | 139 |
| Provider `voice_id` values | 13 |
| PAYG key fingerprints | 4 |
| Raw key, JWT, private-key or cloud-credential patterns | **0** |

`scripts/check_receipt_secrets.py` reports 71 pre-existing violations and an
empty growth list: its baseline explicitly allows these historical values
because a new commit cannot remove them from public history. The checker's own
documentation says the public repository already contains raw provider voice
IDs, task/trace IDs, account balances and a PAYG key fingerprint.

**What is not exposed:** no raw API key, JWT, private key or cloud credential
was found in either tree or in the receipt set.

**What is exposed:** private account balances, provider voice identifiers and a
PAYG key fingerprint, in public Git history.

## 5. Decisions still required

1. **Receipt exposure.** Choose one: (a) history rewrite plus a GitHub Support
   cache purge (destructive, invalidates clones and may not remove PR refs);
   (b) rotate the PAYG key if it is live and accept the historical balances and
   voice IDs as already public; (c) make the repository private (does not remove
   already-published history); (d) record acceptance explicitly. No option is
   chosen by this report.
2. **XHS.** Confirm the root Apache-2.0 scope, exclude `guizang-social-card-skill`
   (AGPL) and preserve the MIT notices; then decide whether to land a
   rights-cleared subset.
3. **GZH.** Decide whether to clear 45 skills individually, exclude the tree
   permanently, or replace the unlicensed skills. The tree remains unmerged.
4. **No closure.** #56 and #51 stay open until the decisions above are recorded
   and the corresponding work is done.

## 6. Statement of effect

- Issues closed: **none**.
- Files changed by the audit: none in the archived trees.
- Archives created: the four worktree snapshots and branch bundles recorded in
  `D:\Archives\contentops\2026-11\INDEX.md`.
- Values printed: none.
