"""W6-#6 — 학습 컨테이너 Dockerfile 정합성 (정적 검증).

도커 데몬 없이 파일 자체의 필수 라인만 점검.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_dockerfile_uses_python_311_slim():
    body = _read("Dockerfile")
    assert "FROM python:3.11" in body
    assert "slim" in body


def test_dockerfile_installs_requirements():
    body = _read("Dockerfile")
    assert "requirements.txt" in body
    assert "pip install" in body


def test_dockerfile_copies_train_script():
    body = _read("Dockerfile")
    assert "fds-research/" in body or "train_paysim.py" in body


def test_dockerfile_default_cmd_runs_train_help():
    body = _read("Dockerfile")
    # CMD 라인에 train_paysim.py + --help
    assert "train_paysim.py" in body
    assert "--help" in body


def test_dockerignore_excludes_data_and_caches():
    body = _read(".dockerignore")
    assert "__pycache__/" in body
    assert "data/*.csv" in body
    assert "outputs/*.joblib" in body
