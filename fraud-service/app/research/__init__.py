"""W9-#13 — ABAC/CP-ABE 시뮬레이션 (학술 데모용).

운영 평가 경로(scoring, rule_engine, policy_merge, abe_engine 핵심 5개 룰)와
별도로 SRS 발표 데모용 BidirectionalPolicy / CPABE_Simulator 를 분리 보관.

신규 코드는 ``app.research.abac_simulation`` 에서 import. 기존 코드를 깨지
않기 위해 ``app.services.abe_engine`` 에 deprecation alias 가 잠시 유지됨.
"""
from app.research.abac_simulation import BidirectionalPolicy, CPABE_Simulator

__all__ = ["BidirectionalPolicy", "CPABE_Simulator"]
