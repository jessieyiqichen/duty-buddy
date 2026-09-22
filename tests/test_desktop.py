import json

from dutyboard.desktop import deep_link, load_desktop_index, load_desktop_sessions

NEW_MS, OLD_MS = 1_775_000_000_000, 1_755_000_000_000


def _write(root, name, scope=("org", "user"), **fields):
    d = root.joinpath(*scope); d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(fields))


def test_index_by_cli_id_and_skip_broken(tmp_path):
    _write(tmp_path, "local_a", sessionId="local_a", cliSessionId="cli-a", title="改简历", isArchived=False)
    _write(tmp_path, "local_b", sessionId="local_b", cliSessionId="cli-b", isArchived=True)
    _write(tmp_path, "local_c", sessionId="local_c")
    (tmp_path / "org" / "user" / "local_d.json").write_text("{nope")
    idx = load_desktop_index(tmp_path)
    assert set(idx) == {"cli-a", "cli-b"}
    assert idx["cli-a"].title == "改简历" and idx["cli-a"].local_id == "local_a"
    assert idx["cli-b"].title is None and idx["cli-b"].is_archived is True


def test_load_only_active_scope(tmp_path):
    """两个账号 scope 并存时只认最近有动静的那个：旧 scope 的会话官方接口寻址不到。"""
    _write(tmp_path, "local_new", ("acctA", "wsA"), sessionId="local_new", cliSessionId="cli-new",
           lastActivityAt=NEW_MS)
    _write(tmp_path, "local_old1", ("acctB", "wsB"), sessionId="local_old1", cliSessionId="cli-old1",
           lastActivityAt=OLD_MS)
    _write(tmp_path, "local_old2", ("acctB", "wsB"), sessionId="local_old2", cliSessionId="cli-old2",
           lastActivityAt=OLD_MS - 86_400_000)
    assert [s.local_id for s in load_desktop_sessions(tmp_path)] == ["local_new"]
    assert set(load_desktop_index(tmp_path)) == {"cli-new"}


def test_active_scope_picked_by_newest_not_by_count(tmp_path):
    """旧 scope 文件更多也不算——按最后活动时间挑，不按数量。"""
    for i in range(5):
        _write(tmp_path, f"local_o{i}", ("acctB", "wsB"), sessionId=f"local_o{i}",
               cliSessionId=f"cli-o{i}", lastActivityAt=OLD_MS + i)
    _write(tmp_path, "local_n", ("acctA", "wsA"), sessionId="local_n", cliSessionId="cli-n",
           lastActivityAt=NEW_MS)
    assert [s.local_id for s in load_desktop_sessions(tmp_path)] == ["local_n"]


def test_scope_without_timestamps_still_loads(tmp_path):
    """单 scope 且没有 lastActivityAt（老文件）时不能全部漏掉。"""
    _write(tmp_path, "local_a", sessionId="local_a", cliSessionId="cli-a")
    assert [s.local_id for s in load_desktop_sessions(tmp_path)] == ["local_a"]


def test_empty_root(tmp_path):
    assert load_desktop_sessions(tmp_path) == ()
    assert load_desktop_index(tmp_path) == {}


def test_deep_link():
    assert deep_link("local_x") == "claude://code/continue?session=local_x&source=dutyboard"
