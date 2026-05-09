"""W9-#16 — fds_scripts 패키지 등록 후 정상 import 확인."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_package_importable():
    import fds_scripts  # noqa: F401
    from fds_scripts.evaluation_suite import generate_compliance_checklist
    summary = generate_compliance_checklist()["summary"]
    assert summary["total_items"] > 0
    assert "production_ready_rate" in summary


def test_no_sys_path_hack_in_routes_evaluation():
    """W9-#16: routes_evaluation.py 가 'from evaluation_suite import' 가 아닌
    'from fds_scripts.evaluation_suite import' 를 사용하는지 검증."""
    src = (ROOT / "backend" / "app" / "api" / "routes_evaluation.py").read_text(
        encoding="utf-8"
    )
    assert "from fds_scripts.evaluation_suite" in src
    # 디렉터리 직접 주입 패턴은 제거됐어야 함 — PROJECT_ROOT 보강만 허용
    assert "fds_scripts').resolve" not in src
