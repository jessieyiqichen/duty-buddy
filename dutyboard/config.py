"""所有可调参数集中在这里，代码里不出现裸路径和裸数字。"""
from pathlib import Path

CLAUDE_HOME = Path.home() / ".claude"
SESSIONS_DIR = CLAUDE_HOME / "sessions"      # 每个运行中的 session 一个 <pid>.json
PROJECTS_DIR = CLAUDE_HOME / "projects"      # 每个 session 的对话记录 <slug>/<sessionId>.jsonl
LOG_PATH = Path(__file__).resolve().parent.parent / "dutyboard.log"

APP_TITLE = "◌"
POLL_SECONDS = 5
TAIL_BYTES = 64 * 1024                       # 判断状态只看记录末尾这么多字节
IDLE_SECONDS = 30 * 60                       # 超过这么久没动静就算闲置
PERMISSION_HINT_SECONDS = 45                 # 工具调用悬着超过这么久，提示可能在等你确认
PROMPT_MAX_CHARS = 28
TITLE_MAX_CHARS = 20

STATE_ICONS = {
    "running": "🟢",
    "waiting": "🟡",
    "permission": "🟠",
    "idle": "⚪",
}
ENTRYPOINT_LABELS = {
    "claude-desktop": "桌面",
    "cli": "终端",
}

# 桌面浮窗
PANEL_WIDTH = 380
PANEL_ROW_HEIGHT = 22
PANEL_HEADER_HEIGHT = 26
PANEL_PADDING = 10
PANEL_GROUP_GAP = 6
PANEL_PROMPT_CHARS = 18
PANEL_FONT_SIZE = 12
PANEL_MARGIN_FROM_EDGE = 24                  # 第一次出现时离屏幕右上角的距离
PANEL_POSITION_KEY = "dutyboard.panel.topleft"

# 浮窗的「待办队列」逻辑
OVERDUE_SECONDS = 10 * 60                    # 等你超过这么久，行首加感叹号
STALE_SECONDS = 24 * 3600                    # 闲置超过这么久的连数字都不算，那是该归档的
