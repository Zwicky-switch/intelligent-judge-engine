@echo off
setlocal
cd /d "%~dp0..\frontend"
if not exist "node_modules" (
  echo [Init] 首次运行, 正在 npm install ...
  call npm install
)
echo.
echo ============================================================
echo   智评 Insight 前端启动:  http://127.0.0.1:5173
echo   (开发代理 /v1 -^> http://127.0.0.1:8000, 请先启动后端)
echo   注意: 请用浏览器访问上面的地址, 不要双击 frontend\index.html
echo ============================================================
call npm run dev
endlocal