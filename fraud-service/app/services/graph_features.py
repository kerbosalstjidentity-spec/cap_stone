"""송금 그래프 피처 추출기 (W6.5-#2).

블로그 12 §Track 4 — `graph_store` 의 sorted set 인덱스를 layer-1 시그널로
변환한다. 다음 거래 평가 시 머니뮬·hub-spoke 검출 (W6.5-#3 ``MoneyMuleRule``,
W6.5-#4 ``LayeringRule``) 의 입력이며 ``_evaluate_one`` 응답에도 노출돼
관측·디버깅 가능.

피처 정의:
- ``dest_first_seen_within_24h`` (0/1): 수취인이 그래프에 24시간 내 처음 등장
- ``dest_inbound_velocity_1h`` (int): 1시간 내 수취인이 받은 송금 건수
- ``fan_in_count`` (int): 윈도우 내 수취인에게 송금한 distinct sender 수
- ``pass_through_ratio`` (float): node 의 outbound_amount / inbound_amount
  — 1.0 근처면 받자마자 그대로 내보내는 통과 패턴 (머니뮬)
- ``inbound_amount`` (float): 수취인이 받은 총 금액 (윈도우 내)
- ``outbound_amount`` (float): 송금자가 보낸 총 금액 (윈도우 내)

평가 시점에서 *현재 거래는 아직 store 에 적재되기 직전* 이므로, 피처는
"과거 N분 컨텍스트" 를 의미. evaluate 직후 ``graph_store.record`` 가 호출돼
다음 거래에 반영된다 (W6.5-#1 wiring).
"""
from __future__ import annotations

import time
from typing import Any, Mapping

from app.services.graph_store import graph_store

# 윈도우 (분)
WINDOW_FAN_IN = 60
WINDOW_INBOUND_VELOCITY = 60  # 1h
WINDOW_FIRST_SEEN_HOURS = 24


def dest_first_seen_within_24h(receiver: str) -> int:
    """수취인이 24시간 내 처음 등장하면 1, 그렇지 않으면 0.

    None (그래프에 부재) → 1 (첫 등장).
    24h 보다 오래된 first_seen → 0 (자주 보이는 수취인).
    """
    if not receiver:
        return 0
    fs = graph_store.first_seen_ts(receiver)
    if fs is None:
        return 1
    age_seconds = time.time() - fs
    return 1 if age_seconds < WINDOW_FIRST_SEEN_HOURS * 3600 else 0


def dest_inbound_velocity_1h(receiver: str) -> int:
    """1시간 내 수취인이 받은 송금 건수."""
    if not receiver:
        return 0
    return len(graph_store.inbound(receiver, window_minutes=WINDOW_INBOUND_VELOCITY))


def fan_in_count(receiver: str, window_minutes: int = WINDOW_FAN_IN) -> int:
    return graph_store.fan_in_count(receiver, window_minutes=window_minutes) if receiver else 0


def pass_through_ratio(node: str, window_minutes: int = WINDOW_FAN_IN) -> float:
    """outbound / inbound 금액 비율. 머니뮬 의심 시그널.

    inbound 가 0 이면 0.0 (송금 받은 적 없음 → 통과 패턴 정의 불가).
    1.0 근처면 받은 만큼 그대로 내보내는 hub-spoke / layering 패턴.
    """
    if not node:
        return 0.0
    in_amt = graph_store.inbound_amount(node, window_minutes=window_minutes)
    if in_amt <= 0:
        return 0.0
    out_amt = graph_store.outbound_amount(node, window_minutes=window_minutes)
    return round(out_amt / in_amt, 4)


def inbound_amount(node: str, window_minutes: int = WINDOW_FAN_IN) -> float:
    return graph_store.inbound_amount(node, window_minutes=window_minutes) if node else 0.0


def outbound_amount(node: str, window_minutes: int = WINDOW_FAN_IN) -> float:
    return graph_store.outbound_amount(node, window_minutes=window_minutes) if node else 0.0


def sender_recent_inbound_min_ago(sender: str, window_minutes: int = WINDOW_FAN_IN) -> float:
    """sender 가 가장 최근에 받은 inbound 의 경과 분 (없으면 매우 큰 값).

    LayeringRule(W6.5-#4) 입력 — "직전 받은 송금 후 빠르게 다시 보내는"
    체인 패턴 검출용. None 이면 sentinel 9999.0 으로 반환해 "직전 inbound
    없음=피상이 안 잡힘" 를 명확히.
    """
    if not sender:
        return 9999.0
    edges = graph_store.inbound(sender, window_minutes=window_minutes)
    if not edges:
        return 9999.0
    latest_ts = max(e.ts for e in edges)
    return round((time.time() - latest_ts) / 60.0, 2)


def extract_all(tx: Mapping[str, Any]) -> dict[str, Any]:
    """단건 거래 dict → 그래프 피처 dict.

    ``tx`` 에서 sender(``user_id``) 와 receiver(``nameDest`` > ``receiver_id``)
    를 추출해 평가 직전 컨텍스트(과거 윈도우 누적) 를 반환한다.

    receiver 관점:
        ``fan_in_count`` / ``pass_through_ratio`` / ``inbound_amount`` /
        ``dest_first_seen_within_24h`` / ``dest_inbound_velocity_1h``
    sender 관점 (W6.5-#3 머니뮬 룰 입력):
        ``sender_fan_in_count`` / ``sender_pass_through_ratio`` /
        ``sender_outbound_amount`` — 현재 거래의 송금자가 과거에 받았던
        패턴. 머니뮬은 받자마자 보내는 송금자이므로 sender 의 fan_in 과
        pass_through_ratio 가 모두 높음.

    빈 노드면 모든 피처 0/0.0 반환 (안전 디폴트).
    """
    sender = str(tx.get("user_id", "") or "")
    receiver = str(tx.get("nameDest") or tx.get("receiver_id") or "")
    return {
        "sender": sender,
        "receiver": receiver,
        # receiver 관점
        "dest_first_seen_within_24h": dest_first_seen_within_24h(receiver),
        "dest_inbound_velocity_1h": dest_inbound_velocity_1h(receiver),
        "fan_in_count": fan_in_count(receiver),
        "pass_through_ratio": pass_through_ratio(receiver),
        "inbound_amount": inbound_amount(receiver),
        # sender 관점 (mule / layering 검출용)
        "sender_fan_in_count": fan_in_count(sender),
        "sender_pass_through_ratio": pass_through_ratio(sender),
        "sender_outbound_amount": outbound_amount(sender),
        "sender_recent_inbound_min_ago": sender_recent_inbound_min_ago(sender),
    }
