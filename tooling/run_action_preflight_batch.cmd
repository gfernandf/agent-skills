@echo off
setlocal
cd /d %~dp0\..
".venv\Scripts\python.exe" tooling\run_action_preflight_batches.py %*
set EXITCODE=%ERRORLEVEL%
echo EXITCODE=%EXITCODE%
exit /b %EXITCODE%
