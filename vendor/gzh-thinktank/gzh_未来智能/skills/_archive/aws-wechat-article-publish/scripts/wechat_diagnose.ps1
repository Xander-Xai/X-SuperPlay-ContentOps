<#
.SYNOPSIS
    微信公众号发布诊断工具（PowerShell 版）
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File wechat_diagnose.ps1
    powershell -ExecutionPolicy Bypass -File wechat_diagnose.ps1 -Action token
    powershell -ExecutionPolicy Bypass -File wechat_diagnose.ps1 -Action upload -ImagePath ./cover.png
    powershell -ExecutionPolicy Bypass -File wechat_diagnose.ps1 -Action draft -ArticleDir ./drafts/slug/
#>

param(
    [ValidateSet("diagnose","token","upload","draft")]
    [string]$Action = "diagnose",
    [string]$ImagePath = "",
    [string]$ArticleDir = "",
    [string]$EnvPath = "aws.env",
    [string]$ConfigPath = ".aws-article/config.yaml"
)

function Write-Step { param([string]$M) Write-Host "`n>>> $M" -ForegroundColor Cyan }
function Write-Ok   { param([string]$M) Write-Host "  [OK] $M" -ForegroundColor Green }
function Write-Warn { param([string]$M) Write-Host "  [WARN] $M" -ForegroundColor Yellow }
function Write-Fail { param([string]$M) Write-Host "  [FAIL] $M" -ForegroundColor Red }

function Read-DotEnv {
    param([string]$P)
    $map = @{}
    if (-not (Test-Path $P)) { return $map }
    foreach ($line in Get-Content $P -Encoding UTF8) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith("#")) { continue }
        if ($line.StartsWith("export ")) { $line = $line.Substring(7).Trim() }
        $idx = $line.IndexOf("=")
        if ($idx -lt 0) { continue }
        $k = $line.Substring(0,$idx).Trim()
        $v = $line.Substring($idx+1).Trim()
        if ($v.Length -ge 2 -and $v[0] -eq $v[-1] -and ($v[0] -eq '"' -or $v[0] -eq "'")) { $v = $v.Substring(1,$v.Length-2) }
        $map[$k] = $v
    }
    return $map
}

function Read-ConfigSimple {
    param([string]$P)
    $map = @{}
    if (-not (Test-Path $P)) { return $map }
    foreach ($line in Get-Content $P -Encoding UTF8) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith("#")) { continue }
        $idx = $line.IndexOf(":")
        if ($idx -lt 0) { continue }
        $k = $line.Substring(0,$idx).Trim()
        $v = $line.Substring($idx+1).Trim()
        if ($v -and -not $v.StartsWith("#")) { $map[$k] = $v }
    }
    return $map
}

function Get-WeChatToken {
    param([string]$AppId, [string]$Secret)
    $url = "https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=$AppId&secret=$Secret"
    try {
        $r = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 15 -ErrorAction Stop
        return $r
    } catch {
        return @{ error = $_.Exception.Message }
    }
}

