"""W9-#13 — ABAC 시뮬레이션 모듈 분리(app.research.abac_simulation) 테스트."""
from __future__ import annotations


def test_research_module_owns_classes():
    from app.research.abac_simulation import BidirectionalPolicy, CPABE_Simulator
    assert BidirectionalPolicy.__module__ == "app.research.abac_simulation"
    assert CPABE_Simulator.__module__ == "app.research.abac_simulation"


def test_abe_engine_alias_keeps_compat():
    from app.services.abe_engine import BidirectionalPolicy, CPABE_Simulator
    # alias 도 동일 클래스 객체를 참조해야 함
    from app.research.abac_simulation import (
        BidirectionalPolicy as RB,
        CPABE_Simulator as RS,
    )
    assert BidirectionalPolicy is RB
    assert CPABE_Simulator is RS


def test_bidirectional_policy_basic_flow():
    from app.research.abac_simulation import BidirectionalPolicy
    p = BidirectionalPolicy(
        resource="POST /v1/score",
        no_write_structure="role:guest",
        normal_access_structure="role:admin OR role:fraud_analyst",
    )
    assert p.can_read({"role:admin"}) is True
    assert p.can_write({"role:admin"}) is True
    assert p.can_write({"role:guest"}) is False


def test_cpabe_simulator_full_flow():
    from app.research.abac_simulation import CPABE_Simulator
    sim = CPABE_Simulator()
    sim.setup()
    sim.keygen("u1", ["role:admin", "dept:risk"])
    ct = sim.encrypt("secret", "role:admin AND dept:risk")
    res = sim.decrypt(ct, "u1", {"role:admin", "dept:risk"}, "role:admin AND dept:risk")
    assert res["success"] is True
    res2 = sim.decrypt(ct, "u1", {"role:admin"}, "role:admin AND dept:risk")
    assert res2["success"] is False
