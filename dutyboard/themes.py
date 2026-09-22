"""浮窗风格。纯数据，不 import AppKit，方便测试；panel.py 负责把它翻译成 NSColor / NSFont。"""
from __future__ import annotations

from dataclasses import dataclass, field

RGBA = tuple[float, float, float, float]

DEFAULT_ICONS = {"running": "🟢", "waiting": "🟡", "permission": "🟠", "idle": "⚪", "overdue": "❗", "project": "📁",
                 "project_open": "📂", "cleanup": "🗑", "entry": "·"}
TERMINAL_ICONS = {"running": "[~]", "waiting": "[!]", "permission": "[?]", "idle": "[ ]", "overdue": "[!!]",
                  "project": "+", "project_open": "-", "cleanup": "#", "entry": " "}


@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    material: str | None            # "hud" | "popover" | "sidebar" | None（None 用纯色底）
    background: RGBA | None         # material 为 None 时的底色
    corner: int
    font: str                       # "system" | "mono" | "rounded" | "serif"
    font_size: int
    text: RGBA
    header: RGBA
    muted: RGBA
    icons: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ICONS))


THEMES: dict[str, Theme] = {
    "hud": Theme("hud", "极简 · 深毛玻璃", "hud", None, 12, "system", 12,
                 (0.92, 0.92, 0.92, 1), (1, 1, 1, 1), (0.6, 0.6, 0.6, 1)),
    "frost": Theme("frost", "轻盈 · 浅毛玻璃", "popover", None, 14, "rounded", 12,
                   (0.15, 0.15, 0.17, 1), (0.05, 0.05, 0.08, 1), (0.45, 0.45, 0.5, 1)),
    "paper": Theme("paper", "纸 · 暖白便签", None, (0.99, 0.96, 0.88, 0.97), 6, "serif", 13,
                   (0.25, 0.2, 0.15, 1), (0.55, 0.25, 0.1, 1), (0.55, 0.5, 0.45, 1)),
    "office": Theme("office", "像素办公室 · 小人值班", None, (0.13, 0.14, 0.18, 0.98), 8, "mono", 11,
                    (0.82, 0.84, 0.92, 1), (0.95, 0.95, 1, 1), (0.55, 0.57, 0.68, 1)),
    "terminal": Theme("terminal", "终端 · 黑底绿字", None, (0.04, 0.05, 0.04, 0.94), 4, "mono", 12,
                      (0.55, 0.95, 0.6, 1), (0.75, 1, 0.8, 1), (0.35, 0.6, 0.4, 1), dict(TERMINAL_ICONS)),
}


def resolve_theme(key: str | None, default: str) -> Theme:
    """名字不认识就回默认，别让一条坏的偏好设置把浮窗弄没了。"""
    return THEMES.get(key or "", THEMES[default])


def theme_choices() -> tuple[tuple[str, str], ...]:
    return tuple((t.key, t.label) for t in THEMES.values())
