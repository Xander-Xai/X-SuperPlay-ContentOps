---
translation_of: docs/audits/windows-subprocess-audit.md
language: zh-CN
translation_status: synced
---

# Windows 子进程审计

> Issue: #16 — [G0.7] 在 M2.0 之前消除 Windows 控制台弹窗闪烁
> 分支：`chore/16-windows-no-console-popup`
> 基线：`main` @ `51d875d`
> 方法：对所有 tracked `*.py` 执行 `git grep -nE "subprocess\.(run|Popen|call|check_call|check_output)|os\.system|os\.popen"`，然后逐个人工检查每一个命中点。
> 下面每一个行号都是从文件里读出来的，不是估算的。

[English](windows-subprocess-audit.md) | [简体中文](windows-subprocess-audit.zh-CN.md)

## 范围

只扫描 tracked 的 Python 源码。`Easel/`、`.runtime/` 和 `.env` 已被 gitignore，不在范围内。

`projects/easel-review/` **是 tracked 的**（40 个文件），因此**在范围内**。
本审计的上一版草稿错误地把它当作"已 gitignore"而排除；那个判断是错的，
下面的文件已包含在内。

经核实**没有**任何子进程调用点的文件（无需改动）：

| 文件 | 说明 |
|---|---|
| `scripts/check_easel_upstream.py` | 只使用 `urllib.request`；`subprocess` 仅作为上游扫描列表里的关键字字符串出现（第 35 行） |
| `scripts/check_i18n.py` | 纯标准库文本扫描 |
| `scripts/new_project.py` | 纯文件写入 |

## 分类模型

| 类别 | 含义 |
|---|---|
| `BACKGROUND_HIDDEN` | 在 Windows 上必须零可见控制台窗口 |
| `INTERACTIVE_VISIBLE` | 必须保留可见控制台（面向用户的认证、手动调试） |
| `EXEMPT_WITH_REASON` | 因必要性偏离 helper，并写明理由 |

## 基线发现

在 `main` @ `51d875d` 上，`scripts/process_utils.py` 已经存在，包含
`hidden_run()`、`interactive_run()`、`_get_hidden_kwargs()`、
`_is_debug_visible()` 和 `is_background_command()`，
而且 `tests/test_windows_subprocess.py` 已经通过。

**但没有任何生产代码 import 它。** 全部 34 个调用点都直接使用
`subprocess.run`，既没有 `CREATE_NO_WINDOW`，也没有
`STARTF_USESHOWWINDOW`/`SW_HIDE`。这个 helper 是死代码：测试全绿，效果为零。
这正是"helper 测试通过但真实调用方绕过 helper"的失效模式，
也是弹窗出现的根本原因。

`hidden_popen()` 当时并不存在。

## 清单 —— 34 个调用点，全部为 `BACKGROUND_HIDDEN`

### scripts/assemble_easel.py

| 行 | 命令 | 类别 | 备注 |
|---|---|---|---|
| 205 | `[sys.executable, upstream_assemble, "assemble", ...]` | BACKGROUND_HIDDEN | 已使用 `sys.executable`；timeout 1800 |
| 235 | `["ffmpeg", ...]` 烧录字幕 | BACKGROUND_HIDDEN | timeout 900 |

### scripts/check_docs.py

| 行 | 命令 | 类别 | 备注 |
|---|---|---|---|
| 214 | `["git", "-C", ROOT, "ls-files"]` | BACKGROUND_HIDDEN | 只读列举 |

### scripts/check_repo_policy.py

| 行 | 命令 | 类别 | 备注 |
|---|---|---|---|
| 40 | `["git", "-C", ROOT, "ls-files"]` | BACKGROUND_HIDDEN | 只读列举 |

### scripts/dev_check.py

| 行 | 命令 | 类别 | 备注 |
|---|---|---|---|
| 30 | 通用 `cmd` 执行器 | BACKGROUND_HIDDEN | 分发整个检查矩阵 |

