---
translation_of: docs/UPSTREAM-EASEL.md
language: zh-CN
translation_status: synced
---

# 上游 Easel 策略

[English](UPSTREAM-EASEL.md) | [简体中文](UPSTREAM-EASEL.zh-CN.md)

> X-SuperPlay-ContentOps 如何关联 Easel 上游。

## 核心原则

```text
生产仅跟踪稳定发布。
上游 main 作为早期预警信号监控，
不作为生产运行时消费。
```

## 当前固定版本

| 属性 | 值 |
|---|---|
| 仓库 | https://github.com/ZJU-REAL/Easel |
| Tag | v0.2.1 |
| Commit | ```3fe2d9904c1619281ef57f81d9ee0b7854998399``` |
| 发布日期 | 2026-09-24 |
| 锁文件 | ```runtime/easel.lock.json``` |
| 本地路径 | ```.runtime/easel/```（gitignored） |
| 验证 | 982/982 blob SHA-1 匹配 |

## 规则

1. **禁止自动升级。** 上游升级需要 Founder 批准。
2. **禁止修改上游。** 仅通过 ADAPTER 模式扩展。
3. **禁止 fork。** Fork 是最后手段，需要 ADR。
4. **禁止 main 作为生产。** 上游 main 是兼容雷达，不是部署源。

## Easel 兼容矩阵

| Easel 领域 | ContentOps 依赖 | 回归要求 |
|---|---|---|
| TTS | 高 | 语音冒烟测试 |
| assemble/video | 关键 | 3 个黄金渲染 |
| Windows subprocess | 高 | Windows CI/本地 |
| model registry | 中 | Provider 合约 |
| doctor | 中 | doctor 回归 |
| gateway | 低/中 | gateway 测试 |
| publishing | 低 | 后续 M5/M6 |

## 上游 Delta 台账

| 上游 | ContentOps | 决策 |
|---|---|---|
| Easel v0.2.1 | 固定 | 生产 |
| Easel main | 监控 | 不消费为生产 |
| 下一个 release | 待定 | 兼容门控 |

## 升级门控

```text
获取新版本
    ↓
验证来源
    ↓
运行上游 diff 分析
    ↓
运行单元测试
    ↓
运行 Windows 测试
    ↓
运行 3 个黄金渲染
    ↓
比较凭证
    ↓
人工审查
    ↓
Founder 批准
    ↓
更新锁文件
```

任何步骤失败 → 保持旧版本。

## 上游监控

```bash
python scripts/check_easel_upstream.py
```

监控脚本只做：检测 → 分类 → 报告。绝不修改锁文件、下载替换生产 Easel、或打开自动升级 PR。