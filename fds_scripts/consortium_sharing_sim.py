"""
FDS 컨소시엄 정보 공유 시뮬레이션.

SRS 9 FR-06 (KP-ABE 일대다 이상거래 패턴 공유):
- KP-ABE 기반 1:N 금융 데이터 공유 프로토콜
- 속성 블룸필터(ABF) 기반 클라우드 매칭

SRS 11 FR-07 (HA-KP-ABE vs ABF 비교):
- Match Test vs ABF+KGroup 성능 비교
- 마이데이터/UBI/FDS 시나리오별 적합성 평가

교수님 연구 연계:
- "KP-ABE and Attribute Bloom Filter based Data Sharing" (TDSC)
- "HA-KP-ABE vs ABF Comparison" (TIFS)
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── KP-ABE 시뮬레이션 ─────────────────────────────────────────

@dataclass
class KPABEKey:
    """KP-ABE 사용자 비밀키."""
    user_id: str
    access_policy: str              # "bank:A AND tier:premium"
    key_hash: str = ""

    def __post_init__(self):
        if not self.key_hash:
            self.key_hash = hashlib.sha256(
                f"{self.user_id}:{self.access_policy}".encode()
            ).hexdigest()[:16]


@dataclass
class KPABECiphertext:
    """KP-ABE 암호문 — 속성 집합에 묶임."""
    data_id: str
    attributes: dict[str, str]      # {"bank": "A", "type": "fraud_pattern", ...}
    encrypted_data: str             # 시뮬레이션: 해시화된 원문
    timestamp: float = 0.0


class KPABEProtocol:
    """KP-ABE 기반 1:N 이상거래 패턴 공유 프로토콜."""

    def __init__(self, master_secret: str = "kpabe-master-2026") -> None:
        self._master_secret = master_secret

    def encrypt(self, data: dict[str, Any], attributes: dict[str, str]) -> KPABECiphertext:
        """데이터를 속성 집합에 묶어 암호화."""
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
        encrypted = hashlib.sha256(
            f"{self._master_secret}:{raw}".encode()
        ).hexdigest()
        return KPABECiphertext(
            data_id=f"CT-{hashlib.md5(raw.encode()).hexdigest()[:8]}",
            attributes=attributes,
            encrypted_data=encrypted,
            timestamp=time.time(),
        )

    def keygen(self, user_id: str, access_policy: str) -> KPABEKey:
        """사용자 접근 정책에 대한 비밀키 생성."""
        return KPABEKey(user_id=user_id, access_policy=access_policy)

    def decrypt(self, ct: KPABECiphertext, key: KPABEKey) -> bool:
        """키의 정책이 암호문의 속성을 만족하는지 확인 후 복호화."""
        return self._policy_match(key.access_policy, ct.attributes)

    def _policy_match(self, policy: str, attributes: dict[str, str]) -> bool:
        """정책 문자열이 속성을 만족하는지 평가."""
        # 간단한 AND/OR 파서
        expr = policy
        for key, value in attributes.items():
            expr = expr.replace(f"{key}:{value}", "True")
        # 남은 key:value 토큰은 False
        import re
        expr = re.sub(r"\w+:\w+", "False", expr)
        expr = expr.replace("AND", "and").replace("OR", "or")
        try:
            return bool(eval(expr))  # noqa: S307
        except Exception:
            return False


# ── Attribute Bloom Filter (ABF) ──────────────────────────────

class AttributeBloomFilter:
    """속성 블룸필터 — 속성 매칭을 위한 확률적 자료구조.

    SRS 9, 11: 클라우드에서 데이터 소유자와 요청자의 속성 매칭.
    """

    def __init__(self, size: int = 1024, num_hashes: int = 5) -> None:
        self.size = size
        self.num_hashes = num_hashes
        self.bit_array = [0] * size
        self._items_count = 0

    def _hash_positions(self, item: str) -> list[int]:
        positions = []
        for i in range(self.num_hashes):
            h = hashlib.sha256(f"{item}:{i}".encode()).hexdigest()
            positions.append(int(h, 16) % self.size)
        return positions

    def add(self, item: str) -> None:
        """속성을 블룸필터에 추가."""
        for pos in self._hash_positions(item):
            self.bit_array[pos] = 1
        self._items_count += 1

    def add_attributes(self, attributes: dict[str, str]) -> None:
        """속성 집합을 블룸필터에 추가."""
        for k, v in attributes.items():
            self.add(f"{k}:{v}")

    def contains(self, item: str) -> bool:
        """속성이 블룸필터에 포함되는지 확인 (확률적)."""
        return all(self.bit_array[pos] == 1 for pos in self._hash_positions(item))

    def match_attributes(self, required: dict[str, str]) -> bool:
        """필요 속성이 모두 블룸필터에 존재하는지 확인."""
        return all(self.contains(f"{k}:{v}") for k, v in required.items())

    @property
    def false_positive_rate(self) -> float:
        """이론적 false positive 확률."""
        if self._items_count == 0:
            return 0.0
        return (1 - math.exp(-self.num_hashes * self._items_count / self.size)) ** self.num_hashes


# ── KGroup (Key Group) 매칭 ───────────────────────────────────

class KGroupMatcher:
    """KGroup 기반 매칭 — ABF와 결합하여 다대다 속성 매칭.

    SRS 11: ABF + KGroup 조합으로 효율적 다자간 데이터 공유.
    """

    def __init__(self) -> None:
        self._groups: dict[str, list[str]] = {}  # group_name → [user_ids]

    def create_group(self, group_name: str, members: list[str]) -> None:
        self._groups[group_name] = members

    def match(self, user_id: str, target_group: str) -> bool:
        return user_id in self._groups.get(target_group, [])

    def list_groups(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._groups.items()}


# ── HA-KP-ABE vs ABF 비교 시뮬레이션 (SRS 11) ────────────────

@dataclass
class SharingScenario:
    """공유 시나리오."""
    name: str
    num_data_owners: int
    num_requesters: int
    num_attributes: int
    avg_policy_complexity: int      # AND/OR 노드 수


def run_comparison(
    scenarios: list[SharingScenario] | None = None,
    n_trials: int = 100,
) -> dict[str, Any]:
    """HA-KP-ABE Match Test vs ABF+KGroup 성능 비교.

    SRS 11 NFR-01: 매칭 속도, 정확도, 확장성 비교.
    """
    if scenarios is None:
        scenarios = [
            SharingScenario("마이데이터", 50, 10, 8, 3),
            SharingScenario("UBI (사용량기반보험)", 200, 5, 12, 5),
            SharingScenario("FDS (이상거래탐지)", 500, 20, 15, 7),
        ]

    kpabe = KPABEProtocol()
    results = {"scenarios": []}

    for scenario in scenarios:
        print(f"\n=== 시나리오: {scenario.name} ===")
        print(f"  데이터 소유자: {scenario.num_data_owners}, 요청자: {scenario.num_requesters}")

        # 데이터 준비
        attr_keys = [f"attr_{i}" for i in range(scenario.num_attributes)]
        attr_values = ["A", "B", "C", "D"]

        # 소유자별 데이터 + 속성
        owners_data = []
        for i in range(scenario.num_data_owners):
            attrs = {k: random.choice(attr_values) for k in attr_keys[:random.randint(3, scenario.num_attributes)]}
            owners_data.append(attrs)

        # HA-KP-ABE Match Test 성능
        t0 = time.perf_counter()
        kpabe_matches = 0
        for _ in range(n_trials):
            for owner_attrs in owners_data[:min(50, len(owners_data))]:
                # 간단한 정책 매칭 시뮬레이션
                policy_parts = [f"{k}:{v}" for k, v in list(owner_attrs.items())[:scenario.avg_policy_complexity]]
                policy = " AND ".join(policy_parts)
                key = kpabe.keygen(f"R-{random.randint(0, scenario.num_requesters)}", policy)
                ct = kpabe.encrypt({"pattern": "test"}, owner_attrs)
                if kpabe.decrypt(ct, key):
                    kpabe_matches += 1
        kpabe_time = (time.perf_counter() - t0) * 1000

        # ABF+KGroup 성능
        t0 = time.perf_counter()
        abf_matches = 0
        abf_false_positives = 0
        for _ in range(n_trials):
            for owner_attrs in owners_data[:min(50, len(owners_data))]:
                abf = AttributeBloomFilter(size=512, num_hashes=3)
                abf.add_attributes(owner_attrs)
                # 요청자 속성으로 매칭
                required = {k: v for k, v in list(owner_attrs.items())[:scenario.avg_policy_complexity]}
                if abf.match_attributes(required):
                    abf_matches += 1
        abf_time = (time.perf_counter() - t0) * 1000

        scenario_result = {
            "scenario": scenario.name,
            "kpabe": {
                "time_ms": round(kpabe_time, 2),
                "matches": kpabe_matches,
                "avg_time_per_match_us": round(kpabe_time * 1000 / max(1, n_trials * min(50, len(owners_data))), 2),
            },
            "abf_kgroup": {
                "time_ms": round(abf_time, 2),
                "matches": abf_matches,
                "avg_time_per_match_us": round(abf_time * 1000 / max(1, n_trials * min(50, len(owners_data))), 2),
                "theoretical_fpr": round(
                    AttributeBloomFilter(512, 3).false_positive_rate, 6
                ),
            },
            "comparison": {
                "speed_ratio": round(kpabe_time / max(0.001, abf_time), 2),
                "recommendation": (
                    "ABF+KGroup 권장 (속도 우위)" if kpabe_time > abf_time
                    else "HA-KP-ABE 권장 (정확도 우위)"
                ),
            },
        }
        results["scenarios"].append(scenario_result)

        print(f"  HA-KP-ABE: {kpabe_time:.1f}ms ({kpabe_matches} matches)")
        print(f"  ABF+KGroup: {abf_time:.1f}ms ({abf_matches} matches)")
        print(f"  속도 비율: {scenario_result['comparison']['speed_ratio']}x")
        print(f"  추천: {scenario_result['comparison']['recommendation']}")

    return results


# ── CLI 실행 ──────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("  FDS 컨소시엄 정보 공유 시뮬레이션")
    print("  SRS 9 (KP-ABE + ABF) / SRS 11 (HA-KP-ABE vs ABF)")
    print("=" * 70)

    n_trials = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    results = run_comparison(n_trials=n_trials)

    # 결과 저장
    out_path = Path("outputs/fds/consortium_sharing_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n결과 저장: {out_path}")
