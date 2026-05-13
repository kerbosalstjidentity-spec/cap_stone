# ROADMAP ↔ 블로그 마커 커버리지 (W10-#3)

## 목적

`docs/ROADMAP.md` 에 완료(`- [x]`)된 모든 작업이 해당 출처 블로그 글의 "향후 과제 / ⑤ 설계 포인트" 섹션에 `(✅ ROADMAP W?-#? — …)` 한 줄 마커로 회수되었는지 추적.

본 문서가 운영 단계의 단일 참조로, 이후 신규 작업 완료 시 본 표만 갱신하면 된다.

## 커버리지 원칙

| 분류 | 마커 정책 |
|---|---|
| 블로그 ⑤절에서 명시적으로 짚힌 항목 | **반드시** 해당 줄 끝에 마커 추가 |
| Quick wins (W9) — 별도 ⑤절 항목이 없는 경미한 버그 | ROADMAP 변경이력만으로 충분, 블로그 미기재 허용 |
| 신설 스프린트 (W5.5/W6.5/W7.5) | 12/13/14 본문 또는 perspectives 의 도메인 확장 로드맵에 일괄 기재 |
| 거버넌스/문서 (W8-#7) | 별도 `docs/kpi_ml_mapping.md` 문서가 정본 |

## 현재 커버리지 (2026-05-10)

- 완료 작업: 100/103 (97% — W10-#1/#2/#3/#4/#5 자체 진행 중)
- 블로그 마커 회수: 78+/100 (Quick wins 제외 시 거의 100%)
- Quick wins(W9) 16건 중 블로그 마커 누락 12건 — 의도적, 본 정책 표 1행 참조

## 자동 감사 스크립트

```bash
python -c "
import re
from pathlib import Path
roadmap = Path('docs/ROADMAP.md').read_text(encoding='utf-8')
done = set(re.findall(r'\[x\]\s+\*\*(W[0-9.]+-#[0-9]+)\*\*', roadmap))
mark = set()
for p in Path('docs/blog').rglob('*.md'):
    body = p.read_text(encoding='utf-8')
    mark |= set(re.findall(r'ROADMAP\s+(W[0-9.]+-#[0-9]+)', body))
print('missing:', sorted(done - mark))
"
```

## 책임자 표기

- 본 문서 갱신 책임: 작업 완료 시 PR 작성자
- 정기 감사: 주 1회 (다음 회의 전)

## 변경 이력

- 2026-05-10 W10-#3 — 초안 + 정책 표 작성, 자동 감사 스크립트 임베드
