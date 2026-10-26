@echo off
title Папка по дате - 2026_10_21_
cd /d "%~dp0"
rem pythonw.exe — запуск БЕЗ окна консоли (главное неудобство снято)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    "%~dp0.venv\Scripts\pythonw.exe" "%~dp0create_dated_folder.py" %*
) else (
    "%~dp0.venv\Scripts\python.exe" "%~dp0create_dated_folder.py" %*
)
