"""Konfiguracja asystenta: wersja, ścieżki, limity i tryby (zmienne środowiskowe)."""
from __future__ import annotations

import os


VERSION = "1.8.6"

# Ścieżki potwierdzone podczas poprzednich testów użytkownika — edytowalne.
MCP_SCRIPT = os.environ.get(
    "ENFUSION_MCP_SCRIPT", r"F:\reforger-scripts\enfusion-mcp-BK\dist\index.js"
)
GAME_PATH = os.environ.get(
    "ENFUSION_GAME_PATH", r"D:\SteamLibrary\steamapps\common\Arma Reforger"
)

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


OLLAMA_URL = os.environ.get("OLLAMA_CHAT_URL", "http://127.0.0.1:11434/api/chat")
MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b")
NUM_CTX = _env_int("OLLAMA_NUM_CTX", 32768)
# Wszystkie limity można zmienić zmienną środowiskową (PowerShell: $env:NAZWA = wartość)
# przed startem serwera, bez edycji pliku. W logu przy starcie jest linia [CONFIG].
OLLAMA_NUM_PREDICT = _env_int("OLLAMA_NUM_PREDICT", 16384)  # max tokenów JEDNEJ generacji (z rozumowaniem); 0 lub -1 = bez limitu
MAX_TOOL_CALLS = _env_int("REFORGER_MAX_TOOL_CALLS", 25)    # limit wywołań MCP na jedno pytanie, przeciw zapętleniom
MAX_HISTORY_MESSAGES = _env_int("REFORGER_MAX_HISTORY_MESSAGES", 60)  # pełne tury, nie urywamy historii narzędzi
MAX_TOOL_RESULT_CHARS = _env_int("REFORGER_MAX_TOOL_RESULT_CHARS", 14000)   # jeden odczyt MCP w kontekście modelu
MAX_TOOL_CONTEXT_CHARS = _env_int("REFORGER_MAX_TOOL_CONTEXT_CHARS", 45000)  # suma wyników MCP w aktywnej turze
FINISHED_SOURCE_CHARS = _env_int("REFORGER_FINISHED_SOURCE_CHARS", 3600)    # po turze: max rozmiar jednego odczytu pliku
FINISHED_EVIDENCE_CHARS = _env_int("REFORGER_FINISHED_EVIDENCE_CHARS", 20000)  # po turze: suma dowodów w historii (~6 tys. tokenów)
COMPACT_SEARCH_RESULT_CHARS = _env_int("REFORGER_COMPACT_SEARCH_CHARS", 1200)  # wyniki api_search/asset_search tracą wartość najszybciej
# Miękkie limity wyników (model sam podbija limit do 20, a wynik klasy to ~14 tys. znaków).
SOFT_LIMIT_CLASS_SEARCH = _env_int("REFORGER_SOFT_LIMIT_CLASS", 5)    # api_search type=class/any
SOFT_LIMIT_OTHER_SEARCH = _env_int("REFORGER_SOFT_LIMIT_OTHER", 10)   # api_search type=method/property/enum (wyniki są krótkie)
COMPACT_OLD_RESULT_CHARS = _env_int("REFORGER_COMPACT_OLD_CHARS", 3600)  # starsze odczyty zachowują skrót
MCP_TIMEOUT = _env_int("REFORGER_MCP_TIMEOUT", 90)          # inicjalizacja / narzędzia (sekundy)
OLLAMA_TIMEOUT = _env_int("OLLAMA_TIMEOUT", 300)
OLLAMA_TEMPERATURE = _env_float("OLLAMA_TEMPERATURE", 0.1)
OLLAMA_THINK = os.environ.get("OLLAMA_THINK", "")   # np. low / medium / high; puste = nie wysyłaj
THINKING_KEEP_CHARS = _env_int("REFORGER_THINKING_CHARS", 3000)   # ile końcówki rozumowania zostaje w kontekście w obrębie tury; 0 = nic, -1 = całość
VIEW_LIMIT_PER_FILE = _env_int("REFORGER_VIEW_LIMIT", 6)    # max lokalnych widoków (query/zakres) jednego pliku w turze
# Weryfikator cytatów: off = wyłączony; log = tylko wpisy [VERIFY] w logu; footer = dodatkowo znacznik pod odpowiedzią;
# fix (domyślnie od 1.8.4) = jedna runda poprawkowa (cytat "z kodu gry", którego nie ma w pliku; numery linii
# spoza widoków pliku), a uwagi, które zostały, trafiają pod odpowiedź.
VERIFY_MODE = os.environ.get("REFORGER_VERIFY", "fix").strip().lower()
if VERIFY_MODE not in ("off", "log", "footer", "fix"):
    VERIFY_MODE = "fix"
# Kontrola nazw API w kodzie odpowiedzi: off; log (tylko wpis [API] w logu); fix (domyślnie: jedna runda
# poprawkowa, a gdy nazwy nadal są niepotwierdzone, ostrzeżenie pod odpowiedzią).
API_CHECK_MODE = os.environ.get("REFORGER_API_CHECK", "fix").strip().lower()
if API_CHECK_MODE not in ("off", "log", "fix"):
    API_CHECK_MODE = "fix"
# Odpowiedzi awaryjne (synteza bez pełnego badania) w kontekście modelu: placeholder (domyślnie) albo keep.
# Błąd z takiej odpowiedzi potrafił trafić do następnej tury jako "z kodu gry".
# Wiedza przed kodem (od 1.8.0): gdy model pisze własny kod, a w tej turze nie sięgnął do bazy wiedzy BK,
# silnik sam pobiera pasujące wzorce (wb_knowledge) i daje modelowi jedną rundę na porównanie. on / off.
KB_CHECK_MODE = os.environ.get("REFORGER_KB_CHECK", "on").strip().lower()
if KB_CHECK_MODE not in ("on", "off"):
    KB_CHECK_MODE = "on"
EMERGENCY_IN_HISTORY = os.environ.get("REFORGER_EMERGENCY_IN_HISTORY", "placeholder").strip().lower()
if EMERGENCY_IN_HISTORY not in ("placeholder", "keep"):
    EMERGENCY_IN_HISTORY = "placeholder"


def config_summary() -> str:
    return (f"[CONFIG] wersja={VERSION} model={MODEL} num_ctx={NUM_CTX} "
            f"num_predict={OLLAMA_NUM_PREDICT if OLLAMA_NUM_PREDICT > 0 else 'bez limitu'} "
            f"temperature={OLLAMA_TEMPERATURE} think={OLLAMA_THINK or '-'} "
            f"max_wywołań_MCP={MAX_TOOL_CALLS} wynik_narzędzia={MAX_TOOL_RESULT_CHARS} "
            f"kontekst_narzędzi={MAX_TOOL_CONTEXT_CHARS} dowody_po_turze={FINISHED_EVIDENCE_CHARS} "
            f"limit_api_klasy={SOFT_LIMIT_CLASS_SEARCH}/inne={SOFT_LIMIT_OTHER_SEARCH} "
            f"limit_widoków={VIEW_LIMIT_PER_FILE} weryfikator={VERIFY_MODE} awaryjne_w_historii={EMERGENCY_IN_HISTORY} "
            f"rozumowanie_w_turze={THINKING_KEEP_CHARS if THINKING_KEEP_CHARS >= 0 else 'całość'} "
            f"kontrola_api={API_CHECK_MODE} wiedza_przed_kodem={KB_CHECK_MODE}")
