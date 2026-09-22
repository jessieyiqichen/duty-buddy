# Claude 值班表

macOS 桌面浮窗 + 菜单栏小工具：一眼看到本机所有正在运行的 Claude Code session（CLI / 桌面 Code / Cowork 都算）在干嘛、谁在等你。

- 桌面浮窗是**待办队列**，不是清单：只列等你的 session（等最久的在最上面，超过 10 分钟行首变 ❗），在跑的压成一行「▸ 另有 4 个在跑」，点它展开；闲着的不上浮窗，去「按项目找会话」里看。没人等你时整个窗只剩一条「● 都在跑，没人等你」
- 浮窗永远置顶、跨所有桌面空间，按住空白处拖，位置会记住；点标题折叠成一条；菜单栏里可以「显示 / 隐藏浮窗」
- 浮窗最底下「▸ 项目 · N 个」：展开是最近一个月有动静的项目（Code 会话按目录分，Cowork 单独一组），点项目再展开它的会话（在跑的在前、最多 8 条），点会话直接跳过去。这就是侧边栏「按项目筛选」的替代
- 「🗑 可归档 · N 个超过 7 天没动」：点它，Claude 会打开一个新会话，输入框里已经填好清单和「用 archive_session 逐个归档」的请求，你按发送，之后每个归档点一次确认。值班表自己不写桌面 app 的数据文件
- 菜单栏下拉仍是按项目分组的完整清单
- 菜单栏：`◐ 2` = 两个在等你；`● 3` = 三个在跑、没人等你；`◌` = 没有运行中的 session
- 下拉：按项目分组，每行 `状态 · 标题 · 「最后一句输入」 · 来源 · 多久前`
  - 🟢 在跑　🟡 回完了等你　🟠 工具调用悬着 45 秒以上，可能在等你点确认　⚪ 30 分钟没动静
- session 从「在跑」变成「等你」时弹系统通知
- 点某一行直接跳过去：桌面 app 的 session 走 `claude://code/continue?session=local_…` 深链，Claude 会切到那个会话；终端的开 Terminal `claude --resume`

## 数据来源（只读，不改任何 Claude 文件）

- `~/.claude/sessions/<pid>.json`：运行中的 session 名单
- `~/Library/Application Support/Claude/claude-code-sessions/*/*/local_*.json`：桌面 app 的 session 元数据，取你手改的标题和深链用的 local id
- `~/Library/Application Support/Claude/local-agent-mode-sessions/*/*/local_*.json`：Cowork 会话元数据（只有标题和最后活动时间，没有对话记录，所以看不出在跑还是在等）
- `~/.claude/projects/*/<sessionId>.jsonl`：对话记录尾部，取标题、最后一句输入、最后一条消息的 stop_reason

## 用

```bash
./run.sh          # 启动 / 重启
pkill -f dutyboard.app   # 停
python3 -m pytest -q tests
```

菜单栏项目太多时 macOS 会把新图标藏到刘海左边，`run.sh` 里用 `defaults write` 把它钉在靠右的位置。

依赖：`pip install rumps pyobjc`。`run.sh` 里的解释器路径可以用 `DUTYBOARD_PYTHON` 环境变量覆盖。

菜单栏「风格」子菜单切换浮窗外观（极简深毛玻璃 / 轻盈浅毛玻璃 / 像素办公室 / 纸 / 终端），选择会记住；加风格改 `dutyboard/themes.py`。

**像素办公室**：一间带墙和地砖的办公室，每个项目一张桌子（三台电脑三把椅子），每个会话一个小人。新会话的小人从左下角的门进来走到座位；新项目的桌子由一个小人从左边推进来，到位后电脑一台台冒出来；会话没了的人起身走出门。背对你敲键盘、屏幕亮=在跑；转过身举气泡=做完等你，超过 10 分钟原地蹦；举「?」=等你点确认；坐着看书冒 z=闲着（偶尔起身去盆栽那儿溜达）；空椅子=最近有过但没在跑；整张桌子褪色=7 天没人来。右下角垃圾桶旁的数字=可归档数，点它宠物跑一趟并把清单交给 Claude。项目多时办公室在浮窗里上下滚动（鼠标悬停滚轮），可视高度上限在 `config.py` 的 OFFICE_VIEW_MAX_HEIGHT。点小人直接跳到那个会话。素材来源见 `dutyboard/assets/CREDITS.md`（CC0 / MIT）。

参数都在 `dutyboard/config.py`。日志在 `dutyboard.log`。
