# #15 ABAC/ABE 접근 제어 — 속성으로 판단하고, 속성으로 암호화한다

## ① 개요

PayWise의 fraud-service는 두 가지 속성 기반 보안 메커니즘을 한 시스템 안에 함께 구현했다. **ABAC (Attribute-Based Access Control)** 는 사용자/리소스/환경 속성을 평가해 접근을 허용·거부·마스킹하고, **ABE (Attribute-Based Encryption)** 는 데이터를 암호화할 때부터 "이 속성을 가진 사용자만 복호화 가능"이라는 정책을 함께 묶는다. 전자가 게이트키퍼라면, 후자는 데이터 자체에 정책을 새기는 방식이다. 두 메커니즘이 결합되면 — 인증 우회·DB 직접 노출·내부자 위협 등 다층적 공격 표면에 대응할 수 있다.

> **구현 참고**: 실제 CP-ABE 라이브러리(charm-crypto)는 도입되어 있지 않고, 인터페이스만 동일하게 유지한 **경량 구현**(HMAC + AES-GCM)이 사용된다. [abe_engine.py:9-13](fraud-service/app/services/abe_engine.py:9) 의 docstring 에서 "실제 CP-ABE 라이브러리(charm-crypto) 도입 시 교체 가능하도록 인터페이스 분리" 라고 명시되어 있다.

---

## ② 시스템 구성

```
┌────────────────────────────────────────────────────────────────┐
│  요청 수신 (FastAPI)                                            │
│   X-ABE-Token: Base64({user_id, attributes:{role, dept,...}}) │
└────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  AbeAuthMiddleware  (abe_auth.py — Layer 2)                    │
│   ├─ 토큰 디코딩 → AttributeToken                              │
│   ├─ find_policy(method, path)  ← YAML 정책 매칭               │
│   ├─ evaluate_access_structure(structure, attrs)              │
│   │       │                                                     │
│   │       └─ build_access_tree() → AccessTreeNode              │
│   │              (AND/OR/괄호/와일드카드 평가)                 │
│   │                                                             │
│   └─ 속성 불만족 → 403 Forbidden                               │
│      속성 만족   → request.state.abe_attrs 저장                │
└────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  라우터 핸들러 (routes_score, routes_fraud, ...)               │
│   비즈니스 로직 수행 → 응답 생성                                │
└────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  filter_response()  (응답 단계 마스킹 — 후속 통합 예정)         │
│   encrypted_fields → "[ENCRYPTED: 접근 권한 부족]"             │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│  ABACEngine  (abac_engine.py — 데이터 마스킹 전용)             │
│   ├─ 8가지 ABAC 규칙 평가                                       │
│   │   (Clearance, BusinessHours, Location, Device, MFA,        │
│   │    DeptSeparation, ThreatLevel, SensitiveFieldMask)        │
│   ├─ AccessDecision (allowed, masking_level, masked_fields)    │
│   └─ mask_data(data, decision) → 행/열/셀 단위 마스킹          │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│  AttributeRevocationManager  ─  속성 취소(SRS 2,5)             │
│  CPABE_Simulator             ─  Setup/KeyGen/Encrypt/Decrypt   │
│  BidirectionalPolicy         ─  No-Read + No-Write 동시 적용   │
│  encrypt_field / decrypt_field ─ AES-GCM + access_structure AAD│
└────────────────────────────────────────────────────────────────┘
```

| 파일 | 역할 |
|---|---|
| `app/services/abe_engine.py` | CP-ABE 시뮬레이션, Access Tree, 필드 암호화, 정책 로더 |
| `app/services/abac_engine.py` | 8가지 ABAC 규칙, 행/열/셀 마스킹, FGAC vs CGAC 비교 |
| `app/middleware/abe_auth.py` | 미들웨어 — 토큰 파싱 + 정책 평가 + 403 차단 |
| `policies/abe_access_policy_v1.yaml` | 11개 리소스별 access_structure 정의 |

