param(
    [switch]$SkipFraud,
    [switch]$SkipFrontend,
    [switch]$Clean   # 기존 프로세스 강제 종료 후 시작
)

$ErrorActionPreference = "Continue"

$FraudDir   = "C:\Users\alstj\Downloads\fraud-service"
$BackendDir = "C:\Users\alstj\Downloads\4_1_cosume_pattern\backend"
$FrontDir   = "C:\Users\alstj\Downloads\4_1_cosume_pattern\frontend"
$PgDataDir  = "C:\Program Files\PostgreSQL\17\data"
$PgService  = "postgresql-x64-17"

# ──────────────────────────────────────────────
#  헬퍼 함수
# ──────────────────────────────────────────────

function Kill-Port {
    param([int]$Port)
    $pids = (netstat -ano | Select-String ":$Port\s") |
        ForEach-Object { ($_ -split '\s+')[-1] } |
        Sort-Object -Unique
    foreach ($p in $pids) {
        if ($p -match '^\d+$' -and $p -ne '0') {
            Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue
            Write-Host "  포트 $Port 점유 프로세스(PID $p) 종료" -ForegroundColor DarkGray
        }
    }
}

function Wait-Port {
    param([int]$Port, [int]$TimeoutSec = 30)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        $tcp = New-Object System.Net.Sockets.TcpClient
        try {
            $tcp.Connect("127.0.0.1", $Port)
            $tcp.Close()
            return $true
        } catch { Start-Sleep -Milliseconds 500 }
    }
    return $false
}

