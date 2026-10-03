# Windows Subprocess Audit

> Issue: #16 — [G0.7] Eliminate Windows console popup flashes before M2.0
> Branch: `chore/16-windows-no-console-popup`
> Base: `main` @ `51d875d`
> Method: `git grep -nE "subprocess\.(run|Popen|call|check_call|check_output)|os\.system|os\.popen"` over all tracked `*.py`, then manual inspection of every hit.
> Every line number below was read from the file, not estimated.

## Scope

Tracked Python sources only. `Easel/`, `.runtime/` and `.env` are gitignored and out of scope.

`projects/easel-review/` **is tracked** (40 files) and therefore **in scope**. A previous
draft of this audit wrongly excluded it as "gitignored"; that was incorrect and the
files below are included.

Files with **zero** subprocess callsites (verified, no action needed):

| File | Note |
|---|---|
| `scripts/check_easel_upstream.py` | Uses `urllib.request` only; `subprocess` appears solely as a keyword string in an upstream scan list (line 35) |
| `scripts/check_i18n.py` | Pure stdlib text scan |
| `scripts/new_project.py` | Pure file writes |

## Classification model

| Class | Meaning |
|---|---|
| `BACKGROUND_HIDDEN` | Must run with zero visible console window on Windows |
| `INTERACTIVE_VISIBLE` | Must keep console visible (user-facing auth, manual debug) |
| `EXEMPT_WITH_REASON` | Deviates from the helper by necessity, with a stated reason |

## Baseline finding

On `main` @ `51d875d`, `scripts/process_utils.py` already existed with `hidden_run()`,
`interactive_run()`, `_get_hidden_kwargs()`, `_is_debug_visible()` and
`is_background_command()` — and `tests/test_windows_subprocess.py` already passed.

**But zero production code imported it.** All 34 callsites used raw `subprocess.run`
with no `CREATE_NO_WINDOW` and no `STARTF_USESHOWWINDOW`/`SW_HIDE`. The helper was
dead code: green tests, zero effect. This is exactly the "helper tests pass but real
callers bypass the helper" failure mode, and it is the primary reason popups occurred.

`hidden_popen()` did not exist.

## Inventory — 34 callsites, all `BACKGROUND_HIDDEN`

### scripts/assemble_easel.py

| Line | Command | Class | Note |
|---|---|---|---|
| 205 | `[sys.executable, upstream_assemble, "assemble", ...]` | BACKGROUND_HIDDEN | Already uses `sys.executable`; timeout 1800 |
| 235 | `["ffmpeg", ...]` subtitle burn | BACKGROUND_HIDDEN | timeout 900 |

### scripts/check_docs.py

| Line | Command | Class | Note |
|---|---|---|---|
| 214 | `["git", "-C", ROOT, "ls-files"]` | BACKGROUND_HIDDEN | Read-only listing |

### scripts/check_repo_policy.py

| Line | Command | Class | Note |
|---|---|---|---|
| 40 | `["git", "-C", ROOT, "ls-files"]` | BACKGROUND_HIDDEN | Read-only listing |

### scripts/dev_check.py

| Line | Command | Class | Note |
|---|---|---|---|
| 30 | generic `cmd` runner | BACKGROUND_HIDDEN | Dispatches the whole check matrix |

### scripts/doctor.py

| Line | Command | Class | Note |
|---|---|---|---|
| 44 | `[name, *version_args]` tool version probe | BACKGROUND_HIDDEN | Probes python/git/ffmpeg/gh |
| 88 | `["node", "--version"]` | BACKGROUND_HIDDEN | |

### scripts/qc_video.py

| Line | Command | Class | Note |
|---|---|---|---|
| 42 | `["ffmpeg", ..., "volumedetect"]` | BACKGROUND_HIDDEN | Reads results from **stderr** |
| 67 | `["ffprobe", ..., "-print_format", "json"]` | BACKGROUND_HIDDEN | |
| 162 | `["ffmpeg", ..., "rawvideo", "gray"]` | BACKGROUND_HIDDEN | Multi-frame sampling loop |

### scripts/qc_visual.py

| Line | Command | Class | Note |
|---|---|---|---|
| 33 | `["ffprobe", ..., "-show_format"]` | BACKGROUND_HIDDEN | |
| 44 | `["ffmpeg", ..., scale=...]` thumbnail | BACKGROUND_HIDDEN | |
| 55 | `["ffmpeg", ..., "rawvideo", "gray", "-"]` | BACKGROUND_HIDDEN | **Binary stdout** — no `text=True`; requires `text=False` passthrough |
| 91 | `["ffmpeg", "-y"] + inputs + filter_complex` | BACKGROUND_HIDDEN | Layout composition |

### scripts/resolve_easel.py

| Line | Command | Class | Note |
|---|---|---|---|
| 66 | `["git", "-C", path, *args]` | BACKGROUND_HIDDEN | Shared git read helper |
| 215 | `["git", "clone", "--depth", "1", ...]` | BACKGROUND_HIDDEN | Network, timeout 600 |
| 238 | `["gh", "api", .../tarball/...]` | BACKGROUND_HIDDEN | **`stdout=<file handle>`**, `stderr=PIPE`; requires stdout passthrough |

### scripts/run_v1.py

