# 신용카드 사기 탐지 (캡스톤)

비지도(Isolation Forest)와 지도(Random Forest) 실험을 한 저장소입니다.

## 폴더 구조

| 경로 | 설명 |
|------|------|
| `scripts/creditcard/` | Kaggle `creditcard.csv` — 비지도·하이브리드 실험 |
| `scripts/open/` | `data/open/` — 지도 학습·제출 파일 생성 |
| `scripts/README.md` | **스크립트별 목적·산출물 표** (먼저 읽기 권장) |
| `data/creditcard.csv` | Kaggle 벤치마크 (Time, Amount, V1–V28, Class) |
| `data/open/` | 별도 과제용 CSV (`train`/`val`/`test`, 제출 파일 생성) |
| `docs/` | 보고서 (`FRAUD_DETECTION_REPORT.md`) |
| `outputs/` | 실험 산출 (`creditcard/`, `ieee_cis/` 등 — `outputs/README.md`) |

## 스크립트 (요약)

| 경로 | 내용 |
|------|------|
| `scripts/creditcard/if_unsupervised.py` | 비지도 전체: Part A/B/C + `outputs/creditcard/if_eval_summary.csv` |
| `scripts/creditcard/if_holdout.py` | 비지도 경량: contamination·하위 k%만 |
| `scripts/creditcard/if_demo.py` | 전체 데이터 한 번 fit, 콘솔 요약만 |
| `scripts/creditcard/hybrid_if_rf.py` | IF 점수 + RF 지도 결합 + `outputs/creditcard/hybrid_if_rf_compare.csv` |
| `scripts/open/supervised_rf.py` | `data/open/` 지도 학습 + 제출 CSV |

## 실행

프로젝트 루트에서:

```text
py -3 scripts/creditcard/if_unsupervised.py
py -3 scripts/open/supervised_rf.py
```

의존성: `pandas`, `scikit-learn`.

## 보고서

상세 서술·비즈니스용 요약은 `docs/FRAUD_DETECTION_REPORT.md` 를 참고하세요.
