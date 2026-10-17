@echo off
title NIDAR RESCUE GCS - TEAM EDITH
cd /d "%~dp0"
echo ========================================================
echo   NIDAR RESCUE GCS - TEAM EDITH AIRMOUSE SKELETAL V1
echo ========================================================
echo Starting Ground Control Station...
set "PY_CMD="

:: 1. Prefer project virtual environment (.venv)
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -c "import PyQt6" >nul 2>&1
    if not errorlevel 1 (
        set "PY_CMD=%~dp0.venv\Scripts\python.exe"
    )
)

:: 2. Try python on PATH with PyQt6
if not defined PY_CMD (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import PyQt6" >nul 2>&1
        if not errorlevel 1 (
            set "PY_CMD=python"
        )
    )
)

:: 3. Try py -3.11 launcher if default python lacks PyQt6
if not defined PY_CMD (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3.11 -c "import PyQt6" >nul 2>&1
        if not errorlevel 1 (
            set "PY_CMD=py -3.11"
        )
    )
)

:: 4. Try standard Python 3.11 install location directly
if not defined PY_CMD (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" -c "import PyQt6" >nul 2>&1
        if not errorlevel 1 (
            set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        )
    )
)

if not defined PY_CMD (
    echo.
    echo ERROR: Python 3.10+ with PyQt6 was not found.
    echo Please ensure the project .venv or PyQt6 is installed:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo Using Python runtime: %PY_CMD%
%PY_CMD% -u "%~dp0edith_gcs_qt.py"
if errorlevel 1 (
    echo.
    echo ERROR: NIDAR GCS stopped unexpectedly. The traceback above identifies the cause.
    pause
    exit /b 1
)
pause
