#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

PORT="${PORT:-7860}"

if lsof -tiTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  PID="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN | head -n 1)"
  CMD="$(ps -p "$PID" -o command= 2>/dev/null || true)"
  echo "端口 $PORT 已被占用（PID: $PID）"
  if [[ "$CMD" == *"/$(basename "$PWD")/app.py"* ]] || [[ "$CMD" == *"/Users/huxiaoman/Documents/310/app.py"* ]] || [[ "$CMD" == *" app.py"* ]]; then
    echo "检测到本项目服务已在运行：$CMD"
    echo "直接访问: http://127.0.0.1:$PORT"
    echo "如需重启，先执行: kill $PID"
    exit 0
  fi
  echo "占用进程: $CMD"
  echo "请先释放端口，或使用新端口启动，例如: PORT=7861 ./run.sh"
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
exec .venv/bin/python app.py
