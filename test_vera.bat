@echo off
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: test_vera.bat "C:\path\to\magicpin-ai-challenge"
  pause
  exit /b 1
)
python run_local.py "%~1"
pause
