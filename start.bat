@echo off
cd /d C:\Users\Glen\Documents\GitHub\shoppilot
call .venv\Scripts\activate
start http://127.0.0.1:8000/dashboard
uvicorn main:app --host 127.0.0.1 --port 8000
pause