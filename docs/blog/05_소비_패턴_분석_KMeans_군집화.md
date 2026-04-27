# #5 소비 패턴 분석 — K-Means 군집화로 사용자 유형 분류하기

> PayWise 22개 기능 분석 시리즈 다섯 번째 글. 이번에는 사용자의 카테고리별 지출 비율을 입력으로 받아 **절약형 / 균형형 / 소비형 / 투자형** 네 가지 유형으로 분류하는 K-Means 군집화 모듈을 뜯어본다.

---

## ① 개요

PayWise는 사용자의 거래 내역을 카테고리별로 집계한 뒤, 그 비율 벡터를 K-Means에 태워 **소비 유형**을 매긴다. 단순히 "이번 달 얼마 썼다"가 아니라 "당신은 식비 비중이 높은 균형형입니다" 같은 정성적 라벨을 만들어, 이후 전략 추천(#10)·금융 교육(#11)·XAI 설명(#7)이 모두 이 라벨을 분기 키로 사용한다. 모델은 비지도 학습이라 정답 라벨이 없어도 운영 데이터만으로 주기적으로 갱신된다.

---

## ② 시스템 구성

이 기능에 직접 관여하는 컴포넌트만 추리면 다음과 같다.

```
┌──────────────────────┐    거래 적재     ┌──────────────────────────┐
│ TransactionIngest    │ ───────────────▶ │ InMemorySpendProfileStore │
│ (POST /spend/ingest) │                  │  - category_totals        │
└──────────────────────┘                  │  - category_counts        │
                                          └─────────────┬─────────────┘
                                                        │ get_profile()
                                                        ▼
┌────────────────────────┐  category_pcts  ┌──────────────────────────┐
│ GET /v1/analysis/      │ ──────────────▶ │ SpendClusterModel.predict │
│ pattern/{user_id}      │                 │  - StandardScaler         │
└────────────────────────┘                 │  - KMeans(n=4)            │
              ▲                            │  - cluster_labels         │
              │ cluster_id, label          └──────────────┬───────────┘
              │                                           ▲
              │                                           │ fit(profiles)
              │                                ┌──────────┴───────────┐
              └──── routes_strategy / ─────────│  ml.trainer          │
                    routes_education /         │  _train_clustering() │
                    xai_engine 가 동일 모델 공유 │  (DB 전체 사용자 집계)│
                                               └──────────────────────┘
```

- **데이터 소스**: `InMemorySpendProfileStore` — 사용자별 카테고리 합계·건수·시간대 집계를 메모리에 보관 ([spend_profile.py](backend/app/services/spend_profile.py))
- **모델**: `SpendClusterModel` — `StandardScaler` + `sklearn.cluster.KMeans` 묶음, 싱글턴 ([clustering.py](backend/app/ml/clustering.py:179))
- **API**: `GET /v1/analysis/pattern/{user_id}` ([routes_analysis.py:38](backend/app/api/routes_analysis.py:38))
- **학습 트리거**: `ml.trainer._train_clustering` — DB의 전 사용자 거래를 비율로 환산해 `fit()` 호출 ([trainer.py:48](backend/app/ml/trainer.py:48))

---

## ③ 동작 흐름

요청 한 번이 들어왔을 때 거치는 단계는 다음과 같다.

1. **요청 진입** — 클라이언트가 `GET /v1/analysis/pattern/{user_id}` 호출
2. **프로필 조회** — `profile_store.get_profile(user_id)`로 누적 거래 집계를 꺼낸다. 없으면 404
3. **카테고리 비율화** — `CategorySummary.pct_of_total` 값을 `{"food": 0.32, "shopping": 0.18, ...}` 형태 dict로 변환
4. **특성 벡터 구성** — `_build_feature_vector`가 11개 카테고리 고정 순서(FEATURE_CATEGORIES)에 맞춰 길이 11 벡터를 만든다
5. **스케일링 + 예측** — `scaler.transform` 후 `KMeans.predict`로 cluster_id 산출
6. **라벨 매핑** — 학습 시 자동으로 정해진 `self.cluster_labels`에서 `절약형 / 균형형 / 소비형 / 투자형` 한글 라벨을 가져온다
7. **응답 조립** — 라벨, cluster_id, 카테고리 breakdown, 특성 벡터를 함께 반환
8. **(미학습 분기)** — 모델이 아직 fit되지 않았다면 카테고리 비율 합 기반 규칙으로 fallback

---

## ④ 핵심 코드 분석

### 4-1. 특성 벡터 — "카테고리 순서를 고정"하는 게 핵심

[clustering.py:25](backend/app/ml/clustering.py:25)
```python
FEATURE_CATEGORIES = [
    SpendCategory.FOOD,
    SpendCategory.SHOPPING,
    SpendCategory.TRANSPORT,
    SpendCategory.ENTERTAINMENT,
    SpendCategory.EDUCATION,
    SpendCategory.HEALTHCARE,
    SpendCategory.HOUSING,
    SpendCategory.UTILITIES,
    SpendCategory.FINANCE,
    SpendCategory.TRAVEL,
    SpendCategory.OTHER,
]
```

K-Means는 입력 차원의 **순서**가 의미를 가진다(centroid·distance가 인덱스 단위로 계산되므로). 그래서 dict로 받은 카테고리 비율을 학습 시점·예측 시점 모두 동일한 순서로 펼쳐야 한다.

[clustering.py:50](backend/app/ml/clustering.py:50)
```python
def _build_feature_vector(self, category_pcts: dict[str, float]) -> np.ndarray:
    return np.array([category_pcts.get(c.value, 0.0) for c in FEATURE_CATEGORIES])
```

`get(..., 0.0)` 기본값으로 **사용자가 한 번도 쓰지 않은 카테고리**도 0으로 채워 차원을 맞춘다. dict 키 누락은 자주 일어나기 때문에 이 단계가 없으면 KeyError로 터진다.

### 4-2. 학습 — 라벨을 "총지출 비율 합"으로 자동 정렬

[clustering.py:54](backend/app/ml/clustering.py:54)
```python
def fit(self, user_profiles: list[dict[str, float]]) -> None:
    if len(user_profiles) < self.n_clusters:
        return

    X = np.array([self._build_feature_vector(p) for p in user_profiles])
    X_scaled = self.scaler.fit_transform(X)
    self.model.fit(X_scaled)
    self.is_fitted = True

    centers = self.scaler.inverse_transform(self.model.cluster_centers_)
    total_spend = centers.sum(axis=1)
    order = np.argsort(total_spend)
    labels = ["절약형", "균형형", "소비형", "투자형"]
    self.cluster_labels = {int(order[i]): labels[i] for i in range(min(len(order), len(labels)))}
```

K-Means는 군집 인덱스 자체에 의미가 없다 — 같은 데이터를 학습해도 random_state에 따라 cluster_id 0/1/2/3 매핑이 매번 바뀐다. 그러면 API 응답의 라벨이 학습 때마다 뒤집히는 사고가 난다.

여기서는 **각 군집 중심을 원래 스케일로 역변환한 뒤(`inverse_transform`) 카테고리 비율 합으로 정렬**한다. 비율 합이 작은 군집(=소비가 적은 그룹)이 `절약형`, 큰 쪽이 `투자형`. 정렬 키 자체에 도메인 의미를 부여해서 학습이 다시 돌아도 라벨 매핑이 안정적으로 유지된다.

> 한 가지 주의: 비율 벡터 합은 보통 1.0에 가까워야 한다. 실제로는 카테고리 누락·반올림 때문에 군집별로 미세한 차이가 나고, 그 차이를 정렬 신호로 쓰는 셈이다. "지출 총액"이 아니라 "비율 분포의 분산 패턴"으로 라벨을 매기는 게 정확한 표현.

### 4-3. 예측 — fit 안 됐을 때의 규칙 fallback

[clustering.py:75](backend/app/ml/clustering.py:75)
```python
def predict(self, category_pcts: dict[str, float]) -> dict:
    vec = self._build_feature_vector(category_pcts).reshape(1, -1)

    if not self.is_fitted:
        total = sum(category_pcts.values())
        if total < 0.3:
            return {"cluster_id": -1, "cluster_label": "절약형", ...}
        elif total < 0.6:
            return {"cluster_id": -1, "cluster_label": "균형형", ...}
        else:
            return {"cluster_id": -1, "cluster_label": "소비형", ...}

    X_scaled = self.scaler.transform(vec)
    cluster_id = int(self.model.predict(X_scaled)[0])
    label = self.cluster_labels.get(cluster_id, f"군집_{cluster_id}")
    return {"cluster_id": cluster_id, "cluster_label": label, ...}
```

운영 초기에는 학습할 사용자 수가 4명도 안 되는 상황이 벌어진다(`n_clusters=4`라서 `fit()`이 즉시 return). 그 동안 API가 500을 뱉으면 안 되니, **카테고리 비율 합 기준 단순 분기**로 임시 라벨을 매긴다. 이때 `cluster_id`는 `-1`로 마킹해서 호출 측이 "ML 결과인지 fallback인지" 구분할 수 있게 했다.

### 4-4. explain — 군집 귀속 근거를 풀어주는 미니 XAI

[clustering.py:104](backend/app/ml/clustering.py:104)
```python
def explain(self, category_pcts: dict[str, float]) -> dict:
    ...
    vec_scaled = self.scaler.transform(vec)
    cluster_id = int(self.model.predict(vec_scaled)[0])
    centers = self.model.cluster_centers_  # scaled 좌표

    dists = [
        {"cluster": i, "label": ..., "distance": round(float(np.linalg.norm(vec_scaled - centers[i])), 4)}
        for i in range(self.n_clusters)
    ]

    center_orig = self.scaler.inverse_transform(centers[cluster_id].reshape(1, -1))[0]
    user_vec = vec[0]
    deviations = []
    for i, cat in enumerate(FEATURE_CATEGORIES):
        diff = float(user_vec[i]) - float(center_orig[i])
        deviations.append({
            "category": cat.value,
            "user_value": round(float(user_vec[i]), 4),
            "center_value": round(float(center_orig[i]), 4),
            "deviation": round(diff, 4),
        })

    deviations.sort(key=lambda x: abs(x["deviation"]), reverse=True)
    toward = next((d for d in deviations if d["deviation"] < 0), {}).get("category_kr", "")
    away = next((d for d in deviations if d["deviation"] > 0), {}).get("category_kr", "")
```

K-Means는 본디 설명력이 약한 모델이지만, 여기서는 두 가지 트릭으로 "왜 이 군집인지"를 사용자에게 보여준다:

1. **거리 비교** — 사용자 벡터와 모든 군집 중심까지의 유클리드 거리를 함께 반환. "절약형(0.42), 균형형(0.51), …" 식으로 보여주면 "두 번째로 가까운 군집"이 무엇인지 알 수 있다(경계선상 사용자 식별에 유용).
2. **per-feature 편차** — 할당된 군집 중심과 비교해 어떤 카테고리가 평균보다 높고/낮은지를 절댓값 큰 순으로 정렬. "쇼핑 비중이 군집 평균보다 높음, 식비 비중이 낮음" 같은 자연어 요약(`summary_text`)이 여기서 만들어진다.

이 `explain` 출력은 [xai_engine.py:258](backend/app/services/xai_engine.py:258)이 호출해서 #7(XAI) 응답에 그대로 합쳐진다.

### 4-5. API 레이어 — 비율 dict 만드는 단계가 의외의 길목

[routes_analysis.py:38](backend/app/api/routes_analysis.py:38)
```python
async def analyze_pattern(user_id: str):
    profile = profile_store.get_profile(user_id)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found")

    cat_pcts = {cs.category.value: cs.pct_of_total for cs in profile.category_breakdown}
    result = cluster_model.predict(cat_pcts)
    ...
```

핵심은 `cs.category.value`로 **Enum이 아닌 문자열 키**를 쓴다는 점. 모델 내부 `_build_feature_vector`도 `c.value`로 조회하므로 양쪽이 같은 문자열("food", "shopping" 등)을 쓰지 않으면 모든 값이 0이 되어 결과가 망가진다. Enum을 키로 직접 쓰지 않은 이유가 이 일관성 때문이다.

### 4-6. 학습 데이터 만들기 — DB에서 비율로 환산

[trainer.py:48](backend/app/ml/trainer.py:48)
```python
async def _train_clustering(session: AsyncSession) -> dict:
    result = await session.execute(
        select(
            Transaction.user_id,
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
        ).group_by(Transaction.user_id, Transaction.category)
    )
    rows = result.all()
    ...
    user_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    user_grand: dict[str, float] = defaultdict(float)
    for r in rows:
        user_totals[r.user_id][r.category] += r.total
        user_grand[r.user_id] += r.total

    profiles = []
    for uid, cats in user_totals.items():
        grand = user_grand[uid]
        if grand <= 0:
            continue
        pct = {cat: amt / grand for cat, amt in cats.items()}
        profiles.append(pct)

    if len(profiles) < cluster_model.n_clusters:
        return {"status": "skipped", "reason": "insufficient_users", "count": len(profiles)}

    cluster_model.fit(profiles)
```

DB 단에서 (user_id, category) 그룹별 합계를 한 번에 가져온 뒤, 파이썬에서 사용자별 총액으로 나눠 비율로 환산. K-Means 입력은 절대 금액이 아니라 **분포 형태**라는 게 일관된다 — 100만 원 쓰는 사람과 1,000만 원 쓰는 사람의 "패턴"이 같다면 같은 군집이어야 하니까.

---

## ⑤ 설계 포인트 / 트러블슈팅 거리

- **왜 K-Means 4개 군집인가** — 비지도 학습 중 가장 단순하고 빠른 알고리즘이라 운영 부담이 적다. 4는 도메인 라벨 4종(`절약형/균형형/소비형/투자형`)에 맞춘 인위적 수치 — 엄밀히는 elbow나 silhouette로 검증한 값이 아니다. 데이터가 충분히 쌓이면 군집 수를 데이터 기반으로 재선정해야 한다.
- **싱글턴 모델의 동시성 위험** — `cluster_model = SpendClusterModel()`이 모듈 레벨 싱글턴이라 학습 중에도 `predict`가 들어올 수 있다. `KMeans.fit`은 내부 상태를 갱신하므로 학습/예측이 겹치면 일시적으로 모순된 결과가 나올 수 있다. 현재는 학습 빈도가 낮아 회피하고 있을 뿐, 본격 운영에선 락이나 swap 패턴이 필요하다.
- **인메모리 프로필 저장소 한계** — `InMemorySpendProfileStore`는 프로세스 재시작 시 휘발. 학습은 DB에서 다시 끌어오지만, 예측 API는 인메모리 집계에 의존하므로 재시작 직후 사용자가 0건으로 보일 수 있다. `spend_profile_db.py`로의 마이그레이션 흔적이 같은 디렉터리에 보이는 건 이 이슈를 알고 있다는 신호다.
- **fallback 분기의 임의성** — fit 전 임시 분류는 비율 합 0.3 / 0.6 임계값으로 나누는데, 이는 도메인 근거 없는 매직 넘버에 가깝다. 카테고리 비율 합은 정상값이 1.0 근처라 0.3 미만이면 사실 "거래가 거의 없는 사용자"에 가깝다 — 즉 fallback의 "절약형" 라벨이 실제 절약형이 아니라 "데이터 부족"을 가리키는 경우가 많다.
- **explain의 안정성 가정** — `top_pull_toward / top_pull_away`는 deviation이 음수/양수인 첫 항목을 집어내는데, 사용자 벡터가 군집 중심과 거의 같으면 둘 중 하나가 빈 문자열이 된다. 그 결과 summary_text가 "', X 지출이 낮음" 식으로 어색하게 시작할 수 있다.

---

### 예상 질문 & 답변 (발표 Q&A 대비)

**Q1. 왜 K=4 클러스터인가요? 엘보우/실루엣 분석은?**
> 4개 라벨(절약형·균형형·소비형·투자형)은 도메인 정의가 먼저였고 군집 수를 거기에 맞췄습니다. 실루엣 점수 기반 자동 K 선정은 운영 데이터 누적 후 K=3~6 범위에서 재평가 예정.

**Q2. 비지도 학습인데 모델 정확도는 어떻게 검증하나요?**
> 비지도라 직접 정확도는 못 매기지만, 군집 중심 비율 합 기반 라벨 매핑이 결정적이라 **재학습마다 라벨이 뒤바뀌지 않는다**는 안정성을 검증합니다. 향후 사용자 자가 신고 라벨로 ARI(Adjusted Rand Index) 측정 예정.

**Q3. 카테고리 비율 11차원만 보고 분류해도 충분한가요?**
> 절대 금액·소득 대비 지출률·시점은 다른 모델(#7 XGBoost 과소비, #6 LSTM 예측)이 담당하는 분리 설계입니다. K-Means는 "지출 구조의 형태"만, 다른 ML이 "지출 강도와 시점"을 보완.

**Q4. 거래가 거의 없는 신규 사용자(콜드 스타트)는?**
> fit 전에는 비율 합 0.3/0.6 임계값 규칙 fallback으로 임시 라벨을 줍니다. 다만 ⑤절에서 지적한 대로 fallback의 "절약형"이 실제로는 "데이터 부족"인 경우가 많아, 향후 `is_cold_start: bool` 플래그 응답 포함 계획.

**Q5. 학습 중 예측 요청이 들어오면?**
> 현재는 모듈 싱글턴이라 학습/예측 동시 호출 시 일시적 모순 가능 (⑤절 참조). 운영 시 락 또는 swap 패턴(새 모델 학습 후 atomic 교체)이 필요한 후속 작업.

---

## ⑥ 한 줄 정리

K-Means 4-클러스터로 카테고리 비율 분포만 보고 사용자를 절약형/균형형/소비형/투자형으로 라벨링하되, **군집 중심 비율 합 정렬**로 라벨 매핑을 안정화하고 **fit 전 규칙 fallback**으로 콜드스타트를 막는 게 PayWise 소비 패턴 분석의 골격이다.
