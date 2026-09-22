"""桌面浮窗：无边框、永远置顶、可拖动、跟着值班表刷新。点标题栏折叠/展开。"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

import objc
from AppKit import (NSBackingStoreBuffered, NSButton, NSColor, NSFloatingWindowLevel, NSFont,
                    NSMakeRect, NSPanel, NSScreen, NSTextAlignmentLeft, NSTextField, NSUserDefaults,
                    NSVisualEffectBlendingModeBehindWindow, NSVisualEffectMaterialHUDWindow,
                    NSVisualEffectStateActive, NSVisualEffectView,
                    NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorStationary,
                    NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel)
from Foundation import NSObject

from . import config
from .labels import row_label
from .sessions import SessionInfo

log = logging.getLogger("dutyboard.panel")


def panel_height(group_sizes: tuple[int, ...], collapsed: bool) -> int:
    """纯函数：给定每个项目下的行数，算浮窗总高度。"""
    height = config.PANEL_PADDING * 2 + config.PANEL_HEADER_HEIGHT
    if collapsed:
        return height
    for size in group_sizes:
        height += config.PANEL_ROW_HEIGHT * (size + 1) + config.PANEL_GROUP_GAP
    if not group_sizes:
        height += config.PANEL_ROW_HEIGHT
    return height


class FloatingPanel(NSObject):
    """PyObjC 的 target 必须是 NSObject 子类，所以浮窗控制器本身就是一个 NSObject。"""

    def initWithOpener_(self, opener: Callable[[SessionInfo], None]):
        self = objc.super(FloatingPanel, self).init()
        if self is None:
            return None
        self.opener = opener
        self.rows: list[SessionInfo] = []
        self.collapsed = False
        self.window = self._make_window()
        self.content = self._make_content()
        self.window.setContentView_(self.content)
        self.window.orderFrontRegardless()
        return self

    # ---------- 构建 ----------
    @objc.python_method
    def _make_window(self) -> NSPanel:
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        frame = NSMakeRect(0, 0, config.PANEL_WIDTH, panel_height((), False))
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
    def render(self, grouped: dict[str, tuple[SessionInfo, ...]], now: datetime, headline: str) -> None:
        try:
            self._render(grouped, now, headline)
        except Exception:  # 浮窗画坏了不能拖死整个进程
            log.exception("浮窗刷新失败")

    @objc.python_method
    def _render(self, grouped: dict[str, tuple[SessionInfo, ...]], now: datetime, headline: str) -> None:
        self.rows = [info for rows in grouped.values() for info in rows]
        height = panel_height(tuple(len(r) for r in grouped.values()), self.collapsed)
        self._resize_keeping_top_left(height)
        for sub in list(self.content.subviews()):
            sub.removeFromSuperview()
        y = height - config.PANEL_PADDING - config.PANEL_HEADER_HEIGHT
        self._add_header(y, f"Claude 值班表   {headline}")
        if self.collapsed:
            return
        y -= config.PANEL_GROUP_GAP
        if not grouped:
            y -= config.PANEL_ROW_HEIGHT
            self._add_label(y, "没有正在运行的 session", bold=False)
        tag = 0
        for project, rows in grouped.items():
            y -= config.PANEL_ROW_HEIGHT
            self._add_label(y, f"📁 {project}", bold=True)
            for info in rows:
                y -= config.PANEL_ROW_HEIGHT
                self._add_row(y, row_label(info, now, config.PANEL_PROMPT_CHARS), tag)
                tag += 1
            y -= config.PANEL_GROUP_GAP

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
    def _add_label(self, y: float, text: str, bold: bool) -> None:
        width = config.PANEL_WIDTH - config.PANEL_PADDING * 2
        label = NSTextField.labelWithString_(text)
        label.setFrame_(NSMakeRect(config.PANEL_PADDING, y, width, config.PANEL_ROW_HEIGHT))
        size = config.PANEL_FONT_SIZE
        label.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
        label.setLineBreakMode_(4)  # NSLineBreakByTruncatingTail
        self.content.addSubview_(label)

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

    def toggleCollapsed_(self, _sender) -> None:
        self.collapsed = not self.collapsed

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
