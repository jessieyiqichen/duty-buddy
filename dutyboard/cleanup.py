"""清仓：挑出该归档的会话，生成交给 Claude 会话的归档请求。纯函数。"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from .config import CLEANUP_BATCH, CLEANUP_FOLDER, CLEANUP_NEW_SESSION_LINK, CLEANUP_STALE_SECONDS
from .desktop import DesktopSession
from .sessions import SessionInfo


def stale_candidates(desktop: tuple[DesktopSession, ...], live: tuple[SessionInfo, ...],
                     now: datetime) -> tuple[DesktopSession, ...]:
    """没归档、没在跑、超过 CLEANUP_STALE_SECONDS 没动的 Code 会话，最久的在前。"""
    live_ids = {i.desktop_id for i in live if i.desktop_id}
    picked = [
        s for s in desktop
        if s.source == "code" and not s.is_archived and s.local_id not in live_ids
        and s.last_activity_at is not None
        and (now - s.last_activity_at).total_seconds() > CLEANUP_STALE_SECONDS
    ]
    return tuple(sorted(picked, key=lambda s: s.last_activity_at))


def archive_prompt(candidates: tuple[DesktopSession, ...], now: datetime) -> str:
    lines = [f"- {s.local_id}  「{s.title or '(无标题)'}」  {_days(s, now)} 天没动" for s in candidates[:CLEANUP_BATCH]]
    return (
        "这是值班表挑出来的、超过 7 天没动的 Code 会话。请先用 list_sessions 核对一遍，"
        "对不上的跳过、最后一并报出来；对得上的用 archive_session 逐个归档，"
        "不要改它们的内容，每个都等我确认。归档完报一下数。\n\n" + "\n".join(lines)
    )


def cleanup_link(candidates: tuple[DesktopSession, ...], now: datetime) -> str:
    return CLEANUP_NEW_SESSION_LINK.format(
        prompt=quote(archive_prompt(candidates, now), safe=""),
        folder=quote(str(CLEANUP_FOLDER), safe=""),
    )


def _days(s: DesktopSession, now: datetime) -> int:
    return int((now - s.last_activity_at).total_seconds() // 86400) if s.last_activity_at else 0
