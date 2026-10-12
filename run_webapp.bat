@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo Steam Review Analyzer WebApp
echo ============================================
echo.

if not exist .venv (
    echo [1/4] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment. Please check Python installation.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Virtual environment already exists.
)

echo [2/4] Installing requirements...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install requirements.
    pause
    exit /b 1
)

echo [3/4] Browser will open automatically once...
start "" cmd /c "timeout /t 6 /nobreak >nul && rundll32 url.dll,FileProtocolHandler http://localhost:8501"

echo [4/4] Starting Streamlit webapp...
echo.
echo If the browser does not open automatically, go to:
echo http://localhost:8501
echo.
.venv\Scripts\python.exe -m streamlit run app.py --server.headless=true

pause
