# FDS 강화 로드맵 — "이상 스크리너 → 진짜 FDS" 전환

> 본 문서는 PayWise FDS(fraud-service)를 단순 카드 결제 이상 스크리닝에서
> 운영급 사기 탐지 시스템으로 격상하기 위한 전용 스프린트 계획서.
>
> 단일 진척 트래커: [`docs/ROADMAP.md`](ROADMAP.md) 의 **W5.5 / W6.5 / W7.5** 섹션.
> 다른 세션 인계 시 시작점: [`docs/FDS_RESUME.md`](FDS_RESUME.md).

## Why — 현재 갭

블로그 [`12_실시간_사기_점수_IF_RF_하이브리드.md`](blog/12_실시간_사기_점수_IF_RF_하이브리드.md) 의 "도메인 확장 로드맵" 섹션에 명시된 한계:

- **데이터**: Kaggle creditcard.csv (V1~V30 PCA 익명 카드결제) — 송금자/수취자 관계 없음
- **라벨**: `final_action ∈ {PASS, SOFT_REVIEW, REVIEW, BLOCK}` 4단계만 있고 **사기 유형** 미식별
- **그래프**: 단일 거래 단위 평가만, 거래 *네트워크* 패턴 (머니뮬 hub-spoke) 검출 불가
- **비용**: 모든 거래에 동일 임계값 — 1만원과 1억원 거래의 BLOCK 비용 차이 무시
- **검증**: "어떤 사기 유형을 몇 % 잡는가" 정량 답변 부재

**이게 빠지면 캡스톤 발표에서 "진짜 FDS인가?" 질문에 답할 수 없다.**

## What — 4축 전환 지도

| 축 | 핵심 변경 | 캡스톤 가치 | 의존성 |
|---|---|---|---|
| **① 데이터·도메인** | PaySim 도입 + 사기 유형 multiclass | "송금 사기 도메인" 답변 | 모든 후속 트랙의 전제 |
| **② 그래프** | 송금 네트워크 피처 (`graph_features.py`) | "머니뮬·hub-spoke" 검출 | ① PaySim 필수 |
| **③ 비용·운영** | expected_loss 기반 임계값, 시나리오 시뮬레이터 | "운영 사고 직결" 답변 | 독립 |
| **④ 시계열·시퀀스** | 잔액 급변 패턴, 사용자 시퀀스 LSTM | "단일 거래 vs 패턴" 답변 | ① PaySim 필수 |

---

## 스프린트 구조 (W5.5 / W6.5 / W7.5)

### W5.5 — PaySim 도메인 확장 (약 2주, 우선순위 최상)

목표: 데이터셋 교체 → 사기 유형 학습 → 검출률 측정 체계.

| # | 작업 | 작업량 | 출처 | 산출물 |
|---|---|---|---|---|
| **W5.5-#1** | 시나리오 시뮬레이터 (보이스피싱/머니뮬/계정탈취/카드테스팅) | 반나절 | `12-Track 2` | `fraud-service/app/services/scenario_generator.py` + `routes_scenario.py` + 검출률 표 |
| **W5.5-#2** | PaySim 데이터셋 다운로드 + 로더 | 반나절 | `12-Track 1` 전제 | `fds-research/data/paysim.csv` (.gitignore 등록) + `make paysim-download` 스크립트 |
| **W5.5-#3** | PaySim 학습 스크립트 (Isolation Forest + RF) | 3일 | `12-Track 1` | `fds-research/train_paysim.py` + 신규 model bundle (V1~V30 → PaySim feature 셋) |
| **W5.5-#4** | fraud-service 입력 스키마 PaySim 정합화 | 2일 | `12-Track 1` | `app/scoring/features.py` 컬럼 매핑 (type/oldbalance/newbalance), `_normalize_anomaly` 상수 재튜닝 |
| **W5.5-#5** | `fraud_type` 다중분류 라벨 도입 | 3일 | `12-Track 3` | `policy_merge.py` 룰→유형 매핑 + `routes_fraud.py` 응답 스키마 `fraud_type` 필드 |
| **W5.5-#6** | 불균형 데이터 처리 (SMOTE 또는 class_weight) | 1일 | 신규 | PaySim 사기 비율 0.13% 대응, 학습 스크립트 옵션 추가 |
| **W5.5-#7** | 시나리오별 검출률 회귀 테스트 | 1일 | `12-Track 2` 확장 | `tests/test_scenario_detection.py` + CI 통합 (목표: 시나리오별 ≥80% 검출) |

