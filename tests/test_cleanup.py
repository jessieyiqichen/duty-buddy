from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from dutyboard.cleanup import archive_prompt, cleanup_link, stale_candidates
from dutyboard.config import CLEANUP_BATCH, CLEANUP_STALE_SECONDS
from dutyboard.desktop import DesktopSession
from dutyboard.sessions import RunningSession, SessionInfo, State

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
OLD = CLEANUP_STALE_SECONDS + 3600


def _d(local, age_s, archived=False, source="code", title="t"):
    return DesktopSession(local, "cli-" + local, title, archived, "/p/x", NOW - timedelta(seconds=age_s), source)


def test_stale_candidates_filters_and_sorts_oldest_first():
    live = (SessionInfo(RunningSession(1, "cli-run", "/p/x", "claude-desktop", "n", 0), State.IDLE, "t", None, NOW, "x", "run"),)
    desktop = (
        _d("fresh", 3600), _d("old2", OLD * 2), _d("old1", OLD),
        _d("archived", OLD, archived=True), _d("cowork", OLD, source="cowork"), _d("run", OLD),
        DesktopSession("noact", "cli-noact", "t", False, "/p/x", None, "code"),
    )
    assert [s.local_id for s in stale_candidates(desktop, live, NOW)] == ["old2", "old1"]


def test_prompt_and_link():
    cands = tuple(_d(f"s{i}", OLD + i, title=f"标题{i}") for i in range(CLEANUP_BATCH + 3))
    text = archive_prompt(cands, NOW)
    assert "archive_session" in text and "s0" in text and "标题0" in text and f"s{CLEANUP_BATCH}" not in text
    url = urlparse(cleanup_link(cands, NOW))
    assert url.scheme == "claude" and url.path == "/new"
    q = parse_qs(url.query)
    assert q["prompt"][0] == text and q["source"] == ["dutyboard"] and "folder" in q


def test_prompt_tells_the_session_to_verify_before_archiving():
    """提示词必须要求先核对：值班表只能看到桌面元数据，寻址得靠官方接口。"""
    text = archive_prompt((_d("s0", OLD),), NOW)
    assert "list_sessions" in text and "archive_session" in text
