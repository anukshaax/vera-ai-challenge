@echo off
cd /d "%~dp0"
echo Starting Vera on http://127.0.0.1:8080
python -m uvicorn bot:app --host 0.0.0.0 --port 8080
pause
