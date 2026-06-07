# PayWise 외부 배포 가이드 (Vercel + Render)

> 프론트(Next.js) → **Vercel**, 백엔드/추론/DB → **Render**.
> Kafka 제외(없어도 graceful 기동). 모든 코드 변경은 로컬 실행과 호환(기본값=기존 동작).

## 구성
```
[Vercel] frontend (Next.js)  ──HTTP──▶  [Render] backend (FastAPI)
                                              │  ├─▶ paywise-db (Postgres)
                                              │  ├─▶ paywise-redis (Key Value)
                                              └─▶ paywise-fraud (FastAPI, 모델 내장)
```

## 0. 사전 준비
- GitHub repo: `kerbosalstjidentity-spec/cap_stone` (이미 있음)
- 배포 브랜치: `deploy/render-vercel` (이 변경들이 담긴 브랜치)
- 계정: **Render**, **Vercel** (둘 다 GitHub 로그인 가능)

> 먼저 브랜치를 push 해야 Render/Vercel 이 볼 수 있음:
> `git push -u origin deploy/render-vercel`
> (또는 master 에 머지 후 master 로 배포)

---

## 1. Render — 백엔드/추론/DB (Blueprint 한 번에)

1. Render 대시보드 → **New → Blueprint**
2. `cap_stone` repo 연결 → **브랜치 `deploy/render-vercel`** 선택
3. Render 가 루트의 **`render.yaml`** 을 읽어 4개 리소스를 자동 생성:
   - `paywise-db` (Postgres), `paywise-redis` (Key Value)
   - `paywise-fraud` (추론), `paywise-backend` (API)
4. **Apply** → 빌드 시작. (첫 빌드 수 분)
5. 빌드 후 **`paywise-backend` 의 URL 복사** (예: `https://paywise-backend.onrender.com`)
   - 백엔드 시작 시 **Alembic 마이그레이션 자동 실행** → 테이블 생성됨
   - `GET /health` 가 200 이면 정상

### 데모 데이터 시드 (선택)
```
curl -X POST https://paywise-backend.onrender.com/v1/seed/demo/demo_user_001
```

---

## 2. Vercel — 프론트엔드 (Next.js)

1. Vercel → **Add New → Project** → `cap_stone` import
2. **Root Directory = `frontend`** 로 지정 (모노레포라 필수)
3. **Environment Variables** 에 추가:
   - `NEXT_PUBLIC_BACKEND_URL` = `https://paywise-backend.onrender.com` (위 1-5 URL)
   - ※ Next.js 는 `NEXT_PUBLIC_*` 를 **빌드 시 박제** → 배포 전에 설정해야 함
4. **Deploy** → `https://<프로젝트>.vercel.app` 발급

---

## 3. 배포 후 점검
- [ ] `https://paywise-backend.onrender.com/health` → 200
- [ ] `https://paywise-backend.onrender.com/docs` → Swagger 열림
- [ ] Vercel 사이트 접속 → 백엔드와 통신되는지 (네트워크 탭 확인)
- [ ] (시드 후) 데모 사용자 데이터 보이는지

---

## 4. 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| backend 가 DB 연결 실패 | `DB_SSL=true` 확인. Render Postgres 는 SSL 필수 (코드가 env 로 처리) |
| backend `+asyncpg` 관련 에러 | `DATABASE_URL` 스킴 → 코드가 `postgresql://`→`+asyncpg` 자동 변환. env 그대로 두면 됨 |
| backend 가 fraud 호출 실패 | `FRAUD_SERVICE_URL=http://paywise-fraud:10000` (Render 사설망 내부주소). 내부망이 안 되면 fraud 의 **공개 URL**(`https://paywise-fraud.onrender.com`)로 교체 |
| fraud 가 모델 로드 실패 | `MODEL_PATH=/app/models/model_bundle_paysim_time_clean.joblib` 확인. 모델은 `fraud-service/models/` 에 포함됨(3MB) |
| Kafka 에러 로그 | 무시해도 됨 — Kafka 없이 graceful. 동기 경로는 정상 |
| `runtime: docker` 파싱 에러 | 구버전 Render 는 `env: docker` 사용 → render.yaml 키만 교체 |
| 첫 접속 ~50초 느림 | **무료티어 슬립**(15분 미사용). 발표 직전 미리 한 번 열어 깨워둘 것. 확실히 하려면 유료 $7/mo |
| FIDO2/패스키 동작 안 함 | `WEBAUTHN_RP_ID`/`WEBAUTHN_ORIGIN` 이 localhost 기본값. 패스키까지 쓰려면 backend env 에 Vercel 도메인 설정 (데모가 패스키 안 쓰면 무시 가능) |

---

## 5. 발표 직전 체크리스트
- [ ] 발표 10분 전 backend `/health` + Vercel 사이트 1회 접속 → **슬립 깨우기**
- [ ] 데모 데이터 시드 완료
- [ ] 백업: 로컬 Docker(`docs/DEMO_RUNBOOK.md`)도 띄울 수 있게 준비
