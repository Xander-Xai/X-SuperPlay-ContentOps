#Requires -Version 7.0
<#
.SYNOPSIS
    Register the curated project skills into the agent shared store and the
    Claude host directory, without copying content.

.DESCRIPTION
    A project catalog (the Easel runtime, the vendored 公众号 track) is
    authoritative on disk but invisible to the Skill tool until a host links to
    it. This script creates the same two-hop link the governance skill already
    uses for ``computer-hygiene``:

        <repo>/.../<name>        <-junction-  <sharedStore>/<name>
        <sharedStore>/<name>     <-junction-  <hostRoot>/<name>

    Dry-run by default. Nothing is copied, overwritten, or deleted; an existing
    path that is not the expected junction is reported and left alone.

.PARAMETER Apply
    Create the junctions. Without it the script only reports the plan.

.PARAMETER SharedStore
    Shared skill store. Defaults to ~/.agents/skills.

.PARAMETER HostRoot
    Host skill directory. Defaults to ~/.claude/skills.

.EXAMPLE
    & scripts/register_skill_links.ps1
    & scripts/register_skill_links.ps1 -Apply
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$SharedStore = (Join-Path $HOME '.agents\skills'),
    [string]$HostRoot = (Join-Path $HOME '.claude\skills')
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$easel = Join-Path $repo '.runtime\easel\skills\openclaw'
$gzh = Join-Path $repo 'vendor\gzh-thinktank\gzh_未来智能\skills'

# Entry-point skills, not the whole library. The rest stay reachable through
# scripts/skill_route.py; registering all of them would bloat every prompt.
$curated = [ordered]@{
    'card-design'             = $easel
    'slideshow-video'         = $easel
    'video-production'        = $easel
    'auto-subtitle'           = $easel
    'video-script'            = $easel
    'ai-music'                = $easel
    'tts-voiceover'           = $easel
    'video-reframe'           = $easel
    'clipify'                 = $easel
    'beat-sync-video'         = $easel
    'gzh-article-orchestrator' = $gzh
    'gzh-article-writing'     = $gzh
    'gzh-article-format'      = $gzh
    'gzh-visual-director'     = $gzh
    'gzh-title-seo'           = $gzh
    'gzh-editorial-review'    = $gzh
    'wechat-publisher'        = $gzh
    'wemp-operator'           = $gzh
}

foreach ($root in @($SharedStore, $HostRoot)) {
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        throw "skill directory not found: $root"
    }
}

$plan = [System.Collections.Generic.List[object]]::new()

function Add-Step {
    param([string]$Name, [string]$Link, [string]$Target)
    $item = Get-Item -LiteralPath $Link -Force -ErrorAction SilentlyContinue
    if ($null -ne $item) {
        $current = [string]$item.Target
        if ($item.LinkType -and $current -and ([System.IO.Path]::GetFullPath($current) -ieq [System.IO.Path]::GetFullPath($Target))) {
            $plan.Add([pscustomobject]@{ name = $Name; link = $Link; action = 'ok'; detail = 'already linked' })
        } else {
            $plan.Add([pscustomobject]@{ name = $Name; link = $Link; action = 'conflict'; detail = "existing path ($($item.LinkType)) left untouched" })
        }
        return
    }
    if (-not $Apply) {
        $plan.Add([pscustomobject]@{ name = $Name; link = $Link; action = 'would-link'; detail = $Target })
        return
    }
    New-Item -ItemType Junction -Path $Link -Target $Target -ErrorAction Stop | Out-Null
    $plan.Add([pscustomobject]@{ name = $Name; link = $Link; action = 'linked'; detail = $Target })
}

foreach ($entry in $curated.GetEnumerator()) {
    $name = $entry.Key
    $source = Join-Path $entry.Value $name
    if (-not (Test-Path -LiteralPath (Join-Path $source 'SKILL.md') -PathType Leaf)) {
        $plan.Add([pscustomobject]@{ name = $name; link = $source; action = 'source-missing'; detail = 'no SKILL.md' })
        continue
    }
    $sharedLink = Join-Path $SharedStore $name
    $hostLink = Join-Path $HostRoot $name
    Add-Step -Name $name -Link $sharedLink -Target $source
    Add-Step -Name $name -Link $hostLink -Target $sharedLink
}

$plan | Format-Table -AutoSize name, action, link, detail
$counts = $plan | Group-Object action | Sort-Object Name
$counts | ForEach-Object { "{0}: {1}" -f $_.Name, $_.Count }
if (-not $Apply) { "dry run; re-run with -Apply to create the junctions" }
if (@($plan | Where-Object { $_.action -eq 'conflict' -or $_.action -eq 'source-missing' }).Count -gt 0) {
    exit 1
}
