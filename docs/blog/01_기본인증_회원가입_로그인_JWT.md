# #1 기본 인증 — 회원가입 / 로그인 / JWT

## ① 개요

PayWise의 인증 시스템은 이메일+비밀번호 기반 기본 인증 위에 **TOTP 2FA와 FIDO2를 선택적으로 레이어링**하는 구조다. 단순 로그인 API처럼 보이지만, 2FA 활성화 여부에 따라 응답 스킴이 달라지고 JWT 토큰 타입도 `access` / `refresh` / `pre_auth` / `stepup` 4종으로 분리되어 있다. 이후 Step-up 인증(#3), FIDO2(#2)와 공유하는 기반 레이어이기도 하다.

---

## ② 시스템 구성

```
클라이언트
    │  Bearer Token (Authorization header)
    ▼
FastAPI Router  (/v1/auth/*)          ← routes_auth.py
    │  Depends(get_current_user)
    ▼
auth/deps.py  ─────────────────────── 토큰 파싱 · DB 사용자 조회
    │
    ├── auth/jwt.py ────────────────── bcrypt 해싱 · JWT 생성·검증
    │        │ jose(python-jose)
    │        └── settings.JWT_SECRET_KEY / ALGORITHM / EXPIRE
    │
    └── DB (User 테이블)
              ├── hashed_password (bcrypt, nullable — FIDO only 계정 대비)
              ├── totp_secret / totp_enabled
              └── last_login_at / is_active
```

외부 의존: `python-jose` (JWT), `bcrypt`, `pyotp`, `qrcode`

---

## ③ 동작 흐름

### 회원가입 (`POST /v1/auth/register`)

1. 이메일 중복 SELECT → 409 반환
2. `uuid4`로 `u_<12hex>` 형태의 `user_id` 생성
3. `bcrypt.hashpw` 로 비밀번호 해싱 후 User 저장
4. **데모 데이터 시딩** (`routes_seed.seed_user_data`) — 가입 직후 대시보드가 빈 화면이 되지 않도록
5. **ML 모델 재학습** (`ml.trainer.train_all`) — 새 사용자 데이터 반영
6. access + refresh 토큰 즉시 발급 → `TokenResponse` 반환

### 로그인 (`POST /v1/auth/login`)

1. 이메일로 User 조회
2. `bcrypt.checkpw` 비밀번호 검증 → 실패 시 보안 이벤트 기록 + 401
3. FIDO2 크레덴셜 존재 여부 별도 SELECT
4. TOTP 활성화 **또는** FIDO2 등록 → **`pre_auth` 토큰(5분)** 발급 후 중간 응답 반환 (2단계 대기)
5. 2FA 없음 → access + refresh 토큰 즉시 발급

### TOTP 2단계 (`POST /v1/auth/login/totp`)

1. `pre_auth` 토큰 디코딩 → `type == "pre_auth"` 검증
2. `pyotp.TOTP.verify(code, valid_window=1)` — ±30초 허용
3. 성공 시 최종 access + refresh 토큰 발급

### 토큰 갱신 (`POST /v1/auth/refresh`)

1. `refresh` 타입 토큰 검증 → `type == "refresh"` 명시적 체크
2. 사용자 활성 상태 확인
3. 새 access + refresh 쌍 재발급

---

## ④ 핵심 코드 분석

### 1. 비밀번호 해싱

```python
# [jwt.py](backend/app/auth/jwt.py:15)
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False
```

`bcrypt.gensalt()`는 기본 cost factor 12를 사용한다. `verify_password`가 `try/except`로 감싸진 이유는 `hashed_password`가 `nullable=True`(FIDO only 계정)인 경우 `None.encode()` 같은 예외를 조용히 처리하기 위해서다.

---

### 2. JWT 토큰 타입 분리

```python
# [jwt.py](backend/app/auth/jwt.py:30)
def create_access_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def create_pre_auth_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=5)
    payload = {"sub": user_id, "exp": expire, "type": "pre_auth"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
```

현재 설정값: `ACCESS=60분`, `REFRESH=30일`, `pre_auth=5분`. 네 종류의 토큰(`access`, `refresh`, `pre_auth`, `stepup`)이 **동일한 시크릿 키와 알고리즘(HS256)** 을 공유하지만, `type` 클레임으로 용도를 구분한다.

---

### 3. 토큰 타입 명시적 검증

```python
# [deps.py](backend/app/auth/deps.py:24)
payload = decode_token(credentials.credentials)
if payload.get("type") != "access":
    raise ValueError("invalid token type")
```

```python
# [routes_auth.py](backend/app/api/routes_auth.py:215)
payload = decode_token(body.refresh_token)
if payload.get("type") != "refresh":
    raise ValueError("invalid token type")
```

refresh 토큰을 Authorization 헤더에 넣어 API를 호출하거나, access 토큰으로 refresh 엔드포인트를 때리는 시도를 막는다. `decode_token`이 서명 검증까지 통과해도 `type` 불일치면 차단.

---

### 4. 2FA 분기 — `pre_auth` 토큰 발급

```python
# [routes_auth.py](backend/app/api/routes_auth.py:141)
if user.totp_enabled or has_fido:
    pre_auth_token = create_pre_auth_token(user.user_id)
    return LoginResponse(
        totp_required=user.totp_enabled,
        fido_available=has_fido,
        pre_auth_token=pre_auth_token,
        user_id=user.user_id,
        nickname=user.nickname,
    )
```

TOTP와 FIDO2가 동시에 활성화된 경우 클라이언트가 어느 방식으로 2단계를 진행할지 선택할 수 있도록 `totp_required` + `fido_available` 플래그를 함께 반환한다.

---

### 5. TOTP 검증 — `valid_window=1`

```python
# [routes_auth.py](backend/app/api/routes_auth.py:190)
totp = pyotp.TOTP(user.totp_secret)
if not totp.verify(body.code, valid_window=1):
    await _log_security_event(session, user.user_id, "totp_fail", False)
    raise HTTPException(status_code=401, detail="OTP 코드가 올바르지 않습니다.")
```

`valid_window=1`은 TOTP 윈도우(30초) 기준 ±1 = **±30초 허용**이다. 클라이언트 시계가 서버보다 최대 30초 늦거나 빠른 경우를 커버하며, 그 이상이면 실패한다.

---

### 6. 보안 이벤트 기록

```python
# [routes_auth.py](backend/app/api/routes_auth.py:41)
async def _log_security_event(session, user_id, method, verified, risk_score=0.0):
    event = StepUpSession(
        ...
        expires_at=datetime.now(UTC) + timedelta(seconds=1),  # 이미 만료된 이벤트 기록용
    )
```

`StepUpSession` 테이블을 **이벤트 로그 테이블로 겸용**한다. `expires_at`을 1초 후로 설정해 "이미 만료된 세션"처럼 삽입하는 방식으로, 세션 관리 테이블의 스키마를 재사용하면서 별도 감사 로그 테이블 없이 처리하는 트레이드오프다.

---

### 7. 회원가입 후 데모 시딩 + ML 학습

```python
# [routes_auth.py](backend/app/api/routes_auth.py:94)
try:
    from app.api.routes_seed import seed_user_data
    await seed_user_data(user_id, session, months=3, tx_per_month=40)
except Exception as e:
    logging.getLogger(__name__).warning("Auto-seed after register failed: %s", e)

try:
    from app.ml.trainer import train_all
    await train_all(session)
except Exception as e:
    logging.getLogger(__name__).warning("Auto-train after register failed: %s", e)
```

`try/except`로 감싸 시딩이나 학습이 실패해도 회원가입 자체는 성공으로 처리한다. 단, `await`이므로 동기적으로 실행 — ML 학습이 느린 경우 회원가입 응답이 수 초 지연될 수 있다.

---

## ⑤ 설계 포인트

- **`hashed_password nullable=True`**: FIDO2 전용 계정(비밀번호 없는 계정)을 처음부터 설계에 포함. `verify_password`의 `try/except`도 이 케이스를 위한 안전망이다.
- **토큰 타입 명시적 검증**: 서명 검증(jose)과 별개로 `type` 클레임을 직접 체크해 토큰 혼용 공격을 막는다. 같은 시크릿을 공유하므로 이 검증이 없으면 refresh 토큰을 Bearer로 사용하는 우회가 가능.
- **`StepUpSession` 겸용 로그**: 보안 이벤트 기록용 별도 테이블 없이 기존 테이블을 재활용. 코드는 단순해지지만, 감사 로그와 세션 데이터가 섞여 정합성 쿼리가 복잡해질 수 있다.
- **ML 학습을 register 요청 내에서 `await`**: 회원가입 응답 지연의 원인이 될 수 있다. BackgroundTasks나 Celery 큐로 분리하는 것이 자연스러운 개선 방향이지만, 현재는 데모 목적으로 단순화한 것으로 보인다.
- **TOTP `valid_window=1` (±30초)**: 적당한 값이지만, 네트워크 지연이 심한 환경에서 `valid_window=2`(±60초)로 늘릴 여지가 있다. 보안과 UX의 트레이드오프.

---

### 예상 질문 & 답변 (발표 Q&A 대비)

**Q1. 왜 JWT 토큰을 4종(`access`/`refresh`/`pre_auth`/`stepup`)으로 분리했나요?**
> 각각 용도와 만료시간이 달라 단일 토큰으로 처리하면 권한 오용 위험이 큽니다. 예: `pre_auth`는 2FA 검증 전 임시 토큰(5분 만료, 본 API 호출 불가), `stepup`은 위험 거래 직후 단발성 검증용. 토큰 타입 명시 검증으로 혼용 차단.

**Q2. bcrypt 라운드는 몇으로 설정했나요?**
> bcrypt 기본값(12 라운드, ~250ms). 더 높이면 보안 강화지만 로그인 응답 지연. 향후 Argon2id 마이그레이션 검토 예정.

**Q3. JWT secret이 유출되면?**
> 모든 토큰 무효화 + 로테이션 필요. 현재는 `JWT_SECRET_KEY` 환경변수 단일 키 — 키 로테이션 메커니즘(`kid` 헤더 기반 다중 키)은 후속 작업. (✅ ROADMAP W1-#3 — `JWT_ALGORITHM=RS256` + `JWT_RSA_PUBLIC_KEYS_JSON` `{kid: PEM}` 다중 검증 키 + production 시 시크릿 fail-fast (W1-#4))

**Q4. 회원가입 시 ML 학습을 같이 돌리는데 응답 지연이 안 생기나요?**
> ⑤절에서 지적한 약점입니다. 현재 `await`로 동기 호출되어 응답 지연 가능. BackgroundTasks 또는 Celery 큐로 분리하는 게 후속 작업.

**Q5. TOTP `valid_window=1`이 좁지 않나요?**
> ±30초 윈도우. 일반적 환경에서 충분하지만 네트워크 지연이 큰 경우 ±60초로 확장 여지. 보안과 UX 트레이드오프.

---

## ⑥ 한 줄 정리

이메일+bcrypt 기반 로그인에 TOTP/FIDO2 2FA를 **`pre_auth` 중간 토큰**으로 연결하고, 4종 JWT 타입 명시 검증으로 토큰 혼용을 차단한 계층형 인증 설계다.