### scripts/doctor.py

| 行 | 命令 | 类别 | 备注 |
|---|---|---|---|
| 44 | `[name, *version_args]` 工具版本探测 | BACKGROUND_HIDDEN | 探测 python/git/ffmpeg/gh |
| 88 | `["node", "--version"]` | BACKGROUND_HIDDEN | |

### scripts/qc_video.py

| 行 | 命令 | 类别 | 备注 |
|---|---|---|---|
| 42 | `["ffmpeg", ..., "volumedetect"]` | BACKGROUND_HIDDEN | 结果从 **stderr** 读取 |
| 67 | `["ffprobe", ..., "-print_format", "json"]` | BACKGROUND_HIDDEN | |
| 162 | `["ffmpeg", ..., "rawvideo", "gray"]` | BACKGROUND_HIDDEN | 多帧采样循环 |

### scripts/qc_visual.py

| 行 | 命令 | 类别 | 备注 |
|---|---|---|---|
| 33 | `["ffprobe", ..., "-show_format"]` | BACKGROUND_HIDDEN | |
| 44 | `["ffmpeg", ..., scale=...]` 缩略图 | BACKGROUND_HIDDEN | |
| 55 | `["ffmpeg", ..., "rawvideo", "gray", "-"]` | BACKGROUND_HIDDEN | **二进制 stdout** — 没有 `text=True`；需要 `text=False` 透传 |
| 91 | `["ffmpeg", "-y"] + inputs + filter_complex` | BACKGROUND_HIDDEN | 版式合成 |

### scripts/resolve_easel.py

| 行 | 命令 | 类别 | 备注 |
|---|---|---|---|
| 66 | `["git", "-C", path, *args]` | BACKGROUND_HIDDEN | 共用 git 读取 helper |
| 215 | `["git", "clone", "--depth", "1", ...]` | BACKGROUND_HIDDEN | 网络操作，timeout 600 |
| 238 | `["gh", "api", .../tarball/...]` | BACKGROUND_HIDDEN | **`stdout=<文件句柄>`**、`stderr=PIPE`；需要 stdout 透传 |

### scripts/run_v1.py

| 行 | 命令 | 类别 | 备注 |
|---|---|---|---|
| 50 | `["ffprobe", ..., json]` | BACKGROUND_HIDDEN | |
| 131 | PowerShell TTS（`ps_cmd`） | BACKGROUND_HIDDEN | 把 shell *解释器* 当工具用，不是 `shell=True` |
| 140 | `["espeak", ...]` | BACKGROUND_HIDDEN | 没有 `text=True`；可二进制 |
| 170 | `["ffmpeg", ..., 图像适配]` | BACKGROUND_HIDDEN | |
| 186 | `["ffmpeg", ..., drawtext]` 标题卡 | BACKGROUND_HIDDEN | |
| 199 | `["ffmpeg", ..., concat]` | BACKGROUND_HIDDEN | timeout 600 |
| 293 | `[sys.executable, tts_script, "speak", ...]` | BACKGROUND_HIDDEN | 已是 `sys.executable` |
| 414 | `["ffmpeg", ..., stillimage]` 镜头片段 | BACKGROUND_HIDDEN | |

### scripts/test_basic.py

| 行 | 命令 | 类别 | 备注 |
|---|---|---|---|
| 17 | `[PYTHON, *args]` 测试执行器 | BACKGROUND_HIDDEN | `PYTHON = sys.executable` |
| 128 | `["git", "-C", easel, *a]`（写在 `lambda` 里） | BACKGROUND_HIDDEN | 必须改成 `def` 才能干净地传 kwargs |

### scripts/verify_easel_runtime.py

| 行 | 命令 | 类别 | 备注 |
|---|---|---|---|
| 70 | `["gh", "api", .../git/trees/...]` | BACKGROUND_HIDDEN | |
| 102 | `["gh", "api", .../git/ref/tags/...]` | BACKGROUND_HIDDEN | |
| 113 | `["gh", "api", .../git/tags/...]` | BACKGROUND_HIDDEN | 剥离 annotated tag |

