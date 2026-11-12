@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0.pydeps"
set "MPLCONFIGDIR=%~dp0.cache\matplotlib"
set "PYTHONIOENCODING=utf-8"

where python >nul 2>nul
if errorlevel 1 (
  echo Python not found. Install Python 3.11+ and try again.
  pause
  exit /b 1
)

if not exist ".pydeps\ezdxf" (
  echo Installing dependencies into .pydeps ...
  python -m pip install --disable-pip-version-check --target .pydeps -r requirements.txt
  if errorlevel 1 (
    echo Dependency install failed.
    pause
    exit /b 1
  )
)

python -m netsketch serve %*
if errorlevel 1 pause
