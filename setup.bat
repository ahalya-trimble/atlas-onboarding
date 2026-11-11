@echo off
rem One-step installer: double-click, or run: setup.bat "C:\path\to\atlas_v2.0" [-Remove]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" %*
echo.
pause
