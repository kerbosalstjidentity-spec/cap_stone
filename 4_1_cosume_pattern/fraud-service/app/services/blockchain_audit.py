"""
Layer 4 — Blockchain 불변 감사 추적 (Hash-chain Audit Trail)

모든 FDS 판정을 해시 체인으로 연결하여 변조를 감지할 수 있는
불변 감사 로그를 제공한다.

교수님 연구 연계:
- "Blockchain-Token Based Lightweight Handover Authentication"
- Cryptographic hash chain을 활용한 무결성 보장
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
class AuditBlock:
    """해시 체인의 단일 블록."""

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
    blk.block_hash = blk.compute_hash()
    return blk


# ── BlockchainAuditChain ──────────────────────────────────────
class BlockchainAuditChain:
    """In-memory hash chain with optional JSON persistence."""

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

        return {
            "valid": True,
            "chain_length": len(self._chain),
            "latest_hash": self._chain[-1].block_hash,
        }

    def verify(self) -> dict[str, Any]:
        """전체 체인의 무결성을 검증한다."""
        with self._lock:
            return self._verify_unlocked()

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
            }

    def get_block(self, index: int) -> dict[str, Any] | None:
        """인덱스로 블록 조회."""
        with self._lock:
            if 0 <= index < len(self._chain):
                return asdict(self._chain[index])
            return None

    def search(self, tx_id: str) -> list[dict[str, Any]]:
        """거래 ID로 블록 검색."""
        with self._lock:
            return [asdict(b) for b in self._chain if b.transaction_id == tx_id]

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