### tests/test_windows_paths.py

| 行 | 命令 | 类别 | 备注 |
|---|---|---|---|
| 24 | `args` 测试执行器 | BACKGROUND_HIDDEN | 生成子解释器 |

### projects/easel-review/scripts/capture_evidence.py

| 行 | 命令 | 类别 | 备注 |
|---|---|---|---|
| 86 | `["ffmpeg", ..., lavfi color]` | BACKGROUND_HIDDEN | |
| 108 | `cmd`（变量） | BACKGROUND_HIDDEN | 动态命令列表 |

### projects/easel-review/scripts/gen_screenshots.py

| 行 | 命令 | 类别 | 备注 |
|---|---|---|---|
| 49 | `cmd`（变量，ffmpeg） | BACKGROUND_HIDDEN | |

## `EXEMPT_WITH_REASON`

### scripts/process_utils.py

这个文件**就是**抽象层本身。它对 `subprocess` 的直接使用是实现目标，不是违规。

| 用途 | 类别 | 理由 |
|---|---|---|
| `hidden_run` → `subprocess.run` | EXEMPT_WITH_REASON | 隐藏窗口 wrapper 的实现；给自己再加隐藏参数是循环定义 |
| `hidden_popen` → `subprocess.Popen` | EXEMPT_WITH_REASON | 同上 |
| `interactive_run` → `subprocess.run` | EXEMPT_WITH_REASON | 有意**保持可见并继承 stdio**；抑制窗口或管道化流都会让 `gh auth login` / `mmx auth login` 无法使用 |
| `interactive_run_captured` → `subprocess.run` | EXEMPT_WITH_REASON | 显式选择"可见 + 捕获"，独立成函数，绝不为它削弱认证默认语义 |

### scripts/check_subprocess_policy.py

由本 Issue 新增。只使用 `ast`，自身没有任何 `subprocess` 调用。
检测是**语义化**的而非文本匹配：在判定任何调用之前，先把 import 解析成符号表，
因此没有任何别名能藏住违规（见下方"策略门禁覆盖范围"）。

## `INTERACTIVE_VISIBLE`

**目前没有任何一个需要。** 现有 tracked 调用点没有面向用户的交互：
`gh` 只以 `gh api` 形式使用（只读、后台），从不使用 `gh auth login`。

为 MiniMax provider 工作（Issue #4, M2.0）保留：

| 命令 | 类别 | 理由 |
|---|---|---|
| `mmx auth login` | INTERACTIVE_VISIBLE | 用户必须输入凭据 / 完成 OAuth |
| `mmx quota` / `image` / `speech` / `video` / `video task get` | BACKGROUND_HIDDEN | 非交互的 provider 调用 |

对所有未来 provider 代码的规则：不允许在 `process_utils.py` 之外出现裸的
`subprocess.run(["mmx", ...])`。认证是唯一允许的交互例外。

## 交互语义

`interactive_run()` 存在的意义是让人类完成一个流程，因此它**继承父终端**而不是捕获它：

| 属性 | 取值 | 原因 |
|---|---|---|
| 控制台 | 可见 | 用户必须看到提示 |
| `CREATE_NO_WINDOW` | 永不传入 | 否则根本没有可交互的窗口 |
| `SW_HIDE` | 永不传入 | 否则会把会话藏起来 |
| `stdin` | 继承 | 用户必须往里输入 |
| `stdout` | 继承 | 输出实时出现在用户终端 |
| `stderr` | 继承 | 提示和错误保持可见 |
| `capture_output` | 默认永不传入 | 管道化会让提示无法触达 |

`interactive_run_captured()` 是独立的、显式命名的变体，用于极少数
既需要可见窗口、又需要留存记录的场景。交互认证的默认语义绝不为此让步。

