"""读桌面 app 的 session 元数据（Code 和 Cowork 两处）。只读。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import COWORK_PROJECT_NAME, DESKTOP_DEEP_LINK


@dataclass(frozen=True)
class DesktopSession:
    local_id: str
    cli_session_id: str
    title: str | None
    is_archived: bool
    cwd: str = ""
    last_activity_at: datetime | None = None
    source: str = "code"          # "code" | "cowork"


def load_desktop_sessions(root: Path, source: str = "code") -> tuple[DesktopSession, ...]:
    """只取当前活跃的那个账号 scope。文件坏了或缺字段就跳过，桌面 app 随时在写这些文件。

    目录是 <账号>/<工作区>/local_*.json。换过账号的机器上会留下旧 scope 的元数据，
    那些会话官方接口寻址不到（archive_session 一律 not found），必须排除。
    """
    by_scope: dict[Path, list[DesktopSession]] = {}
    for path in sorted(root.glob("*/*/local_*.json")):
        session = _parse(path, source)
        if session is not None:
            by_scope.setdefault(path.parent, []).append(session)
    if not by_scope:
        return ()
    active = max(sorted(by_scope), key=lambda scope: _newest(by_scope[scope]))
    return tuple(by_scope[active])


def _newest(sessions: list[DesktopSession]) -> datetime:
    """scope 里最后一次有动静的时间；全都没时间戳就当最早，让有时间戳的 scope 赢。"""
    stamps = [s.last_activity_at for s in sessions if s.last_activity_at is not None]
    return max(stamps) if stamps else datetime.fromtimestamp(0, tz=timezone.utc)


def load_desktop_index(root: Path) -> dict[str, DesktopSession]:
    """按 CLI session id 索引 Code 会话，给运行中的进程对回桌面 id 和标题。"""
    return {s.cli_session_id: s for s in load_desktop_sessions(root, "code")}


def _parse(path: Path, source: str) -> DesktopSession | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    local_id, cli_id = raw.get("sessionId"), raw.get("cliSessionId")
    if not isinstance(local_id, str) or not isinstance(cli_id, str):
        return None
    title = raw.get("title") if isinstance(raw.get("title"), str) else None
    cwd = raw.get("cwd") if isinstance(raw.get("cwd"), str) else ""
    return DesktopSession(local_id, cli_id, title, bool(raw.get("isArchived")), cwd,
                          _ms_to_dt(raw.get("lastActivityAt")), source)


def _ms_to_dt(raw: object) -> datetime | None:
    if not isinstance(raw, (int, float)) or raw <= 0:
        return None
    return datetime.fromtimestamp(raw / 1000, tz=timezone.utc)


def project_of(session: DesktopSession) -> str:
    if session.source == "cowork":
        return COWORK_PROJECT_NAME
    return Path(session.cwd).name or session.cwd or "?"


def deep_link(local_id: str) -> str:
    return DESKTOP_DEEP_LINK.format(local_id=local_id)
