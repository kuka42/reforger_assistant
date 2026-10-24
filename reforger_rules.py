"""Reguły jako dane: lista narzędzi tylko do odczytu, wzorce rozpoznawania kodu i ścieżek,
listy nazw wbudowanych dla kontroli API, wzorce komunikatów kompilatora."""
from __future__ import annotations

import re

from reforger_i18n import EN, tr


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


# Od 2.0.0 wzorce rozumieją oba języki (odpowiedzi po polsku i po angielsku).
_OWN_CODE_RE = re.compile(r"szkic|nowy plik|nowa klasa|WYMY[ŚS]L|\bsketch|\bdraft\b|new file|new class|INVENTED", re.I)


# Tuż przed blokiem: "Przykład użycia" / "Jak użyć" = kod własny modelu, chyba że ten sam fragment
# podpisuje go jako cytat z gry ("fragment z gry", "Plik: ...", ścieżka).
_EXAMPLE_RE = re.compile(r"przykład|przyklad|jak użyć|jak uzyc|użycie|uzycie|w własnym|w swoim|własnym skrypcie"
                         r"|\bexample|how to use|\busage\b|in your own|your own script", re.I)


_GAME_QUOTE_RE = re.compile(r"fragment\w*\s+z\s+(?:gry|kodu|pliku)|z kodu gry|z pliku|plik\s*:|źródł|kod\s+pochodzi"
                            r"|(?:excerpt|fragment|snippet)\w*\s+from\s+(?:the\s+)?(?:game|code|file)|from (?:the )?game code"
                            r"|from (?:the )?file|\bfile\s*:|\bsource\b|code\s+comes\s+from", re.I)


# Separator pominięcia: sama linia "..." albo komentarz zaczynający się od "..." (np. "// ... (reszta Init)")
_EXAMPLE_PATH_RE = re.compile(r"example|yourscript|your_script|mymod|myscript|twojmod|twoj_mod|sample|placeholder", re.I)


_GAME_LABEL_RE = re.compile(r"z\s+kodu\s+gry|fragment\w*\s+z\s+gry|kod\s+z\s+gry"
                            r"|from\s+(?:the\s+)?game\s+code|(?:excerpt|fragment|snippet)\w*\s+from\s+(?:the\s+)?game"
                            r"|code\s+from\s+(?:the\s+)?game", re.I)


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
     tr("sufiks f przy liczbie (np. 0.5f) - Enforce Script go nie przyjmuje (kompilator: Broken expression); pisz 0.5",
        "f suffix on a number (e.g. 0.5f) - Enforce Script does not accept it (compiler: Broken expression); write 0.5")),
    (re.compile(r"\?"),
     tr("operator ?: lub ?. nie istnieje w Enforce Script - użyj if/else (baza wiedzy BK: enforceScript-language.md)",
        "the ?: or ?. operator does not exist in Enforce Script - use if/else (BK knowledge base: enforceScript-language.md)")),
    (re.compile(r"(?<!new )\b[A-Za-z_]\w*\s*<\s*[A-Z]\w*\s*>\s*\("),
     tr("wywołanie z parametrem typu (np. GetComponent<T>()) nie istnieje w Enforce Script - komponent pobierasz przez "
        "Typ.Cast(owner.FindComponent(Typ))",
        "a call with a type parameter (e.g. GetComponent<T>()) does not exist in Enforce Script - get a component with "
        "Type.Cast(owner.FindComponent(Type))")),                                                  # od 1.8.6
    (re.compile(r'(?<![\w."])\d+(?:\.\d+)?\s*\+\s*""'),
     tr('liczba + tekst (3 + "tekst") to błąd parsowania - tekst musi być po lewej ("tekst" + 3)',
        'number + text (3 + "text") is a parse error - the text must be on the left ("text" + 3)')),
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
    "GetGame": tr("GetGame() zwraca obiekt gry ArmaReforgerScripted; jego metody wywołujesz jako GetGame().Metoda(...).",
                  "GetGame() returns the game object ArmaReforgerScripted; call its methods as GetGame().Method(...)."),
    "Print": tr("Deklarację z pliku gry silnik dopisuje poniżej (jeśli plik jest w danych gry).",
                "The engine appends the declaration from the game file below (if the file is in the game data)."),
    "PrintFormat": tr("Deklarację z pliku gry silnik dopisuje poniżej (jeśli plik jest w danych gry).",
                      "The engine appends the declaration from the game file below (if the file is in the game data)."),
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
# Od 2.0.0 także po angielsku ("line 12", "lines 8-12").
LINE_REF_RE = (r"\b(?:lini(?:a|e|i|ach|ę)|lines?)\s*(?:nr\.?\s*|no\.\s*|#)?~?\s*(\d{1,5})"
               r"(?:\s*[-‑–]\s*(\d{1,5}))?")
