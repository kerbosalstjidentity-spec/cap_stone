FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY models ./models
COPY policies ./policies

ENV PYTHONUNBUFFERED=1
EXPOSE 8010

# 포트는 배포 플랫폼이 주는 $PORT 사용(없으면 8010) — 로컬 compose 와 Render 양쪽 호환
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8010}"]
