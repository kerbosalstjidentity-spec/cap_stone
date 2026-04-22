"""Tests for Layer 4: Blockchain Audit Trail."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.services.blockchain_audit import AuditBlock, BlockchainAuditChain


class TestAuditBlock:
    def test_hash_deterministic(self):
        blk = AuditBlock(
            index=1,
            timestamp="2026-01-01T00:00:00+00:00",
            transaction_id="TX001",
            user_id="U1",
            action="BLOCK",
            score=0.95,
            rule_ids=["AMOUNT_BLOCK"],
            reason_code="V14",
            amount=5_000_000,
            prev_hash="a" * 64,
        )
        h1 = blk.compute_hash()
        h2 = blk.compute_hash()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_different_data_different_hash(self):
        common = dict(
            index=1,
            timestamp="2026-01-01T00:00:00+00:00",
            transaction_id="TX001",
            user_id="U1",
            action="BLOCK",
            score=0.95,
            rule_ids=[],
            reason_code="",
            amount=100,
            prev_hash="a" * 64,
        )
        b1 = AuditBlock(**common)
        b2 = AuditBlock(**{**common, "action": "PASS"})
        assert b1.compute_hash() != b2.compute_hash()


class TestBlockchainAuditChain:
    def _make_chain(self, tmp_dir: str) -> BlockchainAuditChain:
        return BlockchainAuditChain(persist_path=Path(tmp_dir) / "chain.json")

    def test_genesis_created(self):
        with tempfile.TemporaryDirectory() as d:
            chain = self._make_chain(d)
            st = chain.status()
            assert st["chain_length"] == 1
            genesis = chain.get_block(0)
            assert genesis["transaction_id"] == "GENESIS"

    def test_append_and_verify(self):
        with tempfile.TemporaryDirectory() as d:
            chain = self._make_chain(d)
            blk = chain.append(
                transaction_id="TX100",
                user_id="USER_A",
                action="REVIEW",
                score=0.45,
                rule_ids=["TIME_RISK"],
                reason_code="V7",
                amount=800_000,
            )
            assert blk.index == 1
            assert blk.block_hash == blk.compute_hash()

            result = chain.verify()
            assert result["valid"] is True
            assert result["chain_length"] == 2

    def test_multiple_appends(self):
        with tempfile.TemporaryDirectory() as d:
            chain = self._make_chain(d)
            for i in range(5):
                chain.append(
                    transaction_id=f"TX{i}",
                    user_id=f"U{i}",
                    action="PASS",
                    score=0.001,
                    rule_ids=[],
                    amount=1000,
                )
            assert chain.status()["chain_length"] == 6  # genesis + 5
            assert chain.verify()["valid"] is True

    def test_tamper_detection(self):
        with tempfile.TemporaryDirectory() as d:
            chain = self._make_chain(d)
            chain.append(
                transaction_id="TX1", user_id="U1",
                action="PASS", score=0.01, rule_ids=[], amount=100,
            )
            chain.append(
                transaction_id="TX2", user_id="U2",
                action="BLOCK", score=0.99, rule_ids=["AMOUNT_BLOCK"], amount=9_000_000,
            )
            # 변조: 중간 블록의 action을 위조
            chain._chain[1].action = "BLOCK"
            result = chain.verify()
            assert result["valid"] is False
            assert result["block_index"] == 1

    def test_search(self):
        with tempfile.TemporaryDirectory() as d:
            chain = self._make_chain(d)
            chain.append(
                transaction_id="TX_FIND", user_id="U1",
                action="REVIEW", score=0.5, rule_ids=[], amount=500,
            )
            chain.append(
                transaction_id="TX_OTHER", user_id="U2",
                action="PASS", score=0.01, rule_ids=[], amount=100,
            )
            results = chain.search("TX_FIND")
            assert len(results) == 1
            assert results[0]["transaction_id"] == "TX_FIND"

    def test_persistence_and_reload(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "chain.json"
            chain1 = BlockchainAuditChain(persist_path=path)
            chain1.append(
                transaction_id="TX_PERSIST", user_id="U1",
                action="BLOCK", score=0.99, rule_ids=["R1"], amount=10_000,
            )
            hash_before = chain1.status()["latest_hash"]

            # 새 인스턴스로 로드
            chain2 = BlockchainAuditChain(persist_path=path)
            assert chain2.status()["chain_length"] == 2
            assert chain2.status()["latest_hash"] == hash_before
            assert chain2.verify()["valid"] is True

    def test_tail(self):
        with tempfile.TemporaryDirectory() as d:
            chain = self._make_chain(d)
            for i in range(10):
                chain.append(
                    transaction_id=f"TX{i}", user_id="U",
                    action="PASS", score=0.01, rule_ids=[], amount=100,
                )
            recent = chain.tail(3)
            assert len(recent) == 3
            # 최신순 (index 10, 9, 8)
            assert recent[0]["index"] == 10
            assert recent[2]["index"] == 8
