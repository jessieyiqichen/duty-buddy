import json
from datetime import datetime, timezone

from dutyboard.transcript import parse_lines, read_tail, view_from_records


def _rec(kind, **extra):
    return json.dumps({"type": kind, **extra}, ensure_ascii=False)


def test_parse_lines_skips_blank_and_broken_lines():
    lines = ["", _rec("user"), "{not json", _rec("assistant")]
    assert [r["type"] for r in parse_lines(lines)] == ["user", "assistant"]


def test_read_tail_drops_partial_first_line_when_truncated(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(f"line{i:04d}" for i in range(200)) + "\n")
    lines = read_tail(path, max_bytes=100)
    assert 0 < len(lines) < 200
    assert all(line.startswith("line") for line in lines)


def test_read_tail_keeps_everything_when_file_is_small(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text("a\nb\n")
    assert read_tail(path, max_bytes=100) == ["a", "b"]


def test_read_tail_missing_file_returns_empty(tmp_path):
    assert read_tail(tmp_path / "nope.jsonl") == []


def test_view_takes_last_title_prompt_and_message():
    records = parse_lines([
        _rec("custom-title", customTitle="旧名"),
        _rec("user", message={"role": "user", "content": "hi"}, timestamp="2026-09-13T10:00:00.000Z"),
        _rec("assistant", message={"role": "assistant", "stop_reason": "tool_use"}, timestamp="2026-09-13T10:00:05.000Z"),
        _rec("custom-title", customTitle="新名"),
        _rec("last-prompt", lastPrompt="继续"),
        _rec("assistant", message={"role": "assistant", "stop_reason": "end_turn"}, timestamp="2026-09-13T10:01:00.000Z"),
        _rec("attachment"),
        _rec("assistant", isSidechain=True, message={"role": "assistant", "stop_reason": "tool_use"}, timestamp="2026-09-13T10:02:00.000Z"),
    ])
    view = view_from_records(records)
    assert view.title == "新名"
    assert view.last_prompt == "继续"
    assert view.last_role == "assistant"
    assert view.stop_reason == "end_turn"
    assert view.last_message_at == datetime(2026, 9, 13, 10, 1, tzinfo=timezone.utc)


def test_view_with_no_messages():
    view = view_from_records(parse_lines([_rec("attachment")]))
    assert view.last_role is None and view.last_message_at is None
