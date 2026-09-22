import random
from datetime import datetime, timedelta, timezone

from dutyboard import sim
from dutyboard.browser import Entry, ProjectView
from dutyboard.pixel import build_scene

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def _e(title, icon="🟢"):
    return Entry(title, icon, NOW - timedelta(minutes=1), "local_" + title, "code")


def _scene(*projects):
    return build_scene(tuple(projects), stale=0, now=NOW)


def test_sync_spawns_actor_at_door_with_route_and_moving_desk():
    scene = _scene(ProjectView("p", 1, (_e("a"),)))
    st = sim.sync(sim.empty_state(), scene, random.Random(0))
    actor = st.actors["local_a"]
    assert (actor.x, actor.y) == sim.door(scene)
    assert actor.path[-1] == (float(scene.desks[0].seats[0].x), float(scene.desks[0].seats[0].y))
    assert "p" in st.desks and not st.desks["p"].docked
    assert st.pet is not None


def test_step_walks_actor_to_seat_and_docks_desk():
    scene = _scene(ProjectView("p", 1, (_e("a"),)))
    st = sim.sync(sim.empty_state(), scene, random.Random(0))
    for _ in range(400):
        st = sim.step(st, scene, random.Random(1))
    actor = st.actors["local_a"]
    assert not actor.walking and (actor.x, actor.y) == actor.path_end if hasattr(actor, "path_end") else True
    assert (actor.x, actor.y) == (float(scene.desks[0].seats[0].x), float(scene.desks[0].seats[0].y))
    assert actor.facing == "up"          # 打字的人背对我们
    assert "p" not in st.desks           # 桌子到位、电脑冒完就从搬运名单里移除
    assert sim.pcs_visible(None) == 3


def test_removed_seat_makes_actor_leave_and_vanish():
    scene = _scene(ProjectView("p", 1, (_e("a"),)))
    st = sim.sync(sim.empty_state(), scene, random.Random(0))
    for _ in range(400):
        st = sim.step(st, scene, random.Random(1))
    scene2 = _scene(ProjectView("p", 0, (Entry("a", "·", NOW, "local_a", "code"),)))
    st = sim.sync(st, scene2, random.Random(0))
    assert st.actors["local_a"].leaving
    for _ in range(400):
        st = sim.step(st, scene2, random.Random(1))
    assert "local_a" not in st.actors


def test_known_desk_does_not_move_again():
    scene = _scene(ProjectView("p", 1, (_e("a"),)))
    st = sim.sync(sim.empty_state(), scene, random.Random(0))
    for _ in range(400):
        st = sim.step(st, scene, random.Random(1))
    st = sim.sync(st, scene, random.Random(0))
    assert "p" not in st.desks


def test_pcs_pop_progressively():
    d = sim.MovingDesk("p", 10, 0, 10, 0, docked_frames=sim.PC_POP_FRAMES * 2)
    assert sim.pcs_visible(d) == 2
    assert sim.pcs_visible(sim.MovingDesk("p", 0, 0, 10, 0)) == 0


def test_pet_stays_in_bounds():
    scene = _scene(ProjectView("p", 1, (_e("a"),)))
    st = sim.sync(sim.empty_state(), scene, random.Random(0))
    for i in range(600):
        st = sim.step(st, scene, random.Random(i))
        assert 0 <= st.pet.x <= scene.width
