"""교육 프로그램 API 테스트."""

import pytest

pytestmark = pytest.mark.api


# ──────────────────────────────────────────────
#  정적 엔드포인트 (DB 불필요)
# ──────────────────────────────────────────────

def test_list_courses(api_client):
    resp = api_client.get("/v1/education/courses")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 12
    assert len(data["courses"]) == 12


def test_get_course_detail(api_client):
    resp = api_client.get("/v1/education/course/L1_C1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["course_id"] == "L1_C1"
    assert data["level"] == "beginner"
    assert len(data["steps"]) == data["total_steps"]


def test_get_course_not_found(api_client):
    resp = api_client.get("/v1/education/course/INVALID_ID")
    assert resp.status_code == 404


def test_list_challenges(api_client):
    resp = api_client.get("/v1/education/challenges")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 3
    assert all("challenge_id" in c for c in data["challenges"])


# ──────────────────────────────────────────────
#  퀴즈 생성 (DB 불필요)
# ──────────────────────────────────────────────

def test_fraud_quiz_generation(api_client):
    resp = api_client.post("/v1/education/quiz/fraud?user_id=test_user&count=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    for q in data["questions"]:
        assert q["correct_answer"] in ["정상 거래", "의심 거래"]
        assert "explanation" in q


def test_spending_quiz_generation(api_client):
    resp = api_client.post("/v1/education/quiz/spending?user_id=test_user&count=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    for q in data["questions"]:
        assert len(q["options"]) >= 2
        assert q["correct_answer"] in q["options"]


# ──────────────────────────────────────────────
#  사기 시뮬레이션 (DB 불필요)
# ──────────────────────────────────────────────

def test_fraud_sim_normal(api_client):
    resp = api_client.post("/v1/education/simulate/fraud", json={
        "user_id": "sim_user", "amount": 5000, "hour": 14,
        "category": "food", "is_foreign_ip": False, "is_new_merchant": False,
    })
    assert resp.status_code == 200
    assert resp.json()["final_action"] == "PASS"


def test_fraud_sim_block(api_client):
    resp = api_client.post("/v1/education/simulate/fraud", json={
        "user_id": "sim_user", "amount": 6000000, "hour": 3,
        "category": "shopping", "is_foreign_ip": True, "is_new_merchant": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["final_action"] == "BLOCK"
    assert len(data["rules_triggered"]) >= 1


def test_fraud_sim_review_high_amount(api_client):
    resp = api_client.post("/v1/education/simulate/fraud", json={
        "user_id": "sim_user", "amount": 1500000, "hour": 10,
        "category": "shopping", "is_foreign_ip": False, "is_new_merchant": False,
    })
    assert resp.status_code == 200
    assert resp.json()["final_action"] == "REVIEW"


# ──────────────────────────────────────────────
#  코스 커버리지 검증
# ──────────────────────────────────────────────

def test_all_levels_have_courses(api_client):
    resp = api_client.get("/v1/education/courses")
    courses = resp.json()["courses"]
    levels = {c["level"] for c in courses}
    assert "beginner" in levels
    assert "intermediate" in levels
    assert "advanced" in levels


def test_course_steps_are_sequential(api_client):
    resp = api_client.get("/v1/education/course/L2_C1")
    course = resp.json()
    steps = course["steps"]
    step_numbers = [s["step"] for s in steps]
    assert step_numbers == list(range(1, len(steps) + 1))
