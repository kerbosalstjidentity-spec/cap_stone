# #3 Step-up 인증 — 위험 거래 감지 시 자동으로 2FA를 끼워넣는 방법

---

## ① 개요

PayWise는 모든 API 요청에 JWT 하나로 접근을 허용하는 대신, fraud-service가 산출한 **리스크 스코어**가 임계값을 넘는 순간 추가 인증(TOTP 또는 FIDO2)을 강제하는 **Step-up 인증** 레이어를 별도로 둔다. 평상시 사용성은 그대로 유지하되, 이상 징후가 감지된 세션에만 마찰을 추가하는 **Risk-Based Authentication(RBA)** 패턴을 직접 구현한 결과다.

---

## ② 시스템 구성

```
┌──────────────────────────────────────────────────────┐
│                   Frontend (React)                    │
└────────────────────────┬─────────────────────────────┘
                         │ Bearer access_token
                         ▼
┌──────────────────────────────────────────────────────┐
│            backend  (FastAPI, port 8020)              │
│                                                      │
│  routes_stepup.py                                    │
│  ├─ POST /v1/auth/stepup/challenge  ─────────────┐   │
│  ├─ POST /v1/auth/stepup/verify                  │   │
│  └─ GET  /v1/auth/stepup/history                 │   │
│                                                  │   │
│  fraud_client.py  ◄──────────────────────────────┘   │
│  └─ fetch_fraud_profile(user_id)                     │
│                          │ HTTP GET (timeout 5 s)     │
│                          ▼                           │
│  ┌──────────────────────────────────┐                │
│  │  fraud-service (port 8010)       │                │
│  │  GET /v1/profile/{user_id}       │                │
│  └──────────────────────────────────┘                │
│                                                      │
│  auth/jwt.py                                         │
│  └─ create_stepup_token()  →  stepup JWT (10 min)    │
│                                                      │
│  models/tables.py                                    │
│  ├─ StepUpSession  (stepup_sessions)                 │
│  ├─ FidoCredential (fido_credentials)                │
│  └─ User.totp_enabled / totp_secret                  │
└──────────────────────────────────────────────────────┘
```

| 컴포넌트 | 역할 |
|---|---|
| `routes_stepup.py` | Step-up 챌린지 발행 · 검증 · 이력 조회 |
| `fraud_client.py` | fraud-service REST 프록시 (5 s 타임아웃) |
| `StepUpSession` 테이블 | 챌린지 토큰 발급 기록 + 재사용 방지 플래그 |
| `auth/jwt.py` | 단기 stepup JWT 생성·검증 |

---

## ③ 동작 흐름

### Challenge 발행 (`POST /challenge`)

1. **리스크 조회** — `_get_risk_score(user_id)` 가 `fraud_client.fetch_fraud_profile()` 를 호출해 `risk_score` 필드를 꺼낸다. fraud-service가 무응답이면 `0.0` 으로 안전하게 fallback.
2. **임계값 비교** — `risk_score < STEPUP_RISK_THRESHOLD(0.6)` 이면 `required: false` 를 즉시 반환하고 종료.
3. **2FA 수단 결정** — `_determine_method(user)` 로 `totp_enabled` 플래그를 확인하고, TOTP가 없으면 DB에서 `FidoCredential` 존재 여부를 확인해 `fido` 로 결정한다.
4. **stepup JWT 발급** — `create_stepup_token(user_id, method, ttl=10)` 으로 페이로드에 `type: "stepup"`, `method` 를 포함한 단기 토큰 생성.
5. **세션 저장** — `StepUpSession` 레코드를 INSERT해 토큰과 `risk_score`, 만료 시각을 영속화한다.
6. **챌린지 응답** — `{ required: true, method, stepup_token, risk_score }` 반환.

### 검증 (`POST /verify`)

7. **토큰 검증 3단계** — JWT 서명·만료 확인 → `type == "stepup"` 확인 → `sub == current_user.user_id` 확인.
8. **DB 세션 조회** — `session_token` + `user_id` 로 `StepUpSession` 조회. 없거나(`404`), 이미 사용됐거나(`verified=True`), 만료됐으면 즉시 거부.
9. **방법별 검증** — TOTP면 `pyotp.TOTP.verify(code, valid_window=1)`, FIDO면 `/fido/authenticate/verify` 엔드포인트에서 이미 검증된 `stepup_token` 을 수락.
10. **완료 처리** — `stepup_session.verified = True` 로 재사용을 차단하고, 신규 `access_token` 발급.

---

## ④ 핵심 코드 분석

### 리스크 스코어 조회 — graceful fallback

```python
# backend/app/api/routes_stepup.py:26-35
async def _get_risk_score(user_id: str) -> float:
    try:
        profile = await fetch_fraud_profile(user_id)
        if not profile:
            return 0.0
        return float(profile.get("risk_score", profile.get("anomaly_score", 0.0)))
    except Exception:
        return 0.0
```

