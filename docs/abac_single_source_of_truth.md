# ABAC 단일 진실 출처 (W8-#1)

## Why

`backend/app/services/abac_simulation.py` (시뮬레이터, 5개 룰) 와
`fraud-service/app/services/abac_engine.py` (운영 게이트, 8개 룰) 가
**서로 다른 룰셋**으로 진화해 왔다. 같은 사용자에 대해 두 서비스의 판단이
어긋날 위험이 컸다.

## What

- 정책 정본: `policies/abac_unified.json` (저장소 루트)
- 운영 정본 코드: `fraud-service/app/services/abac_engine.py`
- 시뮬레이션 코드: `backend/app/services/abac_simulation.py` (W9-#13 으로
  research 디렉터리에서 분리됨)
- 핫 리로드: 양쪽 모두 `policy_loader.PolicyFile`(W8-#3) 로 로드 가능

## 정합성 체크 (CI)

- `fraud-service/tests/test_abac_unified_policy.py` — JSON 스키마/룰 키 검증
- `backend/tests/test_abac_simulation_rules.py` (기존) — 시뮬레이터 5개 룰
  키가 통합 정책 부분집합인지 확인

## 룰 매핑

| 룰 | backend(5) | fraud(8) |
|---|---|---|
| time_window | ✅ | ✅ |
| location_country | ✅ | ✅ |
| device_type | ✅ | ✅ |
| mfa_required | ✅ | ✅ |
| clearance_match | ✅ | ✅ |
| threat_level | ❌ | ✅ |
| department_isolation | ❌ | ✅ |
| data_masking | ❌ | ✅ |

추가 3개는 운영 환경 전용 — 백엔드 시뮬레이터는 발표 시각화 목적이라 의도적
누락. 둘의 차이를 본 문서가 명시함으로써 **silent divergence** 위험 제거.

## 변경 절차

1. `policies/abac_unified.json` 수정
2. CI 통과 후 운영 환경에 파일 배포
3. admin API (`reload_all` — W8-#3) 로 fraud-service 핫 리로드
4. backend 는 다음 cron 또는 재시작 시 자동 반영

## 변경 이력

- 2026-05-10 W8-#1 — 초안 작성 + 통합 정책 JSON 추출
