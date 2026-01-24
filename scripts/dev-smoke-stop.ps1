param(
  [int]$MockPort = 4010,
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173,
  [int]$TimeoutSec = 30
)

$ErrorActionPreference = "Stop"

function Test-PortListening {
  param([int]$Port)
  try {
    return (Test-NetConnection -ComputerName "127.0.0.1" -Port $Port -InformationLevel Quiet)
  } catch {
    return $false
  }
}

function Wait-PortClosed {
  param(
    [int]$Port,
    [int]$TimeoutSeconds = 30
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (-not (Test-PortListening -Port $Port)) {
      return
    }
    Start-Sleep -Milliseconds 400
  }
  throw "Timeout waiting for port to close: $Port"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$stateDir = Join-Path $repoRoot "test/.artifacts/dev-smoke"
$pidsPath = Join-Path $stateDir "pids.json"

if (Test-Path $pidsPath) {
  $state = Get-Content -Encoding UTF8 -Path $pidsPath | ConvertFrom-Json
  $pids = @()
  if ($state.pids.mock_llm) { $pids += [int]$state.pids.mock_llm }
  if ($state.pids.backend) { $pids += [int]$state.pids.backend }
  if ($state.pids.frontend) { $pids += [int]$state.pids.frontend }

  foreach ($procId in $pids) {
    try {
      Write-Host ("[dev-smoke] stopping pid {0}..." -f $procId)
      & taskkill.exe /PID $procId /T /F | Out-Null
    } catch {
      # ignore missing process
    }
  }
} else {
  Write-Host ("[dev-smoke] state not found: {0}" -f $pidsPath)
  Write-Host "[dev-smoke] nothing to stop by pid; checking ports only..."
}

foreach ($p in @($MockPort, $BackendPort, $FrontendPort)) {
  if (Test-PortListening -Port $p) {
    Write-Host ("[dev-smoke] waiting for port {0} to close..." -f $p)
    Wait-PortClosed -Port $p -TimeoutSeconds $TimeoutSec
  }
}

if (Test-Path $pidsPath) {
  Remove-Item -Force -Path $pidsPath
}

Write-Host "[dev-smoke] stopped; ports are free."
