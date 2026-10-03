# Bootstrap X-SuperPlay-ContentOps runtime on Windows PowerShell.
#
# - Checks git, python>=3.10, node>=22.19, ffmpeg, ffprobe
# - Clones Easel into .runtime/easel/ at the pinned commit
# - Verifies HEAD matches runtime/easel.lock.json
# - Does NOT auto-upgrade upstream

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir '..')
$Lock = Join-Path $Root 'runtime/easel.lock.json'
$EaselDir = Join-Path $Root '.runtime/easel'

function Write-Section($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)     { Write-Host "  OK    $msg" -ForegroundColor Green }
function Write-Warn($msg)   { Write-Host "  WARN  $msg" -ForegroundColor Yellow }
function Write-Err($msg)    { Write-Host "  ERROR $msg" -ForegroundColor Red }

function Require-Tool($name, [string[]]$args = @('--version')) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $cmd) { Write-Err "$name missing"; return $false }
    try {
        $line = (& $name @args 2>&1 | Select-Object -First 1)
        Write-Ok "$name -> $line"
        return $true
    } catch {
        Write-Err "$name failed: $_"
        return $false
    }
}

Write-Section "X-SuperPlay-ContentOps bootstrap (PowerShell)"

Write-Section "[1/4] Toolchain check"
$ok = $true
$ok = (Require-Tool git) -and $ok
$ok = (Require-Tool ffmpeg '-version') -and $ok
$ok = (Require-Tool ffprobe '-version') -and $ok
$ok = (Require-Tool python) -and $ok
$ok = (Require-Tool node) -and $ok
if (-not $ok) {
    Write-Err "Required tool missing. Aborting."
    exit 2
}

Write-Section "[2/4] Lock file"
if (-not (Test-Path $Lock)) { Write-Err "missing $Lock"; exit 2 }
$lockData = Get-Content $Lock -Raw | ConvertFrom-Json
$Expected = $lockData.commit
$Tag = $lockData.tag
Write-Host "  expected commit: $Expected  ($Tag)"

Write-Section "[3/4] Clone Easel"
New-Item -ItemType Directory -Force -Path (Split-Path $EaselDir) | Out-Null
if (-not (Test-Path (Join-Path $EaselDir '.git'))) {
    git clone --no-checkout https://github.com/ZJU-REAL/Easel.git $EaselDir
    if ($LASTEXITCODE -ne 0) { Write-Err "git clone failed"; exit 3 }
}

Write-Section "[4/4] Checkout pinned commit"
Push-Location $EaselDir
try {
    git fetch --depth=1 origin $Expected
    if ($LASTEXITCODE -ne 0) { Write-Err "git fetch failed"; exit 4 }
    git checkout $Expected
    if ($LASTEXITCODE -ne 0) { Write-Err "git checkout failed"; exit 4 }
    $Actual = (git rev-parse HEAD).Trim()
    if ($Actual -ne $Expected) {
        Write-Err "HEAD mismatch: $Actual != $Expected"
        exit 5
    }
    Write-Ok "Easel checked out at $Actual"
} finally {
    Pop-Location
}

Write-Section "Running doctor..."
& python (Join-Path $Root 'scripts/doctor.py')
if ($LASTEXITCODE -ne 0) { Write-Warn "doctor reported warnings (see above)" }

Write-Host "`nBootstrap complete." -ForegroundColor Green
Write-Host ""
Write-Host "Next:"
Write-Host "  python scripts\new_project.py --slug easel-review --title 'Easel 实测'"
Write-Host "  python scripts\run_v1.py projects\easel-review"
Write-Host "  python scripts\qc_video.py projects\easel-review"