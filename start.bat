@echo off
rem Starts the AI Urban Flood Sentinel backend (see start.ps1 for options).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
pause
