@echo off
cd /d "%~dp0"
python image_resizer.py
if errorlevel 1 (
    echo.
    echo  [ERROR] pip install -r requirements.txt
    echo.
    pause
)
