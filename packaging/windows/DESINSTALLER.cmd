@echo off
rem Chess Calculation Trainer - Desinstallation (donnees conservees).
rem Tout tient sur une ligne : ce fichier est supprime pendant la desinstallation
rem et cmd.exe relit un .cmd ligne par ligne.
setlocal
cd /d "%~dp0"
if not exist "%~dp0scripts\windows\uninstall.ps1" (echo ERREUR : fichiers incomplets. & pause & exit /b 1)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\uninstall.ps1" & pause & exit /b
