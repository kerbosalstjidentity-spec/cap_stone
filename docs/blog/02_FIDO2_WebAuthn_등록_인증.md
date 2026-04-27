# #2 FIDO2/WebAuthn — 패스키 등록과 인증

## ① 개요

PayWise는 이메일+비밀번호 로그인(#1) 위에 **FIDO2/WebAuthn 기반 패스키 인증**을 선택적 레이어로 얹는다. 사용자는 지문·FaceID·보안키로 2단계 인증을 수행하거나, 비밀번호 입력 없이 FIDO2만으로 로그인하는 두 가지 경로를 모두 쓸 수 있다. 서버는 `py_webauthn` 라이브러리로 W3C WebAuthn 사양을 구현하고, 클라이언트는 브라우저 네이티브 `navigator.credentials` API를 직접 호출한다.

---

## ② 시스템 구성

```
클라이언트 (브라우저)
    │  navigator.credentials.create() / get()
    │  base64url ↔ ArrayBuffer 변환
    ▼
FastAPI Router  (/v1/auth/fido/*)          ← routes_fido.py
    │
    ├── 챌린지 저장소 (인메모리 dict)
    │       _registration_challenges[user_id] = challenge
    │       _authentication_challenges[user_id] = challenge
    │       _login_challenges[pre_auth_token] = (challenge, user_id)
    │
    ├── py_webauthn
    │       generate_registration_options()
    │       verify_registration_response()
    │       generate_authentication_options()
    │       verify_authentication_response()
    │
    ├── auth/jwt.py
    │       create_stepup_token()    ← 인증 성공 시 발급
    │       create_pre_auth_token()  ← 1단계 비밀번호 통과 시 발급
    │
    └── DB
            fido_credentials  (credential_id · public_key · sign_count · aaguid)
            stepup_sessions   (이벤트 로그 겸용)

외부 의존: webauthn>=2.2 (py_webauthn), python-jose
설정: WEBAUTHN_RP_ID="localhost", WEBAUTHN_RP_NAME="Consume Pattern", WEBAUTHN_ORIGIN="http://localhost:3020"
```

---

## ③ 동작 흐름

PayWise의 FIDO2 구현은 **세 개의 독립된 흐름**으로 나뉜다.

### A. 패스키 등록 (로그인된 상태에서 장치 추가)

1. 클라이언트 → `GET /v1/auth/fido/register/options` (Bearer access token 필요)
2. 서버: `generate_registration_options()` 호출 → challenge 생성, 인메모리 저장 후 옵션 반환
3. 브라우저: `navigator.credentials.create({ publicKey: ... })` — OS/하드웨어가 생체 인식 팝업 띄움
4. 클라이언트 → `POST /v1/auth/fido/register/verify` (credential_id, client_data_json, attestation_object)
5. 서버: `verify_registration_response()` — challenge·origin·rp_id 검증
6. 중복 credential_id 확인 후 `fido_credentials` 테이블에 공개키·sign_count·aaguid 저장

### B. Step-up 인증 (로그인된 상태에서 고위험 동작 인증)

1. 클라이언트 → `GET /v1/auth/fido/authenticate/options` (Bearer access token 필요)
2. 서버: 사용자의 등록된 credential 목록 조회 → `allow_credentials` 포함한 옵션 반환
3. 브라우저: `navigator.credentials.get({ publicKey: ... })` — assertion 생성
4. 클라이언트 → `POST /v1/auth/fido/authenticate/verify`
5. 서버: `verify_authentication_response()` → sign_count 클론 탐지 → **`stepup_token` 발급**

### C. FIDO2 로그인 (비밀번호 1단계 통과 후 2FA)

1. `POST /v1/auth/login` → 비밀번호 통과 → `pre_auth_token` 발급
2. 클라이언트 → `POST /v1/auth/fido/login/options` (pre_auth_token 포함)
3. 서버: pre_auth_token 디코딩 → user_id 추출 → 해당 사용자 credential 목록 조회 → 챌린지 생성
4. 브라우저: `navigator.credentials.get()` → assertion 생성
5. 클라이언트 → `POST /v1/auth/fido/login/verify`
6. 서버: 챌린지·서명 검증 → sign_count 업데이트 → **최종 access + refresh 토큰 발급**

---

## ④ 핵심 코드 분석

### 1. 등록 옵션 생성 — 챌린지 주입

```python
# [routes_fido.py](backend/app/api/routes_fido.py:97)
options = webauthn.generate_registration_options(
    rp_id=settings.WEBAUTHN_RP_ID,
    rp_name=settings.WEBAUTHN_RP_NAME,
    user_id=current_user.user_id.encode(),
    user_name=current_user.email or current_user.nickname,
    authenticator_selection=AuthenticatorSelectionCriteria(
        resident_key=ResidentKeyRequirement.PREFERRED,
        user_verification=UserVerificationRequirement.PREFERRED,
    ),
)
_registration_challenges[current_user.user_id] = options.challenge
```

`resident_key: PREFERRED`는 Passkey(discoverable credential)를 허용하되 강제하지 않는 옵션이다. `REQUIRED`로 설정하면 보안키(YubiKey 등) 중 resident key를 미지원하는 구형 기기를 거부하게 된다. PREFERRED로 타협해 두면 최신 스마트폰과 구형 보안키 모두를 수용할 수 있다.

---

### 2. 등록 검증 — 공개키 저장

```python
# [routes_fido.py](backend/app/api/routes_fido.py:147)
verification = webauthn.verify_registration_response(
    credential=RegistrationCredential(
        id=body.credential_id,
        raw_id=base64url_to_bytes(body.credential_id),
        response=AuthenticatorAttestationResponse(
            client_data_json=base64url_to_bytes(body.client_data_json),
            attestation_object=base64url_to_bytes(body.attestation_object),
        ),
        type="public-key",
    ),
    expected_challenge=stored_challenge,
    expected_rp_id=settings.WEBAUTHN_RP_ID,
    expected_origin=settings.WEBAUTHN_ORIGIN,
    require_user_verification=False,
)
```

```python
# [routes_fido.py](backend/app/api/routes_fido.py:171)
fido_cred = FidoCredential(
    user_id=current_user.user_id,
    credential_id=body.credential_id,
    public_key=base64.b64encode(verification.credential_public_key).decode(),
    sign_count=verification.sign_count,
    device_type="platform" if verification.credential_backed_up else "cross-platform",
    aaguid=str(verification.aaguid),
    name=body.device_name,
)
session.add(fido_cred)
```

`verify_registration_response()`는 내부적으로 세 가지를 검증한다: ① client_data_json 안의 challenge가 서버가 발급한 것과 일치하는가, ② origin이 설정과 일치하는가, ③ rp_id hash가 올바른가. 세 조건 중 하나라도 실패하면 `InvalidCBORData` 또는 `InvalidRegistrationResponse` 예외가 발생한다.

`credential_public_key`는 CBOR 인코딩된 바이너리 공개키다. 이를 base64로 인코딩해 TEXT 컬럼에 저장하고, 인증 시 다시 디코딩해서 서명 검증에 사용한다.

---

### 3. FidoCredential 모델 — sign_count의 역할

```python
# [tables.py](backend/app/models/tables.py:229)
class FidoCredential(TimestampMixin, Base):
    __tablename__ = "fido_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id"), nullable=False)
    credential_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)      # CBOR base64
    sign_count: Mapped[int] = mapped_column(Integer, nullable=False)   # 클론 탐지용
    device_type: Mapped[str] = mapped_column(String(32), nullable=False)
    aaguid: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

`sign_count`는 FIDO2 클론 탐지의 핵심이다. 정상적인 authenticator는 서명할 때마다 카운터를 1씩 증가시킨다. 서버는 새로운 sign_count가 저장된 값보다 반드시 크거나 같아야 한다고 기대한다. 만약 공격자가 authenticator를 복제(clone)해서 다른 기기에서 사용하면 복제본과 원본 중 하나의 sign_count가 서버에 저장된 값보다 낮아지는 순간 탐지된다.

`aaguid`는 authenticator 모델을 식별하는 UUID다. 예를 들어 Touch ID와 Windows Hello는 서로 다른 aaguid를 가진다. 이를 저장해 두면 나중에 "어떤 종류의 장치로 등록했는가"를 감사 로그로 추적할 수 있다.

---

### 4. 인증 검증 — sign_count 업데이트

```python
# [routes_fido.py](backend/app/api/routes_fido.py:251)
verification = webauthn.verify_authentication_response(
    credential=AuthenticationCredential(
        id=body.credential_id,
        raw_id=base64url_to_bytes(body.credential_id),
        response=AuthenticatorAssertionResponse(
            client_data_json=base64url_to_bytes(body.client_data_json),
            authenticator_data=base64url_to_bytes(body.authenticator_data),
            signature=base64url_to_bytes(body.signature),
        ),
        type="public-key",
    ),
    expected_challenge=stored_challenge,
    expected_rp_id=settings.WEBAUTHN_RP_ID,
    expected_origin=settings.WEBAUTHN_ORIGIN,
    credential_public_key=base64.b64decode(cred.public_key),  # 저장된 공개키 복원
    credential_current_sign_count=cred.sign_count,
)

cred.sign_count = verification.new_sign_count  # 클론 탐지 후 갱신
cred.last_used_at = datetime.now(UTC)
```

등록(Registration)과 인증(Authentication)의 결정적 차이는 `credential_public_key`의 출처다. 등록 시에는 authenticator가 공개키를 직접 전달하지만, 인증 시에는 서버가 **이미 저장해 둔 공개키**로 signature를 검증한다. 서버가 공개키를 보유하고 있으므로 비밀(private key)은 authenticator 밖으로 절대 나가지 않는다.

---

### 5. 로그인 흐름 — pre_auth_token으로 챌린지 바인딩

```python
# [routes_fido.py](backend/app/api/routes_fido.py:372)
payload = decode_token(body.pre_auth_token)
if payload.get("type") != "pre_auth":
    raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
user_id = payload["sub"]

# 해당 사용자의 FIDO2 장치 조회
fido_creds = (await session.execute(
    select(FidoCredential).where(FidoCredential.user_id == user_id)
)).scalars().all()

options = webauthn.generate_authentication_options(
    rp_id=settings.WEBAUTHN_RP_ID,
    allow_credentials=[
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
        for c in fido_creds
    ],
)
_login_challenges[body.pre_auth_token] = (options.challenge, user_id)
```

로그인용 챌린지는 `_login_challenges[pre_auth_token]`으로 저장된다. pre_auth_token 자체가 키가 되므로, 비밀번호를 통과하지 않고 FIDO2 엔드포인트만 직접 호출하는 시도는 유효한 pre_auth_token 없이는 불가능하다. 챌린지 맵에 user_id도 함께 저장해 검증 단계에서 credential 소유자를 재확인한다.

---

### 6. 로그인 검증 — 최종 토큰 발급

```python
# [routes_fido.py](backend/app/api/routes_fido.py:457)
stored = _login_challenges.pop(body.pre_auth_token, None)
stored_challenge, user_id = stored

cred = (await session.execute(
    select(FidoCredential).where(
        FidoCredential.credential_id == body.credential_id,
        FidoCredential.user_id == user_id,  # 소유자 검증
    )
)).scalar_one_or_none()

verification = webauthn.verify_authentication_response(...)
cred.sign_count = verification.new_sign_count

# 보안 이벤트 기록
stepup = StepUpSession(
    user_id=user_id, method="login_fido",
    verified=True, risk_score=0.0,
    expires_at=datetime.now(UTC) + timedelta(seconds=1),
)
session.add(stepup)

access_token = create_access_token(user_id)
refresh_token = create_refresh_token(user_id)
```

`_login_challenges.pop()`으로 챌린지를 꺼내면서 동시에 삭제한다. 같은 챌린지로 두 번 검증을 시도하는 replay attack을 인메모리 수준에서 막는 최소한의 방어다.

---

### 7. 프론트엔드 — base64url ↔ ArrayBuffer 변환

```typescript
// [login/page.tsx](frontend/src/app/auth/login/page.tsx:8)
function base64urlToBuffer(base64url: string): ArrayBuffer {
    const base64 = base64url.replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes.buffer;
}

function bufferToBase64url(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    bytes.forEach(b => binary += String.fromCharCode(b));
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}
```

WebAuthn API는 challenge, credential_id, authenticator_data 등 모든 바이너리 값을 `ArrayBuffer`로 다룬다. 반면 HTTP JSON 페이로드는 문자열이다. 두 세계를 잇는 것이 이 두 함수다. base64url은 표준 base64에서 `+`→`-`, `/`→`_`, 패딩(`=`) 제거한 URL-safe 형태다.

---

### 8. 프론트엔드 — FIDO2 로그인 호출 흐름

```typescript
// [login/page.tsx](frontend/src/app/auth/login/page.tsx:116)
async function handleFidoLogin() {
    if (!window.PublicKeyCredential) {
        setError("이 브라우저는 WebAuthn을 지원하지 않습니다.");
        return;
    }

    // 1. 챌린지 요청
    const opts = await fetch("/api/v1/auth/fido/login/options", {
        method: "POST",
        body: JSON.stringify({ pre_auth_token: preAuthToken }),
    }).then(r => r.json());

    // 2. 브라우저 네이티브 API — 생체 팝업 트리거
    const credential = await navigator.credentials.get({
        publicKey: {
            challenge: base64urlToBuffer(opts.challenge),
            rpId: opts.rp_id,
            allowCredentials: opts.allow_credentials.map(c => ({
                id: base64urlToBuffer(c.id),
                type: "public-key" as const,
            })),
            timeout: opts.timeout ?? 60000,
            userVerification: "preferred" as const,
        },
    }) as PublicKeyCredential | null;

    // 3. assertion 서버 검증
    const response = credential.response as AuthenticatorAssertionResponse;
    await fetch("/api/v1/auth/fido/login/verify", {
        method: "POST",
        body: JSON.stringify({
            pre_auth_token: preAuthToken,
            credential_id: bufferToBase64url(credential.rawId),
            client_data_json: bufferToBase64url(response.clientDataJSON),
            authenticator_data: bufferToBase64url(response.authenticatorData),
            signature: bufferToBase64url(response.signature),
        }),
    });
}
```

`navigator.credentials.get()`은 OS가 처리한다. 브라우저는 `allowCredentials`에 나열된 credential 중 현재 기기에 있는 것을 찾아 생체 인식을 요청하고, private key로 challenge에 서명해 `AuthenticatorAssertionResponse`를 돌려준다. 서버는 이 서명을 저장된 공개키로 검증한다. private key는 이 과정 어디에서도 전송되지 않는다.

---

### 9. 보안 설정 페이지 — 장치 등록 흐름

```typescript
// [security/page.tsx](frontend/src/app/security/page.tsx:148)
const credential = await navigator.credentials.create({
    publicKey: {
        challenge: base64urlToBuffer(opts.challenge),
        rp: { id: opts.rp_id, name: opts.rp_name },
        user: {
            id: new TextEncoder().encode(opts.user_id),
            name: opts.user_name,
            displayName: opts.user_name,
        },
        pubKeyCredParams: [
            { alg: -7, type: "public-key" },    // ES256 (ECDSA P-256)
            { alg: -257, type: "public-key" },  // RS256 (RSA)
        ],
        timeout: opts.timeout ?? 60000,
        authenticatorSelection: {
            userVerification: "preferred",
            residentKey: "preferred",
        },
        attestation: "none",
    },
});
```

`pubKeyCredParams`에서 alg `-7`은 ES256, `-257`은 RS256이다. COSE 알고리즘 레지스트리 번호다. 두 알고리즘을 모두 허용해 Touch ID(EC 키), YubiKey(RSA 지원 버전) 등 다양한 authenticator와 호환된다. `attestation: "none"`은 서버가 authenticator 제조사 인증서를 검증하지 않겠다는 뜻으로, 검증 복잡도를 낮추는 대신 authenticator 출처를 보증하지 못하는 트레이드오프다.

---

## ⑤ 설계 포인트

- **인메모리 챌린지 저장의 한계**: `_registration_challenges`, `_authentication_challenges`, `_login_challenges` 세 dict가 프로세스 메모리에만 존재한다. 멀티 프로세스(uvicorn workers > 1) 환경이나 서버 재시작 시 챌린지가 사라져 검증이 실패한다. 프로덕션에서는 `redis.setex(f"fido:{user_id}", 300, challenge)` 형태로 TTL이 있는 외부 스토어에 위임해야 한다.

- **sign_count=0 예외 처리 미구현**: FIDO2 사양은 sign_count가 0이면 "카운터를 지원하지 않는 authenticator"로 간주해 검증을 통과시키도록 권장한다. 현재 구현이 `verify_authentication_response()` 라이브러리 기본 동작에 위임하고 있어 실제 클론 탐지가 어떻게 동작하는지는 py_webauthn 버전에 따라 달라진다.

- **세 개의 챌린지 맵 → 단일 테이블 통합 여지**: 등록·인증·로그인 챌린지가 각자 별도 dict에 저장된다. 키 설계(`user_id` vs `pre_auth_token`)가 달라 통합이 쉽지 않지만, Redis를 도입한다면 prefix로 구분하는 단일 인터페이스로 추상화할 수 있다.

- **`credential_backed_up` → device_type 판단**: `verification.credential_backed_up`이 True면 "platform"(iCloud Keychain 등에 동기화되는 패스키), False면 "cross-platform"(물리 보안키)으로 분류한다. 이 값은 attestation에서 추출되는 단일 비트이므로 다소 단순화된 분류지만, UI에서 장치 유형을 구분해 보여주는 용도로는 충분하다.

- **`attestation: "none"` vs `"direct"` 트레이드오프**: 현재 설정에서는 authenticator가 보내는 attestation statement를 서버가 검증하지 않는다. 기업 환경에서는 "FIPS 인증 YubiKey만 허용"처럼 aaguid로 허용 목록을 관리하려면 `"direct"` 또는 `"enterprise"` attestation으로 전환하고 FIDO MDS(Metadata Service)를 연동해야 한다. PayWise는 소비자 서비스이므로 "none"이 적합한 선택이다.

---

### 예상 질문 & 답변 (발표 Q&A 대비)

**Q1. TOTP가 있는데 FIDO2까지 추가한 이유는?**
> TOTP는 공유 비밀(secret)이 서버에도 저장되어 DB 유출 시 위험. FIDO2는 **private key가 장치 밖으로 나가지 않는** 구조라 서버 유출에 강함. 또 피싱 사이트에 코드를 입력하는 사회공학 공격을 origin 검증으로 자동 차단.

**Q2. 챌린지를 인메모리 dict에 저장하면 멀티 인스턴스에서 문제 안 생기나요?**
> 네, 현재 단일 인스턴스 가정. K8s replica 또는 Gunicorn `--workers 4`로 띄우면 챌린지 라우팅이 워커마다 분리되어 검증 실패 가능. Redis hash + TTL로 옮기는 게 표준 해법(후속).

**Q3. 패스키 분실 시 복구는?**
> 현재 1차 복구는 TOTP 코드, 2차는 비밀번호 + 이메일 인증. 패스키만 등록한 사용자(passwordless-only)는 등록 시점에 백업 코드 발급 권장. UX 흐름은 후속 작업.

**Q4. `attestation: "none"`인데 보안에 문제 없나요?**
> 소비자 서비스라 적합한 선택입니다. 기업 환경에서 "FIPS 인증 YubiKey만 허용"이 필요하면 `"direct"`로 전환하고 FIDO MDS 연동. PayWise는 사용자 편의 우선.

**Q5. sign_count 검증이 정말 도용을 막나요?**
> Authenticator가 매 인증마다 카운터를 증가시키는데, 만약 키가 복제(클론)되면 두 디바이스에서 카운터가 엇갈려 서버가 비정상을 즉시 탐지. 100% 차단은 아니지만 도용 흔적 보존엔 효과적.

---

## ⑥ 한 줄 정리

브라우저 네이티브 WebAuthn API와 py_webauthn의 챌린지-응답 검증으로 private key가 장치 밖을 나가지 않는 FIDO2 인증을 구현하고, **sign_count 클론 탐지**와 **pre_auth_token 바인딩**으로 replay·도용 공격 경계를 만들었다.
