@echo off
rem Chess Calculation Trainer - Mise a jour
rem PowerShell est lance pour CE script seulement (-ExecutionPolicy Bypass sur ce
rem processus) : aucune politique du poste n'est modifiee.
setlocal
cd /d "%~dp0"
if not exist "%~dp0scripts\windows\update.ps1" (
  echo ERREUR : fichiers incomplets. Extrayez tout le ZIP ^(clic droit, Extraire tout^) puis relancez.
  pause
  exit /b 1
)
echo ==========================================
echo  Chess Calculation Trainer - Mise a jour
echo ==========================================
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\update.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
