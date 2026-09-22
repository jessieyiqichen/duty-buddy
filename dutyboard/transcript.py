"""读 Claude 对话记录（jsonl）的末尾，提取标题、最后一句输入、最后一条消息的状态。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import TAIL_BYTES

MESSAGE_TYPES = frozenset({"user", "assistant"})
TITLE_TYPE, TITLE_FIELD = "custom-title", "customTitle"
PROMPT_TYPE, PROMPT_FIELD = "last-prompt", "lastPrompt"


@dataclass(frozen=True)
class TranscriptView:
    title: str | None
    last_prompt: str | None
    last_role: str | None          # "user" | "assistant" | None
    stop_reason: str | None
    last_message_at: datetime | None


def parse_lines(lines: Iterable[str]) -> list[dict]:
    """坏行直接跳过：记录文件正在被别的进程写，尾部半行是常态，不是错误。"""
    records = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            records.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    return records


def read_tail(path: Path, max_bytes: int = TAIL_BYTES) -> list[str]:
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            fh.seek(max(0, size - max_bytes))
            data = fh.read()
    except OSError:
        return []
    lines = data.decode("utf-8", errors="ignore").splitlines()
    return lines[1:] if size > max_bytes else lines


def scan_title(path: Path) -> str | None:
    """标题记录可能在文件很前面，尾部找不到时全文扫一次（调用方负责缓存）。"""
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            titles = [r.get(TITLE_FIELD) for r in parse_lines(fh) if r.get("type") == TITLE_TYPE]
    except OSError:
        return None
    return titles[-1] if titles else None


def view_from_records(records: list[dict]) -> TranscriptView:
    title = _last_field(records, TITLE_TYPE, TITLE_FIELD)
    prompt = _last_field(records, PROMPT_TYPE, PROMPT_FIELD)
    messages = [r for r in records if r.get("type") in MESSAGE_TYPES and not r.get("isSidechain")]
    if not messages:
        return TranscriptView(title, prompt, None, None, None)
    last = messages[-1]
    message = last.get("message") or {}
    return TranscriptView(title, prompt, last["type"], message.get("stop_reason"), _parse_ts(last.get("timestamp")))


def load_view(path: Path) -> TranscriptView:
    return view_from_records(parse_lines(read_tail(path)))


def _last_field(records: list[dict], kind: str, field: str) -> str | None:
    values = [r.get(field) for r in records if r.get("type") == kind and r.get(field)]
    return values[-1] if values else None


def _parse_ts(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