---

## ③ 동작 흐름

### ABE 미들웨어 (요청 게이트키핑)

```
1. ABE_ENABLED 환경변수 확인 — false면 기본 viewer 속성으로 통과
2. 제외 경로(/health, /docs 등) 우회
3. X-ABE-Token 헤더 → Base64 디코딩 → AttributeToken
   ↳ 토큰 없으면 anonymous + 기본 속성
   ↳ 디코딩 실패 시 400 Bad Request
4. find_policy(method, path) — YAML 정책 중 매칭되는 것 찾기
   ↳ "*" 와일드카드 지원: "GET /v1/audit/*" → "GET /v1/audit/chain/status"
5. evaluate_access_structure(policy.access_structure, user_attr_set)
   ↳ build_access_tree로 AccessTreeNode 구성 → 재귀 평가
   ↳ 실패 시 정규식 + eval() fallback
6. 속성 불만족 → 403 + 정책 + 사용자 속성 노출
   속성 만족   → request.state.abe_attrs 저장 후 다음 핸들러로
```

### ABAC 엔진 (데이터 마스킹)

```
1. SubjectAttributes / ResourceAttributes / EnvironmentAttributes 구성
2. ABACEngine.evaluate() — 8개 규칙 순회
   ↳ DENY 발생 시 즉시 break (이후 규칙 평가 스킵)
   ↳ MASK_COLUMN/MASK_ROW/MASK_CELL 누적
3. masking_level 우선순위: row > cell > column > none
4. mask_data(data, decision) — 데이터 행렬에 마스킹 적용
   ↳ row 마스킹: 특정 행 전체를 "***"
   ↳ column 마스킹: _mask_value() 로 첫/마지막만 보임 ("12345" → "1***5")
   ↳ cell 마스킹: 특정 필드의 값만 마스킹
```

---

## ④ 핵심 코드 분석

### 4-1. AttributeToken — 사용자 속성 컨테이너

```python
# abe_engine.py:36-73
@dataclass
class AttributeToken:
    user_id: str
    attributes: dict[str, str]   # {"role": "analyst", "dept": "fraud_team", ...}
    issued_at: str = ""
    signature: str = ""
    expires_at: str = ""

    def attr_set(self) -> set[str]:
        """속성을 'key:value' 형태의 집합으로 반환."""
        return {f"{k}:{v}" for k, v in self.attributes.items()}

    def sign(self, master_secret: str) -> None:
        payload = json.dumps(
            {"user_id": self.user_id, "attributes": self.attributes, "issued_at": self.issued_at},
            sort_keys=True,
        )
        self.signature = hmac.new(master_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    def verify_signature(self, master_secret: str) -> bool:
        # ... payload 재생성 후 hmac.compare_digest로 timing-safe 비교
        return hmac.compare_digest(self.signature, expected)
```

[abe_engine.py:36](fraud-service/app/services/abe_engine.py:36)

`attr_set()` 이 dict를 `{"role:analyst", "dept:fraud_team", ...}` 형태의 set으로 변환하는 것이 핵심이다. 이후 모든 정책 평가는 이 set을 입력으로 받아 `"role:analyst" in user_attrs` 같은 단순 멤버십 체크로 환원된다.

서명 검증은 `hmac.compare_digest()` 를 사용한 timing-safe 비교 — 단순 `==` 비교는 짧은 시간 차이로 부분 일치를 탐지하는 timing attack 에 취약하기 때문이다.

### 4-2. CP-ABE Access Tree — AND/OR 게이트의 임계값 추상화

```python
# abe_engine.py:78-101
@dataclass
class AccessTreeNode:
    threshold: int = 1            # 1=OR, len(children)=AND
    children: list["AccessTreeNode"] = field(default_factory=list)
    attribute: str = ""           # 리프 노드만 사용

    @property
    def is_leaf(self) -> bool:
        return bool(self.attribute)

    def evaluate(self, user_attrs: set[str]) -> bool:
        if self.is_leaf:
            if self.attribute.endswith(":*"):
                key = self.attribute[:-2]
                return any(a.startswith(f"{key}:") for a in user_attrs)
            return self.attribute in user_attrs
        satisfied = sum(1 for c in self.children if c.evaluate(user_attrs))
        return satisfied >= self.threshold
```

