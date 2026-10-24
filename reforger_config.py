"""Konfiguracja asystenta: wersja, ścieżki, limity i tryby (zmienne środowiskowe)."""
from __future__ import annotations

import os


VERSION = "2.0.2"

# Ścieżki (od 1.9.0 ustawiane także w interfejsie): zmienna środowiskowa > assistant_web_data/settings.json
# > wartość domyślna poniżej. Zmiana w interfejsie obowiązuje od następnego uruchomienia.
from reforger_paths import resolve as _resolve_path, default_docs_path as _default_docs_path
from reforger_i18n import LANG  # noqa: F401  (od 2.0.0: "pl" / "en"; REFORGER_LANG albo "lang" w settings.json)

DEFAULT_MCP_SCRIPT = r"C:\enfusion-mcp-BK\dist\index.js"
DEFAULT_GAME_PATH = r"C:\Program Files\Steam\steamapps\common\Arma Reforger"
MCP_SCRIPT, _MCP_SRC = _resolve_path("mcp_script", DEFAULT_MCP_SCRIPT)
GAME_PATH, _GAME_SRC = _resolve_path("game_path", DEFAULT_GAME_PATH)
DOCS_PATH, _DOCS_SRC = _resolve_path("docs_path", "")          # puste = Arma Reforger Tools obok gry
if not DOCS_PATH:
    DOCS_PATH, _DOCS_SRC = _default_docs_path(GAME_PATH), "auto"
PATH_SOURCES = {"mcp_script": _MCP_SRC, "game_path": _GAME_SRC, "docs_path": _DOCS_SRC}

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
# Od 1.8.7: odpowiedź Ollamy odbierana na bieżąco (stream). Gdy samo rozumowanie przekroczy THINK_ABORT_TOKENS
# (a tekstu odpowiedzi jeszcze nie ma), silnik przerywa generację zamiast czekać do num_predict (testy: 16384 tokenów
# rozumowania i pusta odpowiedź, ok. 2-3 min). 0 = bez przerywania. REFORGER_STREAM=off wraca do starego trybu.
OLLAMA_STREAM = os.environ.get("REFORGER_STREAM", "on").strip().lower() != "off"
THINK_ABORT_TOKENS = _env_int("REFORGER_THINK_ABORT", 8000)
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
    if LANG == "en":
        return (f"[CONFIG] version={VERSION} model={MODEL} num_ctx={NUM_CTX} "
                f"num_predict={OLLAMA_NUM_PREDICT if OLLAMA_NUM_PREDICT > 0 else 'unlimited'} "
                f"temperature={OLLAMA_TEMPERATURE} think={OLLAMA_THINK or '-'} "
                f"max_MCP_calls={MAX_TOOL_CALLS} tool_result={MAX_TOOL_RESULT_CHARS} "
                f"tool_context={MAX_TOOL_CONTEXT_CHARS} evidence_after_turn={FINISHED_EVIDENCE_CHARS} "
                f"api_limit_class={SOFT_LIMIT_CLASS_SEARCH}/other={SOFT_LIMIT_OTHER_SEARCH} "
                f"view_limit={VIEW_LIMIT_PER_FILE} verifier={VERIFY_MODE} emergency_in_history={EMERGENCY_IN_HISTORY} "
                f"reasoning_in_turn={THINKING_KEEP_CHARS if THINKING_KEEP_CHARS >= 0 else 'all'} "
                f"api_check={API_CHECK_MODE} knowledge_before_code={KB_CHECK_MODE} "
                f"stream={'on' if OLLAMA_STREAM else 'off'} reasoning_abort={THINK_ABORT_TOKENS or 'off'} language={LANG}")
    return (f"[CONFIG] wersja={VERSION} model={MODEL} num_ctx={NUM_CTX} "
            f"num_predict={OLLAMA_NUM_PREDICT if OLLAMA_NUM_PREDICT > 0 else 'bez limitu'} "
            f"temperature={OLLAMA_TEMPERATURE} think={OLLAMA_THINK or '-'} "
            f"max_wywołań_MCP={MAX_TOOL_CALLS} wynik_narzędzia={MAX_TOOL_RESULT_CHARS} "
            f"kontekst_narzędzi={MAX_TOOL_CONTEXT_CHARS} dowody_po_turze={FINISHED_EVIDENCE_CHARS} "
            f"limit_api_klasy={SOFT_LIMIT_CLASS_SEARCH}/inne={SOFT_LIMIT_OTHER_SEARCH} "
            f"limit_widoków={VIEW_LIMIT_PER_FILE} weryfikator={VERIFY_MODE} awaryjne_w_historii={EMERGENCY_IN_HISTORY} "
            f"rozumowanie_w_turze={THINKING_KEEP_CHARS if THINKING_KEEP_CHARS >= 0 else 'całość'} "
            f"kontrola_api={API_CHECK_MODE} wiedza_przed_kodem={KB_CHECK_MODE} "
            f"stream={'on' if OLLAMA_STREAM else 'off'} przerwanie_rozumowania={THINK_ABORT_TOKENS or 'off'} jezyk={LANG}")
