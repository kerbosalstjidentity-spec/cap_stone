#!/usr/bin/env bash
# consume-pattern 전체 스택 실행 (Docker Compose)
# 사용: bash scripts/docker-up.sh [--rebuild] [--clean] [--logs]

set -euo pipefail

cd "$(dirname "$0")/.."

REBUILD=0
CLEAN=0
LOGS=0
for arg in "$@"; do
  case "$arg" in
    --rebuild) REBUILD=1 ;;
    --clean)   CLEAN=1 ;;
    --logs)    LOGS=1 ;;
    -h|--help)
      echo "옵션: --rebuild(이미지 재빌드) --clean(볼륨까지 제거 후 재시작) --logs(실행 후 로그 팔로우)"
      exit 0 ;;
  esac
done

echo "==================================================="
echo "  consume-pattern Docker 스택 시작"
echo "==================================================="

if ! command -v docker >/dev/null 2>&1; then
  echo "[오류] docker가 설치되어 있지 않습니다. Docker Desktop을 먼저 설치하세요." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "[오류] docker compose를 찾을 수 없습니다." >&2
  exit 1
fi

MODEL_DIR="./fds-research/outputs/fds"
MODEL_FILE="$MODEL_DIR/model_bundle_open_full.joblib"
if [ ! -f "$MODEL_FILE" ]; then
  echo "[경고] 모델 번들을 찾을 수 없습니다: $MODEL_FILE"
  echo "        fraud-service가 정상 동작하지 않을 수 있습니다."
fi

if [ "$CLEAN" = "1" ]; then
  echo "[clean] 기존 컨테이너/볼륨 제거..."
  $DC down -v --remove-orphans
fi

BUILD_FLAG=""
[ "$REBUILD" = "1" ] && BUILD_FLAG="--build"

echo "[up] 스택 기동..."
$DC up -d $BUILD_FLAG

echo ""
echo "==================================================="
echo "  서비스 상태"
echo "==================================================="
$DC ps

cat <<EOF

[서비스 주소]
  프론트엔드:     http://localhost:3020
  Backend API:   http://localhost:8020/docs
  fraud-service: http://localhost:8010/health

[유용한 명령]
  로그 보기:   $DC logs -f
  정지:        $DC down
  완전 초기화: $DC down -v

EOF

if [ "$LOGS" = "1" ]; then
  $DC logs -f
fi
