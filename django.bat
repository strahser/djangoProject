@echo off
cd /d "%~dp0"
call e:\Venvs\djangoProject\Scripts\activate.bat
python manage.py runserver