测试以语义方式断言这一点：`interactive_run` 内部的 `subprocess.run` 调用
用 `ast` 解析，必须不携带 `capture_output`、`stdout`、`stderr`、`stdin`、
`startupinfo`、`creationflags` 中的任何一个，也不允许用 `**kwargs`
把其中任何一个夹带进来。函数体内不允许出现任何 `PIPE`/`DEVNULL` 引用。

## Shell 分类

只有**裸启动**的 shell 才是交互式的。作为工具使用时属于后台工作，
必须和其他子进程一样被隐藏。

| 调用形式 | 类别 | 理由 |
|---|---|---|
| `powershell` / `pwsh` / `cmd` / `bash` / `sh`（无参数） | INTERACTIVE_VISIBLE | 打开一个由用户操作的提示符 |
| `powershell -Command ...` / `-EncodedCommand` / `-NonInteractive -Command` | BACKGROUND_HIDDEN | 执行完载荷就退出 |
| `pwsh -NoProfile -Command ...` | BACKGROUND_HIDDEN | 同上，只是前面带修饰参数 |
| `cmd /c ...` | BACKGROUND_HIDDEN | 执行后退出 |
| `cmd /k ...` | INTERACTIVE_VISIBLE | 保持提示符打开 |
| `bash -c ...` / `sh -c ...` / `bash -lc ...` | BACKGROUND_HIDDEN | 组合短选项同样属于"执行后退出" |
| `bash script.sh` / `powershell script.ps1` / `cmd some.exe` | BACKGROUND_HIDDEN | 运行脚本或程序 |

`.exe` 后缀和完整路径会被归一化，因此 `pwsh.exe` 与
`C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe` 分类结果一致。
分类同时看可执行文件**及其参数**；别名 `sp` 不说明任何问题，因为没有任何名字被信任。

## 策略门禁覆盖范围

解析按文件进行且感知 import，因此以下写法都会让 CI 失败：

| 源码 | 解析结果 |
|---|---|
| `import subprocess` / `as proc` / `as anything` | `subprocess` / `proc` / `anything` |
| `from subprocess import run` / `run as execute` / `Popen` | `run` / `execute` / `Popen` |
| `import os as operating_system` | `operating_system` |
| `from os import system` / `popen as pipe` | `system` / `pipe` |
| `import os.path as osp` | `osp` |
| `from subprocess import *` | 标记：绑定关系无法证明 |
| `asyncio.create_subprocess_exec` / `create_subprocess_shell` | 标记，避免未来的 async provider 绕过门禁 |
| 嵌套作用域与多名称 import | 标记 |

以下惰性引用**刻意不标记**：`subprocess.PIPE`、`subprocess.DEVNULL`、
`subprocess.STARTUPINFO`、`subprocess.CREATE_NO_WINDOW`、`subprocess.SW_HIDE`、
`subprocess.CompletedProcess`、`subprocess.TimeoutExpired`、
`from subprocess import PIPE, DEVNULL`，以及 `-> subprocess.CompletedProcess`
这类注解。字符串字面量、注释和文档字符串也不会触发。

## 未发现的问题

- `shell=True` 在 tracked Python 源码中**完全没有出现**
  （只在 `process_utils.py` / `tests/` 的文档字符串和注释里）。
  无需迁移；helper 现在会直接拒绝 `shell=True` 以防止回归。
- `os.system` / `os.popen` 在 tracked Python 源码中**完全没有出现**。
- `subprocess.call` / `check_call` / `check_output` **完全没有出现**。

## 修复计划

1. 扩展 `process_utils.py`：新增 `hidden_popen()`、`python_executable()`、
   `stdout`/`stderr`/`stdin` 透传、`text=False` 支持、拒绝 `shell=True`。
2. 把全部 34 个调用点迁移到 helper。不做内联 `_hidden_kwargs()` 重复实现 ——
   Windows 标志只保留一份，并由 `check_subprocess_policy.py` 强制。
