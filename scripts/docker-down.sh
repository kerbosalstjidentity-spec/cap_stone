#!/usr/bin/env bash
# 스택 정지 (-v 옵션 시 DB 볼륨까지 삭제)
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "-v" ] || [ "${1:-}" = "--volumes" ]; then
  echo "[down] 컨테이너 + 볼륨 제거..."
  docker compose down -v --remove-orphans
else
  echo "[down] 컨테이너 정지..."
  docker compose down
fi
