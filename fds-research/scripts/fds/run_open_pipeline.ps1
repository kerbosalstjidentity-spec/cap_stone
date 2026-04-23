# Windows 작업 스케줄러용 예시: 프로젝트 루트에서 open 표준 FDS 파이프라인
# 사용법: PowerShell에서 .\scripts\fds\run_open_pipeline.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $Root
& py -3 scripts/fds/pipeline_open_standard.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "OK: outputs/fds/ 산출물 갱신됨"
