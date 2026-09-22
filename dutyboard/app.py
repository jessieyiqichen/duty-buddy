"""菜单栏界面。每几秒刷新一次值班表，session 做完时弹系统通知。"""
from __future__ import annotations

import logging
import shlex
import subprocess
from datetime import datetime, timezone

import rumps

from . import config
from .browser import Entry
from .desktop import deep_link, load_desktop_sessions
from .labels import age_label, bar_title, clip, row_label  # noqa: F401  测试从这里导入
from .panel import FloatingPanel
from .sessions import SessionInfo, State, build_board, group_by_project, newly_done
from .themes import theme_choices

log = logging.getLogger("dutyboard")


def notify(title: str, body: str) -> None:
    script = f"display notification {shlex.quote(body)} with title {shlex.quote(title)}"
    script = script.replace("'", '"')  # AppleScript 用双引号包字符串
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=5)
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("通知发送失败: %s", exc)


def jump_command(info: SessionInfo | Entry) -> list[str]:
    """纯函数：点某一行该执行什么。桌面 session 走深链直接切过去；终端的开 Terminal 恢复。"""
    if isinstance(info, Entry):
        return ["open", deep_link(info.desktop_id)] if info.source == "code" else ["open", "-a", "Claude"]
    if info.desktop_id:
        return ["open", deep_link(info.desktop_id)]
    if info.session.entrypoint == "claude-desktop":
        return ["open", "-a", "Claude"]
    cmd = f"cd {shlex.quote(info.session.cwd)} && claude --resume {shlex.quote(info.session.session_id)}"
    script = f'tell application "Terminal" to do script "{cmd}"\ntell application "Terminal" to activate'
    return ["osascript", "-e", script]


def open_link(url: str) -> None:
    try:
        subprocess.run(["open", url], check=True, timeout=5, capture_output=True)
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("打开链接失败: %s", exc)
        rumps.alert("打不开", str(exc))


def open_session(info: SessionInfo | Entry) -> None:
    try:
        subprocess.run(jump_command(info), check=True, timeout=5, capture_output=True)
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("打开 session 失败: %s", exc)
        rumps.alert("打不开这个 session", str(exc))


class DutyBoard(rumps.App):
    def __init__(self) -> None:
        super().__init__(config.APP_TITLE, quit_button=None)
        self.states: dict[str, State] = {}
        self.title_cache: dict[str, str] = {}
        self.panel = FloatingPanel.alloc().initWithOpener_linkOpener_(open_session, open_link)
        self.timer = rumps.Timer(self.refresh, config.POLL_SECONDS)
        self.timer.start()
        self.refresh(None)

    def refresh(self, _sender) -> None:
        now = datetime.now(timezone.utc)
        try:
            code = load_desktop_sessions(config.DESKTOP_SESSIONS_DIR, "code")
            cowork = load_desktop_sessions(config.COWORK_SESSIONS_DIR, "cowork")
            index = {s.cli_session_id: s for s in code}
            infos, self.title_cache = build_board(config.SESSIONS_DIR, config.PROJECTS_DIR, now,
                                                 self.title_cache, index)
        except Exception:  # 刷新失败不能让菜单栏进程死掉，记日志、下一轮再试
            log.exception("刷新值班表失败")
            self.title = "◌ !"
            return
        current = {i.session.session_id: i.state for i in infos}
        by_id = {i.session.session_id: i for i in infos}
        for sid in newly_done(self.states, current):
            notify(f"{by_id[sid].project} 做好了", by_id[sid].title)
        self.states = current
        self.title = bar_title(infos)
        self._rebuild_menu(infos, now)
        self.panel.render(infos, now, code + cowork)

    def _theme_menu(self) -> rumps.MenuItem:
        menu = rumps.MenuItem("风格")
        for key, label in theme_choices():
            menu.add(_theme_item(self, key, label))
        return menu

    def _rebuild_menu(self, infos: tuple[SessionInfo, ...], now: datetime) -> None:
        items: list = []
        grouped = group_by_project(infos)
        if not grouped:
            items.append(_disabled("没有正在运行的 session"))
        for project, rows in grouped.items():
            items.append(_disabled(f"📁 {project}  ({len(rows)})"))
            items.extend(rumps.MenuItem(row_label(i, now), callback=_opener(i)) for i in rows)
            items.append(None)
        items.append(rumps.MenuItem("显示 / 隐藏浮窗", callback=lambda _: self.panel.toggle_visible()))
        items.append(self._theme_menu())
        items.append(rumps.MenuItem("刷新", callback=self.refresh))
        items.append(rumps.MenuItem("退出", callback=lambda _: rumps.quit_application()))
        self.menu.clear()
        self.menu.update(items)


def _theme_item(self, key: str, label: str) -> rumps.MenuItem:
    item = rumps.MenuItem(("✓ " if self.panel.theme.key == key else "    ") + label,
                          callback=lambda _: self.panel.set_theme(key))
    return item


def _disabled(label: str) -> rumps.MenuItem:
    item = rumps.MenuItem(label)
    item.set_callback(None)
    return item


def _opener(info: SessionInfo):
    return lambda _sender: open_session(info)


def main() -> None:
    logging.basicConfig(filename=config.LOG_PATH, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    log.info("启动")
    DutyBoard().run()


if __name__ == "__main__":
    main()
