# PayWise 향후 작업 로드맵

> `docs/blog/` 40개 문서에서 추출한 향후 과제 108건의 단일 진척 트래커.
> 작업 완료 시 체크박스 + 커밋 SHA + 날짜를 함께 기록한다.
>
> 원본 플랜: [`~/.claude/plans/docs-blog-snoopy-thompson.md`](../../.claude/plans/docs-blog-snoopy-thompson.md)

## 사용 규칙

- **체크 표기**: `- [x] 작업명 ... — ✅ <commit-sha> (YYYY-MM-DD)`
- **부분 완료**: `- [~] 작업명 ... — 🟡 진행중 (YYYY-MM-DD)` — 같은 작업이 여러 PR로 갈릴 때
- **블로그 글 갱신**: 작업 완료 시 해당 블로그 글의 "향후 과제" 섹션에도 `(✅ ROADMAP W?-#?)` 한 줄 추가
- **커밋 컨벤션**: `<type>(W?-#?): <짧은 설명>` 예) `feat(W1-#1): IDOR 차단 위해 알림 user_id를 JWT에서 추출`
- **진척률 갱신**: 주 1회 아래 "진척률" 표 카운터 수동 갱신

## 진척률

| 주차 | 영역 | 총 | 완료 | % |
|---|---|---|---|---|
| W1 | 인증·인가 보안 (P0) | 7 | 7 | 100% |
| W2 | 챌린지·세션 외부화 (P0) | 7 | 7 | 100% |
| W3 | 감사 체인 영속화 (P0) | 7 | 7 | 100% |
| W4 | 인프라 활성화 (P1) | 7 | 7 | 100% |
| **W5.5** | **FDS 강화: PaySim 도메인 확장 (P1, 신설)** | **8** | **8** | **100%** |
| **W6.5** | **FDS 강화: 그래프 + 비용 가중 (P1, 신설)** | **7** | **7** | **100%** |
| **W7.5** | **FDS 강화: 시계열·운영 신뢰성 (P2, 신설)** | **6** | **6** | **100%** |
| W5 | ML 정확성 (P1) | 8 | 4 | 50% |
| W6 | 모델 영속화·MLOps (P1) | 8 | 1 | 13% |
| W7 | 드리프트·관측·A/B (P1) | 9 | 7 | 78% |
| W8 | 거버넌스 (P2) | 8 | 0 | 0% |
| W9 | Quick wins (P3) | 16 | 16 | 100% |
| W10 | 검증·문서화 | 5 | 0 | 0% |
| **합계** | | **103** | **77** | **75%** |

> 🔥 **W5.5/W6.5/W7.5 = FDS 강화 신설 스프린트** — 상세 명세는 [`FDS_ROADMAP.md`](FDS_ROADMAP.md), 다른 세션 인계는 [`FDS_RESUME.md`](FDS_RESUME.md). 캡스톤 발표에서 "진짜 FDS인가?" 질문 대응 핵심.

> 참고: 플랜 표기 "108건"은 동일 작업의 여러 블로그 출처를 별도 카운트한 수치이며, 실제 단일 작업 단위는 위 표의 **82건**.

---

## W1 — 인증·인가 보안 (P0)

목표: 외부에서 직접 악용 가능한 인증/인가 결함 봉쇄.

- [x] **W1-#1** 알림 REST API `user_id` 쿼리스트링 → JWT 추출 (IDOR 차단) — `21_알림_시스템.md:204` — [하/보안] — ✅ fb96fe4 (2026-05-02)
- [x] **W1-#2** JWT 블랙리스트 메커니즘 (jti 기반, 로그아웃·계정잠금 시 무효화) — `perspectives/threat/01:77` — [상/보안] — ✅ 4aa499c (2026-05-02)
- [x] **W1-#3** JWT HS256 → RS256 전환 + kid 헤더 다중 키 라우팅 — `perspectives/threat/01:76` + `01_기본인증:214` — [상/보안] — ✅ fefe706 (2026-05-02)
- [x] **W1-#4** ABE 마스터 시크릿 미설정 시 fail-fast 기동 중단 — `15_ABAC_ABE:517` — [하/보안] — ✅ fefe706 (2026-05-02)
- [x] **W1-#5** ABAC 엔진 ↔ ABE 미들웨어 wiring (8가지 룰 런타임 연결) — `15_ABAC_ABE:512` — [상/보안] — ✅ 74f6bb2 (2026-05-02)
- [x] **W1-#6** 클라이언트 시그널 HMAC 서명 + 서버사이드 보강 — `14_행동_시그널:191` — [상/보안] — ✅ d515839 (2026-05-02)
- [x] **W1-#7** 403 응답에서 `required_policy`/`your_attributes` 마스킹 (운영 모드) — `15_ABAC_ABE:513` — [하/보안] — ✅ 74f6bb2 (2026-05-02)

---

## W2 — 챌린지·세션 외부화 (P0)

목표: 인메모리 의존 → Redis/PG. 멀티 인스턴스·재시작 안전성.

