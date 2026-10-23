"""Reguły jako dane: lista narzędzi tylko do odczytu, wzorce rozpoznawania kodu i ścieżek,
listy nazw wbudowanych dla kontroli API, wzorce komunikatów kompilatora."""
from __future__ import annotations

import re


# Ściśle tylko narzędzia do odczytu. Nie wystawiamy project, mod, wb_* itd.
READ_ONLY_TOOLS = (
    "asset_search", "game_browse", "game_read", "api_search",
    "component_search", "wiki_search", "wiki_read", "wb_knowledge",
)
# project i prefab NIE są udostępniane: asystent nie czyta plików projektów użytkownika (decyzja użytkownika).


KEEP_PREFAB_BLOCKS = ("ActionsManagerComponent",)


VIEW_QUERY_KEYS = ("query", "pattern", "grep", "search", "find", "text", "contains")


VIEW_START_KEYS = ("line_start", "start_line", "start", "from_line")


VIEW_END_KEYS = ("line_end", "end_line", "end", "to_line")


GAME_READ_ALIASES = ("game_read", "read", "open", "read_file", "cat", "functions.game_read")


VIEW_MAX_LINES = 160


_CODE_BLOCK_RE = re.compile(r"```[ \t]*([\w+\-]*)[ \t]*\n(.*?)```", re.S)


_PATH_RE = re.compile(r"((?:scripts|prefabs|configs|ui)/[\w./\-{}]+\.(?:c|et|conf|layout|proto))", re.I)


_OWN_CODE_RE = re.compile(r"szkic|nowy plik|nowa klasa|WYMY[ŚS]L", re.I)


# Tuż przed blokiem: "Przykład użycia" / "Jak użyć" = kod własny modelu, chyba że ten sam fragment
# podpisuje go jako cytat z gry ("fragment z gry", "Plik: ...", ścieżka).
_EXAMPLE_RE = re.compile(r"przykład|przyklad|jak użyć|jak uzyc|użycie|uzycie|w własnym|w swoim|własnym skrypcie", re.I)


_GAME_QUOTE_RE = re.compile(r"fragment\w*\s+z\s+(?:gry|kodu|pliku)|z kodu gry|z pliku|plik\s*:|źródł|kod\s+pochodzi", re.I)


# Separator pominięcia: sama linia "..." albo komentarz zaczynający się od "..." (np. "// ... (reszta Init)")
_EXAMPLE_PATH_RE = re.compile(r"example|yourscript|your_script|mymod|myscript|twojmod|twoj_mod|sample|placeholder", re.I)


_GAME_LABEL_RE = re.compile(r"z\s+kodu\s+gry|fragment\w*\s+z\s+gry|kod\s+z\s+gry", re.I)


_ENTRY_GUID_RE = re.compile(r'([A-Za-z_]\w*)\s+"\{([0-9A-Fa-f]{16})\}"\s*[:{]')     # (klasa wpisu, GUID wpisu) w prefabie


_SCRIPT_LIKE_RE = re.compile(r"^\s*(?:proto external|modded class|override\s|class\s+\w+\s*[:{])", re.M)


_PREFAB_LIKE_RE = re.compile(r'^\s*\w+\s+"\{[0-9A-Fa-f]{16}\}"', re.M)


_SEPARATOR_RE = re.compile(r"^\s*(?:\.\.\.|…|//\s*(?:\.\.\.|…).*|/\*\s*(?:\.\.\.|…).*\*/)\s*$")


# Błąd kompilatora Enforce Script, np. "Scripts/Game/RA_Fuel.c(13): Undefined function 'ArmaReforgerScripted.IsServer'"
_COMPILE_ERR_RE = re.compile(r"(?:Undefined|Unknown)\s+(?:function|method|variable|type|member)\s+'([\w.:]+)'", re.I)


_API_GAME_CLASSES = ("ArmaReforgerScripted", "ChimeraGame", "Game", "BaseGame")


_API_GLOBAL_OK = {"Print", "PrintFormat", "GetGame"}


# Podstawy języka (string, array, map, Cast): nie wymagają wyszukiwania w API.
_API_METHOD_OK = {"Cast", "ToString", "Format", "Length", "Contains", "IsEmpty", "Substring", "Insert", "Count",
                  "Get", "Set", "Find", "Remove", "RemoveItem", "Clear", "Resize", "Copy", "IndexOf", "Replace",
                  "ToLower", "ToUpper", "Trim", "TrimInPlace", "Split", "Join", "IsIndexValid", "Debug",
                  "FindComponent"}      # IEntity.FindComponent + Cast: sprawdzony, podstawowy wzorzec


_API_CLASS_OK = {"Math", "Math3D", "string", "array", "map", "set", "SCR_Enum", "Type"}


