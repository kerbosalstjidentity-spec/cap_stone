# FDS 보안 기능 확장 명세서 v2

> 교수님 연구 주제(ABE, Privacy-Preserving FL, Blockchain, Fine-grained Access Control,
> Edge Computing)를 **웹/모바일 금융 사기 탐지 플랫폼**에 접목하기 위한 기능 명세
>
> 핵심 전략: 교수님 논문의 응용 도메인(차량·IoT·메타버스)을 **웹/모바일 금융 서비스**로
> 치환하되, 핵심 기술(ABE, FL, Blockchain, Edge 처리)은 그대로 적용

---

## 0. 도메인 치환 원칙

교수님 연구의 핵심 기술은 도메인 독립적이다.

| 교수님 논문 원래 도메인 | → 본 프로젝트 대응 |
|---|---|
| 차량 OBD/CAN Bus 신호 | 웹 디바이스 핑거프린트 + 행동 생체인식 |
| RSU / Edge Node | CDN Edge / 브라우저 사이드 경량 스코어링 |
| IoT 기기 속성 (device_type, location) | 웹 세션 속성 (IP, browser, device, geolocation) |
| 메타버스 Cross-domain 플랫폼 | Cross-Service (은행·이커머스·PG사 간) |
| 차량 간 통신 (V2V, V2I) | 기관 간 통신 (Bank-to-Bank fraud intelligence) |

---

## 1. 전체 아키텍처

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Layer 1 │ Client / Edge  ─  Risk Signal Collection
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
         │  브라우저/앱에서 수집 후 서버로 전달
         │  - 디바이스 핑거프린트 (UA, 해상도, 타임존, WebGL)
         │  - 행동 생체인식 (마우스 속도, 키 입력 패턴, 스크롤)
         │  - 세션 이상 징후 (탭 전환, 체류 시간, Ctrl+V 감지)
         │  - 네트워크 컨텍스트 (IP 위치, VPN/프록시 감지)
         ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Layer 2 │ CP-ABE 기반 Fine-grained Access Control
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
         │  - 역할(analyst·admin·auditor) × 속성(기관·부서·등급)
         │  - API 응답 민감 필드를 CP-ABE로 선택적 암호화
         │  - 속성 불만족 시 해당 필드 복호화 불가
         ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Layer 3 │ ML 사기 탐지 엔진  (기존 FDS 재활용)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
         │  - XGBoost / RF 앙상블 스코어링
         │  - 룰 엔진 (금액·시간·속도·디바이스 변경)
         │  - SHAP 기반 reason codes
         │  - Layer 1 행동 시그널을 추가 피처로 통합
         ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Layer 4 │ Blockchain 불변 감사 추적
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
         │  - 모든 판정(PASS/REVIEW/BLOCK)을 해시 체인에 기록
         │  - 블록 = 판정 데이터 + prev_hash + timestamp
         │  - 변조 감지 + 무결성 검증 API
         ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Layer 5 │ FL 기반 Cross-Service 인텔리전스 공유
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
         │  - 복수 금융 서비스가 FL로 공동 모델 학습
         │    (원본 데이터 비공유, 모델 가중치만 교환)
         │  - ABE 암호화된 사기 패턴을 정책 만족 기관만 복호화
         │  - Differential Privacy 노이즈 적용
         │  - 기관별 기여도 검증 (Shapley Value)
