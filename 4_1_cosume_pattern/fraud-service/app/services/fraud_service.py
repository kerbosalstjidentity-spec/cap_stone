import datetime

from app.services.policy_merge import audit_summary, merge_actions
from app.services.rule_engine import rule_engine
from app.services.profile_store import profile_store

# 1. 시스템 설정 (제공된 JSON 데이터 기반)
SYSTEM_CONFIG = {
    "BLOCK_THRESHOLD": 0.95,
    "REVIEW_THRESHOLD": 0.35,
    "P99_THRESHOLD": 0.005,   # 잠재적 위험군 기준
    "PASS_RATE": 0.998,
    "MISS_RATE": 0.334,       # 1 - holdout_recall_in_queue (0.666)
    # 금액 기반 규칙 임계값 (원화)
    "AMOUNT_BLOCK_THRESHOLD": 5_000_000,   # 500만원 이상 → 규칙 BLOCK
    "AMOUNT_REVIEW_THRESHOLD": 1_000_000,  # 100만원 이상 → 규칙 REVIEW
}


class FraudServiceManager:
    def __init__(self, tx_data: dict):
        self.tx = tx_data
        self.score = float(tx_data.get("score", 0.0))
        self.amount = float(tx_data.get("amount", 0))

    # [서비스 1] 운영팀: 모델 스코어 기반 action
    def get_model_action(self) -> str:
        if self.score >= SYSTEM_CONFIG["BLOCK_THRESHOLD"]:
            return "BLOCK"
        if self.score >= SYSTEM_CONFIG["REVIEW_THRESHOLD"]:
            return "REVIEW"
        if self.score >= SYSTEM_CONFIG["P99_THRESHOLD"]:
            return "SOFT_REVIEW"
        return "PASS"

    # [서비스 1-b] Rule Engine 기반 action
    def get_rule_action(self) -> tuple[str, str]:
        """(rule_action, rule_ids) 반환. Rule Engine 전체 평가."""
        from app.services.access_list import access_list
        user_id = self.tx.get("user_id", "")
        # 화이트리스트 → Rule 생략
        if user_id and access_list.is_whitelisted(user_id):
            return "PASS", "WHITELIST"
        profile = profile_store.get_profile(user_id)
        results = rule_engine.evaluate_all(self.tx, profile)
        return rule_engine.get_strongest(results)

    # [서비스 1-c] 모델 + 규칙 통합 최종 action
    def get_final_action(self) -> str:
        model_action = self.get_model_action()
        rule_action, _ = self.get_rule_action()
        return merge_actions(rule_action, model_action)

    # [레거시 호환] admin_routing
    def get_admin_routing(self) -> dict:
        action = self.get_final_action()
        priority_map = {
            "BLOCK": ("CRITICAL", "Immediate_Action"),
            "REVIEW": ("HIGH", "Manual_Verify"),
            "SOFT_REVIEW": ("MEDIUM", "Monitoring_List"),
            "PASS": ("LOW", "None"),
        }
        priority, queue = priority_map.get(action, ("LOW", "None"))
        return {"action": action, "priority": priority, "queue": queue}

    # [서비스 2] 사용자: 거래 상태 피드백 (모든 action에 메시지 반환)
    def get_user_trust_message(self) -> dict:
        action = self.get_final_action()
        amount_str = f"{int(self.amount):,}원"
        if action == "PASS":
            return {
                "status": "Secure",
                "message": f"현시각 보안 엔진이 {SYSTEM_CONFIG['PASS_RATE']*100:.1f}%의 거래와 함께 고객님의 결제를 안전하게 보호 중입니다.",
            }
        if action == "SOFT_REVIEW":
            return {
                "status": "Monitoring",
                "message": f"{amount_str} 결제가 모니터링 대상에 포함되어 있습니다. 본인이 시도한 거래라면 정상 처리됩니다.",
            }
        if action == "REVIEW":
            return {
                "status": "PendingVerification",
                "message": f"{amount_str} 결제에 대해 본인 확인이 필요합니다. 잠시 후 앱에서 승인 요청을 확인해 주세요.",
            }
        # BLOCK
        return {
            "status": "Blocked",
            "message": f"{amount_str} 결제가 비정상 패턴으로 감지되어 차단되었습니다. 본인 거래라면 고객센터(1588-XXXX)로 문의해 주세요.",
        }

    # [서비스 3] 이상 징후 발생 시: 사용자 확인 푸시 (Step-up Auth)
    def trigger_step_up_auth(self) -> dict:
        from app.services.push_service import build_step_up_payload, send_sync
        action = self.get_final_action()
        tx_id = self.tx.get("tx_id", "")
        fcm_token = self.tx.get("fcm_token", "")

        if action == "BLOCK":
            payload = build_step_up_payload(tx_id, self.amount, "BLOCK_ALERT")
            if fcm_token:
                send_sync(fcm_token, payload["title"], payload["body"], payload["data"])
            return {"push_sent": bool(fcm_token), "type": "BLOCK_ALERT", **payload}

        if action in ("REVIEW", "SOFT_REVIEW"):
            payload = build_step_up_payload(tx_id, self.amount, "STEP_UP_AUTH")
            if fcm_token:
                send_sync(fcm_token, payload["title"], payload["body"], payload["data"])
            return {"push_sent": bool(fcm_token), "type": "STEP_UP_AUTH", **payload}

        return {"push_sent": False}

    # [서비스 4] audit 요약 (운영 로그용)
    def get_audit(self, reason_code: str = "") -> str:
        _, rule_id = self.get_rule_action()
        return audit_summary(reason_code, rule_id)


# [서비스 5] 사내 보고용: 미탐지(Leakage) 리스크 시뮬레이터
def generate_risk_leakage_report(total_processed_amount: float) -> dict:
    potential_leakage = total_processed_amount * (1 - SYSTEM_CONFIG["PASS_RATE"]) * SYSTEM_CONFIG["MISS_RATE"]
    return {
        "report_date": datetime.date.today().isoformat(),
        "current_leakage_estimate": f"₩{potential_leakage:,.0f}",
        "insight": "현재 Recall(66%) 기준, 탐지되지 않고 빠져나갈 수 있는 잠재적 사고 노출액입니다.",
    }
