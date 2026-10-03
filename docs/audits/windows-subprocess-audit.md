# Windows Subprocess Audit

> Issue: #16 — [G0.7] Eliminate Windows console popup flashes before M2.0
> Branch: `chore/16-windows-no-console-popup`
> Base: `main` @ `51d875d`
> Method: `git grep -nE "subprocess\.(run|Popen|call|check_call|check_output)|os\.system|os\.popen"` over all tracked `*.py`, then manual inspection of every hit.
> Every line number below was read from the file, not estimated.

[English](windows-subprocess-audit.md) | [简体中文](windows-subprocess-audit.zh-CN.md)

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
| `interactive_run` → `subprocess.run` | EXEMPT_WITH_REASON | Deliberately **visible with inherited stdio**; suppressing the window or piping the streams would break `gh auth login` / `mmx auth login` |
| `interactive_run_captured` → `subprocess.run` | EXEMPT_WITH_REASON | Explicit opt-in for visible **and** captured, kept separate so the auth default is never weakened |

### scripts/check_subprocess_policy.py

Added by this issue. Uses `ast` only — no `subprocess` calls of its own. Detection is
semantic, not textual: imports are resolved into a symbol table before any call is
judged, so no alias can hide a violation (see "Policy gate coverage" below).

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

## Interactive semantics

`interactive_run()` exists so a human can complete a flow, so it inherits the parent
terminal rather than capturing it:

| Property | Value | Why |
|---|---|---|
| Console | visible | The user has to see the prompt |
| `CREATE_NO_WINDOW` | never passed | Would allocate nothing to interact with |
| `SW_HIDE` | never passed | Would hide the session |
| `stdin` | inherited | The user has to type into it |
| `stdout` | inherited | Output appears in the user's terminal live |
| `stderr` | inherited | Prompts and errors stay visible |
| `capture_output` | never passed by default | Piping would make the prompt unreachable |

`interactive_run_captured()` is the separate, explicitly named variant for the rare
case that needs a visible window *and* a recorded transcript. The interactive auth
default is never changed to serve it.

Tests assert this semantically: the `subprocess.run` call inside `interactive_run` is
parsed with `ast` and must carry none of `capture_output`, `stdout`, `stderr`,
`stdin`, `startupinfo`, `creationflags`, nor a `**kwargs` splat that could smuggle
any of them in. No `PIPE`/`DEVNULL` reference is permitted in the function body.

## Shell classification

A shell is only interactive when launched **bare**. Used as a tool it is background
work, so it must be hidden like any other child process.

| Invocation | Class | Reason |
|---|---|---|
| `powershell` / `pwsh` / `cmd` / `bash` / `sh` (no args) | INTERACTIVE_VISIBLE | Opens a prompt the user drives |
| `powershell -Command ...` / `-EncodedCommand` / `-NonInteractive -Command` | BACKGROUND_HIDDEN | Runs a payload and exits |
| `pwsh -NoProfile -Command ...` | BACKGROUND_HIDDEN | Same, with modifiers first |
| `cmd /c ...` | BACKGROUND_HIDDEN | Executes and exits |
| `cmd /k ...` | INTERACTIVE_VISIBLE | Keeps the prompt open |
| `bash -c ...` / `sh -c ...` / `bash -lc ...` | BACKGROUND_HIDDEN | Combined short flags count as run-and-exit |
| `bash script.sh` / `powershell script.ps1` / `cmd some.exe` | BACKGROUND_HIDDEN | Runs a script or program |

`.exe` suffixes and full paths are normalised, so `pwsh.exe` and
`C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe` classify identically.
Classification looks at the executable **and** its arguments; the alias `sp` proves
nothing because no name is trusted.

## Policy gate coverage

Resolution is per-file and import-aware, so these all fail CI:

