@echo off
setlocal
rem Konsola i Python w UTF-8: polskie znaki w oknie i w logu nie rozsypuja sie.
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo Reforger Assistant WEB - Ollama + Enfusion MCP BK

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
        echo BLAD: obok START_ASSISTANT_WEB.cmd nie ma pliku %%F
        echo Skopiuj wszystkie pliki asystenta do jednego folderu.
        pause
        exit /b 1
    )
)

rem --- Opcjonalna konfiguracja: usun "rem " z wybranych linii i ustaw wartosc ---
rem Model i kontekst mozna tez wybrac w interfejsie (przyciski u gory). Zapisane tam ustawienia
rem (assistant_web_data\settings.json) maja pierwszenstwo przed OLLAMA_MODEL i OLLAMA_NUM_CTX.
rem set OLLAMA_MODEL=gpt-oss:20b
rem set OLLAMA_NUM_CTX=32768
rem set OLLAMA_NUM_PREDICT=16384
rem set OLLAMA_THINK=
rem set REFORGER_MAX_TOOL_CALLS=25
rem set REFORGER_THINKING_CHARS=3000
rem set REFORGER_VERIFY=log
rem set REFORGER_EMERGENCY_IN_HISTORY=placeholder

python "reforger_assistant_WEB.py"
if errorlevel 1 (
    echo.
    echo Program zakonczyl sie bledem. Sprawdz komunikat wyzej.
    pause
)
endlocal
