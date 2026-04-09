"""
Layer 4 — Blockchain 불변 감사 추적 (Hash-chain Audit Trail)

모든 FDS 판정을 해시 체인으로 연결하여 변조를 감지할 수 있는
불변 감사 로그를 제공한다.

교수님 연구 연계:
- "Blockchain-Token Based Lightweight Handover Authentication"
- Cryptographic hash chain을 활용한 무결성 보장
- SRS 1,2,3,5,6 공통 요구: 온체인 해시 + 오프체인 원문 분리 저장
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class OnChainRecord:
    """온체인에 기록되는 최소 정보 (해시만 저장)."""
    index: int
    block_hash: str
    prev_hash: str
    merkle_leaf: str       # SHA-256(off-chain payload)
    timestamp: str


@dataclass
class OffChainData:
    """오프체인에 저장되는 원문 데이터."""
    index: int
    transaction_id: str
    user_id: str
    action: str
    score: float
    rule_ids: list[str]
    reason_code: str
    amount: float
    timestamp: str


@dataclass
class AuditBlock:
    """해시 체인의 단일 블록 (온체인+오프체인 통합 뷰)."""

    index: int
    timestamp: str
    transaction_id: str
    user_id: str
    action: str                     # PASS | SOFT_REVIEW | REVIEW | BLOCK
    score: float
    rule_ids: list[str]
    reason_code: str
    amount: float
    prev_hash: str
    block_hash: str = ""
    merkle_leaf: str = ""           # SHA-256(off-chain payload)

    def compute_hash(self) -> str:
        payload = json.dumps(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "transaction_id": self.transaction_id,
                "user_id": self.user_id,
                "action": self.action,
                "score": round(self.score, 6),
                "rule_ids": sorted(self.rule_ids),
                "amount": self.amount,
                "prev_hash": self.prev_hash,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def compute_merkle_leaf(self) -> str:
        """오프체인 원문 데이터의 SHA-256 해시 (Merkle leaf)."""
        off_chain = {
            "transaction_id": self.transaction_id,
            "user_id": self.user_id,
            "action": self.action,
            "score": round(self.score, 6),
            "rule_ids": sorted(self.rule_ids),
            "reason_code": self.reason_code,
            "amount": self.amount,
            "timestamp": self.timestamp,
        }
        payload = json.dumps(off_chain, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_onchain(self) -> OnChainRecord:
        return OnChainRecord(
            index=self.index,
            block_hash=self.block_hash,
            prev_hash=self.prev_hash,
            merkle_leaf=self.merkle_leaf,
            timestamp=self.timestamp,
        )

    def to_offchain(self) -> OffChainData:
        return OffChainData(
            index=self.index,
            transaction_id=self.transaction_id,
            user_id=self.user_id,
            action=self.action,
            score=self.score,
            rule_ids=self.rule_ids,
            reason_code=self.reason_code,
            amount=self.amount,
            timestamp=self.timestamp,
        )


# ── Merkle Root 계산 ───────────────────────────────────────────

def _compute_merkle_root(leaves: list[str]) -> str:
    """Merkle root를 계산한다."""
    if not leaves:
        return "0" * 64
    if len(leaves) == 1:
        return leaves[0]

    nodes = list(leaves)
    while len(nodes) > 1:
        if len(nodes) % 2 == 1:
            nodes.append(nodes[-1])  # 홀수면 마지막 노드 복제
        next_level = []
        for i in range(0, len(nodes), 2):
            combined = nodes[i] + nodes[i + 1]
            next_level.append(hashlib.sha256(combined.encode()).hexdigest())
        nodes = next_level
    return nodes[0]


# ── Genesis block ──────────────────────────────────────────────
_GENESIS_PREV = "0" * 64


def _make_genesis() -> AuditBlock:
    blk = AuditBlock(
        index=0,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        transaction_id="GENESIS",
        user_id="SYSTEM",
        action="INIT",
        score=0.0,
        rule_ids=[],
        reason_code="Chain initialised",
        amount=0.0,
        prev_hash=_GENESIS_PREV,
    )
    blk.merkle_leaf = blk.compute_merkle_leaf()
    blk.block_hash = blk.compute_hash()
    return blk


# ── BlockchainAuditChain ──────────────────────────────────────
class BlockchainAuditChain:
    """In-memory hash chain with optional JSON persistence.

    온체인/오프체인 분리 저장:
    - 온체인: index, block_hash, prev_hash, merkle_leaf, timestamp
    - 오프체인: 원문 트랜잭션 데이터
    """

    def __init__(self, persist_path: str | Path | None = None) -> None:
        self._lock = threading.Lock()
        self._persist_path = Path(persist_path) if persist_path else None
        self._chain: list[AuditBlock] = []

        if self._persist_path and self._persist_path.exists():
            self._load()
        else:
            self._chain.append(_make_genesis())
            self._save()

    # ── Public API ─────────────────────────────────────────────

    def append(
        self,
        transaction_id: str,
        user_id: str,
        action: str,
        score: float,
        rule_ids: list[str],
        reason_code: str = "",
        amount: float = 0.0,
    ) -> AuditBlock:
        """새 블록을 체인에 추가하고 반환한다."""
        with self._lock:
            prev = self._chain[-1]
            blk = AuditBlock(
                index=prev.index + 1,
                timestamp=datetime.now(tz=timezone.utc).isoformat(),
                transaction_id=transaction_id,
                user_id=user_id,
                action=action,
                score=score,
                rule_ids=rule_ids,
                reason_code=reason_code,
                amount=amount,
                prev_hash=prev.block_hash,
            )
            blk.merkle_leaf = blk.compute_merkle_leaf()
            blk.block_hash = blk.compute_hash()
            self._chain.append(blk)
            self._save()
            return blk

    def _verify_unlocked(self) -> dict[str, Any]:
        """체인 무결성 검증 (lock 없이, 내부 호출용)."""
        if not self._chain:
            return {"valid": False, "error": "Empty chain"}

        for i, blk in enumerate(self._chain):
            if blk.compute_hash() != blk.block_hash:
                return {
                    "valid": False,
                    "error": f"Block {i}: hash mismatch",
                    "block_index": i,
                }
            if i > 0 and blk.prev_hash != self._chain[i - 1].block_hash:
                return {
                    "valid": False,
                    "error": f"Block {i}: prev_hash broken",
                    "block_index": i,
                }
            # Merkle leaf 검증
            if blk.merkle_leaf and blk.compute_merkle_leaf() != blk.merkle_leaf:
                return {
                    "valid": False,
                    "error": f"Block {i}: merkle_leaf mismatch (off-chain tampered)",
                    "block_index": i,
                }

        return {
            "valid": True,
            "chain_length": len(self._chain),
            "latest_hash": self._chain[-1].block_hash,
            "merkle_root": self.get_merkle_root_unlocked(),
        }

    def verify(self) -> dict[str, Any]:
        """전체 체인의 무결성을 검증한다."""
        with self._lock:
            return self._verify_unlocked()

    def verify_range(self, start: int, end: int) -> dict[str, Any]:
        """특정 범위의 블록 무결성 검증."""
        with self._lock:
            if start < 0 or end >= len(self._chain) or start > end:
                return {"valid": False, "error": "Invalid range"}
            for i in range(start, end + 1):
                blk = self._chain[i]
                if blk.compute_hash() != blk.block_hash:
                    return {"valid": False, "error": f"Block {i}: hash mismatch", "block_index": i}
                if i > 0 and blk.prev_hash != self._chain[i - 1].block_hash:
                    return {"valid": False, "error": f"Block {i}: prev_hash broken", "block_index": i}
            return {"valid": True, "range": [start, end], "blocks_verified": end - start + 1}

    def verify_offchain_integrity(self, index: int) -> dict[str, Any]:
        """특정 블록의 오프체인 데이터 무결성 검증."""
        with self._lock:
            if not (0 <= index < len(self._chain)):
                return {"valid": False, "error": "Block not found"}
            blk = self._chain[index]
            expected = blk.compute_merkle_leaf()
            actual = blk.merkle_leaf
            return {
                "valid": expected == actual,
                "index": index,
                "expected_merkle_leaf": expected,
                "stored_merkle_leaf": actual,
            }

    def get_merkle_root_unlocked(self) -> str:
        """Merkle root 계산 (lock 없이)."""
        leaves = [blk.merkle_leaf for blk in self._chain if blk.merkle_leaf]
        return _compute_merkle_root(leaves)

    def get_merkle_root(self) -> str:
        """Merkle root 계산."""
        with self._lock:
            return self.get_merkle_root_unlocked()

    def status(self) -> dict[str, Any]:
        """체인 상태 요약."""
        with self._lock:
            if not self._chain:
                return {"chain_length": 0}
            latest = self._chain[-1]
            return {
                "chain_length": len(self._chain),
                "latest_index": latest.index,
                "latest_hash": latest.block_hash,
                "latest_timestamp": latest.timestamp,
                "merkle_root": self.get_merkle_root_unlocked(),
            }

    def stats(self) -> dict[str, Any]:
        """체인 통계: 액션별 카운트, 블록 수, 평균 점수."""
        with self._lock:
            action_counts: dict[str, int] = {}
            total_score = 0.0
            for blk in self._chain:
                action_counts[blk.action] = action_counts.get(blk.action, 0) + 1
                total_score += blk.score
            n = len(self._chain)
            return {
                "total_blocks": n,
                "action_counts": action_counts,
                "avg_score": round(total_score / n, 4) if n else 0.0,
                "merkle_root": self.get_merkle_root_unlocked(),
            }

    def get_block(self, index: int) -> dict[str, Any] | None:
        """인덱스로 블록 조회."""
        with self._lock:
            if 0 <= index < len(self._chain):
                return asdict(self._chain[index])
            return None

    def get_onchain(self, index: int) -> dict[str, Any] | None:
        """온체인 레코드만 조회."""
        with self._lock:
            if 0 <= index < len(self._chain):
                return asdict(self._chain[index].to_onchain())
            return None

    def search(self, tx_id: str) -> list[dict[str, Any]]:
        """거래 ID로 블록 검색."""
        with self._lock:
            return [asdict(b) for b in self._chain if b.transaction_id == tx_id]

    def search_by_user(self, user_id: str) -> list[dict[str, Any]]:
        """사용자 ID로 블록 검색."""
        with self._lock:
            return [asdict(b) for b in self._chain if b.user_id == user_id]

    def search_by_action(self, action: str) -> list[dict[str, Any]]:
        """액션 타입으로 블록 검색."""
        with self._lock:
            return [asdict(b) for b in self._chain if b.action == action.upper()]

    def search_by_time_range(self, start_iso: str, end_iso: str) -> list[dict[str, Any]]:
        """시간 범위로 블록 검색."""
        with self._lock:
            return [
                asdict(b) for b in self._chain
                if start_iso <= b.timestamp <= end_iso
            ]

    def tail(self, n: int = 20) -> list[dict[str, Any]]:
        """최근 n개 블록 반환 (최신순)."""
        with self._lock:
            return [asdict(b) for b in reversed(self._chain[-n:])]

    # ── Persistence ────────────────────────────────────────────

    def _save(self) -> None:
        if self._persist_path is None:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(b) for b in self._chain]
        tmp = self._persist_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._persist_path)

    def _load(self) -> None:
        raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
        self._chain = []
        for item in raw:
            blk = AuditBlock(**item)
            self._chain.append(blk)
        # 로드 후 무결성 체크 (lock 이미 없는 상태이므로 _verify_unlocked 사용)
        result = self._verify_unlocked()
        if not result["valid"]:
            raise RuntimeError(f"Chain integrity check failed on load: {result['error']}")


# ── 싱글턴 인스턴스 ────────────────────────────────────────────
_DEFAULT_PATH = Path("logs/audit_chain.json")
audit_chain = BlockchainAuditChain(persist_path=_DEFAULT_PATH)