| Source | Resolved |
|---|---|
| `import subprocess` / `as proc` / `as anything` | `subprocess` / `proc` / `anything` |
| `from subprocess import run` / `run as execute` / `Popen` | `run` / `execute` / `Popen` |
| `import os as operating_system` | `operating_system` |
| `from os import system` / `popen as pipe` | `system` / `pipe` |
| `import os.path as osp` | `osp` |
| `from subprocess import *` | flagged: bindings become unprovable |
| `asyncio.create_subprocess_exec` / `create_subprocess_shell` | flagged, so an async provider cannot bypass the gate later |
| nested-scope and multi-name imports | flagged |

Inert references are deliberately **not** flagged: `subprocess.PIPE`,
`subprocess.DEVNULL`, `subprocess.STARTUPINFO`, `subprocess.CREATE_NO_WINDOW`,
`subprocess.SW_HIDE`, `subprocess.CompletedProcess`, `subprocess.TimeoutExpired`,
`from subprocess import PIPE, DEVNULL`, and annotations such as
`-> subprocess.CompletedProcess`. String literals, comments and docstrings cannot
trigger it.

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

---

# Phase 6/7 — measurement on real Windows hardware

Host: Windows, CPython 3.13.15, `D:\Projects\X-SuperPlay-ContentOps`.
Method: poll `EnumWindows` every 5 ms for newly visible windows whose class is
`ConsoleWindowClass`, `PseudoConsoleWindow` or `CASCADIA_HOSTING_WINDOW_CLASS`,
record the owning PID, then resolve the full PPID chain via `Win32_Process`.

## Why a plain terminal cannot prove anything

The first attempt produced `ContentOps-owned popup count = 0` for everything —
including a deliberately unhidden control. That zero was **worthless**, because
the measurement ran from an interactive shell whose parent process already owned
a console, so every console child silently inherited it and no window was ever
allocated.

A zero count is only evidence if a control proves the detector fires.

## Which parent configurations actually produce a popup

Measured, with an unhidden child:

| Parent configuration | Visible console windows |
|---|---|
| console `python.exe` | 0 — child inherits the existing console |
| `CREATE_NO_WINDOW` parent | 0 — child runs without a console |
| **`DETACHED_PROCESS` parent** | **2 — popup** |
| **`pythonw.exe` (GUI) parent** | **2 — popup** |

The last row is the real-world case: an IDE or Claude Code has no console, so any
console child it starts allocates a fresh visible window.

## Harness artifact, and how it was removed

Under `DETACHED_PROCESS` the harness itself produced 2 windows, because
`python.exe` + `DETACHED_PROCESS` allocates its own detached console. A `NOOP`
arm (detached worker that spawns nothing) measured that artifact at exactly 2
windows, so every treatment arm was corrected by subtracting it:

```
NOOP baseline (detached, spawns nothing)   : 2
unhidden control                           : 2   -> 0 attributable to the child
hidden cmd / ffmpeg / ffprobe / git / python: 2 each -> 0 attributable to the child
```

The `pythonw.exe` arm needs no correction: its `NOOP` baseline is 0.

## Result — `pythonw.exe` GUI parent, real ContentOps commands

Control first, to prove the detector:

| Command | rc | Visible console windows |
|---|---|---|
| **CONTROL** raw `subprocess.run` (no suppression) | 0 | **2** |
| `scripts/doctor.py` | 0 | 0 |
| `scripts/check_docs.py` | 0 | 0 |
| `scripts/check_repo_policy.py` | 0 | 0 |
| `scripts/check_subprocess_policy.py` | 0 | 0 |
| `git -C … ls-files` | 0 | 0 |
| `ffprobe -version` | 0 | 0 |
| `ffmpeg -version` | 0 | 0 |
| `tests/test_windows_subprocess.py` | 0 | 0 |
| `tests/test_windows_paths.py` | 0 | 0 |
| `scripts/test_basic.py` | 0 | 0 |
| `scripts/dev_check.py` | 0 | 0 |

**ContentOps-owned popup count = 0.**

The control reproducing 2 windows while all eleven real commands produce 0 is the
proof: the condition is real, and suppression removes it.

## Phase 7 — residual popup attribution

