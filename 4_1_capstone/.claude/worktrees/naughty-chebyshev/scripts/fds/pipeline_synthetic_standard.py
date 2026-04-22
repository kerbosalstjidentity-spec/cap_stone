"""
합성 데이터 표준 파이프라인 (권장 순서).

실제 데이터(open/ieee-cis)가 없을 때 합성 데이터로 전체 FDS 파이프라인을 실행한다.

1) 합성 학습 데이터 생성 (--skip-gen 으로 생략 가능)
2) 앙상블(RF+LGBM) CV 학습·번들 생성
3) mock 데이터로 배치 스코어링 + velocity 규칙 평가
4) 검토 큐 추출 + 운영 모니터 JSON
5) 드리프트 감지 (학습 vs mock)
6) 재학습 트리거 dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_V1 = ROOT / "schemas" / "fds" / "schema_v1_open.yaml"
SCHEMA_V2 = ROOT / "schemas" / "fds" / "schema_v2_open_mock.yaml"
DATA_FDS = ROOT / "data" / "fds"
OUT = ROOT / "outputs" / "fds"
POLICIES = ROOT / "policies" / "fds"


def run(cmd: list[str]) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def main() -> None:
    p = argparse.ArgumentParser(description="합성 데이터 표준 FDS 파이프라인")
    p.add_argument(
        "--skip-gen",
        action="store_true",
        help="합성 데이터 생성 건너뜀 (이미 data/fds/synthetic_train.csv 존재 시)",
    )
    p.add_argument("--cv-folds", type=int, default=5, metavar="N", help="CV fold 수 (기본 5)")
    p.add_argument(
        "--nrows-train",
        type=int,
        default=30000,
        help="학습 합성 데이터 행 수 (기본 30,000)",
    )
    p.add_argument(
        "--fraud-rate",
        type=float,
        default=0.015,
        help="합성 데이터 사기 비율 (기본 0.015 = 1.5%%)",
    )
    p.add_argument("--skip-drift", action="store_true", help="드리프트 단계 생략")
    args = p.parse_args()

    py = sys.executable

    # ── 단계 1: 합성 데이터 생성 ─────────────────────────────────────────────
    if not args.skip_gen:
        print("\n[1/6] 합성 학습 데이터 생성")
        run([
            py, str(ROOT / "scripts" / "fds" / "build_mock_v2_dataset.py"),
            "--out", str(DATA_FDS / "synthetic_train.csv"),
            "--nrows", str(args.nrows_train),
            "--fraud-rate", str(args.fraud_rate),
            "--realistic",
        ])
        run([
            py, str(ROOT / "scripts" / "fds" / "build_mock_v2_dataset.py"),
            "--out", str(DATA_FDS / "mock_transactions_v2.csv"),
            "--nrows", "5000",
            "--fraud-rate", str(args.fraud_rate),
            "--realistic",
            "--seed", "99",
        ])
    else:
        print("\n[1/6] 합성 데이터 생성 건너뜀 (--skip-gen)")

    # ── 단계 2: 앙상블 CV 학습 ───────────────────────────────────────────────
    print("\n[2/6] RF+LGBM 앙상블 CV 학습")
    bundle_path = OUT / "model_bundle_synthetic_ensemble.joblib"
    metrics_path = OUT / f"metrics_synthetic_ensemble_cv{args.cv_folds}.json"
    run([
        py, str(ROOT / "scripts" / "fds" / "train_export_ensemble.py"),
        "--schema", str(SCHEMA_V1),
        "--train-csv", str(DATA_FDS / "synthetic_train.csv"),
        "--out", str(bundle_path),
        "--cv-folds", str(args.cv_folds),
        "--metrics-out", str(metrics_path),
    ])

    # ── 단계 3: 배치 스코어링 + velocity 규칙 ───────────────────────────────
    print("\n[3/6] 배치 스코어링 + velocity 규칙")
    decisions_path = OUT / "decisions_synthetic.csv"
    run([
        py, str(ROOT / "scripts" / "fds" / "batch_run.py"),
        "--bundle", str(bundle_path),
        "--schema", str(SCHEMA_V2),
        "--input", str(DATA_FDS / "mock_transactions_v2.csv"),
        "--rules", str(POLICIES / "rules_v2_velocity.yaml"),
        "--thresholds", str(POLICIES / "thresholds_v1.yaml"),
        "--output", str(decisions_path),
    ])

    # ── 단계 4: 검토 큐 추출 + 모니터 ───────────────────────────────────────
    print("\n[4/6] 검토 큐 추출 + 운영 모니터")
    run([
        py, str(ROOT / "scripts" / "fds" / "export_review_queue.py"),
        "--decisions", str(decisions_path),
        "--output", str(OUT / "review_queue_synthetic.csv"),
    ])
    run([
        py, str(ROOT / "scripts" / "fds" / "ops_monitor.py"),
        "--decisions", str(decisions_path),
        "--json-out", str(OUT / "monitor_synthetic.json"),
    ])

    # ── 단계 5: 드리프트 감지 ────────────────────────────────────────────────
    if not args.skip_drift:
        print("\n[5/6] 드리프트 감지 (학습 vs mock)")
        drift_path = OUT / "drift_synthetic.json"
        run([
            py, str(ROOT / "scripts" / "fds" / "ops_drift.py"),
            "--ref", str(DATA_FDS / "synthetic_train.csv"),
            "--current", str(DATA_FDS / "mock_transactions_v2.csv"),
            "--json-out", str(drift_path),
        ])
    else:
        drift_path = OUT / "drift_synthetic.json"
        print("\n[5/6] 드리프트 감지 건너뜀 (--skip-drift)")

    # ── 단계 6: 재학습 트리거 dry-run ────────────────────────────────────────
    print("\n[6/6] 재학습 트리거 dry-run")
    if drift_path.exists():
        run([
            py, str(ROOT / "scripts" / "fds" / "retrain_trigger.py"),
            "--drift-report", str(drift_path),
            "--schema", str(SCHEMA_V1),
            "--train-csv", str(DATA_FDS / "synthetic_train.csv"),
            "--bundle-out", str(OUT / "model_bundle_retrained.joblib"),
            "--cv-folds", str(args.cv_folds),
            "--dry-run",
        ])
    else:
        print("  드리프트 리포트 없음 — 재학습 트리거 건너뜀")

    print(
        f"\n완료. 주요 산출물:\n"
        f"  모델  : {bundle_path.name}\n"
        f"  지표  : {metrics_path.name}\n"
        f"  결정  : {decisions_path.name}\n"
        f"  드리프트: drift_synthetic.json\n"
        f"  모니터 : monitor_synthetic.json"
    )


if __name__ == "__main__":
    main()
