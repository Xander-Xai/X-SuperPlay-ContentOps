# 微信公众号发布脚本
# 将 Markdown 发布到微信公众号草稿箱

param(
    [Parameter(Mandatory=$true)]
    [string]$File,
    
    [Parameter(Mandatory=$true)]
    [string]$Title,
    
    [string]$Author = "",
    
    [string]$Summary = "",
    
    [string]$Cover = ""
)

# 加载配置
. "$PSScriptRoot\config.ps1"

# 检查文件是否存在
if (-not (Test-Path $File)) {
    Write-Error "文件不存在: $File"
    exit 1
}

# 读取 Markdown 内容
$content = Get-Content $File -Raw -Encoding UTF8

# 简单的 Markdown 到 HTML 转换
function Convert-MarkdownToHtml {
    param([string]$md)
    
    $html = $md
    
    # 移除 frontmatter (---开头和结尾的内容)
    $html = $html -replace '(?s)^---.*?---', ''
    
    # 标题转换
    $html = $html -replace '^# (.+)$', '<h1>$1</h1>'
    $html = $html -replace '^## (.+)$', '<h2>$1</h2>'
    $html = $html -replace '^### (.+)$', '<h3>$1</h3>'
    
    # 粗体和斜体
    $html = $html -replace '\*\*(.+?)\*\*', '<strong>$1</strong>'
    $html = $html -replace '\*(.+?)\*', '<em>$1</em>'
    
    # 行内代码
    $html = $html -replace '`(.+?)`', '<code>$1</code>'
    
    # 代码块
    $html = $html -replace '```(\w+)?\n([\s\S]+?)\n```', '<pre><code>$2</code></pre>'
    
    # 链接
    $html = $html -replace '\[(.+?)\]\((.+?)\)', '<a href="$2">$1</a>'
    
    # 图片
    $html = $html -replace '!\[(.+?)\]\((.+?)\)', '<img src="$2" alt="$1"/>'
    
    # 引用
    $html = $html -replace '^> (.+)$', '<blockquote>$1</blockquote>'
    
    # 换行
    $html = $html -replace "`n", '<br/>'
    
    # 清理多余空白
    $html = $html -replace '<br/><br/>', '<br/>'
    
    return $html
}

# 获取 Access Token
function Get-WeChatAccessToken {
    $url = "https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=$env:WECHAT_APP_ID&secret=$env:WECHAT_APP_SECRET"
    
    try {
        $response = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 10
        return $response.access_token
    }
    catch {
        Write-Error "获取 Access Token 失败: $_"
        return $null
    }
}

# 上传图片
function Upload-WeChatImage {
    param(
        [string]$Token,
        [string]$ImagePath
    )
    
    if (-not (Test-Path $ImagePath)) {
        Write-Warning "图片不存在: $ImagePath"
        return $null
    }
    
    $url = "https://api.weixin.qq.com/cgi-bin/media/upload?access_token=$Token&type=image"
    
    try {
        $boundary = [Guid]::NewGuid().ToString()
        $fileName = Split-Path $ImagePath -Leaf
        $mimeType = "image/png"
        
        $header = "--$boundary`r`nContent-Disposition: form-data; name=`"media`"; filename=`"$fileName`"`r`nContent-Type: $mimeType`r`n`r`n"
        $footer = "`r`n--$boundary--"
        
        $bytes = [System.IO.File]::ReadAllBytes($ImagePath)
        $bodyBytes = $header.ToCharArray() + $bytes + $footer.ToCharArray()
        
        $response = Invoke-RestMethod -Uri $url -Method Post -ContentType "multipart/form-data; boundary=$boundary" -Body ([byte[]]$bodyBytes)
        
        return $response.url
    }
    catch {
        Write-Error "上传图片失败: $_"
        return $null
    }
}

# 发布到草稿箱
function Publish-ToDraft {
    param(
        [string]$Token,
        [string]$Title,
        [string]$Content,
        [string]$Author,
        [string]$Summary
    )
    
    $url = "https://api.weixin.qq.com/cgi-bin/draft/add?access_token=$Token"
    
    $body = @{
        "articles" = @(
            @{
                "title" = $Title
                "author" = $Author
                "digest" = $Summary
                "content" = $Content
                "content_source_url" = ""
                "thumb_media_id" = ""
                "need_open_comment" = 1
                "only_fans_can_comment" = 0
            }
        )
    } | ConvertTo-Json -Depth 10
    
    try {
        $response = Invoke-RestMethod -Uri $url -Method Post -ContentType "application/json" -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
        
        if ($response.errcode -eq 0) {
            Write-Host "✅ 文章已发布到草稿箱！" -ForegroundColor Green
            Write-Host "请前往 https://mp.weixin.qq.com/ 审核并发布"
            return $true
        }
        else {
            Write-Error "发布失败: $($response.errmsg)"
            return $false
        }
    }
    catch {
        Write-Error "发布请求失败: $_"
        return $false
    }
}

# 主流程
Write-Host "🚀 开始发布到微信公众号..." -ForegroundColor Cyan
Write-Host "标题: $Title"
Write-Host "文件: $File"
Write-Host ""

# 检查配置
if ([string]::IsNullOrEmpty($env:WECHAT_APP_ID)) {
    Write-Error "请先配置 WECHAT_APP_ID 和 WECHAT_APP_SECRET"
    Write-Host "编辑 scripts\config.ps1 文件"
    exit 1
}

# 1. 获取 Token
Write-Host "📡 获取 Access Token..." -ForegroundColor Yellow
$token = Get-WeChatAccessToken
if (-not $token) {
    exit 1
}
Write-Host "✅ Token 获取成功" -ForegroundColor Green

# 2. 转换内容
Write-Host "🔄 转换 Markdown 为 HTML..." -ForegroundColor Yellow
$htmlContent = Convert-MarkdownToHtml -md $content
Write-Host "✅ 转换完成" -ForegroundColor Green

# 3. 发布到草稿箱
Write-Host "📤 发布到草稿箱..." -ForegroundColor Yellow
Publish-ToDraft -Token $token -Title $Title -Content $htmlContent -Author $Author -Summary $Summary

Write-Host ""
Write-Host "✨ 完成！" -ForegroundColor Green
