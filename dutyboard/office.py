"""像素办公室的绘制和动画：一个 NSView，用 pixel-agents 的素材（CC0 / MIT）拼场景，定时器翻帧。"""
from __future__ import annotations

import logging
from typing import Callable

import objc
from AppKit import (NSBezierPath, NSColor, NSCompositingOperationSourceOver, NSFont, NSFontAttributeName,
                    NSForegroundColorAttributeName, NSGraphicsContext, NSImage, NSImageInterpolationNone, NSMakeRect,
                    NSString, NSView)
from Foundation import NSTimer

from . import config
from .browser import Entry
from . import sim
from .pixel import (BOTTOM_H, BUBBLE_H, DESK_W, DESK_Y_IN_CELL, MARGIN, PERSON_H, PERSON_W, WALL_H, Bubble, Desk,
                    Scene, Seat, layout_bubbles, pile_hit, seat_at)

log = logging.getLogger("dutyboard.office")
S = config.PIXEL_SCALE
SW, SH = config.SPRITE_W, config.SPRITE_H
# 角色图：行 0 正面 / 1 背面 / 2 侧面；列 0-2 走路、3-4 打字、5-6 看书
POSE_FRAMES = {"typing": (1, (3, 4)), "wave": (0, (0, 0)), "jump": (0, (0, 0)), "ask": (0, (0, 0)), "sleep": (0, (5, 6))}
WALK_ROWS = {"down": 0, "up": 1, "right": 2, "left": 2}   # left 用右侧镜像
PET_IDLE, PET_WALK = (0, (3, 4, 5)), (2, (0, 1, 2))        # 宠物图：行 0 正面（走 3 + 站 3）、行 2 向右走
FURNITURE = {"desk": "furniture/DESK_FRONT.png", "chair_back": "furniture/CHAIR_BACK.png",
             "chair_front": "furniture/CHAIR_FRONT.png", "pc_off": "furniture/PC_OFF.png",
             "pc_1": "furniture/PC_ON_1.png", "pc_2": "furniture/PC_ON_2.png", "pc_3": "furniture/PC_ON_3.png",
             "bin": "furniture/BIN.png", "plant": "furniture/PLANT.png", "cactus": "furniture/CACTUS.png",
             "clock": "furniture/CLOCK.png", "whiteboard": "furniture/WHITEBOARD.png",
             "floor": "floors/floor_2.png", "wall": "walls/wall_0.png", "pet": "pets/claudio.png"}
C = {"bg": (0.11, 0.12, 0.15), "bubble": (1.0, 1.0, 1.0), "bubble_text": (0.10, 0.10, 0.12),
     "label": (0.90, 0.90, 0.95), "shadow": (0.0, 0.0, 0.0), "alert": (0.96, 0.30, 0.30), "zzz": (0.80, 0.80, 0.95)}


def load_assets() -> tuple[list[NSImage], dict[str, NSImage]]:
    """缺什么就少画什么，不报错，别让素材问题拖死浮窗。"""
    chars = [img for i in range(config.CHARACTER_COUNT)
             if (img := NSImage.alloc().initWithContentsOfFile_(str(config.CHARACTER_DIR / f"char_{i}.png")))]
    furniture = {k: img for k, rel in FURNITURE.items()
                 if (img := NSImage.alloc().initWithContentsOfFile_(str(config.ASSET_DIR / rel)))}
    return chars, furniture


def mirrored(image: NSImage) -> NSImage:
    """水平翻转一张图（向左走 = 向右走的镜像）。"""
    from AppKit import NSAffineTransform
    size = image.size()
    out = NSImage.alloc().initWithSize_(size)
    out.lockFocus()
    NSGraphicsContext.currentContext().setImageInterpolation_(NSImageInterpolationNone)
    t = NSAffineTransform.transform()
    t.translateXBy_yBy_(size.width, 0)
    t.scaleXBy_yBy_(-1, 1)
    t.concat()
    image.drawInRect_fromRect_operation_fraction_(NSMakeRect(0, 0, size.width, size.height), NSMakeRect(0, 0, size.width, size.height), NSCompositingOperationSourceOver, 1.0)
    out.unlockFocus()
    return out