# Nagłówek kolumny tabeli z numerami linii ("Linia", "Linie", "Line", "Lines").
LINE_COLUMN_RE = r"(?i)[*`]*(?:lini|line)"
# Uwagi weryfikatora, które NIE uruchamiają rundy poprawkowej (często cytat z pominięciami).
VERIFY_NO_FIX_MARKERS = ("nie sąsiadują", "not adjacent")


# ---------------------------------------------------------------- od 1.8.6
QUESTION_FILES_MAX = 4           # ile nazw z pytania silnik sprawdza w asset_search przed pierwszą odpowiedzią modelu
QUESTION_NAME_RE = r"\b([A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+){2,})\b"   # SCR_X, Weapon_Base, ScriptedUserAction


# ---------------------------------------------------------------- od 1.8.7
# Rozumowanie modelu, które wyciekło do treści odpowiedzi (gpt-oss bez osobnego pola thinking).
REASONING_LEAK_START_RE = r"^\s*(?:We need to|We have|We should|We must|Let's|Let us|The user|User asks|I need to|Need to)\b"
REASONING_LEAK_MARKERS_RE = r"\b(?:We need|We should|We have|We must|Let's|We can|We might|Thus|So we)\b"
# Od 2.0.0: w wersji angielskiej odpowiedź też jest po angielsku, więc wyciek musi mieć więcej znaczników rozumowania.
REASONING_LEAK_MIN_MARKERS = 3 if EN else 2
# Ile razy ten sam wiersz tabeli / linia tekstu może się powtórzyć, zanim silnik uzna to za zapętlenie.
REPEAT_LINE_MAX = 2
# Zalecanie SCR_ jako prefiksu własnego moda (w prozie).
SCR_TAG_TEXT_RE = (r"(?:prefiks\w*|prefix\w*|tag\w*)\s*[:`*]*\s*`?SCR_`?\s*\+|`?SCR_`?\s*\+\s*(?:własn|tag|nazw|your|own|name)"
                   r"|(?:tag|prefiks|prefix)[^\n]{0,80}\((?:np\.|e\.g\.)\s*`?SCR_`?\s*[,)]"
                   r"|(?<!nie )(?:używaj|użyj|stosuj|zacznij)\w*\s+(?:od\s+)?(?:prefiksu\s+)?`?SCR_`?\s*(?:\+|jako|dla)"
                   r"|(?<!not )(?<!n't )(?<!never )\b(?:use|start\s+with|prefix\s+with)\s+(?:the\s+)?(?:prefix\s+)?`?SCR_`?\s*"
                   r"(?:\+|as\b|for\b)"
                   r"|(?<!not )(?<!n't )(?<!never )\b(?:use|start\s+with)\s+(?:the\s+)?`?SCR_`?\s+prefix\s+(?:for|as|in|on)\s+"
                   r"(?:your|all|mod|own|new)")
# Typy wartości Enforce Script (do kontroli typu zwracanego przy przypisaniu).
VALUE_TYPES = ("int", "float", "bool", "string", "vector", "ResourceName")
VALUE_TYPE_COMPAT = (("int", "float"), ("float", "int"), ("string", "ResourceName"), ("ResourceName", "string"))


# ---------------------------------------------------------------- od 1.8.8
# Zastój (rundy bez nowych danych): koniec wyszukiwania po STALL_STOP_ROUNDS rundach, ale tylko gdy model wykonał już
# STALL_STOP_MIN_CALLS wywołań MCP; bez tego warunku dopiero po STALL_STOP_ROUNDS_HARD rundach.
STALL_STOP_ROUNDS = 4
STALL_STOP_ROUNDS_HARD = 6
STALL_STOP_MIN_CALLS = 8


# ---------------------------------------------------------------- od 1.9.2
# Pliki gry z deklaracjami funkcji globalnych (nazwa pliku bez .c; ścieżkę silnik znajduje sam przez asset_search).
# Potwierdzone przez użytkownika w Workbenchu: Print i PrintFormat są w EnDebug.c.
GLOBAL_FUNCTION_FILES = {"Print": "EnDebug", "PrintFormat": "EnDebug"}
# Przykładowe nazwy klas/plików moda z prefiksem gry w tekście odpowiedzi (od 1.9.3).
SCR_EXAMPLE_NAME_RE = r"`(?:class\s+)?SCR_(?:My|Example|Mod|Custom|Test)\w*(?:\.c)?`"
