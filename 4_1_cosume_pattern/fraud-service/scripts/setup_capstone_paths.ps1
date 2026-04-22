# 캡스톤 레포 루트를 지정해 fraud-service/.env 생성·갱신
param(
    [string]$CapstoneRoot = "C:\Users\alstj\Downloads\4_1_capstone"
)
$ErrorActionPreference = "Stop"
# PSScriptRoot = ...\fraud-service\scripts  → 레포 루트 = 한 단계 위
$FraudRoot = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path $CapstoneRoot)) {
    Write-Error "캡스톤 폴더 없음: $CapstoneRoot"
}
$OutFds = Join-Path $CapstoneRoot "outputs\fds"
$Bundle = Join-Path $OutFds "model_bundle_open_full.joblib"
$envFile = Join-Path $FraudRoot ".env"
$lines = @(
    "# 자동 생성 — scripts/setup_capstone_paths.ps1",
    "MODEL_PATH=$Bundle",
    "CAPSTONE_OUTPUTS_DIR=$OutFds",
    "LOG_LEVEL=info"
)
$lines | Set-Content -Path $envFile -Encoding utf8
Write-Host "작성: $envFile"
if (-not (Test-Path $Bundle)) {
    Write-Warning "번들 없음. 캡스톤에서 실행: py -3 scripts/fds/pipeline_open_standard.py"
}
if (-not (Test-Path (Join-Path $OutFds "metrics_open_val_holdout.json"))) {
    Write-Warning "metrics JSON 없음. 위 파이프라인으로 생성하세요."
}
