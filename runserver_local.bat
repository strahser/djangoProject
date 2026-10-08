@echo off
title Django - runserver 8000
cd /d "%~dp0"
call "%~dp0.venv\Scripts\activate.bat"
python manage.py runserver 127.0.0.1:8000 --noreload
pause
