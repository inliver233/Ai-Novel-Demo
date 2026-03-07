param(
  [ValidateSet("quick", "full")]
  [string]$Scenario = "full",
  [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$testDir = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $testDir
$python = Join-Path $repoRoot "backend/.venv/Scripts/python.exe"

function Get-FreePortPair {
  $json = & $python -c @"
import json
import socket

def reserve_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port

print(json.dumps({"backend": reserve_port(), "frontend": reserve_port()}))
"@
  return $json | ConvertFrom-Json
}

Push-Location $testDir
try {
  $ports = Get-FreePortPair
  $env:E2E_BACKEND_URL = "http://127.0.0.1:$($ports.backend)"
  $env:E2E_FRONTEND_URL = "http://127.0.0.1:$($ports.frontend)"
  $env:AINOVEL_PERF_SCENARIO = $Scenario
  if ($OutputPath) {
    $env:AINOVEL_PERF_OUTPUT_PATH = $OutputPath
  } else {
    Remove-Item Env:AINOVEL_PERF_OUTPUT_PATH -ErrorAction SilentlyContinue
  }
  Write-Host "[perf] backend=$env:E2E_BACKEND_URL frontend=$env:E2E_FRONTEND_URL scenario=$Scenario"
  & npx playwright test -c playwright.perf.config.ts --workers=1
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
} finally {
  Remove-Item Env:E2E_BACKEND_URL -ErrorAction SilentlyContinue
  Remove-Item Env:E2E_FRONTEND_URL -ErrorAction SilentlyContinue
  Remove-Item Env:AINOVEL_PERF_SCENARIO -ErrorAction SilentlyContinue
  Remove-Item Env:AINOVEL_PERF_OUTPUT_PATH -ErrorAction SilentlyContinue
  Pop-Location
}
