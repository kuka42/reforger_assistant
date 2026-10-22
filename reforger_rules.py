"""Reguły jako dane: lista narzędzi tylko do odczytu, wzorce rozpoznawania kodu i ścieżek,
listy nazw wbudowanych dla kontroli API, wzorce komunikatów kompilatora."""
from __future__ import annotations

import re


# Ściśle tylko narzędzia do odczytu. Nie wystawiamy project, mod, wb_* itd.
READ_ONLY_TOOLS = (
    "asset_search", "game_browse", "game_read", "api_search",
    "component_search", "wiki_search", "wiki_read", "wb_knowledge",
)


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
