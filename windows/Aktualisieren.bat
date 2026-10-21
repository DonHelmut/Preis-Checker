@echo off
REM Preis-Checker auf der VM aktualisieren. IP unten anpassen.
set VM=192.168.1.50:8080

echo Update wird angefordert ...
curl -s -f -X POST http://%VM%/api/update >nul
if errorlevel 1 (
  echo FEHLER: VM nicht erreichbar ^(%VM%^)
  pause
  exit /b 1
)
echo Laeuft ... ^(kann ein paar Minuten dauern^)
for /l %%i in (1,1,60) do (
  timeout /t 5 /nobreak >nul
  curl -s -f http://%VM%/api/update/status > "%TEMP%\pc_update.txt" 2>nul
  findstr /b "ok fehler" "%TEMP%\pc_update.txt" >nul && goto fertig
)
echo Zeitueberschreitung. Log auf der VM: data/update.log
pause
exit /b 1

:fertig
type "%TEMP%\pc_update.txt"
echo.
curl -s http://%VM%/api/version
echo.
pause
