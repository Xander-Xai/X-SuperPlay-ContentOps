# MiniMax 图片生成工具

基于 mmx-cli 的微信公众号配图生成工具，支持文生图、风格控制、批量生成。

## 依赖
- Node.js 18+
- mmx-cli (npm install -g mmx-cli)

## 安装 mmx-cli
```bash
npm install -g mmx-cli
```

## 配置认证
```bash
# API Key 方式（推荐）
mmx auth login --api-key sk-your-api-key

# 验证
mmx auth status
mmx quota
```

## 图片生成命令

### 基础用法
```bash
# 简单文生图
mmx image "一只穿宇航服的猫"

# 指定比例
mmx image generate --prompt "科技感Logo" --aspect-ratio 16:9

# 批量生成
mmx image generate --prompt "山水画" --n 3 --out-dir ./images/
```

### 参数说明
| 参数 | 说明 |
|------|------|
| --prompt | 图片描述（英文效果更好） |
| --n | 生成数量 |
| --aspect-ratio | 宽高比：2.35:1（封面）、16:9（配图）、1:1（方图） |
| --out | 输出文件名 |

## 公众号配图推荐

### 封面图（2.35:1）
```bash
mmx image generate --prompt "AI tech cover, futuristic neural network, blue gradient, minimalist design" --aspect-ratio 2.35:1 --out cover.png
```

### 文章配图（16:9）
```bash
mmx image generate --prompt "clean workspace with laptop, professional photography" --aspect-ratio 16:9 --out article.png
```

### AI哨兵快讯风格
```bash
mmx image generate --prompt "minimalist tech news illustration, glowing AI chip, neon accents" --aspect-ratio 2.35:1
```

### X超玩•未来智能深度内容风格
```bash
mmx image generate --prompt "educational AI neural network diagram, professional textbook style" --aspect-ratio 16:9
```

## Token 查询
```bash
mmx quota
```
