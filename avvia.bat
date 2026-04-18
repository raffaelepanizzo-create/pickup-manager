@echo off
REM ==================================================================
REM   Avvio PickUp Manager dalla chiavetta USB
REM   Doppio-click per partire. Il browser si apre automaticamente.
REM   Il DB pickup.db viene creato/aggiornato sulla chiavetta accanto
REM   a questo file (persistenza garantita).
REM ==================================================================
title PickUp Manager - Server
cd /d "%~dp0"
echo.
echo Avvio PickUp Manager...
echo Per fermare il server chiudi questa finestra.
echo.
PickupManager.exe
pause