- [x] **W2-#1** FIDO2 챌린지 3종 → Redis 단일 인터페이스 통합 — `02_FIDO2:360,364` — [중/인프라] — ✅ 2f5d504 (2026-05-02)
- [x] **W2-#2** step-up 토큰 store → Redis hash — `12_실시간_사기:327` — [중/인프라] — ✅ 8cfd028 (2026-05-02)
- [x] **W2-#3** 행동 시그널 DeviceStore → Redis sorted set + TTL — `14_행동_시그널:189` — [중/인프라] — ✅ 1ed2137 (2026-05-02)
- [x] **W2-#4** 룰 토글 상태 → Redis/DB 영속화 — `13_규칙_엔진:254` — [중/인프라] — ✅ 2d89817 (2026-05-02)
- [x] **W2-#5** 위협 인텔 in-memory → PostgreSQL/Redis — `17_위협_인텔리전스:168` — [중/인프라] — ✅ 7c1b11d (2026-05-02)
- [x] **W2-#6** 소비 프로필/추천 store → DB — `05_KMeans:240` + `10_추천:254` — [중/인프라] — ✅ e1b73eb (2026-05-02)
- [x] **W2-#7** velocity 계산 → Redis sorted set으로 O(1)화 — `13_규칙_엔진:251` — [중/인프라] — ✅ f047782 (2026-05-02)

---

## W3 — 감사 체인 영속화 + 클론 탐지 (P0)

목표: 감사 무결성 + WebAuthn 클론 위협 봉쇄.

- [x] **W3-#1** backend 인메모리 감사 체인 → PostgreSQL/Redis 영속화 — `04_보안_대시보드:283` + `journey/05:88` — [상/인프라] — ✅ a13e82d (2026-05-02)
- [x] **W3-#2** backend ↔ fraud-service 감사 체인 통합 (단일 정본) — `journey/05:87` + `threat/05:85` — [상/인프라] — ✅ 4de9f1d (2026-05-02)
- [x] **W3-#3** Genesis 블록 환경변수/마이그레이션 박제 — `16_블록체인:360` — [하/인프라] — ✅ 3a511c6 (2026-05-02)
- [x] **W3-#4** `_save()` 전체 재직렬화 → JSONL append-only로 O(1)화 — `16_블록체인:358` — [상/인프라] — ✅ 3a511c6 (2026-05-02)
- [x] **W3-#5** sign_count=0 처리 + 역행 시 클론 탐지 동작 — `02_FIDO2:362` — [중/보안] — ✅ eb43246 (2026-05-02)
- [x] **W3-#6** 감사 디스크 I/O 백그라운드 워커 분리 — `16_블록체인:364` — [중/인프라] — ✅ 3a511c6 (2026-05-02)
- [x] **W3-#7** 패스키 분실 백업 코드 발급/소진 흐름 — `02_FIDO2:381` + `threat/01:79` — [중/UX] — ✅ eb43246 (2026-05-02)

---

## W4 — 인프라 활성화 (P1)

목표: Kafka·BackgroundTasks·비동기 호출 도입.

- [x] **W4-#1** docker-compose에 Kafka 브로커 + topic retention 정책 — `19_Kafka:220` + `pipeline/04:89,93` — [중/인프라] — ✅ 762b67a (2026-05-02)
- [x] **W4-#2** `aiokafka` 의존 추가 + Producer 무음 실패 → DLQ/로깅 — `19_Kafka:219` + `pipeline/04:90` — [중/인프라] — ✅ 762b67a (2026-05-02)
- [x] **W4-#3** `_process_message`를 `asyncio.to_thread`로 감싸 이벤트루프 블로킹 제거 — `19_Kafka:207` — [중/백엔드] — ✅ 762b67a (2026-05-02)
- [x] **W4-#4** DLQ topic + 알람 + consumer 재시작 워치독 — `19_Kafka:205,209,211` — [중/인프라] — ✅ 762b67a (2026-05-02)
- [x] **W4-#5** 가입 시 ML 학습을 BackgroundTasks/Celery로 분리 — `01_기본인증:217` + `20_학습:112` — [중/인프라] — ✅ 762b67a (2026-05-02)
- [x] **W4-#6** FCM `send_sync` → `asyncio.to_thread` 래핑 + Redis pub/sub 단일 경로 — `21_알림:208,210` — [중/백엔드] — ✅ 762b67a (2026-05-02)
- [x] **W4-#7** user_id 기준 Kafka 파티셔닝으로 순서 보장 — `pipeline/04:92` — [중/백엔드] — ✅ 762b67a (2026-05-02)

---

## W5.5 — FDS 강화: PaySim 도메인 확장 (P1, 신설) 🔥

목표: 데이터셋 교체 → 사기 유형 multiclass → 검출률 측정 체계. 캡스톤 핵심 차별화.
**상세 명세**: [`FDS_ROADMAP.md § W5.5`](FDS_ROADMAP.md).