_API_KEYWORDS = {"if", "for", "foreach", "while", "switch", "return", "new", "delete", "super", "this", "sizeof",
                 "typename", "override", "class", "modded", "static", "protected", "private", "void", "bool", "int",
                 "float", "string", "vector", "auto", "ref", "null", "true", "false", "case", "break", "continue",
                 "else", "const", "out", "inout", "notnull", "typedef", "enum", "array", "map", "set"}


_NON_CODE_LANGS = {"xml", "json", "bat", "cmd", "powershell", "ps1", "text", "txt", "ini", "conf", "et", "log",
                   "markdown", "md", "bash", "sh", "yaml", "yml"}


_API_CODE_BLOCK_RE = re.compile(r"```[ \t]*([\w+\-]*)[ \t]*\n(.*?)```", re.S)



# ---------------------------------------------------------------- narzędzia z akcjami (od 1.7.1)
# Zabezpieczenie na wypadek, gdyby narzędzie z akcjami trafiło kiedyś do READ_ONLY_TOOLS: tylko akcje odczytu,
# bez argumentów zapisu i projectPath. Dziś project i prefab nie są udostępniane, więc te wpisy są nieaktywne.
TOOL_ACTION_LIMITS = {"project": ("browse", "read"), "prefab": ("inspect",)}
TOOL_DROP_ARGS = {
    "project": ("projectPath", "content", "createDirectories"),
    "prefab": ("projectPath", "name", "prefabType", "variant", "parentPrefab", "components",
               "description", "includeAncestry"),
}
WB_KNOWLEDGE_MAX_FILES = 2       # BK pozwala na 4 pliki po 30 tys. znaków; więcej i tak nie zmieści się w kontekście

# ---------------------------------------------------------------- błędy kompilatora z numerem linii (od 1.7.1)
# Konsola Workbencha:  @"Scripts/Game/RA_Fuel.c,21": Broken expression ...  albo  Scripts/Game/RA_Fuel.c(21): ...
_COMPILE_LINE_RES = (
    re.compile(r'@"([^"\n]+?\.c),\s*(\d+)"\s*:\s*([^\n]+)'),
    re.compile(r'([\w./\\:-]+?\.c)\((\d+)\)\s*:\s*([^\n]+)'),
)
KB_PITFALLS_QUERY = "enforce language pitfall"     # trafia w enforceScript-language.md bazy BK (punktacja 9 do 1)
KB_SECTION_RE = re.compile(r"ternary|pitfall|primitive|switch|operator", re.I)

# ---------------------------------------------------------------- składnia, której Enforce Script nie przyjmuje (od 1.7.1)
# Każda reguła ma źródło: baza wiedzy BK (enforceScript-language.md) albo potwierdzenie przez kompilator.
SYNTAX_RULES = (
    (re.compile(r"(?<![\w.])\d+(?:\.\d*)?[fF]\b|(?<![\w.])\.\d+[fF]\b"),
     "sufiks f przy liczbie (np. 0.5f) - Enforce Script go nie przyjmuje (kompilator: Broken expression); pisz 0.5"),
    (re.compile(r"\?"),
     "operator ?: lub ?. nie istnieje w Enforce Script - użyj if/else (baza wiedzy BK: enforceScript-language.md)"),
    (re.compile(r"(?<!new )\b[A-Za-z_]\w*\s*<\s*[A-Z]\w*\s*>\s*\("),
     "wywołanie z parametrem typu (np. GetComponent<T>()) nie istnieje w Enforce Script - komponent pobierasz przez "
     "Typ.Cast(owner.FindComponent(Typ))"),                                                       # od 1.8.6
    (re.compile(r'(?<![\w."])\d+(?:\.\d+)?\s*\+\s*""'),
     'liczba + tekst (3 + "tekst") to błąd parsowania - tekst musi być po lewej ("tekst" + 3)'),
)


# ---------------------------------------------------------------- wiedza przed kodem (od 1.8.0)
KB_CHECK_MAX_FILES = 2
KB_CHECK_CAP = 5000                       # znaków wzorców w podpowiedzi
KB_CHECK_DROP_WORDS = ("scr", "class")    # słowa z nazw klas pomijane w zapytaniu do bazy
# Sekcje plików bazy pokazywane najpierw: reguły, pułapki, struktura podstawowa, dobre praktyki.
KB_CHECK_PRIORITY_RE = re.compile(r"rule|pitfall|basic|structure|best|key|modd", re.I)


# ---------------------------------------------------------------- od 1.8.1
# api_search z zapytaniem "Klasa Metoda" (np. "IEntity GetOrigin"): BK szuka i tak po nazwie metody.
API_CLASS_METHOD_QUERY_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*$")
API_QUERY_KEYWORDS = ("class", "enum", "struct", "method", "function")   # "class Game" -> "Game"
API_QUERY_BUILTIN_TYPES = ("vector", "string", "array", "map", "set", "float", "int", "bool")  # "vector Distance"
COMPILE_LOOKUP_MAX = 6                   # ile różnych metod z błędów kompilatora sprawdzać automatycznie
COMPILE_LINES_MAX = 6                    # ile błędów z numerem linii pokazywać
EMERGENCY_CODE_CAP = 12000               # ile znaków kodu z odpowiedzi awaryjnej zostaje w kontekście


