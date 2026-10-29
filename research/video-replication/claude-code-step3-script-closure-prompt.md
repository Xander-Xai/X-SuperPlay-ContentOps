---
status: experiment
canonical: false
issue: "#34"
date: 2026-10-28
---

# Step 3 提示词｜两支脚本收尾（stale 拍改写 + 根因二口播闭环）

> 仓库：`D:\Projects\X-SuperPlay-ContentOps`，分支 `feat/34-video-replication`。
> 前置依据：`research/video-replication/script-smoke-audit-2026-10-28.md` 第 6.4 节。
> 硬约束：不改 `auto-short-video/scripts/assemble.py`、不改 `scripts/qc_video.py` 判定逻辑；不发布、不生成发布链接；不编造数字；`outputs/` 已 gitignore。

## 可直接粘贴给 Claude Code 的提示词

```
任务：收尾两支 video-script 冒烟脚本里仅剩的文案问题。先读
research/video-replication/script-smoke-audit-2026-10-28.md 第 6.4 节，结论已复核。
环境：Windows + PowerShell + Python；读 JSON 用 UTF-8，不要用默认 GBK 编码。

=== 一、A 组：改写已过时的 NEXT_VALIDATION_OPPORTUNITY 拍（P0） ===
文件：
- outputs/scripts/x-superplay-1024-smoke-video-skill-route.md
- outputs/scripts/x-superplay-1024-smoke-video-skill-route.narration.txt

现状：narration 第 7 行「下期验证：让 DNA 的路径和 skill 目录自动对账。」对应的校验
已经在本轮落进 scripts/check_account_dna.py（catalog 成员校验 + path_base 基准声明），
这句"下期验证"与仓库现状矛盾，必须改成一个真正还没做的下一步验证。

要求：
1. 把这一拍口播改为指向尚未落地的下一步，例如：
   「下一步：把这条路由校验挂到 CI，每次提交自动跑一遍。」
   你可以按口语节奏微调，但必须满足：
   - 说的是一件当前还没做、可验证、可复现的事；
   - 不宣称已上线、不编造 CI 现状；如果仓库现在没有 CI，就写成"打算挂上"，
     不要说"已经在每次提交自动跑"；
   - 不带成本、用户数、star 等无来源数字。
2. 同步更新 md 里该拍的口播、字幕、画面备注：画面线稿中段的节点从「未校验」
   改成「CI 待接入」含义，箭头方向不变；删除原"自动对账"的旧表述。
3. 保持 md 口播行与 narration.txt 逐行 1:1 一致（沿用仓库现有比对方式，identical=True）。
4. 重跑字数校验，必须退出码 0：
   python Easel/skills/shared/scripts/wordcount.py check --target 202 --tolerance 0.1 \
     -f outputs/scripts/x-superplay-1024-smoke-video-skill-route.narration.txt
   目标区间 [182, 222]；改完超区间就继续压缩，不要超 60s 窗口。
5. 更新 md 头部字数、剪辑备注里"stale 拍待改写"的标注，以及待补证据清单第 4 条
   （该条改写完成后移除对应阻塞标记，但保留录屏、.gitignore 实拍两条人工证据项）。

=== 二、B 组：根因二拍口播补一句"现已声明"（措辞闭环） ===
文件：
- outputs/scripts/x-superplay-future-intelligence-smoke-video-skill-route.md
- outputs/scripts/x-superplay-future-intelligence-smoke-video-skill-route.narration.txt

现状：ROOT_CAUSE（二）口播「还有一个坑：DNA 里的 script 是 Easel 相对，
同一个数组里的 qc_video.py 却是仓库相对。两种基准，容易写错。」只讲了历史隐患，
没交代本轮已经用 path_base 显式声明；画面备注已写"靠声明不靠猜"，口播要对齐。

要求：
1. 在该拍口播末尾补一句闭环，例如：「现在靠 path_base 字段显式声明，不靠前缀猜。」
   可微调口语，但不得新增技术概念、不得改动七拍结构和锚点「目录即注册表」。
2. 整稿字数继续留在 380–400（social_count 口径），不要为加这一句把上界 423 顶满；
   若超了，从 ROOT_CAUSE（一）的重复修饰里等长删减，事实链不丢。
3. md 口播行与 narration 逐行 1:1 一致；CTA「需要复现或交付，评论区说你的技术栈。」
   原句一个字不改。
4. 重跑字数校验，必须退出码 0：
   python Easel/skills/shared/scripts/wordcount.py check --target 385 --tolerance 0.1 \
     -f outputs/scripts/x-superplay-future-intelligence-smoke-video-skill-route.narration.txt
   目标区间 [347, 423]。
5. 同步该拍字幕与画面备注措辞；REPRO_AND_REPO 仍只写相对路径，公开 URL 未确认前
   不念链接、不写"已开源可用"。

=== 三、锚点回扣（可选，不强制加字数） ===
B 组锚点「目录即注册表」目前只口播一次，48s 是字幕/画面回扣。若加这句口头回扣
不会把 social_count 推过 400，就在 ROOT_CAUSE（一）开头自然带一次；会超字数就放弃，
不要为凑回扣硬加。

=== 四、交付前自检（逐项回报，不许跳过） ===
1. 两支 narration 与对应 md 口播逐行比对 identical=True（贴出比对结果）。
2. 两支 wordcount.py 退出码都为 0，贴命令、social_count、所属区间。
3. git diff 中不出现 assemble.py、qc_video.py 的改动；不出现任何发布链接或自动发布指令。
4. python scripts/check_account_dna.py 退出码 0；python scripts/dev_check.py 退出码 0。
5. 列一张"仍缺哪些人工证据才能进 compose"的清单：A 组终端录屏 ≥38s、.gitignore 实拍；
   B 组 CATALOG_ROOTS 三行与 _check_skill_route 源码截图、公开 URL；不要替我补齐这些。

完成后回报：改了哪些口播行、两支最终 social_count、字数校验退出码、可选锚点回扣是否加了。
```

## 不纳入本提示词的人工证据（Claude Code 不得生成替代）

- A 组：真实终端录屏（`--list --json` + `md5sum`，裁切 ≥38s）、`.gitignore` 第 31 行实拍。
- B 组：`CATALOG_ROOTS` 三行、`_check_skill_route` 新增段源码局部截图；仓库公开 URL。
