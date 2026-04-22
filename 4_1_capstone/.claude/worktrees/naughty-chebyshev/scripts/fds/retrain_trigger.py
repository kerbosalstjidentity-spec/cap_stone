"""
드리프트 감지 → 자동 재학습 트리거 (MLOps).

사용법:
  python scripts/fds/retrain_trigger.py \
    --drift-report outputs/fds/drift_train_vs_test.json \
    --schema schemas/fds/schema_v1_open.yaml \
    --train-csv data/open/val.csv \
    --bundle-out outputs/fds/model_bundle_open_cv.joblib \
    [--cv-folds 5] \
    [--dry-run]

로직:
  1. drift JSON 읽기
  2. 특성별 PSI 확인: major (psi > 0.1) 또는 critical (psi > 0.25) 피처 수 카운트
  3. 트리거 조건: critical 피처 1개 이상 OR major 피처 3개 이상
  4. 조건 충족 시 → subprocess로 train_export_rf.py 호출
  5. 결과를 JSON으로 출력 (트리거 여부, 사유, 재학습 명령어)

--dry-run: 실제 학습 없이 트리거 여부만 출력.

drift JSON 지원 형식:
  A) per_column 배열: [{"column": "V1", "psi": 0.03, ...}, ...]
  B) psi_per_feature 딕트: {"V1": 0.03, "V2": 0.28, ...}
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PSI_MAJOR_THRESHOLD = 0.1
PSI_CRITICAL_THRESHOLD = 0.25


def _extract_psi_per_feature(drift_data: dict) -> dict[str, float]:
    """drift JSON에서 피처별 PSI 딕트를 추출한다.

    형식 A (per_column 배열) 또는 형식 B (psi_per_feature 딕트) 모두 지원.
    """
    # 형식 B: psi_per_feature 딕트
    if "psi_per_feature" in drift_data:
        raw = drift_data["psi_per_feature"]
        return {str(k): float(v) for k, v in raw.items()}

    # 형식 A: per_column 배열
    if "per_column" in drift_data:
        result: dict[str, float] = {}
        for entry in drift_data["per_column"]:
            col = str(entry.get("column", "UNKNOWN"))
            psi_val = float(entry.get("psi", 0.0))
            result[col] = psi_val
        return result

    raise ValueError(
        "drift JSON에서 PSI 데이터를 찾을 수 없습니다. "
        "'psi_per_feature' 딕트 또는 'per_column' 배열이 필요합니다."
    )


def _classify_features(
    psi_per_feature: dict[str, float],
) -> tuple[list[str], list[str]]:
    """각 피처를 major/critical로 분류한다.

    반환: (major_features, critical_features)
    critical은 psi > 0.25, major는 psi > 0.1 (critical 제외)
    """
    major: list[str] = []
    critical: list[str] = []
    for feat, psi in psi_per_feature.items():
        if psi > PSI_CRITICAL_THRESHOLD:
            critical.append(feat)
        elif psi > PSI_MAJOR_THRESHOLD:
            major.append(feat)
    return major, critical


def _build_retrain_command(
    schema: Path,
    train_csv: Path,
    bundle_out: Path,
    cv_folds: int | None,
) -> list[str]:
    """train_export_rf.py 호출 커맨드 빌드."""
    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parent / "train_export_rf.py"),
        "--schema", str(schema),
        "--train-csv", str(train_csv),
        "--out", str(bundle_out),
    ]
    if cv_folds is not None:
        cmd += ["--cv-folds", str(cv_folds)]
    return cmd


def main() -> None:
    p = argparse.ArgumentParser(description="드리프트 감지 → 재학습 트리거")
    p.add_argument(
        "--drift-report",
        type=Path,
        required=True,
        help="drift JSON 경로 (outputs/fds/drift_train_vs_test.json)",
    )
    p.add_argument(
        "--schema",
        type=Path,
        required=True,
        help="schemas/fds/schema_v1_*.yaml",
    )
    p.add_argument(
        "--train-csv",
        type=Path,
        required=True,
        help="재학습에 사용할 CSV 경로",
    )
    p.add_argument(
        "--bundle-out",
        type=Path,
        required=True,
        help="재학습 모델 번들 저장 경로 (.joblib)",
    )
    p.add_argument(
        "--cv-folds",
        type=int,
        default=None,
        metavar="N",
        help="Stratified K-Fold CV fold 수 (미지정 시 전체 학습만)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 학습 없이 트리거 조건만 출력",
    )
    args = p.parse_args()

    # 1. drift JSON 읽기
    if not args.drift_report.exists():
        result = {
            "triggered": False,
            "reason": f"drift 리포트 파일을 찾을 수 없음: {args.drift_report}",
            "error": True,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    with args.drift_report.open(encoding="utf-8") as f:
        drift_data = json.load(f)

    # 2. 피처별 PSI 추출
    try:
        psi_per_feature = _extract_psi_per_feature(drift_data)
    except ValueError as e:
        result = {
            "triggered": False,
            "reason": str(e),
            "error": True,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    # 3. 심각도 분류
    major_features, critical_features = _classify_features(psi_per_feature)

    # 4. 트리거 조건 판단
    should_trigger = len(critical_features) >= 1 or len(major_features) >= 3

    trigger_reasons: list[str] = []
    if critical_features:
        trigger_reasons.append(
            f"critical PSI 피처 {len(critical_features)}개 (psi > {PSI_CRITICAL_THRESHOLD}): "
            + ", ".join(sorted(critical_features))
        )
    if len(major_features) >= 3:
        trigger_reasons.append(
            f"major PSI 피처 {len(major_features)}개 (psi > {PSI_MAJOR_THRESHOLD}): "
            + ", ".join(sorted(major_features))
        )

    retrain_cmd = _build_retrain_command(
        args.schema, args.train_csv, args.bundle_out, args.cv_folds
    )

    result: dict = {
        "triggered": should_trigger,
        "dry_run": args.dry_run,
        "drift_report": str(args.drift_report),
        "n_features_checked": len(psi_per_feature),
        "n_critical_features": len(critical_features),
        "n_major_features": len(major_features),
        "critical_features": sorted(critical_features),
        "major_features": sorted(major_features),
        "trigger_reasons": trigger_reasons if trigger_reasons else ["트리거 조건 미충족"],
        "retrain_command": retrain_cmd,
    }

    if not should_trigger:
        result["message"] = (
            f"재학습 불필요: critical={len(critical_features)}개, major={len(major_features)}개 "
            f"(임계: critical>=1 또는 major>=3)"
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0)

    # 5. 재학습 실행
    if args.dry_run:
        result["message"] = "dry-run 모드: 재학습 필요하지만 실제 실행 건너뜀"
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0)

    print(f"[retrain_trigger] 재학습 트리거: {' '.join(retrain_cmd)}")
    proc = subprocess.run(retrain_cmd, capture_output=False)

    result["retrain_exit_code"] = proc.returncode
    if proc.returncode == 0:
        result["message"] = "재학습 완료"
    else:
        result["message"] = f"재학습 실패 (exit code={proc.returncode})"

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
