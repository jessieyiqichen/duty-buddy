"""像素办公室的场景模型：把项目和会话排成桌子和小人。纯函数，单位是像素画格子（1 格 = 1 素材像素）。

布局（一张桌子 48 宽）：
  顶部一条墙；每个项目一张桌子，桌上三台电脑，桌前三把椅子；
  在跑的人背对你打字（能看见屏幕亮），做完的人转过身举气泡；
  底部一条：垃圾桶 + 数字 = 可归档的会话，旁边趴着一只宠物，点垃圾桶它就跑一趟。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .browser import Entry, ProjectView
from .config import OFFICE_COLS, OFFICE_MAX_DESKS, OVERDUE_SECONDS

DESK_W, DESK_H, DESK_GAP = 48, 92, 4
MARGIN, WALL_H, BOTTOM_H = 8, 32, 40
AISLE_W = 20                      # 左侧过道，小人上下楼走这里
CORRIDOR_Y = 60                   # 每排桌子下方的走廊（小人头顶在格子里的 y）
TOP_ZONE = 18                     # 桌子上方留给显示器探出来的高度
DESK_Y_IN_CELL = TOP_ZONE         # 桌面精灵在格子里的 y
SEAT_Y_IN_CELL = 40               # 小人在格子里的 y
SEATS_PER_DESK = 3
SEAT_XS = (0, 16, 32)
PERSON_W, PERSON_H = 16, 32
DUSTY_SECONDS = 7 * 24 * 3600
POSES = {"🟢": "typing", "🟡": "wave", "🟠": "ask", "⚪": "sleep", "·": "empty"}
LABEL_CHARS = 8
BUBBLE_H, BUBBLE_STACK = 9, 10


@dataclass(frozen=True)
class Seat:
    x: int
    y: int
    pose: str            # typing | wave | ask | jump | sleep | empty
    label: str | None    # 气泡里的字
    entry: Entry
    skin: int = 0        # 用第几张角色图，同一个会话永远同一个人


@dataclass(frozen=True)
class Desk:
    x: int
    y: int
    name: str
    seats: tuple[Seat, ...]
    dusty: bool = False   # 全是空椅子而且很久没人来过，整张桌子褪色


@dataclass(frozen=True)
class Scene:
    width: int
    height: int
    desks: tuple[Desk, ...]
    pile: int            # 该归档的会话数
    pile_x: int          # 垃圾桶位置
    pile_y: int
    hidden_desks: int    # 放不下没画出来的项目数


def pose_for(entry: Entry, now: datetime) -> str:
    pose = POSES.get(entry.icon, "empty")
    if pose == "wave" and entry.at and (now - entry.at).total_seconds() > OVERDUE_SECONDS:
        return "jump"
    return pose


def skin_for(entry: Entry, count: int = 6) -> int:
    return sum(ord(ch) for ch in entry.desktop_id) % count


def build_scene(projects: tuple[ProjectView, ...], stale: int, now: datetime,
                cols: int = OFFICE_COLS, max_desks: int = OFFICE_MAX_DESKS) -> Scene:
    shown = projects[:max_desks]
    width = AISLE_W + MARGIN + cols * DESK_W + (cols - 1) * DESK_GAP
    desks = tuple(_desk(i, view, now, cols) for i, view in enumerate(shown))
    rows = max(1, (len(shown) + cols - 1) // cols)
    body_bottom = WALL_H + rows * DESK_H
    return Scene(width, body_bottom + BOTTOM_H, desks, stale, width - MARGIN - 16, body_bottom + 8,
                 len(projects) - len(shown))


def _desk(index: int, view: ProjectView, now: datetime, cols: int) -> Desk:
    x = AISLE_W + (index % cols) * (DESK_W + DESK_GAP)
    y = WALL_H + (index // cols) * DESK_H
    seats = []
    for slot, entry in enumerate(view.entries[:SEATS_PER_DESK]):
        pose = pose_for(entry, now)
        label = entry.title[:LABEL_CHARS] if pose in ("wave", "jump", "ask") else None
        seats.append(Seat(x + SEAT_XS[slot], y + SEAT_Y_IN_CELL, pose, label, entry, skin_for(entry)))
    ages = [(now - e.at).total_seconds() for e in view.entries if e.at]
    dusty = all(s.pose == "empty" for s in seats) and bool(ages) and min(ages) > DUSTY_SECONDS
    return Desk(x, y, view.name, tuple(seats), dusty)


def seat_at(scene: Scene, ux: int, uy: int) -> Seat | None:
    """点击命中：格子坐标落在哪个座位（一个小人 16×32）范围里。"""
    for desk in scene.desks:
        for seat in desk.seats:
            if seat.x <= ux < seat.x + PERSON_W and seat.y - 12 <= uy < seat.y + PERSON_H:
                return seat
    return None


def pile_hit(scene: Scene, ux: int, uy: int) -> bool:
    return scene.pile > 0 and scene.pile_x - 24 <= ux < scene.pile_x + 18 and scene.pile_y - 4 <= uy < scene.pile_y + 24


@dataclass(frozen=True)
class Bubble:
    seat: Seat
    x: int
    y: int
    w: int
    text: str


def bubble_width(text: str) -> int:
    return max(8, sum(5 if ord(ch) > 255 else 3 for ch in text) + 3)


def layout_bubbles(desk: Desk, scene_width: int) -> tuple[Bubble, ...]:
    """同一张桌子上几个人同时举气泡时，后面的往上摞一层，别互相盖住；右边出界的往左挪。"""
    placed: list[Bubble] = []
    for seat in desk.seats:
        if not seat.label:
            continue
        text = ("? " + seat.label) if seat.pose == "ask" else seat.label
        w = bubble_width(text)
        x = min(seat.x - 1, scene_width - w - 1)
        y = seat.y - 11
        while any(b.y == y and b.x < x + w and x < b.x + b.w for b in placed):
            y -= BUBBLE_STACK
        placed.append(Bubble(seat, x, y, w, text))
    return tuple(placed)
