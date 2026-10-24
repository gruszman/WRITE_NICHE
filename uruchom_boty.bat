@echo off
setlocal

REM ==========================================
REM Autostart botow Python przez Anaconde
REM ==========================================

set "SKRYPTY=C:\Users\gruszkam.ENERGO\Downloads"
set "PYTHONW=C:\archiwum\aaaa\pythonw.exe"

REM Zakoncz, jezeli interpreter nie istnieje
if not exist "%PYTHONW%" exit /b 1

REM Uruchom bota deszczowego
start "DESZCZ" /min "%PYTHONW%" "%SKRYPTY%\deszcz.py"
timeout /t 3 /nobreak >nul

REM Uruchom monitor BTC
start "BTC BOX" /min "%PYTHONW%" "%SKRYPTY%\THE_BOX_BTC_V1.py"
timeout /t 3 /nobreak >nul

REM Uruchom system Gold
start "GOLD BOT" /min "%PYTHONW%" "%SKRYPTY%\THE_BOX_GOLD_V2.py"

REM Uruchom system indykator short
start "GOLD short BOT2" /min "%PYTHONW%" "%SKRYPTY%\new_short_m15_v2.py"


REM Skaner SP500
start "BTC BOT2" /min "%PYTHONW%" "%SKRYPTY%\SKANER_SP500_V5.py"

REM skaner GPW
start "BTC BOT3" /min "%PYTHONW%" "%SKRYPTY%\SKANER_GPW_V6.py"


endlocal
exit /b


