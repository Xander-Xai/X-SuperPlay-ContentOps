---
status: superseded
superseded_by: research/archive/dy1024-skills-2026-10-28/README.md
historical_context: copied contract from the retired dy_x1024 workspace; archived, not routed to
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
date: 2026-10-28
name: generative-media-guidance
description: 为 X·超玩1024 的生图与图生视频提供受生产合同约束的提示词指导；只规划 ChatGPT Bridge 图片和基于已验收图片的 gflow-cli i2v，不执行文生视频或替换提供商。
---

# 生图与图生视频指导适配层

本 Skill 是工作流入口，不是第三个媒体提供商。它把本地上游
`../imagegen/SKILL.md`、`../model-selector/SKILL.md` 和
`../prompt-translator/SKILL.md` 的提示词方法收敛到本项目唯一允许的执行链：

`场景计划 → 结构化生图提示词 → ChatGPT Bridge → 图片人工验收并锁定 SHA-256 → gflow-cli i2v 提示词 → 视频人工验收 → 剪辑/质检/交付`

## 强制边界

- 图片提供商只能是 `chatgpt-bridge`；不可用时阻断，不切到 Skill 自带 CLI/API。
- 视频提供商只能是 `gflow-cli`，模式只能是 `i2v`；禁止文生视频。
- 本 Skill 只生成提示词计划和 job spec；provider 提交与实际生成属于 canonical `Media Generation` 阶段。Assets 只接收、检查并登记真实素材，不把规划回执当作生成完成。
- i2v 只能引用当前内容包内已验收的 Bridge 图片，并同时绑定资产 ID、生成任务 ID 和 SHA-256。
- 上游 `model-selector` 只作能力维度参考，不执行模型选择；模型和 Flow project 必须由当前账号预检与报价证据确定。
- 上游 `prompt-translator` 的跨模型数据未随独立 Skill 目录安装，不能宣称查表转换；这里只采用其语义拆解字段。
- 所有提示词计划、输入、导出、临时文件、回执、质检和成片必须位于
  `DY_ARTIFACT_ROOT/<content_id>/` 内容包内。工作流仓库只保存代码、Skill、配置、schema 和测试。

## 生图指导合同

每条提示词至少包含：

```text
Use case: <用途分类>
Asset type: <在视频中的用途>
Primary request: <本镜头唯一视觉任务>
Scene/backdrop: <场景>
Subject: <主体>
Style/medium: <媒介与风格>
Composition/framing: Native portrait 9:16; mobile-safe composition
Text (verbatim): ""
Constraints: one cognitive anchor; one core action; illustration, not factual evidence
Avoid: text, letters, labels, numbers, logos, watermarks, UI, code, formulas
```

已有参考图时必须标明每张图的角色，并在上传前单独批准远程上传、完成文字检查。
编辑图时重复写明保持项；每次返修只改一个变量。产出后必须检查主体、构图、风格、
文字禁令与保持项。

## 图生视频指导合同

使用 `scripts/generation_guidance.py build-i2v` 从已验收图片生成任务草案。提示词固定拆为：

```text
Subject: <沿用首帧主体，不重塑身份>
Scene: <沿用首帧环境>
Motion: <一个清晰、可在 4/6/8 秒内完成的动作及时间顺序>
Camera: <一个主要镜头运动>
Style: <保持首帧视觉风格、光线与色彩>
Preserve: composition, identity, object count, background geometry
Negative: no morphing, no new text, no logo, no extra limbs, no scene cut, no camera jump
```

不要重复描述静态画面来代替运动，不堆多个互相竞争的动作。音频不由生成视频承担；
成片旁白、字幕、信息层与时间线仍分别由既有 Audio、HyperFrames、OpenChatCut、
Remotion 合同处理。

## 标准命令

```powershell
python scripts/image_prompt_plan.py --project "$env:DY_ARTIFACT_ROOT\<content_id>" --mode auto
python scripts/generation_guidance.py build-i2v --project "$env:DY_ARTIFACT_ROOT\<content_id>" --input "05_assets/i2v-requests.json"
python scripts/media_pipeline.py plan --project "$env:DY_ARTIFACT_ROOT\<content_id>" --input "05_assets/i2v-job-specs.json"
```

上述命令只规划并落盘，不产生媒体。预算批准及 provider 提交由 `media_pipeline.py` 的独立确认门禁控制；获批后的实际生成和 generation receipt 归 `Media Generation`，生成后的文件仍须进入 Assets ledger 并通过来源、权利、hash 与技术检查。

## 验收

- 提示词与本 Skill/上游参考文件的 SHA-256 一起写入任务规格。
- Skill 或参考文件变化会让旧任务在规划、提交或 Assets 检查时失效。
- 任何输出路径逃逸内容包、内容包不在 `DY_ARTIFACT_ROOT` 直接子目录、图片未验收、
  哈希变化、远程上传未批准、模式不是 i2v，均必须失败关闭。
