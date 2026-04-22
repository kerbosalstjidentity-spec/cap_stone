"""
IEEE-CIS Fraud Detection 표준 프로세스 (권장 순서).

사전 조건: data/ieee-cis/ 에 train_transaction.csv, test_transaction.csv 배치
           (Kaggle IEEE-CIS Fraud Detection 데이터셋)

1) train CV 평가(기본 5-fold) 또는 홀드아웃으로 학습·번들 + 지표 JSON
   - 사기 건수(~57,000건)가 충분하므로 CV/홀드아웃 모두 신뢰도 높음
2) train 전체로 학습·번들 (test 스코어링용)
3) test 전체 batch_run → 검토 큐 추출 → 모니터 JSON
4) train vs test 특성 드리프트 JSON

데이터 없이 테스트만 할 경우:
  python pipeline_ieee_cis_standard.py --help   (종료코드 0)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "fds" / "schema_v1_ieee_cis.yaml"
IEEE = ROOT / "data" / "ieee-cis"
OUT = ROOT / "outputs" / "fds"

# IEEE-CIS train/test 파일명 (Kaggle 기본 명칭)
TRAIN_CSV = IEEE / "train_transaction.csv"
TEST_CSV = IEEE / "test_transaction.csv"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def _assert_data_exists() -> None:
    missing = [str(p) for p in (TRAIN_CSV, TEST_CSV, SCHEMA) if not p.exists()]
    if missing:
        print(
            "[오류] 아래 파일이 없습니다. data/ieee-cis/ 에 Kaggle CSV를 배치하세요:",
            file=sys.stderr,
        )
        for m in missing:
            print(f"  {m}", file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    p = argparse.ArgumentParser(
        description="IEEE-CIS 표준 FDS 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "예시:\n"
            "  python pipeline_ieee_cis_standard.py\n"
            "  python pipeline_ieee_cis_standard.py --cv-folds 3 --skip-drift\n"
            "  python pipeline_ieee_cis_standard.py --holdout 0.2\n"
        ),
    )

    eval_grp = p.add_mutually_exclusive_group()
    eval_grp.add_argument(
        "--cv-folds",
        type=int,
        default=5,
        metavar="N",
        help="평가 방식: Stratified K-Fold CV (기본값=5). 대용량이므로 --cv-folds 3도 충분.",
    )
    eval_grp.add_argument(
        "--holdout",
        type=float,
        default=None,
        metavar="FRAC",
        help="평가 방식: stratified 홀드아웃 비율 (예: 0.2). 사기 건수 충분하여 신뢰도 높음.",
    )

    p.add_argument("--skip-drift", action="store_true", help="드리프트 단계 생략(시간 절약)")
    p.add_argument(
        "--drift-ref-nrows",
        type=int,
        default=50000,
        help="드리프트 참조·현재 각각 상한 (기본값=50000, 메모리·시간 절약)",
    )
    p.add_argument(
        "--train-nrows",
        type=int,
        default=None,
        help="학습 데이터 행 수 제한 (빠른 실험용). 미지정 시 전체 사용.",
    )
    args = p.parse_args()

    _assert_data_exists()

    py = sys.executable

    # ── 단계 1: 평가 번들 ─────────────────────────────────────────────────────
    eval_cmd = [
        py,
        str(ROOT / "scripts" / "fds" / "train_export_rf.py"),
        "--schema", str(SCHEMA),
        "--train-csv", str(TRAIN_CSV),
    ]
    if args.train_nrows:
        eval_cmd += ["--nrows", str(args.train_nrows)]

    if args.holdout is not None:
        eval_cmd += [
            "--holdout-fraction", str(args.holdout),
            "--out", str(OUT / "model_bundle_ieee_cis_eval.joblib"),
            "--metrics-out", str(OUT / f"metrics_ieee_cis_holdout{int(args.holdout*100)}.json"),
        ]
    else:
        eval_cmd += [
            "--cv-folds", str(args.cv_folds),
            "--out", str(OUT / "model_bundle_ieee_cis_cv.joblib"),
            "--metrics-out", str(OUT / f"metrics_ieee_cis_cv{args.cv_folds}.json"),
        ]
    run(eval_cmd)

    # ── 단계 2: 전체 학습 번들 (test 스코어링용) ─────────────────────────────
    full_cmd = [
        py,
        str(ROOT / "scripts" / "fds" / "train_export_rf.py"),
        "--schema", str(SCHEMA),
        "--train-csv", str(TRAIN_CSV),
        "--out", str(OUT / "model_bundle_ieee_cis_full.joblib"),
    ]
    if args.train_nrows:
        full_cmd += ["--nrows", str(args.train_nrows)]
    run(full_cmd)

    # ── 단계 3: batch_run → 큐 추출 → 모니터 ────────────────────────────────
    run(
        [
            py,
            str(ROOT / "scripts" / "fds" / "batch_run.py"),
            "--schema", str(SCHEMA),
            "--input", str(TEST_CSV),
            "--bundle", str(OUT / "model_bundle_ieee_cis_full.joblib"),
            "--output", str(OUT / "decisions_ieee_cis_test_full.csv"),
        ]
    )
    run(
        [
            py,
            str(ROOT / "scripts" / "fds" / "export_review_queue.py"),
            "--decisions", str(OUT / "decisions_ieee_cis_test_full.csv"),
            "--output", str(OUT / "review_queue_ieee_cis_test_full.csv"),
        ]
    )
    run(
        [
            py,
            str(ROOT / "scripts" / "fds" / "ops_monitor.py"),
            "--decisions", str(OUT / "decisions_ieee_cis_test_full.csv"),
            "--json-out", str(OUT / "monitor_ieee_cis_test_full.json"),
        ]
    )

    # ── 단계 4: 드리프트 ─────────────────────────────────────────────────────
    if not args.skip_drift:
        run(
            [
                py,
                str(ROOT / "scripts" / "fds" / "ops_drift.py"),
                "--ref", str(TRAIN_CSV),
                "--current", str(TEST_CSV),
                "--ref-nrows", str(args.drift_ref_nrows),
                "--current-nrows", str(args.drift_ref_nrows),
                "--sample-seed", "42",
                "--json-out", str(OUT / "drift_ieee_cis_train_vs_test.json"),
            ]
        )

    metrics_file = (
        f"metrics_ieee_cis_cv{args.cv_folds}.json"
        if args.holdout is None
        else f"metrics_ieee_cis_holdout{int(args.holdout * 100)}.json"
    )
    print(
        f"\n완료. 산출: outputs/fds/ — {metrics_file}, "
        "model_bundle_ieee_cis_*.joblib, decisions_ieee_cis_test_full.csv, "
        "review_queue_ieee_cis_test_full.csv, monitor_ieee_cis_test_full.json"
    )


if __name__ == "__main__":
    main()
