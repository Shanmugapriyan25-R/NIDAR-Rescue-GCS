@echo off
title NIDAR RESCUE GCS - TEAM EDITH
cd /d "%~dp0"
echo ========================================================
echo   NIDAR RESCUE GCS - TEAM EDITH AIRMOUSE SKELETAL V1
echo ========================================================
echo Starting Ground Control Station...
set "PY_CMD="

:: 1. Try python on PATH with PyQt6
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import PyQt6" >nul 2>&1
    if not errorlevel 1 (
        set "PY_CMD=python"
    )
)

:: 2. Try py -3.11 launcher if default python lacks PyQt6
if not defined PY_CMD (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3.11 -c "import PyQt6" >nul 2>&1
        if not errorlevel 1 (
            set "PY_CMD=py -3.11"
        )
    )
)

:: 3. Try standard Python 3.11 install location directly
if not defined PY_CMD (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" -c "import PyQt6" >nul 2>&1
        if not errorlevel 1 (
            set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        )
    )
)

if not defined PY_CMD (
    echo ERROR: Python 3.10+ with PyQt6 was not found.
    echo Please ensure PyQt6 is installed: pip install PyQt6
    pause
    exit /b 1
)

%PY_CMD% -u "%~dp0edith_gcs_qt.py"
if errorlevel 1 (
    echo.
    echo ERROR: NIDAR GCS stopped unexpectedly. The traceback above identifies the cause.
    pause
    exit /b 1
)
pause
