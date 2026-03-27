"""LSTM 기반 월별 지출 예측.

xlsx 참고: 시계열 분석 — LSTM / GRU
  → 거래 흐름 및 다음 타이밍 분석
  → 시계열 (Log) 데이터

사용자의 월별 지출 시계열 → 다음 달 예측.
데이터 부족 시 이동평균 fallback.
"""

import numpy as np

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


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

    def predict(self, recent_months: list[float]) -> dict:
        """최근 N개월 → 다음 달 예측.

        Args:
            recent_months: 최근 seq_length 개월의 총 지출

        Returns:
            {"predicted": 금액, "confidence": 0~1, "method": "lstm"|"moving_avg"}
        """
        if self.is_trained and TORCH_AVAILABLE and len(recent_months) >= self.seq_length:
            data = np.array(recent_months[-self.seq_length:], dtype=np.float32)
            data_norm = (data - self._scaler_mean) / self._scaler_std
            X_t = torch.FloatTensor(data_norm).unsqueeze(0).unsqueeze(-1)

            self.model.eval()
            with torch.no_grad():
                pred_norm = self.model(X_t).item()

            predicted = pred_norm * self._scaler_std + self._scaler_mean
            return {
                "predicted": round(max(0, predicted), 2),
                "confidence": 0.7,
                "method": "lstm",
            }

        # Fallback: 가중 이동평균 (최근 값에 가중치)
        if not recent_months:
            return {"predicted": 0, "confidence": 0, "method": "no_data"}

        n = len(recent_months)
        weights = np.arange(1, n + 1, dtype=float)
        weights /= weights.sum()
        predicted = float(np.dot(recent_months, weights))

        return {
            "predicted": round(predicted, 2),
            "confidence": min(0.3 + 0.1 * n, 0.6),
            "method": "weighted_moving_avg",
        }


# 싱글턴
forecaster = SpendForecaster()