```

---

## 2. 교수님 논문과의 1:1 연결

| Layer | 교수님 논문 | 적용 내용 |
|-------|------------|-----------|
| **L1** | "EC-SVC: Edge Computing 기반 차량 내 통신" (TIFS 2022) | 클라이언트 사이드 경량 리스크 시그널 수집·사전 스크리닝 |
| **L1** | "차량 보안 위협 방지 공격 대응 및 지능형 RSU 기술" (IITP 프로젝트) | 행동 생체인식 기반 이상 감지 (RSU → 브라우저/앱) |
| **L2** | "Privacy-preserving ABE with Bidirectional Access Control" (TDSC, to be submitted) | API 응답 민감 필드 CP-ABE 암호화 |
| **L2** | "Ensuring End-to-End Security with Fine-grained AC for CAV" (TIFS 2024) | 역할·속성 기반 엔드포인트 접근 제어 |
| **L4** | "Blockchain-Token Based Lightweight Handover Authentication" (to be submitted) | 판정 결과 해시 체인 불변 기록 |
| **L5** | "Secure and Verifiable Contribution Evaluation in FL" (TDSC, submitted) | 기관별 FL 기여도 검증 |
| **L5** | "Secure Data Sharing with Fine-grained AC for IoT Data Marketplace" (TNSM, revised) | ABE 암호화된 사기 패턴 교차 공유 |
| **L5** | "Cross-domain Fine-grained AC for IoT Data Sharing in Metaverse" (TDSC, submitted) | Cross-Service 인텔리전스 정책 기반 공유 |

---

## 3. 레이어별 상세 명세

### Layer 1: Client/Edge Risk Signal Collection

**목적**: 거래 발생 전·후 클라이언트에서 행동 시그널을 수집하여 ML 피처로 활용

#### 수집 항목

```yaml
# schemas/fds/behavioral_signals_v1.yaml
behavioral_signals:
  device_fingerprint:
    - user_agent_hash       # UA 해시 (식별자 아님, 패턴용)
    - screen_resolution     # 화면 해상도
    - timezone_offset       # UTC 오프셋
    - language              # 브라우저 언어
    - webgl_renderer_hash   # GPU 렌더러 해시
    - canvas_fingerprint    # Canvas 렌더링 해시

  behavioral_biometrics:
    - mouse_avg_speed       # 마우스 평균 이동 속도 (px/ms)
    - mouse_speed_variance  # 속도 분산 (불규칙성)
    - key_dwell_avg         # 키 누름 지속 시간 평균 (ms)
    - key_flight_avg        # 키 간 비행 시간 평균 (ms)
    - scroll_velocity       # 스크롤 속도 (px/s)
    - clipboard_paste_count # Ctrl+V 횟수 (자동화 감지)
    - form_fill_duration    # 결제 폼 작성 소요 시간 (ms)

  session_context:
    - tab_focus_changes     # 탭 전환 횟수
    - page_dwell_time       # 결제 페이지 체류 시간 (ms)
    - back_navigation_count # 뒤로가기 횟수
    - is_devtools_open      # 개발자 도구 감지

  network_context:
    - ip_country            # IP 국가 (ISO 3166-1)
    - is_vpn                # VPN 감지 여부
    - is_proxy              # 프록시 감지 여부
    - is_tor                # Tor 감지 여부
    - connection_type       # wifi / cellular / wired
```

#### 아키텍처

```
[브라우저 JS SDK / 앱 SDK]
    ├── 행동 시그널 수집 (비동기)
    └── 결제 요청 시 signals 첨부 → POST /v1/fraud/evaluate
                                         { transaction: {...}, signals: {...} }
```

#### 구현 위치

- **`fraud-service`**: `app/api/routes_fraud.py` request body에 `signals` 필드 추가
- **`fraud-service`**: `app/scoring/features.py`에 behavioral signal → feature matrix 변환 추가
- **`4_1_capstone`**: `schemas/fds/behavioral_signals_v1.yaml` 스키마 정의

---

### Layer 2: CP-ABE Fine-grained Access Control

**목적**: 현재 단순 API Key 인증을 속성 기반 세분화 접근 제어로 확장

#### 접근 정책 구조

```yaml
# policies/fds/abe_access_policy_v1.yaml
attributes:
  roles: [analyst, admin, auditor, viewer]
  departments: [fraud_team, compliance, risk, ops]
  institutions: [bank_a, bank_b, fintech_c, *]
  clearance_levels: [low, medium, high]

policies:
  - resource: "POST /v1/score"
    access_structure: "(role:analyst OR role:admin) AND dept:fraud_team"
    visible_fields: [transaction_id, score, action]
    encrypted_fields: [reason_code, feature_values]

  - resource: "POST /v1/fraud/evaluate"
    access_structure: "role:admin AND clearance:high"
    visible_fields: [transaction_id, action]
    encrypted_fields: [score, reason_code, rule_details, signals]

  - resource: "GET /v1/audit/chain"
    access_structure: "role:auditor OR role:admin"
    visible_fields: ["*"]
    encrypted_fields: []

  - resource: "GET /v1/intelligence/patterns"
    access_structure: "institution:* AND role:analyst AND clearance:medium"
    visible_fields: [pattern_type, frequency]
    encrypted_fields: [pattern_details, affected_accounts]
