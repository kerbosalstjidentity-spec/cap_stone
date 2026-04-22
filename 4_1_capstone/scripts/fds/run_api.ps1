# 준실시간 스코어 API 기동 (번들 경로는 환경변수로 선택)
#   $env:FDS_BUNDLE_PATH = "outputs\fds\model_bundle_open_full.joblib"
#   .\scripts\fds\run_api.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not $env:FDS_BUNDLE_PATH) {
    $Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $env:FDS_BUNDLE_PATH = Join-Path $Root "outputs\fds\model_bundle_open_full.joblib"
}
& py -3 -m uvicorn api_score_app:app --host 127.0.0.1 --port 8765
