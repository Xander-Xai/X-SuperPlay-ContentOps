---
status: proposed-issue
canonical: false
issue: "#7"
date: 2026-10-30
---

# Issue 草案：`test_windows_subprocess.py` 依赖交互式控制台，在无控制台环境中失败

**类型**：test / windows
**优先级**：中（阻断 CI 全绿，但不影响任何运行时行为）

## 现象

在捕获输出或无交互控制台的环境中运行该套件，3–4 个用例抛 `OSError(9, 'invalid handle')`：

```
[ERR ] test_interactive_run_inherits_stdin: OSError(9, ...)
[ERR ] test_interactive_run_captured_is_explicit: OSError(9, ...)
[ERR ] test_debug_override_disables_suppression: OSError(9, ...)
```

## 复现条件（已实测）

| 环境 | 结果 |
|---|---|
| `main`（`5d1fcf2`）干净 worktree，输出被捕获 | 3/47 失败 |
| `feat/content-router`（`3f76030`）干净 worktree，输出被捕获 | 3–4/49 失败 |
| 同一个函数在带控制台的进程里单独调用 | 通过 |
| 单独 import 后逐个运行（`test_interactive_run_captured_is_explicit` 先跑） | 通过 |

结论：**与分支内容无关，只与"当前进程有没有真实的控制台句柄"有关**。同一个测试在不同次运行中
失败数在 3 与 4 之间浮动，说明前一个用例失败会污染后续用例（`test_interactive_run_inherits_stdin`
失败后 `test_debug_override_disables_suppression` 随之失败）。

## 影响

- `python scripts\dev_check.py` 在任何 CI / 代理 / 捕获输出的运行方式下都退出 1，因此"全绿"这一
  信号失去意义；
- 三个用例本身是有价值的（它们校验 `interactive_run` 确实保留可见窗口、确实继承 stdin），
  不能简单删除。

## 建议方案（三选一，需评审）

1. **显式探测并 skip**：在套件开头检测当前进程是否拥有控制台
   （`ctypes.windll.kernel32.GetConsoleWindow()` 或 `sys.stdin.isatty()` 组合），
   无控制台时 `print` 一行原因并跳过这 3 个用例。**不是无条件 skip**：有控制台时必须真跑。
2. **改为可注入的句柄**：让 `process_utils.interactive_run` 接受显式的 stdin/stdout 句柄，
   测试用一个受控管道代替真实控制台，从而在没有控制台的环境里也能验证"没有加隐藏窗口标志"。
3. **拆成两套**：`test_windows_subprocess.py`（无需控制台）+ `test_windows_console.py`
   （需要控制台，CI 中标记为 manual / 允许 skip）。

## 验收标准

- [ ] 在**无控制台**环境（CI、捕获输出、计划任务）中，`python tests\test_windows_subprocess.py`
      退出 0，且输出明确说明跳过了哪几个用例与原因；
- [ ] 在**有控制台**的 PowerShell 窗口中，这 3 个用例真实执行并通过，跳过逻辑不触发；
- [ ] `python scripts\dev_check.py` 在两种环境下都退出 0；
- [ ] 不降低断言强度：不得为了变绿删除对 `CREATE_NO_WINDOW` / `SW_HIDE` 的 AST 检查。

## 不接受的替代做法

- 无条件 `skip`；
- 把该套件从 `dev_check` 的发现里移除；
- 捕获并吞掉 `OSError(9)` 后仍打印通过。