```

#### 구현 위치

- **`fraud-service`**: `app/middleware/abe_auth.py` (신규) — 속성 추출 + 정책 매칭
- **`fraud-service`**: `app/services/abe_engine.py` (신규) — CP-ABE 암호화/복호화
- **`4_1_capstone`**: `policies/fds/abe_access_policy_v1.yaml` (신규)

#### 기술 스택

- **`charm-crypto`**: Python CP-ABE 라이브러리 (Charm Framework)
- 또는 **직접 구현**: AES 기반 속성 정책 만족 검증 (경량화)

---

### Layer 4: Blockchain 불변 감사 추적

**목적**: 파일 기반 감사 로그를 해시 체인 기반 변조 불가 기록으로 강화

#### 블록 구조

```python
@dataclass
class AuditBlock:
    index: int
    timestamp: str              # ISO 8601
    transaction_id: str
    action: str                 # PASS | REVIEW | BLOCK
    score: float
    rule_ids: list[str]
    reason_code: str
    analyst_id: str             # ABE 속성 포함
    prev_hash: str              # 이전 블록 SHA-256 해시
    block_hash: str             # 현재 블록 해시 (자동 계산)

    def compute_hash(self) -> str:
        payload = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "transaction_id": self.transaction_id,
            "action": self.action,
            "score": round(self.score, 6),
            "rule_ids": sorted(self.rule_ids),
            "prev_hash": self.prev_hash,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()
```

#### 주요 API

```
GET  /v1/audit/chain/status    → 체인 길이, 최신 해시, 무결성 상태
GET  /v1/audit/chain/verify    → 전체 해시 체인 연속성 검증
GET  /v1/audit/block/{index}   → 특정 블록 조회
GET  /v1/audit/search?tx_id=X  → 거래 ID로 감사 기록 검색
```

#### 구현 위치

- **`fraud-service`**: `app/services/blockchain_audit.py` (신규)
- **`fraud-service`**: `app/api/routes_audit.py` (신규)
- **`fraud-service`**: 기존 `app/services/audit_logger.py` 연동 (판정 시 블록 자동 생성)

---

### Layer 5: FL 기반 Cross-Service 인텔리전스 공유

**목적**: 복수 금융 서비스가 원본 데이터 없이 협력 학습 + 암호화된 사기 패턴 공유

#### 연합학습 흐름 (시뮬레이션)

```
[데이터 파티셔닝]
  기존 데이터셋을 N개 기관으로 분할 (IID / Non-IID)

[로컬 학습]
  각 파티션에서 독립적으로 RF/LGBM 학습
  → 그래디언트 클리핑
  → Gaussian 노이즈 주입 (Differential Privacy, ε=1.0~10.0)

[Secure Aggregation]
  FedAvg: 가중치 평균으로 글로벌 모델 생성
  기여도 평가: Shapley Value 기반 기관별 기여도 측정

[성능 비교 실험]
  중앙 집중식 vs FL (IID) vs FL (Non-IID) 비교
  Metrics: AUC-ROC, AUC-PR, Recall@FPR=1%
```

#### ABE 암호화 패턴 공유

```
[기관 A: 사기 패턴 발견]
    │
    ▼ CP-ABE 암호화
    │  접근 정책: "institution:banking AND role:analyst AND clearance:medium"
    │
    ▼ 공유 저장소에 게시
    │
    ├── 기관 B (정책 만족 ✓) → 복호화 성공 → 패턴 활용
    └── 기관 C (정책 불만족 ✗) → 복호화 실패
