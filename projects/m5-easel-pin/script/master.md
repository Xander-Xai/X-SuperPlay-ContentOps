# m5-easel-pin — 脚本文本

由 `script/script.json` 生成；每条事实声明在 `script/claims.json` 中绑定到来源引文。

| # | 旁白 | 字幕 | 事实来源 | 素材 |
|---|---|---|---|---|
| l1 | Easel 固定在 v0.2.1，提交是 3fe2d99。 | Easel 钉在 v0.2.1 | easel_pin | projects/easel-review/sources/screenshots/12-easel-version-evidence.png |
| l2 | 听起来像洁癖，其实是可复现的底线。 | 不是洁癖，是底线 | easel_pin | projects/easel-review/sources/screenshots/12-easel-version-evidence.png |
| l3 | 本地运行时按内容哈希，和上游这个提交逐文件比对。 | 逐文件比对内容哈希 | pin_verifiable | projects/easel-review/sources/screenshots/12-easel-version-evidence.png |
| l4 | 少一个文件、改一个字节、多放一个文件，都会直接报错。 | 缺、改、多都报错 | pin_verifiable | projects/easel-review/sources/screenshots/13-easel-skill-layers.png |
| l5 | 文档写得很清楚：不许自动升级，升级必须创始人批准。 | 升级要创始人批准 | no_auto_upgrade | projects/easel-review/sources/screenshots/14-easel-skills-dir.png |
| l6 | 根目录那个旧的 Easel 克隆也不是 v0.2.1，不能当生产引擎。 | 旧克隆不是 v0.2.1 | legacy_clone | projects/easel-review/sources/screenshots/14-easel-skills-dir.png |
| l7 | 所以钉版本不是慢，是不让漂移悄悄混进生产。 | 钉版本，防漂移 | — | projects/easel-review/sources/screenshots/12-easel-version-evidence.png |
