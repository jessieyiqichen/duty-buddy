"""像素办公室的场景模型：把项目和会话排成桌子和小人。纯函数，单位是像素画格子（1 格 = 1 素材像素）。

布局（一座岛 48 宽 64 高的大方桌）：
  顶部一条墙；每个项目一座四人岛：北边两人面对桌子（看见脸和显示器背面），南边两人背对你（看见屏幕）；
  做完的人转过身举气泡；
  底部一条：垃圾桶 + 数字 = 可归档的会话，旁边趴着一只宠物，点垃圾桶它就跑一趟。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .browser import Entry, ProjectView
from .config import OFFICE_COLS, OFFICE_MAX_DESKS, OVERDUE_SECONDS

DESK_W, DESK_H, DESK_GAP = 48, 124, 4
MARGIN, WALL_H, BOTTOM_H = 8, 32, 56
ROW_TOP_GAP = 12                  # 第一排岛上方留给北边人气泡的空间
AISLE_W = 20                      # 左侧过道，小人上下楼走这里
CORRIDOR_Y = 92                   # 每排岛下方的走廊（小人头顶在格子里的 y）
TABLE_Y_IN_CELL = 24              # 方桌精灵在格子里的 y（桌子 48×64）
SEATS_PER_DESK = 4
SEAT_SLOTS = ((4, 0, "n"), (28, 0, "n"), (4, 70, "s"), (28, 70, "s"))   # (dx, dy, 北/南)
PERSON_W, PERSON_H = 16, 32
DUSTY_SECONDS = 7 * 24 * 3600
POSES = {"🟢": "typing", "🟡": "wave", "🟠": "ask", "⚪": "sleep", "·": "empty"}
LABEL_CHARS = 8
BUBBLE_H, BUBBLE_STACK = 9, 10


@dataclass(frozen=True)
class Seat:
    x: int
    y: int
    pose: str            # typing | wave | ask | jump | sleep | parked | empty
    label: str | None    # 气泡里的字
    entry: Entry
    skin: int = 0        # 用第几张角色图，同一个会话永远同一个人
    side: str = "s"      # n = 桌子北边（面对桌子，我们看见脸）；s = 南边（背对我们）


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
    if pose in ("wave", "ask") and entry.seen:
        return "parked"                      # 看过了：安安静静坐着，不举手不蹦
    if pose == "wave" and entry.at and (now - entry.at).total_seconds() > OVERDUE_SECONDS:
        return "jump"
    return pose


def live_projects(projects: tuple[ProjectView, ...]) -> tuple[ProjectView, ...]:
    """办公室只画进程活着的会话，只摆有活人的岛。"""
    kept = []
    for view in projects:
        alive = tuple(e for e in view.entries if e.live)
        if alive:
            kept.append(ProjectView(view.name, view.live, alive))
    return tuple(kept)


def skin_for(entry: Entry, count: int = 6) -> int:
    return sum(ord(ch) for ch in entry.desktop_id) % count


def build_scene(projects: tuple[ProjectView, ...], stale: int, now: datetime,
                cols: int = OFFICE_COLS, max_desks: int = OFFICE_MAX_DESKS) -> Scene:
    shown = live_projects(projects)[:max_desks]
    width = AISLE_W + MARGIN + cols * DESK_W + (cols - 1) * DESK_GAP
    desks = tuple(_desk(i, view, now, cols) for i, view in enumerate(shown))
    rows = max(1, (len(shown) + cols - 1) // cols)
    body_bottom = WALL_H + ROW_TOP_GAP + rows * DESK_H
    return Scene(width, body_bottom + BOTTOM_H, desks, stale, width - MARGIN - 18, body_bottom + 22,
                 len(projects) - len(shown))


def _desk(index: int, view: ProjectView, now: datetime, cols: int) -> Desk:
    x = AISLE_W + (index % cols) * (DESK_W + DESK_GAP)
    y = WALL_H + ROW_TOP_GAP + (index // cols) * DESK_H
    seats = []
    for (dx, dy, side), entry in zip(SEAT_SLOTS, view.entries[:SEATS_PER_DESK]):
        pose = pose_for(entry, now)
        label = entry.title[:LABEL_CHARS] if pose in ("wave", "jump", "ask") else None
        seats.append(Seat(x + dx, y + dy, pose, label, entry, skin_for(entry), side))
    return Desk(x, y, view.name, tuple(seats), False)


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
