# FDS 강화 작업 — 다른 세션 인계 가이드

> 본 문서는 FDS 강화 스프린트(W5.5/W6.5/W7.5)를 다른 Claude Code 세션에서
> 이어서 진행할 수 있도록 만든 부팅 가이드.
>
> 첫 줄에 이 파일을 읽히면 모든 컨텍스트를 자동으로 복원한다.

## 1. 첫 메시지 템플릿 (다른 세션에서 그대로 붙여넣기)

```
docs/ROADMAP.md, docs/FDS_ROADMAP.md, docs/FDS_RESUME.md 읽고
미완료 W5.5/W6.5/W7.5 작업 중 "in_progress" 또는 첫 미완료 항목부터 이어서 진행해줘.
완료 시 4단계 갱신(체크박스/블로그/진척률/변경이력) + 커밋 컨벤션 `<type>(W?.?-#?): ...`
```

## 2. 핵심 컨텍스트

- **레포**: `C:\Users\alstj\Downloads\캡스톤_프로젝트` (Windows, bash)
- **현재 브랜치**: `master`
- **이전 세션 마지막 커밋**: `762b67a` (W4 전체 + W9-#6)
- **진척률**: 30/82 (W1~W4 + W9-#6,#14 완료) — `docs/ROADMAP.md` 상단 표 참조
- **언어**: 모든 응답·커밋 메시지·블로그 표기 한국어

## 3. 작업 규칙 (생략 금지)

각 작업 완료 시 **반드시** 다음 4단계 수행:

1. **코드 변경** + 구문 검증 (`python -c "import ast; ast.parse(open(...).read())"`)
2. **블로그 글 갱신**: 출처 블로그 글의 ⑤절 해당 줄에 `(✅ ROADMAP W?.?-#? — 한 줄 요약)` 추가
3. **ROADMAP 갱신**:
   - 체크박스 `- [ ]` → `- [x] ... — ✅ <commit-sha-7> (YYYY-MM-DD)`
   - 진척률 표 카운터 +1 + % 재계산
   - 변경 이력 표에 1줄 append
4. **커밋**: `feat(W5.5-#1): <짧은 설명>` 형식 — 커밋 후 SHA를 ROADMAP placeholder `tbd` 와 교체

## 4. 다음 작업 (우선순위순)

### 즉시 시작 가능 (의존성 없음)

- **W5.5-#1** 시나리오 시뮬레이터 (반나절) — PaySim 다운로드 전에 가능, 발표용 검출률 표 산출

### PaySim 데이터 도착 후

- **W5.5-#2** PaySim 다운로드 (반나절, 사용자가 수동 다운로드 OR Kaggle API 키 제공)
- **W5.5-#3** 학습 스크립트 (3일)
- **W5.5-#4** 입력 스키마 정합화 (2일)
- **W5.5-#5~#7** multiclass·SMOTE·검출률 회귀 (5일)

### W5.5 완료 후

- **W6.5** 그래프 + 비용 가중 (2주)
- **W7.5** 시계열·운영 신뢰성 (2주)

상세 명세: [`docs/FDS_ROADMAP.md`](FDS_ROADMAP.md)

## 5. 환경·도구 의존성

### PaySim 데이터셋

- **수동**: [kaggle.com/datasets/ealaxi/paysim1](https://www.kaggle.com/datasets/ealaxi/paysim1) → 압축 해제 → `fds-research/data/paysim.csv`
- **자동**: Kaggle API 키 (`~/.kaggle/kaggle.json`) 설치 후 `make paysim-download` (W5.5-#2 산출물)

### 도커 환경

```bash
docker compose up -d  # postgres, redis, kafka, fraud-service, backend, frontend
```

W4 작업으로 Kafka 활성화됨. fraud-service 가 `KAFKA_BOOTSTRAP_SERVERS=kafka:9092` 사용.

### 학습 환경

```bash
cd fds-research
pip install -r requirements.txt  # scikit-learn, xgboost, pandas
python train_paysim.py  # W5.5-#3 산출 후
```

## 6. 진행 상태 확인 명령어

```bash
# 현재 진척률
grep "합계" docs/ROADMAP.md

# 최근 커밋 5개
git log --oneline -5

# 미완료 W5.5/W6.5/W7.5 항목
grep -E "W[567]\.5-#" docs/ROADMAP.md | grep "\[ \]"

# 다음 작업 자동 식별
grep -E "W[567]\.5-#" docs/ROADMAP.md | grep "\[ \]" | head -1
```

## 7. 트러블슈팅

| 증상 | 원인 | 대응 |
|---|---|---|
| `tbd` SHA 미갱신 | 커밋 직후 ROADMAP 업데이트 누락 | `python -c "p='docs/ROADMAP.md'; s=open(p,encoding='utf-8').read(); open(p,'w',encoding='utf-8').write(s.replace('tbd','<sha>'))"` |
| PaySim CSV 미존재 | W5.5-#2 미수행 | `fds-research/data/paysim.csv` 배치 후 재시도 |
| Kafka 연결 실패 | `docker compose ps kafka` 확인, `unhealthy` 면 `docker compose restart kafka` |
| ABE 시크릿 fail-fast | `ENV=production` 인데 `ABE_MASTER_SECRET` 미설정 | 32자+ 시크릿 환경변수 주입 또는 `ENV=development` |

## 8. 참조 문서

- [`docs/ROADMAP.md`](ROADMAP.md) — 전체 92건 단일 트래커
- [`docs/FDS_ROADMAP.md`](FDS_ROADMAP.md) — W5.5/W6.5/W7.5 상세 명세
- [`docs/blog/12_실시간_사기_점수_IF_RF_하이브리드.md`](blog/12_실시간_사기_점수_IF_RF_하이브리드.md) — Track 1~4 원전
- [`docs/blog/13_규칙_엔진.md`](blog/13_규칙_엔진.md) — Track A~D 원전
- [`docs/blog/14_행동_시그널_분석.md`](blog/14_행동_시그널_분석.md) — Track α~ε 원전
- [`docs/blog/perspectives/mlops/04_운영_관측과_향후_과제.md`](blog/perspectives/mlops/04_운영_관측과_향후_과제.md) — 운영 SLO 부록
