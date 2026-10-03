```yaml
status: superseded
superseded_by: runtime/easel-runtime.json (canonical provenance), docs/UPSTREAM-EASEL.md
historical_context: Described git clone acquisition. Actual acquisition used GitHub release tarball (gh api).
notes: "http://localhost:7860" as daily entry was never verified. Web workbench has 6 doctor FAILs.
```
# Easel 部署决策 — 克隆源码 + 本地 Web 工作台 v0.2.1

> 2026-10-02 决策记录。
> 来源：本次落盘的结论。
> 相关 memory：[[easel-v021-decision]] / [[open-source-version-heuristics]]

## 一句话结论

**Easel 选「克隆源码 + 本地 Web 工作台」，版本固定 v0.2.1。**

源码版和 Web 版不是两个版本——下载源码是为了在自己电脑上跑，Web 工作台只是这份源码提供的前端界面。

## 部署架构

```
GitHub Easel v0.2.1
        ↓
clone 到 Windows
        ↓
setup.ps1
        ↓
本地 Easel 后端 + OpenClaw + Skills
        ↓
easel web
        ↓
http://localhost:7860
        ↓
浏览器日常主要入口
```

## 为什么不是桌面版 / CLI-only

桌面 `.exe` 目前不是官方主路线；CLI (`easel chat` / `easel skill`) 只做辅助。

Web 前端官方明确推荐：会话、素材、账号、画像、内容库、发布管理比 CLI 完整。

## 为什么必须克隆源码（不能只下 Release ZIP）

未来需要改：

```text
skills/
web/
easel/
profiles/
scripts/
```

源码都在手里，比封装好的 `.exe` 灵活得多。

v0.2.1 已支持在页面配置 6 类模型供应商（chat / transcribe / image / video / music / speech）+ Base URL + API Key。

## Windows 安装命令（PowerShell，不需要 WSL）

```powershell
git clone https://github.com/ZJU-REAL/Easel.git
cd Easel

git checkout v0.2.1

Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1

.\.venv\Scripts\activate

easel doctor
easel ping
easel web
```

浏览器打开 `http://localhost:7860`。

## V1 阶段规则（v0.2.1 本仓库）

**第一阶段先完全不改 Easel 源码。**

先用原版真正完成一次完整链路：

```
热点 → 选题 → 脚本 → 内容生成 → 发布前检查 → 发布 / 人工确认 → 数据回收
```

跑通之后，再决定哪些地方值得接数字人、视频 API、OPC 工作流。

禁止清单：
- 不 fork / 复制 Easel 源码
- 不自动升级 upstream
- 不为扩展性提前造抽象

## 锁定信息

| 项 | 值 |
|---|---|
| Tag | v0.2.1 |
| Commit | `3fe2d9904c1619281ef57f81d9ee0b7854998399` |
| Release 日期 | 2026-09-24 |
| 升级策略 | 仅 Founder 明确同意才能升级 |
| Lock 文件 | `runtime/easel.lock.json` |
| 本地路径 | `.runtime/easel/` |
