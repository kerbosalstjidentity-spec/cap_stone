"""
open 데이터 표준 프로세스 (권장 순서).

1) val stratified 홀드아웃(기본 20%)으로 학습·번들 + 정직한 지표 JSON
2) val 전체로 학습·번들 (test 스코어링용)
3) test 전체 batch_run → 검토 큐 추출 → 모니터 JSON
4) train vs test 특성 드리프트 JSON (샘플 전량은 행 수에 비례해 오래 걸릴 수 있음)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "fds" / "schema_v1_open.yaml"
OPEN = ROOT / "data" / "open"
OUT = ROOT / "outputs" / "fds"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def main() -> None:
    p = argparse.ArgumentParser(description="open 표준 FDS 파이프라인")
    p.add_argument("--holdout", type=float, default=0.2)
    p.add_argument("--skip-drift", action="store_true", help="드리프트 단계 생략(대용량 시)")
    p.add_argument(
        "--drift-ref-nrows",
        type=int,
        default=20000,
        help="드리프트 참조·현재 각각 상한 (메모리·시간 절약)",
    )
    args = p.parse_args()

    py = sys.executable
    ho = str(args.holdout)

    run(
        [
            py,
            str(ROOT / "scripts" / "fds" / "train_export_rf.py"),
            "--schema",
            str(SCHEMA),
            "--train-csv",
            str(OPEN / "val.csv"),
            "--holdout-fraction",
            ho,
            "--out",
            str(OUT / "model_bundle_open_eval.joblib"),
            "--metrics-out",
            str(OUT / "metrics_open_val_holdout.json"),
        ]
    )
    run(
        [
            py,
            str(ROOT / "scripts" / "fds" / "train_export_rf.py"),
            "--schema",
            str(SCHEMA),
            "--train-csv",
            str(OPEN / "val.csv"),
            "--out",
            str(OUT / "model_bundle_open_full.joblib"),
        ]
    )
    run(
        [
            py,
            str(ROOT / "scripts" / "fds" / "batch_run.py"),
            "--schema",
            str(SCHEMA),
            "--input",
            str(OPEN / "test.csv"),
            "--bundle",
            str(OUT / "model_bundle_open_full.joblib"),
            "--output",
            str(OUT / "decisions_open_test_full.csv"),
        ]
    )
    run(
        [
            py,
            str(ROOT / "scripts" / "fds" / "export_review_queue.py"),
            "--decisions",
            str(OUT / "decisions_open_test_full.csv"),
            "--output",
            str(OUT / "review_queue_open_test_full.csv"),
        ]
    )
    run(
        [
            py,
            str(ROOT / "scripts" / "fds" / "ops_monitor.py"),
            "--decisions",
            str(OUT / "decisions_open_test_full.csv"),
            "--json-out",
            str(OUT / "monitor_open_test_full.json"),
        ]
    )
    if not args.skip_drift:
        run(
            [
                py,
                str(ROOT / "scripts" / "fds" / "ops_drift.py"),
                "--ref",
                str(OPEN / "train.csv"),
                "--current",
                str(OPEN / "test.csv"),
                "--ref-nrows",
                str(args.drift_ref_nrows),
                "--current-nrows",
                str(args.drift_ref_nrows),
                "--json-out",
                str(OUT / "drift_train_vs_test.json"),
            ]
        )

    print("\n완료. 산출: outputs/fds/ — metrics_open_val_holdout.json, model_bundle_open_*.joblib, "
          "decisions_open_test_full.csv, review_queue_open_test_full.csv, monitor_open_test_full.json")


if __name__ == "__main__":
    main()
