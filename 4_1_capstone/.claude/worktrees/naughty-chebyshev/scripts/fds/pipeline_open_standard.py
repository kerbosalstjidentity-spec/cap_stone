"""
open 데이터 표준 프로세스 (권장 순서).

1) val CV 평가(기본 5-fold) 또는 홀드아웃으로 학습·번들 + 지표 JSON
   - 사기 건수(30건)가 적으므로 --cv-folds 5(기본값) 사용 권장
   - 단순 홀드아웃은 --holdout 옵션으로 사용 가능 (사기 ≈6건, 신뢰도 낮음)
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

    eval_grp = p.add_mutually_exclusive_group()
    eval_grp.add_argument(
        "--cv-folds",
        type=int,
        default=5,
        metavar="N",
        help="평가 방식: Stratified K-Fold CV (기본값=5, 권장). 사기 건수 부족 시 홀드아웃보다 신뢰도 높음.",
    )
    eval_grp.add_argument(
        "--holdout",
        type=float,
        default=None,
        metavar="FRAC",
        help="평가 방식: stratified 홀드아웃 비율 (예: 0.2). 사기 ≈6건으로 신뢰도 낮음.",
    )

    p.add_argument("--skip-drift", action="store_true", help="드리프트 단계 생략(대용량 시)")
    p.add_argument(
        "--drift-ref-nrows",
        type=int,
        default=20000,
        help="드리프트 참조·현재 각각 상한 (메모리·시간 절약)",
    )
    args = p.parse_args()

    py = sys.executable

    # ── 단계 1: 평가 번들 ─────────────────────────────────────────────────────
    if args.holdout is not None:
        print(
            f"\n[경고] --holdout {args.holdout} 사용 중: 사기 건수 ≈ {round(30 * args.holdout)}건 "
            f"— 지표 신뢰도 낮음. --cv-folds 사용 권장.\n"
        )
        eval_cmd = [
            py,
            str(ROOT / "scripts" / "fds" / "train_export_rf.py"),
            "--schema", str(SCHEMA),
            "--train-csv", str(OPEN / "val.csv"),
            "--holdout-fraction", str(args.holdout),
            "--out", str(OUT / "model_bundle_open_eval.joblib"),
            "--metrics-out", str(OUT / "metrics_open_val_holdout.json"),
        ]
    else:
        eval_cmd = [
            py,
            str(ROOT / "scripts" / "fds" / "train_export_rf.py"),
            "--schema", str(SCHEMA),
            "--train-csv", str(OPEN / "val.csv"),
            "--cv-folds", str(args.cv_folds),
            "--out", str(OUT / "model_bundle_open_cv.joblib"),
            "--metrics-out", str(OUT / f"metrics_open_cv{args.cv_folds}.json"),
        ]
    run(eval_cmd)

    # ── 단계 2: 전체 학습 번들 (test 스코어링용) ─────────────────────────────
    run(
        [
            py,
            str(ROOT / "scripts" / "fds" / "train_export_rf.py"),
            "--schema", str(SCHEMA),
            "--train-csv", str(OPEN / "val.csv"),
            "--out", str(OUT / "model_bundle_open_full.joblib"),
        ]
    )

    # ── 단계 3: batch_run → 큐 추출 → 모니터 ────────────────────────────────
    run(
        [
            py,
            str(ROOT / "scripts" / "fds" / "batch_run.py"),
            "--schema", str(SCHEMA),
            "--input", str(OPEN / "test.csv"),
            "--bundle", str(OUT / "model_bundle_open_full.joblib"),
            "--output", str(OUT / "decisions_open_test_full.csv"),
        ]
    )
    run(
        [
            py,
            str(ROOT / "scripts" / "fds" / "export_review_queue.py"),
            "--decisions", str(OUT / "decisions_open_test_full.csv"),
            "--output", str(OUT / "review_queue_open_test_full.csv"),
        ]
    )
    run(
        [
            py,
            str(ROOT / "scripts" / "fds" / "ops_monitor.py"),
            "--decisions", str(OUT / "decisions_open_test_full.csv"),
            "--json-out", str(OUT / "monitor_open_test_full.json"),
        ]
    )

    # ── 단계 4: 드리프트 ─────────────────────────────────────────────────────
    if not args.skip_drift:
        run(
            [
                py,
                str(ROOT / "scripts" / "fds" / "ops_drift.py"),
                "--ref", str(OPEN / "train.csv"),
                "--current", str(OPEN / "test.csv"),
                "--ref-nrows", str(args.drift_ref_nrows),
                "--current-nrows", str(args.drift_ref_nrows),
                "--sample-seed", "42",
                "--json-out", str(OUT / "drift_train_vs_test.json"),
            ]
        )

    metrics_file = (
        f"metrics_open_cv{args.cv_folds}.json"
        if args.holdout is None
        else "metrics_open_val_holdout.json"
    )
    print(
        f"\n완료. 산출: outputs/fds/ — {metrics_file}, "
        "model_bundle_open_*.joblib, decisions_open_test_full.csv, "
        "review_queue_open_test_full.csv, monitor_open_test_full.json"
    )


if __name__ == "__main__":
    main()
