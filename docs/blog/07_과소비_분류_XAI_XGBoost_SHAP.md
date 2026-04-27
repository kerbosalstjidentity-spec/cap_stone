# PayWise #7 — 과소비 분류 + XAI (XGBoost + SHAP)

> "이 사용자는 지금 과소비 중일까?"
> 모델이 "0.82 위험"이라 답하는 건 쉽다. 어려운 건 그 0.82가 **왜 그렇게 나왔는지**를 사용자에게 한 줄로 보여주는 일이다.
> PayWise는 이 문제를 **XGBoost 이진 분류 + SHAP TreeExplainer** 의 한 쌍으로 푼다.

---

## ① 개요

PayWise의 과소비 기능은 두 개의 분리된 책임으로 나뉜다. 하나는 **현재 소비가 과소비인지 0~1 확률로 답하는 분류기**([classifier.py](backend/app/ml/classifier.py)), 다른 하나는 그 확률이 **어떤 특성 때문에 그렇게 나왔는지를 한국어 문장으로 설명하는 XAI 엔진**([xai_engine.py](backend/app/services/xai_engine.py))이다. 분류기는 7차원 소비 특성 벡터를 받아 XGBoost로 학습하며, 학습이 안 된 환경에서는 규칙 기반으로 자동 fallback한다. 설명은 SHAP `TreeExplainer`로 각 특성의 기여도를 뽑고, 가장 큰 기여를 한 특성을 한국어 라벨과 함께 사용자에게 돌려준다.

---

## ② 시스템 구성

이 기능에 직접 관여하는 컴포넌트만 추리면 다음과 같다.

```
┌──────────┐    GET /v1/xai/overspend/{uid}    ┌──────────────────────┐
│  Client  │ ────────────────────────────────▶ │ routes_xai.py        │
└──────────┘                                    │  xai_overspend()     │
                                                └──────────┬───────────┘
                                                           │
                                                           ▼
                                              ┌────────────────────────┐
                                              │ xai_engine.py          │
                                              │  explain_overspend()   │
                                              └─────┬─────────────┬────┘
                                                    │ ① 특성 빌드 │ ② SHAP
                                                    ▼             ▼
                              ┌──────────────────────┐  ┌───────────────────────┐
                              │ OverspendClassifier  │  │ shap.TreeExplainer    │
                              │  build_features()    │  │  expected_value/벡터  │
                              │  predict()           │  └───────────────────────┘
                              │  explain()           │
                              └──────────┬───────────┘
                                         │ (학습 안됨)
                                         ▼
                              ┌──────────────────────┐
                              │  rule-based fallback │
                              │  amount/monthly_ratio│
                              └──────────────────────┘
```

- **`OverspendClassifier`**: [classifier.py:22](backend/app/ml/classifier.py:22) — XGBoost `XGBClassifier` 싱글턴. `is_fitted`/`threshold`/`feature_names` 를 인스턴스 상태로 들고 다닌다.
- **`explain_overspend()`**: [xai_engine.py:51](backend/app/services/xai_engine.py:51) — DB에서 최근 90일 거래를 끌어와 7개 집계 특성을 구성하고, 분류기 예측·SHAP 설명·한국어 요약을 한 응답에 합친다.
- **학습 트리거**: [trainer.py:_train_classifier](backend/app/ml/trainer.py:203) — 전체 사용자 거래에서 5천 건을 샘플링한 뒤 "사용자별 평균의 2배 이상이면 1" 이라는 **휴리스틱 레이블**로 학습.
- **호출처**: 이 분류기는 `/analysis/overspend`([routes_analysis.py:228](backend/app/api/routes_analysis.py:228)), `/strategy`, `/education` 등 여러 라우터에서 공유 싱글턴으로 재사용된다. XAI 라우터는 그 위에 SHAP 한 겹을 더 입힌 설명 전용 엔드포인트.

---

## ③ 동작 흐름

`GET /v1/xai/overspend/{user_id}` 한 번의 요청을 따라가 보자.

