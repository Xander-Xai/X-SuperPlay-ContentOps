# Legacy clone retirement — `Easel/` (2026-11-16)

> Status: executed. Authorised by the Founder on 2026-11-16 ("如果正确换了底座，那就删除").
> Scope: one gitignored directory in the checkout. No tracked file was removed by the
> deletion itself; the documentation that referred to it was corrected in the same change.

## What the directory was

| Property | Value |
|---|---|
| Path | `D:\Projects\X-SuperPlay-ContentOps\Easel` |
| Size | 2.2 GB |
| Git state | its own clone, HEAD `4b9c03cf2129b6155595b66fc1e604546a3aa4ad` (24 commits past v0.2.1) |
| Tracked by this repository | no — `.gitignore` has ignored it since 2026-11-01 |
| Accepted by `scripts/resolve_easel.py` | no — the resolver only accepts the registered root |
| Code referencing it | none: `grep -rn "Easel/" scripts src` has no business hit |
| Production engine actually in use | `.runtime/easel-v030` (v0.3.0, `bb3c8ff`) |

## Why it was retired

It was a shallow working copy left over from the v0.2.1 era. It produced no artefact, no
receipt and no call. Keeping it made the answer to "where is the engine?" ambiguous for
every later reader, and it is the kind of residue that AGENTS §10 exists to prevent.

## What was checked before deleting

Its two uncommitted modifications were the only thing that could have been unique. They are
an **earlier revision of tuning this repository already owns**:

| Path in the clone | Corresponding repository file | Verdict |
|---|---|---|
| `skills/openclaw/video-script/SKILL.md` (+15 lines) | `extensions/easel-workbench/skills/builtin/video-script/SKILL.md` | superseded — the repository copy is the later revision (it points at the account DNA as the source of numbers instead of hard-coding 220 cpm, 45–60 s, and the CTA text) |
| `skills/openclaw/video-script/references/benchmark-playbook.md` (untracked) | `extensions/easel-workbench/skills/builtin/video-script/references/benchmark-playbook.md` | superseded — same content, later revision with the credibility note about the transcripts not being in the repository |

Nothing was salvaged because nothing was unique. The diff was read in full before the
decision; the only differences are the improvements already present in the repository copy.

## Engine-swap evidence at the moment of deletion

Both commands were run on 2026-11-16 before the directory was removed:

| Check | Result |
|---|---|
| `python scripts/verify_easel_runtime.py --overlay --json` | `VERIFIED` — 1071 baseline blobs, 14 declared overlay files, 0 mismatches, 0 extras, license Apache-2.0 |
| `python scripts/resolve_easel.py` | `OK` — `engine_id=v0.3.0`, `commit=bb3c8ff…`, `verification=upstream_overlay_and_generated_profiles` |
| `projects/m5-easel-pin` render on v0.3.0 | QC PASS; output sha256 identical to the v0.2.1 render (recorded in the project receipt) |
| `python tests/test_easel_workbench_overlay.py` | 46/46 |

## What was not deleted

`.runtime/easel` (v0.2.1, `role: rollback`) stays: it is the only rollback tree and it is
registered. Its retention deadline is a separate Founder decision (foundation PRD §9.3).

## How it was removed

```bash
cmd /c rmdir /s /q "D:\Projects\X-SuperPlay-ContentOps\Easel"
```

`Remove-Item -Recurse` was avoided deliberately: on Windows PowerShell 5.1 it follows
directory junctions into their targets, and one wrong path there deletes the archive.
