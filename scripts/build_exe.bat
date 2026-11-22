@echo off
REM ============================================================================
REM AgroScan Windows Standalone Executable Build Script (T4.1)
REM Usage: scripts\build_exe.bat
REM Output: dist\AgroScan\AgroScan.exe
REM ============================================================================
setlocal
cd /d "%~dp0\.."

echo [AgroScan Build] Checking Python environment...
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [AgroScan Build] Cleaning previous build artifacts...
if exist "build\AgroScan" rmdir /s /q "build\AgroScan"
if exist "dist\AgroScan" rmdir /s /q "dist\AgroScan"

echo [AgroScan Build] Running PyInstaller with agroscan.spec...
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean agroscan.spec
if errorlevel 1 (
    echo [AgroScan Build] ERROR: PyInstaller build failed.
    exit /b 1
)

if exist ".env.example" (
    copy /y ".env.example" "dist\AgroScan\.env.example" >nul
)

echo [AgroScan Build] SUCCESS: Standalone executable created at dist\AgroScan\AgroScan.exe
exit /b 0

