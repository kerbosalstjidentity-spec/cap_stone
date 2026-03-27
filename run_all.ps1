# consume-pattern 전체 서비스 기동 스크립트
# fraud-service + backend + frontend 를 각각 새 창에서 실행
#
# 사용법:
#   .\run_all.ps1                  # 전체 실행
#   .\run_all.ps1 -SkipFraud       # fraud-service 제외 (이미 실행 중인 경우)
#   .\run_all.ps1 -SkipFrontend    # 프론트엔드 제외

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

# 1) fraud-service (port 8010)
if (-not $SkipFraud) {
    Write-Host "[1/3] fraud-service 시작 (port 8010)..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$FraudDir'; Write-Host 'fraud-service @ http://localhost:8010' -ForegroundColor Green; .\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8010"
    ) -WindowStyle Normal
    Start-Sleep -Seconds 2
} else {
    Write-Host "[1/3] fraud-service 건너뜀 (이미 실행 중)" -ForegroundColor Gray
}

# 2) consume-pattern backend (port 8020)
Write-Host "[2/3] Backend 시작 (port 8020)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$BackendDir'; Write-Host 'Backend @ http://localhost:8020' -ForegroundColor Green; Write-Host 'Swagger @ http://localhost:8020/docs' -ForegroundColor Cyan; .\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8020 --reload"
) -WindowStyle Normal
Start-Sleep -Seconds 3

# 3) Frontend Next.js (port 3020)
if (-not $SkipFrontend) {
    Write-Host "[3/3] Frontend 시작 (port 3020)..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$FrontDir'; Write-Host 'Frontend @ http://localhost:3020' -ForegroundColor Green; npm run dev"
    ) -WindowStyle Normal
} else {
    Write-Host "[3/3] Frontend 건너뜀" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  실행 완료! 잠시 후 접속하세요" -ForegroundColor Cyan
Write-Host ""
Write-Host "  프론트엔드:  http://localhost:3020" -ForegroundColor Green
Write-Host "  Backend API: http://localhost:8020/docs" -ForegroundColor Green
Write-Host "  fraud-service: http://localhost:8010/admin" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# 브라우저 자동 열기 (3초 후)
Start-Sleep -Seconds 3
Start-Process "http://localhost:3020"
