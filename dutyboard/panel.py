"""桌面浮窗：待办队列形态。只列等你的 session，其余压成一行数字，点那行展开。
无边框、永远置顶、可拖动，点标题折叠。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

import objc
from AppKit import (NSBackingStoreBuffered, NSButton, NSColor, NSFloatingWindowLevel, NSFont,
                    NSMakeRect, NSPanel, NSScreen, NSTextAlignmentLeft, NSUserDefaults,
                    NSVisualEffectBlendingModeBehindWindow, NSVisualEffectMaterialHUDWindow,
                    NSVisualEffectStateActive, NSVisualEffectView,
                    NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorStationary,
                    NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel)
from Foundation import NSObject

from . import config
from .browser import Entry, ProjectView, build_projects
from .cleanup import cleanup_link, stale_candidates
from .desktop import DesktopSession
from .labels import age_label, headline_label, queue_row_label, summary_label
from .queue import QueueView, build_queue, is_overdue
from .sessions import SessionInfo

JumpTarget = SessionInfo | Entry

log = logging.getLogger("dutyboard.panel")


def panel_height(attention: int, others_shown: int, has_summary: bool, collapsed: bool,
                 project_rows: int = 0) -> int:
    """纯函数：浮窗总高度 = 标题 + 等你的行 + 汇总行 + 展开的其他行 + 项目区的行。"""
    height = config.PANEL_PADDING * 2 + config.PANEL_HEADER_HEIGHT
    if collapsed:
        return height
    rows = attention + others_shown + (1 if has_summary else 0)
    height += config.PANEL_ROW_HEIGHT * rows + (config.PANEL_GROUP_GAP if rows else 0)
    return height + config.PANEL_ROW_HEIGHT * project_rows + (config.PANEL_GROUP_GAP if project_rows else 0)


def project_rows(projects: tuple[ProjectView, ...], show: bool, opened: str | None) -> int:
    """项目区占几行：1 行开关；展开后每个项目 1 行，打开的那个项目再加它的会话行。"""
    if not show:
        return 1
    return 1 + len(projects) + sum(len(v.entries) for v in projects if v.name == opened)


class FloatingPanel(NSObject):
    """PyObjC 的 target 必须是 NSObject 子类，所以浮窗控制器本身就是一个 NSObject。"""

    def initWithOpener_linkOpener_(self, opener: Callable[[SessionInfo], None], open_link: Callable[[str], None]):
        self = objc.super(FloatingPanel, self).init()
        if self is None:
            return None
        self.opener = opener
        self.open_link = open_link
        self.rows: list[SessionInfo] = []
        self.collapsed = False
        self.show_others = False
        self.show_projects = False
        self.opened_project: str | None = None
        self.projects: tuple[ProjectView, ...] = ()
        self.entries: list[Entry] = []
        self.last_infos: tuple[SessionInfo, ...] = ()
        self.last_desktop: tuple[DesktopSession, ...] = ()
        self.stale: tuple[DesktopSession, ...] = ()
        self.window = self._make_window()
        self.content = self._make_content()
        self.window.setContentView_(self.content)
        self.window.orderFrontRegardless()
        return self

    # ---------- 构建 ----------
    @objc.python_method
    def _make_window(self) -> NSPanel:
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        frame = NSMakeRect(0, 0, config.PANEL_WIDTH, panel_height(0, 0, False, False))
        window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(frame, style, NSBackingStoreBuffered, False)
        window.setLevel_(NSFloatingWindowLevel)
        window.setOpaque_(False)
        window.setBackgroundColor_(NSColor.clearColor())
        window.setHasShadow_(True)
        window.setMovableByWindowBackground_(True)
        window.setHidesOnDeactivate_(False)
        window.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary)
        window.setFrameTopLeftPoint_(self._saved_top_left())
        return window

    @objc.python_method
    def _make_content(self) -> NSVisualEffectView:
        view = NSVisualEffectView.alloc().initWithFrame_(self.window.contentView().bounds())
        view.setMaterial_(NSVisualEffectMaterialHUDWindow)
        view.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        view.setState_(NSVisualEffectStateActive)
        view.setWantsLayer_(True)
        view.layer().setCornerRadius_(12)
        view.layer().setMasksToBounds_(True)
        return view

    # ---------- 刷新 ----------
    @objc.python_method
    def render(self, infos: tuple[SessionInfo, ...], now: datetime,
               desktop: tuple[DesktopSession, ...] = ()) -> None:
        self.last_infos, self.last_desktop = infos, desktop
        try:
            self.projects = build_projects(desktop, infos, now)
            self.stale = stale_candidates(desktop, infos, now)
            self._render(build_queue(infos, now), now)
        except Exception:  # 浮窗画坏了不能拖死整个进程
            log.exception("浮窗刷新失败")

    @objc.python_method
    def _render(self, queue: QueueView, now: datetime) -> None:
        summary = summary_label(queue.running, queue.idle, self.show_others)
        others = queue.others if (self.show_others and summary) else ()
        self.rows = [*queue.attention, *others]
        prows = project_rows(self.projects, self.show_projects, self.opened_project) + (1 if self.stale else 0)
        height = panel_height(len(queue.attention), len(others), bool(summary), self.collapsed, prows)
        self._resize_keeping_top_left(height)
        for sub in list(self.content.subviews()):
            sub.removeFromSuperview()
        y = height - config.PANEL_PADDING - config.PANEL_HEADER_HEIGHT
        self._add_header(y, "Claude 值班表   " + headline_label(len(queue.attention), queue.running))
        if self.collapsed:
            return
        y -= config.PANEL_GROUP_GAP
        for tag, info in enumerate(queue.attention):
            y -= config.PANEL_ROW_HEIGHT
            self._add_row(y, queue_row_label(info, now, is_overdue(info, now)), tag)
        if summary:
            y -= config.PANEL_ROW_HEIGHT
            self.content.addSubview_(self._button(y, summary, config.PANEL_ROW_HEIGHT, "toggleOthers:", 0))
        for offset, info in enumerate(others):
            y -= config.PANEL_ROW_HEIGHT
            self._add_row(y, queue_row_label(info, now, False), len(queue.attention) + offset)
        self._render_projects(y - config.PANEL_GROUP_GAP, now)

    @objc.python_method
    def _render_projects(self, y: float, now: datetime) -> None:
        arrow = "▾" if self.show_projects else "▸"
        y -= config.PANEL_ROW_HEIGHT
        self.content.addSubview_(self._button(y, f"{arrow} 按项目找会话 · {len(self.projects)} 个项目", config.PANEL_ROW_HEIGHT, "toggleProjects:", 0))
        if not self.show_projects:
            self._render_cleanup(y)
            return
        self.entries = []
        for index, view in enumerate(self.projects):
            y -= config.PANEL_ROW_HEIGHT
            mark = "📂" if view.name == self.opened_project else "📁"
            live = f" · {view.live} 个在跑" if view.live else f" · {len(view.entries)} 个"
            self.content.addSubview_(self._button(y, f"    {mark} {view.name}{live}", config.PANEL_ROW_HEIGHT, "projectClicked:", index))
            if view.name != self.opened_project:
                continue
            for entry in view.entries:
                y -= config.PANEL_ROW_HEIGHT
                where = "  Cowork" if entry.source == "cowork" else ""
                label = f"        {entry.icon} {entry.title[:config.TITLE_MAX_CHARS]} · {age_label(entry.at, now)}{where}"
                self.content.addSubview_(self._button(y, label, config.PANEL_ROW_HEIGHT, "entryClicked:", len(self.entries)))
                self.entries.append(entry)
        self._render_cleanup(y)

    @objc.python_method
    def _render_cleanup(self, y: float) -> float:
        if not self.stale:
            return y
        y -= config.PANEL_ROW_HEIGHT
        label = f"🗑 可归档 · {len(self.stale)} 个超过 7 天没动 · 点我交给 Claude 清"
        self.content.addSubview_(self._button(y, label, config.PANEL_ROW_HEIGHT, "cleanupClicked:", 0))
        return y

    @objc.python_method
    def _resize_keeping_top_left(self, height: int) -> None:
        frame = self.window.frame()
        top = frame.origin.y + frame.size.height
        self.window.setFrame_display_(NSMakeRect(frame.origin.x, top - height, config.PANEL_WIDTH, height), True)
        self.content.setFrame_(self.window.contentView().bounds())
        self._save_top_left(frame.origin.x, top)

    @objc.python_method
    def _add_header(self, y: float, text: str) -> None:
        button = self._button(y, text, config.PANEL_HEADER_HEIGHT, "toggleCollapsed:", 0)
        button.setFont_(NSFont.boldSystemFontOfSize_(config.PANEL_FONT_SIZE + 1))
        self.content.addSubview_(button)

    @objc.python_method
    def _add_row(self, y: float, text: str, tag: int) -> None:
        self.content.addSubview_(self._button(y, "    " + text, config.PANEL_ROW_HEIGHT, "rowClicked:", tag))

    @objc.python_method
    def _button(self, y: float, text: str, height: int, selector: str, tag: int) -> NSButton:
        width = config.PANEL_WIDTH - config.PANEL_PADDING * 2
        button = NSButton.alloc().initWithFrame_(NSMakeRect(config.PANEL_PADDING, y, width, height))
        button.setTitle_(text)
        button.setBordered_(False)
        button.setAlignment_(NSTextAlignmentLeft)
        button.setFont_(NSFont.systemFontOfSize_(config.PANEL_FONT_SIZE))
        button.setLineBreakMode_(4)
        button.setTarget_(self)
        button.setAction_(selector)
        button.setTag_(tag)
        return button

    # ---------- 事件 ----------
    def rowClicked_(self, sender) -> None:
        index = sender.tag()
        if 0 <= index < len(self.rows):
            self.opener(self.rows[index])

    @objc.python_method
    def _redraw_now(self) -> None:
        self.render(self.last_infos, datetime.now(timezone.utc), self.last_desktop)

    def toggleCollapsed_(self, _sender) -> None:
        self.collapsed = not self.collapsed
        self._redraw_now()

    def toggleOthers_(self, _sender) -> None:
        self.show_others = not self.show_others
        self._redraw_now()

    def toggleProjects_(self, _sender) -> None:
        self.show_projects = not self.show_projects
        self._redraw_now()

    def projectClicked_(self, sender) -> None:
        index = sender.tag()
        if 0 <= index < len(self.projects):
            name = self.projects[index].name
            self.opened_project = None if self.opened_project == name else name
        self._redraw_now()

    def cleanupClicked_(self, _sender) -> None:
        if self.stale:
            self.open_link(cleanup_link(self.stale, datetime.now(timezone.utc)))

    def entryClicked_(self, sender) -> None:
        index = sender.tag()
        if 0 <= index < len(self.entries):
            self.opener(self.entries[index])

    @objc.python_method
    def toggle_visible(self) -> None:
        if self.window.isVisible():
            self.window.orderOut_(None)
        else:
            self.window.orderFrontRegardless()

    # ---------- 位置记忆 ----------
    @objc.python_method
    def _saved_top_left(self):
        saved = NSUserDefaults.standardUserDefaults().arrayForKey_(config.PANEL_POSITION_KEY)
        if saved and len(saved) == 2:
            return (float(saved[0]), float(saved[1]))
        screen = NSScreen.mainScreen().visibleFrame()
        margin = config.PANEL_MARGIN_FROM_EDGE
        return (screen.origin.x + screen.size.width - config.PANEL_WIDTH - margin,
                screen.origin.y + screen.size.height - margin)

    @objc.python_method
    def _save_top_left(self, x: float, top: float) -> None:
        NSUserDefaults.standardUserDefaults().setObject_forKey_([x, top], config.PANEL_POSITION_KEY)