3. 新增 `scripts/check_subprocess_policy.py`（基于 AST），并接入
   `dev_check.py` 与 CI。
4. 在真实 Windows 硬件上验证；用 PPID 追踪任何残余弹窗。

---

# Phase 6/7 —— 真实 Windows 机器上的测量

主机：Windows，CPython 3.13.15，`D:\Projects\X-SuperPlay-ContentOps`。
方法：每 5 ms 轮询 `EnumWindows`，查找类名为 `ConsoleWindowClass`、
`PseudoConsoleWindow` 或 `CASCADIA_HOSTING_WINDOW_CLASS` 的新可见窗口，
记录属主 PID，再通过 `Win32_Process` 解析完整 PPID 链。

## 为什么普通终端无法证明任何事

第一次尝试对所有项目（包括一个故意不隐藏的对照）都得到
`ContentOps-owned popup count = 0`。那个零**毫无价值**，
因为测量是在一个父进程本身就拥有控制台的交互式 shell 里跑的，
于是所有控制台子进程都静默继承了它，从未分配过任何窗口。

只有当对照实验证明检测器会响时，零计数才算证据。

## 究竟哪些父进程配置会产生弹窗

实测，子进程不做隐藏：

| 父进程配置 | 可见控制台窗口数 |
|---|---|
| 控制台 `python.exe` | 0 —— 子进程继承已有控制台 |
| `CREATE_NO_WINDOW` 父进程 | 0 —— 子进程无控制台运行 |
| **`DETACHED_PROCESS` 父进程** | **2 —— 弹窗** |
| **`pythonw.exe`（GUI）父进程** | **2 —— 弹窗** |

最后一行才是真实场景：IDE 或 Claude Code 没有控制台，
所以它启动的任何控制台子进程都会新分配一个可见窗口。

## 测试脚手架自身产生的干扰，以及如何扣除

在 `DETACHED_PROCESS` 下，脚手架自己产生了 2 个窗口，
因为 `python.exe` + `DETACHED_PROCESS` 会分配自己的独立控制台。
一个 `NOOP` 臂（ detached worker 什么都不启动）把这个干扰精确测为 2 个窗口，
于是每个处理臂都减去了它：

```
NOOP 基线（detached，不启动任何东西）      : 2
不隐藏的对照                              : 2   -> 归因于子进程 0
隐藏的 cmd / ffmpeg / ffprobe / git / python: 各 2 -> 归因于子进程 0
```

`pythonw.exe` 那一臂不需要修正：它的 `NOOP` 基线是 0。

## 结果 —— `pythonw.exe` GUI 父进程，真实 ContentOps 命令

先跑对照，证明检测器有效：

| 命令 | rc | 可见控制台窗口数 |
|---|---|---|
| **对照** 裸 `subprocess.run`（不做抑制） | 0 | **2** |
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

**ContentOps 自有弹窗数 = 0。**

对照复现出 2 个窗口，而全部 11 条真实命令都是 0，这就是证明：
问题真实存在，而抑制手段消除了它。

## Phase 7 —— 残余弹窗归因

没有残余的 ContentOps 弹窗，所以无需归因。为记录在案，
本该使用的归因规则已实现为祖先链分类：沿 PPID 回溯到根，
若任一祖先是 `python.exe`/`git.exe`/`ffmpeg.exe`/`ffprobe.exe`/`node.exe`/`gh.exe`
则标记 `CONTENTOPS_OWNED`；若任一祖先是 `claude.exe`/`bash.exe`/`cmd.exe`/
`powershell.exe`/`WindowsTerminal.exe` 则标记 `UPSTREAM_CLAUDE_WINDOWS_POPUP`。

测量中发现的一个注意点：对照实验的两个窗口，在 WMI 查询时属主进程都已退出，
因此要给短命弹窗做实时归因，观察者的采样必须快于子进程的生命周期。
这不影响零结果，因为零结果依赖的是"不存在"，而不是归因。

