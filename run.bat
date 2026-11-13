@echo off
setlocal
cd /d "%~dp0"
title MAACRO

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found.
    echo Install Python 3.11 or newer from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during setup. Then run this again.
    pause
    exit /b 1
)

rem First run (or an install that didn't finish): set up the packages.
if not exist .venv\installed.ok (
    echo Setting up MAACRO for the first time. This takes a few minutes...
    if not exist .venv python -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip >nul
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Some packages need Git to download. Installing everything else...
        findstr /v /c:"git+" requirements.txt > "%TEMP%\maacro_requirements.txt"
        .venv\Scripts\python.exe -m pip install -r "%TEMP%\maacro_requirements.txt"
        if errorlevel 1 (
            echo Setup failed. Check your internet connection and run this again.
            pause
            exit /b 1
        )
    )
    echo ok> .venv\installed.ok
)

start "" .venv\Scripts\pythonw.exe main.py