- [x] **W5.5-#1** 시나리오 시뮬레이터 4종 (보이스피싱/머니뮬/계정탈취/카드테스팅) — `12-Track 2` — [중/ML] — ✅ 2b8650a (2026-05-05)
- [x] **W5.5-#2** PaySim 데이터셋 다운로드 + 로더 (`make paysim-download`) — `12-Track 1 전제` — [하/인프라] — ✅ be5adc2 (2026-05-05)
- [x] **W5.5-#3** PaySim 학습 스크립트 (`fds-research/train_paysim.py`) — `12-Track 1` — [상/ML] — ✅ 29663c3 (2026-05-05)
- [x] **W5.5-#4** fraud-service 입력 스키마 PaySim 정합화 + `_normalize_anomaly` 재튜닝 — `12-Track 1` — [중/ML] — ✅ db61630 (2026-05-05)
- [x] **W5.5-#5** `fraud_type` 다중분류 라벨 (룰→유형 매핑) — `12-Track 3` — [중/ML] — ✅ f3ac83f (2026-05-05)
- [x] **W5.5-#6** 불균형 데이터 처리 (SMOTE 또는 class_weight, PaySim 사기율 0.13%) — 신규 — [중/ML] — ✅ 44a560e (2026-05-05)
- [x] **W5.5-#7** 시나리오별 검출률 회귀 테스트 (목표 ≥80%) — `12-Track 2 확장` — [중/테스트] — ✅ f9988f1 (2026-05-05)
- [x] **W5.5-#8** PaySim 번들로 운영 모델 전환 + 누수 해소 + profile ingest wiring — 신규 audit — [상/ML+백엔드] — ✅ ecc044e (2026-05-05)
  1. `train_paysim.py --split-by-step` 시간순 split + `--no-leakage` ablation 옵션
  2. evaluate flow 에 `profile_store.ingest` 자동 호출 (velocity 룰 활성화)
  3. `MODEL_PATH` 기본값을 `model_bundle_paysim_time_clean.joblib` 로 전환 (.env, docker-compose)
  4. 시간순 split AUC 0.99999~1.0 (누수 피처 ablation 후에도 동등 성능, 정직성 입증)

---

## W6.5 — FDS 강화: 그래프 + 비용 가중 (P1, 신설) 🔥

목표: 단일 거래 평가 → 송금 네트워크·금액 가중 평가. 머니뮬 검출.
**상세 명세**: [`FDS_ROADMAP.md § W6.5`](FDS_ROADMAP.md).

- [x] **W6.5-#1** 송금 그래프 store (Redis sorted set, sender→receiver 엣지 + TTL) — `12-Track 4` — [상/인프라] — ✅ d72a653 (2026-05-05)
- [x] **W6.5-#2** 그래프 피처 추출기 (`graph_features.py`: `dest_first_seen`, `fan_in_count`, `pass_through_ratio`) — `12-Track 4` — [상/ML] — ✅ cd12b3d (2026-05-05)
- [x] **W6.5-#3** 머니뮬 hub-spoke 룰 (`MoneyMuleRule`) — `13-Track A` 부분 — [중/백엔드] — ✅ be11664 (2026-05-05)
- [x] **W6.5-#4** 다단계 자금세탁 룰 (`LayeringRule`) — `13-Track A` 부분 — [중/백엔드] — ✅ c2e91f5 (2026-05-05)
- [x] **W6.5-#5** 비용 가중 BLOCK 임계값 (`expected_loss = p × amount`, `COST_THRESHOLD_KRW` env) — 신규 — [중/ML] — ✅ bbbc717 (2026-05-05)
- [x] **W6.5-#6** 유형별 임계값 차등 (머니뮬 0.5, 카드테스팅 0.7) — 신규 — [하/백엔드] — ✅ da1b8fe (2026-05-05)
- [x] **W6.5-#7** 그래프 + 비용 통합 검출률 측정 (머니뮬 ≥90% 목표) — 신규 — [중/테스트] — ✅ 187e393 (2026-05-06)

---

## W7.5 — FDS 강화: 시계열·운영 신뢰성 (P2, 신설) 🔥

목표: 패턴·드리프트·피드백 루프 — 진짜 운영용 FDS.
**상세 명세**: [`FDS_ROADMAP.md § W7.5`](FDS_ROADMAP.md).

- [x] **W7.5-#1** 잔액 급변 패턴 룰 (`BalanceDrainRule`, oldbalance→newbalance 분석) — 신규 — [중/백엔드] — ✅ 769266a (2026-05-07)
- [x] **W7.5-#2** 사용자 시퀀스 LSTM 도입 (직전 N건 → 다음 정상도 예측) — `14-Track γ 확장` — [상/ML] — ✅ 44c1ab3 (2026-05-09)
- [x] **W7.5-#3** 시간대 외 거래 군집 탐지 (사용자별 평균 활동 시간 학습) — 신규 — [중/ML] — ✅ 587a213 (2026-05-07)
- [x] **W7.5-#4** chargeback 피드백 루프 (`POST /v1/fraud/feedback/chargeback` + ground truth 라벨) — 신규 — [상/백엔드] — ✅ 08d9613 (2026-05-09)
- [x] **W7.5-#5** 적대적 회귀 테스트 (정교한 머니뮬 체인·smurfing·CASH_OUT 분할) — 신규 — [상/테스트] — ✅ c789a25 (2026-05-07)
- [x] **W7.5-#6** FDS SLO 대시보드 (시나리오별 검출률·latency·FN/FP 시계열) — 신규 — [중/백엔드] — ✅ 8ae914f (2026-05-09)

---

## W5 — ML 정확성 (P1)

목표: 가중치 하드코딩·정규화 가정 등 ML 신뢰도 결함 해결.