[abe_engine.py:78](fraud-service/app/services/abe_engine.py:78)

CP-ABE 의 **threshold gate** 개념을 그대로 구현한다. `threshold=1` 이면 자식 중 하나만 만족해도 통과(OR), `threshold=N` 이면 N개 모두 만족해야 통과(AND). 일반적인 boolean tree 와 달리 "k-of-n" 임계값을 자연스럽게 표현할 수 있는 구조다 — 예: "5명의 임원 중 3명 동의" 같은 정책도 같은 코드로 표현 가능하다.

와일드카드 처리(`role:*`)는 리프 노드 평가에서 prefix 매칭으로 처리된다. `dept:fraud_team`, `dept:compliance` 어느 쪽이든 `dept:*` 정책을 만족시킨다.

### 4-3. Access Structure 파서 — 최상위 분리 알고리즘

```python
# abe_engine.py:104-161
def build_access_tree(structure: str) -> AccessTreeNode:
    structure = structure.strip()

    # 외부 괄호 제거
    if structure.startswith("(") and structure.endswith(")"):
        inner = structure[1:-1]
        depth = 0
        for c in inner:
            if c == "(":   depth += 1
            elif c == ")": depth -= 1
            if depth < 0:  break
        else:
            structure = inner

    # AND 분리 시도 (최상위 레벨)
    parts = _split_top_level(structure, "AND")
    if len(parts) > 1:
        node = AccessTreeNode(threshold=len(parts))    # AND
        for p in parts:
            node.children.append(build_access_tree(p.strip()))
        return node

    # OR 분리 시도
    parts = _split_top_level(structure, "OR")
    if len(parts) > 1:
        node = AccessTreeNode(threshold=1)             # OR
        for p in parts:
            node.children.append(build_access_tree(p.strip()))
        return node

    # 리프 노드
    return AccessTreeNode(attribute=structure.strip())
```

[abe_engine.py:104](fraud-service/app/services/abe_engine.py:104)

`_split_top_level` 은 괄호 깊이를 추적하며 최상위 레벨에서만 연산자를 분리한다. AND를 OR 보다 먼저 시도해서 **AND가 OR 보다 우선 결합**되도록 트리를 구성한다. 즉 `A OR B AND C` 는 `A OR (B AND C)` 로 해석된다 — 일반적인 boolean 우선순위와 동일.

### 4-4. Fallback 평가 — `eval()` 의 안전한(?) 사용

```python
# abe_engine.py:166-196
def evaluate_access_structure(structure: str, user_attrs: set[str]) -> bool:
    try:
        tree = build_access_tree(structure)
        return tree.evaluate(user_attrs)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(...)

    # fallback: 기존 방식
    expr = structure
    tokens = re.findall(r"[\w]+:[\w*]+", expr)
    for token in tokens:
        key, value = token.split(":", 1)
        matched = any(a.startswith(f"{key}:") for a in user_attrs) if value == "*" else token in user_attrs
        expr = expr.replace(token, str(matched), 1)

    expr = expr.replace("AND", "and").replace("OR", "or")
    try:
        return bool(eval(expr))  # noqa: S307 — 내부 정책 식만 평가
    except Exception:
        return False
```

[abe_engine.py:166](fraud-service/app/services/abe_engine.py:166)

Access Tree 평가가 실패하면 정규식으로 토큰을 뽑은 뒤 `True/False` 로 치환한 문자열을 `eval()` 한다. 주석에 "S307 — 내부 정책 식만 평가" 라고 적혀 있지만, **YAML 정책이 외부에서 변조될 수 있다면 RCE 위험이 있는 코드**다. 정책 파일을 신뢰할 수 있는 빌드 산출물로 관리하는 운영 정책이 전제되어야 한다.

