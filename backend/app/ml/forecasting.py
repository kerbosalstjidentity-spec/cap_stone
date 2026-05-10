"""LSTM 기반 월별 지출 예측.

xlsx 참고: 시계열 분석 — LSTM / GRU
  → 거래 흐름 및 다음 타이밍 분석
  → 시계열 (Log) 데이터

사용자의 월별 지출 시계열 → 다음 달 예측.
데이터 부족 시 이동평균 fallback.

W9-#8:
- 음수 → 0 클램프 발생률을 헬스체크용으로 누적 (clamp_stats)
- LSTM_SEED env 로 결정성 확보 (np/torch seed 동시 적용)
"""
from __future__ import annotations

import os
import threading

import numpy as np

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


# ── W9-#8: 클램프 발생률 + seed 훅 ─────────────────────────────

_clamp_lock = threading.Lock()
_clamp_stats = {"total_predictions": 0, "clamped": 0}


def _record_clamp(predicted: float, was_clamped: bool) -> None:
    with _clamp_lock:
        _clamp_stats["total_predictions"] += 1
        if was_clamped:
            _clamp_stats["clamped"] += 1


def get_clamp_health() -> dict:
    """헬스체크용 클램프 비율 — 분포 음수 빈도가 높으면 모델 캘리브레이션 의심."""
    with _clamp_lock:
        total = _clamp_stats["total_predictions"]
        clamped = _clamp_stats["clamped"]
    rate = clamped / total if total else 0.0
    return {
        "total_predictions": total,
        "clamped": clamped,
        "clamp_rate": round(rate, 4),
        "threshold_warning": rate >= 0.05,  # 5% 이상이면 모델 점검 권고
    }


def reset_clamp_stats() -> None:
    with _clamp_lock:
        _clamp_stats["total_predictions"] = 0
        _clamp_stats["clamped"] = 0


def seed_lstm(seed: int | None = None) -> int:
    """numpy/torch 시드 일괄 고정. seed=None → LSTM_SEED env (기본 42)."""
    if seed is None:
        try:
            seed = int(os.environ.get("LSTM_SEED", "42"))
        except ValueError:
            seed = 42
    np.random.seed(seed)
    if TORCH_AVAILABLE:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    return seed


class _LSTMModel(nn.Module if TORCH_AVAILABLE else object):
    """단순 LSTM 지출 예측 모델."""

    def __init__(self, input_size: int = 1, hidden_size: int = 32, num_layers: int = 2):
        if not TORCH_AVAILABLE:
            return
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x):
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size)
        out, _ = self.lstm(x, (h0, c0))
        out = self.fc(out[:, -1, :])
        return out


