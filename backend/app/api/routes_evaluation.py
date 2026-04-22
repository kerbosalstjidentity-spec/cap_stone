"""SRS 검증 대시보드 API — 벤치마크, 위협 테스트, 컴플라이언스.

fds_scripts/evaluation_suite.py의 함수를 API로 래핑하여
프론트엔드에서 직접 실행·조회할 수 있게 한다.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter

# fds_scripts를 import path에 추가
_fds_dir = str(Path(__file__).resolve().parent.parent.parent.parent / "fds_scripts")
if _fds_dir not in sys.path:
    sys.path.insert(0, _fds_dir)

from evaluation_suite import (  # noqa: E402
    benchmark_abe_vs_standard,
    benchmark_blockchain_vs_central,
    benchmark_encryption_hybrid,
    benchmark_fgac_vs_cgac,
    generate_compliance_checklist,
    test_attribute_forgery_defense,
    test_insider_threat_defense,
    test_mitm_defense,
    test_replay_attack_defense,
)

router = APIRouter(prefix="/v1/evaluation", tags=["evaluation"])


@router.get("/benchmarks")
async def get_benchmarks() -> dict[str, Any]:
    """4종 성능 벤치마크 실행 (블록체인 vs 중앙, FGAC vs CGAC 등)."""
    return {
        "benchmarks": {
            "blockchain_vs_central": benchmark_blockchain_vs_central(),
            "fgac_vs_cgac": benchmark_fgac_vs_cgac(),
            "abe_vs_oeep": benchmark_abe_vs_standard(),
            "encryption_hybrid": benchmark_encryption_hybrid(),
        }
    }


@router.get("/threats")
async def get_threat_tests() -> dict[str, Any]:
    """4종 위협 시나리오 테스트 실행."""
    threats = {
        "replay_attack": test_replay_attack_defense(),
        "insider_threat": test_insider_threat_defense(),
        "attribute_forgery": test_attribute_forgery_defense(),
        "mitm_attack": test_mitm_defense(),
    }
    all_passed = all(t["status"] == "PASS" for t in threats.values())
    return {"threats": threats, "all_passed": all_passed}


@router.get("/compliance")
async def get_compliance() -> dict[str, Any]:
    """SRS 1-11 규제 준수 체크리스트."""
    return generate_compliance_checklist()


@router.get("/full")
async def get_full_evaluation() -> dict[str, Any]:
    """벤치마크 + 위협 + 컴플라이언스 전체 실행."""
    benchmarks = {
        "blockchain_vs_central": benchmark_blockchain_vs_central(),
        "fgac_vs_cgac": benchmark_fgac_vs_cgac(),
        "abe_vs_oeep": benchmark_abe_vs_standard(),
        "encryption_hybrid": benchmark_encryption_hybrid(),
    }
    threats = {
        "replay_attack": test_replay_attack_defense(),
        "insider_threat": test_insider_threat_defense(),
        "attribute_forgery": test_attribute_forgery_defense(),
        "mitm_attack": test_mitm_defense(),
    }
    compliance = generate_compliance_checklist()
    all_passed = all(t["status"] == "PASS" for t in threats.values())
    return {
        "benchmarks": benchmarks,
        "threats": threats,
        "all_threats_passed": all_passed,
        "compliance": compliance,
    }