- [x] **W5-#1** 앙상블 ALPHA/BETA → `SYSTEM_CONFIG`/env 외부화 + 동적 조정 — `12_사기점수:119` + `journey/04:99` + `threat/04:86` — [중/ML] — ✅ d2932b8 (2026-05-09)
- [ ] **W5-#2** IF 정규화 상수 → 학습 시 quantile 기반 자동 추정 후 번들 저장 — `12_사기점수:323` + `pipeline/03:106` — [상/ML]
- [ ] **W5-#3** 사용자별 적응형 step-up 임계값 (전역 0.6 제거) — `03_Step-up:239` + `journey/04:102` + `threat/02:87` — [상/ML]
- [ ] **W5-#4** LSTM 신뢰도 → 예측 분산 추정 + 모델 가중치 영속화 — `06_LSTM:229,231` — [상/ML]
- [x] **W5-#5** XGBoost 학습 (mu, std) 번들 저장 → 단건 z-score 일관성 — `07_XAI:266` — [중/ML] — ✅ 9de2c1f (2026-05-09)
- [ ] **W5-#6** 카테고리 분류 confidence score 도입 + 가중치화 — `journey/03:84` + `pipeline/01:87` — [상/ML]
- [x] **W5-#7** KMeans K값 silhouette 자동 선정 + cold-start 플래그 — `05_KMeans:249,258` — [중/ML] — ✅ 84dd4b9 (2026-05-10)
- [x] **W5-#8** 감정 라벨 룰 → JSON/DSL 외부화 — `journey/03:86` + `pipeline/01:89` — [중/백엔드] — ✅ f6123ed (2026-05-09)

---

## W6 — 모델 영속화 + 학습 자동화 (P1)

- [ ] **W6-#1** `train_all()` 결과 `joblib.dump`로 디스크 저장 + 부팅 시 자동 로드 — `20_학습:198` — [중/ML]
- [x] **W6-#2** `model_loader.py`에 `@functools.lru_cache(maxsize=1)` — `20_학습:178` — [하/백엔드] — ✅ 8c4df96 (2026-05-09)
- [ ] **W6-#3** 번들 포맷 스키마 정의 + 로드 시 키/predict_proba/입력차원 검증 — `pipeline/02:95` + `mlops/02:91` — [중/백엔드]
- [ ] **W6-#4** 메타데이터 자동 검증 (AUC 임계값 미달 시 거부) — `pipeline/02:97` + `mlops/04:90` — [중/ML]
- [ ] **W6-#5** fds-research → fraud-service MLflow/DVC 버전 관리 + CI/CD — `20_학습:200` + `pipeline/02:94` + `mlops/02:90` — [상/인프라]
- [ ] **W6-#6** 학습 환경 컨테이너화 (Dockerfile + CI 학습) — `mlops/01:91` — [상/인프라]
- [ ] **W6-#7** 학습 진행 상태 DB 테이블 기록 (부분 실패 추적) — `20_학습:114` — [중/백엔드]
- [ ] **W6-#8** ORDER BY random() → TABLESAMPLE BERNOULLI 최적화 — `20_학습:157` — [중/백엔드]

---

## W7 — 드리프트·관측·A/B (P1)

- [x] **W7-#1** Feature drift 자동 탐지 (KS 검정 / 분위수 차이) — `mlops/04:87` + `threat/04:90` — [상/ML] — ✅ 9a19771 (2026-05-10)
- [x] **W7-#2** 추론 latency 단계별 측정 + 응답헤더/메트릭 노출 (P99) — `pipeline/03:108` + `mlops/04:88` — [중/백엔드] — ✅ 23a6df9 (2026-05-09)
- [x] **W7-#3** 모델 점수 분포 일별 모니터링 (평균·분위수 시계열) — `mlops/04:89` — [중/백엔드] — ✅ 4a22b7a (2026-05-10)
- [x] **W7-#4** 분포 변화 임계값 알람 + **자동 롤백** — `mlops/04:91,92` — [상/인프라] — ✅ f9ba448 (2026-05-10)
- [x] **W7-#5** A/B 트래픽 비율 동적 조정 API (1% → 10% → 50%) — `18_AB:168` + `mlops/02:94` + `mlops/03:90` — [상/백엔드] — ✅ tbd (2026-05-10)
- [x] **W7-#6** shadow_evaluate ↔ `_evaluate_one` wiring + `_record()` — `18_AB:174` — [중/ML] — ✅ f4d1b95 (2026-05-09)
- [ ] **W7-#7** A/B 통계적 유의성 검정 자동화 (chi-square / t-test) — `mlops/03:92` — [상/ML]
- [x] **W7-#8** HMAC 기반 A/B 라우팅 키로 예측 불가능성 강화 — `18_AB:180` — [중/보안] — ✅ b1fc4d1 (2026-05-10)
- [ ] **W7-#9** ground truth precision/recall 비교 메트릭 — `18_AB:178` — [상/ML]

---

## W8 — 거버넌스·정책 통합 (P2)

