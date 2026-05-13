"""W8-#2 — OSINT/상용 위협 피드 어댑터 추상화.

운영 환경에서는 AbuseIPDB / VirusTotal / 자체 피드 등을 도입. 본 모듈은
어댑터 인터페이스 + Mock 구현 + 신뢰도 가중 합산 API 만 제공.

이미 운영 중인 ``intelligence_store`` 와 통합하는 wiring 은 별도 작업
(W8-#2 후속) 으로 분리 — 본 작업은 인터페이스 정의 + Mock + 신뢰도 가중
합산 알고리즘이 목표.

### 신뢰도 가중

여러 피드가 같은 IP/도메인을 보고할 때 단일 점수 합산:

    combined = 1 - Π(1 - feed_score_i * feed_weight_i)

(naive Bayes 가정 — 피드 간 독립). 운영 단계에서 피드별 historical FP
rate 측정 후 weight 보정.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ThreatReport:
    indicator: str  # IP / 도메인 / hash 등
    score: float    # 0~1 위험도
    source: str     # 피드 이름
    weight: float = 1.0  # 0~1 피드 신뢰도
    details: dict | None = None


class OsintFeedAdapter(ABC):
    """OSINT 피드 통합 인터페이스."""

    name: str = "abstract"
    default_weight: float = 1.0

    @abstractmethod
    def lookup(self, indicator: str) -> ThreatReport | None:
        """단일 indicator 조회. 미확인 시 None."""

    def lookup_many(self, indicators: list[str]) -> list[ThreatReport]:
        out: list[ThreatReport] = []
        for ind in indicators:
            r = self.lookup(ind)
            if r is not None:
                out.append(r)
        return out


class AbuseIPDBAdapter(OsintFeedAdapter):
    """AbuseIPDB API 어댑터 — Mock 구현.

    실제 API 호출 대신 클래스 생성자에 ``mock_db`` 를 주입하면 그 dict 가
    응답으로 사용된다. 운영 시 ``api_key`` 와 ``requests`` 모듈로 교체.
    """

    name = "abuseipdb"
    default_weight = 0.8

    def __init__(
        self,
        *,
        api_key: str | None = None,
        mock_db: dict[str, float] | None = None,
    ) -> None:
        self.api_key = api_key
        self._mock = mock_db or {}

    def lookup(self, indicator: str) -> ThreatReport | None:
        # Mock 분기 (운영 환경에서 API 호출로 교체)
        score = self._mock.get(indicator)
        if score is None:
            return None
        return ThreatReport(
            indicator=indicator,
            score=float(score),
            source=self.name,
            weight=self.default_weight,
            details={"mock": True},
        )


def combine_reports(reports: list[ThreatReport]) -> dict:
    """피드별 점수 → 단일 0~1 위험 점수 (naive Bayes 가정).

    빈 입력 → score=0.0.
    """
    if not reports:
        return {"score": 0.0, "feeds": [], "n": 0}
    product = 1.0
    feed_summary = []
    for r in reports:
        score = max(0.0, min(1.0, float(r.score)))
        weight = max(0.0, min(1.0, float(r.weight)))
        effective = score * weight
        product *= (1.0 - effective)
        feed_summary.append({
            "source": r.source,
            "score": round(score, 4),
            "weight": round(weight, 4),
            "effective": round(effective, 4),
        })
    combined = 1.0 - product
    return {
        "score": round(combined, 4),
        "feeds": feed_summary,
        "n": len(reports),
    }


def lookup_with_adapters(
    adapters: list[OsintFeedAdapter],
    indicator: str,
) -> dict:
    """여러 어댑터 일괄 조회 + 합산."""
    reports: list[ThreatReport] = []
    for a in adapters:
        try:
            r = a.lookup(indicator)
            if r is not None:
                reports.append(r)
        except Exception:
            continue
    return combine_reports(reports)
