from dutyboard.themes import DEFAULT_ICONS, THEMES, resolve_theme, theme_choices


def test_resolve_falls_back_to_default():
    assert resolve_theme("terminal", "hud").key == "terminal"
    assert resolve_theme("nope", "hud").key == "hud"
    assert resolve_theme(None, "hud").key == "hud"


def test_every_theme_is_complete():
    for t in THEMES.values():
        assert (t.material is None) != (t.background is None)
        assert set(t.icons) == set(DEFAULT_ICONS)
        assert t.font in {"system", "mono", "rounded", "serif"}


def test_choices_match_keys():
    assert [k for k, _ in theme_choices()] == list(THEMES)
