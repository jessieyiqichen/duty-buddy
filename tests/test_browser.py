from datetime import datetime, timedelta, timezone

from dutyboard.browser import build_projects
from dutyboard.config import BROWSER_MAX_AGE_SECONDS, BROWSER_MAX_PER_PROJECT
from dutyboard.desktop import DesktopSession
from dutyboard.sessions import RunningSession, SessionInfo, State

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def _d(local, cwd, age_h=1, title=None, archived=False, source="code"):
    return DesktopSession(local, "cli-" + local, title or local, archived, cwd, NOW - timedelta(hours=age_h), source)


def _live(local, state=State.WAITING):
    return SessionInfo(RunningSession(1, "cli-" + local, "/p/x", "claude-desktop", "n", 0), state, local, None,
                       NOW - timedelta(minutes=1), "x", local)


def test_groups_by_project_live_first_and_cowork_bucket():
    desktop = (
        _d("a1", "/p/alpha", age_h=5), _d("a2", "/p/alpha", age_h=1),
        _d("b1", "/p/beta", age_h=2),
        _d("old", "/p/beta", age_h=BROWSER_MAX_AGE_SECONDS / 3600 + 1),
        _d("arch", "/p/alpha", archived=True),
        _d("cw", "", age_h=3, source="cowork", title="签证"),
    )
    views = build_projects(desktop, (_live("a1"),), NOW)
    assert [v.name for v in views] == ["alpha", "beta", "Cowork"]
    alpha = views[0]
    assert alpha.live == 1
    assert [e.title for e in alpha.entries] == ["a1", "a2"]
    assert alpha.entries[0].icon == "🟡" and alpha.entries[1].icon == "·"
    assert [e.title for e in views[1].entries] == ["b1"]
    assert views[2].entries[0].title == "签证" and views[2].entries[0].source == "cowork"


def test_per_project_cap():
    desktop = tuple(_d(f"s{i}", "/p/one", age_h=i) for i in range(BROWSER_MAX_PER_PROJECT + 5))
    views = build_projects(desktop, (), NOW)
    assert len(views[0].entries) == BROWSER_MAX_PER_PROJECT
    assert views[0].entries[0].title == "s0"
