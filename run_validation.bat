@echo off
setlocal
cd /d %~dp0
if not exist .venv (
    python -m venv .venv
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run_week6_sample_validation.py
pause
