@echo off
REM ==================================================================
REM   Build PickUp Manager standalone .exe (Windows)
REM   Esegui da Prompt dei comandi nella cartella del progetto.
REM ==================================================================

echo.
echo [1/4] Verifica Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRORE: Python non trovato. Installa Python 3.10+ da python.org
    echo Ricordati di spuntare "Add Python to PATH" durante l'installazione.
    pause
    exit /b 1
)

echo.
echo [2/4] Creazione virtual environment in .venv ...
if not exist .venv (
    python -m venv .venv
)
call .venvScriptsactivate.bat

echo.
echo [3/4] Installazione dipendenze...
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt
if errorlevel 1 (
    echo ERRORE durante installazione dipendenze.
    pause
    exit /b 1
)

echo.
echo [4/4] Build con PyInstaller...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller pickup_manager.spec
if errorlevel 1 (
    echo ERRORE durante il build.
    pause
    exit /b 1
)

echo.
echo ==================================================================
echo   BUILD COMPLETATO!
echo.
echo   File generato: dist\PickupManager.exe
echo.
echo   Per usarlo sulla chiavetta USB:
echo     1. Copia dist\PickupManager.exe sulla chiavetta
echo     2. Copia anche avvia.bat sulla chiavetta
echo     3. Doppio click su avvia.bat per partire
echo ==================================================================
pause

