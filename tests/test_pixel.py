from datetime import datetime, timedelta, timezone

from dutyboard.browser import Entry, ProjectView
from dutyboard.config import OVERDUE_SECONDS
from dutyboard.pixel import AISLE_W, DESK_GAP, DESK_W, ROW_TOP_GAP, WALL_H, build_scene, pile_hit, pose_for, seat_at, skin_for

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def _e(icon, title="改简历", age=60, seen=False):
    return Entry(title, icon, NOW - timedelta(seconds=age), "local_" + title, "code", icon != "·", seen)


def test_pose_mapping_and_overdue_jump():
    assert pose_for(_e("🟢"), NOW) == "typing"
    assert pose_for(_e("🟡"), NOW) == "wave"
    assert pose_for(_e("🟡", age=OVERDUE_SECONDS + 1), NOW) == "jump"
    assert pose_for(_e("🟠"), NOW) == "ask"
    assert pose_for(_e("⚪"), NOW) == "sleep"
    assert pose_for(_e("·"), NOW) == "empty"


def test_scene_layout_wraps_rows_caps_seats_and_desks():
    projects = tuple(ProjectView(f"p{i}", 0, (_e("🟢"), _e("🟡"), _e("·"), _e("·"), _e("·"))) for i in range(8))
    scene = build_scene(projects, stale=5, now=NOW, cols=3, max_desks=6)
    assert len(scene.desks) == 6 and scene.hidden_desks == 2
    assert len(scene.desks[0].seats) == 2                     # 没在跑的不画
    assert scene.desks[0].y == WALL_H + ROW_TOP_GAP and scene.desks[0].y == scene.desks[2].y and scene.desks[3].y > scene.desks[0].y
    assert scene.desks[1].x == AISLE_W + DESK_W + DESK_GAP
    assert scene.desks[0].seats[1].label == "改简历"
    assert scene.desks[0].seats[0].label is None
    assert scene.pile == 5 and scene.pile_y > scene.desks[5].y


def test_hit_testing():
    scene = build_scene((ProjectView("p", 1, (_e("🟡"),)),), stale=1, now=NOW)
    seat = scene.desks[0].seats[0]
    assert seat_at(scene, seat.x + 2, seat.y + 2) is seat
    assert seat_at(scene, 0, 0) is None
    assert pile_hit(scene, scene.pile_x + 1, scene.pile_y + 1)
    assert not pile_hit(scene, 0, 0)


def test_empty_scene_has_one_row():
    scene = build_scene((), stale=0, now=NOW)
    assert scene.desks == () and scene.height > 0 and scene.pile == 0


def test_projects_without_live_sessions_get_no_desk_and_seen_is_parked():
    old = Entry("旧", "·", NOW - timedelta(days=20), "local_old", "code")
    scene = build_scene((ProjectView("p", 0, (old,)),), stale=0, now=NOW)
    assert scene.desks == ()
    assert skin_for(old) == skin_for(old) and 0 <= skin_for(old) < 6
    four = ProjectView("q", 4, (_e("🟢", "a"), _e("🟡", "b"), _e("🟡", "c", seen=True), _e("🟠", "d", seen=True)))
    seats = build_scene((four,), stale=0, now=NOW).desks[0].seats
    assert [s.side for s in seats] == ["n", "n", "s", "s"] and seats[2].y > seats[0].y
    assert [s.pose for s in seats] == ["typing", "wave", "parked", "parked"]
    assert seats[2].label is None
    assert pose_for(_e("🟡", age=OVERDUE_SECONDS + 1, seen=True), NOW) == "parked"


def test_bubbles_stack_and_stay_inside():
    from dutyboard.pixel import layout_bubbles
    projects = (ProjectView("p", 3, (_e("🟡", title="改简历定稿版"), _e("🟡", title="负一屏专项需求"), _e("🟠", title="集成"))),)
    scene = build_scene(projects, stale=0, now=NOW)
    bubbles = layout_bubbles(scene.desks[0], scene.width)
    assert [b.text for b in bubbles] == ["改简历定稿版", "负一屏专项需求", "? 集成"]
    ys = [b.y for b in bubbles]
    assert ys[1] < ys[0]                      # 第二个和第一个横向重叠，摞上去
    assert all(b.x + b.w <= scene.width for b in bubbles)
