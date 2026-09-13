@echo off
REM ============================================================
REM 智评·Insight 后端生产启动脚本 (Windows)
REM 多 worker uvicorn, 适合无 Docker 的 Windows 服务器部署
REM ============================================================
setlocal

cd /d "%~dp0"

REM 检测虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] 未找到 .venv\Scripts\python.exe
    echo 请先运行: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    exit /b 1
)

REM Worker 数 = CPU 核数 (ASR/OCR CPU 密集, 不超过物理核数)
for /f "tokens=2 delims==" %%a in ('wmic cpu get NumberOfLogicalProcessors /value') do set CORES=%%a
set /a WORKERS=CORES
if %WORKERS% gtr 8 set WORKERS=8

echo ============================================================
echo 智评·Insight 后端生产启动
echo Worker 数: %WORKERS% (CPU 逻辑核数 %CORES%)
echo 监听: http://0.0.0.0:8000
echo ============================================================

.venv\Scripts\python -m uvicorn app.main:app ^
    --host 0.0.0.0 --port 8000 ^
    --workers %WORKERS% ^
    --limit-concurrency 50 ^
    --timeout-keep-alive 30 ^
    --log-level info

endlocal
