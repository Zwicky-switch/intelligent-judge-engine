@echo off
setlocal
echo [1/2] 启动后端(127.0.0.1:8000) ...
start "Insight-Backend" cmd /k "%~dp0start_backend.bat"
timeout /t 4 /nobreak >nul
echo [2/2] 启动前端(http://127.0.0.1:5173) ...
start "Insight-Frontend" cmd /k "%~dp0start_frontend.bat"

echo 正在等待前后端就绪(首次运行若需 npm install 会稍慢)...
set tries=0
:wait
curl -s -o nul --max-time 2 http://127.0.0.1:8000/ >nul 2>&1
if errorlevel 1 goto notyet
curl -s -o nul --max-time 2 http://127.0.0.1:5173/ >nul 2>&1
if errorlevel 1 goto notyet
goto up
:notyet
set /a tries+=1
if %tries% GEQ 90 (
  echo 等待超时。请确认后端/前端窗口无报错后, 手动在浏览器打开 http://127.0.0.1:5173
  goto done
)
timeout /t 2 /nobreak >nul
goto wait

:up
echo 前后端已就绪, 正在打开浏览器 ...
echo 注意: 请勿直接双击 frontend\index.html(会白屏), 一律访问 http://127.0.0.1:5173
start "" "http://127.0.0.1:5173"
:done
endlocal