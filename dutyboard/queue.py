"""浮窗用的待办队列：只把需要你动手的 session 拎出来，其余压成数字。纯函数。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .config import OVERDUE_SECONDS, STALE_SECONDS
from .sessions import SessionInfo, State

ATTENTION_STATES = frozenset({State.WAITING, State.PERMISSION})


@dataclass(frozen=True)
class QueueView:
    attention: tuple[SessionInfo, ...]   # 等你的（还没看过），等最久的在前
    parked: tuple[SessionInfo, ...]      # 等你但你已经看过，搁着
    others: tuple[SessionInfo, ...]      # 只有在跑的；闲着的不上浮窗，去「按项目找会话」里看
    running: int
    idle: int
    stale: int                           # 闲置超过 STALE_SECONDS，不计入


def _seconds_since(info: SessionInfo, now: datetime) -> float:
    return (now - info.last_at).total_seconds() if info.last_at else float("inf")


def needs_attention(info: SessionInfo) -> bool:
    return info.state in ATTENTION_STATES and not info.seen


def is_overdue(info: SessionInfo, now: datetime) -> bool:
    return needs_attention(info) and _seconds_since(info, now) > OVERDUE_SECONDS


def build_queue(infos: tuple[SessionInfo, ...], now: datetime) -> QueueView:
    attention = tuple(sorted((i for i in infos if needs_attention(i)), key=lambda i: -_seconds_since(i, now)))
    parked = tuple(sorted((i for i in infos if i.state in ATTENTION_STATES and i.seen), key=lambda i: -_seconds_since(i, now)))
    rest = [i for i in infos if i.state not in ATTENTION_STATES]
    stale = [i for i in rest if i.state == State.IDLE and _seconds_since(i, now) > STALE_SECONDS]
    others = tuple(sorted((i for i in rest if i.state == State.RUNNING), key=lambda i: i.project))
    return QueueView(
        attention=attention, parked=parked, others=others,
        running=sum(1 for i in others if i.state == State.RUNNING),
        idle=sum(1 for i in rest if i.state == State.IDLE and i not in stale),
        stale=len(stale),
    )
