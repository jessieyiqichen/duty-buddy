"""把 SessionInfo 变成给人看的文字。菜单栏和浮窗共用。"""
from __future__ import annotations

from datetime import datetime

from . import config
from .sessions import SessionInfo, State


def age_label(at: datetime | None, now: datetime) -> str:
    if at is None:
        return "无记录"
    seconds = max(0, int((now - at).total_seconds()))
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    return f"{seconds // 86400} 天前"


def clip(text: str | None, limit: int) -> str:
    if not text:
        return ""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def row_label(info: SessionInfo, now: datetime, prompt_chars: int = config.PROMPT_MAX_CHARS) -> str:
    icon = config.STATE_ICONS[info.state.value]
    where = config.ENTRYPOINT_LABELS.get(info.session.entrypoint, info.session.entrypoint)
    parts = [f"{icon} {clip(info.title, config.TITLE_MAX_CHARS)}", where, age_label(info.last_at, now)]
    prompt = clip(info.last_prompt, prompt_chars)
    if prompt:
        parts.insert(2, f"「{prompt}」")
    return "  ·  ".join(parts)


def bar_title(infos: tuple[SessionInfo, ...]) -> str:
    waiting = sum(1 for i in infos if i.state in (State.WAITING, State.PERMISSION))
    running = sum(1 for i in infos if i.state == State.RUNNING)
    if waiting:
        return f"◐ {waiting}"
    if running:
        return f"● {running}"
    return config.APP_TITLE


def waited_label(at: datetime | None, now: datetime) -> str:
    text = age_label(at, now)
    return text if text in ("无记录", "刚刚") else "等了 " + text.removesuffix("前")


def queue_row_label(info: SessionInfo, now: datetime, overdue: bool, icons: dict[str, str] | None = None) -> str:
    icons = icons or config.STATE_ICONS
    parked = info.seen and info.state in (State.WAITING, State.PERMISSION)
    icon = icons.get("parked", "📌") if parked else (icons.get("overdue", "❗") if overdue else icons[info.state.value])
    if parked:
        when = "看过了 · 搁置 " + age_label(info.last_at, now).removesuffix("前")
    else:
        when = waited_label(info.last_at, now) if info.state in (State.WAITING, State.PERMISSION) else age_label(info.last_at, now)
    return f"{icon} {info.project} · {clip(info.title, config.TITLE_MAX_CHARS)} · {when}"


def summary_label(running: int, idle: int, expanded: bool, parked: int = 0) -> str:
    """闲着的不占浮窗，只报在跑的和看过搁着的。"""
    parts = [f"{running} 个在跑"] if running else []
    if parked:
        parts.append(f"{parked} 个看过搁着")
    if not parts:
        return ""
    return ("▾ 另有 " if expanded else "▸ 另有 ") + " · ".join(parts)


def headline_label(attention: int, running: int) -> str:
    if attention:
        return f"◐ {attention} 个等你"
    if running:
        return f"● 都在跑，没人等你 · {running} 个"
    return "◌ 没有运行中的 session"