[routes_stepup.py:26](backend/app/api/routes_stepup.py:26) — fraud-service가 `risk_score` 를 내려주지 않으면 `anomaly_score` 를 백업으로 쓰고, 그것도 없으면 0.0을 반환한다. 외부 서비스 장애가 사용자 로그인을 막지 않도록 의도된 방어 코드다.

### fraud-service REST 클라이언트

```python
# backend/app/services/fraud_client.py:12-27
async def fetch_fraud_profile(user_id: str) -> dict | None:
    url = f"{settings.FRAUD_SERVICE_URL}/v1/profile/{user_id}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
    except (httpx.ConnectError, httpx.TimeoutException):
        pass
    return None
```

[fraud_client.py:21](backend/app/services/fraud_client.py:21) — 5초 타임아웃을 걸고, `ConnectError` / `TimeoutException` 만 명시적으로 잡는다. 예상치 못한 예외는 상위 `_get_risk_score` 의 `except Exception` 이 처리한다. 계층 분리가 깔끔하다.

### 챌린지 발행 — TOTP 우선, FIDO 보조

```python
# backend/app/api/routes_stepup.py:64-113
risk_score = await _get_risk_score(current_user.user_id)

if risk_score < settings.STEPUP_RISK_THRESHOLD:          # ← 0.6 미만이면 통과
    return StepUpChallengeResponse(required=False, ...)

method = _determine_method(current_user)                 # totp_enabled 먼저 확인
if method == "none":                                     # TOTP 없으면 DB로 FIDO 확인
    result = await session.execute(
        select(FidoCredential)
        .where(FidoCredential.user_id == current_user.user_id)
        .limit(1)
    )
    if result.scalar_one_or_none():
        method = "fido"

token = create_stepup_token(current_user.user_id, method, ttl_minutes=10)

stepup = StepUpSession(
    user_id=current_user.user_id,
    session_token=token,
    method=method,
    risk_score=risk_score,
    expires_at=datetime.now(UTC) + timedelta(minutes=10),
)
session.add(stepup)
await session.commit()
```

[routes_stepup.py:80](backend/app/api/routes_stepup.py:80) — FIDO 확인에 `.limit(1)` 을 달아 전체 인덱스 스캔을 피한다. 등록된 장치가 하나라도 있으면 방법을 `fido` 로 확정한다.

### stepup JWT 구조

```python
# backend/app/auth/jwt.py:47-51
def create_stepup_token(user_id: str, method: str, ttl_minutes: int = 10) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    payload = {"sub": user_id, "exp": expire, "type": "stepup", "method": method}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
```

[jwt.py:47](backend/app/auth/jwt.py:47) — 일반 `access` 토큰과 달리 `type: "stepup"` 과 `method` 를 포함한다. 검증 단계에서 `type` 필드를 반드시 확인하기 때문에 access 토큰을 stepup 슬롯에 주입하는 공격을 막는다.

### StepUpSession 테이블

```python
# backend/app/models/tables.py:252-262
class StepUpSession(Base):
    __tablename__ = "stepup_sessions"

    id           = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id      = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"))
    session_token= mapped_column(String(128), unique=True, nullable=False, index=True)
    method       = mapped_column(String(16))        # fido / totp / login / login_fail …
    verified     = mapped_column(Boolean, default=False)
    risk_score   = mapped_column(Float, default=0.0)
    expires_at   = mapped_column(DateTime(timezone=True))
    created_at   = mapped_column(DateTime(timezone=True), server_default=func.now())
```

[tables.py:257](backend/app/models/tables.py:257) — `session_token` 에 `unique=True` + 인덱스가 함께 걸려 있다. 같은 토큰을 두 번 INSERT하면 DB 레벨에서 막히고, 조회는 인덱스 덕에 O(log n)다.

### TOTP 검증 — valid_window

```python
# backend/app/api/routes_stepup.py:162-164
totp = pyotp.TOTP(current_user.totp_secret)
if not totp.verify(body.code, valid_window=1):
    return StepUpVerifyResponse(verified=False, message="OTP 코드가 올바르지 않습니다.")
```

[routes_stepup.py:163](backend/app/api/routes_stepup.py:163) — `valid_window=1` 은 현재 타임스탬프 ±1, 즉 최대 90초(30초 × 3 윈도우)를 허용한다. 네트워크 지연과 사용자 시계 오차를 커버하기 위한 관행적 설정이다.

### 재사용 방지 3단계

```python
# backend/app/api/routes_stepup.py:149-154
if not stepup_session:
    raise HTTPException(400, "step-up 세션을 찾을 수 없습니다.")
if stepup_session.verified:
    raise HTTPException(400, "이미 사용된 step-up 토큰입니다.")
if stepup_session.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
    raise HTTPException(400, "step-up 토큰이 만료되었습니다.")
```