**완료 조건**: PaySim 학습 모델 인입 + 4개 시나리오 검출률 ≥80% + `fraud_type` 응답 노출.

### W6.5 — 그래프 + 비용 가중 (약 2주)

목표: 단일 거래 평가 → 네트워크·금액 가중 평가.

| # | 작업 | 작업량 | 출처 | 산출물 |
|---|---|---|---|---|
| **W6.5-#1** | 송금 그래프 store (Redis sorted set) | 3일 | `12-Track 4` | `fraud-service/app/services/graph_store.py` (sender→receiver 엣지 + TTL) |
| **W6.5-#2** | 그래프 피처 추출기 | 3일 | `12-Track 4` | `app/services/graph_features.py`: `dest_first_seen_within_24h`, `dest_inbound_velocity_1h`, `fan_in_count`, `pass_through_ratio` |
| **W6.5-#3** | 머니뮬 hub-spoke 탐지 룰 | 2일 | `13-Track A` 부분 | `rule_engine.MoneyMuleRule` (fan_in≥N + 통과율 80%↑) |
| **W6.5-#4** | 다단계 자금세탁(layering) 탐지 룰 | 2일 | `13-Track A` 부분 | `rule_engine.LayeringRule` (A→B→C 단시간 송금 + 잔액 통과) |
| **W6.5-#5** | 비용 가중 BLOCK 임계값 (`expected_loss = p × amount`) | 2일 | 신규 | `fraud_service.FraudServiceManager` 임계값 로직 교체 + `COST_THRESHOLD_KRW` env |
| **W6.5-#6** | 유형별 임계값 차등 (머니뮬 0.5, 카드테스팅 0.7) | 1일 | 신규 | `policy_merge.py` 유형별 임계값 dict |
| **W6.5-#7** | 그래프 + 비용 통합 검출률 측정 (W5.5-#7 확장) | 1일 | 신규 | 머니뮬 시나리오 검출률 ≥90%, 단일 시그널보다 +X% 개선 측정 |

**완료 조건**: 머니뮬 시나리오 검출률 측정 가능 + 비용 임계값 도입 후 BLOCK 비용 효율 측정.

### W7.5 — 시계열·운영 신뢰성 (약 2주)

목표: 진짜 운영용 FDS — 패턴·드리프트·피드백 루프.

| # | 작업 | 작업량 | 출처 | 산출물 |
|---|---|---|---|---|
| **W7.5-#1** | 잔액 급변 패턴 룰 (`oldbalance → newbalance` 분석) | 2일 | 신규 | `BalanceDrainRule` |
| **W7.5-#2** | 사용자 시퀀스 LSTM 도입 (직전 N건 → 다음 정상도 예측) | 1주 | `14-Track γ` 확장 | `forecasting.py` 재활용, `app/scoring/sequence_score.py` |
| **W7.5-#3** | 시간대 외 거래 군집 탐지 | 1일 | 신규 | 사용자별 평균 활동 시간대 학습 + 이탈 시 시그널 |
| **W7.5-#4** | chargeback 피드백 루프 (ground truth 라벨링 API) | 3일 | 신규 | `POST /v1/fraud/feedback/chargeback` + 일별 라벨 누적 + W7-#7 (precision/recall) 와 결합 |
| **W7.5-#5** | 적대적 회귀 테스트 (12-Track 2 확장) | 2일 | 신규 | 정교한 머니뮬 체인·smurfing·CASH_OUT 분할 시나리오 추가 |
| **W7.5-#6** | FDS SLO 정의 + 검출률 대시보드 | 2일 | 신규 | `routes_security_dashboard.py` 확장: 시나리오별 검출률·평균 latency·FN/FP 비율 시계열 |

