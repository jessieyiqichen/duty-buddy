#!/bin/zsh
# 启动菜单栏值班表（后台常驻）。再运行一次会先停掉旧的。
cd "$(dirname "$0")"
# 需要 rumps + pyobjc 的那个解释器；换机器时用 DUTYBOARD_PYTHON 覆盖
PYTHON="${DUTYBOARD_PYTHON:-/opt/anaconda3/bin/python3}"
pkill -f "dutyboard.app" 2>/dev/null
# 菜单栏挤满时新图标会被藏到刘海左边看不见；把它钉在靠右第 60pt 的位置
defaults write python3 "NSStatusItem Preferred Position Item-0" -float 60
nohup "$PYTHON" -m dutyboard.app >/dev/null 2>&1 &
echo "已启动，看菜单栏右上角。日志: $(pwd)/dutyboard.log"
