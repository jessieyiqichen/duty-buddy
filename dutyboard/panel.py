"""桌面浮窗：待办队列形态。只列等你的 session，其余压成一行数字，点那行展开。
无边框、永远置顶、可拖动，点标题折叠。外观由 themes.py 里的 Theme 决定。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

import objc
from AppKit import (NSAttributedString, NSScrollView, NSBackingStoreBuffered, NSButton, NSColor, NSFloatingWindowLevel, NSFont,
                    NSFontAttributeName, NSFontDescriptorSystemDesignMonospaced, NSFontDescriptorSystemDesignRounded,
                    NSFontDescriptorSystemDesignSerif, NSForegroundColorAttributeName, NSMakeRect,
                    NSMutableParagraphStyle, NSPanel, NSParagraphStyleAttributeName, NSScreen, NSTextAlignmentLeft,
                    NSUserDefaults, NSView, NSVisualEffectBlendingModeBehindWindow, NSVisualEffectMaterialHUDWindow,
                    NSVisualEffectMaterialPopover, NSVisualEffectMaterialSidebar, NSVisualEffectStateActive,
                    NSVisualEffectView, NSWindowCollectionBehaviorCanJoinAllSpaces,
                    NSWindowCollectionBehaviorStationary, NSWindowStyleMaskBorderless,
                    NSWindowStyleMaskNonactivatingPanel)
from Foundation import NSObject

from . import config
from .browser import Entry, ProjectView, build_projects
from .cleanup import cleanup_link, stale_candidates
from .desktop import DesktopSession
from .labels import age_label, headline_label, queue_row_label, summary_label
from .office import OfficeView
from .pixel import build_scene
from .queue import QueueView, build_queue, is_overdue
from .sessions import SessionInfo
from .themes import Theme, resolve_theme

log = logging.getLogger("dutyboard.panel")
MATERIALS = {"hud": NSVisualEffectMaterialHUDWindow, "popover": NSVisualEffectMaterialPopover,
             "sidebar": NSVisualEffectMaterialSidebar}
DESIGNS = {"rounded": NSFontDescriptorSystemDesignRounded, "serif": NSFontDescriptorSystemDesignSerif,
           "mono": NSFontDescriptorSystemDesignMonospaced}
ROW, GAP, PAD = config.PANEL_ROW_HEIGHT, config.PANEL_GROUP_GAP, config.PANEL_PADDING


def panel_height(attention: int, others_shown: int, has_summary: bool, collapsed: bool,
                 project_rows: int = 0) -> int:
    """纯函数：浮窗总高度 = 标题 + 等你的行 + 汇总行 + 展开的其他行 + 项目区的行。"""
    height = PAD * 2 + config.PANEL_HEADER_HEIGHT
    if collapsed:
        return height
    rows = attention + others_shown + (1 if has_summary else 0)
    height += ROW * rows + (GAP if rows else 0)
    return height + ROW * project_rows + (GAP if project_rows else 0)


def project_rows(projects: tuple[ProjectView, ...], show: bool, opened: str | None) -> int:
    """项目区占几行：1 行开关；展开后每个项目 1 行，打开的那个项目再加它的会话行。"""
    if not show:
        return 1
    return 1 + len(projects) + sum(len(v.entries) for v in projects if v.name == opened)


class FloatingPanel(NSObject):
    """PyObjC 的 target 必须是 NSObject 子类，所以浮窗控制器本身就是一个 NSObject。"""

    def initWithOpener_linkOpener_(self, opener: Callable[[SessionInfo | Entry], None], open_link: Callable[[str], None]):
        self = objc.super(FloatingPanel, self).init()
        if self is None:
            return None
        self.opener, self.open_link = opener, open_link
        self.collapsed = self.show_others = self.show_projects = False
        self.opened_project: str | None = None
        self.rows: list[SessionInfo] = []
        self.entries: list[Entry] = []
        self.projects: tuple[ProjectView, ...] = ()
        self.stale: tuple[DesktopSession, ...] = ()
        self.last_infos: tuple[SessionInfo, ...] = ()
        self.last_desktop: tuple[DesktopSession, ...] = ()
        self.office: OfficeView | None = None
        self.office_scroll: NSScrollView | None = None
        self.theme = resolve_theme(NSUserDefaults.standardUserDefaults().stringForKey_(config.THEME_KEY), config.DEFAULT_THEME)
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
    def _make_content(self) -> NSView:
        bounds = self.window.contentView().bounds()
        if self.theme.material:
            view = NSVisualEffectView.alloc().initWithFrame_(bounds)
            view.setMaterial_(MATERIALS[self.theme.material])
            view.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
            view.setState_(NSVisualEffectStateActive)
        else:
            view = NSView.alloc().initWithFrame_(bounds)
        view.setWantsLayer_(True)
        if self.theme.background:
            view.layer().setBackgroundColor_(_color(self.theme.background).CGColor())
        view.layer().setCornerRadius_(self.theme.corner)
        view.layer().setMasksToBounds_(True)
        return view

    @objc.python_method
    def set_theme(self, key: str) -> None:
        self.theme = resolve_theme(key, config.DEFAULT_THEME)
        NSUserDefaults.standardUserDefaults().setObject_forKey_(self.theme.key, config.THEME_KEY)
        self.content = self._make_content()
        self.window.setContentView_(self.content)
        self._redraw_now()

    # ---------- 刷新 ----------
    @objc.python_method
    def render(self, infos: tuple[SessionInfo, ...], now: datetime,
               desktop: tuple[DesktopSession, ...] = ()) -> None:
        self.last_infos, self.last_desktop = infos, desktop
        try:
            self.projects = build_projects(desktop, infos, now, self.theme.icons)
            self.stale = stale_candidates(desktop, infos, now)
            self._render(build_queue(infos, now), now)
        except Exception:  # 浮窗画坏了不能拖死整个进程
            log.exception("浮窗刷新失败")

    @objc.python_method
    def _render(self, queue: QueueView, now: datetime) -> None:
        if self.theme.key == "office":
            self._render_office(queue, now)
            return
        summary = summary_label(queue.running, queue.idle, self.show_others, len(queue.parked))
        others = (queue.others + queue.parked) if (self.show_others and summary) else ()
        self.rows = [*queue.attention, *others]
        prows = project_rows(self.projects, self.show_projects, self.opened_project) + (1 if self.stale else 0)
        height = panel_height(len(queue.attention), len(others), bool(summary), self.collapsed, prows)
        self._resize_keeping_top_left(height)
        for sub in list(self.content.subviews()):
            sub.removeFromSuperview()
        y = height - PAD - config.PANEL_HEADER_HEIGHT
        self._add(y, "Claude 值班表   " + headline_label(len(queue.attention), queue.running),
                  "toggleCollapsed:", 0, config.PANEL_HEADER_HEIGHT, self.theme.header, bold=True, bigger=True)
        if self.collapsed:
            return
        y -= GAP
        for tag, info in enumerate(queue.attention):
            y -= ROW
            self._add(y, "    " + queue_row_label(info, now, is_overdue(info, now), self.theme.icons), "rowClicked:", tag)
        if summary:
            y -= ROW
            self._add(y, summary, "toggleOthers:", 0, color=self.theme.muted)
        for offset, info in enumerate(others):
            y -= ROW
            self._add(y, "    " + queue_row_label(info, now, False, self.theme.icons), "rowClicked:", len(queue.attention) + offset)
        self._render_projects(y - GAP, now)

    @objc.python_method
    def _render_office(self, queue: QueueView, now: datetime) -> None:
        scene = build_scene(self.projects, len(self.stale), now)
        view_h = min(scene.height * config.PIXEL_SCALE, config.OFFICE_VIEW_MAX_HEIGHT)
        body = 0 if self.collapsed else view_h + GAP
        height = PAD * 2 + config.PANEL_HEADER_HEIGHT + body
        self._resize_keeping_top_left(height)
        for sub in list(self.content.subviews()):
            sub.removeFromSuperview()
        self._add(height - PAD - config.PANEL_HEADER_HEIGHT, "Claude 值班表   " + headline_label(len(queue.attention), queue.running),
                  "toggleCollapsed:", 0, config.PANEL_HEADER_HEIGHT, self.theme.header, bold=True, bigger=True)
        if self.collapsed:
            return
        if self.office is None:
            self.office = OfficeView.alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
            self.office.on_seat = self.opener
            self.office.on_pile = lambda: self.open_link(cleanup_link(self.stale, datetime.now(timezone.utc)))
            self.office_scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
            self.office_scroll.setDocumentView_(self.office)
            self.office_scroll.setDrawsBackground_(False)
            self.office_scroll.setHasVerticalScroller_(True)
            self.office_scroll.setScrollerStyle_(1)                    # NSScrollerStyleOverlay
        self.office.setFrame_(NSMakeRect(0, 0, scene.width * config.PIXEL_SCALE, scene.height * config.PIXEL_SCALE))
        self.office.set_scene(scene)
        self.office_scroll.setFrame_(NSMakeRect(PAD, PAD, scene.width * config.PIXEL_SCALE, view_h))
        self.content.addSubview_(self.office_scroll)

    @objc.python_method
    def _render_projects(self, y: float, now: datetime) -> None:
        icons = self.theme.icons
        y -= ROW
        arrow = "▾" if self.show_projects else "▸"
        self._add(y, f"{arrow} 按项目找会话 · {len(self.projects)} 个项目", "toggleProjects:", 0, color=self.theme.muted)
        if self.show_projects:
            self.entries = []
            for index, view in enumerate(self.projects):
                y -= ROW
                mark = icons["project_open"] if view.name == self.opened_project else icons["project"]
                count = f" · {view.live} 个在跑" if view.live else f" · {len(view.entries)} 个"
                self._add(y, f"    {mark} {view.name}{count}", "projectClicked:", index)
                if view.name != self.opened_project:
                    continue
                for entry in view.entries:
                    y -= ROW
                    where = "  Cowork" if entry.source == "cowork" else ""
                    label = f"        {entry.icon} {entry.title[:config.TITLE_MAX_CHARS]} · {age_label(entry.at, now)}{where}"
                    self._add(y, label, "entryClicked:", len(self.entries))
                    self.entries.append(entry)
        if self.stale:
            y -= ROW
            self._add(y, f"{icons['cleanup']} 可归档 · {len(self.stale)} 个超过 7 天没动 · 点我交给 Claude 清",
                      "cleanupClicked:", 0, color=self.theme.muted)

    @objc.python_method
    def _resize_keeping_top_left(self, height: int) -> None:
        frame = self.window.frame()
        top = frame.origin.y + frame.size.height
        self.window.setFrame_display_(NSMakeRect(frame.origin.x, top - height, config.PANEL_WIDTH, height), True)
        self.content.setFrame_(self.window.contentView().bounds())
        self._save_top_left(frame.origin.x, top)

    @objc.python_method
    def _add(self, y: float, text: str, selector: str, tag: int, height: int = ROW,
             color=None, bold: bool = False, bigger: bool = False) -> None:
        button = NSButton.alloc().initWithFrame_(NSMakeRect(PAD, y, config.PANEL_WIDTH - PAD * 2, height))
        button.setBordered_(False)
        button.setAlignment_(NSTextAlignmentLeft)
        button.setLineBreakMode_(4)  # NSLineBreakByTruncatingTail
        button.setAttributedTitle_(_attributed(text, _color(color or self.theme.text), self._font(bold, bigger)))
        button.setTarget_(self)
        button.setAction_(selector)
        button.setTag_(tag)
        self.content.addSubview_(button)

    @objc.python_method
    def _font(self, bold: bool, bigger: bool) -> NSFont:
        size = self.theme.font_size + (1 if bigger else 0)
        base = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
        design = DESIGNS.get(self.theme.font)
        if design is None:
            return base
        return NSFont.fontWithDescriptor_size_(base.fontDescriptor().fontDescriptorWithDesign_(design), size) or base

    # ---------- 事件 ----------
    @objc.python_method
    def _redraw_now(self) -> None:
        self.render(self.last_infos, datetime.now(timezone.utc), self.last_desktop)

    def rowClicked_(self, sender) -> None:
        index = sender.tag()
        if 0 <= index < len(self.rows):
            self.opener(self.rows[index])

    def entryClicked_(self, sender) -> None:
        index = sender.tag()
        if 0 <= index < len(self.entries):
            self.opener(self.entries[index])

    def cleanupClicked_(self, _sender) -> None:
        if self.stale:
            self.open_link(cleanup_link(self.stale, datetime.now(timezone.utc)))

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


def _color(rgba) -> NSColor:
    r, g, b, a = rgba
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, a)


def _attributed(text: str, color: NSColor, font: NSFont) -> NSAttributedString:
    style = NSMutableParagraphStyle.alloc().init()
    style.setAlignment_(NSTextAlignmentLeft)
    style.setLineBreakMode_(4)
    attrs = {NSForegroundColorAttributeName: color, NSFontAttributeName: font, NSParagraphStyleAttributeName: style}
    return NSAttributedString.alloc().initWithString_attributes_(text, attrs)
