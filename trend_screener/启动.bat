@echo off
chcp 65001 >/dev/null
cd /d "%~dp0"
echo.
echo   ============================
echo    趋势筛选器 Web UI
echo   ============================
echo.
echo   启动中...
echo.
start "" http://localhost:5050
python server.py
pause
