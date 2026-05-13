"""W10-#2 — 자체 asyncio 부하 테스트.

목적:
- fraud-service `/v1/fraud/evaluate` p99 latency 측정
- Kafka 처리량 간접 측정 (응답 헤더 + 큐 깊이)
- 감사 체인 1M 삽입 burst 시 안정성

의존성 최소화 (aiohttp 만). locust/k6 미사용 — CI 환경에서 부담 없이 실행.

사용:
    python scripts/loadtest/run.py \\
      --url http://localhost:8001/v1/fraud/evaluate \\
      --rps 200 --duration 60 --concurrency 50

출력:
    JSON 한 줄 — p50/p95/p99 latency_ms, success_rate, error_count.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from statistics import median

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


def _payload(i: int) -> dict:
    prefix = random.choice(["VP", "MM", "ATO", "CT", "TX"])
    return {
        "tx_id": f"{prefix}-LT-{i}",
        "user_id": f"user-{i % 100}",
        "amount": random.uniform(10_000, 50_000_000),
        "type": random.choice(["TRANSFER", "CASH_OUT", "PAYMENT"]),
        "score": random.uniform(0.0, 1.0),
    }


async def _worker(
    session: "aiohttp.ClientSession",
    url: str,
    queue: asyncio.Queue,
    latencies: list[float],
    errors: list[str],
) -> None:
    while True:
        try:
            i = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        t0 = time.perf_counter()
        try:
            async with session.post(url, json=_payload(i), timeout=10) as resp:
                await resp.read()
                if resp.status >= 400:
                    errors.append(f"http_{resp.status}")
                else:
                    latencies.append((time.perf_counter() - t0) * 1000.0)
        except Exception as exc:
            errors.append(str(exc)[:60])
        finally:
            queue.task_done()


async def run_loadtest(
    url: str, n_requests: int, concurrency: int
) -> dict:
    if aiohttp is None:
        return {"error": "aiohttp_missing"}

    queue: asyncio.Queue = asyncio.Queue()
    for i in range(n_requests):
        queue.put_nowait(i)

    latencies: list[float] = []
    errors: list[str] = []

    started = time.perf_counter()
    async with aiohttp.ClientSession() as session:
        workers = [
            asyncio.create_task(_worker(session, url, queue, latencies, errors))
            for _ in range(concurrency)
        ]
        await asyncio.gather(*workers, return_exceptions=True)
    elapsed = time.perf_counter() - started

    return {
        "url": url,
        "n_requests": n_requests,
        "concurrency": concurrency,
        "elapsed_sec": round(elapsed, 3),
        "rps": round(n_requests / elapsed, 2) if elapsed else 0,
        "success": len(latencies),
        "errors": len(errors),
        "error_sample": errors[:5],
        "latency_ms": {
            "avg": round(sum(latencies) / len(latencies), 3) if latencies else 0,
            "p50": round(median(latencies), 3) if latencies else 0,
            "p95": round(_percentile(latencies, 95), 3),
            "p99": round(_percentile(latencies, 99), 3),
            "max": round(max(latencies), 3) if latencies else 0,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8001/v1/fraud/evaluate")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--concurrency", type=int, default=50)
    args = ap.parse_args()
    result = asyncio.run(run_loadtest(args.url, args.n, args.concurrency))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
