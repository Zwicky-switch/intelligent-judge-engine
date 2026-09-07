@echo off
setlocal
cd /d "%~dp0..\backend"

if not exist ".venv\Scripts\python.exe" (
  echo [Init] 未发现虚拟环境, 正在创建 .venv 并安装依赖...
  python -m venv .venv
  call .venv\Scripts\activate.bat
  python -m pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)

echo.
echo ============================================================
echo   智评 Insight 后端启动:  http://127.0.0.1:8000
echo   首次启动将自动建表并注入初始化示例数据; 重置为初始状态可删除
echo   backend\data\app.db 后重启。
echo ============================================================
python run.py
endlocal