No ContentOps popup remained, so nothing needed attributing. For the record, the
attribution rule that would have been applied is implemented as ancestor-chain
classification: walk PPID to the root, then label `CONTENTOPS_OWNED` if any
ancestor is `python.exe`/`git.exe`/`ffmpeg.exe`/`ffprobe.exe`/`node.exe`/`gh.exe`,
or `UPSTREAM_CLAUDE_WINDOWS_POPUP` if any ancestor is `claude.exe`/`bash.exe`/
`cmd.exe`/`powershell.exe`/`WindowsTerminal.exe`.

One caveat found while measuring: the two control windows both resolved to an
owner that had already exited by the time WMI was queried, so live attribution of
a short-lived popup needs the observer to sample faster than the child lives.
That does not affect the zero result, which relies on absence rather than
attribution.

---

# Phase 9 — WSL2 validation

Host: Ubuntu-22.04 on WSL2, kernel 6.6.87.2-microsoft-standard-WSL2,
CPython 3.10.12, git 2.34.1.

## Correctness on Linux

The window-suppression path must be a strict no-op off Windows, so POSIX
behaviour is unchanged:

- `os.name == "posix"` → `_get_hidden_kwargs()` returns `{}`, no `startupinfo`,
  no `creationflags`.
- `hidden_run` / `hidden_popen` execute normally.
- Interactive/background classification is identical to Windows.
- Full suite passes: policy gate, 32 subprocess regression tests, Windows path
  tests, `test_basic.py`, `check_docs.py`, `check_i18n.py`,
  `check_repo_policy.py`, and `dev_check.py`.

### One real bug found here

`scripts/doctor.py --json` crashed with
`FileNotFoundError: [Errno 2] No such file or directory: 'node'` on any host
without `node`. `_check_node()` lacked both the `shutil.which()` guard and the
`try/except` that `_check_tool()` already had. Verified pre-existing by
reproducing it on `main` @ `51d875d` with these changes stashed. Fixed in this
branch, because it blocked the WSL2 validation path.

## /mnt/d performance — measured, and not acceptable

| Metric | `/mnt/d` (DrvFs) | `~/projects` (ext4) | Ratio |
|---|---|---|---|
| file create+read+delete | 61.7 ops/sec | 16401.9 ops/sec | **266x** |
| `dev_check.py` full gate | 124.18 s | 1.66 s | **75x** |

On `/mnt/d`, `tests/test_windows_paths.py` fails: `dev_check --quick` exceeds the
60 s cap that the path test imposes, purely on I/O latency.

### Recommendation

Use an **ext4 working tree** for WSL development:

```
~/projects/X-SuperPlay-ContentOps
```

Verified: the full suite passes there and `dev_check` completes in 1.66 s. Keep
`/mnt/d` for the Windows-side checkout and for large video assets and outputs,
syncing between them as needed. Working directly on `/mnt/d` from WSL costs
75x on the developer gate and makes a legitimate test fail on timing alone.

---

# Phase 10 — binding rule for the MiniMax provider (Issue #4, M2.0)

Provider integration inherits this policy automatically, because
`scripts/check_subprocess_policy.py` runs in CI. A bare
`subprocess.run(["mmx", ...])` anywhere outside `scripts/process_utils.py` fails
the build; the gate does not need to know what `mmx` is.

Classification is already encoded in `is_interactive_command()`:

| Command | Class | Entry point |
|---|---|---|
| `mmx auth login` | INTERACTIVE_VISIBLE | `interactive_run()` |
| `mmx quota` | BACKGROUND_HIDDEN | `hidden_run()` |
| `mmx image` | BACKGROUND_HIDDEN | `hidden_run()` |
| `mmx speech` | BACKGROUND_HIDDEN | `hidden_run()` |
| `mmx video` | BACKGROUND_HIDDEN | `hidden_run()` |
| `mmx video task get` | BACKGROUND_HIDDEN | `hidden_run()` |

Child interpreters must use `python_executable()`; the bare string `"python"` is
not permitted, and `process_utils.py` itself is asserted to contain none.

## Verification commands

```
python scripts/test_basic.py
python tests/test_windows_subprocess.py
python tests/test_windows_paths.py
python scripts/check_subprocess_policy.py
python scripts/dev_check.py
git diff --check
```