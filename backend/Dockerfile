FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# Python 의존성 (torch 제외 — 선택적 의존성, ~3 GB 절약)
COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

# 앱 소스
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .

EXPOSE 8020

# 포트는 배포 플랫폼이 주는 $PORT 사용(없으면 8020) — 로컬 compose 와 Render 양쪽 호환
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8020}"]
