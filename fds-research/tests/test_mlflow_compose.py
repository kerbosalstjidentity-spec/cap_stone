"""W6-#5 — docker-compose.mlflow.yml + CI 워크플로우 정합성 테스트."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_mlflow_compose_exists_and_exposes_5000():
    body = _read("docker-compose.mlflow.yml")
    assert "mlflow" in body.lower()
    assert "5000" in body
    assert "backend-store-uri" in body
    assert "sqlite" in body


def test_ci_workflow_builds_train_image():
    body = _read(".github/workflows/ml-train.yml")
    assert "docker/build-push-action" in body
    assert "fds-research/Dockerfile" in body
    assert "train_paysim.py --help" in body


def test_ci_workflow_runs_pytest_jobs():
    body = _read(".github/workflows/ml-train.yml")
    assert "pytest-fraud" in body
    assert "pytest-backend" in body
    assert "test_bundle_schema" in body
    assert "test_ml_persistence" in body
