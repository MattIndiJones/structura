@echo off
cd /d "C:\Users\admin\GitHub\structura\backend"

REM Si le serveur tourne deja, ouvrir le navigateur directement
netstat -ano | find ":8000" | find "LISTENING" >nul 2>&1
if %errorlevel%==0 goto open_browser

REM Lancer le serveur FastAPI (uvicorn) en arriere-plan
start /b "" "C:\Users\admin\GitHub\structura\.venv\Scripts\python.exe" run.py

REM Attendre le demarrage
timeout /t 4 /nobreak >nul

:open_browser
start "" "http://localhost:8000"