---

# Phase 9 —— WSL2 验证

主机：WSL2 上的 Ubuntu-22.04，内核 6.6.87.2-microsoft-standard-WSL2，
CPython 3.10.12，git 2.34.1。

## Linux 上的正确性

窗口抑制路径在非 Windows 上必须是严格的 no-op，以保证 POSIX 行为不变：

- `os.name == "posix"` → `_get_hidden_kwargs()` 返回 `{}`，
  没有 `startupinfo`，没有 `creationflags`。
- `hidden_run` / `hidden_popen` 正常执行。
- 交互/后台分类与 Windows 完全一致。
- 完整测试套件通过：策略门禁、32 个子进程回归测试、Windows 路径测试、
  `test_basic.py`、`check_docs.py`、`check_i18n.py`、
  `check_repo_policy.py`，以及 `dev_check.py`。

### 在这里发现的一个真实 bug

在任何没有 `node` 的主机上，`scripts/doctor.py --json` 都会崩溃并报
`FileNotFoundError: [Errno 2] No such file or directory: 'node'`。
`_check_node()` 既缺少 `_check_tool()` 已经有的 `shutil.which()` 前置检查，
也缺少它的 `try/except`。通过在本分支改动 stash 掉后在
`main` @ `51d875d` 上复现，确认为**既有问题**。
本分支已修复，因为它阻塞了 WSL2 验证路径。

## /mnt/d 性能 —— 实测，不可接受

| 指标 | `/mnt/d`（DrvFs） | `~/projects`（ext4） | 倍数 |
|---|---|---|---|
| 文件 创建+读取+删除 | 61.7 ops/秒 | 16401.9 ops/秒 | **266x** |
| `dev_check.py` 完整门禁 | 124.18 秒 | 1.66 秒 | **75x** |

在 `/mnt/d` 上，`tests/test_windows_paths.py` 会失败：
`dev_check --quick` 超过了路径测试设定的 60 秒上限，
原因纯粹是 I/O 延迟。

### 建议

WSL 开发请使用 **ext4 工作树**：

```
~/projects/X-SuperPlay-ContentOps
```

已验证：完整套件在那里通过，`dev_check` 1.66 秒完成。
`/mnt/d` 保留给 Windows 侧 checkout 以及大体积视频素材和输出，按需同步。
在 WSL 里直接开发 `/mnt/d` 会让开发者门禁慢 75 倍，
并让一个本来合理的测试仅因耗时而失败。

---

# Phase 10 —— 对 MiniMax provider 的约束（Issue #4, M2.0）

provider 集成会自动继承本策略，因为
`scripts/check_subprocess_policy.py` 在 CI 中运行。
在 `scripts/process_utils.py` 之外任何位置出现裸的
`subprocess.run(["mmx", ...])` 都会让构建失败；
门禁不需要知道 `mmx` 是什么。

分类已经编码在 `is_interactive_command()` 里：

| 命令 | 类别 | 入口 |
|---|---|---|
| `mmx auth login` | INTERACTIVE_VISIBLE | `interactive_run()` |
| `mmx quota` | BACKGROUND_HIDDEN | `hidden_run()` |
| `mmx image` | BACKGROUND_HIDDEN | `hidden_run()` |
| `mmx speech` | BACKGROUND_HIDDEN | `hidden_run()` |
| `mmx video` | BACKGROUND_HIDDEN | `hidden_run()` |
| `mmx video task get` | BACKGROUND_HIDDEN | `hidden_run()` |

子解释器必须使用 `python_executable()`；不允许使用裸字符串 `"python"`，
并且测试会断言 `process_utils.py` 自身也不含裸字符串。

## 验证命令

```
python scripts/test_basic.py
python tests/test_windows_subprocess.py
python tests/test_windows_paths.py
python scripts/check_subprocess_policy.py
python scripts/dev_check.py
git diff --check
```