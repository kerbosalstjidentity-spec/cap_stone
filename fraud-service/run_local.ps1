# fraud-service 로컬 기동 (8000이 이미 쓰이면 8010 기본)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

if (-not $env:PORT) { $env:PORT = "8010" }
Write-Host ""
Write-Host "  관리 페이지: http://127.0.0.1:$env:PORT/admin"
Write-Host "  API 문서:    http://127.0.0.1:$env:PORT/docs"
Write-Host "  (8000을 쓰려면 다른 터미널에서 uvicorn/다른 앱을 종료한 뒤 `$env:PORT='8000' )"
Write-Host ""

# PowerShell이 uvicorn의 INFO 로그(stderr)를 빨간 오류로 보여줄 수 있음 — 실제 오류는 마지막 줄 확인
& py -3 -m uvicorn app.main:app --host 127.0.0.1 --port $env:PORT
