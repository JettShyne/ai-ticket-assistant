@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem 优先用本项目自己的虚拟环境，其次是 PyCharm 的 venv312，最后用系统 python
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "..\venv312\Scripts\python.exe" set "PY=..\venv312\Scripts\python.exe"
if not defined PY set "PY=python"

echo Using: %PY%
echo Starting AI ticket assistant... a browser window will open.
%PY% -m streamlit run app.py --server.headless false

if errorlevel 1 (
    echo.
    echo [ERROR] Streamlit failed to start. Read the message above.
    pause
)
exit /b 0