# ---------------------------------------------------------------- od 1.8.2
# Funkcje globalne Enforce Script: api_search indeksuje tylko składowe klas, więc dla nich zawsze zwraca
# "brak dokładnego trafienia". Bez tej listy model wnioskował, że np. GetGame() nie istnieje.
# Wartość: krótka informacja dla modelu (pusty tekst = tylko ostrzeżenie).
API_GLOBAL_FUNCTIONS = {
    "GetGame": "GetGame() zwraca obiekt gry ArmaReforgerScripted; jego metody wywołujesz jako GetGame().Metoda(...).",
    "Print": "Opis i przykłady: wiki_search('Print').",
    "PrintFormat": "Opis i przykłady: wiki_search('PrintFormat').",
}
# Klasy bazowe nieznane danym API BK (prawie połowa klas Arma ma pustą listę rodziców): silnik odczytuje
# deklarację klasy z pliku gry (asset_search + game_read) i uzupełnia łańcuch dziedziczenia.
PARENT_RESOLVE_DEPTH = 4         # ile poziomów w górę szukać w plikach gry
PARENT_RESOLVE_PER_TURN = 4      # ile klas na turę rozwiązuje silnik (każda to 2-3 wywołania MCP poza limitem modelu)
PARENT_NOTE_MAX_NAMES = 60       # ile nazw metod jednej klasy bazowej pokazać modelowi
PARENT_NOTE_CAP = 2200           # maks. długość uzupełnienia dopisanego do wyniku api_search
_CLASS_DECL_RE = r"^\s*(?:sealed\s+)?class\s+{name}\s*(?::|extends)\s*([A-Za-z_]\w*)"   # .format(name=re.escape(...))
_CLASS_ROOT_RE = r"^\s*(?:sealed\s+)?class\s+{name}\b"


# ---------------------------------------------------------------- od 1.8.3
# game_browse w BK: "pattern" to WYŁĄCZNIE filtr rozszerzenia ("*.c" -> ".c"). Każdy inny wzorzec
# (np. "*Inspect*", "GetInspect") nie pasuje do żadnego pliku i zwraca same katalogi.
GAME_BROWSE_PATTERN_RE = r"\*?\.[A-Za-z0-9]+"
GAME_BROWSE_ANY_PATTERNS = ("*", "*.*")          # równoważne braku filtra: usuwamy argument
# asset_search szuka w NAZWACH plików; nawiasy, cudzysłowy, spacje itp. oznaczają kod, nie nazwę pliku.
ASSET_QUERY_CODE_RE = r"[()\"'\s;=,<>]"
# api_search: zapytanie wyglądające na nazwę klasy i istniejące jako klasa -> pełny widok (limit=1),
# bo przy kilku wynikach BK pokazuje tylko 10 metod klasy i bez metod dziedziczonych.
API_EXACT_CLASS_RE = r"[A-Z][A-Za-z0-9_]*"
# Synteza awaryjna (gdy odpowiedź bez narzędzi w tej samej rozmowie zawiedzie dwa razy):
SYNTH_BUDGET_CHARS = 23000       # łączny rozmiar wybranych wyników
SYNTH_ITEM_MAX_CHARS = 9000      # maks. jeden wynik (wcześniej 3500: ucinało np. CharacterControllerComponent.c)


# ---------------------------------------------------------------- od 1.8.4
# Narzędzia "szukaj w treści plików", które modele wymyślają (np. game_search). Takiego narzędzia nie ma:
# ze ścieżką do pliku -> game_read z query (widok lokalny), bez ścieżki -> odrzucenie z podpowiedzią.
CONTENT_SEARCH_ALIASES = ("game_search", "search_files", "file_search", "search_content", "find_in_files",
                          "search_in_files", "grep_files", "content_search")
# Odwołania do numerów linii w odpowiedzi ("linia 12", "linie 8-12", "linii 5-7").
LINE_REF_RE = r"\blini(?:a|e|i|ach|ę)\s*(?:nr\.?\s*)?~?\s*(\d{1,5})(?:\s*[-‑–]\s*(\d{1,5}))?"
# Uwagi weryfikatora, które NIE uruchamiają rundy poprawkowej (często cytat z pominięciami).
VERIFY_NO_FIX_MARKERS = ("nie sąsiadują",)


# ---------------------------------------------------------------- od 1.8.6
QUESTION_FILES_MAX = 4           # ile nazw z pytania silnik sprawdza w asset_search przed pierwszą odpowiedzią modelu
QUESTION_NAME_RE = r"\b([A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+){2,})\b"   # SCR_X, Weapon_Base, ScriptedUserAction