[routes_stepup.py:149](backend/app/api/routes_stepup.py:149) — JWT 서명 자체는 stateless로 만료를 체크하지만, DB의 `verified` 플래그와 `expires_at` 이중 검증으로 JWT 탈취 후 재사용(replay attack) 시나리오를 막는다.

### 보안 이력 — StepUpSession 이중 용도

```python
# backend/app/api/routes_stepup.py:207-214
_method_label = {
    "login":      "비밀번호 로그인",
    "login_fail": "로그인 실패",
    "login_totp": "TOTP 로그인",
    "totp_fail":  "TOTP 실패",
    "totp":       "TOTP Step-up",
    "fido":       "FIDO2 Step-up",
}
```

[routes_stepup.py:207](backend/app/api/routes_stepup.py:207) — `StepUpSession` 은 step-up 챌린지 뿐만 아니라 일반 로그인 성공·실패도 같은 테이블에 기록한다. `/history` 하나로 전체 보안 이벤트를 조회할 수 있다.

---

## ⑤ 설계 포인트 / 트러블슈팅 거리

- **외부 서비스 장애가 사용자 흐름을 막지 않는다.** `_get_risk_score` 가 항상 `0.0` 을 반환하는 fallback을 두기 때문에 fraud-service가 다운돼도 로그인 자체는 막히지 않는다. 반대로 말하면, fraud-service 장애 시 고위험 세션도 step-up 없이 통과한다 — 가용성과 보안 간 의도적인 트레이드오프다.

- **FIDO step-up은 검증을 위임한다.** `/verify` 는 FIDO assertion을 직접 검증하지 않고 `/fido/authenticate/verify` 에서 발급된 `stepup_token` (method=fido) 을 수락한다. 책임 분리는 좋지만, 클라이언트가 두 엔드포인트를 올바른 순서로 호출해야 한다는 암묵적 의존이 생긴다.

- **StepUpSession의 이중 용도.** 챌린지 레코드와 감사 로그(로그인 이벤트)가 동일 테이블을 공유한다. `expires_at = now() + 1s` 트릭으로 이벤트 레코드를 이미 만료된 상태로 저장하는데, 쿼리할 때 만료 기준으로 필터하면 이벤트 레코드가 누락될 수 있다.

- **임계값 0.6이 하드코딩에 가깝다.** `settings.STEPUP_RISK_THRESHOLD` 로 환경변수화는 됐지만, 값 결정 근거(FPR/TPR 트레이드오프)가 코드에 남아 있지 않다. 임계값 조정 시 기준이 모호해진다.

- **Rate limiting 부재.** `/verify` 에 TOTP 코드를 반복 시도해도 막는 장치가 없다. 6자리 TOTP 공간(10⁶)은 작지 않지만, 30초 윈도우 × valid_window=3 구간 동안 브루트포스를 시도하면 이론적으로 위협이 된다.

---

### 예상 질문 & 답변 (발표 Q&A 대비)

**Q1. 왜 모든 거래에 2FA를 거치지 않고 위험 거래에만 거나요?**
> 모든 거래에 2FA를 강제하면 사용자 경험이 무너집니다. RBA(Risk-Based Authentication)는 평상시 마찰을 0으로 두고, fraud-service 점수가 임계값을 넘는 순간만 마찰 추가. 보안과 UX의 균형.

**Q2. 임계값(0.6)은 어떻게 정했나요?**
> 도메인 휴리스틱. ML 점수 분포에서 SOFT_REVIEW(0.005)과 REVIEW(0.35) 사이의 운영 보수 지점. ROC 분석 기반 자동 튜닝은 운영 데이터 누적 후 후속 작업.

**Q3. fraud-service가 다운되면 step-up 인증은 어떻게?**
> `fraud_client.fetch_fraud_profile()`이 5초 타임아웃 후 fail-open(평상 인증 흐름) 또는 fail-close(전부 step-up 강제) 정책 선택 가능. 현재는 fail-open으로 가용성 우선.

**Q4. step-up JWT의 만료가 짧은 이유?**
> 단기(5분) 단발성 토큰으로 재사용 차단. DB `verified` 플래그까지 같이 두는 이중 잠금 — 토큰을 탈취해도 DB 상태가 갱신되어 재사용 불가.

**Q5. `/verify`에 TOTP 브루트포스가 가능하지 않나요?**
> ⑤절 지적대로 현재 rate limiting이 없어 이론적 위협 존재. 6자리 TOTP × 30초 윈도우 × valid_window=3 구간이라 실효 공간이 좁지만, IP 기반 rate limiter 추가가 후속 작업.

---

## ⑥ 한 줄 정리

fraud-service 리스크 점수가 0.6을 넘는 순간 단기 stepup JWT를 발급하고, DB `verified` 플래그로 재사용을 차단한 뒤 TOTP 또는 FIDO2 검증을 통과해야만 새 access_token을 내려주는 **이중 잠금 RBA 구조**다.
