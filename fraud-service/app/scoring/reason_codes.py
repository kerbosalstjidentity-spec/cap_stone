"""상위 기여 특성 이유 코드 — capstone reason_codes.py 이식 + 한글 설명 생성."""

from __future__ import annotations

import numpy as np


def top_feature_reasons(
    X: np.ndarray,
    feature_names: list[str],
    importances: np.ndarray,
    *,
    top_k: int = 3,
) -> list[str]:
    """
    각 행마다 importance * |z| 가 큰 순으로 top_k 특성 이름을 나열.
    z는 배치 내 컬럼별 표준화(평균 0, 표준편차 1) 기준.
    단건 입력(행 1개)이면 z=0으로 순수 importance 순.
    """
    mu = X.mean(axis=0)
    std = np.maximum(X.std(axis=0), 1e-9)
    z = np.abs((X - mu) / std)
    imp = np.asarray(importances, dtype=float)
    n = X.shape[0]
    out: list[str] = []
    for i in range(n):
        score = imp * (1.0 + z[i])
        idx = np.argsort(-score)[:top_k]
        out.append(";".join(feature_names[j] for j in idx))
    return out


def single_reason(
    x_row: np.ndarray,
    feature_names: list[str],
    importances: np.ndarray,
    *,
    top_k: int = 3,
) -> str:
    """단건 1행 → reason_code 문자열."""
    X = x_row.reshape(1, -1)
    return top_feature_reasons(X, feature_names, importances, top_k=top_k)[0]


def reason_code_to_human(
    x_row: np.ndarray,
    feature_names: list[str],
    importances: np.ndarray,
    *,
    top_k: int = 3,
) -> list[str]:
    """
    reason_code 피처들에 대해 사람이 읽을 수 있는 한글 설명 생성.
    z-score 기반으로 '평균 대비 N배' 또는 '하위/상위 X%' 형식.
    """
    X = x_row.reshape(1, -1)
    mu = X.mean(axis=0)   # 단건이라 배치 평균은 값 자체
    std = np.maximum(X.std(axis=0), 1e-9)
    imp = np.asarray(importances, dtype=float)
    z = np.abs((X[0] - mu) / std)
    score = imp * (1.0 + z)
    idx = np.argsort(-score)[:top_k]

    descriptions = []
    for j in idx:
        name = feature_names[j]
        val = float(X[0, j])
        imp_rank = float(imp[j])
        z_val = float(z[j])

        if abs(val) < 1e-6:
            desc = f"{name}: 값이 0에 가깝습니다 (중요도 {imp_rank:.3f})."
        elif z_val > 3.0:
            desc = f"{name}: 정상 분포 대비 {z_val:.1f}σ 이상 벗어났습니다 (극단값)."
        elif z_val > 1.5:
            desc = f"{name}: 평균에서 {z_val:.1f}σ 벗어났습니다 (비정상 패턴)."
        else:
            desc = f"{name}: 중요도 {imp_rank:.3f}로 판단에 영향을 미쳤습니다."
        descriptions.append(desc)

    return descriptions
