@echo off
title Django - Waitress (prod)
cd /d "%~dp0"
call e:\Venvs\djangoProject\Scripts\activate.bat
waitress-serve --listen=127.0.0.1:8000 --threads=4 djangoProject.wsgi:application
