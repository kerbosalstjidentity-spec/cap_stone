# 사기 탐지용 데이터 스키마 참고 (이상적·공개 데이터 혼합 시)

앞서 논의한 **도메인·특성·라벨 품질**을 한 번에 보려고 만든 **참고 스키마**입니다.  
실제 공개 데이터는 개인정보·보안 때문에 **아래 컬럼 전부를 갖추지 못하는 경우가 대부분**이며, Kaggle `creditcard`는 V1–V28·Amount·Time·Class 수준으로 축소된 예에 가깝습니다.

---

## 1. 식별·도메인 (메타)

| 논리 이름 | 타입 (예시) | 설명 | 비고 |
|-----------|-------------|------|------|
| `transaction_id` | string (UUID) | 거래 고유 ID | 중복 없음 |
| `event_ts` | datetime (UTC) | 거래 시각 | 시간 순 검증·시계열 특성에 사용 |
| `user_id` | string (해시) | 사용자/카드 단위 ID | 없으면 시퀀스·집계 특성 제한 |
| `channel` | categorical | 온라인 / 오프라인 / ATM / 기타 | 도메인 분리 |
| `country_txn` | string (ISO 국가코드) | 거래 발생 국가 | 해외 사기 등 |
| `currency` | string | 통화 코드 | 환산 시 금액 정규화 |

---

## 2. 거래 금액·상품 맥락

| 논리 이름 | 타입 (예시) | 설명 | 비고 |
|-----------|-------------|------|------|
| `amount` | float | 거래 금액 (현지 통화) | 로그·구간화에 사용 |
| `amount_orig` | float | 원화 등 기준 통화 금액 | 선택 |
| `installment` | int | 할부 개월 (0=일시불) | 선택 |

---

## 3. 가맹점·업종 (도메인 특성)

| 논리 이름 | 타입 (예시) | 설명 | 비고 |
|-----------|-------------|------|------|
| `merchant_id` | string (해시) | 가맹점 ID | 집계·빈도 특성 |
| `mcc` | string / int | 업종 코드 (MCC) | 업종별 리스크 |
| `merchant_country` | string | 가맹점 국가 | 선택 |

---

## 4. 디바이스·접속 (계정·카드 탈취 등)

| 논리 이름 | 타입 (예시) | 설명 | 비고 |
|-----------|-------------|------|------|
| `device_id` | string (해시) | 단말/앱 인스턴스 | 없으면 생략 |
| `ip_country` | string | IP 기준 국가 | VPN·해외 접속 등 |
| `app_vs_web` | categorical | 앱 / 웹 | 선택 |

---

## 5. 행동·집계 (과거 윈도우에서 파생 가능)

원시 컬럼으로 있거나, `event_ts`·`user_id`가 있으면 **파생**해서 만들 수 있습니다.

| 논리 이름 | 타입 (예시) | 설명 | 비고 |
|-----------|-------------|------|------|
| `cnt_txn_1h` | int | 최근 1시간 거래 건수 | 사용자 기준 |
| `sum_amt_24h` | float | 최근 24시간 합계 금액 | 선택 |
| `cnt_distinct_merchant_7d` | int | 최근 7일 서로 다른 가맹점 수 | 선택 |

---

## 6. 라벨·품질 메타

| 논리 이름 | 타입 (예시) | 설명 | 비고 |
|-----------|-------------|------|------|
| `is_fraud` | int {0,1} | 사기 여부 (지도 학습 타깃) | 정의 문서와 일치해야 함 |
| `label_ts` | datetime | 라벨 확정 시각 | 지연 라벨 분석 |
| `label_source` | categorical | 규칙 / 수동 / 분쟁 결과 등 | 편향·한계 서술에 유용 |
| `label_version` | string | 라벨 규칙 버전 | 재현성 |

---

## 7. 비교: 현재 프로젝트 `data/creditcard.csv` (Kaggle)

| 컬럼 | 의미 |
|------|------|
| `Time` | 첫 거래로부터 경과 시간(초) |
| `Amount` | 금액 |
| `V1`–`V28` | PCA 등으로 변환·익명화된 특성 (해석 어려움) |
| `Class` | 0 정상, 1 사기 |

즉 **§1–§6의 풍부한 도메인 컬럼은 없고**, 대신 **익명화된 수치 특성 + 금액·시간 + 라벨** 구조입니다.

---

## 8. 기계가 읽는 스키마 예시 (JSON Schema 스타일 요약)

아래는 **문서용 요약**이며, 검증 도구에 바로 넣는 완전한 JSON Schema는 아닙니다.

```json
{
  "description": "이상적 참고 스키마 — 실제 데이터셋은 부분 집합만 포함",
  "required_core": ["transaction_id", "event_ts", "amount", "is_fraud"],
  "optional_rich": [
    "user_id", "channel", "merchant_id", "mcc",
    "device_id", "country_txn", "label_source"
  ],
  "types": {
    "transaction_id": "string",
    "event_ts": "datetime",
    "amount": "number",
    "is_fraud": "integer_enum_0_1"
  }
}
```

---

## 9. 이 파일의 용도

- 새 공개 데이터를 고를 때 **체크리스트**로 쓰거나,
- 보고서에 **“이상적 특성 vs 본 연구 데이터”**를 표로 비교할 때 참고합니다.