```

#### 공유 데이터 유형

| 데이터 | 접근 정책 | 민감도 |
|--------|-----------|--------|
| 블랙리스트 (계정 해시) | `institution:partner AND clearance:medium` | 중 |
| 사기 패턴 통계 (집계) | `role:analyst AND institution:*` | 낮음 |
| 이상 행동 시그니처 | `institution:partner AND clearance:high` | 높음 |
| 모델 성능 메트릭 | `role:admin OR role:auditor` | 낮음 |

#### 구현 위치

- **`4_1_capstone`**: `scripts/fds/federated_sim.py` (신규) — FL 시뮬레이션
- **`4_1_capstone`**: `scripts/fds/fl_contribution_eval.py` (신규) — 기여도 평가
- **`fraud-service`**: `app/api/routes_intelligence.py` (신규) — 패턴 공유 API

---

## 4. 구현 로드맵

```
Phase 1 — 기반 (우선 구현)
├── Layer 4: Blockchain 감사 추적
│   - AuditBlock + 해시 체인 + 기존 audit_logger 연동
│   - /v1/audit/* API
└── Layer 2: ABE 접근 제어 (경량 버전)
    - 속성 스키마 + YAML 정책 엔진
    - 미들웨어 교체 (API Key → 속성 토큰)

Phase 2 — 확장
├── Layer 1: 행동 시그널 수집
│   - request body에 signals 필드 추가
│   - 기존 ML 피처에 통합
└── Layer 5: FL 시뮬레이션
    - 데이터 파티셔닝 + FedAvg + 성능 비교
    - DP 노이즈 적용

Phase 3 — 고도화 (선택)
├── Layer 2: CP-ABE 암호화 응답 (charm-crypto 연동)
├── Layer 5: ABE 암호화 패턴 공유 API
└── Layer 5: Shapley Value 기여도 평가
```

---

## 5. 프로젝트별 구현 위치 요약

| Layer | `4_1_capstone` | `fraud-service` |
|-------|---------------|-----------------|
| **L1** 행동 시그널 | `schemas/fds/behavioral_signals_v1.yaml` | `routes_fraud.py`, `features.py` |
| **L2** ABE 접근 제어 | `policies/fds/abe_access_policy_v1.yaml` | `middleware/abe_auth.py`, `services/abe_engine.py` |
| **L3** ML 엔진 | 기존 `scripts/fds/` (재활용) | 기존 `scoring/` (재활용) |
| **L4** Blockchain 감사 | — | `services/blockchain_audit.py`, `api/routes_audit.py` |
| **L5** FL + 공유 | `scripts/fds/federated_sim.py`, `fl_contribution_eval.py` | `api/routes_intelligence.py` |

---

## 6. 예상 효과

1. **학술적 기여**: 교수님 ABE/FL/Blockchain 연구를 실제 웹 금융 서비스에 적용한 구현 사례
2. **기술적 차별화**: 단순 ML FDS를 넘어 **암호학적 보안 계층 + 프라이버시 보존 협력 학습**
3. **현실적 가치**: 개인정보보호법·전자금융감독규정 준수에 직결
4. **확장성**: 웹 → 모바일 앱으로의 자연스러운 확장 (SDK 방식으로 Layer 1 재사용)

---

## 7. 참고 자료

### ABE / Fine-grained Access Control
- [Attribute-Based Encryption for Fine-Grained Access Control (Goyal et al.)](https://eprint.iacr.org/2006/309.pdf)
- [Registered ABE with Blockchain (Frontiers of CS, 2025)](https://link.springer.com/article/10.1007/s11704-025-50707-3)
- [Secure IoT Access Control with Dynamic Attributes (Nature, 2024)](https://www.nature.com/articles/s41598-024-80307-3)
- [ABE with Payable Outsourced Decryption (arXiv, 2024)](https://arxiv.org/html/2411.03844v1)

### Privacy-Preserving Federated Learning
- [Federated Learning for Privacy-Preserving Financial Fraud Detection (SSRN, 2025)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5399668)
- [AI-Driven Adaptive FL for Credit Card Fraud Detection (Wiley, 2025)](https://onlinelibrary.wiley.com/doi/10.1155/acis/7116768)
- [FedFraud: Scalable and Trustworthy Financial Fraud Detection (Wiley, 2025)](https://onlinelibrary.wiley.com/doi/full/10.1002/spy2.70099)
- [Fed-RD: Privacy-Preserving FL for Financial Crime Detection (arXiv)](https://arxiv.org/html/2408.01609v1)
- [Explainable FL for Transparent Banking (MDPI, 2025)](https://www.mdpi.com/1911-8074/18/4/179)

### Blockchain Audit Trail
- [Immutable Audit Trails Using Blockchain for AI-Driven Fraud Investigations](https://www.researchgate.net/publication/399466376_IMMUTABLE_AUDIT_TRAILS_USING_BLOCKCHAIN_FOR_AI-_DRIVEN_FINANCIAL_FRAUD_INVESTIGATIONS)
- [Blockchain-Based Audit Trails: Improving Transparency (IJACSA, 2025)](https://thesai.org/Downloads/Volume17No1/Paper_62-Blockchain_Based_Audit_Trails.pdf)
