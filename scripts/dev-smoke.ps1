param(
  [int]$MockPort = 4010,
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173,
  [int]$TimeoutSec = 60,
  [switch]$NoWait
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

function Wait-HttpOk {
  param(
    [string]$Url,
    [int]$TimeoutSeconds = 60
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $res = Invoke-WebRequest -Uri $Url -TimeoutSec 5
      if ($res.StatusCode -ge 200 -and $res.StatusCode -lt 400) {
        return
      }
    } catch {
      # ignore
    }
    Start-Sleep -Milliseconds 500
  }
  throw "Timeout waiting for: $Url"
}

function Start-LoggedProcess {
  param(
    [string]$Name,
    [string]$WorkingDirectory,
    [string]$FilePath,
    [string[]]$Arguments,
    [hashtable]$Environment,
    [string]$StdOutPath,
    [string]$StdErrPath
  )

  $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $StdOutPath)
  $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $StdErrPath)

  Write-Host ("[dev-smoke] starting {0}..." -f $Name)

  $params = @{
    FilePath               = $FilePath
    ArgumentList           = $Arguments
    WorkingDirectory       = $WorkingDirectory
    PassThru               = $true
    RedirectStandardOutput = $StdOutPath
    RedirectStandardError  = $StdErrPath
    WindowStyle            = "Hidden"
  }
  if ($Environment -and $Environment.Count -gt 0 -and (Get-Command Start-Process).Parameters.ContainsKey("Environment")) {
    $params.Environment = $Environment
  } else {
    foreach ($k in $Environment.Keys) {
      Set-Item -Path ("Env:{0}" -f $k) -Value ([string]$Environment[$k])
    }
  }

  return Start-Process @params
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$stateDir = Join-Path $repoRoot "test/.artifacts/dev-smoke"
$pidsPath = Join-Path $stateDir "pids.json"
$null = New-Item -ItemType Directory -Force -Path $stateDir

if (Test-Path $pidsPath) {
  Write-Error "[dev-smoke] found existing state: $pidsPath`nRun: pwsh scripts/dev-smoke-stop.ps1"
}

$ports = @($MockPort, $BackendPort, $FrontendPort)
$inUse = @()
foreach ($p in $ports) {
  if (Test-PortListening -Port $p) {
    $inUse += $p
  }
}
if ($inUse.Count -gt 0) {
  Write-Error ("[dev-smoke] port(s) already in use: {0}`nHint: run `pwsh scripts/dev-smoke-stop.ps1` or stop the other process." -f ($inUse -join ", "))
}

$python = Join-Path $repoRoot "backend/.venv/Scripts/python.exe"
if (!(Test-Path $python)) {
  Write-Error "[dev-smoke] missing backend venv python: $python`nHint: create venv in backend/.venv first (see README.md)."
}

$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (!$nodeCmd) {
  Write-Error "[dev-smoke] missing dependency: node (required for mock-llm)."
}
$nodeExe = $nodeCmd.Source

$npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (!$npmCmd) {
  Write-Error "[dev-smoke] missing dependency: npm.cmd (required for frontend dev server)."
}
$npmExe = $npmCmd.Source

$started = @{
  ports = @{
    mock_llm  = $MockPort
    backend   = $BackendPort
    frontend  = $FrontendPort
  }
  pids = @{}
  logs = @{}
  started_at = (Get-Date).ToString("s")
}

try {
  $mockOut = Join-Path $stateDir "mock-llm.out.log"
  $mockErr = Join-Path $stateDir "mock-llm.err.log"
  $mockProc = Start-LoggedProcess `
    -Name "mock-llm" `
    -WorkingDirectory $repoRoot `
    -FilePath $nodeExe `
    -Arguments @("test/mock-llm/server.js") `
    -Environment @{ PORT = "$MockPort" } `
    -StdOutPath $mockOut `
    -StdErrPath $mockErr
  $started.pids.mock_llm = $mockProc.Id
  $started.logs.mock_llm_out = $mockOut
  $started.logs.mock_llm_err = $mockErr

  $backendOut = Join-Path $stateDir "backend.out.log"
  $backendErr = Join-Path $stateDir "backend.err.log"
  $backendProc = Start-LoggedProcess `
    -Name "backend" `
    -WorkingDirectory (Join-Path $repoRoot "backend") `
    -FilePath $python `
    -Arguments @(
      "-m", "uvicorn", "app.main:app",
      "--reload",
      "--workers", "1",
      "--port", "$BackendPort"
    ) `
    -Environment @{
      APP_ENV = "dev"
      DATABASE_URL = "sqlite:///./.tmp_test/ainovel-dev-smoke.db"
    } `
    -StdOutPath $backendOut `
    -StdErrPath $backendErr
  $started.pids.backend = $backendProc.Id
  $started.logs.backend_out = $backendOut
  $started.logs.backend_err = $backendErr

  $frontendOut = Join-Path $stateDir "frontend.out.log"
  $frontendErr = Join-Path $stateDir "frontend.err.log"
  $frontendProc = Start-LoggedProcess `
    -Name "frontend" `
    -WorkingDirectory (Join-Path $repoRoot "frontend") `
    -FilePath $npmExe `
    -Arguments @("run", "dev") `
    -Environment @{
      VITE_DEV_FALLBACK_ENABLED = "true"
      VITE_DEV_PORT = "$FrontendPort"
      VITE_API_PROXY_TARGET = "http://127.0.0.1:$BackendPort"
    } `
    -StdOutPath $frontendOut `
    -StdErrPath $frontendErr
  $started.pids.frontend = $frontendProc.Id
  $started.logs.frontend_out = $frontendOut
  $started.logs.frontend_err = $frontendErr

  $started | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 -Path $pidsPath

  if (-not $NoWait) {
    Wait-HttpOk -Url "http://127.0.0.1:$MockPort/health" -TimeoutSeconds $TimeoutSec
    Wait-HttpOk -Url "http://127.0.0.1:$BackendPort/api/health" -TimeoutSeconds $TimeoutSec
    Wait-HttpOk -Url "http://127.0.0.1:$FrontendPort" -TimeoutSeconds $TimeoutSec
  }

  Write-Host ""
  Write-Host "[dev-smoke] ready:"
  Write-Host ("  - mock-llm : http://127.0.0.1:{0}/health" -f $MockPort)
  Write-Host ("  - backend  : http://127.0.0.1:{0}/api/health" -f $BackendPort)
  Write-Host ("  - frontend : http://127.0.0.1:{0}" -f $FrontendPort)
  Write-Host ""
  Write-Host ("[dev-smoke] logs: {0}" -f $stateDir)
  Write-Host ("[dev-smoke] state: {0}" -f $pidsPath)
  Write-Host ""
  Write-Host "[dev-smoke] stop:"
  Write-Host "  pwsh scripts/dev-smoke-stop.ps1"
} catch {
  Write-Host ("[dev-smoke] startup failed: {0}" -f $_.Exception.Message)
  Write-Host ("[dev-smoke] logs: {0}" -f $stateDir)
  if (Test-Path $pidsPath) {
    Write-Host "[dev-smoke] attempting cleanup..."
    & pwsh -NoProfile -File (Join-Path $repoRoot "scripts/dev-smoke-stop.ps1") | Out-Host
  } else {
    foreach ($procId in @($started.pids.mock_llm, $started.pids.backend, $started.pids.frontend)) {
      if (!$procId) { continue }
      try { & taskkill.exe /PID $procId /T /F | Out-Null } catch { }
    }
  }
  throw
}
