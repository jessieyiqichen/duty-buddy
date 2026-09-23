from datetime import datetime, timedelta, timezone

from dutyboard import app
from dutyboard.sessions import RunningSession, SessionInfo, State

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def _info(state, title="改简历", prompt="把第二段改短", entry="claude-desktop", age=90):
    return SessionInfo(RunningSession(1, "sid", "/p/job-pilot", entry, "n", 0), state, title, prompt,
                       NOW - timedelta(seconds=age), "job-pilot")


def test_age_label():
    assert app.age_label(None, NOW) == "无记录"
    assert app.age_label(NOW - timedelta(seconds=5), NOW) == "刚刚"
    assert app.age_label(NOW - timedelta(minutes=3), NOW) == "3 分钟前"
    assert app.age_label(NOW - timedelta(hours=2), NOW) == "2 小时前"


def test_row_label_includes_icon_title_prompt_and_source():
    label = app.row_label(_info(State.WAITING), NOW)
    assert label.startswith("🟡 改简历")
    assert "「把第二段改短」" in label and "桌面" in label and "1 分钟前" in label


def test_row_label_without_prompt():
    assert "「" not in app.row_label(_info(State.RUNNING, prompt=None), NOW)


def test_clip_truncates():
    assert app.clip("a" * 40, 10).endswith("…") and len(app.clip("a" * 40, 10)) == 10


def test_bar_title_prefers_waiting_count():
    assert app.bar_title((_info(State.WAITING), _info(State.RUNNING), _info(State.PERMISSION))) == "◐ 2"
    assert app.bar_title((_info(State.RUNNING), _info(State.IDLE))) == "● 1"
    assert app.bar_title(()) == "◌"


def test_queue_labels():
    from dutyboard.labels import headline_label, queue_row_label, summary_label, waited_label
    assert waited_label(NOW - timedelta(minutes=14), NOW) == "等了 14 分钟"
    assert waited_label(NOW - timedelta(seconds=5), NOW) == "刚刚"
    assert queue_row_label(_info(State.WAITING, age=840), NOW, overdue=True) == "❗ job-pilot · 改简历 · 等了 14 分钟"
    assert queue_row_label(_info(State.RUNNING, age=90), NOW, overdue=False) == "🟢 job-pilot · 改简历 · 1 分钟前"
    assert summary_label(4, 3, False) == "▸ 另有 4 个在跑"
    assert summary_label(0, 3, True) == ""
    assert summary_label(2, 0, False, parked=1) == "▸ 另有 2 个在跑 · 1 个看过搁着"
    assert headline_label(2, 5) == "◐ 2 个等你"
    assert headline_label(0, 4) == "● 都在跑，没人等你 · 4 个"
    assert headline_label(0, 0) == "◌ 没有运行中的 session"


def test_jump_command_prefers_deep_link():
    from dutyboard.sessions import RunningSession, SessionInfo
    desk = SessionInfo(RunningSession(1, "cli-1", "/p/x", "claude-desktop", "n", 0), State.WAITING, "t", None, NOW, "x", "local_1")
    assert app.jump_command(desk) == ["open", "claude://code/continue?session=local_1&source=dutyboard"]
    nodesk = SessionInfo(RunningSession(1, "cli-1", "/p/x", "claude-desktop", "n", 0), State.WAITING, "t", None, NOW, "x")
    assert app.jump_command(nodesk) == ["open", "-a", "Claude"]
    cli = SessionInfo(RunningSession(1, "cli-1", "/p/x", "cli", "n", 0), State.WAITING, "t", None, NOW, "x")
    cmd = app.jump_command(cli)
    assert cmd[0] == "osascript" and "claude --resume cli-1" in cmd[2]


def test_jump_command_for_browser_entries():
    from dutyboard.browser import Entry
    assert app.jump_command(Entry("t", "·", None, "local_2", "code")) == ["open", "claude://code/continue?session=local_2&source=dutyboard"]
    assert app.jump_command(Entry("t", "·", None, "local_3", "cowork")) == ["open", "-a", "Claude"]


def test_parked_row_label():
    from dutyboard.labels import queue_row_label
    from dutyboard.sessions import RunningSession, SessionInfo
    info = SessionInfo(RunningSession(1, "s", "/p/x", "claude-desktop", "n", 0), State.WAITING, "改简历", None,
                       NOW - timedelta(minutes=14), "x", "local_1", True)
    assert queue_row_label(info, NOW, overdue=True) == "📌 x · 改简历 · 看过了 · 搁置 14 分钟"