### 4-5. 필드 레벨 암호화 — AES-GCM with policy-as-AAD

```python
# abe_engine.py:382-398
def encrypt_field(value: Any, access_structure: str) -> str:
    plaintext = json.dumps(value, ensure_ascii=False).encode("utf-8")
    key   = _derive_field_key(access_structure, "field")   # SHA-256(secret + structure)
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext, access_structure.encode("utf-8"))  # ← AAD!
    blob = nonce + ct
    return "ABE:" + b64encode(blob).decode("ascii")
```

[abe_engine.py:382](fraud-service/app/services/abe_engine.py:382)

**핵심은 `access_structure.encode("utf-8")` 가 AAD(Additional Authenticated Data) 로 들어간다는 점**이다. AES-GCM 의 AAD 는 암호화되지는 않지만 무결성이 보장된다. 즉:

- 정책이 한 글자라도 바뀌면 복호화 시 인증 실패 (정책 위변조 자동 탐지)
- 키 자체도 정책 해시에서 파생되므로 다른 정책으로는 복호화 자체가 불가능

```python
# abe_engine.py:401-437
def decrypt_field(encrypted: str, user_attrs: set[str], access_structure: str = "") -> Any:
    # ...
    if access_structure and not evaluate_access_structure(access_structure, user_attrs):
        return None        # 정책 미충족 → 복호화 시도조차 안 함

    blob  = b64decode(encrypted[4:])
    nonce = blob[:12]
    ct    = blob[12:]

    key = _derive_field_key(access_structure, "field")
    aad = access_structure.encode("utf-8") if access_structure else None
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ct, aad)
        return json.loads(plaintext)
    except Exception:
        return None
```

[abe_engine.py:401](fraud-service/app/services/abe_engine.py:401)

복호화 흐름은 **이중 안전망**이다: ① 정책 평가가 실패하면 키 파생 자체를 건너뛰고, ② 어떤 이유로 ①을 우회하더라도 잘못된 키로는 GCM 인증이 실패한다.

### 4-6. CP-ABE Simulator — 4단계 흐름의 교육적 구현

```python
# abe_engine.py:275-328
class CPABE_Simulator:
    """SRS 5: CP-ABE 4단계 흐름 시뮬레이션. Setup → KeyGen → Encrypt → Decrypt"""

    def setup(self) -> dict[str, Any]:
        """1단계: 공개 파라미터 + 마스터 키 생성."""
        self._public_params = {
            "group": "BN256",
            "g": hashlib.sha256(b"generator").hexdigest()[:16],
            "policy_universe": ["role:*", "dept:*", "clearance:*"],
        }

    def keygen(self, user_id: str, attributes: list[str]) -> dict[str, Any]:
        """2단계: 속성 기반 사용자 비밀키 생성."""
        sk_material = hashlib.sha256(
            f"{self._master_secret}:{user_id}:{','.join(sorted(attributes))}".encode()
        ).hexdigest()
        # ...

    def encrypt(self, plaintext: str, access_structure: str) -> dict[str, Any]:
        """3단계: 접근 구조로 암호화."""
        policy_hash = hash_policy(access_structure)
        # ...

    def decrypt(self, ct, user_id, user_attrs, access_structure):
        """4단계: 속성 만족 시 복호화."""
        if ct.get("policy_hash") != hash_policy(access_structure):
            return {"success": False, "reason": "Policy hash mismatch"}
        if evaluate_access_structure(access_structure, user_attrs):
            return {"success": True, "plaintext": "[decrypted]"}
        return {"success": False, "reason": "Attributes do not satisfy"}
```

[abe_engine.py:275](fraud-service/app/services/abe_engine.py:275)

