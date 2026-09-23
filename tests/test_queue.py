from datetime import datetime, timedelta, timezone

from dutyboard.config import OVERDUE_SECONDS, STALE_SECONDS
from dutyboard.queue import build_queue, is_overdue
from dutyboard.sessions import RunningSession, SessionInfo, State

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def _info(sid, state, age, project="p", seen=False):
    return SessionInfo(RunningSession(1, sid, f"/x/{project}", "cli", sid, 0), state, sid, None,
                       NOW - timedelta(seconds=age), project, None, seen)


def test_attention_sorted_longest_wait_first_and_counts():
    infos = (
        _info("w-new", State.WAITING, 30),
        _info("w-old", State.WAITING, 900),
        _info("perm", State.PERMISSION, 100),
        _info("run", State.RUNNING, 5),
        _info("idle", State.IDLE, 3600),
        _info("stale", State.IDLE, STALE_SECONDS + 1),
    )
    q = build_queue(infos, NOW)
    assert [i.title for i in q.attention] == ["w-old", "perm", "w-new"]
    assert (q.running, q.idle, q.stale) == (1, 1, 1)
    assert [i.title for i in q.others] == ["run"]


def test_overdue_threshold():
    assert is_overdue(_info("a", State.WAITING, OVERDUE_SECONDS + 1), NOW)
    assert not is_overdue(_info("b", State.WAITING, OVERDUE_SECONDS - 1), NOW)
    assert not is_overdue(_info("c", State.RUNNING, OVERDUE_SECONDS + 99), NOW)


def test_empty():
    q = build_queue((), NOW)
    assert q.attention == () and q.others == () and (q.running, q.idle, q.stale) == (0, 0, 0)


def test_seen_waiting_is_parked_not_attention():
    q = build_queue((_info("w", State.WAITING, 900), _info("seen", State.WAITING, 900, seen=True),
                     _info("p-seen", State.PERMISSION, 100, seen=True)), NOW)
    assert [i.title for i in q.attention] == ["w"]
    assert [i.title for i in q.parked] == ["seen", "p-seen"]
    assert not is_overdue(_info("seen", State.WAITING, OVERDUE_SECONDS + 99, seen=True), NOW)