**완료 조건**: chargeback 피드백 루프 작동 + SLO 대시보드에 모든 시나리오 검출률 노출.

---

## PaySim 데이터셋 도입 가이드

### 자동 다운로드 (Kaggle API)

```bash
# 1) Kaggle API 키 발급 (kaggle.com/account → Create New API Token)
mkdir -p ~/.kaggle
mv ~/Downloads/kaggle.json ~/.kaggle/kaggle.json
chmod 600 ~/.kaggle/kaggle.json

# 2) 다운로드 (W5.5-#2 산출물 스크립트)
cd fds-research
make paysim-download
# → data/paysim.csv (~470MB, 6.3M rows)
```

### 수동 다운로드

[kaggle.com/datasets/ealaxi/paysim1](https://www.kaggle.com/datasets/ealaxi/paysim1) 접속 → "Download" → 압축 해제 후 `fds-research/data/paysim.csv` 배치.

### 데이터 스키마

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `step` | int | 시뮬레이션 시간 단위 (1 step = 1시간) |
| `type` | str | `CASH_IN`, `CASH_OUT`, `DEBIT`, `PAYMENT`, `TRANSFER` |
| `amount` | float | 거래 금액 |
| `nameOrig` | str | 송금자 ID (`C`로 시작 = customer, `M` = merchant) |
| `oldbalanceOrg` | float | 송금 전 잔액 |
| `newbalanceOrg` | float | 송금 후 잔액 |
| `nameDest` | str | 수취자 ID |
| `oldbalanceDest` | float | 수취 전 잔액 |
| `newbalanceDest` | float | 수취 후 잔액 |
| `isFraud` | int (0/1) | **도메인 라벨 — 학습 타겟** |
| `isFlaggedFraud` | int | 200K↑ 단일 거래 자동 차단 (룰 기반, 거의 0) |

### 도메인 매핑

| PaySim type | PayWise 매핑 | 룰 적용 |
|---|---|---|
| `TRANSFER` | 사용자→사용자 송금 | MoneyMuleRule, LayeringRule |
| `CASH_OUT` | ATM 출금 | BalanceDrainRule, AmountSpikeRule |
| `PAYMENT` | 가맹점 결제 | 기존 카드결제 룰 재활용 |
| `CASH_IN` | 입금 | 학습만, 차단 대상 아님 |
| `DEBIT` | 직불 결제 | 기존 룰 재활용 |

PaySim의 `isFraud` 분포: TRANSFER + CASH_OUT 에만 사기 발생 (전체의 0.13%) → 이 두 타입에 학습·평가 집중.

---

## 핵심 변경 파일 (착수 시 우선 열어볼 곳)

- `fds-research/data/paysim.csv` — 신규, .gitignore
- `fds-research/train_paysim.py` — 신규 학습 스크립트
- `fds-research/Makefile` — `paysim-download` 타겟 추가
- `fraud-service/app/scoring/features.py` — PaySim 컬럼 매핑
- `fraud-service/app/scoring/ensemble.py` — `_normalize_anomaly` 상수 재튜닝
- `fraud-service/app/services/graph_store.py`, `graph_features.py` — 신규
- `fraud-service/app/services/rule_engine.py` — `MoneyMuleRule`, `LayeringRule`, `BalanceDrainRule` 추가
- `fraud-service/app/services/policy_merge.py` — 룰→`fraud_type` 매핑 + 유형별 임계값
- `fraud-service/app/services/scenario_generator.py` — 신규
- `fraud-service/app/api/routes_scenario.py` — 신규
- `fraud-service/tests/test_scenario_detection.py` — 신규

---

## 검증 방법

1. **시나리오 검출률**: 4종 시나리오 각 100건 합성 → BLOCK+REVIEW 비율 ≥80%
2. **부하**: 그래프 store 1M 엣지 INSERT 후 `dest_inbound_velocity_1h` p99 < 50ms
3. **드리프트**: PaySim 분포에서 학습한 모델이 실제 거래 시뮬레이션에서도 AUC ≥0.85 유지
4. **회귀**: chargeback 피드백 100건 추가 후 precision/recall 회귀 테스트 통과
