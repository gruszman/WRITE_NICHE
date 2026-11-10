@echo off
echo Czyszczenie folderu Temp uzytkownika...
del /q /f /s "%TEMP%\*"
for /d %%x in ("%TEMP%\*") do rd /s /q "%%x"

echo Czyszczenie folderu Temp systemu...
del /q /f /s "C:\Windows\Temp\*"
for /d %%x in ("C:\Windows\Temp\*") do rd /s /q "%%x"

echo Oproznianie Kosza...
PowerShell.exe -NoProfile -Command Clear-RecycleBin -Confirm:$false

echo Czyszczenie zakonczone!
pause