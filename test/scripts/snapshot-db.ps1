$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$backendDir = Join-Path $repoRoot "backend"
$testDir = Join-Path $repoRoot "test"
$baselineDbPath = Join-Path $backendDir ".tmp_test/ainovel.schema.baseline.db"

Push-Location $backendDir
try {
  New-Item -ItemType Directory -Force -Path ".tmp_test" | Out-Null
  if (Test-Path $baselineDbPath) {
    Remove-Item $baselineDbPath -Force
  }
  $env:APP_ENV = "dev"
  $env:TASK_QUEUE_BACKEND = "inline"
  $env:DATABASE_URL = "sqlite:///./.tmp_test/ainovel.schema.baseline.db"
  $py = if ($IsWindows) { ".\\.venv\\Scripts\\python.exe" } else { "./.venv/bin/python" }
  & $py -c "from app.db.migrations import ensure_db_schema; ensure_db_schema(); print('schema ok')"
} finally {
  Pop-Location
}

Push-Location $testDir
try {
  New-Item -ItemType Directory -Force -Path "contracts" | Out-Null
  $py = if ($IsWindows) { "..\\backend\\.venv\\Scripts\\python.exe" } else { "../backend/.venv/bin/python" }
  & $py "scripts/db_schema_snapshot.py" snapshot --db "..\\backend\\.tmp_test\\ainovel.schema.baseline.db" --out "contracts/db_schema.json"
  Write-Host "Updated: test/contracts/db_schema.json"
} finally {
  Pop-Location
}

