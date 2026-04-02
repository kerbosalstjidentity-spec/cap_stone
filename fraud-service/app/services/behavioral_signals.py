"""
Layer 1 — Client/Edge 행동 시그널 리스크 분석.

교수님 연구 연계:
- "EC-SVC: Edge Computing 기반 차량 내 통신" (TIFS 2022)
  → 차량 OBD 신호를 웹 행동 시그널로 치환
- Edge에서 경량 리스크 사전 스크리닝 수행

브라우저/앱 SDK에서 수집한 행동 시그널을 분석하여
리스크 점수(0~1)와 이상 플래그를 산출한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SignalRiskResult:
    """행동 시그널 기반 리스크 분석 결과."""
    risk_score: float       # 0.0 ~ 1.0
    flags: list[str]        # 감지된 이상 플래그
    detail: dict[str, Any]  # 각 시그널별 상세


def analyze_signals(signals: dict[str, Any] | None) -> SignalRiskResult:
    """행동 시그널 딕셔너리에서 리스크를 분석한다.

    signals가 None이면 분석 불가 → 중립(0.0) 반환.
    """
    if not signals:
        return SignalRiskResult(risk_score=0.0, flags=[], detail={})

    score = 0.0
    flags: list[str] = []
    detail: dict[str, Any] = {}

    # ── 행동 생체인식 ──────────────────────────────────────
    biometrics = signals.get("behavioral_biometrics", {})

    # 마우스 속도 분산이 극단적으로 낮으면 봇 의심
    mouse_var = biometrics.get("mouse_speed_variance")
    if mouse_var is not None and mouse_var < 0.01:
        score += 0.3
        flags.append("BOT_MOUSE_PATTERN")
        detail["mouse_speed_variance"] = mouse_var

    # 폼 작성 시간이 3초 미만이면 자동 입력 의심
    fill_ms = biometrics.get("form_fill_duration_ms")
    if fill_ms is not None and fill_ms < 3000:
        score += 0.4
        flags.append("FAST_FORM_FILL")
        detail["form_fill_duration_ms"] = fill_ms

    # 클립보드 붙여넣기 횟수
    paste = biometrics.get("clipboard_paste_count")
    if paste is not None and paste >= 3:
        score += 0.2
        flags.append("EXCESSIVE_PASTE")
        detail["clipboard_paste_count"] = paste

    # ── 세션 컨텍스트 ──────────────────────────────────────
    session = signals.get("session_context", {})

    tab_changes = session.get("tab_focus_changes")
    if tab_changes is not None and tab_changes > 10:
        score += 0.1
        flags.append("HIGH_TAB_SWITCHING")
        detail["tab_focus_changes"] = tab_changes

    dwell = session.get("page_dwell_time_ms")
    if dwell is not None and dwell < 2000:
        score += 0.15
        flags.append("VERY_SHORT_DWELL")
        detail["page_dwell_time_ms"] = dwell

    # ── 네트워크 컨텍스트 ──────────────────────────────────
    network = signals.get("network_context", {})

    if network.get("is_tor"):
        score += 0.5
        flags.append("TOR_DETECTED")

    if network.get("is_vpn"):
        score += 0.2
        flags.append("VPN_DETECTED")

    if network.get("is_proxy"):
        score += 0.15
        flags.append("PROXY_DETECTED")

    # 최종 점수 클리핑
    risk_score = min(score, 1.0)

    return SignalRiskResult(
        risk_score=round(risk_score, 4),
        flags=flags,
        detail=detail,
    )