| Line | Command | Class | Note |
|---|---|---|---|
| 50 | `["ffprobe", ..., json]` | BACKGROUND_HIDDEN | |
| 131 | PowerShell TTS (`ps_cmd`) | BACKGROUND_HIDDEN | Shell *interpreter* as a tool, not `shell=True` |
| 140 | `["espeak", ...]` | BACKGROUND_HIDDEN | No `text=True`; binary-capable |
| 170 | `["ffmpeg", ..., image fit]` | BACKGROUND_HIDDEN | |
| 186 | `["ffmpeg", ..., drawtext]` title card | BACKGROUND_HIDDEN | |
| 199 | `["ffmpeg", ..., concat]` | BACKGROUND_HIDDEN | timeout 600 |
| 293 | `[sys.executable, tts_script, "speak", ...]` | BACKGROUND_HIDDEN | Already `sys.executable` |
| 414 | `["ffmpeg", ..., stillimage]` shot segment | BACKGROUND_HIDDEN | |

### scripts/test_basic.py

| Line | Command | Class | Note |
|---|---|---|---|
| 17 | `[PYTHON, *args]` test runner | BACKGROUND_HIDDEN | `PYTHON = sys.executable` |
| 128 | `["git", "-C", easel, *a]` (inside a `lambda`) | BACKGROUND_HIDDEN | Must become a `def` to pass kwargs cleanly |

### scripts/verify_easel_runtime.py

| Line | Command | Class | Note |
|---|---|---|---|
| 70 | `["gh", "api", .../git/trees/...]` | BACKGROUND_HIDDEN | |
| 102 | `["gh", "api", .../git/ref/tags/...]` | BACKGROUND_HIDDEN | |
| 113 | `["gh", "api", .../git/tags/...]` | BACKGROUND_HIDDEN | Annotated-tag peel |

### tests/test_windows_paths.py

| Line | Command | Class | Note |
|---|---|---|---|
| 24 | `args` test runner | BACKGROUND_HIDDEN | Spawns child interpreters |

### projects/easel-review/scripts/capture_evidence.py

| Line | Command | Class | Note |
|---|---|---|---|
| 86 | `["ffmpeg", ..., lavfi color]` | BACKGROUND_HIDDEN | |
| 108 | `cmd` (variable) | BACKGROUND_HIDDEN | Dynamic command list |

### projects/easel-review/scripts/gen_screenshots.py

| Line | Command | Class | Note |
|---|---|---|---|
| 49 | `cmd` (variable, ffmpeg) | BACKGROUND_HIDDEN | |

## `EXEMPT_WITH_REASON`

### scripts/process_utils.py

This file *is* the abstraction. Its direct `subprocess` use is the implementation
target, not a violation.

| Purpose | Class | Reason |
|---|---|---|
| `hidden_run` → `subprocess.run` | EXEMPT_WITH_REASON | Implementation of the hidden-window wrapper; adding hidden kwargs to itself is circular |
| `hidden_popen` → `subprocess.Popen` | EXEMPT_WITH_REASON | Same |
| `interactive_run` → `subprocess.run` | EXEMPT_WITH_REASON | Deliberately **visible**; suppressing the window would break `gh auth login` / `mmx auth login` |

### scripts/check_subprocess_policy.py

Added by this issue. Uses `ast` only — no `subprocess` calls of its own.

## `INTERACTIVE_VISIBLE`

**None required at this time.** No existing tracked callsite is user-interactive:
`gh` is used only as `gh api` (read-only, background), never `gh auth login`.

Reserved for the MiniMax provider work (Issue #4, M2.0):

| Command | Class | Reason |
|---|---|---|
| `mmx auth login` | INTERACTIVE_VISIBLE | User must type credentials / complete OAuth |
| `mmx quota` / `image` / `speech` / `video` / `video task get` | BACKGROUND_HIDDEN | Non-interactive provider calls |

Policy for all future provider code: no bare `subprocess.run(["mmx", ...])` anywhere
outside `process_utils.py`. Auth is the single permitted interactive exception.

## Non-findings

- `shell=True` appears **nowhere** in tracked Python source (only in docstrings and
  comments in `process_utils.py` / `tests/`). No migration needed; the helper now
  raises on `shell=True` to prevent regression.
- `os.system` / `os.popen` appear **nowhere** in tracked Python source.
- `subprocess.call` / `check_call` / `check_output` appear **nowhere**.

## Remediation plan

1. Extend `process_utils.py`: add `hidden_popen()`, `python_executable()`, `stdout`/
   `stderr`/`stdin` passthrough, `text=False` support, `shell=True` rejection.
2. Migrate all 34 callsites to the helper. No inline `_hidden_kwargs()` duplication —
   a single copy of the Windows flags, enforced by `check_subprocess_policy.py`.
3. Add `scripts/check_subprocess_policy.py` (AST-based) and wire into `dev_check.py`
   and CI.
4. Verify on real Windows hardware; trace any residual popup by PPID.

## Popup ownership boundary

This audit covers **ContentOps-owned** processes only. Windows consoles can also be
created by Claude Code itself (heartbeat, shell tool, IDE detection). Those are
out of ContentOps' control — ContentOps cannot patch the Claude Code binary. Any
residual popup must be attributed by PPID before further ContentOps changes are made:

- parent in `{python.exe, git.exe, ffmpeg.exe, ffprobe.exe, node.exe}` → **ContentOps-owned**, keep fixing.
- parent in `{claude.exe, bash.exe, cmd.exe, powershell.exe, WindowsTerminal.exe}` → label **UPSTREAM_CLAUDE_WINDOWS_POPUP** and stop.