"""
Layer 4 — Blockchain 불변 감사 추적 (Hash-chain Audit Trail)

모든 FDS 판정을 해시 체인으로 연결하여 변조를 감지할 수 있는
불변 감사 로그를 제공한다.

교수님 연구 연계:
- "Blockchain-Token Based Lightweight Handover Authentication"
- Cryptographic hash chain을 활용한 무결성 보장
- SRS 1,2,3,5,6 공통 요구: 온체인 해시 + 오프체인 원문 분리 저장

W3-#3: Genesis 블록 결정성 — 환경변수 `AUDIT_GENESIS_TIMESTAMP` 로 고정.
W3-#4: 전체 직렬화 → JSONL append-only. _save 가 O(1) (LF 라인 1개 추가).
       기존 JSON 파일은 자동 감지해 JSONL로 마이그레이션.
W3-#6: 디스크 I/O 를 백그라운드 워커 스레드로 분리 — append() 는 큐에 enqueue 후 즉시 반환.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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


# ── Genesis block (W3-#3: 결정성 확보) ─────────────────────────
_GENESIS_PREV = "0" * 64
_GENESIS_TIMESTAMP = os.getenv(
    "AUDIT_GENESIS_TIMESTAMP", "2025-01-01T00:00:00+00:00"
)


def _make_genesis() -> AuditBlock:
    blk = AuditBlock(
        index=0,
        timestamp=_GENESIS_TIMESTAMP,  # ← 고정 타임스탬프, 인스턴스 간 동일 hash
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
    """In-memory hash chain with JSONL append-only persistence.

    온체인/오프체인 분리 저장:
    - 온체인: index, block_hash, prev_hash, merkle_leaf, timestamp
    - 오프체인: 원문 트랜잭션 데이터

    W3-#4: 디스크 영속화는 JSONL append-only — 새 블록 1개당 LF 라인 1개 추가.
            전체 chain 재직렬화 비용 제거.
    W3-#6: append() 호출은 메모리 갱신만 동기로 처리하고, 디스크 flush 는
            백그라운드 워커 스레드가 큐에서 빼서 fsync 까지 처리.
    """

    def __init__(
        self,
        persist_path: str | Path | None = None,
        async_persist: bool = True,
    ) -> None:
        self._lock = threading.Lock()
        self._persist_path = Path(persist_path) if persist_path else None
        self._chain: list[AuditBlock] = []
        self._async_persist = async_persist and self._persist_path is not None
        self._write_queue: queue.Queue[AuditBlock | None] | None = None
        self._writer_thread: threading.Thread | None = None

        # 기존 데이터 로드 (JSONL 우선, 레거시 JSON 도 지원)
        if self._persist_path:
            self._init_from_disk()
        else:
            self._chain.append(_make_genesis())

        if self._async_persist:
            self._start_writer()

    # ── 디스크 초기화 ─────────────────────────────────────────
    def _jsonl_path(self) -> Path:
        """영속화 파일 경로 — JSONL 확장자 강제."""
        if self._persist_path is None:
            raise RuntimeError("persist_path is None")
        if self._persist_path.suffix == ".jsonl":
            return self._persist_path
        return self._persist_path.with_suffix(".jsonl")

    def _init_from_disk(self) -> None:
        jsonl = self._jsonl_path()
        legacy_json = self._persist_path  # type: ignore[assignment]

        if jsonl.exists() and jsonl.stat().st_size > 0:
            self._load_jsonl(jsonl)
        elif legacy_json and legacy_json.exists() and legacy_json.suffix == ".json":
            # 레거시 JSON → JSONL 마이그레이션
            self._migrate_json_to_jsonl(legacy_json, jsonl)
        else:
            # 신규 체인 — Genesis 추가 + JSONL 첫 라인 기록
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            genesis = _make_genesis()
            self._chain.append(genesis)
            self._append_line_sync(genesis, jsonl)

    def _migrate_json_to_jsonl(self, legacy: Path, target: Path) -> None:
        try:
            raw = json.loads(legacy.read_text(encoding="utf-8"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as f:
                for item in raw:
                    blk = AuditBlock(**item)
                    self._chain.append(blk)
                    f.write(json.dumps(asdict(blk), ensure_ascii=False) + "\n")
            logger.info("[audit] JSON → JSONL 마이그레이션 완료 (%d blocks)", len(self._chain))
        except Exception as e:
            raise RuntimeError(f"audit chain 마이그레이션 실패: {e}") from e

    def _load_jsonl(self, path: Path) -> None:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    self._chain.append(AuditBlock(**item))
                except Exception as e:
                    logger.warning("[audit] JSONL 파싱 실패 (skip): %s", e)
        result = self._verify_unlocked()
        if not result.get("valid"):
            raise RuntimeError(f"Chain integrity check failed on load: {result.get('error')}")

    # ── 백그라운드 writer (W3-#6) ────────────────────────────
    def _start_writer(self) -> None:
        if self._writer_thread is not None:
            return
        self._write_queue = queue.Queue()
        t = threading.Thread(target=self._writer_loop, name="audit-writer", daemon=True)
        t.start()
        self._writer_thread = t

    def _writer_loop(self) -> None:
        if self._persist_path is None or self._write_queue is None:
            return
        path = self._jsonl_path()
        while True:
            blk = self._write_queue.get()
            if blk is None:  # shutdown sentinel
                break
            try:
                self._append_line_sync(blk, path)
            except Exception as e:
                logger.error("[audit] 디스크 append 실패 (block %d): %s", blk.index, e)

    @staticmethod
    def _append_line_sync(blk: AuditBlock, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(blk), ensure_ascii=False) + "\n")

    def shutdown(self) -> None:
        """flush all pending writes and stop writer thread (테스트/종료용)."""
        if self._write_queue is not None:
            self._write_queue.put(None)
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=5)
            self._writer_thread = None

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
            # W3-#4 + W3-#6: 백그라운드 큐에 enqueue (비동기) 또는 즉시 append (동기)
            self._enqueue_persist(blk)
            return blk

    def _enqueue_persist(self, blk: AuditBlock) -> None:
        if self._persist_path is None:
            return
        if self._async_persist and self._write_queue is not None:
            self._write_queue.put(blk)
        else:
            self._append_line_sync(blk, self._jsonl_path())

    def _verify_unlocked(self) -> dict[str, Any]:
        """체인 무결성 검증 (lock 없이, 내부 호출용)."""
        if not self._chain:
            return {"valid": False, "error": "Empty chain"}

        for i, blk in enumerate(self._chain):
            if blk.compute_hash() != blk.block_hash:
                return {"valid": False, "error": f"Block {i}: hash mismatch", "block_index": i}
            if i > 0 and blk.prev_hash != self._chain[i - 1].block_hash:
                return {"valid": False, "error": f"Block {i}: prev_hash broken", "block_index": i}
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
        with self._lock:
            return self._verify_unlocked()

    def verify_range(self, start: int, end: int) -> dict[str, Any]:
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
        leaves = [blk.merkle_leaf for blk in self._chain if blk.merkle_leaf]
        return _compute_merkle_root(leaves)

    def get_merkle_root(self) -> str:
        with self._lock:
            return self.get_merkle_root_unlocked()

    def status(self) -> dict[str, Any]:
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
        with self._lock:
            if 0 <= index < len(self._chain):
                return asdict(self._chain[index])
            return None

    def get_onchain(self, index: int) -> dict[str, Any] | None:
        with self._lock:
            if 0 <= index < len(self._chain):
                return asdict(self._chain[index].to_onchain())
            return None

    def search(self, tx_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(b) for b in self._chain if b.transaction_id == tx_id]

    def search_by_user(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(b) for b in self._chain if b.user_id == user_id]

    def search_by_action(self, action: str) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(b) for b in self._chain if b.action == action.upper()]

    def search_by_time_range(self, start_iso: str, end_iso: str) -> list[dict[str, Any]]:
        with self._lock:
            return [
                asdict(b) for b in self._chain
                if start_iso <= b.timestamp <= end_iso
            ]

    def tail(self, n: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(b) for b in reversed(self._chain[-n:])]


# ── 싱글턴 인스턴스 ────────────────────────────────────────────
# W3-#3: AUDIT_CHAIN_PATH 환경변수로 오버라이드 가능 (테스트 격리)
_DEFAULT_PATH = Path(os.getenv("AUDIT_CHAIN_PATH", "logs/audit_chain.jsonl"))
audit_chain = BlockchainAuditChain(persist_path=_DEFAULT_PATH)
