@echo off
REM Run Python CAD Pro Application

echo Starting Python CAD Pro...
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Run application
python main.py

pause
