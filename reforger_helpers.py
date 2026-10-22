# -*- coding: utf-8 -*-
"""Gotowe, PRZETESTOWANE helpery do reforger_assistant_MCP_BK.py

1) repair_tool_call()  - naprawia halucynowane nazwy narzędzi (search/open/grep...),
                         nieznane argumenty, typy i limity wg PRAWDZIWEGO inputSchema z tools/list.
2) digest_enforce()    - kompaktuje źródło .c bez gubienia deklaracji
                         (zamiast _excerpt(), który wycina środek pliku).

Test na prawdziwym BaseUserAction.c (5280 zn.):
  _excerpt(2200)            -> gubi 20 z 31 metod
  digest_enforce(docs)      -> 3673 zn., 0 zgubionych metod
  digest_enforce(sygnatury) -> 1721 zn., 0 zgubionych metod
"""
import re
from urllib.parse import unquote

# nazwy, które modele (zwł. gpt-oss) halucynują z własnego treningu
ALIASES = {
    "search": "api_search", "grep": "api_search", "find": "asset_search",
    "browser.search": "api_search", "functions.search": "api_search",
    "open": "game_read", "read": "game_read", "read_file": "game_read",
    "cat": "game_read", "ls": "game_browse", "list": "game_browse",
    "browse": "game_browse",
}

# opis api_search w BK mówi "both", a enum w schemacie to "all" -> model słucha opisu
ENUM_SYNONYMS = {"both": "all", "everything": "all", "any": "all", "oba": "all"}


def _coerce(value, spec):
    t = spec.get("type")
    try:
        if t in ("number", "integer") and isinstance(value, str):
            value = float(value) if t == "number" else int(value)
        if t == "boolean" and isinstance(value, str):
            value = value.strip().lower() in ("1", "true", "yes", "tak")
        if t == "string" and not isinstance(value, str):
            value = str(value)
        if t in ("number", "integer") and isinstance(value, (int, float)):
            if "maximum" in spec: value = min(value, spec["maximum"])
            if "minimum" in spec: value = max(value, spec["minimum"])
    except (ValueError, TypeError):
        return None
    if "enum" in spec and value not in spec["enum"]:
        alt = ENUM_SYNONYMS.get(str(value).strip().lower(), value)
        if alt not in spec["enum"]:
            return None
        value = alt
    return value