1. `routes_xai.xai_overspend()` 진입 — [routes_xai.py:13](backend/app/api/routes_xai.py:13). 의존성으로 `AsyncSession` 주입.
2. `explain_overspend(user_id, session)` 호출 → 최근 90일 `Transaction` 조회 ([xai_engine.py:55](backend/app/services/xai_engine.py:55)). 거래가 0건이면 `{"error": ...}` 즉시 반환.
3. 집계 특성 계산 — 평균 금액, 3개월 누적 / 3, 카테고리별 합계, 상위 카테고리 비중.
4. 가장 최근 거래 1건을 "대표 케이스"로 골라 `build_features()` 로 7차원 벡터 구성 ([xai_engine.py:79](backend/app/services/xai_engine.py:79)).
5. `overspend_classifier.predict(features)` — 학습됐으면 `predict_proba`, 아니면 규칙 기반.
6. `overspend_classifier.explain(features)` — SHAP `TreeExplainer` 로 7개 특성의 기여도를 뽑아 `{base_value, shap_values, top_factor}` 반환.
7. 7개 특성을 `abs(shap_value)` 기준 내림차순 정렬, 1위를 `top_factor`로 선택 ([xai_engine.py:107](backend/app/services/xai_engine.py:107)).
8. `_build_overspend_summary()` 가 확률→레벨(매우 높음/높음/보통/낮음) 매핑과 top factor의 부호(증가/감소 기여)를 합쳐 한국어 한 줄 요약 생성.

---

## ④ 핵심 코드 분석

### 1) 7차원 특성 벡터 — "왜 이 7개인가"

[classifier.py:38-46](backend/app/ml/classifier.py:38)

```python
self.feature_names = [
    "amount",
    "avg_amount_ratio",      # 이번 지출 / 평균 지출
    "category_pct",          # 해당 카테고리 비율
    "hour",                  # 거래 시간
    "is_domestic",           # 국내 여부
    "monthly_total_ratio",   # 이번달 누적 / 월평균
    "tx_frequency",          # 최근 거래 빈도
]
```

특성 7개는 모두 **"평소 대비"** 라는 정규화 축을 따라 골라져 있다. 절대 금액(`amount`)을 그대로 넣되, 동시에 `amount / avg_amount` 비율을 따로 둬서 모델이 "이 사람한테 큰 금액인가"를 학습할 수 있게 한다. `monthly_total_ratio` 도 동일한 발상 — 누적이 월평균보다 얼마나 빨리 쌓이는지가 과소비 신호다. `hour`/`is_domestic` 은 행동 컨텍스트(심야 결제, 해외 결제) 변수.

### 2) 0/1 분기와 `avg_amount > 0` 가드

[classifier.py:60-68](backend/app/ml/classifier.py:60)

```python
return np.array([[
    amount,
    amount / avg_amount if avg_amount > 0 else 0,
    category_pct,
    hour,
    1 if is_domestic else 0,
    monthly_total / monthly_avg if monthly_avg > 0 else 0,
    recent_tx_count,
]])
```

특성 빌더는 평균이 0인 신규 사용자(분모 0) 케이스를 명시적으로 막는다. 그 결과 신규 사용자에 대해서는 비율 특성이 모두 0으로 들어가는데, 이는 이후 SHAP 설명에서 "평균 대비 비율 (감소 방향 기여)" 처럼 해석되어 자연스럽게 **"낮음"** 결과로 이어진다 — 데이터 부족이 곧 위험으로 둔갑하지 않도록 하는 가드.

### 3) 학습 — 휴리스틱 라벨 ("정답"이 없는 문제 풀기)

[trainer.py:178-203](backend/app/ml/trainer.py:178)

```python
for tx in txs:
    ...
    features = [tx.amount, tx.amount / avg_amt if avg_amt > 0 else 0, ...]
    X_list.append(features)
    # 레이블: 평균의 2배 이상이면 과소비
    y_list.append(1 if tx.amount > avg_amt * 2 else 0)

X = np.array(X_list)
y = np.array(y_list)
result = overspend_classifier.fit(X, y)
```

