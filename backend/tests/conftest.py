"""pytest 설정 — API 테스트는 서버 실행 필요, 기본은 skip."""

import pytest


def pytest_collection_modifyitems(items):
    """API 테스트(TestClient)는 --run-api 플래그 없으면 skip."""
    for item in items:
        # test_ml_modules.py 는 항상 실행
        if "test_ml_modules" in str(item.fspath):
            continue
        # 나머지 API 테스트는 마커 추가
        if "test_profile_api" in str(item.fspath) or \
           "test_analysis_api" in str(item.fspath) or \
           "test_strategy_api" in str(item.fspath):
            item.add_marker(pytest.mark.api)


def pytest_addoption(parser):
    parser.addoption("--run-api", action="store_true", default=False,
                     help="API 통합 테스트 실행 (서버 불필요, TestClient 사용)")


def pytest_configure(config):
    config.addinivalue_line("markers", "api: API 통합 테스트")