실제 암호 연산은 SHA-256 해시로 대체되어 있어 **암호학적 보안성은 없는** 시뮬레이터다. 하지만 4단계 인터페이스 (Setup/KeyGen/Encrypt/Decrypt) 는 charm-crypto 의 그것과 동일하게 맞춰져 있어서, 실제 라이브러리로 교체해도 호출 코드는 변경할 필요가 없다. 이는 학술 논문(SRS 5)에서 CP-ABE 흐름을 시연하기 위한 설계로 보인다.

### 4-7. 미들웨어의 정책 매칭 + 403 응답

```python
# abe_auth.py:92-107
policies = _load_policies_lazy()
policy = find_policy(policies, method, path)

if policy:
    user_attr_set = token.attr_set()
    if not evaluate_access_structure(policy.access_structure, user_attr_set):
        return JSONResponse(
            status_code=403,
            content={
                "error": "Forbidden",
                "detail": "속성 기반 접근 제어: 요청된 리소스에 대한 접근 권한이 없습니다.",
                "required_policy": policy.access_structure,
                "your_attributes": sorted(user_attr_set),
            },
        )

request.state.abe_attrs = token.attributes
request.state.abe_token = token
```

[abe_auth.py:92](fraud-service/app/middleware/abe_auth.py:92)

403 응답에 **required_policy 와 your_attributes 가 그대로 노출**된다. 디버깅 편의를 위한 의도적 설계로 보이지만, 운영 환경에서는 정책 자체와 사용자 속성 전부를 응답에 노출하는 것이 정보 유출이 될 수 있다. ABE 의 "Hidden Policy"(SRS 7) 원칙과도 상충된다.

### 4-8. ABAC 8가지 규칙 평가 + 마스킹 결정

```python
# abac_engine.py:94-138
def evaluate(self, subject, resource, env=None) -> AccessDecision:
    if env is None:
        env = EnvironmentAttributes()

    applied_rules: list[str] = []
    denied_reason = ""
    masked_fields: list[str] = []
    masking_level = "none"

    for rule in self._rules:
        result = rule.evaluate(subject, resource, env)
        if result is not None:
            applied_rules.append(rule.rule_id)
            if result["action"] == "DENY":
                denied_reason = result["reason"]
                break                                    # 첫 DENY 에서 즉시 종료
            elif result["action"] == "MASK_COLUMN":
                masked_fields.extend(result.get("fields", []))
                masking_level = "column"
            elif result["action"] == "MASK_ROW":
                masking_level = "row"
                masked_fields.extend(result.get("fields", []))
            elif result["action"] == "MASK_CELL":
                if masking_level != "row":               # row > cell 우선순위
                    masking_level = "cell"
                masked_fields.extend(result.get("fields", []))

    if denied_reason:
        return AccessDecision(allowed=False, reason=denied_reason, applied_rules=applied_rules)

    return AccessDecision(
        allowed=True, reason="접근 허용",
        masked_fields=list(set(masked_fields)),
        masking_level=masking_level,
        applied_rules=applied_rules,
    )
```

[abac_engine.py:94](fraud-service/app/services/abac_engine.py:94)

**masking_level 우선순위 규칙**: `row > cell > column > none`. 한 규칙이 row 마스킹을 이미 결정했으면, 이후 cell 마스킹 규칙이 발동해도 masking_level 은 row 로 유지된다 — 더 강한(범위가 넓은) 마스킹이 우선이다. 단 `masked_fields` 자체는 모든 규칙에서 누적되어 set으로 합쳐진다.

8가지 규칙은 다음 표와 같다:

| 규칙 | 조건 | 액션 |
|---|---|---|
| ClearanceLevel | `subject.clearance < resource.sensitivity` | DENY |
| BusinessHours | `!is_business_hours && sensitivity ≥ HIGH` | DENY (CRITICAL) / MASK_COLUMN (HIGH) |
| LocationRestriction | `location=external && sensitivity ≥ HIGH` | DENY (TOP_SECRET) / MASK_COLUMN |
| DeviceType | `device ∈ {mobile, tablet} && sensitivity ≥ HIGH` | MASK_CELL |
| MFARequirement | `!mfa_verified && sensitivity ≥ HIGH` | DENY |
| DepartmentSeparation | `dept ≠ owner_dept && sensitivity ≥ MEDIUM && !admin` | MASK_COLUMN |
| ThreatLevel | `threat ∈ {high, critical} && sensitivity ≥ MEDIUM && role ∉ {admin, auditor}` | MASK_COLUMN |
| SensitiveFieldMask | `role == viewer` | MASK_COLUMN (PII) |

### 4-9. 마스킹 함수 — 첫·마지막만 살리기

```python
# abac_engine.py:338-345
def _mask_value(value: Any) -> str:
    if value is None:
        return "***"
    s = str(value)
    if len(s) <= 2:
        return "***"
    return s[0] + "*" * (len(s) - 2) + s[-1]
```

[abac_engine.py:338](fraud-service/app/services/abac_engine.py:338)

`"hong@example.com"` → `"h**************m"`. 길이 정보와 첫·마지막 글자가 그대로 노출되는 약한 마스킹이다. 이메일·전화번호처럼 부분 매칭으로 추론 가능한 경우에는 부족할 수 있다. 더 안전하게는 길이 정보까지 숨기기 위해 고정 길이 `"***"` 로 처리하거나, hash-based pseudonym 으로 대체하는 방식이 있다.

### 4-10. 정책 YAML — 11개 리소스별 access_structure

```yaml
# policies/abe_access_policy_v1.yaml:12-15
- resource: "POST /v1/score"
  access_structure: "(role:analyst OR role:admin OR role:system) AND dept:fraud_team"
  encrypted_fields: ["score", "rule_ids", "reason_code"]

# policies/abe_access_policy_v1.yaml:18-21
- resource: "GET /v1/audit/*"
  access_structure: "role:admin OR role:auditor OR (role:analyst AND clearance:high)"
  encrypted_fields: ["user_id", "amount", "score"]
```

[abe_access_policy_v1.yaml:10](fraud-service/policies/abe_access_policy_v1.yaml:10)

11개 리소스 전부에 대해 미들웨어 단계의 access_structure 와 응답 단계의 encrypted_fields 가 함께 정의된다. **두 가지가 동시에 적용**되는 설계 — 미들웨어를 통과해도 응답 레벨에서 마스킹이 한 번 더 가능하다.

### 4-11. 양방향 접근 제어 — No-Read + No-Write 동시 적용

```python
# abe_engine.py:246-270
@dataclass
class BidirectionalPolicy:
    """SRS 2: No-read + No-write 동시 적용 정책."""
    resource: str
    no_read_structure: str = ""
    no_write_structure: str = ""
    normal_access_structure: str = ""

    def can_read(self, user_attrs: set[str]) -> bool:
        if self.no_read_structure and evaluate_access_structure(self.no_read_structure, user_attrs):
            return False
        if self.normal_access_structure:
            return evaluate_access_structure(self.normal_access_structure, user_attrs)
        return True

    def can_write(self, user_attrs: set[str]) -> bool:
        # 동일 패턴
```

[abe_engine.py:246](fraud-service/app/services/abe_engine.py:246)

전통적인 ACL 이 "허용 목록"으로 동작하는 데 비해, 이 구조는 "**금지 목록 + 허용 목록의 결합**"이다. `no_read_structure` 가 우선 평가되어 차단되면 normal 평가는 스킵된다 — 직무 분리 같은 음의 정책을 깔끔하게 표현할 수 있다. 다만 현재 코드 베이스에서는 이 BidirectionalPolicy 클래스를 호출하는 곳이 없어, 인프라만 준비된 상태다.

### 4-12. 속성 취소 + 응답 필터 통합