과소비에는 **참값 라벨이 없다**. 누구도 "이 거래는 과소비입니다"라고 표시하지 않는다. PayWise는 "사용자별 평균의 2배 이상" 이라는 단순 규칙을 **약한 라벨(weak label)** 로 사용한다. 이 결정은 의도적이다 — 모델이 학습하는 건 "평균 2배 룰" 그 자체가 아니라, 그 룰이 참인 영역의 **고차원 패턴(시간대·카테고리·빈도 조합)** 이다. 학습 후 모델은 평균 2배 이하인 거래에 대해서도 다른 특성 조합으로 위험 점수를 다르게 매긴다.

### 4) `predict()` — 학습 전후 두 경로

[classifier.py:116-151](backend/app/ml/classifier.py:116)

```python
def predict(self, features: np.ndarray) -> dict:
    if self.is_fitted and XGB_AVAILABLE:
        proba = float(self.model.predict_proba(features)[0][1])
        return {"probability": round(proba, 4),
                "is_overspend": proba >= self.threshold,
                "method": "xgboost"}

    # Fallback: 규칙 기반
    amount_ratio = features[0][1] if features.shape[1] > 1 else 0
    monthly_ratio = features[0][5] if features.shape[1] > 5 else 0

    score = 0.0
    if amount_ratio > 3:
        score += 0.4
    elif amount_ratio > 2:
        score += 0.2
    if monthly_ratio > 1.2:
        score += 0.3
    elif monthly_ratio > 1.0:
        score += 0.1
    if features[0][2] > 0.4:  # category_pct
        score += 0.2

    score = min(score, 1.0)
    return {"probability": round(score, 4),
            "is_overspend": score >= self.threshold, "method": "rule_based"}
```

응답에 `method` 필드가 들어가는 게 핵심이다. 프론트는 `"xgboost"` 인지 `"rule_based"` 인지 보고 "AI 분석" / "기본 분석" 라벨을 다르게 띄울 수 있다 — **데이터가 자라는 동안에도 답을 주되, 어떤 모드에서 답한 건지를 숨기지 않는다**. fallback의 점수표(0.4 / 0.2 / 0.3 / 0.1 / 0.2) 합은 최대 1.1이지만 `min(score, 1.0)` 으로 클램프되며, 임계값 `OVERSPEND_THRESHOLD=0.7` ([config.py:23](backend/app/config.py:23)) 과 일관된 0~1 스케일을 유지한다.

### 5) SHAP 설명 — `expected_value` 의 함정

[classifier.py:86-114](backend/app/ml/classifier.py:86)

```python
import shap
explainer = shap.TreeExplainer(self.model)
shap_vals = explainer.shap_values(features)
# shap_vals: (1, n_features) for binary classification
vals = shap_vals[0] if shap_vals.ndim == 2 else shap_vals
shap_dict = {
    fname: float(vals[i])
    for i, fname in enumerate(self.feature_names)
}
base_val = float(explainer.expected_value) if not hasattr(explainer.expected_value, '__len__') else float(explainer.expected_value[1])
top = max(shap_dict, key=lambda k: abs(shap_dict[k]))
```

세 가지 디테일이 묻혀 있다.

- **이진 분류의 출력 모양 분기**: `shap_values()` 는 SHAP 버전·xgboost 버전에 따라 `(n_features,)` 또는 `(1, n_features)` 둘 다 나올 수 있다. `vals.ndim == 2` 분기로 두 모양을 모두 받는다.
- **`expected_value` 의 모양 분기**: 마찬가지로 스칼라 vs `[neg, pos]` 두 클래스 base 값 리스트가 모두 가능하다. `hasattr(..., '__len__')` 체크로 양쪽을 통합 — 리스트면 양성 클래스(index 1)의 base 사용.
- **top factor 선택 기준은 절댓값**: SHAP 값은 부호가 있다(양수 = 과소비 확률을 끌어올림, 음수 = 끌어내림). 가장 영향이 큰 특성을 고를 때는 `abs()` 기준이 맞다. 부호는 이후 한국어 요약에서 "증가/감소 방향 기여"로 따로 표현된다.

