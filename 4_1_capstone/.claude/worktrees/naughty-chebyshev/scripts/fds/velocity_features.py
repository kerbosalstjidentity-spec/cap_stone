"""실시간 FDS velocity(속도) 피처 시뮬레이션 모듈.

입력 DataFrame 컬럼 가정:
  - user_id: 사용자 식별자
  - event_ts: 거래 일시 (datetime 또는 ISO 문자열)
  - amount: 거래 금액 (숫자)
  - country_txn: 거래 국가 코드 (문자열)

컬럼이 없을 경우 zero-fill graceful 처리.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_velocity_features(df: pd.DataFrame) -> pd.DataFrame:
    """주어진 DataFrame에 각 거래 시점 기준으로 동일 user_id의 과거 거래 집계 피처를 추가.

    추가 컬럼:
    - tx_count_1h: 직전 1시간 내 거래 건수 (본 건 제외)
    - tx_count_24h: 직전 24시간 내 거래 건수
    - tx_count_7d: 직전 7일 내 거래 건수
    - amount_sum_24h: 직전 24시간 거래 금액 합계
    - amount_sum_7d: 직전 7일 거래 금액 합계
    - unique_countries_7d: 직전 7일 거래 국가 수
    - country_change_flag: 직전 거래와 다른 국가이면 1, 같으면 0 (첫 거래는 0)
    - tx_velocity_ratio: tx_count_1h / (tx_count_24h + 1) — 급증 지표

    user_id, event_ts, amount, country_txn 컬럼 없으면 zero-fill로 graceful 처리.
    """
    _REQUIRED = ("user_id", "event_ts", "amount", "country_txn")
    _ZERO_COLS = (
        "tx_count_1h",
        "tx_count_24h",
        "tx_count_7d",
        "amount_sum_24h",
        "amount_sum_7d",
        "unique_countries_7d",
        "country_change_flag",
        "tx_velocity_ratio",
    )

    out = df.copy()

    # 필수 컬럼 누락 시 zero-fill 반환
    missing = [c for c in _REQUIRED if c not in out.columns]
    if missing:
        for col in _ZERO_COLS:
            out[col] = 0
        return out

    # event_ts를 datetime으로 변환 (이미 datetime이면 그대로 유지)
    out["event_ts"] = pd.to_datetime(out["event_ts"], utc=False, errors="coerce")

    # amount를 숫자로 변환
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce").fillna(0.0)

    # 결과 컬럼 초기화
    n = len(out)
    tx_count_1h = np.zeros(n, dtype=np.int64)
    tx_count_24h = np.zeros(n, dtype=np.int64)
    tx_count_7d = np.zeros(n, dtype=np.int64)
    amount_sum_24h = np.zeros(n, dtype=np.float64)
    amount_sum_7d = np.zeros(n, dtype=np.float64)
    unique_countries_7d = np.zeros(n, dtype=np.int64)
    country_change_flag = np.zeros(n, dtype=np.int64)

    # 인덱스 리셋 후 원본 인덱스 보존
    original_index = out.index
    out = out.reset_index(drop=True)

    # user_id별 그룹 처리
    for uid, grp in out.groupby("user_id", sort=False):
        # event_ts 기준 정렬
        grp_sorted = grp.sort_values("event_ts")
        idxs = grp_sorted.index.to_numpy()
        ts_arr = grp_sorted["event_ts"].to_numpy(dtype="datetime64[ns]")
        amt_arr = grp_sorted["amount"].to_numpy(dtype=np.float64)
        country_arr = grp_sorted["country_txn"].astype(str).to_numpy()

        ts_ns = ts_arr.astype(np.int64)
        ns_1h = np.int64(3_600 * 1_000_000_000)
        ns_24h = np.int64(24 * 3_600 * 1_000_000_000)
        ns_7d = np.int64(7 * 24 * 3_600 * 1_000_000_000)

        for pos, idx in enumerate(idxs):
            t = ts_ns[pos]

            # 이전 거래만 집계 (본 건 제외, strict <)
            past_mask_1h = (ts_ns < t) & (ts_ns >= t - ns_1h)
            past_mask_24h = (ts_ns < t) & (ts_ns >= t - ns_24h)
            past_mask_7d = (ts_ns < t) & (ts_ns >= t - ns_7d)

            tx_count_1h[idx] = int(past_mask_1h.sum())
            tx_count_24h[idx] = int(past_mask_24h.sum())
            tx_count_7d[idx] = int(past_mask_7d.sum())
            amount_sum_24h[idx] = float(amt_arr[past_mask_24h].sum())
            amount_sum_7d[idx] = float(amt_arr[past_mask_7d].sum())

            past_countries = country_arr[past_mask_7d]
            unique_countries_7d[idx] = int(len(set(past_countries)))

            # country_change_flag: 직전 거래(가장 최근 과거 거래) 국가와 비교
            prev_mask = ts_ns < t
            if prev_mask.sum() > 0:
                prev_pos = int(np.argmax(ts_ns * prev_mask - (~prev_mask) * 10**18))
                # 가장 최근 과거 인덱스 찾기
                prev_positions = np.where(prev_mask)[0]
                last_prev_pos = prev_positions[np.argmax(ts_ns[prev_positions])]
                if country_arr[pos] != country_arr[last_prev_pos]:
                    country_change_flag[idx] = 1
                else:
                    country_change_flag[idx] = 0
            else:
                country_change_flag[idx] = 0

    out["tx_count_1h"] = tx_count_1h
    out["tx_count_24h"] = tx_count_24h
    out["tx_count_7d"] = tx_count_7d
    out["amount_sum_24h"] = amount_sum_24h
    out["amount_sum_7d"] = amount_sum_7d
    out["unique_countries_7d"] = unique_countries_7d
    out["country_change_flag"] = country_change_flag
    out["tx_velocity_ratio"] = tx_count_1h / (tx_count_24h + 1)

    # 원본 인덱스 복원
    out.index = original_index

    return out