class OfficeView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(OfficeView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.scene: Scene | None = None
        self.frame_no = 0
        self.sweep = -1
        self.characters, self.furniture = load_assets()
        self.characters_mirror = [mirrored(c) for c in self.characters]
        if "pet" in self.furniture:
            self.furniture["pet_mirror"] = mirrored(self.furniture["pet"])
        self.sim = sim.empty_state()
        self.on_seat: Callable[[Entry], None] = lambda _e: None
        self.on_pile: Callable[[], None] = lambda: None
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / config.OFFICE_FPS, self, "tick:", None, True)
        return self

    def isFlipped(self) -> bool:          # 原点在左上角，和 pixel.py 的坐标一致
        return True

    def mouseDownCanMoveWindow(self) -> bool:
        return False

    def tick_(self, _timer) -> None:
        self.frame_no += 1
        if self.frame_no % 300 == 0:
            log.info("office 心跳 frame=%d actors=%d", self.frame_no, len(self.sim.actors))
        if self.sweep >= 0:
            self.sweep = self.sweep + 1 if self.sweep < config.OFFICE_SWEEP_FRAMES else -1
        if self.scene is not None:
            self.sim = sim.step(self.sim, self.scene)
        self.setNeedsDisplay_(True)

    @objc.python_method
    def set_scene(self, scene: Scene) -> None:
        self.scene = scene
        self.sim = sim.sync(self.sim, scene)
        self.setNeedsDisplay_(True)

    def mouseDown_(self, event) -> None:
        if self.scene is None:
            return
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        ux, uy = int(p.x // S), int(p.y // S)
        seat = seat_at(self.scene, ux, uy)
        if seat is not None:
            self.on_seat(seat.entry)
        elif pile_hit(self.scene, ux, uy):
            self.sweep = 0
            self.on_pile()

    # ---------- 绘制 ----------
    def drawRect_(self, _rect) -> None:
        NSGraphicsContext.currentContext().setImageInterpolation_(NSImageInterpolationNone)
        scene = self.scene
        _fill(C["bg"], 0, 0, self.bounds().size.width / S, self.bounds().size.height / S)
        if scene is None:
            return
        self._draw_room(scene)
        for desk in scene.desks:
            self._draw_desk(desk, self.sim.desks.get(desk.name))
        self._draw_corner(scene)
        for actor in sorted(self.sim.actors.values(), key=lambda a: a.y):
            self._draw_actor(actor)
        for moving in self.sim.desks.values():
            if not moving.docked:
                self._draw_walker(moving.mover_skin, moving.x + DESK_W + 2, moving.y + 8, "right")
        seated = {a.seat.entry.desktop_id for a in self.sim.actors.values() if a.seat and not a.walking}
        for desk in scene.desks:
            for bubble in layout_bubbles(desk, scene.width):
                if bubble.seat.entry.desktop_id in seated:
                    _draw_bubble(bubble, self.frame_no)

    @objc.python_method
    def _draw_room(self, scene: Scene) -> None:
        for ty in range(WALL_H, scene.height, 16):
            for tx in range(0, scene.width, 16):
                self._img("floor", tx, ty, 16, 16)
        for tx in range(0, scene.width, 16):          # 墙：图集按 4 位邻接掩码排 16 块，东西都有邻居 = 10
            self._img("wall", tx, 0, 16, WALL_H, src=(WALL_MID_X, WALL_MID_Y, 16, 32))
        self._img("whiteboard", MARGIN + 4, 0, 32, 32)
        self._img("clock", scene.width - MARGIN - 20, 0, 16, 32)

    @objc.python_method
    def _draw_desk(self, desk: Desk, moving) -> None:
        f = self.frame_no
        alpha = 0.45 if desk.dusty else 1.0
        x = int(sim.desk_x(desk, moving))
        desk_y = desk.y + DESK_Y_IN_CELL
        self._img("desk", x, desk_y, DESK_W, 32, alpha=alpha)
        seated = {a.seat.entry.desktop_id for a in self.sim.actors.values() if a.seat and not a.walking}
        for slot in range(sim.pcs_visible(moving)):
            seat = desk.seats[slot] if slot < len(desk.seats) else None
            on = seat is not None and seat.pose == "typing" and seat.entry.desktop_id in seated
            key = f"pc_{1 + (f // 2) % 3}" if on else "pc_off"
            self._img(key, x + slot * 16, desk_y - TOP_PC_OVERHANG, 16, 32, alpha=alpha)
        if moving is not None and not moving.docked:
            return
        for seat in desk.seats:
            if seat.pose == "typing" and seat.entry.desktop_id in seated:
                continue                                              # 背对的人在椅背后面，椅子随人一起画
            self._img("chair_back", seat.x, seat.y + 2, 16, 32, alpha=alpha)
        _text(desk.name[:8], desk.x + 1, desk.y + DESK_H_LABEL, 9, C["label"])

    @objc.python_method
    def _draw_actor(self, actor) -> None:
        if actor.walking or actor.seat is None:
            self._draw_walker(actor.skin, actor.x, actor.y, actor.facing)
            return
        seat = actor.seat
        if seat.pose == "typing":                                     # 背对我们：椅背在人身前，挡住腿
            self._draw_person(seat, self.frame_no)
            self._img("chair_back", seat.x, seat.y + 4, 16, 32)
        else:
            self._draw_person(seat, self.frame_no)

    @objc.python_method
    def _draw_walker(self, skin: int, x: float, y: float, facing: str) -> None:
        if not self.characters:
            return
        sheets = self.characters_mirror if facing == "left" else self.characters
        col = (0, 1, 0, 2)[(self.frame_no // 1) % 4]
        _sprite(sheets[skin % len(sheets)], col, WALK_ROWS[facing], int(x), int(y), SW, SH)

    @objc.python_method
    def _draw_person(self, seat: Seat, f: int) -> None:
        if not self.characters:
            return
        row, cols = POSE_FRAMES.get(seat.pose, (0, (0, 0)))
        col = cols[(f // (3 if seat.pose == "sleep" else 1)) % len(cols)]
        dy = -3 if (seat.pose == "jump" and f % 2) else 0
        image = self.characters[seat.skin % len(self.characters)]
        _sprite(image, col, row, seat.x, seat.y + dy, SW, SH)
        if seat.pose == "sleep":
            _text("z", seat.x + 13, seat.y - 4 - (f // 3) % 3, 8, C["zzz"])
        if seat.pose == "jump":
            _fill(C["alert"], seat.x + 14, seat.y + dy - 3, 2, 2)

    @objc.python_method
    def _draw_corner(self, scene: Scene) -> None:
        self._img("plant", MARGIN, scene.height - BOTTOM_H - 4, 16, 32)
        if scene.pile:
            self._img("bin", scene.pile_x, scene.pile_y, 16, 16)
            _text(f"x{scene.pile}", scene.pile_x - 22, scene.pile_y + 2, 9, C["label"])
        if scene.hidden_desks:
            _text(f"+{scene.hidden_desks} 个项目没画下", MARGIN + 20, scene.pile_y + 2, 8, C["label"])
        pet = self.furniture.get("pet")
        state = self.sim.pet
        if pet is None or state is None:
            return
        if self.sweep >= 0:                                           # 清仓：跑向垃圾桶
            span = max(1, scene.pile_x - MARGIN - 40)
            x = MARGIN + 20 + span * self.sweep // config.OFFICE_SWEEP_FRAMES
            _sprite(pet, PET_WALK[1][self.frame_no % 3], PET_WALK[0], x, scene.pile_y - 12, SW, SH)
        elif state.facing == "stay":
            _sprite(pet, PET_IDLE[1][(self.frame_no // 4) % 3], PET_IDLE[0], int(state.x), int(state.y) - 14, SW, SH)
        else:
            sheet = self.furniture["pet_mirror"] if state.facing == "left" else pet
            _sprite(sheet, PET_WALK[1][self.frame_no % 3], PET_WALK[0], int(state.x), int(state.y) - 14, SW, SH)

    @objc.python_method
    def _img(self, key: str, x: int, y: int, w: int, h: int, src=None, alpha: float = 1.0) -> None:
        image = self.furniture.get(key)
        if image is None:
            return
        size = image.size()
        if src is None:
            from_rect = NSMakeRect(0, 0, size.width, size.height)
        else:
            sx, sy, sw, sh = src
            from_rect = NSMakeRect(sx, size.height - sy - sh, sw, sh)
        image.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
            NSMakeRect(x * S, y * S, w * S, h * S), from_rect, NSCompositingOperationSourceOver, alpha, True, None)


WALL_MID_X, WALL_MID_Y = 32, 64
TOP_PC_OVERHANG = 9       # 电脑精灵底部有空白，往下压一点让键盘落在桌面上
DESK_H_LABEL = 82         # 项目名在格子里的 y


def _sprite(sheet: NSImage, col: int, row: int, x: int, y: int, w: int, h: int, alpha: float = 1.0) -> None:
    src = NSMakeRect(col * w, sheet.size().height - (row + 1) * h, w, h)
    sheet.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
        NSMakeRect(x * S, y * S, w * S, h * S), src, NSCompositingOperationSourceOver, alpha, True, None)


def _draw_bubble(bubble: Bubble, f: int) -> None:
    x, y = bubble.x, bubble.y - (1 if bubble.seat.pose == "jump" and f % 2 else 0)
    _fill(C["shadow"], x + 1, y + 1, bubble.w, BUBBLE_H)
    _fill(C["bubble"], x, y, bubble.w, BUBBLE_H)
    _fill(C["bubble"], bubble.seat.x + 2, y + BUBBLE_H, 3, 1)
    _text(bubble.text, x + 1, y + 1, 9, C["bubble_text"], shadow=False)


def _fill(rgb, x, y, w, h) -> None:
    NSColor.colorWithSRGBRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], 1).set()
    NSBezierPath.fillRect_(NSMakeRect(x * S, y * S, w * S, h * S))


def _text(text: str, x: int, y: int, size: int, rgb, shadow: bool = True) -> None:
    font = NSFont.monospacedSystemFontOfSize_weight_(size, 0.4)
    if shadow and rgb is C["label"]:
        dark = {NSFontAttributeName: font, NSForegroundColorAttributeName: NSColor.colorWithSRGBRed_green_blue_alpha_(0.1, 0.1, 0.12, 0.9)}
        for ox, oy in ((1, 0), (0, 1), (1, 1), (-1, 0), (0, -1)):
            NSString.stringWithString_(text).drawAtPoint_withAttributes_((x * S + ox, y * S + oy), dark)
    attrs = {NSFontAttributeName: font,
             NSForegroundColorAttributeName: NSColor.colorWithSRGBRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], 1)}
    NSString.stringWithString_(text).drawAtPoint_withAttributes_((x * S, y * S), attrs)
