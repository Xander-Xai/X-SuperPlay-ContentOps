---
status: superseded
superseded_by: research/archive/dy1024-skills-2026-10-28/README.md
historical_context: copied contract from the retired dy_x1024 workspace; archived, not routed to
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
date: 2026-10-28
name: creator-cockpit
description: 在本机安装、启动、更新或修复 Creator Cockpit 创作者管理看板。适用于用户希望搭建个人内容工作台、从 GitHub 安装 Creator Cockpit、恢复本地备份，或排查 Node.js 与 pnpm 运行环境问题的场景。
---

# 安装创作者管理看板

使用以下 GitHub 仓库中的最新 `main`：

`https://github.com/Jackywxsz/creator-cockpit`

## 保护本地数据

- 创建目录前先询问用户希望安装到哪里。
- 确认准确的目标路径，不要覆盖已有内容的目录。
- 未经用户明确确认和备份，不要删除或替换已有安装。
- 不要让用户在聊天中发送 API Key；直接分析只调用用户本机已经登录的 Codex CLI 或 Claude Code。
- 尽量保持相同的浏览器、浏览器用户和本地地址，默认使用 `http://localhost:3100`。IndexedDB 数据与浏览器和访问地址绑定。
- 更新或修复前，如果看板仍能打开，先让用户在「设置与备份」中导出完整 JSON 备份。
- 如果数据看起来消失了，先检查浏览器用户、主机名和端口，再考虑恢复备份。

## 安装

1. 检查操作系统，并确认已安装 Git 和 Node.js 22.13 或更高版本。
2. 检查 pnpm，优先使用 `package.json` 中声明的包管理器版本。
3. 如果缺少运行环境，说明最小必要改动；安装系统软件前先征得用户同意。
4. 查询 `https://api.github.com/repos/Jackywxsz/creator-cockpit/commits/main`，确认仓库 `main` 可以访问，并读取最新提交 SHA 供安装结果核对。
5. 将 `main` 克隆到用户确认的空目录：

   `git clone --branch main --depth 1 https://github.com/Jackywxsz/creator-cockpit.git <目标目录>`

6. 进入项目目录。如果没有 pnpm，运行 `corepack enable`；如果需要管理员权限，先向用户说明，并在获得同意后使用合适的用户级方案。
7. 运行 `pnpm install --frozen-lockfile`。
8. 不要创建 `.env.local` 或索取 API Key。用户需要直接分析时，再检查本机 Codex CLI / Claude Code。
9. 在持续运行的终端会话中执行 `pnpm dev:lab`，默认打开 `http://localhost:3100`。这个命令会同时启动工作台和只监听 `127.0.0.1:4318` 的 Agent Bridge。
10. 不要静默更换端口。如果 3100 端口被占用，询问用户是停止其他服务还是改用新端口，并说明不同端口会拥有独立的本地数据空间。
11. 如果用户只需要内容管理，可以改用 `pnpm dev`；没有启动 Agent Bridge 时，看板仍可复制提示词和导出创作卡片。
12. 打开准确的本地地址并保持服务运行，告诉用户如何停止和重新启动。
13. 首次进入时，让用户选择示例工作区或空白工作区，并填写姓名、内容平台和创作方向。

## 配置可选本地 Agent

1. 检查 `codex --version` / `codex login status` 与 `claude --version` / `claude auth status`，只报告是否可用，不输出凭证。
2. 在独立持续运行的终端会话中执行 `pnpm agent`。
3. 打开设置页，确认 Agent Bridge、Codex 和 Claude 的可用状态。
4. 直接分析只在用户点击时运行；界面应显示实际 Agent、等待时间和取消入口，单次最长 180 秒。
5. 如果使用 macOS LaunchAgent 后台运行，确保启动脚本读取当前系统代理供 CLI 联网；未安装、未登录、超时或取消时，生成可复制提示词属于正常降级行为。

## 更新

1. 先从看板导出完整 JSON 备份。
2. 保持原安装目录、浏览器用户、主机名和端口不变。
3. 查询 GitHub `main` 的最新提交，并用 `git rev-parse HEAD` 检查当前安装版本；向用户说明提交变化。
4. 未经明确同意，不要重置或丢弃用户对源代码的本地修改。
5. 如果工作区干净，运行 `git fetch origin main`，再以 fast-forward 方式更新到 `origin/main`；如果存在本地修改或无法快进，先停止并让用户决定保留方式。
6. 运行 `pnpm install --frozen-lockfile`。
7. 运行 `pnpm test`，通过后重新启动看板。
8. 如果原来启用了本地 Agent，也重新启动 `pnpm agent`。
9. 确认已有本地数据可以正常打开，数据结构迁移已经完成。

## 修复

1. 读取完整的启动错误或浏览器错误。
2. 检查 Node.js、pnpm 版本以及 `pnpm-lock.yaml` 是否存在。
3. 运行 `pnpm install --frozen-lockfile`；如果仍然无法启动，再运行 `pnpm test`。
4. 不要把清除浏览器数据当作排错捷径。
5. 如果检查浏览器和访问地址后数据仍不可用，只从用户指定的 JSON 备份恢复，并先使用看板的导入预览。
