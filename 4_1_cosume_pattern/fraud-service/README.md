# Fraud scoring service (skeleton)

캡스톤(`4_1_capstone`)의 **연구·재현**과 분리한 **추론 API**용 최소 구조입니다. 학습 스크립트는 capstone 쪽에 두고, 여기서는 **배포 가능한 추론 경로**만 담당합니다.

## 구조

| 경로 | 역할 |
|------|------|
| `app/api/` | HTTP 라우트 (헬스, 점수) |
| `app/scoring/` | 모델 로드·특성 변환 (캡스톤 로직을 점진적으로 이식) |
| `app/config.py` | 환경 변수·설정 |
| `models/` | 학습 산출물(가중치 등) — Git에는 크기 때문에 보통 넣지 않고 README만 둠 |

## 로컬 실행

```text
cd fraud-service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
REM .env 에 MODEL_PATH, CAPSTONE_OUTPUTS_DIR 채우기 (capstone outputs/fds 경로)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**포트 충돌** (`[WinError 10048]` / `address already in use`): 이미 8000을 쓰는 프로세스가 있음(예: 예전 uvicorn).  
- 다른 포트: `py -3 -m uvicorn app.main:app --host 127.0.0.1 --port 8010`  
- 또는 루트에서 `.\run_local.ps1` (기본 **8010** — 관리 페이지는 `http://127.0.0.1:8010/admin`)

PowerShell에서 **INFO 로그가 빨간 줄**로 보일 수 있음 — uvicorn이 stderr로 찍기 때문이며, 서버가 뜨면 브라우저로 접속하면 됨.

- **관리 대시보드**: 브라우저에서 `http://127.0.0.1:8000/admin` — 모델 로드 여부·캡스톤 `outputs/fds` JSON 요약
- 상태 JSON: `GET /admin/api/status`
- 헬스: `GET http://127.0.0.1:8000/health`
- 점수: `POST http://127.0.0.1:8000/v1/score` — 본문 `{"features": {"V1": 0.1, "V2": -0.2, ...}}` (V1–V30, 번들과 동일 스키마)

## 두 폴더 연결 (fraud-service + 4_1_capstone)

캡스톤은 `...\4_1_capstone`, 서비스는 `...\fraud-service`에 두는 전제다.

1. 캡스톤에서 한 번 실행해 산출물 생성:
   ```text
   cd C:\Users\alstj\Downloads\4_1_capstone
   py -3 scripts/fds/pipeline_open_standard.py
   ```
2. **방법 A** — `fraud-service` 루트에 `.env` 파일:
   ```env
   MODEL_PATH=C:\Users\alstj\Downloads\4_1_capstone\outputs\fds\model_bundle_open_full.joblib
   CAPSTONE_OUTPUTS_DIR=C:\Users\alstj\Downloads\4_1_capstone\outputs\fds
   ```
3. **방법 B** — 스크립트(캡스톤 경로만 맞추면 됨):
   ```text
   .\scripts\setup_capstone_paths.ps1
   .\scripts\setup_capstone_paths.ps1 -CapstoneRoot "D:\work\4_1_capstone"
   ```
4. `uvicorn`을 **`fraud-service` 폴더에서** 띄운 뒤 브라우저에서 `/admin` 새로고침.

`.env`는 `.gitignore`에 있으니 경로가 다른 PC면 위처럼 다시 만들면 된다.

## 캡스톤과의 관계

- **데이터 CSV 경로** 대신, API는 **요청 JSON 특성**을 받는 형태로 확장하면 됩니다.
- 모델은 캡스톤 `outputs/fds/*.joblib`를 `MODEL_PATH`로 가리키거나, `models/`에 복사 후 경로 지정.