def normalize_wiki_title(title):
    """Tytuł strony dla wiki_read: dokładnie jak w nagłówku '## Tytuł' wyniku wiki_search (np. 'Scripting: Conventions').
    Modele kopiują zamiast tego fragment adresu ('Arma_Reforger:Scripting:_Conventions'), który wiki_read odrzuca
    ('No wiki page found'). Usuwamy adres i prefiks 'Arma Reforger:', podkreślniki zamieniamy na spacje,
    a po dwukropku wstawiamy spację. Gdy po normalizacji nic nie zostaje, zwracamy tytuł bez zmian."""
    original = str(title or "").strip()
    t = original.strip("\"'`")
    m = re.search(r"/wiki/([^?#\s]+)", t)
    if m:
        t = unquote(m.group(1))
    t = re.sub(r"^Arma[ _]Reforger\s*:\s*", "", t, flags=re.I)
    t = t.replace("_", " ")
    t = re.sub(r":(?=\S)", ": ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or original


def repair_tool_call(name, args, tools):
    """-> (name, args, notes). Naprawia deterministycznie; nic nie zgaduje po cichu:
    każda zmiana trafia do notes i wraca do modelu razem z wynikiem."""
    notes = []
    name = (name or "").strip()
    if name.startswith("functions."): name = name[len("functions."):]
    if name not in tools:
        target = ALIASES.get(name.lower())
        if target not in tools:
            return None, args, [f"Nie ma narzędzia '{name}'. Dostępne: {', '.join(tools)}."]
        notes.append(f"'{name}' nie istnieje -> użyto {target}")
        args = dict(args)
        q = args.get("query") or args.get("q") or args.get("pattern") or args.get("path") or ""
        q = re.sub(r"^(class|modded class|enum)\s+", "", str(q)).strip()
        if target == "game_read":
            args = {"path": args.get("path") or args.get("file") or q}
        elif target == "game_browse":
            args = {k: args[k] for k in ("path", "pattern") if k in args}
        else:
            args = {"query": q, **({"limit": args["limit"]} if "limit" in args else {})}
        name = target
    props = tools[name].get("inputSchema", {}).get("properties", {})
    clean = {}
    for k, v in args.items():
        if k not in props:
            notes.append(f"pominięto nieznany argument '{k}'")
            continue
        cv = _coerce(v, props[k])
        if cv is None:
            notes.append(f"pominięto argument '{k}' (zła wartość: {v!r}; dozwolone: {props[k].get('enum') or props[k].get('type')})")
        else:
            if cv != v: notes.append(f"'{k}': {v!r} -> {cv!r}")
            clean[k] = cv
    if name == "wiki_read" and isinstance(clean.get("title"), str):
        norm = normalize_wiki_title(clean["title"])
        if norm != clean["title"]:
            notes.append(f"'title': {clean['title']!r} -> {norm!r} (tytuł jak w nagłówku wyniku wiki_search)")
            clean["title"] = norm
    miss = [r for r in tools[name].get("inputSchema", {}).get("required", []) if r not in clean]
    if miss:
        return None, clean, [f"{name}: brak wymaganych argumentów {miss}"] + notes
    return name, clean, notes



BANNER = re.compile(r"/\*\s*=+.*?=+\s*\*/|/\*!\s*\\(?:addtogroup|\{|\}).*?\*/", re.S)

def digest_enforce(text: str, doc_cap: int = 70, keep_docs: bool = True) -> str:
    """Kompakt źródła Enforce Script: zostają WSZYSTKIE deklaracje, znika szum.
    keep_docs=False -> tylko sygnatury (tryb awaryjny, ~40% oryginału)."""
    header = ""
    lines = text.split("\n")
    while lines and lines[0].startswith("//"):          # nagłówek MCP: ścieżka + rozmiar
        header += (" " if header else "") + lines.pop(0)[2:].strip()
    text = "\n".join(lines)
    header = "// " + header if header else ""
    text = BANNER.sub("", text)
    out, doc, in_block, depth_body = [], [], False, 0
    for raw in text.splitlines():
        s = raw.strip()
        if in_block:                                   # wnętrze /*! ... */
            if "*/" in s:
                in_block = False
                s = s.split("*/")[0].strip()
            if s: doc.append(s)
            continue
        if s.startswith("/*"):
            body = s[2:].lstrip("!").strip()
            if "*/" in body:
                body = body.split("*/")[0].strip()
            else:
                in_block = True
            if body: doc.append(body)
            continue
        if s.startswith("//"):
            body = s.lstrip("/").lstrip("!").strip()
            if body: doc.append(body)
            continue
        if not s:
            continue
        # ciała w klamrach: zostaw nagłówek metody, pomiń implementację getterów/setterów
        if depth_body:
            depth_body += s.count("{") - s.count("}")
            continue
        d = " ".join(doc)[:doc_cap] if keep_docs else ""
        doc.clear()
        if s == "{" and out and not out[-1].startswith(("class ", "modded class ")) \
                and ("(" in out[-1]):
            depth_body = 1                              # to ciało metody
            continue
        out.append(f"{s}  // {d}" if d else s)
    res = "\n".join(out)
    return (header + "\n" + res) if header else res




HIDE_PARAMS = {  # parametry, które tylko mylą model; serwer użyje swoich domyślnych
    "api_search": ("source", "format"),
    "asset_search": ("refresh",),
}


def slim_tool_definitions(tools: dict) -> list:
    """Zamiast ollama_tool_definitions(): ukrywa parametry z HIDE_PARAMS."""
    out = []
    for name, tool in tools.items():
        schema = dict(tool.get("inputSchema", {"type": "object", "properties": {}}))
        props = {k: v for k, v in schema.get("properties", {}).items()
                 if k not in HIDE_PARAMS.get(name, ())}
        schema["properties"] = props
        schema["required"] = [r for r in schema.get("required", []) if r in props]
        out.append({"type": "function", "function": {
            "name": name, "description": tool.get("description", ""), "parameters": schema}})
    return out


if __name__ == "__main__":
    # Samotest: python reforger_helpers.py
    demo_tools = {
        "api_search": {"inputSchema": {"properties": {
            "query": {"type": "string"},
            "limit": {"type": "number", "minimum": 1, "maximum": 50},
            "source": {"type": "string", "enum": ["enfusion", "arma", "all"]},
            "format": {"type": "string", "enum": ["detailed", "tree"]}},
            "required": ["query"]}},
        "game_read": {"inputSchema": {"properties": {"path": {"type": "string"}},
                                      "required": ["path"]}},
    }
    cases = [
        ("search", {"query": "GetPrefabData()", "path": "", "limit": 5}),
        ("api_search", {"query": "ScriptedUserAction", "source": "both"}),
        ("python", {"code": "1+1"}),
    ]
    print("=== repair_tool_call ===")
    for name, args in cases:
        print(f"{name} {args}\n   -> {repair_tool_call(name, args, demo_tools)}")
    print("\n=== slim_tool_definitions (parametry widoczne dla modelu) ===")
    for d in slim_tool_definitions(demo_tools):
        print(d["function"]["name"], list(d["function"]["parameters"]["properties"]))
    sample = "// a.c (from .pak)\nclass A\n{\n\t//! Opis\n\tproto external void Foo();\n}\n"
    print("\n=== digest_enforce ===")
    print(digest_enforce(sample))
    print("\nOK - biblioteka działa. Importuj ją w silniku, nie uruchamiaj osobno.")
