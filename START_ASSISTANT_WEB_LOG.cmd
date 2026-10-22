@echo off
setlocal
rem Wariant z zapisem logu do pliku (UTF-8) w folderze logs. Okno konsoli pozostaje puste.
rem Podglad na zywo w drugim oknie PowerShella:  Get-Content .\logs\NAZWA.txt -Wait
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo Reforger Assistant WEB - Ollama + Enfusion MCP BK (z logiem do pliku)

where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo BLAD: nie znaleziono polecenia "python" w PATH.
    pause
    exit /b 1
)

for %%F in (reforger_assistant_WEB.py reforger_assistant_MCP_BK.py reforger_helpers.py assistant.html) do (
    if not exist "%%F" (
        echo.
        echo BLAD: obok tego pliku nie ma pliku %%F
        echo Skopiuj wszystkie pliki asystenta do jednego folderu.
        pause
        exit /b 1
    )
)

if not exist "logs" mkdir "logs"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set STAMP=%%i
set LOGFILE=logs\log_%STAMP%.txt
echo Log: %LOGFILE%
echo Serwer: http://127.0.0.1:8765  (zatrzymanie: zamknij to okno albo Ctrl+C)

rem --- Opcjonalna konfiguracja: usun "rem " z wybranych linii i ustaw wartosc ---
rem Model i kontekst mozna tez wybrac w interfejsie (przyciski u gory). Zapisane tam ustawienia
rem (assistant_web_data\settings.json) maja pierwszenstwo przed OLLAMA_MODEL i OLLAMA_NUM_CTX.
rem set OLLAMA_MODEL=gpt-oss:20b
rem set OLLAMA_NUM_CTX=32768
rem set OLLAMA_NUM_PREDICT=16384
rem set REFORGER_VERIFY=log

python -u "reforger_assistant_WEB.py" > "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo.
    echo Program zakonczyl sie bledem. Szczegoly w pliku %LOGFILE%
    pause
)
endlocal