- [ ] **W8-#1** ABAC 룰 단일 진실 출처 확립 (backend 5개 vs fraud 8개 통합) — `journey/05:89` + `threat/03:88` — [상/거버넌스]
- [ ] **W8-#2** 위협 인텔 외부 OSINT/상용 피드 연동 + 신뢰도 가중 — `journey/05:90` + `threat/05:88` — [상/거버넌스]
- [ ] **W8-#3** 정책 YAML 핫 리로드 (파일 watch / admin API) — `15_ABAC_ABE:525` — [중/인프라]
- [ ] **W8-#4** 감사 로그 보존 정책 모듈화 (5년 보관 컴플라이언스) — `threat/05:89` — [중/거버넌스]
- [ ] **W8-#5** 알림 채널 우선순위·중복 억제 정책 — `journey/05:91` — [중/백엔드]
- [ ] **W8-#6** OR 결합 false-positive 비용 평가 + 정책 조정 — `threat/04:87` — [상/거버넌스]
- [ ] **W8-#7** 비즈니스 KPI ↔ ML 지표 매핑 문서화 — `mlops/03:94` — [상/문서]
- [ ] **W8-#8** revocation_manager.filter_attrs() 미들웨어 적용 — `15_ABAC_ABE:521` — [중/보안]

---

## W9 — Quick wins (P3 / 일괄)

- [x] **W9-#1** 11_금융교육 퀴즈 채점 정답 검증 버그 수정 — `11_금융_교육:286` — [하/백엔드] — ✅ 98f29ff (2026-05-09)
- [x] **W9-#2** 22_평가 `compliance_rate` → `production_ready_rate` KeyError 수정 — `22_모델_평가:160` — [하/백엔드] — ✅ 74574b6 (2026-05-09)
- [x] **W9-#3** 12_사기점수 ALPHA/BETA env 외부화 — `12_실시간_사기:119` — [하/백엔드] — ✅ ac48c0d (2026-05-09)
- [x] **W9-#4** 13_룰엔진 `window_minutes` 기본값 5로 조정 — `13_규칙_엔진:249` — [하/백엔드] — ✅ 84fc101 (2026-05-09)
- [x] **W9-#5** 14_행동시그널 임계값 env 분리 + 원점수 보존 — `14_행동_시그널:185,187` — [하/백엔드] — ✅ 1c3d3bb (2026-05-09)
- [x] **W9-#6** 21_알림 Redis pub/sub vs 직접 send 중복 제거, mark_all_read commit 통일 — `21_알림_시스템:202,206` — [하/백엔드] — ✅ 762b67a (2026-05-02, W4-#6과 함께)
- [x] **W9-#7** 18_AB bundle_b 로드 실패 ERROR 로그 + soft_review 키 분리 — `18_AB_테스트:155,182` — [하/백엔드] — ✅ 6ff5fef (2026-05-09)
- [x] **W9-#8** 06_LSTM 클램프 발생률 헬스체크 메트릭 + seed 고정 훅 — `06_지출_예측_LSTM:232,233` — [하/백엔드] — ✅ 14ab8a3 (2026-05-09)
- [x] **W9-#9** 08_카테고리 ingest 경로 wiring + 키워드 우선순위 문서화 — `08_카테고리_자동_분류:157,159` — [하/백엔드] — ✅ e9d56ff (2026-05-09)
- [x] **W9-#10** 09_감정 알림 누락 감사 로그 + 의존성 주입 정리 — `09_감정_기반_소비_분석:305,307` — [하/백엔드] — ✅ 707d739 (2026-05-09)
- [x] **W9-#11** 04_대시보드 MyData 동의 철회 소유권 검증 — `04_보안_대시보드:289` — [하/백엔드] — ✅ f5bd917 (2026-05-09)
- [x] **W9-#12** 01_기본인증 TOTP `valid_window` env 노출 — `01_기본인증:220` — [하/백엔드] — ✅ 58e8d0e (2026-05-09)
- [x] **W9-#13** 15_ABAC BidirectionalPolicy/CPABE_Simulator를 research/로 분리 — `15_ABAC_ABE:523` — [하/문서] — ✅ 69e7edb (2026-05-09)
- [x] **W9-#14** 16_블록체인 싱글턴 환경변수 오버라이드 — `16_블록체인:369` — [하/인프라] — ✅ 3a511c6 (2026-05-02)
- [x] **W9-#15** 17_위협 query Lock 범위 축소 + detail 타입 명시 — `17_위협_인텔리전스:172,174` — [하/백엔드] — ✅ 566f9a1 (2026-05-09)
- [x] **W9-#16** 22_평가 `sys.path` 조작 제거 + 패키지 등록 — `22_모델_평가:152` — [중/백엔드] — ✅ 36a3252 (2026-05-09)

---

## W10 — 검증·문서화

- [ ] **W10-#1** e2e 통합 테스트 (회원가입 → step-up → 사기탐지 → 감사) 시나리오 통과
- [ ] **W10-#2** 부하 테스트: P99 latency, Kafka 처리량, 감사 체인 1M 삽입
- [ ] **W10-#3** 각 블로그 글의 "향후 과제" 섹션에 (✅ ROADMAP W?-#?) 표기 일괄 갱신
- [ ] **W10-#4** `docs/blog/perspectives/mlops/04_운영_관측과_향후_과제.md`에 "1차 마무리" 부록 추가
- [ ] **W10-#5** 메모리 `paywise_features_progress.md` / `paywise_perspectives_progress.md` 산출물 경로 + 완료 표시 갱신

