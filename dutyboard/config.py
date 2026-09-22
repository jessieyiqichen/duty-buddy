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

# 桌面 app 自己的 session 元数据（标题、归档状态、桌面 id），用来做深链跳转
DESKTOP_SESSIONS_DIR = Path.home() / "Library/Application Support/Claude/claude-code-sessions"
DESKTOP_DEEP_LINK = "claude://code/continue?session={local_id}&source=dutyboard"

# 项目浏览（浮窗底部可展开的「项目」区，替代侧边栏的按项目筛选）
COWORK_SESSIONS_DIR = Path.home() / "Library/Application Support/Claude/local-agent-mode-sessions"
COWORK_PROJECT_NAME = "Cowork"
BROWSER_MAX_PER_PROJECT = 8
BROWSER_MAX_AGE_SECONDS = 30 * 24 * 3600     # 项目区只看最近一个月有动静的会话

# 清仓：列出很久没动的会话，交给一个 Claude 会话用官方接口逐个归档
CLEANUP_STALE_SECONDS = 7 * 24 * 3600
CLEANUP_BATCH = 15                            # 一次交多少个，深链里的提示词有长度上限
CLEANUP_FOLDER = Path(__file__).resolve().parent.parent
CLEANUP_NEW_SESSION_LINK = "claude://code/new?prompt={prompt}&folder={folder}&source=dutyboard"

# 最后一条是用户消息、却这么久没有任何回复，说明进程只是活着、模型并没在干活
USER_PENDING_SECONDS = 3 * 60

# 风格
THEME_KEY = "dutyboard.theme"
DEFAULT_THEME = "hud"

# 像素办公室
PIXEL_SCALE = 2                               # 1 个像素画格子 = 几个屏幕像素
ASSET_DIR = Path(__file__).resolve().parent / "assets"
CHARACTER_DIR = ASSET_DIR / "characters"
OFFICE_MAX_DESKS = 40                         # 桌子上限（够用即可，放不下靠滚动）
OFFICE_VIEW_MAX_HEIGHT = 460                  # 浮窗里办公室最多这么高（px），再多就滚动
CHARACTER_COUNT = 6
SPRITE_W, SPRITE_H = 16, 32
OFFICE_COLS = 3                               # 一行几张桌子
OFFICE_FPS = 6
OFFICE_SWEEP_FRAMES = 40                      # 扫地机器人跑一趟多少帧
