"""배치 단위 근사 기여 특성 요약 (전역 중요도 × 로컬 편차 가중).

[방법 설명]
  score_i_j = importance_j × (1 + |z_i_j|)
    - importance_j : RF feature_importances_ (전체 훈련 데이터 기준 전역값)
    - z_i_j        : 배치 내 j번째 특성의 i번째 행 표준화값

[한계]
  - SHAP 같은 per-sample 기여도(Shapley value)가 아닙니다.
  - 전역 중요도가 높은 특성은 항상 상위에 오를 가능성이 높습니다.
  - 개별 거래의 정확한 원인 분석이 아닌, 1차 필터링용 참고 지표로만 사용하세요.
  - 정밀한 설명이 필요하다면 ops_shap_sample.py (TreeExplainer) 사용을 권장합니다.
"""

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
    각 행마다 importance × (1 + |z|) 가 큰 순으로 top_k 특성 이름을 나열.

    z는 배치 내 컬럼별 표준화(평균 0, 표준편차 1) 기준.
    반환값 형식: "V3;V12;V7" (세미콜론 구분)

    주의: 이 값은 근사치입니다. SHAP 기반 정확한 설명은 ops_shap_sample.py 참고.
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
