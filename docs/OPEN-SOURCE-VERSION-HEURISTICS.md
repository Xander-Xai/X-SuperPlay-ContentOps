# 开源项目版本选择决策树

> 通用决策规则，本次落盘的结论之一。
> 适用于任何 GitHub 开源项目，不仅 Easel。
> 相关 memory：[[open-source-version-heuristics]]

## 一句话

**只是想用 → 官方 Release。要接 API / 二次开发 → Clone 源码。**

## 决策树

```
只是想用
    ↓
官方 Release / Desktop

需要快速体验
    ↓
官方 Web Demo

需要接 API / 自动化 / 二次开发 / Skill
    ↓
Clone 源码

项目很活跃
    ↓
优先 Latest Release Tag
    而不是 main

确实需要 main 的新功能 / 修复
    ↓
再升级 main
```

## 为什么 Release Tag > main

- `main` 每天都在变
- Release tag 经过 pin + 测试 + 可复现
- 避免 "昨天还工作，今天坏了" 的事

## 误判警示

| 误判 | 实际 |
|---|---|
| "源码版和 Web 版是两个版本" | 源码就是 Web 版，Web 是源码提供的前端 |
| "封装好的 .exe 才是产品" | 多数活跃项目只把源码当产品 |
| "跟着 main 才是最新" | main 是开发分支，不保证稳定 |
| "下载 ZIP 比 clone 简单" | clone 能切 tag / branch，ZIP 切不了 |

## 决策后第一件事

不管走哪条路，**先用未改动的版本跑通一次完整业务闭环**，再决定改哪里。
