# PayWise #6 — 지출 예측 (LSTM 시계열)

> "이번 달엔 얼마나 쓸까?"
> 가계부 앱이 보여주는 가장 단순한 질문이지만, 답을 내려면 사용자의 과거 소비 시계열을 모델링해야 한다.
> PayWise는 이 문제를 **소형 LSTM 회귀 모델 + 가중이동평균(WMA) fallback** 의 2단 구조로 푼다.

---

## ① 개요

PayWise의 지출 예측 기능은 사용자의 **월별 총 지출 시계열**을 입력받아 다음 달 지출 총액과 카테고리별 예상 금액을 반환한다. 핵심은 [forecasting.py](backend/app/ml/forecasting.py)에 정의된 2-layer LSTM 모델이며, 학습 데이터가 부족하거나 PyTorch가 없는 환경에서는 자동으로 가중이동평균으로 우회한다. "ML이 없으면 죽는 API"가 아니라 **데이터가 자라는 동안에도 항상 답을 주는 API**를 만드는 것이 설계 목표다.

---

## ② 시스템 구성

이 기능에 직접 관여하는 컴포넌트만 추리면 다음과 같다.

```
┌────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│  Client    │ ──▶ │ routes_analysis.py   │ ──▶ │ profile_store        │
│  (FE)      │     │  GET /forecast/{uid} │     │  .get_trend(user_id) │
└────────────┘     └──────────┬───────────┘     └──────────────────────┘
                              │
                              ▼
                   ┌──────────────────────┐     ┌──────────────────────┐
                   │ forecaster.predict() │ ──▶ │ _LSTMModel (PyTorch) │
                   │  (싱글턴)            │     │  hidden=32, layers=2 │
                   └──────────┬───────────┘     └──────────────────────┘
                              │ (학습 안됨/torch 없음)
                              ▼
                   ┌──────────────────────┐
                   │  WMA fallback        │
                   │  (numpy only)        │
                   └──────────────────────┘
```

- **`forecaster`**: [forecasting.py:129](backend/app/ml/forecasting.py:129) — 프로세스 전역 싱글턴. 학습 상태를 메모리에 들고 다닌다.
- **`profile_store.get_trend()`**: 월별 카테고리별 지출 합계 dict. 예측의 입력 시계열이 여기서 나온다.
- **학습 트리거**: [trainer.py:_train_forecaster](backend/app/ml/trainer.py:211) — 전체 사용자의 월별 총 지출을 한 시계열로 묶어서 LSTM을 학습한다. 즉, **사용자별 모델이 아니라 글로벌 모델**.

---

## ③ 동작 흐름

`GET /analysis/forecast/{user_id}` 한 번의 요청을 따라가 보자.

1. `routes_analysis.forecast_spending()` 진입 — [routes_analysis.py:140](backend/app/api/routes_analysis.py:140)
2. `profile_store.get_trend(user_id)` 로 월별 카테고리 지출 dict 조회. 없으면 404.
3. `periods = sorted(trend.keys())` 로 월 순서 정렬 후, 월별 `_total` 키를 제외한 합계로 **단변량 시계열** `monthly_totals` 생성.
4. `forecaster.predict(monthly_totals)` 호출.
   - 학습이 끝났고 `len ≥ seq_length(=6)` 이면 LSTM 추론.
   - 아니면 WMA fallback.
5. 직전 3개월 카테고리 비율을 구해 `predicted * ratio` 로 **카테고리별 분배** — [routes_analysis.py:158-174](backend/app/api/routes_analysis.py:158).
6. `ForecastResult(predicted_total, predicted_by_category, confidence, ...)` 반환.

학습 경로는 별도의 운영 API(`routes_train`) → `_train_forecaster()` → `forecaster.train()` 으로, 새 모델 가중치가 싱글턴 인스턴스에 그대로 덮어씌워진다.

---

## ④ 핵심 코드 분석

### 4-1. LSTM 본체

```python
class _LSTMModel(nn.Module if TORCH_AVAILABLE else object):
    def __init__(self, input_size: int = 1, hidden_size: int = 32, num_layers: int = 2):
        ...
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)
```
[forecasting.py:21-31](backend/app/ml/forecasting.py:21)

