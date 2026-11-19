@echo off
cd /d "%~dp0"
if exist "%~dp0data\STOP" (type "%~dp0data\STOP" & del "%~dp0data\STOP")
echo.
echo  Autopilot RESUMED.
echo  If it had stopped because of bounces or a login problem, fix that in the dashboard first.
pause
