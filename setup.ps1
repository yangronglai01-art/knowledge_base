# Shopkeeper Brain - Setup Script

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Shopkeeper Brain - Env Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$uvExe = "$env:USERPROFILE\.local\bin\uv.exe"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Install uv
Write-Host ""
Write-Host "[1/3] Checking uv..." -ForegroundColor Yellow
if (Test-Path $uvExe) {
    Write-Host "  uv ready" -ForegroundColor Green
} else {
    Write-Host "  Installing..." -ForegroundColor Gray
    irm https://astral.sh/uv/install.ps1 | iex
    Write-Host "  Done" -ForegroundColor Green
}

# 2. uv sync
Write-Host ""
Write-Host "[2/3] Installing Python deps (5-10 min)..." -ForegroundColor Yellow
Set-Location $projectRoot
& $uvExe sync
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Done" -ForegroundColor Green
} else {
    Write-Host "  FAILED - check network" -ForegroundColor Red
    exit 1
}

# 3. Verify
Write-Host ""
Write-Host "[3/3] Verifying..." -ForegroundColor Yellow
& $uvExe run python -c "from knowledge_base.config.config import lm_config; print('Config OK')"
& $uvExe run python -c "from knowledge_base.tool.logger import logger; print('Logger OK')"

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Next: Close and reopen PowerShell, then:" -ForegroundColor Yellow
Write-Host "    cd `"$projectRoot`"" -ForegroundColor Cyan
Write-Host "    uv run uvicorn knowledge_base.web.api.import_service:app --host 0.0.0.0 --port 8000" -ForegroundColor Cyan
