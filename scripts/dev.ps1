# One-click start: FastAPI + Vite (foreground). Ctrl+C stops both.
# Usage (repo root): .\scripts\dev.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$python = $null
if (Test-Path ".\.venv\Scripts\python.exe") {
  $python = (Resolve-Path ".\.venv\Scripts\python.exe").Path
} else {
  $cmd = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($cmd) { $python = $cmd.Source }
}

if (-not $python) {
  Write-Host "[dev] python not found. Create .venv or install Python 3.11+."
  exit 1
}

& $python ".\scripts\dev.py"
exit $LASTEXITCODE