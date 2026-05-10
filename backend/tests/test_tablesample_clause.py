"""W6-#8 — ORDER BY random() → TABLESAMPLE BERNOULLI 폴백 로직 테스트."""
from __future__ import annotations

from app.ml.trainer import _random_sample_clause


def test_no_postgres_returns_none(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///foo.db")
    monkeypatch.delenv("DB_URL", raising=False)
    monkeypatch.delenv("ML_TABLESAMPLE_DISABLE", raising=False)
    assert _random_sample_clause("transactions", 5000, 1_000_000) is None


def test_postgres_returns_clause(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pw@host/db")
    monkeypatch.delenv("ML_TABLESAMPLE_DISABLE", raising=False)
    out = _random_sample_clause("transactions", 5000, 1_000_000)
    assert out is not None
    sql = str(out)
    assert "transactions" in sql
    assert "TABLESAMPLE BERNOULLI" in sql


def test_small_table_returns_none(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://h/d")
    out = _random_sample_clause("transactions", 5000, 4000)  # 표본 ≥ 전체
    assert out is None


def test_disable_env_returns_none(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://h/d")
    monkeypatch.setenv("ML_TABLESAMPLE_DISABLE", "1")
    assert _random_sample_clause("transactions", 5000, 1_000_000) is None


def test_pct_clipped_within_range(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://h/d")
    monkeypatch.delenv("ML_TABLESAMPLE_DISABLE", raising=False)
    # target=5000, total=10M → 0.05% * 2.5 = 0.125%, lower clip 0.1
    out = _random_sample_clause("t", 5000, 10_000_000)
    assert out is not None and "BERNOULLI(0.1" in str(out)
    # target=5000, total=20K → 25% * 2.5 = 62.5% → upper clip 50%
    out2 = _random_sample_clause("t", 5000, 20_000)
    assert out2 is not None and "BERNOULLI(50" in str(out2)
