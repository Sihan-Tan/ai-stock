# Mock CI 本地冒烟：SQLite 内存库 + pytest + 可选前端 build
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$env:DATABASE_URL = "sqlite:///:memory:"
Write-Host "== pytest =="
python -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Test-Path "apps/web/package.json") {
  Write-Host "== web build (optional) =="
  Push-Location apps/web
  npm install
  npm run build
  Pop-Location
}

Write-Host "smoke ok"