- `input_size=1` — 단변량(월 총액 1개 채널) 시계열. 카테고리는 입력으로 넣지 않고, 예측 후 비율로 사후 분배한다. 모델 단순화 + 학습 데이터량 절약.
- `hidden_size=32, num_layers=2` — 가계부 데이터 규모에 비해 과하지 않게 잡은 소형 모델. 12~24개월짜리 시계열에 GRU/Transformer를 들이대는 건 과적합 위험.
- 클래스 정의에서 `nn.Module if TORCH_AVAILABLE else object` 패턴은 **PyTorch 미설치 환경에서도 import가 깨지지 않게** 하는 가드다. 이 가드 덕분에 fallback 경로만으로도 컨테이너가 뜬다.

```python
def forward(self, x):
    h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size)
    c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size)
    out, _ = self.lstm(x, (h0, c0))
    out = self.fc(out[:, -1, :])
    return out
```
[forecasting.py:33-38](backend/app/ml/forecasting.py:33)

- 매 forward마다 `h0/c0` 를 zero로 새로 만든다 — stateless 추론. 월별 호출이라 굳이 hidden state를 캐시할 이유가 없다.
- `out[:, -1, :]` — 시퀀스의 마지막 타임스텝 hidden만 잘라서 FC. **many-to-one 회귀** 의 전형적인 형태.

### 4-2. 학습 — 정규화와 슬라이딩 윈도우

```python
data = np.array(monthly_totals, dtype=np.float32)
self._scaler_mean = data.mean()
self._scaler_std = data.std() if data.std() > 0 else 1.0
data_norm = (data - self._scaler_mean) / self._scaler_std

X, y = [], []
for i in range(len(data_norm) - self.seq_length):
    X.append(data_norm[i:i + self.seq_length])
    y.append(data_norm[i + self.seq_length])
```
[forecasting.py:60-68](backend/app/ml/forecasting.py:60)

- **표준화 스케일러를 인스턴스 필드로 저장**한다(`_scaler_mean`, `_scaler_std`). sklearn `StandardScaler` 같은 별도 객체를 두지 않은 이유는 단순히 두 개의 스칼라이기 때문. 추론 시 같은 평균/표준편차로 역변환해야 하므로 이 두 값은 **모델 파라미터만큼 중요한 상태**.
- `std == 0` (모든 월이 동일 금액)인 코너 케이스를 1.0으로 치환 — division-by-zero 가드.
- 슬라이딩 윈도우로 `(N - seq_length)` 개의 학습 샘플 생성. `seq_length=6` 이면 1년치(12개월) 데이터로 6개의 학습 쌍이 나온다. 적다.

```python
optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
criterion = nn.MSELoss()

self.model.train()
for epoch in range(epochs):
    optimizer.zero_grad()
    output = self.model(X_t)
    loss = criterion(output, y_t)
    loss.backward()
    optimizer.step()
```
[forecasting.py:73-82](backend/app/ml/forecasting.py:73)

- 미니배치 분할 없이 **풀 배치 GD**. 샘플이 십수 개 수준이라 어차피 나눌 게 없다.
- DataLoader/scheduler/early stopping 모두 생략 — 50 epoch 고정. 학습 시계열이 짧고 모델이 작아서 이 수준에서 수렴한다.

### 4-3. 추론 — 정규화 → 모델 → 역정규화

```python
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
```
[forecasting.py:96-110](backend/app/ml/forecasting.py:96)

- `recent_months[-self.seq_length:]` — 항상 **마지막 6개월만** 자른다. 더 긴 입력이 와도 윈도우 크기에 맞춤.
- `unsqueeze(0).unsqueeze(-1)` — `(6,)` → `(1, 6, 1)` 로 batch/feature 축 추가.
- `max(0, predicted)` — LSTM이 음수 예측을 토해낼 수 있어서(특히 저액 구간) 0으로 클램프. "다음 달 -3만원 쓸 거예요"는 안 된다.
- `confidence=0.7` 하드코딩 — **모델이 실제로 뱉는 분산 추정치가 아니라 정성적 신뢰 등급**이다. ML 본문보단 UI 표기용 값.

### 4-4. WMA Fallback — 항상 답을 주는 안전망

