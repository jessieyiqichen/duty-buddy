"""浮窗底部的项目浏览：项目 → 会话 → 跳转。把侧边栏「按项目筛选」搬进来。纯函数。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .config import BROWSER_MAX_AGE_SECONDS, BROWSER_MAX_PER_PROJECT, STATE_ICONS
from .desktop import DesktopSession, project_of
from .sessions import SessionInfo


@dataclass(frozen=True)
class Entry:
    title: str
    icon: str                 # 运行中的用状态图标，没跑的用 ·
    at: datetime | None
    desktop_id: str
    source: str
    live: bool = False    # 进程活着
    seen: bool = False    # 等你但看过了


@dataclass(frozen=True)
class ProjectView:
    name: str
    live: int
    entries: tuple[Entry, ...]


def build_projects(desktop: tuple[DesktopSession, ...], live: tuple[SessionInfo, ...],
                   now: datetime, icons: dict[str, str] | None = None) -> tuple[ProjectView, ...]:
    icons = icons or STATE_ICONS
    live_by_desktop = {i.desktop_id: i for i in live if i.desktop_id}
    cutoff = BROWSER_MAX_AGE_SECONDS
    groups: dict[str, list[Entry]] = {}
    for s in desktop:
        if s.is_archived:
            continue
        running = live_by_desktop.get(s.local_id)
        age = (now - s.last_activity_at).total_seconds() if s.last_activity_at else float("inf")
        if running is None and age > cutoff:
            continue
        icon = icons[running.state.value] if running else icons.get("entry", "·")
        at = running.last_at if running and running.last_at else s.last_activity_at
        groups.setdefault(project_of(s), []).append(Entry(s.title or s.local_id[:14], icon, at, s.local_id, s.source,
                                                          running is not None, bool(running and running.seen)))
    views = [_project_view(name, entries, live_by_desktop) for name, entries in groups.items()]
    return tuple(sorted(views, key=lambda v: (-v.live, -_latest(v))))


def _project_view(name: str, entries: list[Entry], live_by_desktop: dict) -> ProjectView:
    ordered = sorted(entries, key=lambda e: (e.desktop_id not in live_by_desktop, -(e.at.timestamp() if e.at else 0)))
    live = sum(1 for e in ordered if e.desktop_id in live_by_desktop)
    return ProjectView(name, live, tuple(ordered[:BROWSER_MAX_PER_PROJECT]))


def _latest(view: ProjectView) -> float:
    return max((e.at.timestamp() for e in view.entries if e.at), default=0.0)
