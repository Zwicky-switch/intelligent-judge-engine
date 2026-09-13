#!/usr/bin/env bash
# ============================================================
# 智评·Insight 后端生产启动脚本 (Linux/macOS)
# 多 worker uvicorn, 适合无 Docker 的服务器部署
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f ".venv/bin/python" ]; then
    echo "[ERROR] 未找到 .venv/bin/python"
    echo "请先运行: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

# Worker 数 = CPU 核数 (ASR/OCR CPU 密集, 不超过物理核数)
CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
WORKERS=$(( CORES > 8 ? 8 : CORES ))

echo "============================================================"
echo "智评·Insight 后端生产启动"
echo "Worker 数: $WORKERS (CPU 核数 $CORES)"
echo "监听: http://0.0.0.0:8000"
echo "============================================================"

exec .venv/bin/python -m uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 \
    --workers "$WORKERS" \
    --limit-concurrency 50 \
    --timeout-keep-alive 30 \
    --log-level info
