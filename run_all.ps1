param(
    [switch]$SkipFraud,
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Continue"

$FraudDir   = "C:\Users\alstj\Downloads\fraud-service"
$BackendDir = "C:\Users\alstj\Downloads\4_1_cosume_pattern\backend"
$FrontDir   = "C:\Users\alstj\Downloads\4_1_cosume_pattern\frontend"

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  consume-pattern 서비스 시작" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

if (-not $SkipFraud) {
    Write-Host "[1/3] fraud-service 시작 (port 8010)..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$FraudDir'; Write-Host 'fraud-service @ http://localhost:8010' -ForegroundColor Green; .\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8010" -WindowStyle Normal
    Start-Sleep -Seconds 2
} else {
    Write-Host "[1/3] fraud-service 건너뜀" -ForegroundColor Gray
}

Write-Host "[2/3] Backend 시작 (port 8020)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$BackendDir'; Write-Host 'Backend @ http://localhost:8020' -ForegroundColor Green; .\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8020 --reload" -WindowStyle Normal
Start-Sleep -Seconds 3

if (-not $SkipFrontend) {
    Write-Host "[3/3] Frontend 시작 (port 3020)..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$FrontDir'; npm run dev" -WindowStyle Normal
} else {
    Write-Host "[3/3] Frontend 건너뜀" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  [서비스 주소]" -ForegroundColor Cyan
Write-Host "  프론트엔드:     http://localhost:3020"              -ForegroundColor Green
Write-Host "  Backend API:   http://localhost:8020/docs"         -ForegroundColor Green
Write-Host "  fraud-service: http://localhost:8010/admin"        -ForegroundColor Green
Write-Host ""
Write-Host "  [fraud 연계 엔드포인트]" -ForegroundColor Cyan
Write-Host "  이상탐지+fraud:  GET  /v1/analysis/anomaly/{user_id}"   -ForegroundColor Yellow
Write-Host "  fraud 프로필:    GET  /v1/profile/{user_id}/fraud"       -ForegroundColor Yellow
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

Start-Sleep -Seconds 3
Start-Process 'http://localhost:3020'
