---
translation_of: docs/RUNBOOK.md
language: zh-CN
translation_status: synced
---

# 运行手册

[English](RUNBOOK.md) | [简体中文](RUNBOOK.zh-CN.md)

> 真实可执行命令。从实际脚本行为推导，非假设。
> 最后更新：2026-10-31

## 0. 环境检查

```powershell
python scripts/doctor.py
```

## 1. 引导（首次或清理后）

```powershell
python scripts/bootstrap.ps1    # Windows
bash scripts/bootstrap.sh       # WSL/Linux
```

如 Easel 运行时缺失/损坏：

```powershell
python scripts/resolve_easel.py --bootstrap
```

## 2. 验证 Easel 运行时

```powershell
python scripts/verify_easel_runtime.py --resolve-tag
```

## 3. 创建新项目

```powershell
python scripts\new_project.py --slug my-video --title "My Video Title"
```

## 4. 运行生产流水线

```powershell
python scripts\run_v1.py projects\my-video
```

## 5. QC

```powershell
python scripts\qc_video.py projects\my-video
```

## 5.1 证据优先生产链（M5）

```powershell
python scripts\m5_production.py projects\m5-easel-pin
```

来源 → 素材 → 声明 → 脚本 → 旁白 → 字幕 → 分镜 → 合成 → QC → 评审，每个阶段写一份凭证。
任何阶段无法被证据支撑即拒绝（`exit 4`，`state: BLOCKED`）：来源在仓库外、素材 SHA-256 变化、
声明的引文不在来源中逐字出现、素材未声明、字幕覆盖率低于 0.8。

`--skip-compose` 在分镜后停止（不调用 ffmpeg、不调用 Easel）。

旁白使用离线 Windows SAPI 语音，不调用任何联网 TTS。运行始终停在
`PENDING_FOUNDER_REVIEW`，`production_ready: false` —— QC 通过不等于允许发布。


### M5 自动调用 media-use 素材（仅离线）

当 PR #64 的适配器已进入当前版本、本机已有批准后的运行时锁时，
在项目 project.yaml 中声明素材需求。执行原来的 M5 命令时，
系统会自动调用 media-use，而不需要单独运行适配器命令：

~~~yaml
media_use:
  enabled: true
  mode: local-only
  requests:
    - id: support_visual
      kind: image
      intent: local support image
      rights:
        license_id: OWNED-BY-OPERATOR
        source_url: OWNED
        reviewed_by: <reviewer>
        reviewed_at: "2026-10-31"
        review_evidence: assets/support.rights.json
        attribution: project owner
        synthetic: false
~~~

单独的 `rights_reviewed: true` 会被拒绝。每个请求必须附带复核记录
（`assets/<id>.rights.json`，schema `contentops.media-rights-review/v1`），
其许可证、来源 URL、复核人、日期与署名必须与请求完全一致。
软件许可证与非商业许可证不能用于媒体；合成素材永远不能作为证据。

把已核实权利的候选图片放入该项目 assets/，然后在
script/script.json 对应镜头使用 asset_id=support_visual。
只执行正常的工作流：

~~~powershell
python scripts\m5_production.py projects\my-video
~~~

素材阶段会自动 adopt 本项目文件、通过批准的运行时离线 resolve、
生成导入回执并核验 SHA-256，再交给原有素材校验、分镜、合成及 QC。
已有 sources/assets.json 声明的素材优先。找不到素材则明确 BLOCKED，
不擅自联网或调用付费服务。

新增 receipts/media-use-stage.json 和每个文件的来源回执。
导入的授权素材只用于视觉辅助，不自动变成事实证据。
这一版支持 image/icon/logo 的自动画面接入，以及 BGM/SFX 辅助音轨；
音频不进入事实证据。
未设置 media_use.enabled=true 的旧项目保持原行为。

本接线 PR 叠加在 M5 PR #68 上，真实外部调用还需要 PR #64。
CI 使用离线合成测试数据，不运行第三方 Provider。

## 5.2 Bundle handoff 与双线

可在 `project.yaml` 中可选地绑定 Strategy Content Bundle：

```yaml
content_bundle:
  path: bundle.json          # 相对项目目录或仓库根
  account: explorer          # explorer | thinktank
  platform: x                # 可选的交付占位
  source_map:
    SRC-20261102-001: SRC-RUNTIME-001
```

M5 会在 sources 阶段之前写 `receipts/bundle-handoff-video.json`。来源映射缺失或
不匹配会阻断运行；`PLANNED` 平台只记录交付阻断，不阻断视频生产。

单独生成 handoff（不生产、不发布）：

