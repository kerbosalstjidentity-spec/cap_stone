# consume-pattern 전체 스택 실행 (Docker Compose) - Windows
# 사용: .\scripts\docker-up.ps1 [-Rebuild] [-Clean] [-Logs]

param(
    [switch]$Rebuild,  # 이미지 재빌드
    [switch]$Clean,    # 볼륨까지 제거 후 재시작
    [switch]$Logs      # 실행 후 로그 팔로우
)

$ErrorActionPreference = "Stop"

# 레포 루트로 이동
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  consume-pattern Docker 스택 시작" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

# docker 존재 확인
try { docker version --format '{{.Server.Version}}' | Out-Null }
catch {
    Write-Host "[오류] Docker Desktop이 실행 중이 아닙니다. Docker Desktop을 먼저 켜주세요." -ForegroundColor Red
    exit 1
}

# compose 커맨드 결정
$dc = $null
try { docker compose version | Out-Null; $dc = @("docker","compose") } catch {}
if (-not $dc) {
    if (Get-Command docker-compose -ErrorAction SilentlyContinue) { $dc = @("docker-compose") }
    else {
        Write-Host "[오류] docker compose를 찾을 수 없습니다." -ForegroundColor Red
        exit 1
    }
}

# 모델 번들 확인
$modelFile = "fds-research\outputs\fds\model_bundle_open_full.joblib"
if (-not (Test-Path $modelFile)) {
    Write-Host "[경고] 모델 번들을 찾을 수 없습니다: $modelFile" -ForegroundColor Yellow
    Write-Host "        fraud-service가 정상 동작하지 않을 수 있습니다." -ForegroundColor Yellow
}

if ($Clean) {
    Write-Host "[clean] 기존 컨테이너/볼륨 제거..." -ForegroundColor Yellow
    & $dc[0] $dc[1..($dc.Count-1)] down -v --remove-orphans
}

Write-Host "[up] 스택 기동..." -ForegroundColor Yellow
if ($Rebuild) {
    & $dc[0] $dc[1..($dc.Count-1)] up -d --build
} else {
    & $dc[0] $dc[1..($dc.Count-1)] up -d
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "[오류] docker compose up 실패" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  서비스 상태" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
& $dc[0] $dc[1..($dc.Count-1)] ps

Write-Host ""
Write-Host "[서비스 주소]" -ForegroundColor Cyan
Write-Host "  프론트엔드:     http://localhost:3020" -ForegroundColor Green
Write-Host "  Backend API:   http://localhost:8020/docs" -ForegroundColor Green
Write-Host "  fraud-service: http://localhost:8010/health" -ForegroundColor Green
Write-Host ""
Write-Host "[유용한 명령]" -ForegroundColor Cyan
Write-Host "  로그 보기:   docker compose logs -f" -ForegroundColor DarkGray
Write-Host "  정지:        docker compose down" -ForegroundColor DarkGray
Write-Host "  완전 초기화: docker compose down -v" -ForegroundColor DarkGray
Write-Host ""

if ($Logs) {
    & $dc[0] $dc[1..($dc.Count-1)] logs -f
} else {
    Start-Process 'http://localhost:3020'
}
