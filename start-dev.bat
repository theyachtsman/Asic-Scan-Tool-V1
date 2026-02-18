@echo off
title ASIC Scan Tool - Development Mode
echo ============================================
echo   ASIC Scan Tool - Starting Development Mode
echo ============================================
echo.

REM Start Python backend in a new window
echo [1/2] Starting Python backend on port 8765...
start "ASIC Backend" cmd /k "cd /d %~dp0backend && python main.py"

REM Wait for backend to start
timeout /t 3 /nobreak > nul

REM Start Vite dev server
echo [2/2] Starting Vite frontend on port 5173...
cd /d %~dp0frontend
npm run dev

echo.
echo Development servers stopped.
pause
