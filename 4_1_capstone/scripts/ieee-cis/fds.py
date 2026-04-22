"""
IEEE-CIS (Kaggle) 사기 탐지용 데이터 파이프라인 (FDS).

- train_transaction과 train_identity를 TransactionID 기준으로 병합(선택).
- 타깃: isFraud. 식별자: TransactionID (특성에서 제외).
- 수치: 중앙값 대체. 비수치: 결측 채운 뒤 OrdinalEncoder (미지의 범주는 -1).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "ieee-cis"


class IeeeCisFDS:
    """IEEE-CIS 원본 CSV 로드·병합·(X, y) 분리."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR

    def load_train(self, use_identity: bool = True, nrows: int | None = None) -> pd.DataFrame:
        tx_path = self.data_dir / "train_transaction.csv"
        if not tx_path.exists():
            raise FileNotFoundError(f"없음: {tx_path}")

        tx = pd.read_csv(tx_path, nrows=nrows)
        if not use_identity:
            return tx

        id_path = self.data_dir / "train_identity.csv"
        if not id_path.exists():
            return tx

        id_df = pd.read_csv(id_path)
        id_df = id_df[id_df["TransactionID"].isin(tx["TransactionID"])]
        return tx.merge(id_df, on="TransactionID", how="left")

    @staticmethod
    def xy(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        if "isFraud" not in df.columns:
            raise ValueError("isFraud 컬럼이 필요합니다.")
        if "TransactionID" not in df.columns:
            raise ValueError("TransactionID 컬럼이 필요합니다.")
        y = df["isFraud"].astype(int)
        X = df.drop(columns=["isFraud", "TransactionID"])
        return X, y


def split_train_val_by_time(
    df: pd.DataFrame,
    *,
    test_size: float = 0.25,
    time_col: str = "TransactionDT",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    creditcard에는 없는 시각 `TransactionDT` 기준 분할.
    시간 순 정렬 후 **뒤쪽 test_size 비율**을 검증으로 둔다 (미래 구간에 가깝게).
    """
    if time_col not in df.columns:
        raise ValueError(f"{time_col} 컬럼이 없습니다.")
    ordered = df.sort_values(time_col, kind="mergesort")
    n = len(ordered)
    n_test = max(1, int(round(n * test_size)))
    if n_test >= n:
        raise ValueError("test_size 때문에 검증 행이 전체와 같거나 비게 됩니다.")
    train_df = ordered.iloc[: n - n_test].copy()
    val_df = ordered.iloc[n - n_test :].copy()
    return train_df, val_df


def add_extended_prior_features(
    df: pd.DataFrame,
    group_cols: list[str] | None = None,
) -> pd.DataFrame:
    """
    `TransactionDT` 순 정렬 후, 각 그룹 키에 대해 **현재 행 이전** 건수·누적 금액(라벨 미사용).

    기본: card1, addr1, 이메일 도메인, DeviceType(identity 병합 시).
    """
    if group_cols is None:
        group_cols = ["card1", "addr1", "P_emaildomain", "R_emaildomain", "DeviceType"]
    present = [c for c in group_cols if c in df.columns]
    if not present:
        return df
    required = ("TransactionDT", "TransactionAmt")
    for c in required:
        if c not in df.columns:
            raise ValueError(f"add_extended_prior_features 에 필요한 컬럼이 없습니다: {c}")
    out = df.sort_values("TransactionDT", kind="mergesort").copy()
    for c in present:
        key = out[c].astype(str).fillna("__na__")
        g = out.groupby(key, sort=False)
        safe = c.replace(" ", "_").replace(".", "_")
        out[f"{safe}_prior_n"] = g.cumcount()
        amt_cum = g["TransactionAmt"].cumsum()
        out[f"{safe}_prior_amt"] = amt_cum - out["TransactionAmt"]
    return out


def add_card1_prior_features(df: pd.DataFrame) -> pd.DataFrame:
    """하위 호환: card1만 집계 특성 추가."""
    if "card1" not in df.columns:
        raise ValueError("card1 컬럼이 없습니다.")
    return add_extended_prior_features(df, group_cols=["card1"])


def walk_forward_time_splits(
    df: pd.DataFrame,
    n_folds: int = 4,
    time_col: str = "TransactionDT",
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """
    시간 분위 `edges[i] ~ edges[i+1]` 구간을 검증, 그 이전 전체를 학습 (walk-forward).
    첫 구간은 학습 데이터가 비면 스킵.
    """
    if time_col not in df.columns:
        raise ValueError(f"{time_col} 컬럼이 없습니다.")
    ordered = df.sort_values(time_col, kind="mergesort").reset_index(drop=True)
    # 구간 [edges[i], edges[i+1]) 를 n_folds번 쓰려면 분위 점 개수는 n_folds + 2
    edges = np.quantile(ordered[time_col], np.linspace(0, 1, n_folds + 2))
    folds: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    for i in range(1, n_folds + 1):
        val_start = edges[i]
        val_end = edges[i + 1]
        train_df = ordered[ordered[time_col] < val_start].copy()
        val_df = ordered[(ordered[time_col] >= val_start) & (ordered[time_col] < val_end)].copy()
        if len(train_df) == 0 or len(val_df) == 0:
            continue
        folds.append((train_df, val_df))
    return folds


def apply_frequency_encoding(
    X_train: pd.DataFrame,
    X_val: pd.DataFrame,
    cols: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """학습 분포 기준 범주 빈도(정규화) 열 `{col}_freq` 추가. 검증은 학습 map만 사용."""
    Xt = X_train.copy()
    Xv = X_val.copy()
    for c in cols:
        if c not in Xt.columns:
            continue
        vc = Xt[c].astype(str).value_counts(normalize=True)
        Xt[f"{c}_freq"] = Xt[c].astype(str).map(vc).fillna(0.0)
        Xv[f"{c}_freq"] = Xv[c].astype(str).map(vc).fillna(0.0)
    return Xt, Xv


def apply_target_encoding_cv(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    cols: list[str],
    *,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """K-fold CV 타깃 인코딩(sklearn TargetEncoder). 검증은 학습에서만 fit."""
    from sklearn.preprocessing import TargetEncoder

    Xt = X_train.copy()
    Xv = X_val.copy()
    for c in cols:
        if c not in Xt.columns:
            continue
        te = TargetEncoder(cv=5, random_state=random_state)
        tr = te.fit_transform(Xt[[c]].astype(str), y_train)
        va = te.transform(Xv[[c]].astype(str))
        Xt[f"{c}_te"] = np.asarray(tr).ravel()
        Xv[f"{c}_te"] = np.asarray(va).ravel()
    return Xt, Xv


def make_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    """X의 dtype 기준으로 수치/비수치 분리 후 sklearn 전처리기 구성 (미적합)."""
    numeric_features = X.select_dtypes(include=[np.number]).columns.tolist()
    categorical_features = [c for c in X.columns if c not in numeric_features]

    numeric_pipe = Pipeline(
        steps=[("imputer", SimpleImputer(strategy="median"))],
    )
    categorical_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
            (
                "encoder",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                    encoded_missing_value=-2,
                ),
            ),
        ],
    )

    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, numeric_features),
            ("cat", categorical_pipe, categorical_features),
        ],
        remainder="drop",
        sparse_threshold=0.0,
    )
