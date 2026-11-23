@echo off
rem EviVibe web UI launcher -- double-click to start, close window to stop.
set PY=C:\Users\85984\.workbuddy\binaries\python\envs\evivibe\Scripts\python.exe
if not exist "%PY%" set PY=python
cd /d "%~dp0"
"%PY%" -m evivibe.gui
pause