```python
# abe_engine.py:442-467
def filter_response(
    response_data, encrypted_fields, user_attrs, access_structure, user_id="",
) -> dict[str, Any]:
    if not encrypted_fields:
        return response_data

    # 취소된 속성 제거 후 평가
    effective_attrs = revocation_manager.filter_attrs(user_id, user_attrs) if user_id else user_attrs
    has_access = evaluate_access_structure(access_structure, effective_attrs)
    if has_access:
        return response_data

    filtered = dict(response_data)
    for f in encrypted_fields:
        if f in filtered:
            filtered[f] = "[ENCRYPTED: 접근 권한 부족]"
    return filtered
```

[abe_engine.py:442](fraud-service/app/services/abe_engine.py:442)

`revocation_manager.filter_attrs()` 가 effective attributes 를 만들어내는 점이 핵심이다. 사용자가 인증 토큰에 `role:analyst` 를 갖고 있어도, 운영자가 그 속성을 취소(revoke)했다면 정책 평가에서는 제외된다. 토큰을 재발급할 필요 없이 즉시 권한 박탈이 가능한 구조다.

---

## ⑤ 설계 포인트 / 트러블슈팅 거리

- **ABAC 엔진과 ABE 미들웨어가 분리되어 있고, 통합 호출 지점이 없음**: `ABACEngine` 은 8가지 풍부한 규칙(시간/위치/기기/MFA/위협레벨)을 평가할 수 있는데, 미들웨어 흐름에서는 `evaluate_access_structure` 만 호출되고 `ABACEngine.evaluate` 는 어디에서도 호출되지 않는다. 결과적으로 BusinessHours/LocationRestriction/DeviceType/MFA 같은 규칙은 코드만 존재하고 실제 런타임에선 비활성 상태다. 미들웨어에서 토큰 → SubjectAttributes 변환 후 ABACEngine.evaluate 를 호출하고, 그 결과로 응답을 마스킹하는 통합 레이어가 필요하다.

- **403 응답에서 정책 전문 + 사용자 속성 노출**: [abe_auth.py:101-106](fraud-service/app/middleware/abe_auth.py:101) 의 응답에 `required_policy` 와 `your_attributes` 가 평문으로 포함된다. 디버깅에는 편하지만 운영 환경에서는 공격자에게 정책 구조와 권한 모델을 그대로 보여주는 셈이다. SRS 7에서 강조하는 "Hidden Policy" 원칙과도 모순된다. 운영 모드 플래그를 두고 production 에서는 generic 한 메시지만 노출해야 한다.

- **`evaluate_access_structure` 의 fallback `eval()` 위험**: AccessTree 빌드가 실패하면 정규식으로 토큰을 추출한 뒤 `eval()` 로 평가한다. YAML 정책 파일이 신뢰할 수 있는 출처에서만 로드된다는 가정이 깔려 있지만, **누군가 `access_structure` 에 임의 파이썬 표현식을 넣을 수 있다면 RCE**다. AccessTree 가 모든 합법적 표현을 처리하도록 보장하고 fallback 자체를 제거하는 것이 안전하다.

- **마스터 시크릿이 환경변수 기본값에 노출**: [abe_engine.py:370](fraud-service/app/services/abe_engine.py:370) 에서 `_ABE_SECRET = os.getenv("ABE_MASTER_SECRET", "default-dev-secret-change-in-prod")`. 환경변수가 누락되면 하드코딩된 기본값이 사용되는데, 이 값은 모든 사용자가 코드 검색만으로 알 수 있다. fail-fast 로 환경변수 미설정 시 기동을 중단하는 것이 안전하다.

- **`encrypt_field` 와 `decrypt_field` 의 키 파생이 access_structure 문자열에 의존**: 정책 문자열이 한 글자라도 다르면(공백·괄호 추가/제거) 키가 달라지고 복호화가 실패한다. 예를 들어 정책을 `"role:analyst OR role:admin"` 로 암호화한 뒤, 의미가 동등한 `"role:admin OR role:analyst"` 로 복호화 시도하면 실패한다. 정규화된(canonicalized) 정책 표현으로 키 파생을 하는 것이 안전하다.

