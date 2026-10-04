---
translation_of: docs/TEST-PLAN.md
language: zh-CN
translation_status: synced
---

# 测试计划

[English](TEST-PLAN.md) | [简体中文](TEST-PLAN.zh-CN.md)

## 测试套件

| 套件 | 文件 | 平台 |
|---|---|---|
| 基础测试 | ```scripts/test_basic.py``` | Windows + Ubuntu |
| M2 语音回归（85 项） | ```tests/test_minimax_speech.py``` | Windows + Ubuntu |
| M3 图片回归（63 项） | ```tests/test_minimax_image.py``` | Windows + Ubuntu |
| Windows 路径回归 | ```tests/test_windows_paths.py``` | Windows + Ubuntu |
| Windows 子进程回归 | ```tests/test_windows_subprocess.py``` | Windows + Ubuntu |

## CI 检查

| 检查 | 内容 |
|---|---|
| ```Tests (ubuntu-latest)``` | 基础测试 + 路径测试 + 子进程测试 + 文档检查 + i18n 检查 + 空格检查 |
| ```Tests (windows-latest)``` | 同上 |
| ```Repo policy checks``` | 文件放置 + 安全 + 归档元数据 |

## 验证门控

```python scripts/dev_check.py``` 运行：
1. 仓库策略检查
2. 文档一致性检查
3. i18n 一致性检查
4. 基础测试
5. 空格检查

全部必须通过。

### 媒体套件不会访问 provider

`test_minimax_speech.py` 与 `test_minimax_image.py` 驱动
`tests/fixtures/fake_mmx_cli.py`，并注入假计费传输，因此 CI 无需 MiniMax 账号，也不会消耗配额。
需要 `ffmpeg` 或 `Pillow` 的测试在工具缺失时输出 `[skip]` 而不是失败，因此上表测试数为上限。
