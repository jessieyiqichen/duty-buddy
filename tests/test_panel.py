from dutyboard import config
from dutyboard.panel import panel_height

BASE = config.PANEL_PADDING * 2 + config.PANEL_HEADER_HEIGHT


def test_collapsed_is_header_only():
    assert panel_height((3, 2), True) == BASE


def test_empty_board_has_one_placeholder_row():
    assert panel_height((), False) == BASE + config.PANEL_ROW_HEIGHT


def test_groups_add_title_row_plus_rows_plus_gap():
    one = config.PANEL_ROW_HEIGHT * 2 + config.PANEL_GROUP_GAP
    two = config.PANEL_ROW_HEIGHT * 3 + config.PANEL_GROUP_GAP
    assert panel_height((1, 2), False) == BASE + one + two
