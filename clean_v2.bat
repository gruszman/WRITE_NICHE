@echo off
chcp 65001 >nul
title Czyszczenie systemu Windows

:: 1. Automatyczne wymuszenie uprawnien Administratora
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Wymagane uprawnienia Administratora. Ponowne uruchamianie...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo [1/4] Zamykanie zbednych procesow w tle...
:: Dopisz lub usun programy wedlug potrzeb (nie dodawaj tu python.exe, jesli dzialaja skrypty w tle)
for %%p in (
    chrome.exe
    msedge.exe
    firefox.exe
    OneDrive.exe
    Teams.exe
    ms-teams.exe
    Spotify.exe
    Discord.exe
    YourPhone.exe
    PhoneExperienceHost.exe
) do (
    taskkill /F /IM %%p /T >nul 2>&1
)

echo [2/4] Czyszczenie folderu Temp uzytkownika...
del /q /f /s "%TEMP%\*" >nul 2>&1
for /d %%x in ("%TEMP%\*") do rd /s /q "%%x" >nul 2>&1

echo [3/4] Czyszczenie folderu Temp systemu...
del /q /f /s "C:\Windows\Temp\*" >nul 2>&1
for /d %%x in ("C:\Windows\Temp\*") do rd /s /q "%%x" >nul 2>&1

echo [4/4] Oproznianie Kosza...
powershell.exe -NoProfile -Command "Clear-RecycleBin -Force -ErrorAction SilentlyContinue" >nul 2>&1
:: Zapasowe czyszczenie, gdyby PowerShell napotkal uszkodzona sciezke
rd /s /q "C:\$Recycle.Bin" >nul 2>&1

echo.
echo Czyszczenie zakonczone pomyslnie!
pause