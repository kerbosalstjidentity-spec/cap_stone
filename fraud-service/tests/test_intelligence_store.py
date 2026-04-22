"""Tests for Layer 5: Intelligence Store."""
from app.services.intelligence_store import IntelligenceStore


class TestIntelligenceStore:
    def _make_store(self) -> IntelligenceStore:
        return IntelligenceStore()

    def test_publish(self):
        store = self._make_store()
        entry = store.publish(
            publisher_institution="bank_a",
            pattern_type="BLACKLIST",
            summary="Suspicious account hashes",
            access_policy="institution:* AND role:analyst",
            detail={"account_hashes": ["abc123", "def456"]},
            tags=["accounts"],
        )
        assert entry.entry_id == "INTEL-000001"
        assert store.count() == 1

    def test_query_with_access(self):
        store = self._make_store()
        store.publish(
            publisher_institution="bank_a",
            pattern_type="PATTERN",
            summary="High-value fraud pattern",
            access_policy="role:analyst AND clearance:medium",
            detail={"pattern": "rapid small transactions followed by large withdrawal"},
        )
        results = store.query(user_attrs={"role:analyst", "clearance:medium"})
        assert len(results) == 1
        assert results[0]["has_access"] is True
        assert isinstance(results[0]["detail"], dict)

    def test_query_without_access(self):
        store = self._make_store()
        store.publish(
            publisher_institution="bank_a",
            pattern_type="PATTERN",
            summary="Confidential pattern",
            access_policy="role:admin AND clearance:high",
            detail={"secret": "internal data"},
        )
        results = store.query(user_attrs={"role:viewer"})
        assert len(results) == 1
        assert results[0]["has_access"] is False
        assert "ENCRYPTED" in str(results[0]["detail"])

    def test_filter_by_type(self):
        store = self._make_store()
        store.publish("bank_a", "BLACKLIST", "bl", "role:analyst", {})
        store.publish("bank_b", "PATTERN", "pt", "role:analyst", {})
        store.publish("bank_a", "METRIC", "mt", "role:analyst", {})

        results = store.query({"role:analyst"}, pattern_type="PATTERN")
        assert len(results) == 1
        assert results[0]["pattern_type"] == "PATTERN"

    def test_filter_by_tag(self):
        store = self._make_store()
        store.publish("bank_a", "PATTERN", "p1", "role:analyst", {}, tags=["velocity"])
        store.publish("bank_b", "PATTERN", "p2", "role:analyst", {}, tags=["amount"])

        results = store.query({"role:analyst"}, tag="velocity")
        assert len(results) == 1
        assert "velocity" in results[0]["tags"]

    def test_mixed_access(self):
        store = self._make_store()
        store.publish("bank_a", "PATTERN", "public-ish", "role:analyst", {"data": 1})
        store.publish("bank_b", "SIGNATURE", "restricted", "role:admin AND clearance:high", {"data": 2})

        results = store.query({"role:analyst"})
        assert len(results) == 2
        accessible = [r for r in results if r["has_access"]]
        assert len(accessible) == 1
        assert accessible[0]["pattern_type"] == "PATTERN"
