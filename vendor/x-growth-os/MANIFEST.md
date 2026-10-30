# vendor/x-growth-os — imported, pinned, never edited

The X platform track's workflow: one operating manual (docs, prompts, post
drafts, CSV metric templates) and one read-only analytics script. It was not
written here and it is not maintained here.

## Provenance

| Item | Value |
|---|---|
| Repository | `https://github.com/Xander-Xai/X-SuperPlay-X-Growth-OS.git` |
| Visibility | private, owned by the same person as this repository |
| Branch / commit | `main` / `3154db49ad2b070bf5dea2d8fb9a1fc4fdba6f44` |
| Commit subject | `ci(x): make URL integrity checks valid after real publish receipts arrive` |
| Tree | `a19584f16d0cb26f231e554646358f1307bb012e` |
| Files / bytes | 64 / 345,872 (blob bytes, LF) |
| Imported | 2026-10-30 |
| License | **ABSENT** — the source repository declares none. Nothing here is a grant of rights. |
| Source repository | **DELETED 2026-10-30.** The remote was retired after its content, its two unmerged branches and its history were moved into this repository. The cold copy is a verified bundle: `D:\Archives\repos\x-growth-os\2026-10-30\x-growth-os.bundle` (all refs, complete history, SHA-256 `27b901a3b458baa55629bbcc87ff336f4c9bd9fd506f2afc195116ba65c044ca`), with the refs and commits recorded in the `INDEX.md` beside it. |

The pin below still describes this tree exactly, because the tree was not edited
when the remote went away. What the pin cannot describe is the history the remote
held after `3154db49`: one governance commit on `main` and the two unmerged
content branches. Both were carried into `projects/x-growth-en/` before the
deletion, and the bundle holds them in full.

## What was not excluded

Nothing. The whole tree is 64 text files — Markdown, Python, CSV, SVG — with no
`node_modules`, no virtualenv, no build output, no media and no credential-shaped
file. That is why the import is a straight copy: an exclusion would have meant a
file existed that could not be accounted for.

Audited at import, all clean:

| Check | Result |
|---|---|
| C0 control bytes in `.md`/`.py`/`.csv`/`.svg` | 0 |
| `subprocess` / `os.system` / `os.popen` in `.py` | 0 |
| credential-shaped filenames (`.env`, `*.key`, `*.pem`, cookie/secret) | 0 |
| files over 5 MiB (`check_repo_policy.py`'s limit) | 0 |

## Rule: do not edit

A change to this tree is a **new import with a new digest**, recorded in
`scripts/x_growth_pin.py`. Editing a file in place would make the copy disagree
with the pin and with the commit it claims to be — the pin exists precisely to
make that visible.

`MANIFEST.md` (this file) is ours, not upstream's, and is excluded from the
digest so that improving these notes does not look like an edit to vendored code.

## The digest

```text
SHA-256 over, for each file in sorted order and excluding MANIFEST.md,
__pycache__ and *.pyc:
    relative/posix/path \0 sha256(file bytes) \n
```

Pinned value: `4a99c01ebb6515ebce9d861e7b2d8b0dd1dd43abfcdef43ad1a1afbf620a0674`

```powershell
python scripts/x_growth_pin.py            # 0 only when files, bytes and digest agree
python scripts/x_growth_pin.py --checkout D:\Temp\x-growth-os   # also verify a clone
```

## The vendored test suite is not run by CI

`scripts/run_tests.py` discovers suites under `tests/` only, so
`vendor/x-growth-os/tests/test_x_growth_report.py` is **not** executed by
`dev_check`, by `run_tests.py`, or on CI. To run it:

```powershell
python -m unittest discover -s vendor/x-growth-os/tests -p "test_x_growth_report.py"
```

That is deliberate: the suite is upstream's, it is pinned by digest above, and
running it produces `__pycache__` inside the tree (which the digest ignores).

## The two delivery gates this tree states in prose

| Vendored document | What it requires | Enforced here by |
|---|---|---|
| `docs/POST-IMAGE-DELIVERY-GATE.md` | English copy ≤280 weighted chars each; an actual 1600×900 PNG/JPEG (SVG alone is not sufficient); ALT text; `post_status` ∈ {draft, scheduled, published, failed}; never `published` without a real status URL | `src/contentops/publish/x_post.py` |
| `docs/EDITORIAL-QUALITY-GATE.md` | three genuinely different theses; red-team pass; six 0–5 dimensions, ≥24/30 with novelty, evidence and mechanism each ≥4; recovery fields `audience_job`, `proof_grade` P0–P3, `unique_artifact_ref`, `experiment_variable` | `src/contentops/publish/x_editorial.py` |

The prose is the source of truth for *what* the gates mean. The code is the
enforcement. Where the two disagree, the code is wrong and this file should say
which one changed.
