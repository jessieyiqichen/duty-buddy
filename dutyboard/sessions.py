"""把运行中的 session 名单和对话记录拼成一张值班表。纯函数，不碰 UI。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from .config import IDLE_SECONDS, PERMISSION_HINT_SECONDS, USER_PENDING_SECONDS
from .desktop import DesktopSession
from .transcript import TranscriptView, load_view, scan_title

FINAL_STOPS = frozenset({"end_turn", "stop_sequence", "max_tokens"})
REQUIRED_KEYS = ("pid", "sessionId", "cwd")


class State(str, Enum):
    RUNNING = "running"        # 模型在想或工具在跑
    WAITING = "waiting"        # 回完了，等你
    PERMISSION = "permission"  # 工具调用悬着很久，可能在等你点确认
    IDLE = "idle"              # 很久没动静


@dataclass(frozen=True)
class RunningSession:
    pid: int
    session_id: str
    cwd: str
    entrypoint: str
    name: str
    started_at: int


@dataclass(frozen=True)
class SessionInfo:
    session: RunningSession
    state: State
    title: str
    last_prompt: str | None
    last_at: datetime | None
    project: str
    desktop_id: str | None = None


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def load_running(sessions_dir: Path) -> tuple[RunningSession, ...]:
    found = []
    for path in sorted(sessions_dir.glob("*.json")):
        session = _parse_session_file(path)
        if session is not None and pid_alive(session.pid):
            found.append(session)
    return tuple(found)


def _parse_session_file(path: Path) -> RunningSession | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or any(k not in raw for k in REQUIRED_KEYS):
        return None
    return RunningSession(
        pid=int(raw["pid"]), session_id=str(raw["sessionId"]), cwd=str(raw["cwd"]),
        entrypoint=str(raw.get("entrypoint", "cli")), name=str(raw.get("name", "")),
        started_at=int(raw.get("startedAt", 0)),
    )


def find_transcript(projects_dir: Path, session_id: str) -> Path | None:
    return next(projects_dir.glob(f"*/{session_id}.jsonl"), None)


def classify(view: TranscriptView, now: datetime) -> State:
    if view.last_message_at is None:
        return State.IDLE
    age = (now - view.last_message_at).total_seconds()
    if age > IDLE_SECONDS:
        return State.IDLE
    if view.last_role == "assistant" and view.stop_reason in FINAL_STOPS:
        return State.WAITING
    if view.last_role == "assistant" and age > PERMISSION_HINT_SECONDS:
        return State.PERMISSION
    if view.last_role == "user" and age > USER_PENDING_SECONDS:
        return State.IDLE  # 用户消息（常是系统注入的通知）挂了很久没人接，不算在跑
    return State.RUNNING


def project_name(cwd: str) -> str:
    return Path(cwd).name or cwd


def build_board(sessions_dir: Path, projects_dir: Path, now: datetime, title_cache: dict[str, str],
                desktop: dict[str, DesktopSession] | None = None,
                ) -> tuple[tuple[SessionInfo, ...], dict[str, str]]:
    """返回 (值班表, 新的标题缓存)。缓存不原地改，返回新 dict。"""
    infos, cache, desktop = [], dict(title_cache), desktop or {}
    for session in load_running(sessions_dir):
        desk = desktop.get(session.session_id)
        path = find_transcript(projects_dir, session.session_id)
        view = load_view(path) if path else TranscriptView(None, None, None, None, None)
        title = (desk.title if desk and desk.title else None) or _resolve_title(session, view, path, cache)
        cache = {**cache, session.session_id: title} if title != session.name else cache
        infos.append(SessionInfo(session, classify(view, now), title, view.last_prompt,
                                 view.last_message_at, project_name(session.cwd),
                                 desk.local_id if desk else None))
    return tuple(infos), cache


def _resolve_title(session: RunningSession, view: TranscriptView, path: Path | None,
                   cache: dict[str, str]) -> str:
    if view.title:
        return view.title
    if session.session_id in cache:
        return cache[session.session_id]
    scanned = scan_title(path) if path else None
    return scanned or session.name or session.session_id[:8]


def group_by_project(infos: tuple[SessionInfo, ...]) -> dict[str, tuple[SessionInfo, ...]]:
    order = {State.WAITING: 0, State.PERMISSION: 1, State.RUNNING: 2, State.IDLE: 3}
    grouped: dict[str, list[SessionInfo]] = {}
    for info in infos:
        grouped.setdefault(info.project, []).append(info)
    return {
        project: tuple(sorted(items, key=lambda i: (order[i.state], i.title)))
        for project, items in sorted(grouped.items())
    }


def newly_done(prev: dict[str, State], cur: dict[str, State]) -> tuple[str, ...]:
    busy = {State.RUNNING, State.PERMISSION}
    return tuple(sid for sid, state in cur.items() if state == State.WAITING and prev.get(sid) in busy)