```python
n = len(recent_months)
weights = np.arange(1, n + 1, dtype=float)
weights /= weights.sum()
predicted = float(np.dot(recent_months, weights))

return {
    "predicted": round(predicted, 2),
    "confidence": min(0.3 + 0.1 * n, 0.6),
    "method": "weighted_moving_avg",
}
```
[forecasting.py:116-125](backend/app/ml/forecasting.py:116)

- 가중치 `1, 2, ..., n` 을 정규화한 선형 가중. **최근 달일수록 가중**이 커지는 단순 선형 추세 추정.
- `confidence = min(0.3 + 0.1 * n, 0.6)` — 데이터가 1개월이면 0.4, 6개월이면 상한 0.6. LSTM 0.7보다 항상 낮게 보여서 UI에서 모델 신뢰의 위계가 자연스럽게 드러난다.
- numpy만 쓰므로 **PyTorch 미설치 환경에서도 무조건 응답**.

### 4-5. API 핸들러 — 카테고리 분배의 사후 처리

```python
recent = periods[-3:] if len(periods) >= 3 else periods
cat_sums: dict[str, float] = {}
recent_total = 0.0
for p in recent:
    amounts = trend[p]
    for cat, amt in amounts.items():
        if cat == "_total":
            continue
        cat_sums[cat] = cat_sums.get(cat, 0.0) + amt
        recent_total += amt

predicted_by_cat = {}
if recent_total > 0:
    for cat, total in cat_sums.items():
        ratio = total / recent_total
        predicted_by_cat[cat] = round(pred["predicted"] * ratio, 2)
```
[routes_analysis.py:159-174](backend/app/api/routes_analysis.py:159)

- LSTM이 **총액만** 예측하고, 카테고리 분배는 **최근 3개월 비율**을 그대로 곱해 계산한다. 분리 설계의 장점:
  - 카테고리당 시계열을 따로 학습하지 않아도 된다(데이터 희소).
  - 카테고리 추가/제거에 모델 재학습이 불필요.
- 단점은 "구조적 변화"(예: 갑자기 식비 비중 폭증)를 LSTM이 모른다는 점. 이건 ⑤에서 다룬다.

### 4-6. 학습 트리거 — 글로벌 시계열로 모은다

```python
result = await session.execute(
    select(
        func.to_char(Transaction.timestamp, "YYYY-MM").label("period"),
        func.sum(Transaction.amount).label("total"),
    )
    .group_by(text("1"))   # PostgreSQL: GROUP BY 위치 참조 (파라미터 바인딩 충돌 방지)
    .order_by(text("1"))
)
rows = result.all()
if len(rows) < forecaster.seq_length + 1:
    return {"status": "skipped", "reason": "insufficient_months", "count": len(rows)}

monthly_totals = [float(r.total) for r in rows]
result = forecaster.train(monthly_totals)
```
[trainer.py:213-226](backend/app/ml/trainer.py:213)

- **사용자 구분 없이** `Transaction.timestamp` 의 `YYYY-MM` 으로만 묶어 한 시계열로 만든다. 즉, 학습된 모델은 "PayWise 전체 사용자의 평균적 월 지출 패턴"을 외운다.
- `group_by(text("1"))` 주석에 명시된 대로 PostgreSQL의 위치 참조 GROUP BY를 사용한다 — `to_char` 표현식을 다시 쓰면 SQLAlchemy의 파라미터 바인딩과 충돌해서다.
- `seq_length + 1` 미만이면 학습 자체를 건너뛰고 fallback에 의존.

---

## ⑤ 설계 포인트 / 트러블슈팅 거리

