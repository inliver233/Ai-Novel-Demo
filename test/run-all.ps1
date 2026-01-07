$ErrorActionPreference = "Stop"

function Run-Step([string]$title, [scriptblock]$cmd) {
  Write-Host ""
  Write-Host "== $title =="
  & $cmd
  if ($LASTEXITCODE -ne 0) { throw "$title failed with exit code $LASTEXITCODE" }
}

$repoRoot = Split-Path -Parent $PSScriptRoot

Run-Step "Backend unit tests" {
  Push-Location (Join-Path $repoRoot "backend")
  try {
    $py = if ($IsWindows) { ".\\.venv\\Scripts\\python.exe" } else { "./.venv/bin/python" }
    & $py -m compileall -q app alembic
    & $py -m unittest discover -s tests -p "test_*.py" -v
  } finally {
    Pop-Location
  }
}

Run-Step "Frontend unit tests" {
  Push-Location (Join-Path $repoRoot "frontend")
  try {
    npm test
  } finally {
    Pop-Location
  }
}

Run-Step "E2E (this test harness)" {
  Push-Location $PSScriptRoot
  try {
    if (-not (Test-Path ".\\node_modules")) {
      npm install
      npm run install:browsers
    }
    npm test
  } finally {
    Pop-Location
  }
}

Write-Host ""
Write-Host "All checks passed."

