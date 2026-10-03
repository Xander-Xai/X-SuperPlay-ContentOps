目标：
60 秒左右中文竖版技术实测短视频（9:16，1080x1920）。

主题：
Easel 到底是不是一个真正能跑起来的 AI 自媒体工作流 —— 结论来自本机实跑。

风格：
Result-first（先给结果）
Evidence-first（每个结论都要有截图/命令/文件为证）
克制
技术实测
不营销、不吹嘘

结构（严格按此时间轴，总时长 60 秒左右）：

0–4s   结果/冲突：直接给出结论 —— 装上之后 doctor 和 ping 到底通没通
4–10s  它是什么：ZJU-REAL/Easel，一个开源的社媒内容工作流整合层，v0.2.1
10–28s 真实能力：它是 114 个 Skill 的集合，按 discover/plan/produce/publish/attribute 分层，
        创作层 52 个，占比最大；视频生产只是其中一条线
28–44s 本机运行：doctor 报什么、ping 报什么、网关跑在哪个端口
44–54s 限制：Web 工作台的 Python 依赖没装（fastapi/uvicorn/sse_starlette/multipart），
        所以 Web UI 这条路现在还没验证；本次只验证了 CLI + Skill + 合成这条生产路径
54–62s 结论：它不是一个开箱即用的 SaaS，但是一个真的能被调用起来的生产引擎

事实边界（极其重要，违反即作废）：
- 本次真正跑过的只有：`easel doctor`、`easel ping`、一次真实 `easel skill video-script` 调用、
  以及上游 `assemble.py` 的自检。
- 上面这些可以写成本机实测。
- 114 个 Skill、各层数量、v0.2.1 版本号 —— 这些是从 .runtime/easel 源码里数出来的，可以写。
- 其余一切（例如"自动发布""跨平台分发""数字人""归因分析"）本次都【没有】跑过，
  只能写成"官方 README / skill-function-mapping.md 声明"，不能说成实测。

禁止出现的说法：
- 虚构任何本地成功结果
- 把官方 README 宣称写成个人实测
- 承诺任何未验证的功能

请输出：
1) 分镜脚本表：时间轴 / 口播文案 / 字幕文案 / 对应画面
2) 每个镜头的画面必须说明用哪张真实证据图（见下方素材清单），不要让 AI 随机生图
3) 单独列一节「事实边界」，标明哪些是本机实测、哪些是官方声明

真实素材清单（只能从这里挑，一镜一图）：
- 10-easel-doctor.png     —— easel doctor 真实输出（环境检查结果）
- 11-easel-ping.png      —— easel ping 真实输出（网关 + Agent 连通性）
- 12-easel-version-evidence.png —— 版本证据（v0.2.1 / commit / 114 skills）
- 13-easel-skill-layers.png     —— 按 layer 统计的 Skill 分布（数出来的）
- 14-easel-skills-dir.png       —— skills/openclaw 真实目录内容
