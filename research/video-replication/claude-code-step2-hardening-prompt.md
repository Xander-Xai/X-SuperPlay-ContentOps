---
status: experiment
canonical: false
issue: "#34"
date: 2026-10-28
---

# Step 2 提示词｜skill 路由加固 + 双稿收尾（交给 Claude Code）

> 在仓库根 `D:\Projects\X-SuperPlay-ContentOps`、分支 `feat/34-video-replication` 执行。
> 前置：`research/video-replication/script-smoke-audit-2026-10-28.md` 已给出独立复核结论，先读它再动手。
> 硬约束：不要改 `skills/openclaw/auto-short-video/scripts/assemble.py`，不要改 `scripts/qc_video.py` 的判定逻辑；不发布、不生成发布链接；`outputs/` 已在 gitignore，无需提交产物。

---

## 可直接粘贴给 Claude Code 的提示词

```
任务：按复核报告完成 video-script 冒烟后的两项工具加固 + 两支脚本收尾。先读
research/video-replication/script-smoke-audit-2026-10-28.md，里面的事实断言我已独立复跑核实。

仓库：D:\Projects\X-SuperPlay-ContentOps，分支 feat/34-video-replication。
环境：Windows + PowerShell + Python；读 JSON 必须用 UTF-8，不要用默认编码（GBK 会让
ConvertFrom-Json 报"传入对象无效"）。

=== 一、加固 check_account_dna.py（真实缺口 A） ===
现状：scripts/check_account_dna.py 约 325-331 行，对 skill_route[] 只校验
step/skill/script/why 四个字段非空，从不校验 skill 名是否真的存在于路由 catalog。
要求：
1. 复用 scripts/skill_route.py 已有的 catalog 解析（CATALOG_ROOTS：.runtime/easel/skills/openclaw
   优先，其次 Easel/skills/openclaw），不要另写一套扫描逻辑。
2. 对每条 skill_route 项：解析该 skill 目录下 SKILL.md 的 frontmatter，校验
   (a) 目录存在；(b) frontmatter name 与 DNA 里的 skill 字段一致；
   (c) 目录确实落在某个 catalog root 下。任一失败，追加一条明确的 failure（带上 step 名
   和缺失的 skill 名），不要静默跳过。
3. 保持现有失败收集方式（failures.append）与输出格式不变；新增校验要能被现有测试覆盖。
4. 跑通现有 DNA 校验：两份 config/accounts/*.json 在新规则下必须通过（当前 6+6 条路由
   都真实存在）。若报出误报，先核对 catalog root 解析，不要放宽校验。
5. 在 tests/ 下补一个最小测试：构造一个指向不存在 skill 名的临时 DNA，断言校验失败并给出
   可读报错；再用一份合法 DNA 断言通过。

=== 二、统一 skill_route 路径基准（真实缺口 B） ===
现状：同一条 skill_route[] 数组里，多数 script 是 Easel 相对（skills/openclaw/...、
skills/shared/...），只有 qc 是仓库相对（scripts/qc_video.py），基准混用容易写错。
要求：
1. 先把现状列成表（step / skill / script / 判定基准），写进改动说明，不要直接改。
2. 选一种明确基准并在 schema 或注释里写死：建议 skill 类条目统一用 catalog 相对路径
   （skills/openclaw/<skill>/...），仓库级脚本（如 scripts/qc_video.py）单独标一个
   path_base 字段（可选值 catalog | repo），而不是靠字符串前缀猜。
3. 两份 DNA 的 qc 条目补上 path_base: "repo"；其余保持 catalog。
4. check_account_dna.py 新增：按 path_base 解析 script 路径并校验文件存在；缺省值与现有
   行为兼容，但对基准无法判定的条目要报 warning 而不是默默假设。
5. 不要改动各下游脚本本身的位置和调用方式，只改 DNA 声明与校验。

=== 三、收尾 B 组脚本（压字数，去掉贴边风险） ===
文件：outputs/scripts/x-superplay-future-intelligence-smoke-video-skill-route.md
及其 .narration.txt。
现状：social_count=423，正好贴 105s×220cpm 的上界 423.5，没有配音超时余量。
要求：
1. 在不丢七拍、不丢锚点「目录即注册表」两次回扣、不改 CTA 原句的前提下，把口播压到
   380–400 字（social_count 口径）。优先压缩 48-82s 双根因段的重复修饰，保留事实链。
2. 改完保持 md 口播行与 narration.txt 逐行 1:1 一致（沿用之前的脚本比对方式，identical=True）。
3. 重跑：
   python Easel/skills/shared/scripts/wordcount.py check --target 385 --tolerance 0.1 \
     -f outputs/scripts/x-superplay-future-intelligence-smoke-video-skill-route.narration.txt
   必须退出码 0，把 social_count 和区间贴出来。
4. 同步更新 md 头部字数、剪辑备注里"贴上限"的措辞、自检清单对应行。

=== 四、A 组脚本：只做字幕状态闭环，不补录屏 ===
文件：outputs/scripts/x-superplay-1024-smoke-video-skill-route.md。
现状 Hook 是"第一次没生效、同步后一致"的前后叙事，字幕需要让观众看清状态闭环。
要求：
1. 在 FAILURE_OR_BOUNDARY 之后补一句状态字幕（例如"同步 .runtime 后，两份哈希一致"），
   口播可不加字，避免超 45-60s 窗口；若加口播，重跑 wordcount.py 必须仍退出码 0。
2. 真实录屏、.gitignore 实拍画面属于人工素材采集，本轮不要编造，保留"待补证据"清单，
   不要用 AI 生成图冒充录屏。

=== 五、交付前自检（逐项回报，不许跳过） ===
1. python scripts/check_account_dna.py（或仓库现有等价入口）对两份 DNA 退出码 0。
2. python scripts/skill_route.py --list --json 仍为 114 个 skill，video-script 仍在 produce 层。
3. 两支 narration 的 wordcount.py 退出码都为 0，贴出命令与 social_count。
4. git diff 里不出现 assemble.py、qc_video.py 的逻辑改动；不出现发布链接或自动发布脚本。
5. 列一张"还缺哪些真实证据才能进 compose"的清单（对应复核报告第 4 节），不要替我补齐。

完成后回报：改了哪些文件、校验退出码、B 组最终字数、误报/兼容问题各是怎么处理的。
```

## 边界提醒（给我自己，不进上面提示词）

- 一、二是工具层加固，属代码改动，交 Claude Code 落地；我不直接改校验脚本。
- 三、四是脚本文案微调，改完必须重跑字数校验，不靠目测。
- 录屏、源码截图、公开 URL 都属于人工/外部证据，Claude Code 不能生成替代。