---

## 변경 이력

| 날짜 | 주차 | 작업 | 커밋 |
|---|---|---|---|
| 2026-05-02 | — | ROADMAP 초안 작성 | (initial) |
| 2026-05-02 | W1-#1 | 알림 REST API IDOR 차단 (JWT 추출) | fb96fe4 |
| 2026-05-02 | W1-#2 | JWT 블랙리스트 (jti + Redis) + /v1/auth/logout + refresh 회전 | 4aa499c |
| 2026-05-02 | W1-#3 | JWT HS256↔RS256 양립 + kid 다중 키 라우팅 | fefe706 |
| 2026-05-02 | W1-#4 | ABE/JWT 시크릿 production fail-fast | fefe706 |
| 2026-05-02 | W1-#5,#7 | ABAC 엔진 wiring + 403 응답 마스킹 (production) | 74f6bb2 |
| 2026-05-02 | W1-#6 | 행동 시그널 HMAC 서명 + 서버사이드 IP 보강 | d515839 |
| 2026-05-02 | W2-#1 | FIDO2 챌린지 3종 Redis 단일 인터페이스 통합 | 2f5d504 |
| 2026-05-02 | W2-#2 | step-up store Redis hash 외부화 | 8cfd028 |
| 2026-05-02 | W2-#3 | DeviceStore Redis sorted set + TTL | 1ed2137 |
| 2026-05-02 | W2-#4 | 룰 토글 Redis Hash 영속화 + enabled 스킵 fix | 2d89817 |
| 2026-05-02 | W2-#5 | 위협 인텔 Redis List 영속화 | 7c1b11d |
| 2026-05-02 | W2-#6 | spend_profile DB 재수화 (lifespan startup) | e1b73eb |
| 2026-05-02 | W2-#7 | velocity 만료 prune + bisect O(log N) 카운트 | f047782 |
| 2026-05-02 | W3-#3,#4,#6 + W9-#14 | 감사 체인 Genesis 박제·JSONL append·백그라운드 writer·env path | 3a511c6 |
| 2026-05-02 | W3-#1 | backend 감사 체인 PG 영속화 (AuditChainEntry 테이블) | a13e82d |
| 2026-05-02 | W3-#2 | backend↔fraud 감사 체인 write-through 미러링 | 4de9f1d |
| 2026-05-02 | W3-#5,#7 | FIDO2 sign_count 클론 탐지 + 백업 코드 발급/소진 | eb43246 |
| 2026-05-02 | W4 전체 (#1~#7) + W9-#6 | Kafka 인프라 활성화 (브로커·DLQ·워치독·파티셔닝·async·BG ML·notify pubsub 단일) | 762b67a |
| 2026-05-02 | (planning) | W5.5/W6.5/W7.5 FDS 강화 스프린트 신설 (20건 추가, 총 102건) | 5e20d13 |
| 2026-05-05 | W5.5-#1 | 시나리오 시뮬레이터 4종 + /v1/scenario/run 검출률 집계 라우터 + 7개 테스트 | 2b8650a |
| 2026-05-05 | W5.5-#2 | PaySim CSV 배치(6.36M행) + scripts/paysim/load.py 표준 로더 + Makefile + .gitignore | be5adc2 |
| 2026-05-05 | W5.5-#3 | PaySim IF+RF 학습 스크립트 + 번들(2.77M행, AUC 0.9991/PR 0.9981/리콜 99.7%) | 29663c3 |
| 2026-05-05 | W5.5-#4 | fraud-service PaySim 스키마 정합화 (features/ensemble/routes_score 도메인 분기 + ANOMALY_RANGES 재튜닝) | db61630 |
| 2026-05-05 | W5.5-#5 | classify_fraud_type 7종 라벨 매핑 + /v1/fraud/evaluate 응답 fraud_type/fraud_type_label 필드 | f3ac83f |
| 2026-05-05 | W5.5-#6 | train_paysim.py --smote / --smote-k-neighbors 옵션 + class_weight vs SMOTE 비교 메트릭 | 44a560e |
| 2026-05-05 | W5.5-#7 | 시나리오별 ≥80% 검출률 + dominant fraud_type ≥50% 강건 회귀 테스트 9개 (profile_store velocity 시드) | f9988f1 |
| 2026-05-05 | W5.5-#8 | 운영 모델 PaySim 전환 (시간순 split + leakage ablation + ingest wiring + MODEL_PATH 기본 전환) | ecc044e |
| 2026-05-05 | W5.5-audit | Medium 갭 정리: ANOMALY_RANGES 풀 데이터 재측정·scenario paysim_raw 모드+모델 회귀·docstring·BLACKLIST 명세 | 89c42e8 |
| 2026-05-05 | W6.5-#1 | 송금 그래프 store (Redis sorted set 양방향 인덱스 + in-memory 폴백) + evaluate/Kafka 자동 적재 | d72a653 |
| 2026-05-05 | W6.5-#2 | 그래프 피처 추출기 6종 (first_seen·velocity·fan_in·pass_through_ratio 등) + evaluate 응답 노출 | cd12b3d |
| 2026-05-05 | W6.5-#3 | MoneyMuleRule (sender_fan_in≥3 ∧ pass_through≥0.8 → BLOCK) + classify_fraud_type 매핑 + sender 관점 피처 2종 | be11664 |
| 2026-05-05 | W6.5-#4 | LayeringRule (체인 패턴, fan_in<3 ∧ pass_through≥0.9 ∧ recent_inbound≤10min → REVIEW) + sender_recent_inbound_min_ago 피처 | c2e91f5 |
| 2026-05-05 | W6.5-#5 | 비용 가중 BLOCK (expected_loss = score×amount, COST_BLOCK_KRW/COST_REVIEW_KRW env) + evaluate 응답에 expected_loss | bbbc717 |
| 2026-05-05 | W6.5-#6 | fraud_type 별 차등 임계값 (mule 0.5/CT 0.7/VP 0.6/ATO 0.65/anomaly 0.85) + apply 헬퍼 | da1b8fe |
| 2026-05-06 | W6.5-#7 | 그래프+비용 통합 회귀 테스트 (≥90% 강건 + 응답 필드 활성, 2 PASS) + uplift 마이크로 벤치 분리 (저금액 50K +10% BLOCK 관측) | 187e393 |
| 2026-05-07 | W7.5-#1 | BalanceDrainRule (CASH_OUT/TRANSFER, drain≥90% AND amount≥500K AND old≥100K → BLOCK) + BALANCE_DRAIN fraud_type/임계값 0.55 + 10 PASS | 769266a |
| 2026-05-07 | W7.5-#3 | OffHoursClusterRule (UserProfile.hour_histogram + 미사용시간대 REVIEW / ≤5% SOFT_REVIEW, ACCOUNT_TAKEOVER 매핑, InMemory/Redis 양쪽 노출) + 10 PASS | 587a213 |
| 2026-05-07 | W7.5-#5 | 적대적 회귀 5종 (mule chain layering / smurfing 100K×20건 / CASH_OUT 25% drain 분할 + velocity 백업 / 단발 회피 한계 명시) + 5 PASS | c789a25 |
| 2026-05-09 | W7.5-#6 | FDS SLO 대시보드 (`/admin/api/slo`: 시나리오 7종 자동 라벨링·latency p50/p99·FN/FP·분 단위 시계열, stats_collector.slo_summary + routes_fraud latency 측정) + 7 PASS / 회귀 36 PASS | 8ae914f |
| 2026-05-09 | W7.5-#4 | chargeback 피드백 루프 (feedback_store InMemory/Redis + `POST /v1/fraud/feedback/chargeback` + `/feedback/metrics` precision/recall/F1) + 6 PASS / 회귀 30 PASS | 08d9613 |
| 2026-05-09 | W7.5-#2 | 사용자 시퀀스 정상도 점수 (sequence_score.py: 직전 N건 amount z-score + hour anomaly 합성, cold-start 가드, evaluate 응답 노출) + 8 PASS / 회귀 41 PASS | 44c1ab3 |
| 2026-05-09 | W9-#3 | 앙상블 ALPHA/BETA env 외부화 (ENSEMBLE_ALPHA/BETA, _env_float fallback) + 3 PASS / 회귀 19 PASS | ac48c0d |
| 2026-05-09 | W9-#4 | VelocityRule window_minutes 기본 10→5 (profile.velocity 키 1m/5m/15m 정합화, 회귀 21 PASS) | 84fc101 |
| 2026-05-09 | W9-#1 | 사기 퀴즈 채점 정답 검증 버그 수정 (_FRAUD_SCENARIOS id 부여 + _fraud_correct_answer_map 으로 question_id↔정답 대조) + 3 PASS | 98f29ff |
| 2026-05-09 | W9-#2 | evaluation_suite.py 'compliance_rate' KeyError 수정 (실제 키 production_ready_rate 로 print 2곳 교체) | 74574b6 |
| 2026-05-09 | W9-#5 | 행동 시그널 임계값 6종 env 외부화 (BEHAVIOR_T_*) + raw_score 필드 + UNTRUSTED_DECAY env (기존 회귀 11 PASS — W1-#6 untrusted decay 미반영 테스트 동시 정정) | 1c3d3bb |
| 2026-05-09 | W9-#12 | TOTP valid_window env 노출 (TOTP_VALID_WINDOW, 기본 1, 0~5 클립, totp_config.py 분리) — routes_auth 3곳 + routes_stepup 1곳 적용 + 5 PASS | 58e8d0e |
| 2026-05-09 | W9-#7 | A/B bundle_b 로드 실패 ERROR 로그 (load_bundle_b()) + soft_review 키 분리 (_record action 매핑 정정) + 4 PASS / 회귀 2 PASS | 6ff5fef |
| 2026-05-09 | W9-#11 | MyData 동의 철회 소유권 검증 (revoke_mydata_consent: get_current_user 주입 + JWT user_id 와 consent owner 일치 검사 + admin 우회) + 4 PASS | f5bd917 |
| 2026-05-09 | W9-#15 | intelligence_store query Lock 범위 축소 (snapshot 만 lock 안, reversed 밖) + detail 타입 docstring 명시 (dict | "[ENCRYPTED:...]" 문자열) — 회귀 6 PASS | 566f9a1 |
| 2026-05-09 | W9-#16 | fds_scripts 패키지 등록 (__init__.py) + routes_evaluation.py sys.path 디렉터리 주입 → from fds_scripts.evaluation_suite import 로 전환 + 2 PASS | 36a3252 |
| 2026-05-09 | W9-#8 | LSTM 클램프 발생률 헬스체크 (get_clamp_health, threshold 5%) + LSTM_SEED env 시드 고정 훅 (np/torch 동시) + 6 PASS | 14ab8a3 |
| 2026-05-09 | W9-#9 | 카테고리 ingest 경로 wiring (_autoclassify_if_other in spend_profile_db) + 키워드 우선순위 docstring 명시 (삽입 순서) + 6 PASS | e9d56ff |
| 2026-05-09 | W9-#10 | 감정 알림 누락 감사 로그 (_audit_emotion_notify_failure / get_emotion_notify_audit, max 200) + check_and_notify 의존성 주입 (notify_fn keyword-only) + status 반환 + 4 PASS | 707d739 |
| 2026-05-09 | W9-#13 | BidirectionalPolicy/CPABE_Simulator → app/research/abac_simulation.py 분리 + abe_engine __getattr__ lazy alias (순환 import 회피, 후방 호환) + 4 PASS / 회귀 16 PASS | 69e7edb |
| 2026-05-09 | W5-#1 | 앙상블 가중치 동적 조정 (ensemble.set_weights/get_weights + GET/PATCH /admin/api/ensemble-weights, 합 0~1.5 클립) + SYSTEM_CONFIG ENSEMBLE_ALPHA/BETA + 5 PASS / 회귀 5 PASS | d2932b8 |
| 2026-05-09 | W7-#2 | LatencyMiddleware (X-Process-Time-Ms / X-P50-Ms / X-P99-Ms 응답 헤더) + GET /admin/api/latency 경로별 통계 + 4 PASS / 회귀 13 PASS | 23a6df9 |
| 2026-05-09 | W6-#2 | model_loader `@lru_cache(maxsize=1)` + clear_model_cache/model_cache_info 노출, 동일 경로 hit 캐시 + 4 PASS / 회귀 13 PASS | 8c4df96 |
| 2026-05-09 | W7-#6 | shadow_evaluate ↔ /v1/score wiring + _evaluate_one 끝 ab_test._record(variant, action), ScoreRequest.tx_id / FraudEvaluateRequest.ab_variant 추가 + 4 PASS / 회귀 7 PASS | f4d1b95 |
| 2026-05-09 | W5-#8 | 감정 라벨 룰 JSON 외부화 (backend/app/policies/emotion_rules.json + reload_emotion_rules + EMOTION_RULES_PATH env) — 시간대/주말/스트레스 가중치/위험 등급/메시지 일괄 + 4 PASS | f6123ed |
| 2026-05-09 | W5-#5 | train_paysim 번들에 feature_mu/feature_std 저장 + reason_codes 3 함수에 mu/std 옵션 인자 + routes_score 가 번들 mu/std 를 reason_codes 에 주입 (단건 z-score 일관성) + 4 PASS / 회귀 7 PASS | 9de2c1f |
| 2026-05-10 | W5-#7 | KMeans 자동 K (silhouette k=2..6 최대화, KMEANS_AUTO_K env), cold-start 플래그 (표본<n_clusters → fit 스킵·predict 응답에 cold_start:True), labels 6단계 확장 + 4 PASS / 회귀 8 PASS | 84dd4b9 |
| 2026-05-10 | W7-#8 | A/B 라우팅 HMAC-SHA256 (AB_HMAC_SECRET env, 미설정 시 MD5 폴백) — 외부 tx_id 통제 환경에서도 분기 예측 불가능 + 4 PASS / 회귀 8 PASS | b1fc4d1 |
| 2026-05-10 | W7-#3 | 점수 분포 일별 모니터링 (`stats_collector.score_distribution_daily` + `GET /admin/api/score-distribution?days=N`, mean/p50/p95/p99/min/max + block_rate) + 4 PASS / 회귀 15 PASS | 4a22b7a |
| 2026-05-10 | W7-#1 | Feature drift KS 검정 (`drift_detector.py` 양측 KS + Smirnov p-value 근사 + 분위수 차이, evaluate flow 가 amount/score live 기록 + `GET /admin/api/drift?threshold=0.2`) + 6 PASS / 회귀 17 PASS | 9a19771 |
| 2026-05-10 | W7-#4 | 분포 알람 + 자동 롤백 (`alarm_manager.py` drift/score_p99_delta 임계값 → ensemble.set_weights(0,0) 강제 + audit log, `/admin/api/alarm` GET·check·restore + saved_weights 복원) + 6 PASS / 회귀 16 PASS | f9ba448 |
| 2026-05-10 | W7-#5 | A/B 트래픽 비율 동적 조정 (`ab_test.get/set_traffic_pct`, GET·PATCH `/admin/api/ab-traffic`, 0~100 클립, 프로세스 재시작 없이 ramp-up 1%→10%→50%) + 4 PASS / 회귀 12 PASS | tbd |
