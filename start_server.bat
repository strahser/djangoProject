@echo off
rem ============================================================
rem ЕДИНЫЙ launcher сервера Django в этом проекте.
rem
rem   start_server.bat              - dev-сервер  http://127.0.0.1:8000
rem   start_server.bat 8013        - dev-сервер на другом порту
rem   start_server.bat --waitress  - прод-режим (waitress, без autoreload)
rem   start_server.bat --waitress 8013
rem
rem Dev-режим запускается с --noreload: иначе из-за autoreload
rem поднимаются два планировщика почты (APScheduler).
rem ============================================================
set PORT=8000
set MODE=dev
if /i "%~1"=="--waitress" (
    set MODE=waitress
    shift
)
if not "%~1"=="" set PORT=%~1

cd /d "%~dp0"

if /i "%MODE%"=="waitress" (
    title Django - waitress 127.0.0.1:%PORT%
    "%~dp0.venv\Scripts\waitress-serve.exe" --listen=127.0.0.1:%PORT% --threads=4 djangoProject.wsgi:application
    goto fail
)

title Django - 127.0.0.1:%PORT%
"%~dp0.venv\Scripts\python.exe" manage.py runserver 127.0.0.1:%PORT% --noreload
if errorlevel 1 goto fail
exit /b 0

:fail
echo.
echo Сервер не запустился - подробности выше.
pause