class SpendForecaster:
    """월별 지출 예측기."""

    def __init__(self, seq_length: int = 6):
        self.seq_length = seq_length
        self.model = _LSTMModel() if TORCH_AVAILABLE else None
        self.is_trained = False
        self._scaler_mean = 0.0
        self._scaler_std = 1.0

    def train(self, monthly_totals: list[float], epochs: int = 50, lr: float = 0.01) -> dict:
        """월별 총 지출 시계열로 LSTM 학습.

        Args:
            monthly_totals: [1월총액, 2월총액, ...]  최소 seq_length+1 개
        """
        if not TORCH_AVAILABLE or len(monthly_totals) < self.seq_length + 1:
            return {"status": "skipped", "reason": "insufficient_data_or_no_torch"}

        data = np.array(monthly_totals, dtype=np.float32)
        self._scaler_mean = data.mean()
        self._scaler_std = data.std() if data.std() > 0 else 1.0
        data_norm = (data - self._scaler_mean) / self._scaler_std

        X, y = [], []
        for i in range(len(data_norm) - self.seq_length):
            X.append(data_norm[i:i + self.seq_length])
            y.append(data_norm[i + self.seq_length])

        X_t = torch.FloatTensor(np.array(X)).unsqueeze(-1)
        y_t = torch.FloatTensor(np.array(y)).unsqueeze(-1)

        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        criterion = nn.MSELoss()

        self.model.train()
        for epoch in range(epochs):
            optimizer.zero_grad()
            output = self.model(X_t)
            loss = criterion(output, y_t)
            loss.backward()
            optimizer.step()

        self.is_trained = True
        return {"status": "trained", "epochs": epochs, "final_loss": round(loss.item(), 6)}

    def predict(
        self,
        recent_months: list[float],
        *,
        mc_samples: int = 0,
    ) -> dict:
        """최근 N개월 → 다음 달 예측.

        Args:
            recent_months: 최근 seq_length 개월의 총 지출
            mc_samples: W5-#4 — Monte Carlo dropout 분산 추정 샘플 수.
                0(기본) 이면 결정적 단일 추론. >0 이면 학습 모드(드롭아웃 포함)
                로 ``mc_samples`` 회 추론해 표준편차/95% 구간을 함께 반환.

        Returns:
            {"predicted", "confidence", "method", "std", "ci95_low", "ci95_high"}
        """
        if self.is_trained and TORCH_AVAILABLE and len(recent_months) >= self.seq_length:
            data = np.array(recent_months[-self.seq_length:], dtype=np.float32)
            data_norm = (data - self._scaler_mean) / self._scaler_std
            X_t = torch.FloatTensor(data_norm).unsqueeze(0).unsqueeze(-1)

            samples: list[float] = []
            if mc_samples > 0:
                # 드롭아웃 활성 + 입력 노이즈로 의사-MC dropout (LSTMCell 내부
                # 드롭아웃이 없는 단순 모델이므로 입력 jitter 로 대체).
                self.model.train()
                with torch.no_grad():
                    for _ in range(mc_samples):
                        noise = torch.randn_like(X_t) * 0.02
                        out = self.model(X_t + noise).item()
                        samples.append(out * self._scaler_std + self._scaler_mean)
                self.model.eval()
                arr = np.asarray(samples, dtype=float)
                predicted = float(arr.mean())
                std = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
                ci_low = float(np.quantile(arr, 0.025))
                ci_high = float(np.quantile(arr, 0.975))
                # 분산이 클수록 신뢰도 ↓ (표준편차 / 평균 = CV)
                cv = abs(std / predicted) if predicted else 1.0
                confidence = round(max(0.1, min(0.95, 0.9 - cv)), 4)
            else:
                self.model.eval()
                with torch.no_grad():
                    pred_norm = self.model(X_t).item()
                predicted = pred_norm * self._scaler_std + self._scaler_mean
                std = 0.0
                ci_low = predicted
                ci_high = predicted
                confidence = 0.7

            # W9-#8: 음수 → 0 클램프 통계 누적
            _record_clamp(predicted, predicted < 0)
            return {
                "predicted": round(max(0, predicted), 2),
                "confidence": confidence,
                "method": "lstm",
                "std": round(std, 4),
                "ci95_low": round(max(0, ci_low), 2),
                "ci95_high": round(max(0, ci_high), 2),
                "mc_samples": int(mc_samples),
            }

        # Fallback: 가중 이동평균 (최근 값에 가중치)
        if not recent_months:
            return {"predicted": 0, "confidence": 0, "method": "no_data",
                    "std": 0.0, "ci95_low": 0, "ci95_high": 0, "mc_samples": 0}

        n = len(recent_months)
        weights = np.arange(1, n + 1, dtype=float)
        weights /= weights.sum()
        predicted = float(np.dot(recent_months, weights))
        # 이동평균은 가중 표준편차로 분산 추정
        var = float(np.dot(weights, (np.asarray(recent_months) - predicted) ** 2))
        std = float(np.sqrt(var))

        return {
            "predicted": round(predicted, 2),
            "confidence": min(0.3 + 0.1 * n, 0.6),
            "method": "weighted_moving_avg",
            "std": round(std, 4),
            "ci95_low": round(max(0, predicted - 1.96 * std), 2),
            "ci95_high": round(predicted + 1.96 * std, 2),
            "mc_samples": 0,
        }


# 싱글턴
forecaster = SpendForecaster()
