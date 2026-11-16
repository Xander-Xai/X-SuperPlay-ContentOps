# e2e-p2-fi-video — 脚本文本

由 `script/script.json` 生成；每条事实声明在 `script/claims.json` 中绑定到来源引文。

| # | 旁白 | 字幕 | 事实来源 | 素材 |
|---|---|---|---|---|
| fi01 | 做一条能发的技术片，不靠万能动画库，而是三类镜头各就各位。 | 三类镜头，不是万能的库 | — | projects/e2e-p2-fi-video/assets/anchors/fi-pain.png |
| fi02 | 顺序是选题、分镜、镜头渲染，最后交给 Easel 合成整片。 | 分镜 → 镜头 → Easel | [src/contentops/media/animation_backend.py — 短镜头后端合同](<src/contentops/media/animation_backend.py>) | projects/e2e-p2-fi-video/assets/anchors/fi-arch-02.png |
| fi03 | Easel 的版本和提交写在 pin 文件里，并且明确标记为冻结。 | 版本写在 pin 文件里 | [runtime/easel-pins.json — Easel v0.3.0 冻结清单](<runtime/easel-pins.json>) | projects/e2e-p2-fi-video/assets/anchors/fi-pin.png |
| fi04 | 所以升级不是改一行配置，而是一次需要创始人批准的动作。 | 升级要批准，不是配置 | [runtime/easel-pins.json — Easel v0.3.0 冻结清单](<runtime/easel-pins.json>) | projects/e2e-p2-fi-video/assets/anchors/fi-freeze.png |
| fi05 | 短镜头的合同是：两到八秒、静音、竖屏、三十帧。 | 2–8 秒 · 静音 · 1080×1920 | [src/contentops/media/motion_sample.py — 2–8 秒静音样本门](<src/contentops/media/motion_sample.py>) | projects/e2e-p2-fi-video/assets/anchors/fi-contract.png |
| fi06 | 证据型账号要正式生产，没有裁切后的真实录屏就直接阻断。 | 没有录屏就阻断 | [src/contentops/media/animation_backend.py — 短镜头后端合同](<src/contentops/media/animation_backend.py>) | projects/e2e-p2-fi-video/assets/anchors/fi-1024.png |
| fi07 | 解释型账号反过来，拒绝任何桌面录屏和手动操作画面。 | 解释账号拒绝录屏 | [src/contentops/media/animation_backend.py — 短镜头后端合同](<src/contentops/media/animation_backend.py>) · [config/accounts/x-superplay-future-intelligence.json — 未来智能账号 DNA](<config/accounts/x-superplay-future-intelligence.json>) | projects/e2e-p2-fi-video/assets/anchors/fi-explain.png |
| fi08 | 六种镜头模板，各自编译到一个已经验证过的 Huashu 语法。 | 六个模板，三个语法 | [docs/PRD-ANIMATION-SKILLS-INTEGRATION.md — 六模板与后端选型](<docs/PRD-ANIMATION-SKILLS-INTEGRATION.md>) | projects/e2e-p2-fi-video/assets/anchors/fi-templates.png |
| fi09 | 生成的动画一律标成非证据，它只负责解释机制，不负责证明。 | 生成动画不是证据 | [src/contentops/media/generated_clip.py — 生成片段登记为视觉辅助](<src/contentops/media/generated_clip.py>) | projects/e2e-p2-fi-video/assets/anchors/fi-evidence.png |
| fi10 | 缓存能不能复用，看的是渲染任务身份是否完全一致。 | 缓存看身份，不看文件名 | [src/contentops/media/animation_backend.py — 短镜头后端合同](<src/contentops/media/animation_backend.py>) | projects/e2e-p2-fi-video/assets/anchors/fi-cache.png |
| fi11 | 模板、参数、来源、品牌色、版本，任意一项变化就重渲。 | 任一变就重渲 | [src/contentops/media/animation_backend.py — 短镜头后端合同](<src/contentops/media/animation_backend.py>) | projects/e2e-p2-fi-video/assets/anchors/fi-fingerprint.png |
| fi12 | 现有四十五秒样片的技术质检结论是 PASS，但它仍然等着人工审片。 | PASS 之后还要人审 | [projects/m5-easel-pin/receipts/qc-report-m5-easel-pin.json — 45 秒样片技术质检](<projects/m5-easel-pin/receipts/qc-report-m5-easel-pin.json>) | projects/e2e-p2-fi-video/assets/anchors/fi-qc.png |
| fi13 | 复现这条链只要三步：写分镜，跑 M5，交给 Easel 出片。 | 三步复现 | — | projects/e2e-p2-fi-video/assets/anchors/fi-repro.png |
| fi14 | 所以能跑通不等于能发布，发布许可始终留在人手里。 | 能跑通 ≠ 能发布 | [projects/m5-easel-pin/receipts/qc-report-m5-easel-pin.json — 45 秒样片技术质检](<projects/m5-easel-pin/receipts/qc-report-m5-easel-pin.json>) | projects/e2e-p2-fi-video/assets/anchors/fi-limit.png |
