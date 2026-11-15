<#
.SYNOPSIS
Reports listeners on a chosen local port without contacting them or reading
OpenClaw configuration, process command lines, environment, or credentials.
Listener metadata alone cannot establish a gateway's identity or version.
#>
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 18789
)

$ErrorActionPreference = 'Stop'
$result = [ordered]@{
    schema = 'contentops.easel-windows-gateway-observation/v1'
    observed_at_utc = [DateTime]::UtcNow.ToString('o')
    port = $Port
    observation = 'UNKNOWN'
    listeners = @()
    gateway_identity = 'NOT_VERIFIED'
    gateway_version = 'NOT_VERIFIED'
    credentials_read = $false
    network_connection_made = $false
    production_ready = $false
    publish_authorized = $false
}

try {
    $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop)
    foreach ($connection in $connections) {
        $processName = $null
        $executablePath = $null
        try {
            $process = Get-CimInstance -ClassName Win32_Process -Property Name,ExecutablePath,ProcessId -Filter "ProcessId = $($connection.OwningProcess)" -ErrorAction Stop
            $processName = $process.Name
            $executablePath = $process.ExecutablePath
        } catch {
            # Process may exit or be inaccessible between the two observations.
        }
        $result.listeners += [ordered]@{
            address = $connection.LocalAddress
            process_id = $connection.OwningProcess
            process_name = $processName
            executable_path = $executablePath
        }
    }
    $result.observation = if ($connections.Count) { 'LISTENERS_FOUND' } else { 'NO_LISTENER' }
} catch {
    # Get-NetTCPConnection reports no matching rows as a non-terminating error.
    if ($_.FullyQualifiedErrorId -like 'CmdletizationQuery_NotFound*') {
        $result.observation = 'NO_LISTENER'
    } else {
        $result.observation = 'QUERY_FAILED'
    }
}

$result | ConvertTo-Json -Depth 4
if ($result.observation -eq 'QUERY_FAILED') { exit 1 }