```powershell
python scripts\bundle_handoff.py projects\my-video\bundle.json `
  --account explorer --format VIDEO --project-slug my-video `
  --source-map SRC-20261102-001=SRC-RUNTIME-001 --out-project projects\my-video

python scripts\bundle_handoff.py projects\my-video\bundle.json `
  --account explorer --format GRAPHIC_TEXT --project-slug my-article `
  --platform wechat_article --out-project projects\my-article
```

## 5.3 图文人工包

图文线产出可审核的包，而不是平台草稿：

```powershell
python scripts\graphic_package.py `
  --project projects\my-article `
  --handoff projects\my-article\receipts\bundle-handoff-graphic_text.json `
  --input projects\my-article\graphic-input.json
```

写入 `receipts/graphic-package.json` 与 `receipts/graphic-preview.md`，
状态 `AWAITING_MANUAL_REVIEW`、`publish_authorized: false`。每张图都需要 ALT
与已审核权利块；缺失权利、路径逃逸或不可解码图片都会阻断。

## 5.4 受门禁保护的 Easel 宿主

仅查看状态；不启动服务、不安装依赖：

```powershell
python scripts\easel_host.py status
```

在 FastAPI/uvicorn 存在且宿主安全审查记录之前，`HOST_BLOCKED` 是预期结果。
`serve` 只监听 `127.0.0.1` 并拒绝所有写操作；**不要**直接运行上游 `easel web`
或 `web/app.py`。见 ADR-016。

## 6. 开发门控

```bash
python scripts/dev_check.py
```

依次运行：仓库策略 → 子进程策略 → Skill 引用 → 文档 → i18n → 冒烟测试 → 空格检查。

## 6.1 Skill 引用完整性

```bash
python scripts/check_skill_references.py
python scripts/check_skill_references.py --json
```

五个已安装的内容 Skill 引用了未合并分支上的代码。`runtime/content-skill-status.json`
记录了每一条这样的路径；当记录与当前检出不一致时检查失败：未记录的悬空引用、
已经落地（记录过时）的引用，或标记为已合并却缺少代码的 Skill。没有共享 Skill 库
的主机（CI）会跳过引用扫描，只运行“记录与分支”的一致性检查。

这里失败意味着记录需要更新——当某一层落地后，也意味着该能力现在可以在
`runtime/skill-registry.json` 中声明。

## 7. Easel 上游监控

```bash
python scripts/check_easel_upstream.py
```

## 8. i18n 一致性检查

```bash
python scripts/check_i18n.py
```

## 9. media-use 素材（可选）

需要 `~/.agents/skills/media-use` 固定版本技能与 Node ≥ 22（HyperFrames 官方 CLI 下限）。**默认不授权网络、付费供应商、跨项目复用或自动发布。** 可信运行时只证明执行了什么，不授予任何发现素材的许可证。

```powershell
python scripts\media_use_adapter.py status
python scripts\media_use_adapter.py doctor

python scripts\media_use_adapter.py candidates --type image --project projects\<slug>
python scripts\media_use_adapter.py resolve --type sfx --intent "soft transition" --project projects\<slug>

python scripts\media_use_adapter.py adopt --project projects\<slug>
python scripts\media_use_adapter.py import --type image --record-id img_001 `
  --license "CC-BY-4.0" --attribution "..." --project projects\<slug>

python scripts\media_use_adapter.py verify --project projects\<slug> --path assets\pic.png

python scripts\media_use_adapter.py demo --project projects\media-use-demo
```

退出码：`0` 完成，`2` 用法错误，`5` 被阻断／需要人工决定，`1` 意外失败。授权开关（`--allow-network`、`--allow-paid --budget`、`--allow-cross-project`、`--allowed-provider`）必须显式给出，默认关闭。

`import` 拒绝空 `--license`。media-use 记录本身没有许可证字段，因此许可证必须由人决定，不能被默认填充。

### 运行时信任（任何外部调用前必需）

必须同时具备两层，任一层都不能替代另一层：

- `runtime/media-use-runtime-baseline.json` —— 提交到仓库并由所有者批准
  （2026-10-31，仅限离线范围）。批准是记录在文件里的人为决定；它不会安装运行时。
- 本机生成的锁 —— 绝对路径、node 哈希、逐文件哈希，以及已批准基线的摘要 —— 由
  `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK` 指向，绝不提交。

干净检出的机器在生成机器锁之前仍拒绝执行。基线批准记录一旦变化，基线文件摘要也会
变化，之前生成的锁将不再匹配：任何批准变更后都要重新生成锁。不要通过手工编辑锁来
让它匹配新基线。

在一台机器上准备一次：