function Upload-WeChatImage {
    param([string]$Token, [string]$ImgPath)
    if (-not (Test-Path $ImgPath)) { Write-Fail "File not found: $ImgPath"; return $null }
    $fi = Get-Item $ImgPath
    if ($fi.Length -gt 5MB) { Write-Fail "Image > 5MB"; return $null }
    $ext = $fi.Extension.ToLower()
    $mt = if ($ext -in ".jpg",".jpeg") { "image/jpeg" } elseif ($ext -eq ".gif") { "image/gif" } else { "image/png" }
    $url = "https://api.weixin.qq.com/cgi-bin/media/upload?access_token=$Token&type=image"
    try {
        $boundary = [Guid]::NewGuid().ToString()
        $fn = $fi.Name
        $bytes = [IO.File]::ReadAllBytes($fi.FullName)
        $enc = [Text.Encoding]::UTF8
        $hdr = $enc.GetBytes("--$boundary`r`nContent-Disposition: form-data; name=`"media`"; filename=`"$fn`"`r`nContent-Type: $mt`r`n`r`n")
        $ftr = $enc.GetBytes("`r`n--$boundary--")
        $body = New-Object Collections.Generic.List[byte]
        $body.AddRange($hdr); $body.AddRange($bytes); $body.AddRange($ftr)
        $r = Invoke-RestMethod -Uri $url -Method Post -ContentType "multipart/form-data; boundary=$boundary" -Body $body.ToArray() -TimeoutSec 60 -ErrorAction Stop
        if ($r.media_id) {
            Write-Ok "Upload OK: media_id=$($r.media_id)"
            if ($r.url) { Write-Ok "URL: $($r.url)" }
            return $r
        } else {
            Write-Fail "Upload failed: $($r | ConvertTo-Json -Compress)"
            return $null
        }
    } catch {
        Write-Fail "Upload error: $($_.Exception.Message)"
        return $null
    }
}

# --- Diagnose ---
function Invoke-Diagnose {
    $issues = @()
    Write-Step "1. Check config files"
    if (Test-Path $ConfigPath) { Write-Ok "config.yaml found" } else { Write-Fail "config.yaml missing"; $issues += "Create .aws-article/config.yaml" }
    if (Test-Path $EnvPath) { Write-Ok "aws.env found" } else { Write-Fail "aws.env missing"; $issues += "Create aws.env" }
    if ($issues.Count -gt 0) { Write-Host "`n=== Aborted ===" -ForegroundColor Red; return }

    Write-Step "2. Check WeChat credentials"
    $env = Read-DotEnv $EnvPath
    $cfg = Read-ConfigSimple $ConfigPath
    $n = 1
    if ($cfg["wechat_accounts"]) { try { $n = [int]$cfg["wechat_accounts"] } catch {} }
    $probe = $null
    for ($i = 1; $i -le $n; $i++) {
        $nm = $cfg["wechat_${i}_name"]
        $aid = $env["WECHAT_${i}_APPID"]
        $sec = $env["WECHAT_${i}_APPSECRET"]
        if (-not $nm) { Write-Fail "Slot $i : missing wechat_${i}_name"; $issues += "Add wechat_${i}_name to config.yaml" }
        if (-not $aid) { Write-Fail "Slot $i : missing WECHAT_${i}_APPID"; $issues += "Add WECHAT_${i}_APPID to aws.env" }
        if (-not $sec) { Write-Fail "Slot $i : missing WECHAT_${i}_APPSECRET"; $issues += "Add WECHAT_${i}_APPSECRET to aws.env" }
        if ($nm -and $aid -and $sec) { Write-Ok "Slot $i ($nm): OK"; if ($null -eq $probe) { $probe = $i } }
    }
    if ($null -eq $probe) { Write-Fail "No usable slot"; return }

    Write-Step "3. Test Access Token"
    $aid = $env["WECHAT_${probe}_APPID"]; $sec = $env["WECHAT_${probe}_APPSECRET"]
    $tok = Get-WeChatToken $aid $sec
    if ($tok.access_token) {
        Write-Ok "Token: $($tok.access_token.Substring(0,16))..."
    } else {
        Write-Fail "Token failed: errcode=$($tok.errcode) errmsg=$($tok.errmsg)"
        if ($tok.errcode -eq 40164) { Write-Warn "IP not in whitelist. Add your IP in WeChat admin panel." }
        if ($tok.errcode -eq 40001) { Write-Warn "Wrong AppID or AppSecret." }
        $issues += "Fix token issue (see above)"
    }

    Write-Step "4. Test draft API"
    if ($tok.access_token) {
        try {
            $u = "https://api.weixin.qq.com/cgi-bin/draft/count?access_token=$($tok.access_token)"
            $c = Invoke-RestMethod -Uri $u -Method Get -TimeoutSec 15 -ErrorAction Stop
            if ($null -ne $c.total_count) { Write-Ok "Draft API OK (count: $($c.total_count))" } else { Write-Warn "Draft API: $($c | ConvertTo-Json -Compress)" }
        } catch { Write-Warn "Draft API error: $($_.Exception.Message)" }
    }

    Write-Step "5. Check Python"
    try { $v = & python --version 2>&1; Write-Ok "Python: $v" } catch { Write-Fail "Python not found"; $issues += "Install Python" }
    try { & python -c "import yaml" 2>&1 | Out-Null; Write-Ok "PyYAML OK" } catch { Write-Warn "PyYAML missing"; $issues += "pip install pyyaml" }
    try { & python -c "from PIL import Image" 2>&1 | Out-Null; Write-Ok "Pillow OK" } catch { Write-Warn "Pillow missing"; $issues += "pip install Pillow" }

    Write-Host "`n=== Result ===" -ForegroundColor Cyan
    if ($issues.Count -eq 0) { Write-Host "  All checks passed!" -ForegroundColor Green }
    else { Write-Host "  $($issues.Count) issue(s):" -ForegroundColor Yellow; for ($i=0;$i -lt $issues.Count;$i++) { Write-Host "    $($i+1). $($issues[$i])" } }
}

# --- Main ---
switch ($Action) {
    "diagnose" { Write-Host "=== WeChat Publish Diagnose ===" -ForegroundColor Cyan; Invoke-Diagnose }
    "token" {
        $env = Read-DotEnv $EnvPath
        $r = Get-WeChatToken $env["WECHAT_1_APPID"] $env["WECHAT_1_APPSECRET"]
        if ($r.access_token) { Write-Ok "Token: $($r.access_token)" } else { Write-Fail "Failed: $($r | ConvertTo-Json -Compress)"; exit 1 }
    }
    "upload" {
        if (-not $ImagePath) { Write-Fail "Specify -ImagePath"; exit 1 }
        $env = Read-DotEnv $EnvPath
        $r = Get-WeChatToken $env["WECHAT_1_APPID"] $env["WECHAT_1_APPSECRET"]
        if (-not $r.access_token) { Write-Fail "Token failed"; exit 1 }
        Upload-WeChatImage $r.access_token $ImagePath
    }
    "draft" {
        if (-not $ArticleDir -or -not (Test-Path $ArticleDir)) { Write-Fail "Specify valid -ArticleDir"; exit 1 }
        $htmlP = Join-Path $ArticleDir "article.html"
        if (-not (Test-Path $htmlP)) { Write-Fail "No article.html in $ArticleDir"; exit 1 }
        $env = Read-DotEnv $EnvPath
        $cfg = Read-ConfigSimple $ConfigPath
        $r = Get-WeChatToken $env["WECHAT_1_APPID"] $env["WECHAT_1_APPSECRET"]
        if (-not $r.access_token) { Write-Fail "Token failed"; exit 1 }
        Write-Ok "Token OK"
        $thumbId = ""
        $cov = Get-ChildItem $ArticleDir -Filter "cover.*" -File | Where-Object { $_.Extension -match "\.(png|jpg|jpeg|gif)" }
        if ($cov) { Write-Step "Upload cover"; $up = Upload-WeChatImage $r.access_token $cov[0].FullName; if ($up -and $up.media_id) { $thumbId = $up.media_id } }
        $html = Get-Content $htmlP -Raw -Encoding UTF8
        $title = "Untitled"; $author = ""; $digest = ""
        $yamlP = Join-Path $ArticleDir "article.yaml"
        if (Test-Path $yamlP) { $y = Read-ConfigSimple $yamlP; if ($y["title"]) { $title = $y["title"] }; if ($y["author"]) { $author = $y["author"] }; if ($y["digest"]) { $digest = $y["digest"] } }
        Write-Step "Create draft: $title"
        $body = @{ articles = @(@{ title=$title; author=$author; digest=$digest; content=$html; content_source_url=""; thumb_media_id=$thumbId; need_open_comment=1; only_fans_can_comment=0 }) } | ConvertTo-Json -Depth 10
        $bytes = [Text.Encoding]::UTF8.GetBytes($body)
        try {
            $resp = Invoke-RestMethod -Uri "https://api.weixin.qq.com/cgi-bin/draft/add?access_token=$($r.access_token)" -Method Post -ContentType "application/json; charset=utf-8" -Body $bytes -TimeoutSec 30 -ErrorAction Stop
            if ($resp.media_id) { Write-Ok "Draft created! media_id=$($resp.media_id)" } else { Write-Fail "Failed: $($resp | ConvertTo-Json -Compress)"; exit 1 }
        } catch { Write-Fail "Error: $($_.Exception.Message)"; exit 1 }
    }
}