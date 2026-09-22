"""办公室里会动的东西：小人走路、搬桌子、宠物乱逛。纯函数 + 不可变状态，每帧 step 一次。

坐标单位是像素画格子。小人从左下角的门进来，沿左侧过道上楼，沿本排走廊横着走，再走到椅子前坐下。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, replace

from .pixel import AISLE_W, BOTTOM_H, CORRIDOR_Y, DESK_H, DESK_W, DESK_Y_IN_CELL, MARGIN, Desk, Scene, Seat

SPEED = 3                 # 每帧走几格
DESK_SPEED = 4
PC_POP_FRAMES = 5         # 桌子到位后，电脑一台台冒出来的间隔
WANDER_EVERY = 240        # 闲着的人大约每多少帧起身溜达一次（配合 6fps ≈ 40 秒）
PET_TURN_EVERY = 24
PET_SPEED = 1.5
Point = tuple[float, float]


@dataclass(frozen=True)
class Actor:
    id: str
    x: float
    y: float
    path: tuple[Point, ...]        # 还没走完的路点
    facing: str = "down"           # down | up | left | right
    seat: Seat | None = None       # 座位；None 表示走向门口后消失
    skin: int = 0
    leaving: bool = False
    wander_clock: int = 0

    @property
    def walking(self) -> bool:
        return bool(self.path)


@dataclass(frozen=True)
class MovingDesk:
    name: str
    x: float                       # 当前 x，目标是 desk.x
    y: float
    target_x: float
    mover_skin: int
    docked_frames: int = -1        # 到位后过了几帧，-1 = 还在路上

    @property
    def docked(self) -> bool:
        return self.docked_frames >= 0


@dataclass(frozen=True)
class Pet:
    x: float
    y: float
    facing: str = "right"
    clock: int = 0


@dataclass(frozen=True)
class SimState:
    actors: dict[str, Actor]
    desks: dict[str, MovingDesk]   # 只放正在搬或刚到位的桌子；稳定的桌子不在这里
    known_desks: frozenset[str]
    pet: Pet | None
    frame: int = 0


def empty_state() -> SimState:
    return SimState({}, {}, frozenset(), None)


def door(scene: Scene) -> Point:
    return (-16.0, float(scene.height - BOTTOM_H + 4))


def route(scene: Scene, start: Point, end: Point) -> tuple[Point, ...]:
    """先横到过道，再竖到目标排的走廊，再横到目标 x，再竖到目标点。"""
    aisle_x = float(AISLE_W // 2 - 8)
    row_of = lambda y: max(0, min(len(_rows(scene)) - 1, int((y - _rows(scene)[0]) // DESK_H))) if _rows(scene) else 0
    corridor = lambda y: float(_rows(scene)[row_of(y)] + CORRIDOR_Y) if _rows(scene) else end[1]
    return tuple(p for p in ((aisle_x, start[1]), (aisle_x, corridor(end[1])), (end[0], corridor(end[1])), end) if p != start)


def _rows(scene: Scene) -> list[int]:
    return sorted({d.y for d in scene.desks})


def sync(state: SimState, scene: Scene, rng: random.Random | None = None) -> SimState:
    """场景变了：新座位的人从门进来，没座位的人走向门，新桌子安排搬运。"""
    rng = rng or random.Random(state.frame)
    seats = {s.entry.desktop_id: s for d in scene.desks for s in d.seats if s.pose != "empty"}
    actors = dict(state.actors)
    for sid, seat in seats.items():
        old = actors.get(sid)
        if old is None:
            start = door(scene)
            actors[sid] = Actor(sid, start[0], start[1], route(scene, start, (float(seat.x), float(seat.y))), "up", seat, seat.skin)
        elif old.seat is None or (old.seat.x, old.seat.y) != (seat.x, seat.y):
            actors[sid] = replace(old, seat=seat, leaving=False, path=route(scene, (old.x, old.y), (float(seat.x), float(seat.y))))
        else:
            actors[sid] = replace(old, seat=seat)
    for sid, actor in list(actors.items()):
        if sid not in seats and not actor.leaving:
            actors[sid] = replace(actor, seat=None, leaving=True, path=route(scene, (actor.x, actor.y), door(scene)))
    desks = {k: v for k, v in state.desks.items() if any(d.name == k for d in scene.desks)}
    for desk in scene.desks:
        if desk.name not in state.known_desks and desk.name not in desks:
            desks[desk.name] = MovingDesk(desk.name, -DESK_W - 20.0, float(desk.y), float(desk.x), rng.randrange(6))
    pet = state.pet or Pet(float(scene.width // 2), float(scene.height - BOTTOM_H + 6))
    return SimState(actors, desks, frozenset(d.name for d in scene.desks), pet, state.frame)


def step(state: SimState, scene: Scene, rng: random.Random | None = None) -> SimState:
    rng = rng or random.Random(state.frame)
    actors = {}
    for sid, actor in state.actors.items():
        moved = _advance(actor)
        if moved.leaving and not moved.walking:
            continue                                   # 走到门口，消失
        actors[sid] = _maybe_wander(moved, scene, rng)
    desks = {name: _advance_desk(d) for name, d in state.desks.items()}
    desks = {name: d for name, d in desks.items() if d.docked_frames < PC_POP_FRAMES * 4}
    return SimState(actors, desks, state.known_desks, _advance_pet(state.pet, scene, rng), state.frame + 1)


def _advance(actor: Actor) -> Actor:
    if not actor.path:
        return actor
    tx, ty = actor.path[0]
    dx, dy = tx - actor.x, ty - actor.y
    dist = abs(dx) + abs(dy)
    facing = ("right" if dx > 0 else "left") if abs(dx) >= abs(dy) else ("down" if dy > 0 else "up")
    if dist <= SPEED:
        rest = actor.path[1:]
        return replace(actor, x=tx, y=ty, path=rest, facing=facing if rest else ("up" if actor.seat and actor.seat.pose == "typing" else "down"))
    step_x = SPEED * (dx / dist) if dist else 0
    step_y = SPEED * (dy / dist) if dist else 0
    return replace(actor, x=actor.x + step_x, y=actor.y + step_y, facing=facing)


def _maybe_wander(actor: Actor, scene: Scene, rng: random.Random) -> Actor:
    """闲着（看书）的人偶尔起身去盆栽那儿转一圈再回来。"""
    if actor.walking or actor.seat is None or actor.seat.pose != "sleep":
        return actor
    clock = actor.wander_clock + 1
    if clock < WANDER_EVERY or rng.random() > 0.2:
        return replace(actor, wander_clock=clock)
    plant = (float(MARGIN + 18), float(scene.height - BOTTOM_H - 2))
    seat = (float(actor.seat.x), float(actor.seat.y))
    return replace(actor, wander_clock=0, path=route(scene, (actor.x, actor.y), plant) + route(scene, plant, seat))


def _advance_desk(desk: MovingDesk) -> MovingDesk:
    if desk.docked:
        return replace(desk, docked_frames=desk.docked_frames + 1)
    nx = min(desk.target_x, desk.x + DESK_SPEED)
    return replace(desk, x=nx, docked_frames=0 if nx >= desk.target_x else -1)


def _advance_pet(pet: Pet | None, scene: Scene, rng: random.Random) -> Pet | None:
    if pet is None:
        return None
    clock = pet.clock + 1
    facing = pet.facing
    if clock >= PET_TURN_EVERY:
        clock, facing = 0, rng.choice(["left", "right", "left", "right", "stay"])
    if facing == "stay":
        return replace(pet, clock=clock, facing=facing)
    nx = pet.x + (PET_SPEED if facing == "right" else -PET_SPEED)
    lo, hi = MARGIN + 18, scene.width - MARGIN - 44
    if nx < lo or nx > hi:
        facing = "right" if nx < lo else "left"
        nx = max(lo, min(hi, nx))
    return replace(pet, x=nx, clock=clock, facing=facing)


def pcs_visible(desk: MovingDesk | None) -> int:
    """搬进来的桌子上，电脑一台台冒出来；稳定桌子直接 3 台。"""
    if desk is None:
        return 3
    if not desk.docked:
        return 0
    return min(3, desk.docked_frames // PC_POP_FRAMES)


def desk_x(desk: Desk, moving: MovingDesk | None) -> float:
    return moving.x if moving is not None else float(desk.x)
