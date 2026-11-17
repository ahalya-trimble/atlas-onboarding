@echo off
rem Starts Atlas Explorer. Installed by setup.bat as "<atlas>\.atlas-onboarding\Open Atlas Explorer.bat".
rem Before starting it pulls the atlas-onboarding repository this guide was installed from, so new lessons
rem arrive by themselves. That step is silent and never blocks: offline, no git, or local edits just skip it.
setlocal
title Atlas Explorer (close this window to stop)
set "HERE=%~dp0"
for %%I in ("%HERE%..") do set "ATLAS=%%~fI"
set "SRC="
if exist "%HERE%.source-repo" set /p SRC=<"%HERE%.source-repo"
if not defined SRC goto run
if not exist "%SRC%\.git" goto run
set "OLD="
set "NEW="
for /f %%h in ('git -C "%SRC%" rev-parse HEAD 2^>nul') do set "OLD=%%h"
git -C "%SRC%" pull --ff-only >nul 2>&1
for /f %%h in ('git -C "%SRC%" rev-parse HEAD 2^>nul') do set "NEW=%%h"
if not defined OLD goto run
if not defined NEW goto run
if "%OLD%"=="%NEW%" goto run
echo New lessons found. Updating Atlas Explorer, one moment...
set "ATLAS_ONBOARDING_SILENT=1"
rem One line on purpose: setup replaces this file, so cmd must not read further lines from it afterwards.
call "%SRC%\setup.bat" "%ATLAS%" >"%HERE%update.log" 2>&1 & call "%~f0" & exit /b
:run
cd /d "%HERE%explorer"
echo Atlas Explorer: http://localhost:8765  (local only, read-only). Close this window to stop.
python server.py --open --atlas "%ATLAS%"
if errorlevel 1 pause