- **글로벌 단일 모델 vs 사용자별 모델** — 현재 구현은 모든 사용자의 월별 합계를 하나의 시계열로 학습한다. 데이터가 적은 신규 사용자에게도 "평균적 패턴"을 줄 수 있는 장점이 있지만, 헤비유저/라이트유저처럼 스케일이 크게 다른 사용자는 정규화로도 걸러지지 않는 편향을 받는다. 향후엔 user_id를 임베딩으로 넣거나, 글로벌 모델을 사전학습한 뒤 사용자별 fine-tune 하는 방향이 자연스럽다.
- **`confidence` 가 휴리스틱** — LSTM 분기는 `0.7` 고정, WMA는 `0.3 + 0.1n`. 실제 예측 분산이나 잔차 기반 추정이 아니라 UI 라벨용이다. 신뢰도를 보고 액션을 거는 비즈니스 로직은 **이 값에 의존하지 말 것** — 잘못된 안전감을 줄 수 있다.
- **카테고리 비율의 정태 가정** — 총액은 LSTM이 시계열로 풀지만 카테고리 비율은 "최근 3개월 평균"을 곱한다. 트렌드 변화(이사로 식비 폭증, 차량 처분으로 교통비 급감)는 추적하지 못한다. 가벼운 보정으로 "직전 1개월 가중치 ↑" 정도가 들어갈 수 있다.
- **싱글턴 학습 상태의 휘발성** — `forecaster` 가 모듈 전역 싱글턴이고 가중치/스케일러를 메모리에만 들고 있다. 컨테이너 재시작 시 학습이 날아가서 fallback으로 되돌아간다. 운영에선 `state_dict()` + 스케일러 두 스칼라를 함께 디스크/오브젝트 스토리지에 저장하는 persistence가 필요하다.
- **`max(0, predicted)` 클램프** — 음수 예측을 0으로 자르는 건 사용자 표기상 안전한 선택이지만, 모델 진단 신호(예: 학습이 깨져서 음수가 자주 나오는 상황)를 가린다. 운영 메트릭으로 "클램프 발생률"을 따로 찍어두면 모델 헬스체크 지표가 된다.
- **재현성/테스트 가능성** — `optimizer`/`epochs`/`lr` 모두 인자로 노출되어 있어 학습 호출부에서 조절 가능하지만, `torch.manual_seed` 가 잡혀 있지 않다. 회귀 테스트에서 결정적 결과가 필요하면 학습 직전 시드를 고정하는 훅이 있어야 한다.

---

### 예상 질문 & 답변 (발표 Q&A 대비)

**Q1. 왜 LSTM인가요? ARIMA나 Prophet 같은 전통 시계열로도 충분하지 않나요?**
> 사용자별 데이터가 짧은 시계열(월 단위 12~24포인트)이라 ARIMA 차분 가정이 깨지기 쉽고, Prophet은 일별 데이터에 최적화돼 있어 월별 시계열에서 강점이 약합니다. 소형 LSTM(hidden=32, 2-layer)이 비선형 추세·계절성을 가볍게 학습하면서도 학습 비용이 낮아 선택.

**Q2. WMA fallback이 있는데 LSTM이 정말 필요한가요?**
> WMA는 "데이터가 자라는 동안 답을 끊지 않는 안전망"이고, LSTM은 학습 후 시점 간 패턴(급여일·계절성)을 잡습니다. 충분한 데이터 시점에서 LSTM이 WMA 대비 RMSE를 X% 개선한다는 측정은 후속 작업 예정.

**Q3. 학습 데이터가 부족한 사용자는?**
> `len(history) < 6` 이면 자동으로 WMA fallback. PyTorch 미설치 환경에서도 동일하게 우회. "ML이 없으면 죽는 API"가 아니라 "데이터가 자라는 동안 항상 답을 주는 API"가 설계 목표.

**Q4. 카테고리별 예측은 어떻게 하나요?**
> LSTM은 총액 단변량만 예측하고, 카테고리별 분배는 **최근 3개월 카테고리 비율 평균**을 곱하는 단순 구조. ⑤절에서 지적한 대로 카테고리 비율의 트렌드 변화(이사·차량 처분)는 추적 못 함. 향후 직전 1개월 가중치 보정 도입 예정.

**Q5. 재시작 시 학습 결과는요?**
> 현재 가중치/스케일러가 메모리에만 있어 재시작 시 휘발 → fallback으로 회귀. 운영 시 `state_dict()` + 스케일러 디스크 영속화 필요한 후속 작업.

---

## ⑥ 한 줄 정리

**PayWise의 지출 예측은 "단변량 LSTM으로 총액을 추정하고, 카테고리는 최근 비율로 분배"하는 단순 구조에, 데이터가 자라는 동안 끊김 없이 답을 주는 가중이동평균 fallback을 안전망으로 두른 2단 시계열 회귀다.**
