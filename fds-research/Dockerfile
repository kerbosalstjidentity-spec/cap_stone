# W6-#6 — 학습 컨테이너 (Python 3.11 slim)
#
# 빌드:
#   docker build -t paywise-train -f fds-research/Dockerfile .
#
# 실행 (PaySim 학습):
#   docker run --rm \
#     -v $(pwd)/fds-research/data:/app/data \
#     -v $(pwd)/fds-research/outputs:/app/outputs \
#     paywise-train \
#     python train_paysim.py --csv /app/data/paysim.csv --out /app/outputs/bundle.joblib
#
# CI 에서는 기본 entrypoint 가 `python train_paysim.py --help` 로 헬스 체크.

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# scikit-learn / pandas / xgboost 빌드에 필요한 최소 시스템 의존
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements 만 먼저 복사 → 레이어 캐시 활용
COPY fds-research/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 학습 스크립트 + Makefile + 보조 모듈
COPY fds-research/ /app/

# 산출 디렉터리는 볼륨 마운트 가정
VOLUME ["/app/data", "/app/outputs", "/app/logs"]

# 기본 명령: 헬스 체크 (실제 실행은 docker run CMD 으로 오버라이드)
CMD ["python", "train_paysim.py", "--help"]
