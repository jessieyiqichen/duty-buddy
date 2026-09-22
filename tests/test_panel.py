from dutyboard import config
from dutyboard.panel import panel_height

BASE = config.PANEL_PADDING * 2 + config.PANEL_HEADER_HEIGHT
ROW = config.PANEL_ROW_HEIGHT


def test_collapsed_is_header_only():
    assert panel_height(3, 2, True, True) == BASE


def test_nothing_running_is_header_only_too():
    assert panel_height(0, 0, False, False) == BASE


def test_attention_rows_plus_summary_plus_expanded_others():
    assert panel_height(2, 0, True, False) == BASE + ROW * 3 + config.PANEL_GROUP_GAP
    assert panel_height(2, 4, True, False) == BASE + ROW * 7 + config.PANEL_GROUP_GAP


def test_project_rows_and_height():
    from dutyboard.browser import Entry, ProjectView
    from dutyboard.panel import project_rows
    e = Entry("t", "·", None, "local_1", "code")
    projects = (ProjectView("a", 0, (e, e)), ProjectView("b", 1, (e,)))
    assert project_rows(projects, False, None) == 1
    assert project_rows(projects, True, None) == 3
    assert project_rows(projects, True, "a") == 5
    assert panel_height(0, 0, False, False, 5) == BASE + ROW * 5 + config.PANEL_GROUP_GAP