```powershell
# 1. 人审查证据后批准已提交的基线
python scripts\media_use_runtime.py approve --approved-by "Your Name"

# 2. 安装已批准的发布（唯一需要联网的步骤）
python scripts\media_use_runtime.py install --runtime-dir D:\Data\contentops-media-use --node D:\Toolchains\node\node.exe

# 3. 生成机器锁，并与基线比对验证
python scripts\media_use_runtime.py lock --runtime-dir D:\Data\contentops-media-use --node D:\Toolchains\node\node.exe --out D:\Data\contentops-media-use\runtime-lock.json

# 4. 通过生产适配器执行本地、离线操作
python scripts\media_use_runtime.py selfcheck --lock D:\Data\contentops-media-use\runtime-lock.json --project projects\demo
```

```powershell
$env:CONTENTOPS_MEDIA_USE_RUNTIME_LOCK = "D:\Data\contentops-media-use\runtime-lock.json"
python scripts\media_use_adapter.py status
```

`install` 使用仓库内的 `runtime/media-use-package-lock.json` 执行
`npm ci --ignore-scripts`；该文件的 SHA-256 必须等于基线的
`dependency_lock_sha256`，依赖树不同即被拒绝。

`status` 每次都会重新哈希整棵运行时树，并报告 `TRUSTED_RUNTIME`、
`RUNTIME_MISSING`、`INTEGRITY_MISMATCH`、`VERSION_MISMATCH`、
`BASELINE_MISMATCH` 或 `DEPENDENCY_UNVERIFIED` 之一。重新生成锁永远不会批准发布。
没有可信锁时，项目内本地导入仍然可用，但所有外部调用都会被拒绝。

### 升级或回退 HyperFrames

升级是显式、经过审核的变更；适配器从不自动更新。

1. 更新 `runtime/media-use-runtime-baseline.json` 中的版本、官方 SRI、依赖锁摘要与包树摘要。
2. 人工审查证据后运行 `python scripts\media_use_runtime.py approve --approved-by "<name>"`。
3. 安装到**新的**运行时目录（不要覆盖可信目录），再执行 `lock` 与 `verify`。
4. 离线运行 `selfcheck`，再运行 `tests/test_media_use_adapter.py` 与 `tests/test_media_convergence.py`。
5. 将 `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK` 指向新锁。

回退：保留旧的运行时目录与其锁，把环境变量指回旧锁，并验证它针对生成时的基线报告
`TRUSTED_RUNTIME`。绝不要手工编辑锁或逐文件哈希。

### M5 自动获取素材

在 `projects/<slug>/project.yaml` 里声明一次，主入口就会自动解析，无需单独调用 media-use：

```yaml
media_use:
  enabled: true
  mode: local-only
  requests:
    - {id: hero, kind: image, intent: "...", rights: {license_id: OWNED-BY-OPERATOR, source_url: OWNED, reviewed_by: me, reviewed_at: "2026-10-31", review_evidence: assets/hero.rights.json, attribution: "owner capture", synthetic: false}}
    - {id: bed, kind: bgm, intent: "...", volume: 0.18, rights: {license_id: OWNED-GENERATED-LOCAL, source_url: GENERATED, reviewed_by: me, reviewed_at: "2026-10-31", review_evidence: assets/bed.rights.json, attribution: "generated tone", synthetic: true}}
    - {id: click, kind: sfx, intent: "...", at: 6.15, volume: 0.55, rights: {license_id: Pixabay-Content-License, source_url: "https://pixabay.com/sound-effects/", reviewed_by: me, reviewed_at: "2026-10-31", review_evidence: assets/click.rights.json, attribution: "Pixabay", synthetic: false}}
```

```powershell
$env:CONTENTOPS_MEDIA_USE_RUNTIME_LOCK = "<本机已验证的锁>"
python scripts\m5_production.py projects\m5-media-use
```

`stage_media_use` 在素材门控之前执行 `adopt → resolve → import_record → verify`。
视觉导入会进入 `sources/assets.json` 校验；BGM 与 SFX 写入 `script/storyboard.json`
（`bgm`、`bgm_volume`、`sfx[].at`、`sfx[].volume`），由钉死的 Easel 合成器混在旁白之下。
`at` 必须落在旁白时间轴内，重复的音效放置会被拒绝。不会调用任何供应商。
运行时锁缺失或不匹配时，运行以退出码 `4` / `BLOCKED` 停止。`project.yaml`
没有 `media_use` 块的项目行为完全不变。

### 隔离 Easel 演示不等于原始运行时

media-use 演示通过另一套已验证的 Easel 运行时合成。演示成功与 QC `WARN` **不**表示
原始 `.runtime/easel` 检出已健康或已恢复；那仍是一个独立的完整性问题是。