전체를 `try/except Exception` 으로 감싸 SHAP 실패 시 `{"method": "unavailable"}` 로 떨어뜨리는 것도 의도적이다 — XAI는 핵심 비즈니스 로직이 아니므로, 실패해도 분류기 예측 자체는 내려간 적 없는 응답을 만들어야 한다.

### 6) 사용자 향 한국어 요약

[xai_engine.py:18-27, 134-149](backend/app/services/xai_engine.py:18)

```python
FEATURE_KR = {
    "amount": "거래 금액",
    "avg_amount_ratio": "평균 대비 비율",
    "category_pct": "카테고리 비중",
    ...
}

def _build_overspend_summary(pred: dict, top: dict | None) -> str:
    prob = pred["probability"]
    if prob >= 0.8: level = "매우 높음"
    elif prob >= 0.6: level = "높음"
    elif prob >= 0.4: level = "보통"
    else: level = "낮음"

    summary = f"과소비 위험도 {level} ({prob*100:.0f}%)"
    if top and abs(top.get("shap_value", 0)) > 0:
        direction = "증가" if top["shap_value"] > 0 else "감소"
        summary += f" — 주요 원인: {top['feature_kr']} ({direction} 방향 기여)"
    return summary
```

ML 출력을 사용자가 읽을 수 있는 한 문장으로 압축하는 마지막 레이어. SHAP 부호가 그대로 "증가/감소" 자연어로 매핑된다는 점이 깔끔하다. `abs(...) > 0` 가드로 fallback 경로(SHAP 실패 시 모든 shap_value=0)에서는 `— 주요 원인:` 절이 아예 빠져, "주요 원인: 알 수 없음" 같은 어색한 문장이 만들어지지 않는다.

### 7) 분류기 출력에 SHAP 값 결합 — 응답 스키마

[xai_engine.py:96-131](backend/app/services/xai_engine.py:96)

```python
if shap_result["method"] == "shap":
    shap_values = shap_result["shap_values"]
    feature_list = []
    for fname, sval in shap_values.items():
        idx = overspend_classifier.feature_names.index(fname)
        feature_list.append({
            "feature": fname,
            "feature_kr": FEATURE_KR.get(fname, fname),
            "value": round(float(features[0][idx]), 4),
            "shap_value": round(float(sval), 4),
        })
    feature_list.sort(key=lambda x: abs(x["shap_value"]), reverse=True)
    top = feature_list[0] if feature_list else None
...
return {
    "user_id": user_id,
    "base_value": ...,
    "prediction": pred["probability"],
    "is_overspend": pred["is_overspend"],
    "features": feature_list,    # 정렬된 7개
    "top_factor": top["feature"],
    "top_factor_kr": top["feature_kr"],
    "summary_text": summary,
    "method": shap_result["method"],
}
```

SHAP의 raw 값(`{fname: shap}` dict)을 그대로 쓰지 않고, 입력 특성 값과 짝지어 `{feature, feature_kr, value, shap_value}` 객체 리스트로 재구성한다. 프론트는 이 리스트 하나만 받아 **막대 차트(특성별 기여도)** 와 **테이블(특성·실제 값·기여도)** 둘 다를 그릴 수 있다 — 추가 매핑 없이.

---

## ⑤ 설계 포인트

