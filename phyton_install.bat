@echo off
echo ============================================
echo   Instalacja pełnego środowiska Python
echo ============================================
echo.

REM --- Sprawdzanie Pythona ---
echo Sprawdzanie instalacji Python...
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Python nie jest zainstalowany.
    echo Pobierz instalator z https://www.python.org/downloads/windows/
    echo Zainstaluj Python z opcją "Add Python to PATH".
    pause
    exit /b
) ELSE (
    echo Python jest zainstalowany.
)

echo.
echo ============================================
echo   Instalacja Minicondy
echo ============================================
echo.

REM --- Pobieranie Minicondy ---
echo Pobieranie Miniconda installer...
curl -L -o miniconda_installer.exe https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe

echo Uruchamianie instalatora Minicondy...
start /wait "" miniconda_installer.exe /InstallationType=JustMe /AddToPath=1 /RegisterPython=1 /S

echo Miniconda zainstalowana.
echo.

REM --- Aktywacja conda ---
call %USERPROFILE%\Miniconda3\Scripts\activate.bat

echo ============================================
echo   Tworzenie środowiska "analysis"
echo ============================================
echo.

conda create -y -n analysis python=3.12
call conda activate analysis

echo Instalacja pakietów analitycznych...
pip install numpy pandas matplotlib seaborn plotly openpyxl yfinance

echo Instalacja narzędzi automatyzacji...
pip install pyautogui selenium playwright

echo Instalacja AI/ML...
pip install scikit-learn tensorflow
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo Instalacja narzędzi agentowych...
pip install langchain langgraph fastapi uvicorn pydantic

echo Instalacja JupyterLab + kernel...
pip install jupyterlab ipykernel
python -m ipykernel install --user --name analysis

echo.
echo ============================================
echo   Konfiguracja zakonczona
echo ============================================
echo.

echo Srodowisko Python jest gotowe.
echo Uruchom:
echo   conda activate analysis
echo   jupyter lab
echo.
pause