- **속성 취소 후 토큰 자체는 유효**: `revocation_manager` 가 effective attributes 를 필터링해주지만, 미들웨어의 정책 평가는 `token.attr_set()` 을 그대로 사용한다 ([abe_auth.py:97](fraud-service/app/middleware/abe_auth.py:97)). 즉 미들웨어 단계에서는 취소된 속성이 그대로 인정되어 통과되고, `filter_response` 단계에서야 차단된다. 미들웨어에도 `revocation_manager.filter_attrs()` 를 적용해 일관성을 맞춰야 한다.

- **`BidirectionalPolicy` 와 `CPABE_Simulator` 가 미사용 인프라**: 두 클래스는 SRS 요구사항(2, 5)을 충족하기 위해 작성되었지만 실제 호출처가 없다. 학술적 데모용 코드와 운영 코드의 경계가 모호하다 — 별도 디렉토리(예: `app/services/research/`) 로 분리하거나, README 에 명확히 문서화하는 것이 향후 유지보수에 도움이 된다.

- **정책 핫 리로드 부재**: `_load_policies_lazy()` 가 처음 한 번만 YAML 을 읽고 모듈 변수에 캐싱한다 ([abe_auth.py:51-55](fraud-service/app/middleware/abe_auth.py:51)). 정책을 수정하면 fraud-service 를 재시작해야 반영된다. 운영 중 권한 변경 빈도가 높다면 파일 시스템 watch 또는 admin API 를 통한 invalidate 메커니즘이 필요하다.

---

### 예상 질문 & 답변 (발표 Q&A 대비)

**Q1. charm-crypto를 안 쓰고 HMAC + AES-GCM으로 ABE를 구현한 이유는?**
> charm-crypto는 의존성과 빌드 환경(GMP, PBC) 제약이 큽니다. 인터페이스만 동일하게 유지한 경량 구현으로 우선 가고, 운영 도입 시점에 charm-crypto로 교체 가능하게 분리. 약점은 진정한 CP-ABE 보안 모델이 아니라는 점이고, ⑤절에서 명시.

**Q2. ABAC와 ABE는 어떻게 다른가요?**
> ABAC는 **접근 시점 게이트키퍼** — 사용자 속성을 평가해 허용/거부. ABE는 **데이터 자체에 정책을 새기는 암호화** — 정책을 만족하는 사용자만 복호화. 전자는 인증 우회에 약하고 후자는 데이터 유출 후에도 보호.

**Q3. ABAC 8규칙이 fraud-service에 있고 backend에 5개가 따로 있는데, 정합성은?**
> #4에서 정리한 시뮬레이션 분리 이슈. fraud-service가 정본이고 backend는 시연용. 통합은 후속 작업이며, 발표에선 이 차이를 명시.

**Q4. 정책 변경 시 즉시 반영되나요?**
> 아니요, 현재 `_load_policies_lazy()`가 모듈 변수에 캐싱해서 재시작 필요. 운영에서 권한 변경 빈도가 높으면 파일 watch 또는 admin API invalidate 메커니즘이 후속 작업.

**Q5. 내부자(admin)가 모든 데이터를 볼 수 있는 백도어는?**
> ABE 정책에 admin 속성을 명시적으로 부여한 경우만 복호화 가능. 다만 경량 구현이라 마스터 키 유출 시 우회 가능 — 진정한 multi-authority CP-ABE로 후속 강화.

---

## ⑥ 한 줄 정리

CP-ABE Access Tree(threshold gate)로 정책을 평가하고 AES-GCM의 AAD에 정책 자체를 묶어 데이터 무결성과 접근 제어를 동시에 보장하는 — Layer 2 속성 기반 보안 시스템. 단, ABAC 8규칙과 ABE 미들웨어가 아직 통합되지 않은 채 병렬로 존재해 풍부한 규칙들이 런타임에 활용되지 않는 상태다.