- **약한 라벨로 시작하는 결정**: 과소비에 정답이 없다는 본질적 제약을 "사용자별 평균 2배" 라는 단순 규칙으로 우회한다. 한계는 명확 — 규칙 자체에 편향이 있으면 모델도 그걸 학습한다. 다만 학습된 모델은 7차원 조합을 보기 때문에 단일 규칙보다 정밀해질 여지가 있고, 시간이 지나면 **사용자 피드백 라벨(수동 태깅)** 로 점진적 교체가 가능하다.
- **싱글턴 + 메모리 상태**: `overspend_classifier = OverspendClassifier()` ([classifier.py:155](backend/app/ml/classifier.py:155)) 가 프로세스 전역에 살면서 `is_fitted` 플래그를 들고 있다. 학습 결과가 디스크에 영속화되지 않으므로 **재시작 시 전부 fallback 모드로 돌아간다**. 운영 측면 트레이드오프 — 단순한 대신 부팅 후 첫 학습이 끝나기 전까지는 SHAP이 동작하지 않는다.
- **SHAP 실패 시 분류기는 살아있다**: XAI 실패가 분류 결과를 같이 죽이지 않게 분리. 응답의 `method` 필드로 SHAP/룰/미가용을 명시.
- **부호 정보의 보존**: SHAP의 부호(+/-)를 끝까지 끌고 가서 사용자 향 문장의 "증가/감소" 로 사용. 이는 단순한 feature importance(절댓값만 사용) 보다 한 단계 더 나간 설명이다 — 모델 내부 메커니즘에 기반한 **지향성 있는 설명**.
- **잠재 트러블 거리**: `explain_overspend()` 가 "최근 거래 1건" 만을 대표 벡터로 쓴다 ([xai_engine.py:78](backend/app/services/xai_engine.py:78)). 이건 그 한 건이 outlier일 때 사용자에게 보여주는 SHAP 설명이 흔들릴 수 있다는 의미. 향후 "최근 N건의 평균 SHAP" 또는 "각 거래별 SHAP을 모두 보여주기" 로 확장할 여지 있음.

---

### 예상 질문 & 답변 (발표 Q&A 대비)

**Q1. SHAP과 단순 feature importance의 차이가 뭔가요?**
> Feature importance는 "이 피처가 모델 전체에 얼마나 중요한가"의 정적 지표, SHAP은 "이 한 건의 예측에서 각 피처가 +/- 얼마만큼 기여했는가"의 **사례별 분해**입니다. PayWise는 사용자별 설명을 위해 SHAP의 **부호(증가/감소)** 까지 활용해 한국어 문장으로 변환.

**Q2. 단건 호출 시 z-score가 무력화되는 문제는요?**
> ⑤절에서 지적한 대로 `top_feature_reasons`가 입력 행렬 내부 평균/표준편차를 쓰므로 1행 입력 시 z=0이 됩니다. 학습 데이터의 (mu, std)를 번들에 저장해두고 단건 호출 시 그것을 쓰는 방향이 후속 수정 작업.

**Q3. 왜 XGBoost인가요? Random Forest나 LightGBM이 아니고?**
> XGBoost는 SHAP `TreeExplainer`와의 호환이 가장 안정적이고, 결측치 처리가 내장돼 있어 본 ML 파이프라인의 Imputer 단순화에 유리. RF는 비교 대상이고, LightGBM은 추후 A/B 테스트(#18) 후보.

**Q4. 사용자에게 한국어 설명을 어떻게 만드나요?**
> SHAP 기여도 상위 3개 피처를 추출 → `xai_engine.py`의 한국어 라벨 매핑(예: `night_ratio` → "심야 지출 비중")으로 치환 → 부호에 따라 "증가/감소" 동사 결정 → 한 문장 합성. 결과 예: "심야 지출 비중이 평소 대비 3배 증가".

**Q5. 학습 안 된 환경에선 어떻게 동작하나요?**
> `is_fitted=False`면 규칙 기반 fallback(예산 대비 비율, 카테고리 편중)으로 점수 산출. 응답의 `method` 필드로 SHAP/룰/미가용 명시해 클라이언트가 신뢰 수준을 알 수 있게 분리.

---

## ⑥ 한 줄 정리

PayWise의 과소비 기능은 **XGBoost로 0~1 점수를 내고, SHAP로 그 점수의 부호 있는 분해를 한국어 한 줄에 압축**하는 — 분류와 설명이 같은 응답에서 짝을 이루는 ML 엔드포인트다.
