$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
  if (-not (Test-Path ".\\node_modules")) {
    throw "Missing test/node_modules. Run: cd test; npm install"
  }
  npm test
} finally {
  Pop-Location
}

