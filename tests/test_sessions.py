import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from dutyboard import sessions as S
from dutyboard.config import IDLE_SECONDS, PERMISSION_HINT_SECONDS, USER_PENDING_SECONDS
from dutyboard.transcript import TranscriptView

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def _view(role, stop=None, age=1):
    return TranscriptView(None, None, role, stop, NOW - timedelta(seconds=age))


@pytest.mark.parametrize("view,expected", [
    (_view("assistant", "end_turn"), S.State.WAITING),
    (_view("assistant", "end_turn", age=IDLE_SECONDS + 1), S.State.IDLE),
    (_view("assistant", "tool_use"), S.State.RUNNING),
    (_view("assistant", "tool_use", age=PERMISSION_HINT_SECONDS + 1), S.State.PERMISSION),
    (_view("assistant", None), S.State.RUNNING),
    (_view("user"), S.State.RUNNING),
    (_view("user", age=USER_PENDING_SECONDS - 1), S.State.RUNNING),
    (_view("user", age=USER_PENDING_SECONDS + 1), S.State.IDLE),
    (_view("user", age=IDLE_SECONDS + 1), S.State.IDLE),
    (TranscriptView(None, None, None, None, None), S.State.IDLE),
])
def test_classify(view, expected):
    assert S.classify(view, NOW) == expected


def _write_session(dir_, pid, sid, cwd, entry="claude-desktop"):
    (dir_ / f"{pid}.json").write_text(json.dumps({
        "pid": pid, "sessionId": sid, "cwd": cwd, "entrypoint": entry,
        "name": f"n{pid}", "startedAt": 1789309213504,
    }))


def test_load_running_skips_dead_pid_and_broken_files(tmp_path, monkeypatch):
    _write_session(tmp_path, 1, "s1", "/p/a")
    _write_session(tmp_path, 2, "s2", "/p/b")
    (tmp_path / "3.json").write_text("{broken")
    (tmp_path / "4.json").write_text(json.dumps({"pid": 4}))
    monkeypatch.setattr(S, "pid_alive", lambda pid: pid == 1)
    got = S.load_running(tmp_path)
    assert [s.session_id for s in got] == ["s1"]
    assert got[0].cwd == "/p/a" and got[0].entrypoint == "claude-desktop"


def test_pid_alive_for_self_and_bogus():
    assert S.pid_alive(os.getpid()) is True
    assert S.pid_alive(2**22 - 1) is False


def test_find_transcript(tmp_path):
    (tmp_path / "slug").mkdir()
    target = tmp_path / "slug" / "abc.jsonl"
    target.write_text("")
    assert S.find_transcript(tmp_path, "abc") == target
    assert S.find_transcript(tmp_path, "zzz") is None


def test_newly_done_only_on_transition_into_waiting():
    prev = {"a": S.State.RUNNING, "b": S.State.WAITING, "c": S.State.PERMISSION, "d": S.State.RUNNING}
    cur = {"a": S.State.WAITING, "b": S.State.WAITING, "c": S.State.WAITING, "d": S.State.IDLE, "e": S.State.WAITING}
    assert S.newly_done(prev, cur) == ("a", "c")


def test_build_board_end_to_end(tmp_path, monkeypatch):
    sessions_dir, projects_dir = tmp_path / "sessions", tmp_path / "projects"
    sessions_dir.mkdir(); (projects_dir / "slug").mkdir(parents=True)
    _write_session(sessions_dir, 10, "sid-1", "/Users/me/Desktop/job-pilot")
    ts = (NOW - timedelta(seconds=3)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    (projects_dir / "slug" / "sid-1.jsonl").write_text("\n".join([
        json.dumps({"type": "custom-title", "customTitle": "改简历"}),
        json.dumps({"type": "last-prompt", "lastPrompt": "把第二段改短"}),
        json.dumps({"type": "assistant", "message": {"stop_reason": "end_turn"}, "timestamp": ts}),
    ]) + "\n")
    monkeypatch.setattr(S, "pid_alive", lambda pid: True)
    board, cache = S.build_board(sessions_dir, projects_dir, NOW, {})
    assert len(board) == 1
    info = board[0]
    assert info.project == "job-pilot"
    assert info.title == "改简历"
    assert info.last_prompt == "把第二段改短"
    assert info.state == S.State.WAITING
    assert cache == {"sid-1": "改简历"}


def test_title_falls_back_to_cache_then_name(tmp_path, monkeypatch):
    sessions_dir, projects_dir = tmp_path / "sessions", tmp_path / "projects"
    sessions_dir.mkdir(); (projects_dir / "slug").mkdir(parents=True)
    _write_session(sessions_dir, 10, "sid-1", "/p/x")
    (projects_dir / "slug" / "sid-1.jsonl").write_text(json.dumps({"type": "attachment"}) + "\n")
    monkeypatch.setattr(S, "pid_alive", lambda pid: True)
    board, _ = S.build_board(sessions_dir, projects_dir, NOW, {"sid-1": "缓存名"})
    assert board[0].title == "缓存名"
    board, _ = S.build_board(sessions_dir, projects_dir, NOW, {})
    assert board[0].title == "n10"


def test_group_by_project_sorted_with_waiting_first():
    a = S.SessionInfo(S.RunningSession(1, "a", "/p/x", "cli", "a", 0), S.State.RUNNING, "A", None, NOW, "x")
    b = S.SessionInfo(S.RunningSession(2, "b", "/p/x", "cli", "b", 0), S.State.WAITING, "B", None, NOW, "x")
    c = S.SessionInfo(S.RunningSession(3, "c", "/p/y", "cli", "c", 0), S.State.IDLE, "C", None, NOW, "y")
    grouped = S.group_by_project((a, b, c))
    assert list(grouped) == ["x", "y"]
    assert [i.title for i in grouped["x"]] == ["B", "A"]


def test_build_board_uses_desktop_title_and_id(tmp_path, monkeypatch):
    from dutyboard.desktop import DesktopSession
    sessions_dir, projects_dir = tmp_path / "sessions", tmp_path / "projects"
    sessions_dir.mkdir(); (projects_dir / "slug").mkdir(parents=True)
    _write_session(sessions_dir, 10, "sid-1", "/p/x")
    (projects_dir / "slug" / "sid-1.jsonl").write_text(json.dumps({"type": "custom-title", "customTitle": "记录里的名"}) + "\n")
    monkeypatch.setattr(S, "pid_alive", lambda pid: True)
    desktop = {"sid-1": DesktopSession("local_9", "sid-1", "桌面里的名", False)}
    board, _ = S.build_board(sessions_dir, projects_dir, NOW, {}, desktop)
    assert board[0].title == "桌面里的名" and board[0].desktop_id == "local_9"


def test_is_seen_rules():
    from datetime import timedelta
    from dutyboard.desktop import DesktopSession
    from dutyboard.transcript import TranscriptView
    reply_at = NOW
    view = TranscriptView(None, None, "assistant", "end_turn", reply_at)
    before = DesktopSession("l1", "c1", "t", False, "/p", NOW, "code", reply_at - timedelta(minutes=5))
    after = DesktopSession("l2", "c2", "t", False, "/p", NOW, "code", reply_at + timedelta(seconds=30))
    assert S.is_seen(before, view, front=None) is False
    assert S.is_seen(after, view, front=None) is True
    assert S.is_seen(before, view, front="l1") is True        # 当前开着的会话
    assert S.is_seen(None, view, front="l1") is False
