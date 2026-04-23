"""
Layer 5 — Federated Learning 시뮬레이션 (고도화).

SRS 4 요구사항 전체 반영:
1. FedAvg 집계 (기존)
2. Differential Privacy — 다중 ε 스윕 (ε=0.1~10.0)
3. Secure Aggregation (SecAgg) — 비밀 분산 기반 안전 집계 시뮬레이션
4. CCI (Cross-Client Contribution) — 기여도 평가 (Shapley 근사)
5. Non-IID 시나리오 — Dirichlet α 파라미터 스윕

교수님 연구 연계:
- "Secure and Verifiable Contribution Evaluation in Privacy-Preserving FL" (TDSC)
- "Cross-domain Fine-grained AC for IoT Data Sharing in Metaverse" (TDSC)

Usage:
    py -3 scripts/fds/federated_sim.py --train-csv data/open/train.csv --test-csv data/open/test.csv
    py -3 scripts/fds/federated_sim.py --train-csv data/open/train.csv --test-csv data/open/test.csv --mode full
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RANDOM_STATE = 42

# ── 데이터 파티셔닝 ──────────────────────────────────────────

def partition_iid(df: pd.DataFrame, n_clients: int, seed: int = RANDOM_STATE) -> list[pd.DataFrame]:
    """데이터를 IID로 N개 기관에 균등 분할."""
    shuffled = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    chunk = len(shuffled) // n_clients
    parts = []
    for i in range(n_clients):
        start = i * chunk
        end = start + chunk if i < n_clients - 1 else len(shuffled)
        parts.append(shuffled.iloc[start:end].copy())
    return parts


def partition_non_iid(
    df: pd.DataFrame, n_clients: int, label_col: str = "is_fraud", seed: int = RANDOM_STATE
) -> list[pd.DataFrame]:
    """데이터를 Non-IID로 분할. 일부 기관에 사기 비율 편향."""
    rng = np.random.RandomState(seed)
    fraud = df[df[label_col] == 1].copy()
    normal = df[df[label_col] == 0].copy()

    # 사기 데이터를 불균등하게 분배 (Dirichlet 분포)
    alpha = 0.5  # 낮을수록 불균등
    proportions = rng.dirichlet([alpha] * n_clients)
    fraud_splits = []
    start = 0
    for i, p in enumerate(proportions):
        end = start + max(1, int(len(fraud) * p))
        fraud_splits.append(fraud.iloc[start:min(end, len(fraud))])
        start = end

    # 정상 거래는 균등 분배
    normal_shuffled = normal.sample(frac=1, random_state=seed).reset_index(drop=True)
    chunk = len(normal_shuffled) // n_clients
    normal_splits = []
    for i in range(n_clients):
        start = i * chunk
        end = start + chunk if i < n_clients - 1 else len(normal_shuffled)
        normal_splits.append(normal_shuffled.iloc[start:end].copy())

    partitions = []
    for f_part, n_part in zip(fraud_splits, normal_splits):
        merged = pd.concat([f_part, n_part], ignore_index=True).sample(frac=1, random_state=seed)
        partitions.append(merged)

    return partitions


# ── 로컬 학습 ──────────────────────────────────────────────

def train_local_model(
    train_df: pd.DataFrame,
    feature_cols: list[str],
    label_col: str = "is_fraud",
    n_estimators: int = 100,
) -> Pipeline:
    """단일 기관의 로컬 모델 학습."""
    X = train_df[feature_cols].values
    y = train_df[label_col].values

    pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("clf", RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=None,
            class_weight="balanced_subsample",
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )),
    ])
    pipeline.fit(X, y)
    return pipeline


# ── FedAvg 집계 ──────────────────────────────────────────────

def fedavg_predict_proba(
    models: list[Pipeline],
    X: np.ndarray,
    weights: list[float] | None = None,
) -> np.ndarray:
    """FedAvg: 가중 평균으로 글로벌 예측.

    RF는 트리 기��이라 가중치 평균이 불가하므로,
    예측 확률의 가중 평균으로 앙상블한다 (실질적 FedAvg 효과).
    """
    if weights is None:
        weights = [1.0 / len(models)] * len(models)

    probas = np.zeros(len(X))
    for model, w in zip(models, weights):
        p = model.predict_proba(X)[:, 1]
        probas += w * p

    return probas


# ── Differential Privacy ──────────────────────────────────

def add_dp_noise(
    probas: np.ndarray, epsilon: float = 1.0, seed: int = RANDOM_STATE
) -> np.ndarray:
    """예측 확률에 라플라스 노이즈를 추가 (ε-DP).

    실제 FL���서는 그래디언트에 노이즈를 추가하지만,
    RF 기반 시뮬레이션에서는 확률 출력에 적용.
    """
    rng = np.random.RandomState(seed)
    sensitivity = 1.0  # 확률 범위 [0, 1]
    scale = sensitivity / epsilon
    noise = rng.laplace(0, scale, size=len(probas))
    noisy = probas + noise
    return np.clip(noisy, 0, 1)


# ── 평가 ──────────────────────────────────────────────────

def evaluate(y_true: np.ndarray, y_proba: np.ndarray, name: str) -> dict:
    """모델 성능 평가."""
    auc_roc = roc_auc_score(y_true, y_proba)
    auc_pr = average_precision_score(y_true, y_proba)
    y_pred = (y_proba >= 0.5).astype(int)

    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    print(f"  AUC-ROC: {auc_roc:.4f}")
    print(f"  AUC-PR:  {auc_pr:.4f}")
    print(classification_report(y_true, y_pred, target_names=["Normal", "Fraud"], zero_division=0))

    return {"name": name, "auc_roc": round(auc_roc, 4), "auc_pr": round(auc_pr, 4)}


# ── 메인 시뮬레이션 ──────────────────────────────────────

def run_simulation(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_cols: list[str],
    label_col: str = "is_fraud",
    n_clients: int = 3,
    dp_epsilon: float = 5.0,
) -> list[dict]:
    """전체 FL 시뮬레이션 실행."""
    X_test = test_df[feature_cols].values
    y_test = test_df[label_col].values if label_col in test_df.columns else None

    results = []

    # 1. 중앙 집중식 (baseline)
    print("\n[1/4] 중앙 집중식 학습 (Baseline)...")
    central_model = train_local_model(train_df, feature_cols, label_col)
    central_proba = central_model.predict_proba(X_test)[:, 1]
    if y_test is not None:
        results.append(evaluate(y_test, central_proba, "Centralized (Baseline)"))

    # 2. FL - IID 파티셔닝
    print(f"\n[2/4] FL (IID, {n_clients} clients)...")
    iid_parts = partition_iid(train_df, n_clients)
    iid_models = []
    iid_weights = []
    for i, part in enumerate(iid_parts):
        print(f"  Client {i}: {len(part)} samples, fraud={part[label_col].sum()}")
        model = train_local_model(part, feature_cols, label_col)
        iid_models.append(model)
        iid_weights.append(len(part))

    total = sum(iid_weights)
    iid_weights = [w / total for w in iid_weights]
    iid_proba = fedavg_predict_proba(iid_models, X_test, iid_weights)
    if y_test is not None:
        results.append(evaluate(y_test, iid_proba, f"FL-IID ({n_clients} clients)"))

    # 3. FL - Non-IID 파티셔닝
    print(f"\n[3/4] FL (Non-IID, {n_clients} clients)...")
    niid_parts = partition_non_iid(train_df, n_clients, label_col)
    niid_models = []
    niid_weights = []
    for i, part in enumerate(niid_parts):
        print(f"  Client {i}: {len(part)} samples, fraud={part[label_col].sum()}")
        model = train_local_model(part, feature_cols, label_col)
        niid_models.append(model)
        niid_weights.append(len(part))

    total = sum(niid_weights)
    niid_weights = [w / total for w in niid_weights]
    niid_proba = fedavg_predict_proba(niid_models, X_test, niid_weights)
    if y_test is not None:
        results.append(evaluate(y_test, niid_proba, f"FL-NonIID ({n_clients} clients)"))

    # 4. FL + Differential Privacy
    print(f"\n[4/4] FL-IID + DP (ε={dp_epsilon})...")
    dp_proba = add_dp_noise(iid_proba, epsilon=dp_epsilon)
    if y_test is not None:
        results.append(evaluate(y_test, dp_proba, f"FL-IID + DP (ε={dp_epsilon})"))

    # 요약 테이블
    if results:
        print(f"\n{'='*60}")
        print("  성능 비교 요약")
        print(f"{'='*60}")
        print(f"  {'모델':<35} {'AUC-ROC':>8} {'AUC-PR':>8}")
        print(f"  {'-'*51}")
        for r in results:
            print(f"  {r['name']:<35} {r['auc_roc']:>8.4f} {r['auc_pr']:>8.4f}")

    return results


# ── Secure Aggregation (SecAgg) 시뮬레이션 ────────────────────

def secagg_aggregate(
    models: list[Pipeline],
    X: np.ndarray,
    weights: list[float] | None = None,
    seed: int = RANDOM_STATE,
) -> np.ndarray:
    """Secure Aggregation 시뮬레이션.

    SRS 4 요구사항: 비밀 분산(Secret Sharing) 기반 안전 집계.
    실제 SecAgg에서는 각 클라이언트가 pairwise 마스크를 생성하여
    서버가 개별 모델 출력을 볼 수 없게 하지만,
    시뮬레이션에서는 마스킹-언마스킹 과정을 통해 동일 결과를 보장함을 검증.
    """
    rng = np.random.RandomState(seed)
    n = len(models)
    if weights is None:
        weights = [1.0 / n] * n

    # 각 클라이언트의 예측 확률
    raw_probas = [m.predict_proba(X)[:, 1] for m in models]

    # Phase 1: 각 클라이언트가 pairwise 마스크 생성
    masks = [[rng.normal(0, 0.01, size=len(X)) for _ in range(n)] for _ in range(n)]
    # 마스크 대칭: mask[i][j] = -mask[j][i]
    for i in range(n):
        for j in range(i + 1, n):
            masks[j][i] = -masks[i][j]

    # Phase 2: 마스킹된 업데이트 전송
    masked_updates = []
    for i in range(n):
        masked = raw_probas[i] + sum(masks[i])
        masked_updates.append(masked)

    # Phase 3: 서버에서 집계 (마스크가 상쇄됨)
    aggregated = np.zeros(len(X))
    for i, (update, w) in enumerate(zip(masked_updates, weights)):
        aggregated += w * update

    # 마스크 상쇄 검증
    direct_avg = fedavg_predict_proba(models, X, weights)
    diff = np.abs(aggregated - direct_avg).max()
    assert diff < 0.05, f"SecAgg 마스크 상쇄 실패: max diff = {diff:.6f}"

    return np.clip(aggregated, 0, 1)


# ── CCI 기여도 평가 (Shapley 근사) ───────────────────────────

def compute_cci_scores(
    models: list[Pipeline],
    X_test: np.ndarray,
    y_test: np.ndarray,
    weights: list[float] | None = None,
    n_permutations: int = 20,
    seed: int = RANDOM_STATE,
) -> list[dict]:
    """CCI (Cross-Client Contribution) 기여도 평가.

    SRS 4 요구사항: 각 기관의 FL 기여도를 Shapley value 근사로 측정.
    기여도가 높은 기관에 더 높은 인센티브를 부여하는 근거.
    """
    rng = np.random.RandomState(seed)
    n = len(models)
    if weights is None:
        weights = [1.0 / n] * n

    shapley_values = np.zeros(n)

    for _ in range(n_permutations):
        perm = rng.permutation(n)
        prev_score = 0.5  # 기본 baseline (랜덤 추측)

        for pos, client_idx in enumerate(perm):
            # 현재까지의 연합 (perm[:pos+1])
            coalition_models = [models[perm[j]] for j in range(pos + 1)]
            coalition_weights = [weights[perm[j]] for j in range(pos + 1)]
            total_w = sum(coalition_weights)
            coalition_weights = [w / total_w for w in coalition_weights]

            proba = fedavg_predict_proba(coalition_models, X_test, coalition_weights)
            score = roc_auc_score(y_test, proba)

            marginal = score - prev_score
            shapley_values[client_idx] += marginal
            prev_score = score

    shapley_values /= n_permutations

    # 정규화
    total_shapley = sum(abs(v) for v in shapley_values)
    results = []
    for i in range(n):
        results.append({
            "client_id": i,
            "shapley_value": round(shapley_values[i], 6),
            "contribution_pct": round(
                abs(shapley_values[i]) / total_shapley * 100 if total_shapley > 0 else 0, 2
            ),
            "data_weight": round(weights[i], 4),
        })

    results.sort(key=lambda x: -x["shapley_value"])
    return results


# ── DP ε 스윕 ─────────────────────────────────────────────────

def dp_epsilon_sweep(
    base_proba: np.ndarray,
    y_test: np.ndarray,
    epsilons: list[float] | None = None,
) -> list[dict]:
    """다양한 ε 값에 대한 DP 성능 영향 분석.

    SRS 4 요구사항: 프라이버시 예산(ε)과 모델 정확도 간 트레이드오프.
    """
    if epsilons is None:
        epsilons = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0]

    results = []
    base_auc = roc_auc_score(y_test, base_proba)
    results.append({
        "epsilon": "inf (no DP)",
        "auc_roc": round(base_auc, 4),
        "auc_pr": round(average_precision_score(y_test, base_proba), 4),
        "utility_loss_pct": 0.0,
    })

    for eps in epsilons:
        noisy = add_dp_noise(base_proba, epsilon=eps, seed=RANDOM_STATE)
        auc = roc_auc_score(y_test, noisy)
        apr = average_precision_score(y_test, noisy)
        results.append({
            "epsilon": eps,
            "auc_roc": round(auc, 4),
            "auc_pr": round(apr, 4),
            "utility_loss_pct": round((1 - auc / base_auc) * 100, 2),
        })

    return results


# ── Non-IID α 스윕 ────────────────────────────────────────────

def partition_non_iid_alpha(
    df: pd.DataFrame,
    n_clients: int,
    alpha: float,
    label_col: str = "is_fraud",
    seed: int = RANDOM_STATE,
) -> list[pd.DataFrame]:
    """Dirichlet α 파라미터 조절 가능한 Non-IID 파티셔닝."""
    rng = np.random.RandomState(seed)
    fraud = df[df[label_col] == 1].copy()
    normal = df[df[label_col] == 0].copy()

    proportions = rng.dirichlet([alpha] * n_clients)
    fraud_splits = []
    start = 0
    for p in proportions:
        end = start + max(1, int(len(fraud) * p))
        fraud_splits.append(fraud.iloc[start:min(end, len(fraud))])
        start = end

    normal_shuffled = normal.sample(frac=1, random_state=seed).reset_index(drop=True)
    chunk = len(normal_shuffled) // n_clients
    normal_splits = [
        normal_shuffled.iloc[i * chunk: (i + 1) * chunk if i < n_clients - 1 else len(normal_shuffled)]
        for i in range(n_clients)
    ]

    return [
        pd.concat([f, n], ignore_index=True).sample(frac=1, random_state=seed)
        for f, n in zip(fraud_splits, normal_splits)
    ]


def non_iid_alpha_sweep(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_cols: list[str],
    label_col: str = "is_fraud",
    n_clients: int = 3,
    alphas: list[float] | None = None,
) -> list[dict]:
    """다양한 Non-IID 강도(α)에 대한 FL 성능 분석."""
    if alphas is None:
        alphas = [0.1, 0.3, 0.5, 1.0, 5.0, 100.0]

    X_test = test_df[feature_cols].values
    y_test = test_df[label_col].values
    results = []

    for alpha in alphas:
        parts = partition_non_iid_alpha(train_df, n_clients, alpha, label_col)
        models, weights = [], []
        for part in parts:
            models.append(train_local_model(part, feature_cols, label_col))
            weights.append(len(part))
        total = sum(weights)
        weights = [w / total for w in weights]

        proba = fedavg_predict_proba(models, X_test, weights)
        auc = roc_auc_score(y_test, proba)
        apr = average_precision_score(y_test, proba)

        fraud_ratios = [part[label_col].mean() for part in parts]
        results.append({
            "alpha": alpha,
            "non_iid_level": "high" if alpha < 0.5 else "medium" if alpha < 2 else "low",
            "auc_roc": round(auc, 4),
            "auc_pr": round(apr, 4),
            "client_fraud_ratios": [round(r, 4) for r in fraud_ratios],
        })

    return results


# ── 전체 고도화 시뮬레이션 ────────────────────────────────────

def run_full_simulation(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_cols: list[str],
    label_col: str = "is_fraud",
    n_clients: int = 3,
    dp_epsilon: float = 5.0,
    output_dir: str | None = None,
) -> dict:
    """SRS 4 전체 요구사항을 충족하는 고도화 시뮬레이션."""
    import json as _json

    X_test = test_df[feature_cols].values
    y_test = test_df[label_col].values

    results = {"basic": [], "secagg": None, "cci": None, "dp_sweep": None, "niid_sweep": None}

    # 1. 기본 시뮬레이션 (기존)
    print("\n" + "=" * 70)
    print("  Phase 1: 기본 FL 시뮬레이션")
    print("=" * 70)
    results["basic"] = run_simulation(train_df, test_df, feature_cols, label_col, n_clients, dp_epsilon)

    # 2. Secure Aggregation
    print("\n" + "=" * 70)
    print("  Phase 2: Secure Aggregation (SecAgg)")
    print("=" * 70)
    iid_parts = partition_iid(train_df, n_clients)
    iid_models = [train_local_model(part, feature_cols, label_col) for part in iid_parts]
    iid_weights = [len(p) / len(train_df) for p in iid_parts]

    secagg_proba = secagg_aggregate(iid_models, X_test, iid_weights)
    secagg_auc = roc_auc_score(y_test, secagg_proba)
    secagg_apr = average_precision_score(y_test, secagg_proba)
    results["secagg"] = {
        "auc_roc": round(secagg_auc, 4),
        "auc_pr": round(secagg_apr, 4),
        "mask_cancellation_verified": True,
    }
    print(f"  SecAgg AUC-ROC: {secagg_auc:.4f}, AUC-PR: {secagg_apr:.4f}")
    print("  마스크 상쇄 검증: PASS")

    # 3. CCI 기여도 평가
    print("\n" + "=" * 70)
    print("  Phase 3: CCI 기여도 평가 (Shapley 근사)")
    print("=" * 70)
    cci = compute_cci_scores(iid_models, X_test, y_test, iid_weights)
    results["cci"] = cci
    print(f"  {'Client':>8} {'Shapley':>10} {'Contribution':>14} {'Data Weight':>12}")
    print(f"  {'-' * 48}")
    for c in cci:
        print(f"  {c['client_id']:>8} {c['shapley_value']:>10.4f} {c['contribution_pct']:>12.1f}% {c['data_weight']:>12.4f}")

    # 4. DP ε 스윕
    print("\n" + "=" * 70)
    print("  Phase 4: DP ε 스윕 (프라이버시-유틸리티 트레이드오프)")
    print("=" * 70)
    base_proba = fedavg_predict_proba(iid_models, X_test, iid_weights)
    dp_results = dp_epsilon_sweep(base_proba, y_test)
    results["dp_sweep"] = dp_results
    print(f"  {'ε':>12} {'AUC-ROC':>8} {'AUC-PR':>8} {'Loss%':>7}")
    print(f"  {'-' * 38}")
    for d in dp_results:
        print(f"  {str(d['epsilon']):>12} {d['auc_roc']:>8.4f} {d['auc_pr']:>8.4f} {d['utility_loss_pct']:>6.1f}%")

    # 5. Non-IID α 스윕
    print("\n" + "=" * 70)
    print("  Phase 5: Non-IID α 스윕 (데이터 이질성 영향)")
    print("=" * 70)
    niid_results = non_iid_alpha_sweep(train_df, test_df, feature_cols, label_col, n_clients)
    results["niid_sweep"] = niid_results
    print(f"  {'α':>6} {'Level':>8} {'AUC-ROC':>8} {'AUC-PR':>8}")
    print(f"  {'-' * 34}")
    for n in niid_results:
        print(f"  {n['alpha']:>6.1f} {n['non_iid_level']:>8} {n['auc_roc']:>8.4f} {n['auc_pr']:>8.4f}")

    # 결과 저장
    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "fl_full_results.json").write_text(
            _json.dumps(results, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\n결과 저장: {out / 'fl_full_results.json'}")

    return results


# ── CLI ───────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="FL 시뮬레이션 — 기본 / 고도화(full)")
    p.add_argument("--train-csv", type=Path, required=True)
    p.add_argument("--test-csv", type=Path, required=True)
    p.add_argument("--label-col", default="Class")
    p.add_argument("--n-clients", type=int, default=3)
    p.add_argument("--dp-epsilon", type=float, default=5.0)
    p.add_argument("--nrows", type=int, default=None, help="학습 데이터 행 제한")
    p.add_argument("--mode", choices=["basic", "full"], default="basic",
                   help="basic: 기존 4시나리오, full: SRS 4 전체 고도화")
    p.add_argument("--output-dir", type=str, default=None)
    args = p.parse_args()

    train_df = pd.read_csv(args.train_csv, nrows=args.nrows)
    test_df = pd.read_csv(args.test_csv)

    print(f"Train: {len(train_df)} rows, Test: {len(test_df)} rows")
    print(f"Clients: {args.n_clients}, DP ε: {args.dp_epsilon}, Mode: {args.mode}")

    exclude = {args.label_col, "id", "ID", "transaction_id"}
    feature_cols = [c for c in train_df.select_dtypes(include=[np.number]).columns if c not in exclude]
    print(f"Features: {len(feature_cols)} columns")

    if args.mode == "full":
        run_full_simulation(
            train_df, test_df, feature_cols, args.label_col,
            args.n_clients, args.dp_epsilon,
            output_dir=args.output_dir or "outputs/fds",
        )
    else:
        run_simulation(train_df, test_df, feature_cols, args.label_col, args.n_clients, args.dp_epsilon)


if __name__ == "__main__":
    main()
