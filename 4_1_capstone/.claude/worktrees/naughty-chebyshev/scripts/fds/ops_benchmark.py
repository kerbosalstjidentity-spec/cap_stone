"""
단일 프로세스 기준 처리량·지연(스코어링 구간) 벤치마크.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import joblib
import pandas as pd

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FDS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FDS_DIR.parents[1]
sys.path.insert(0, str(FDS_DIR))

from schema import FDSSchema  # noqa: E402
from scoring import score_prepared_frame  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="스코어링 처리량 벤치마크")
    p.add_argument("--schema", type=Path, required=True)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--nrows", type=int, default=20000)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--warmup", type=int, default=1)
    p.add_argument("--targets", type=Path, default=Path("policies/fds/ops_targets_v1.yaml"))
    args = p.parse_args()

    schema = FDSSchema.from_yaml(args.schema)
    bundle = joblib.load(args.bundle)
    df = pd.read_csv(args.input, nrows=args.nrows)
    df = schema.prepare_frame(df)
    n = len(df)

    for _ in range(args.warmup):
        score_prepared_frame(df, bundle)

    times: list[float] = []
    for _ in range(args.repeats):
        t0 = time.perf_counter()
        score_prepared_frame(df, bundle)
        times.append(time.perf_counter() - t0)

    best = min(times)
    rps = n / best
    ms_per = (best / n) * 1000.0

    print(f"rows={n:,}  repeats={args.repeats}  best_wall_sec={best:.4f}")
    print(f"throughput_rps={rps:,.1f}  ms_per_row={ms_per:.4f}")

    if args.targets.exists():
        import yaml

        with args.targets.open(encoding="utf-8") as f:
            tcfg = yaml.safe_load(f)
        lat = (tcfg.get("latency") or {}).get("target_ms_p99_per_transaction")
        thr = (tcfg.get("latency") or {}).get("minimum_throughput_rps")
        if lat is not None:
            print(f"  (목표 p99 ms/건 참고: {lat} — 단일 배치 평균과 직접 비교는 불가)")
        if thr is not None:
            ok = rps >= float(thr)
            print(f"  minimum_throughput_rps 목표 {thr}: {'충족' if ok else '미달'}")


if __name__ == "__main__":
    main()