function Ensure-Postgres {
    $svc = Get-Service $PgService -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Host "  [PostgreSQL] 서비스를 찾을 수 없습니다 ($PgService)" -ForegroundColor Red
        return $false
    }

    if ($svc.Status -eq "Running") {
        Write-Host "  [PostgreSQL] 실행 중" -ForegroundColor Green
        return $true
    }

    # postmaster.pid 잔재 확인 및 정리
    $pidFile = Join-Path $PgDataDir "postmaster.pid"
    if (Test-Path $pidFile) {
        $oldPid = (Get-Content $pidFile -First 1).Trim()
        $alive  = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
        if (-not $alive) {
            Write-Host "  [PostgreSQL] 좀비 postmaster.pid(PID $oldPid) 제거" -ForegroundColor DarkYellow
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        } else {
            Write-Host "  [PostgreSQL] PID $oldPid 프로세스 종료 후 pid 파일 제거" -ForegroundColor DarkYellow
            Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Host "  [PostgreSQL] 서비스 시작 중..." -ForegroundColor Yellow
    Start-Service $PgService -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2

    $svc.Refresh()
    if ($svc.Status -eq "Running") {
        Write-Host "  [PostgreSQL] 시작 완료" -ForegroundColor Green
        return $true
    } else {
        Write-Host "  [PostgreSQL] 시작 실패 — 관리자 권한이 필요할 수 있습니다" -ForegroundColor Red
        return $false
    }
}

# ──────────────────────────────────────────────
#  시작 배너
# ──────────────────────────────────────────────

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  consume-pattern 서비스 시작" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# ──────────────────────────────────────────────
#  [0] 기존 프로세스/포트 정리
# ──────────────────────────────────────────────

Write-Host "[0/4] 포트 충돌 및 좀비 프로세스 정리..." -ForegroundColor Yellow

# -Clean 플래그 또는 포트가 이미 사용 중이면 정리
$ports = @(8020, 3020)
if (-not $SkipFraud) { $ports += 8010 }

foreach ($port in $ports) {
    $inUse = (netstat -ano | Select-String ":$port\s")
    if ($inUse) {
        Write-Host "  포트 $port 충돌 감지 — 기존 프로세스 종료" -ForegroundColor DarkYellow
        Kill-Port -Port $port
        Start-Sleep -Milliseconds 300
    }
}

if ($Clean) {
    Write-Host "  -Clean: 관련 Python/Node 프로세스 전체 종료" -ForegroundColor DarkYellow
    Get-Process python, node -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

Write-Host "  완료" -ForegroundColor Green

# ──────────────────────────────────────────────
#  [1] PostgreSQL 확인/시작
# ──────────────────────────────────────────────

Write-Host "[1/4] PostgreSQL 상태 확인..." -ForegroundColor Yellow
$pgOk = Ensure-Postgres
if (-not $pgOk) {
    Write-Host "  경고: PostgreSQL 없이 계속 진행합니다 (일부 기능 비정상)" -ForegroundColor DarkYellow
}

# ──────────────────────────────────────────────
#  [2] fraud-service (선택)
# ──────────────────────────────────────────────

if (-not $SkipFraud) {
    Write-Host "[2/4] fraud-service 시작 (port 8010)..." -ForegroundColor Yellow
    if (Test-Path $FraudDir) {
        Start-Process powershell -ArgumentList "-NoExit", "-Command", `
            "Set-Location '$FraudDir'; Write-Host 'fraud-service @ http://localhost:8010' -ForegroundColor Green; .\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8010" `
            -WindowStyle Normal
        Start-Sleep -Seconds 2
    } else {
        Write-Host "  fraud-service 디렉토리 없음 — 건너뜀" -ForegroundColor Gray
    }
} else {
    Write-Host "[2/4] fraud-service 건너뜀" -ForegroundColor Gray
}

# ──────────────────────────────────────────────
#  [3] Backend
# ──────────────────────────────────────────────

Write-Host "[3/4] Backend 시작 (port 8020)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "Set-Location '$BackendDir'; Write-Host 'Backend @ http://localhost:8020/docs' -ForegroundColor Green; .\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8020 --reload" `
    -WindowStyle Normal

Write-Host "  백엔드 준비 대기 중..." -ForegroundColor DarkGray
$backendOk = Wait-Port -Port 8020 -TimeoutSec 40
if ($backendOk) {
    Write-Host "  백엔드 준비 완료" -ForegroundColor Green
} else {
    Write-Host "  경고: 백엔드가 40초 내 응답하지 않음" -ForegroundColor DarkYellow
}

# ──────────────────────────────────────────────
#  [4] Frontend
# ──────────────────────────────────────────────

if (-not $SkipFrontend) {
    Write-Host "[4/4] Frontend 시작 (port 3020)..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command", `
        "Set-Location '$FrontDir'; npm run dev" `
        -WindowStyle Normal

    Write-Host "  프론트엔드 준비 대기 중..." -ForegroundColor DarkGray
    $frontOk = Wait-Port -Port 3020 -TimeoutSec 60
    if ($frontOk) {
        Write-Host "  프론트엔드 준비 완료" -ForegroundColor Green
    } else {
        Write-Host "  경고: 프론트엔드가 60초 내 응답하지 않음 (컴파일 중일 수 있음)" -ForegroundColor DarkYellow
    }
} else {
    Write-Host "[4/4] Frontend 건너뜀" -ForegroundColor Gray
}

# ──────────────────────────────────────────────
#  완료 안내
# ──────────────────────────────────────────────

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  [서비스 주소]" -ForegroundColor Cyan
Write-Host "  프론트엔드:     http://localhost:3020"           -ForegroundColor Green
Write-Host "  Backend API:   http://localhost:8020/docs"      -ForegroundColor Green
Write-Host "  fraud-service: http://localhost:8010/admin"     -ForegroundColor Green
Write-Host ""
Write-Host "  [팁]" -ForegroundColor Cyan
Write-Host "  포트 충돌 시:   .\run_all.ps1 -Clean"           -ForegroundColor DarkGray
Write-Host "  fraud 제외:     .\run_all.ps1 -SkipFraud"       -ForegroundColor DarkGray
Write-Host "  프론트 제외:    .\run_all.ps1 -SkipFrontend"    -ForegroundColor DarkGray
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

Start-Process 'http://localhost:3020'
