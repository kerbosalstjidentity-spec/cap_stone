"""pytest 설정 — API 테스트는 서버 실행 필요, 기본은 skip."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api_client():
    """모듈 스코프 TestClient — DB 연결 풀을 모듈 내에서 공유."""
    from app.main import app
    with TestClient(app) as c:
        yield c


_ALWAYS_RUN = {"test_ml_modules", "test_security"}

_API_TEST_FILES = {
    "test_profile_api",
    "test_analysis_api",
    "test_strategy_api",
    "test_auth_api",
    "test_education_api",
}


def pytest_collection_modifyitems(items):
    """
    - test_ml_modules, test_security: 항상 실행 (외부 의존성 없음)
    - 나머지 API 테스트: --run-api 플래그 없으면 skip
    """
    for item in items:
        fname = item.fspath.basename.replace(".py", "")
        if fname in _ALWAYS_RUN:
            continue
        if fname in _API_TEST_FILES:
            item.add_marker(pytest.mark.api)


def pytest_addoption(parser):
    parser.addoption("--run-api", action="store_true", default=False,
                     help="API 통합 테스트 실행 (서버 불필요, TestClient 사용)")


def pytest_configure(config):
    config.addinivalue_line("markers", "api: API 통합 테스트")
