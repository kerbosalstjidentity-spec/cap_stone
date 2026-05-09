"""
Layer 1 — Client/Edge 행동 시그널 리스크 분석.

교수님 연구 연계:
- "EC-SVC: Edge Computing 기반 차량 내 통신" (TIFS 2022)
  → 차량 OBD 신호를 웹 행동 시그널로 치환
- Edge에서 경량 리스크 사전 스크리닝 수행

브라우저/앱 SDK에서 수집한 행동 시그널을 분석하여
리스크 점수(0~1)와 이상 플래그를 산출한다.

W1-#6: 클라이언트 시그널 위변조 방지.
- HMAC-SHA256 서명 + 타임스탬프 검증 (5분 윈도우)
- 서명 누락/실패 시 클라이언트 시그널은 untrusted 로 다운그레이드
- 서버사이드 보강: 요청 IP·국가·UA 등은 서버가 직접 관찰한 값으로 덮어씀
- 환경변수 BEHAVIOR_SIGNAL_SECRET 미설정 시 dev 모드 (검증 스킵 + 경고)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SignalRiskResult:
    """행동 시그널 기반 리스크 분석 결과."""
    risk_score: float       # 0.0 ~ 1.0 (untrusted 감쇠·clip 적용 후)
    flags: list[str]        # 감지된 이상 플래그
    detail: dict[str, Any]  # 각 시그널별 상세
    verified: bool = False  # 클라이언트 HMAC 서명 검증 결과 (False면 untrusted)
    raw_score: float = 0.0  # W9-#5: untrusted 감쇠/clip 이전 원점수 (가중치 튜닝용)


# ──────────────────────────────────────────────
#  HMAC 서명 검증 (W1-#6)
# ──────────────────────────────────────────────

_SIGNAL_SECRET = os.getenv("BEHAVIOR_SIGNAL_SECRET", "")
_SIGNAL_MAX_AGE_S = int(os.getenv("BEHAVIOR_SIGNAL_MAX_AGE_S", "300"))


def _envf(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _envi(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# W9-#5: 임계값 env 외부화 — 사용자별/도메인별 튜닝 가능.
_T_MOUSE_VAR = _envf("BEHAVIOR_T_MOUSE_VAR", 0.01)
_T_FORM_FILL_MS = _envi("BEHAVIOR_T_FORM_FILL_MS", 3000)
_T_PASTE_COUNT = _envi("BEHAVIOR_T_PASTE_COUNT", 3)
_T_TAB_CHANGES = _envi("BEHAVIOR_T_TAB_CHANGES", 10)
_T_DWELL_MS = _envi("BEHAVIOR_T_DWELL_MS", 2000)
_UNTRUSTED_DECAY = _envf("BEHAVIOR_UNTRUSTED_DECAY", 0.5)


def _canonical_payload(signals: dict[str, Any], timestamp: int | str) -> bytes:
    """서명 대상 페이로드를 정규화해 직렬화 — 클라이언트와 동일한 알고리즘.

    JSON sort_keys=True + separators=(",",":") + ts 접미사.
    """
    body = json.dumps(signals, sort_keys=True, separators=(",", ":"))
    return f"{body}|ts={timestamp}".encode("utf-8")


def compute_signal_signature(signals: dict[str, Any], timestamp: int, secret: str | None = None) -> str:
    """클라이언트가 페이로드에 서명할 때 사용. 서버에서도 검증 시 동일 함수 호출."""
    key = (secret or _SIGNAL_SECRET).encode("utf-8")
    return hmac.new(key, _canonical_payload(signals, timestamp), hashlib.sha256).hexdigest()


def verify_signal_signature(
    signals: dict[str, Any] | None,
    signature: str | None,
    timestamp: int | str | None,
    *,
    max_age_s: int = _SIGNAL_MAX_AGE_S,
) -> bool:
    """HMAC 서명 + 타임스탬프 검증. dev에서 시크릿 미설정이면 항상 False."""
    if not signals or not signature or timestamp is None:
        return False
    if not _SIGNAL_SECRET:
        # dev 모드 — 시크릿 미설정. 검증 자체가 불가능하므로 untrusted.
        return False
    try:
        ts = int(timestamp)
        age = abs(int(time.time()) - ts)
        if age > max_age_s:
            return False
    except (TypeError, ValueError):
        return False
    expected = compute_signal_signature(signals, ts)
    return hmac.compare_digest(expected, signature)


def merge_server_context(signals: dict[str, Any] | None, server_ctx: dict[str, Any] | None) -> dict[str, Any]:
    """서버사이드에서 관찰한 값(IP, 국가, UA 등)으로 클라이언트 시그널 보강.

    동일 키가 있으면 **서버 값이 클라이언트 값을 덮어쓴다** — 위변조 방지.
    """
    out: dict[str, Any] = dict(signals or {})
    if not server_ctx:
        return out
    network = dict(out.get("network_context", {}))
    for k in ("ip", "country", "asn", "is_tor", "is_vpn", "is_proxy", "user_agent"):
        if k in server_ctx:
            network[k] = server_ctx[k]
    out["network_context"] = network
    out["server_observed"] = {k: server_ctx.get(k) for k in server_ctx if k.startswith("server_")}
    return out


def analyze_signals(
    signals: dict[str, Any] | None,
    *,
    signature: str | None = None,
    timestamp: int | str | None = None,
    server_context: dict[str, Any] | None = None,
) -> SignalRiskResult:
    """행동 시그널 딕셔너리에서 리스크를 분석한다.

    W1-#6: HMAC 서명 검증 + 서버사이드 보강.
    - signature/timestamp 가 주어지면 검증, 통과 시 result.verified=True
    - 검증 실패 또는 누락 → result.verified=False (UNVERIFIED_SIGNALS 플래그)
    - server_context 가 있으면 IP/국가 등 서버 관찰값으로 덮어씀

    signals가 None이면 분석 불가 → 중립(0.0) 반환.
    """
    if not signals:
        return SignalRiskResult(risk_score=0.0, flags=[], detail={}, verified=False, raw_score=0.0)

    verified = verify_signal_signature(signals, signature, timestamp)
    # 서버 관찰값으로 보강 — 클라이언트가 위조한 IP/국가 등을 무력화
    signals = merge_server_context(signals, server_context)

    score = 0.0
    flags: list[str] = []
    detail: dict[str, Any] = {}

    # ── 행동 생체인식 ──────────────────────────────────────
    biometrics = signals.get("behavioral_biometrics", {})

    # 마우스 속도 분산이 극단적으로 낮으면 봇 의심 (W9-#5: env 임계)
    mouse_var = biometrics.get("mouse_speed_variance")
    if mouse_var is not None and mouse_var < _T_MOUSE_VAR:
        score += 0.3
        flags.append("BOT_MOUSE_PATTERN")
        detail["mouse_speed_variance"] = mouse_var

    # 폼 작성 시간이 임계 미만이면 자동 입력 의심
    fill_ms = biometrics.get("form_fill_duration_ms")
    if fill_ms is not None and fill_ms < _T_FORM_FILL_MS:
        score += 0.4
        flags.append("FAST_FORM_FILL")
        detail["form_fill_duration_ms"] = fill_ms

    # 클립보드 붙여넣기 횟수
    paste = biometrics.get("clipboard_paste_count")
    if paste is not None and paste >= _T_PASTE_COUNT:
        score += 0.2
        flags.append("EXCESSIVE_PASTE")
        detail["clipboard_paste_count"] = paste

    # ── 세션 컨텍스트 ──────────────────────────────────────
    session = signals.get("session_context", {})

    tab_changes = session.get("tab_focus_changes")
    if tab_changes is not None and tab_changes > _T_TAB_CHANGES:
        score += 0.1
        flags.append("HIGH_TAB_SWITCHING")
        detail["tab_focus_changes"] = tab_changes

    dwell = session.get("page_dwell_time_ms")
    if dwell is not None and dwell < _T_DWELL_MS:
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

    # W9-#5: 원점수(untrusted 감쇠·clip 이전) 보존 — 가중치 튜닝/관측용
    raw_score = round(min(score, 1.0), 4)

    # W1-#6: 서명 미검증 시 untrusted 가중치 + 플래그
    if not verified:
        flags.append("UNVERIFIED_SIGNALS")
        score = score * _UNTRUSTED_DECAY

    # 최종 점수 클리핑
    risk_score = min(score, 1.0)

    return SignalRiskResult(
        risk_score=round(risk_score, 4),
        flags=flags,
        detail=detail,
        verified=verified,
        raw_score=raw_score,
    )
