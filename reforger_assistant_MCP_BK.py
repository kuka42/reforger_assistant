#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reforger Assistant MCP BK — Ollama + Enfusion MCP: pętla rozmowy (silnik).

Wyłącznie rozmawia z lokalnym serwerem Enfusion MCP BK, który korzysta z instalacji gry.
Narzędzia zapisu / uruchamiania Workbencha są celowo niedostępne dla modelu.

Układ plików (od 1.7.0):
  reforger_config.py   konfiguracja (wersja, ścieżki, limity, tryby; zmienne środowiskowe)
  reforger_prompts.py  teksty dla modelu i użytkownika (prompt systemowy, podpowiedzi, stopki)
  reforger_rules.py    reguły jako dane (narzędzia tylko do odczytu, wzorce, listy nazw)
  reforger_checks.py   kontrole odpowiedzi (weryfikator cytatów, kontrola nazw API, pamięć sesji)
  reforger_mcp.py      klient Enfusion MCP (stdio)
  reforger_helpers.py  naprawa wywołań narzędzi, skracanie kodu, tytuły wiki
  ten plik             pętla rozmowy: wywołania narzędzi, kontekst, ponowienia, synteza

Wymagania: Python 3.10+, Node.js, Ollama, zbudowany Enfusion MCP BK.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request

from reforger_i18n import EN, tr

try:
    from reforger_helpers import repair_tool_call, slim_tool_definitions, digest_enforce
except ImportError as _exc:  # jasny komunikat zamiast tracebacku
    raise SystemExit(tr("Brak pliku reforger_helpers.py obok tego pliku: ",
                        "File reforger_helpers.py is missing next to this file: ") + str(_exc))

# Moduły projektu (od 1.7.0). Nazwy są importowane jawnie do przestrzeni silnika, więc wszystko,
# co było dostępne jako reforger_assistant_MCP_BK.X (serwer WEB, testy), działa bez zmian.
try:
    from reforger_config import (  # noqa: F401
        KB_CHECK_MODE,
        VERSION,
        MCP_SCRIPT,
        GAME_PATH,
        DOCS_PATH,
        PATH_SOURCES,
        _env_int,
        _env_float,
        OLLAMA_URL,
        MODEL,
        NUM_CTX,
        OLLAMA_NUM_PREDICT,
        MAX_TOOL_CALLS,
        MAX_HISTORY_MESSAGES,
        MAX_TOOL_RESULT_CHARS,
        MAX_TOOL_CONTEXT_CHARS,
        FINISHED_SOURCE_CHARS,
        FINISHED_EVIDENCE_CHARS,
        COMPACT_SEARCH_RESULT_CHARS,
        SOFT_LIMIT_CLASS_SEARCH,
        SOFT_LIMIT_OTHER_SEARCH,
        COMPACT_OLD_RESULT_CHARS,
        MCP_TIMEOUT,
        OLLAMA_TIMEOUT,
        OLLAMA_TEMPERATURE,
        OLLAMA_THINK,
        OLLAMA_STREAM,
        THINK_ABORT_TOKENS,
        THINKING_KEEP_CHARS,
        VIEW_LIMIT_PER_FILE,
        VERIFY_MODE,
        API_CHECK_MODE,
        EMERGENCY_IN_HISTORY,
        config_summary,
    )
    from reforger_prompts import (  # noqa: F401
        NOTE_GLOBAL_FUNCTION,
        NOTE_GLOBAL_OWNERS,
        QUESTION_FILES_NOTE,
        NOTE_PARENTS,
        TOOL_BROWSE_PATTERN,
        TOOL_CONTENT_SEARCH,
        HINT_QUOTE_FIX,
        TOOL_ASSET_CODE_QUERY,
        API_EXACT_CLASS_NOTE,
        HINT_FINAL_NO_TOOLS,
        FOOTER_STOPPED,
        EMERGENCY_CODE_HEADER,
        API_QUERY_REWRITTEN,
        API_CLASS_SEEN,
        API_CLASS_NOT_SEEN,
        HINT_KB_CHECK,
        HINT_COMPILE_LINES,
        COMPILE_LINE_FOUND,
        COMPILE_LINE_FINDINGS,
        COMPILE_LINE_MISSING,
        COMPILE_KB,
        COMPILE_PROJECT,
        HINT_SYNTAX_FIX,
        FOOTER_SYNTAX,
        NOTE_SUBCLASSES,
        NOTE_SEARCH_MISS_FILE,
        NOTE_GLOBAL_DECL,
        NOTE_ENUM_DECL,
        HINT_COMPILE_FULL_CODE,
        HINT_BUDGET,
        DOC_HIERARCHY_SOURCE,
        TOOL_ACTION_BLOCKED,
        SYSTEM_PROMPT,
        EMERGENCY_PLACEHOLDER,
        WIKI_TITLE_HINT,
        HINT_EMPTY_NO_TOOLS,
        HINT_RETRY_AFTER_EMPTY,
        HINT_INCOMPLETE_RETRY,
        HINT_API_FIX,
        HINT_STALL,
        HINT_COMPILE_ERROR,
        HINT_COMPILE_ERROR_LOOKUP,
        TOOL_DUP_IN_CONTEXT,
        TOOL_DUP_BLOCKED,
        TOOL_VIEW_LIMIT,
        TOOL_MCP_LIMIT,
        TOOL_FILE_SHORTENED,
        MSG_EMPTY_TWICE,
        NOTE_INCOMPLETE,
        SYNTH_NO_EVIDENCE,
        SYNTH_INSTRUCTIONS,
        SYNTH_SYSTEM_SUFFIX,
        SYNTH_SECOND_ATTEMPT,
        SYNTH_FOOTER,
        SYNTH_FAILED,
        FOOTER_VERIFY,
        FOOTER_VERIFY_MORE,
        FOOTER_API,
    )
    from reforger_rules import (  # noqa: F401
        API_GLOBAL_FUNCTIONS,
        GAME_BROWSE_PATTERN_RE,
        CONTENT_SEARCH_ALIASES,
        STALL_STOP_ROUNDS,
        GLOBAL_FUNCTION_FILES,
        STALL_STOP_ROUNDS_HARD,
        STALL_STOP_MIN_CALLS,
        QUESTION_FILES_MAX,
        QUESTION_NAME_RE,
        VERIFY_NO_FIX_MARKERS,
        GAME_BROWSE_ANY_PATTERNS,
        ASSET_QUERY_CODE_RE,
        API_EXACT_CLASS_RE,
        SYNTH_BUDGET_CHARS,
        SYNTH_ITEM_MAX_CHARS,
        PARENT_RESOLVE_DEPTH,
        PARENT_RESOLVE_PER_TURN,
        PARENT_NOTE_MAX_NAMES,
        PARENT_NOTE_CAP,
        _CLASS_DECL_RE,
        _CLASS_ROOT_RE,
        API_QUERY_BUILTIN_TYPES,
        API_CLASS_METHOD_QUERY_RE,
        API_QUERY_KEYWORDS,
        COMPILE_LOOKUP_MAX,
        COMPILE_LINES_MAX,
        EMERGENCY_CODE_CAP,
        KB_CHECK_MAX_FILES,
        TOOL_ACTION_LIMITS,
        TOOL_DROP_ARGS,
        WB_KNOWLEDGE_MAX_FILES,
        KB_PITFALLS_QUERY,
        READ_ONLY_TOOLS,
        KEEP_PREFAB_BLOCKS,
        VIEW_QUERY_KEYS,
        VIEW_START_KEYS,
        VIEW_END_KEYS,
        GAME_READ_ALIASES,
        VIEW_MAX_LINES,
        _CODE_BLOCK_RE,
        _PATH_RE,
        _OWN_CODE_RE,
        _EXAMPLE_RE,
        _GAME_QUOTE_RE,
        _EXAMPLE_PATH_RE,
        _GAME_LABEL_RE,
        _ENTRY_GUID_RE,
        _SCRIPT_LIKE_RE,
        _PREFAB_LIKE_RE,
        _SEPARATOR_RE,
        _COMPILE_ERR_RE,
        _API_GAME_CLASSES,
        _API_GLOBAL_OK,
        _API_METHOD_OK,
        _API_CLASS_OK,
        _API_KEYWORDS,
        _NON_CODE_LANGS,
        _API_CODE_BLOCK_RE,
    )
    from reforger_checks import (  # noqa: F401
        _fenced_code_blocks,
        _own_code_blocks,
        _kb_query_from_code,
        _kb_excerpt,
        _compile_line_errors,
        _syntax_problems,
        _syntax_findings,
        _code_line_excerpt,
        _kb_sections,
        _SESSION_FILES,
        _SESSION_FILES_MAX,
        _SESSION_FILE_CAP,
        _path_key,
        _session_files,
        _norm_code,
        _display_name,
        _find_evidence,
        _verify_answer,
        _log_verification,
        _verification_footer,
        _is_wiki_miss,
        _SESSION_META,
        _EVIDENCE_CAP_CHARS,
        _session_meta,
        _add_evidence,
        _strip_code_noise,
        _api_calls,
        _evidence_texts,
        _find_class_method,
        _api_problems,
        _api_footer,
        _game_classes,
        _decl_items,
        _record_view_lines,
        _line_ref_stats,
        _line_ref_problems,
        _quote_problems,
        _decl_target,
        _class_known,
        _strip_leaked_reasoning,
        _collapse_repeats,
        _annotate_answer,
        _sync_entry_classes,
        _enum_refs,
        _enum_values,
        _word_seen,
        _NOT_FOUND_LINE_RE,
    )
    from reforger_mcp import (  # noqa: F401
        MCPError,
        MCPStdioClient,
        ollama_tool_definitions,
        tool_schema_hint,
        _raw_text,
    )
except ImportError as _exc:
    raise SystemExit(tr("Brak pliku modułu asystenta obok reforger_assistant_MCP_BK.py: ",
                        "An assistant module file is missing next to reforger_assistant_MCP_BK.py: ") + str(_exc))


print(config_summary(), flush=True)
_SRC = ({"env": "variable", "settings": "interface", "default": "default", "auto": "next to game"} if EN else
        {"env": "zmienna", "settings": "interfejs", "default": "domyślna", "auto": "obok gry"})
print(tr("[ŚCIEŻKI] BK: ", "[PATHS] BK: ") + f"{MCP_SCRIPT} ({_SRC.get(PATH_SOURCES['mcp_script'])}); "
      + tr("gra: ", "game: ") + f"{GAME_PATH} "
      f"({_SRC.get(PATH_SOURCES['game_path'])}); docs: {DOCS_PATH} ({_SRC.get(PATH_SOURCES['docs_path'])})", flush=True)

# Od 1.8.8: hierarchia klas z lokalnej dokumentacji API Workbencha (Arma Reforger Tools). Tylko odczyt z dysku.
try:
    from reforger_docs import DocHierarchy, docs_dir
    DOCS = DocHierarchy().load(docs_dir(GAME_PATH, DOCS_PATH))
except Exception as _exc:  # dokumentacja jest opcjonalna; jej brak nigdy nie blokuje startu
    DOCS = None
    print(tr("[DOKUMENTACJA] hierarchia klas pominięta z powodu błędu: ",
             "[DOCS] class hierarchy skipped because of an error: ") + repr(_exc), flush=True)
else:
    if DOCS:
        import reforger_checks as _checks
        _checks.GAME_CLASS_LOOKUP = DOCS.knows        # od 2.0.2: klasy gry z dokumentacji (kontrola prefiksu SCR_)
        print(tr("[DOKUMENTACJA] hierarchia klas z dokumentacji Workbench: ",
                 "[DOCS] class hierarchy from the Workbench documentation: ") + "; ".join(DOCS.sources), flush=True)
    else:
        print(tr(f"[DOKUMENTACJA] brak plików hierarchy.html ({docs_dir(GAME_PATH, DOCS_PATH)}); "
                 "klasy bazowe tylko z plików gry. Folder docs ustawisz w interfejsie (przycisk „ścieżki”) albo zmienną REFORGER_DOCS_PATH.",
                 f"[DOCS] no hierarchy.html files ({docs_dir(GAME_PATH, DOCS_PATH)}); "
                 "base classes only from game files. Set the docs folder in the interface (the 'ścieżki' button) or with REFORGER_DOCS_PATH."),
              flush=True)


def _trim_thinking(assistant: dict) -> None:
    """Rozumowanie z poprzednich rund tej samej tury zostaje w kontekście (ciągłość przy wywołaniach narzędzi),
    ale jedna pętla rozumowania na kilkanaście tysięcy tokenów potrafiła podwoić kontekst kolejnych wywołań
    (12 tys. -> 27 tys.) i skończyć się reason=length. Zostawiamy tylko końcówkę."""
    thinking = assistant.get("thinking")
    if not isinstance(thinking, str) or THINKING_KEEP_CHARS < 0 or len(thinking) <= THINKING_KEEP_CHARS:
        return
    if THINKING_KEEP_CHARS == 0:
        assistant.pop("thinking", None)
    else:
        assistant["thinking"] = "[...] " + thinking[-THINKING_KEEP_CHARS:]


def compact_finished_history(messages: list[dict]) -> None:
    """Po zamknięciu tury: dowody MCP zostają w RAM, stare rozumowanie nie.

    Służy WYŁĄCZNIE historii w pamięci procesu. WEB zapisuje tylko user/assistant
    i metadane wywołań, nigdy surowe odpowiedzi MCP.
    """
    # Od 1.8.3: odrzucone szkice i podpowiedzi rund poprawkowych są potrzebne tylko w obrębie tury.
    messages[:] = [m for m in messages if not m.get("_draft")]
    for item in messages:
        if item.get("role") == "assistant":
            # thinking należy zachować podczas wykonywania sekwencji tool calls;
            # po ukończeniu tury nie musi zajmować kontekstu kolejnych pytań.
            item.pop("thinking", None)
    # Po zakończonej turze wyniki wyszukiwań są prawie bezwartościowe, a odczyty plików
    # zostają w skrócie: kolejna tura startuje z małym kontekstem (zostaje miejsce na rozumowanie).
    for item in messages:
        if item.get("role") != "tool":
            continue
        text = item.get("content", "")
        if not isinstance(text, str):
            continue
        if _is_source_result(text, item.get("tool_name", "")):
            item["content"] = _shrink(text, FINISHED_SOURCE_CHARS)
        elif len(text) > 300:
            item["content"] = text[:200] + tr("\n[... wynik wyszukiwania skrócony po zakończeniu tury ...]",
                                              "\n[... search result shortened after the turn ended ...]")
    _compact_tool_context(messages, limit=FINISHED_EVIDENCE_CHARS)
    prune_history(messages)


def _excerpt(value: str, size: int) -> str:
    """Jawnie oznaczony fragment wyniku; nie udaje pelnego pliku."""
    if len(value) <= size:
        return value
    marker = tr("\n[... ŚRODKOWA CZĘŚĆ WYNIKU POMINIĘTA Z POWODU LIMITU KONTEKSTU ...]\n",
                "\n[... MIDDLE PART OF THE RESULT OMITTED BECAUSE OF THE CONTEXT LIMIT ...]\n")
    available = max(100, size - len(marker))
    head = max(50, int(available * 0.75))
    return value[:head] + marker + value[-(available - head):]


# Od 2.0.0: znaczniki skrótu w obu językach (historia rozmowy mogła powstać w drugim języku).
SHORT_NOTE = tr("[SKRÓT", "[SHORTENED")
SHORT_API_NOTE = tr("[SKRÓT WYNIKU API", "[SHORTENED API RESULT")
SHORT_PREFAB_NOTE = tr("[SKRÓT PREFABU", "[SHORTENED PREFAB")
_SHORT_PREFIXES = ("[SKRÓT", "[SHORTENED")
NO_MATCHES_FOR = tr("Brak dopasowań dla", "No matches for")
MCP_TOOL_ERROR = tr("BŁĄD NARZĘDZIA MCP:", "MCP TOOL ERROR:")
ERROR_PREFIX = tr("BŁĄD", "ERROR")
BUDGET_HINT_AT = 15                      # od 2.0.3: po tylu wywołaniach MCP jednorazowe przypomnienie o limicie
NEED_CODE_MARK = "\x00need_code"          # od 2.0.3: wewnętrzny znacznik "brak kodu po błędzie kompilacji"
CALL_FIX_NOTE = tr("\n[korekta wywołania: ", "\n[call correction: ")


def _strip_note(text: str) -> str:
    """Skrócony wynik zaczyna się linią '[SKRÓT...]'; kolejne skracanie i klasyfikacja
    muszą ją pomijać, inaczej wynik przestaje wyglądać jak plik i traci strukturę."""
    if text.startswith(_SHORT_PREFIXES):
        return text.split("\n", 1)[1] if "\n" in text else ""
    return text


def _looks_like_enforce(text: str) -> bool:
    """Wynik game_read dla pliku .c ma nagłówek '// sciezka.c (from .pak)'."""
    first = _strip_note(text).split("\n", 1)[0]
    return first.startswith("//") and ".c " in first + " "


def _looks_like_prefab(text: str) -> bool:
    """Wynik game_read dla prefabu ma nagłówek '// Prefabs/....et (from .pak)'."""
    first = _strip_note(text).split("\n", 1)[0]
    return first.startswith("//") and ".et " in first + " "


def _digest_prefab(text: str) -> str:
    """Prefab: komponenty z KEEP_PREFAB_BLOCKS zostają w całości, pozostałe
    zwijają się do nagłówka (struktura pliku jest zachowana)."""
    lines = text.split("\n")
    out, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        # komponent najwyższego poziomu: dokładnie 2 spacje wcięcia i '{' na końcu
        if line.startswith("  ") and not line.startswith("   ") and line.rstrip().endswith("{"):
            j = i + 1
            while j < n and lines[j].rstrip() != "  }":
                j += 1
            block = lines[i:j + 1]
            name = line.strip().split(" ", 1)[0]
            if name in KEEP_PREFAB_BLOCKS or len(block) <= 3:
                out.extend(block)
            else:
                out.append(line)
                out.append(tr(f"   [... {len(block) - 2} linii komponentu pominięto ...]",
                              f"   [... {len(block) - 2} component lines omitted ...]"))
                out.append("  }")
            i = j + 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _looks_like_api(text: str) -> bool:
    body = _strip_note(text)
    return bool(re.search(r"^##\s+[A-Za-z_]\w*\s*$", body, re.M) and re.search(r"^###\s", body, re.M))


def _shrink_api(text: str, size: int) -> str:
    """Wynik api_search (od 1.8.3): najpierw znikają opisy metod (' -- ...'), potem metody dziedziczone
    zwijają się do nazw; sygnatury własnych metod klasy zostają. Na końcu dopiero jawny wyciąg."""
    body = _strip_note(text)
    first, rest = (body.split("\n", 1) + [""])[:2] if body.startswith("[") else ("", body)
    steps = []
    rest = re.sub(r"^(\s*-\s[^\n]*?) -- [^\n]*$", r"\1", rest, flags=re.M)
    steps.append(tr("usunięto opisy metod", "method descriptions removed"))
    if len(first) + len(rest) > size:
        out, group = [], None
        for line in rest.split("\n"):
            m = re.match(r"^####\s+(\S.*)$", line)
            if m and not m.group(1).startswith("Inherited"):
                group = [m.group(1).strip(), []]
                out.append(group)
                continue
            if group is not None:
                n = re.match(r"^\s*-\s[^\n(]*?\b([A-Za-z_]\w*)\s*\(", line)
                if n:
                    group[1].append(n.group(1))
                    continue
                if line.strip() and not line.startswith("  ..."):
                    group = None
                else:
                    continue
            out.append(line)
        rest = "\n".join(f"#### {g[0]}: " + ", ".join(g[1]) if isinstance(g, list) else g for g in out)
        steps.append(tr("metody dziedziczone zwinięte do nazw", "inherited methods collapsed to names"))
    if len(first) + len(rest) > size:
        rest = re.sub(r"^(\s*-\s)(?:proto\s+)?(?:external\s+|native\s+)", r"\1", rest, flags=re.M)
        steps.append(tr("bez słów 'proto external'", "without the words 'proto external'"))
    note = SHORT_API_NOTE + ": " + ", ".join(steps) + "]\n"
    result = (first + "\n" if first else "") + rest
    return note + (result if len(result) + len(note) <= size else _excerpt(result, max(500, size - len(note))))


def _shrink(text: str, size: int) -> str:
    """Skraca wynik do ~size znaków. Kod .c: zostają WSZYSTKIE deklaracje.
    Reszta: jawnie oznaczony wyciąg (_excerpt)."""
    if len(text) <= size:
        return text
    body = _strip_note(text)
    if _looks_like_prefab(text):
        candidate = _digest_prefab(body)
        note = SHORT_PREFAB_NOTE + tr(": komponenty poza ActionsManagerComponent zwinięte do nagłówków]\n",
                                      ": components other than ActionsManagerComponent collapsed to headers]\n")
        if len(candidate) < len(body) or text.startswith(("[SKRÓT PREFABU", "[SHORTENED PREFAB")):
            # Digest zachowuje blok ActionsManagerComponent w całości; tniemy go dopiero
            # przy naprawdę ogromnym bloku (powyżej max(size, 4200) znaków).
            cap = max(size, 4200)
            return note + (candidate if len(candidate) <= cap else _excerpt(candidate, cap))
    if _looks_like_enforce(text):
        note = SHORT_NOTE + tr(": zachowano wszystkie deklaracje, pominięto ciała metod i część komentarzy]\n",
                               ": all declarations kept, method bodies and some comments omitted]\n")
        for keep_docs in (True, False):
            candidate = digest_enforce(body, keep_docs=keep_docs)
            if len(candidate) <= size:
                return note + candidate
        return note + _excerpt(digest_enforce(body, keep_docs=False), size)
    if _looks_like_api(text) and not text.startswith(("[SKRÓT WYNIKU API", "[SHORTENED API RESULT")):
        return _shrink_api(text, size)
    return _excerpt(text, size)


def _dedupe_api_result(text: str) -> str:
    """api_search: usuń z 'Inherited Members' linie już widoczne wyżej oraz listę
    'Related Classes in Group'. Nic innego nie jest ruszane."""
    out, seen, pending, mode = [], set(), [], None
    for line in text.split("\n"):
        s = line.strip()
        if s == "---":
            seen, pending, mode = set(), [], None
            out.append(line)
            continue
        if mode == "related":
            if s.startswith("Docs:"):
                mode = None
                out.append(line)
            continue
        if s.startswith("### "):
            pending = []
            if s.startswith("### Inherited Members"):
                mode = "inherited"
                pending.append(line)
                continue
            if s.startswith("### Related Classes"):
                mode = "related"
                continue
            mode = None
        elif mode == "inherited":
            if s.startswith("- "):
                key = s.split(" -- ")[0]
                if key in seen:
                    continue
                seen.add(key)
                out.extend(pending)
                pending = []
                out.append(line)
            else:
                pending.append(line)      # nagłówki "From:" / "#### Klasa"
            continue
        if s.startswith("- "):
            seen.add(s.split(" -- ")[0])
        out.append(line)
    return "\n".join(out)


def _ledger(read_paths: list[str], searches: list[str], misses: list[str] | None = None) -> str:
    """Krótki rejestr tego, co już zrobiono w tej turze (pokazywany modelowi przy powtórkach)."""
    parts = []
    if read_paths:
        parts.append(tr("Przeczytane pliki: ", "Files read: ") + "; ".join(read_paths[-12:]) + ".")
    if searches:
        parts.append(tr("Wykonane wyszukiwania: ", "Searches done: ") + "; ".join(searches[-12:]) + ".")
    if misses:
        parts.append(tr("Szukano BEZ trafienia: ", "Searched WITHOUT a match: ") + "; ".join(misses[-10:]) + ".")
    return " ".join(parts)[:1100]


def _extract_view_spec(arguments: dict):
    """Wycina z argumentów game_read parametry lokalnego widoku (game_read w BK ma tylko 'path')."""
    args = dict(arguments)
    view: dict = {}
    for key in VIEW_QUERY_KEYS:
        if key in args:
            value = args.pop(key)
            if isinstance(value, str) and value.strip() and "query" not in view:
                view["query"] = value.strip()
    for key, target in [(k, "start") for k in VIEW_START_KEYS] + [(k, "end") for k in VIEW_END_KEYS]:
        if key in args:
            value = args.pop(key)
            try:
                if target not in view and value not in (None, ""):
                    view[target] = int(value)
            except (TypeError, ValueError):
                pass
    return args, (view or None)


def _view_label(view: dict) -> str:
    if "query" in view:
        return f"query={view['query']!r}"
    return tr("linie ", "lines ") + f"{view.get('start', 1)}-{view.get('end', '...')}"


def _body_lines(raw: str):
    """Linie pliku BEZ trzylinijkowego nagłówka dopisywanego przez game_read (ścieżka, rozmiar, pusta linia).
    Dzięki temu numery w widoku odpowiadają numerom w pliku."""
    lines = raw.split("\n")
    # Nagłówek BK: "// ścieżka (from .pak)" albo "// ścieżka" (plik luzem, od 1.8.4), potem "// N bytes" i pusta linia.
    if (len(lines) >= 3 and lines[0].startswith("//") and re.match(r"^//\s*\d+\s+bytes\s*$", lines[1])
            and lines[2].strip() == ""):
        return lines[3:], 3
    return lines, 0


def _render_view(raw: str, view: dict):
    """Widok liczony lokalnie na PEŁNYM tekście pliku z game_read (nie na skróconym).
    Zwraca (tekst, znaleziono). znaleziono=False oznacza brak dopasowań (brak nowej informacji)."""
    lines, _offset = _body_lines(raw)
    total = len(lines)
    head = tr(f"[Widok lokalny pliku: {total} linii, {len(raw)} znaków. Numeracja = linie pliku "
              "(bez nagłówka dopisywanego przez game_read).]",
              f"[Local file view: {total} lines, {len(raw)} characters. Numbering = file lines "
              "(without the header added by game_read).]")
    if "query" in view:
        q = view["query"]
        try:
            pattern = re.compile(q, re.I)
        except re.error:
            pattern = None
        hits = [i for i, line in enumerate(lines)
                if q.lower() in line.lower() or (pattern and pattern.search(line))]
        if not hits:
            return head + "\n" + tr(
                f"{NO_MATCHES_FOR} '{q}' w CAŁYM pliku (przeszukano wszystkie {total} linii). "
                "Tego tekstu w tym pliku NIE ma. Nie zgaduj kolejnych nazw: zmień strategię "
                "(api_search z type=method, wiki_search) albo napisz, że nie znaleziono.",
                f"{NO_MATCHES_FOR} '{q}' in the WHOLE file (all {total} lines searched). "
                "This text is NOT in this file. Do not guess further names: change strategy "
                "(api_search with type=method, wiki_search) or say that it was not found."), False
        ranges: list[list[int]] = []
        for i in hits:
            lo, hi = max(0, i - 2), min(total - 1, i + 2)
            if ranges and lo <= ranges[-1][1] + 1:
                ranges[-1][1] = max(ranges[-1][1], hi)
            else:
                ranges.append([lo, hi])
        out, used = [], 0
        for lo, hi in ranges:
            if used >= VIEW_MAX_LINES:
                out.append(tr("... (kolejne dopasowania pominięte; zawęź query)", "... (further matches omitted; narrow the query)"))
                break
            take = min(hi - lo + 1, VIEW_MAX_LINES - used)
            out.append("\n".join(f"{n + 1}| {lines[n]}" for n in range(lo, lo + take)))
            used += take
            if lo + take <= hi:
                out.append(tr("... (przycięto)", "... (cut)"))
        return head + tr(f"\nDopasowań dla '{q}': {len(hits)} linii.\n",
                         f"\nMatches for '{q}': {len(hits)} lines.\n") + "\n...\n".join(out), True
    start = max(1, view.get("start", 1))
    end = min(total, view.get("end", start + 199))
    if end < start:
        end = start
    if end - start + 1 > VIEW_MAX_LINES + 90:
        end = start + VIEW_MAX_LINES + 89
    end = min(end, total)
    if start > total:
        return head + tr(f"\nPlik ma tylko {total} linii; zakres zaczyna się za końcem.",
                         f"\nThe file has only {total} lines; the range starts past the end."), False
    body = "\n".join(f"{n}| {lines[n - 1]}" for n in range(start, end + 1))
    more = tr(f"\n... (plik ma jeszcze {total - end} linii)", f"\n... (the file has {total - end} more lines)") if end < total else ""
    return head + tr(f"\nLinie {start}-{end}:\n", f"\nLines {start}-{end}:\n") + body + more, True


def _with_local_view_params(defs: list[dict]) -> list[dict]:
    """Oficjalnie wystawia modelowi lokalne parametry widoku (BK ich nie zna; usuwamy je przed wywołaniem MCP)."""
    for d in defs:
        f = d.get("function", {})
        if f.get("name") == "game_read":
            props = f.setdefault("parameters", {"type": "object", "properties": {}}).setdefault("properties", {})
            props["query"] = {"type": "string", "description":
                "Optional. Text to search for inside the WHOLE file; returns only matching lines with "
                "context, or states that the text is not in the file."}
            props["line_start"] = {"type": "integer", "description":
                "Optional. First line to show (1-based, numbering of the text returned by game_read)."}
            props["line_end"] = {"type": "integer", "description": "Optional. Last line to show."}
            f["description"] = (f.get("description") or "") + (
                " Optional local parameters: query (search inside the whole file) and line_start/line_end.")
    return defs


def _emergency_history_entry(content: str) -> dict:
    """Wpis do historii modelu dla odpowiedzi awaryjnej (patrz REFORGER_EMERGENCY_IN_HISTORY)."""
    if EMERGENCY_IN_HISTORY == "keep":
        return {"role": "assistant", "content": content}
    # Proza z niezweryfikowanymi twierdzeniami znika, ale kod zostaje: użytkownik mógł go skompilować
    # i za chwilę zgłosić błędy (mapowanie linii z komunikatu kompilatora szuka właśnie tego kodu).
    code = _fenced_code_blocks(content, EMERGENCY_CODE_CAP)
    return {"role": "assistant", "content": EMERGENCY_PLACEHOLDER + (EMERGENCY_CODE_HEADER + code if code else "")}


def _compile_error_lookup(question: str, meta: dict, mcp, messages: list | None = None) -> dict | None:
    """Błąd kompilatora w pytaniu: zapamiętaj odrzucone nazwy i sprawdź je od razu w api_search.
    Zwraca jednorazową podpowiedź dla modelu albo None."""
    found = [s for s in dict.fromkeys(_COMPILE_ERR_RE.findall(question or "")) if s not in meta["banned"]]
    line_hint = _compile_line_hint(question, meta, mcp, messages)
    if not found:
        return {"role": "user", "content": line_hint} if line_hint else None
    parts = []
    checked: set[str] = set()
    for sym in found:
        meta["banned"].add(sym)
        meth = sym.replace("::", ".").split(".")[-1]
        if meth in checked or len(checked) >= COMPILE_LOOKUP_MAX or "api_search" not in getattr(mcp, "tools", {}):
            continue
        checked.add(meth)
        args = {"query": meth, "type": "method", "limit": 10}
        try:
            result = mcp.call_tool("api_search", args)
            raw = _raw_text(result)
            _add_evidence(meta, raw)
            parts.append(f"api_search('{meth}'):\n" + tool_text(result, "api_search", args)[:3000])
            print(tr(f"  [API] błąd kompilatora: {sym} - automatyczne api_search('{meth}')",
                     f"  [API] compiler error: {sym} - automatic api_search('{meth}')"), flush=True)
        except (MCPError, OSError, ValueError, TypeError) as exc:
            print(tr(f"  [API] automatyczne sprawdzenie {sym} nieudane: {exc!r}",
                     f"  [API] automatic check of {sym} failed: {exc!r}"), flush=True)
    lookup = HINT_COMPILE_ERROR_LOOKUP.format(results="\n\n".join(parts)) if parts else ""
    content = HINT_COMPILE_ERROR.format(symbols=", ".join(found), lookup=lookup)
    return {"role": "user", "content": content + ("\n\n" + line_hint if line_hint else "")}


def _compile_line_hint(question: str, meta: dict, mcp, messages: list | None) -> str:
    """Błędy kompilatora z plikiem i numerem linii: wskazana linia z ostatniego kodu asystenta,
    wykryta w niej niedozwolona składnia i sekcje o pułapkach z bazy wiedzy BK."""
    errors = _compile_line_errors(question)
    if not errors:
        return ""
    blocks = []
    for path, line, message in errors[:COMPILE_LINES_MAX]:
        hit = _code_line_excerpt(messages or [], path, line)
        print(tr(f"  [KOD] błąd kompilatora: {path}({line}) - ", f"  [CODE] compiler error: {path}({line}) - ")
              + (tr("linia znaleziona w ostatnim kodzie", "line found in the last code") if hit
                 else tr("linii nie ma w ostatnim kodzie", "line not in the last code")), flush=True)
        if hit:
            excerpt, target = hit
            found = _syntax_findings(target)
            findings = COMPILE_LINE_FINDINGS.format(findings="; ".join(found)) if found else ""
            blocks.append(COMPILE_LINE_FOUND.format(file=path, line=line, message=message, excerpt=excerpt, findings=findings))
        else:
            blocks.append(COMPILE_LINE_MISSING.format(file=path, line=line, message=message))
    kb = ""
    if "wb_knowledge" in getattr(mcp, "tools", {}):
        args = {"query": KB_PITFALLS_QUERY, "max_files": 1}
        try:
            raw = _raw_text(mcp.call_tool("wb_knowledge", args))
            _add_evidence(meta, raw)
            meta["kb_this_turn"] = True
            sections = _kb_sections(raw)
            if sections:
                kb = COMPILE_KB.format(sections=sections)
            print(tr(f"  [KOD] automatyczne wb_knowledge('{KB_PITFALLS_QUERY}'): {len(sections)} zn. sekcji o pułapkach",
                     f"  [CODE] automatic wb_knowledge('{KB_PITFALLS_QUERY}'): {len(sections)} chars of pitfall sections"), flush=True)
        except (MCPError, OSError, ValueError, TypeError) as exc:
            print(tr(f"  [KOD] wb_knowledge nieudane: {exc!r}", f"  [CODE] wb_knowledge failed: {exc!r}"), flush=True)
    project = COMPILE_PROJECT if "project" in getattr(mcp, "tools", {}) else ""
    return HINT_COMPILE_LINES.format(errors="\n\n".join(blocks), kb=kb, project=project)


# ---------------------------------------------------------------- klasy bazowe z plików gry (od 1.8.2)
# Hierarchia klas w danych API BK jest niewiarygodna: prawie połowa klas Arma nie ma klasy bazowej
# (np. ArmaReforgerScripted, ChimeraWorld, TimeAndWeatherManagerEntity), a u wielu przodkowie trafili do listy
# "Direct subclasses" (np. SCR_ToggleSafetyUserAction: "Inherits from: BaseUserAction", "Direct subclasses:
# ScriptedUserAction, SCR_InventoryAction, SCR_InspectionUserAction" - to są jej przodkowie). Silnik czyta
# deklarację "class X : Y" z pliku gry (asset_search po dokładnej nazwie pliku + game_read) i idzie w górę.
# Pamięć podręczna na czas działania procesu: pliki gry się nie zmieniają.
_CLASS_RESULTS: dict[str, str] = {}                     # klasa -> surowy wynik api_search(type=class, limit=1) albo ""
_PARENT_CACHE: dict[str, tuple[list[str], str]] = {}    # klasa -> (przodkowie od najbliższego, plik z deklaracją)


def _class_section(raw: str, name: str) -> str:
    """Sekcja '## Klasa' wyniku api_search (do następnego '## '), razem z podsekcjami '#### Przodek'."""
    m = re.search(rf"^##\s+{re.escape(name)}\s*$(.*?)(?=^##\s|\Z)", raw or "", re.M | re.S)
    return m.group(1) if m else ""


def _bk_parent(section: str) -> str:
    m = re.search(r"^Inherits from:\s*([A-Za-z_]\w*)", section, re.M)
    return m.group(1) if m else ""


def _class_result(mcp, name: str) -> str:
    """Pełny widok jednej klasy z api_search (limit=1 daje szczegóły i metody dziedziczone). Tylko dokładna nazwa."""
    if name in _CLASS_RESULTS:
        return _CLASS_RESULTS[name]
    raw = ""
    try:
        result = mcp.call_tool("api_search", {"query": name, "type": "class", "limit": 1})
        text = _raw_text(result)
        if not result.get("isError") and _class_section(text, name):
            raw = text
    except (MCPError, OSError, ValueError, TypeError) as exc:
        print(tr(f"  [BAZA] api_search('{name}') nieudane: {exc!r}", f"  [BASE] api_search('{name}') failed: {exc!r}"), flush=True)
    _CLASS_RESULTS[name] = raw
    return raw


def _stub_parent(mcp, name: str) -> tuple[str | None, str]:
    """(klasa bazowa, plik) z deklaracji 'class Nazwa : Baza' w pliku gry o nazwie Nazwa.c. Nie zgaduje plików:
    tylko dokładna nazwa pliku z asset_search. (None, plik) = klasa bez bazowej; (None, '') = nie ustalono."""
    try:
        listing = _raw_text(mcp.call_tool("asset_search", {"query": name, "type": "script", "limit": 10}))
    except (MCPError, OSError, ValueError, TypeError):
        return None, ""
    paths = [re.sub(r"^\{[0-9A-Fa-f]{16}\}", "", m.group(1))
             for m in re.finditer(r"^\s{2,}(\S+/\S+)\s*$", listing, re.M)]
    exact = [p for p in paths if p.rsplit("/", 1)[-1].lower() == name.lower() + ".c"]
    exact.sort(key=lambda p: "/generated/" not in p.lower())      # najpierw deklaracje API (proto external)
    decl = re.compile(_CLASS_DECL_RE.format(name=re.escape(name)), re.M)
    root = re.compile(_CLASS_ROOT_RE.format(name=re.escape(name)), re.M)
    for path in exact[:2]:
        try:
            result = mcp.call_tool("game_read", {"path": path})
        except (MCPError, OSError, ValueError, TypeError):
            continue
        if result.get("isError"):
            continue
        text = _raw_text(result)
        m = decl.search(text)
        if m:
            return m.group(1), path
        if root.search(text):
            return None, path
    return None, ""


def _ancestors(mcp, meta: dict, name: str) -> tuple[list[str], str]:
    """Łańcuch klas bazowych (od najbliższej) z deklaracji w plikach gry. Gdy pliku klasy nie ma
    (nazwa pliku inna niż nazwa klasy), łańcuch kończy się na ostatniej ustalonej klasie.
    Limit nowych klas na turę: meta['resolve_budget']; wynik (także pusty) zostaje w pamięci podręcznej."""
    if name in _PARENT_CACHE:
        return _PARENT_CACHE[name]
    if DOCS and DOCS.knows(name):
        # Od 1.8.8: dokumentacja API Workbencha zna całe drzewo (bez wywołań MCP i bez limitu na turę).
        chain = DOCS.chain(name, PARENT_RESOLVE_DEPTH)
        _PARENT_CACHE[name] = (chain, DOC_HIERARCHY_SOURCE)
        print(tr(f"  [BAZA] {name}: klasy bazowe z dokumentacji API -> {' : '.join(chain) or 'brak (klasa główna)'}",
                 f"  [BASE] {name}: base classes from the API documentation -> {' : '.join(chain) or 'none (root class)'}"),
              flush=True)
        return chain, DOC_HIERARCHY_SOURCE
    if meta.get("resolve_budget", 0) <= 0:
        return [], ""
    meta["resolve_budget"] -= 1
    chain: list[str] = []
    first_path = ""
    current = name
    for depth in range(PARENT_RESOLVE_DEPTH):
        parent, path = _stub_parent(mcp, current)
        if depth == 0:
            first_path = path
        if not parent or parent == name or parent in chain:
            break
        chain.append(parent)
        current = parent
    _PARENT_CACHE[name] = (chain, first_path)
    print(tr(f"  [BAZA] {name}: klasy bazowe z pliku gry {first_path or '?'} -> {' : '.join(chain) or 'nie ustalono'}",
             f"  [BASE] {name}: base classes from game file {first_path or '?'} -> {' : '.join(chain) or 'not determined'}"),
          flush=True)
    return chain, first_path


def _use_chain(meta: dict, mcp, name: str, chain: list[str]) -> None:
    """Łańcuch do kontroli API + pełne wyniki przodków jako dowody (model nie widzi ich w całości)."""
    meta.setdefault("chains", {})[name] = chain
    added = meta.setdefault("chain_evidence", set())
    for cls in chain:
        raw = _class_result(mcp, cls)
        if raw and cls not in added:
            added.add(cls)
            _add_evidence(meta, raw)


def _member_names(section: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"^\s*-\s*[^\n(]*?\b([A-Za-z_]\w*)\s*\(", section, re.M)))


def _parents_note(mcp, meta: dict, query, raw: str) -> str:
    """Dopisek do wyniku api_search dla dokładnie szukanej klasy, gdy łańcuch z pliku gry różni się
    od danych BK (brak klasy bazowej albo inna klasa bazowa)."""
    q = _norm_query(query)
    if not re.fullmatch(r"[A-Za-z_]\w*", q or ""):
        return ""
    section = _class_section(raw, q)
    if not section:
        return ""
    chain, path = _ancestors(mcp, meta, q)
    if not chain:
        return ""
    _use_chain(meta, mcp, q, chain)
    bk = _bk_parent(section)
    # Od 1.8.8: podklasy z dokumentacji. BK potrafi wpisać przodków jako "Direct subclasses"; lista BK bywa
    # skrócona, więc za błąd uznajemy tylko klasę, której dokumentacja NIE podaje jako podklasy.
    subs_note = ""
    if DOCS and DOCS.knows(q):
        m = re.search(r"^Direct subclasses:\s*(.+)$", section, re.M)
        bk_subs = [x.strip() for x in m.group(1).split(",") if re.fullmatch(r"\w+", x.strip())] if m else []
        doc_subs = DOCS.subclasses(q)
        if any(x not in doc_subs for x in bk_subs):
            shown = ", ".join(doc_subs[:PARENT_NOTE_MAX_NAMES]) + (
                f" (+{len(doc_subs) - PARENT_NOTE_MAX_NAMES})" if len(doc_subs) > PARENT_NOTE_MAX_NAMES else "")
            subs_note = NOTE_SUBCLASSES.format(name=q, subs=shown or tr("brak", "none"))
    if bk == chain[0]:
        return subs_note              # klasa bazowa w BK się zgadza; ewentualnie tylko poprawka podklas
    seen = set(_member_names(section))
    lines = []
    for cls in chain:
        names = [n for n in _member_names(_class_section(_CLASS_RESULTS.get(cls, ""), cls)) if n not in seen]
        if names:
            seen.update(names)
            more = f" (+{len(names) - PARENT_NOTE_MAX_NAMES})" if len(names) > PARENT_NOTE_MAX_NAMES else ""
            lines.append(f"- {cls}: " + ", ".join(names[:PARENT_NOTE_MAX_NAMES]) + more)
    note = NOTE_PARENTS.format(name=q, path=path or "?", chain=f"{q} : " + " : ".join(chain),
                               bk=(f"'Inherits from: {bk}'" if bk else tr("brak klasy bazowej", "no base class")),
                               members="\n".join(lines) or tr("- (brak danych o metodach)", "- (no method data)"),
                               first=chain[0])
    note = note if len(note) <= PARENT_NOTE_CAP else note[:PARENT_NOTE_CAP - 40] + tr("\n[... lista skrócona]]",
                                                                                     "\n[... list shortened]]")
    return note + subs_note


def _prepare_api_evidence(content: str, meta: dict, session_files: dict, mcp) -> None:
    """Przed kontrolą API: dla Klasa.Metoda i GetGame().Metoda, których nie ma w dowodach, silnik sam pobiera
    pełny widok klasy i jej przodków (z deklaracji w plikach gry). Model tych wyników nie widzi."""
    if "api_search" not in getattr(mcp, "tools", {}):
        return
    meta.setdefault("chains", {})

    def classes_for(target: str) -> list[str]:
        return (_game_classes(meta) if target == "ArmaReforgerScripted"
                else [target] + meta["chains"].get(target, []))

    def missing(target: str, methods: list[str]) -> list[str]:
        texts = _evidence_texts(meta, session_files)
        return [m for m in methods if not any(_find_class_method(texts, c, m)[0] for c in classes_for(target))]

    def add(cls: str) -> str:
        raw = _class_result(mcp, cls)
        added = meta.setdefault("chain_evidence", set())
        if raw and cls not in added:
            added.add(cls)
            _add_evidence(meta, raw)
        return raw

    targets: dict[str, list[str]] = {}
    for cls, meth, kind in _api_calls(content):
        if kind == "game":
            targets.setdefault("ArmaReforgerScripted", []).append(meth)
        elif kind == "static":
            targets.setdefault(cls, []).append(meth)
    decl_classes: set[str] = set()
    items = _decl_items(content)
    own = {it[0] for it in items if not it[2]}
    for cls, base, modded, overrides, implicit in items:   # od 1.8.3: class X : Y, modded class X, override
        target = _decl_target(cls, base, modded, own)
        if target:
            decl_classes.add(target)
            targets.setdefault(target, []).extend(overrides + implicit)   # od 1.8.6: także wywołania bez obiektu
    targets = {t: ms for t, ms in targets.items()
               if missing(t, ms) or (t in decl_classes and not _class_known(_evidence_texts(meta, session_files), t))}
    for target, methods in list(targets.items())[:PARENT_RESOLVE_PER_TURN]:
        if not add(target) and target != "ArmaReforgerScripted":
            continue                  # klasy nie ma w API: nie szukamy jej przodków w plikach gry
        if not missing(target, methods):
            continue
        if target not in meta["chains"]:
            chain, _ = _ancestors(mcp, meta, target)
            if chain:
                _use_chain(meta, mcp, target, chain)
        if target == "ArmaReforgerScripted" and missing(target, methods):
            # Obiekt gry: plik ArmaReforgerScripted.c może nie istnieć; sprawdzamy stałą listę klas gry.
            for cls in _game_classes(meta)[1:]:
                add(cls)
    # Od 2.0.3: Enum.WARTOŚĆ, której nie ma w dowodach - silnik szuka deklaracji enuma (najwyżej 2 na sprawdzenie).
    resolved = 0
    for enum, value in _enum_refs(content):
        texts = _evidence_texts(meta, session_files)
        if resolved >= 2 or enum in meta.setdefault("enum_tried", set()) or _enum_values(texts, enum) is not None \
                or _word_seen(texts, value):
            continue
        meta["enum_tried"].add(enum)
        resolved += 1
        path, decl = _resolve_enum(mcp, meta, session_files, enum)
        if path:
            meta.setdefault("enum_notes", []).append(NOTE_ENUM_DECL.format(name=enum, path=path, decl=decl))


def _final_check_footer(content: str, meta: dict, session_files: dict, mcp, where: str) -> str:
    """Kontrola API i składni dla odpowiedzi bez rundy poprawkowej (synteza awaryjna, ponowienie bez narzędzi).
    Wcześniej takie odpowiedzi omijały kontrole. Zwraca stopkę (tryb fix) albo pusty tekst."""
    if API_CHECK_MODE == "off" or not content:
        return ""
    try:
        _prepare_api_evidence(content, meta, session_files, mcp)
        problems = _api_problems(content, meta, session_files)
        syntax = _syntax_problems(content)
    except Exception as exc:  # kontrola nigdy nie psuje odpowiedzi
        print(tr(f"  [API] kontrola ({where}) pominięta z powodu błędu: {exc!r}",
                 f"  [API] check ({where}) skipped because of an error: {exc!r}"), flush=True)
        return ""
    if problems:
        print(tr(f"  [API] ({where}) niepotwierdzone: ", f"  [API] ({where}) not confirmed: ") + "; ".join(problems), flush=True)
    if syntax:
        print(tr(f"  [KOD] ({where}) niedozwolona składnia: ", f"  [CODE] ({where}) disallowed syntax: ")
              + "; ".join(syntax), flush=True)
    if API_CHECK_MODE != "fix":
        return ""
    return (_api_footer(problems) if problems else "") + (
        FOOTER_SYNTAX.format(problems="; ".join(syntax)) if syntax else "")


_EXACT_FILES: dict[str, list[str]] = {}


def _exact_game_files(mcp, name: str) -> list[str]:
    """Pliki gry o DOKŁADNIE takiej nazwie (bez rozszerzenia) jak name: .c, .et, .conf, .layout (asset_search)."""
    if name in _EXACT_FILES:
        return _EXACT_FILES[name]
    listing = _raw_text(mcp.call_tool("asset_search", {"query": name, "type": "any", "limit": 10}))
    paths = [re.sub(r"^\{[0-9A-Fa-f]{16}\}", "", m.group(1)) for m in re.finditer(r"^\s{2,}(\S+/\S+)\s*$", listing, re.M)]
    exact = [p for p in paths if p.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower() == name.lower()
             and p.rsplit(".", 1)[-1].lower() in ("c", "et", "conf", "layout")]
    _EXACT_FILES[name] = exact
    return exact


_GLOBAL_DECLS: dict[str, tuple[str, str, str]] = {}      # funkcja -> (ścieżka, deklaracja, pełny tekst pliku)


def _global_decl(mcp, name: str) -> tuple[str, str, str]:
    """Od 1.9.2: deklaracja funkcji globalnej (np. Print, PrintFormat) z pliku gry wskazanego w GLOBAL_FUNCTION_FILES.
    BK nie przeszukuje treści plików, więc model sam jej nie znajdował (test B: brak PrintFormat i %1).
    Ścieżkę silnik ustala przez asset_search (dokładna nazwa pliku), deklarację czyta z game_read."""
    if name in _GLOBAL_DECLS:
        return _GLOBAL_DECLS[name]
    out = ("", "", "")
    stem = GLOBAL_FUNCTION_FILES.get(name)
    if stem and "game_read" in getattr(mcp, "tools", {}):
        for path in [p for p in _exact_game_files(mcp, stem) if p.lower().endswith(".c")][:2]:
            result = mcp.call_tool("game_read", {"path": path})
            if result.get("isError"):
                continue
            text = _raw_text(result)
            lines = text.split("\n")
            idx = next((i for i, ln in enumerate(lines) if re.search(rf"\bproto\b[^\n(]*\b{re.escape(name)}\s*\(", ln)), None)
            if idx is None:
                continue
            start = idx                       # komentarz dokumentujący tuż nad deklaracją (//! albo /*! ... */)
            if idx > 0 and lines[idx - 1].strip().endswith("*/"):
                opener = next((j for j in range(idx - 1, max(-1, idx - 25), -1) if "/*" in lines[j]), None)
                if opener is not None:
                    start = opener
            else:
                while start > 0 and idx - start < 10 and lines[start - 1].strip().startswith("//"):
                    start -= 1
            out = (path, "\n".join(lines[start:idx + 1]).strip(), text)
            break
    _GLOBAL_DECLS[name] = out
    print(tr(f"  [GLOBALNA] {name}: {('deklaracja z ' + out[0]) if out[0] else 'nie znaleziono pliku z deklaracją'}",
             f"  [GLOBAL] {name}: {('declaration from ' + out[0]) if out[0] else 'file with the declaration not found'}"),
          flush=True)
    return out


_ENUM_DECLS: dict[str, tuple[str, str, str]] = {}       # enum -> (ścieżka, deklaracja, pełny tekst pliku)


def _owner_classes(texts: list[str], name: str) -> list[str]:
    """Klasy, w których wynikach narzędzi pada nazwa (np. typ parametru: AwardXP(int playerId, SCR_EXPRewards rewardID)):
    właściciel z wiersza 'Klasa.Metoda(' albo z najbliższego nagłówka '## Klasa' nad wystąpieniem."""
    owners: list[str] = []
    w_re = re.compile(rf"\b{re.escape(name)}\b")
    for raw in texts:
        text = _NOT_FOUND_LINE_RE.sub("", raw)
        for m in w_re.finditer(text):
            start = text.rfind("\n", 0, m.start()) + 1
            end = text.find("\n", m.start())
            line = text[start:end if end >= 0 else len(text)]
            o = re.match(r"^\s*(?:\d+\.\s*|\*\*Method:\*\*\s*)?([A-Z]\w*)\.", line)
            if o:
                owners.append(o.group(1))
                continue
            heads = re.findall(r"^##\s+([A-Za-z_]\w*)\s*$", text[:m.start()], re.M)
            if heads:
                owners.append(heads[-1])
    return [o for o in dict.fromkeys(owners) if o != name][:2]


def _resolve_enum(mcp, meta: dict, session_files: dict, name: str) -> tuple[str, str]:
    """Od 2.0.3: deklaracja enuma, którego api_search nie zna (BK nie indeksuje wielu enumów ze skryptów, np.
    SCR_EXPRewards). Szuka pliku o nazwie enuma, a potem plików klas, w których wynikach enum pada jako typ
    (zwykle enum leży w pliku klasy, która go używa). Tylko dokładne nazwy plików; nic nie zgaduje."""
    if name in _ENUM_DECLS:
        path, decl, text = _ENUM_DECLS[name]
        if text:
            _add_evidence(meta, text)
            session_files[_path_key(path)] = text
        return path, decl
    out = ("", "", "")
    cands: list[str] = []
    tools = getattr(mcp, "tools", {})
    if "game_read" in tools and "asset_search" in tools:
        cands = [p for p in _exact_game_files(mcp, name) if p.lower().endswith(".c")][:1]
        for owner in _owner_classes(_evidence_texts(meta, session_files), name):
            cands += [p for p in _exact_game_files(mcp, owner) if p.lower().endswith(".c")][:1]
        decl_re = re.compile(rf"^[^\n]*\benum\s+{re.escape(name)}\b[^{{;]*\{{.*?\}}", re.S | re.M)
        for path in list(dict.fromkeys(cands))[:3]:
            result = mcp.call_tool("game_read", {"path": path})
            if result.get("isError"):
                continue
            text = _raw_text(result)
            m = decl_re.search(text)
            if m:
                decl = m.group(0).strip()
                decl = decl if len(decl) <= 3000 else decl[:3000] + "\n..."
                session_files[_path_key(path)] = text
                _add_evidence(meta, text)
                out = (path, decl, text)
                break
    _ENUM_DECLS[name] = out
    if not out[0] and not cands:
        return "", ""                  # nic do sprawdzenia (brak pliku enuma i klas, które go używają): bez wpisu w logu
    print(tr(f"  [ENUM] {name}: {('deklaracja z ' + out[0]) if out[0] else 'nie znaleziono deklaracji'}",
             f"  [ENUM] {name}: {('declaration from ' + out[0]) if out[0] else 'declaration not found'}"), flush=True)
    return out[0], out[1]


def _search_miss_file_note(mcp, query) -> str:
    """Od 1.8.8: api_search nie zna nazwy (np. enum LogLevel), a w grze jest plik o dokładnie takiej nazwie
    (scripts/Core/generated/Debug/LogLevel.c). Test B: model uznał wtedy, że poziomów logowania nie ma."""
    q = _norm_query(query)
    if not re.fullmatch(r"[A-Z][A-Za-z0-9_]{2,}", q or "") or "asset_search" not in getattr(mcp, "tools", {}):
        return ""
    files = [p for p in _exact_game_files(mcp, q) if p.lower().endswith(".c")]
    if not files:
        return ""
    print(tr(f"  [PLIK] api_search bez trafienia dla '{q}', ale jest plik gry: {', '.join(files[:2])}",
             f"  [FILE] api_search found no match for '{q}', but there is a game file: {', '.join(files[:2])}"), flush=True)
    return NOTE_SEARCH_MISS_FILE.format(name=q, files=", ".join(files[:2]))


def _question_files_note(question: str, mcp) -> str:
    """Od 1.8.6: nazwy z pytania (np. Weapon_Base, SCR_ToggleSafetyUserAction), dla których w grze jest plik o DOKŁADNIE
    takiej nazwie, silnik podaje modelowi od razu (test A: pytanie o Weapon_Base, a model nie otworzył tego pliku).
    Tylko dokładne nazwy plików z asset_search; niczego nie zgadujemy."""
    if "asset_search" not in getattr(mcp, "tools", {}):
        return ""
    names = list(dict.fromkeys(re.findall(QUESTION_NAME_RE, question or "")))[:QUESTION_FILES_MAX]
    found = []
    for name in names:
        exact = _exact_game_files(mcp, name)
        if exact:
            found.append(f"{name} -> {', '.join(exact[:2])}")
    print(tr(f"  [PYTANIE] nazwy z pytania: {', '.join(names) or '-'}; pliki: {'; '.join(found) or 'brak dokładnych'}",
             f"  [QUESTION] names from the question: {', '.join(names) or '-'}; files: {'; '.join(found) or 'no exact ones'}"),
          flush=True)
    return QUESTION_FILES_NOTE.format(files="; ".join(found)) if found else ""


def _suggest_paths(mcp, path: str) -> str:
    """Po nieudanym game_read: deterministycznie szukamy prawdziwej ścieżki po nazwie pliku."""
    if "asset_search" not in mcp.tools or not path:
        return ""
    base = path.replace("\\", "/").rstrip("/").split("/")[-1]
    stem, _, ext = base.rpartition(".")
    if not stem:
        stem, ext = base, ""
    kind = {"c": "script", "proto": "script", "et": "prefab", "conf": "config", "layout": "layout"}.get(ext.lower(), "any")
    try:
        found = tool_text(mcp.call_tool("asset_search", {"query": stem, "type": kind, "limit": 8}), "asset_search")
    except (MCPError, RuntimeError, OSError):
        return ""
    proto_note = (tr("\n[W tej instalacji nie ma plików .proto: deklaracje API leżą w plikach .c "
                     "(scripts/Game/generated/...).]",
                     "\n[This installation has no .proto files: API declarations are in .c files "
                     "(scripts/Game/generated/...).]") if ext.lower() == "proto" else "")
    return (tr(f"\n[Podpowiedź: wyniki asset_search dla '{stem}' - użyj jednej z tych ścieżek:]\n",
               f"\n[Hint: asset_search results for '{stem}' - use one of these paths:]\n")
            + found[:1500] + proto_note)


def _is_source_result(text: str, tool_name: str = "") -> bool:
    """Odczyt pliku/wiki (wysoka wartość) vs. wynik wyszukiwania (niska wartość)."""
    first = _strip_note(text).split("\n", 1)[0]
    # Lokalny widok pliku (query / zakres linii) to też odczyt pliku, a nie wynik wyszukiwania.
    # Od 1.8.4 także plik luzem: nagłówek "// ścieżka/plik.ext" bez "(from .pak)".
    return ((first.startswith("//") and ("(from .pak)" in first or re.match(r"^//\s+\S+/\S+\.\w{1,8}\s*$", first)))
            or first.startswith(("[Widok lokalny", "[Local file view"))
            or tool_name in ("wiki_read", "wb_knowledge", "project", "prefab"))


def _compact_tool_context(messages: list[dict], limit: int | None = None) -> None:
    """Zapobiega wypychaniu pytania i odpowiedzi poza okno kontekstu Ollamy.

    Kolejność wg wartości: najpierw wyniki wyszukiwań (api_search/asset_search...),
    potem starsze odczyty plików, na końcu dwa najświeższe wyniki. Nie czyta żadnych
    lokalnych plików gry; zredukowane wyniki mają wyraźne oznaczenie.
    """
    limit = limit or MAX_TOOL_CONTEXT_CHARS
    indices = [i for i, item in enumerate(messages) if item.get("role") == "tool"]

    def content(i):
        return messages[i].get("content", "")

    def total():
        return sum(len(content(i)) for i in indices)

    if total() <= limit:
        return
    recent = set(indices[-2:])
    older = [i for i in indices if i not in recent]
    search_like = [i for i in older if not _is_source_result(content(i), messages[i].get("tool_name", ""))]
    sources = [i for i in older if i not in search_like]
    # 1) wyniki wyszukiwań
    for i in search_like:
        if total() <= limit:
            return
        if len(content(i)) > COMPACT_SEARCH_RESULT_CHARS:
            messages[i]["content"] = _shrink(content(i), COMPACT_SEARCH_RESULT_CHARS)
    # 2) starsze odczyty plików
    for i in sources:
        if total() <= limit:
            return
        if len(content(i)) > COMPACT_OLD_RESULT_CHARS:
            messages[i]["content"] = _shrink(content(i), COMPACT_OLD_RESULT_CHARS)
    # 3) dwa najświeższe wyniki
    for i in indices[-2:]:
        if total() <= limit:
            return
        text = content(i)
        if len(text) > 2000:
            messages[i]["content"] = _shrink(text, max(2000, len(text) - (total() - limit)))
    # 4) awaryjnie: największe wyniki najpierw, po ~30% naraz (bez wycinania jednego do zera);
    #    elementy, których nie da się już skrócić (np. digest prefabu), pomijamy.
    stuck: set[int] = set()
    for _ in range(80):
        if total() <= limit:
            return
        pool = [k for k in indices if k not in stuck and len(content(k)) > 500]
        if not pool:
            return
        biggest = max(pool, key=lambda k: len(content(k)))
        before = len(content(biggest))
        messages[biggest]["content"] = _shrink(content(biggest), max(500, int(before * 0.7)))
        if len(content(biggest)) >= before:
            stuck.add(biggest)


def _is_incomplete_answer(content: str) -> bool:
    text = content.rstrip()
    if not text:
        return True
    if text.count("```") % 2:
        return True
    last = text.splitlines()[-1].strip()
    if last.startswith("|") and last.count("|") < 3:
        return True
    if last.endswith(("...", "…", "(", ",")):
        return True
    return False


def _norm_query(query) -> str:
    q = str(query or "").strip()
    q = re.sub(r"\s*\([^)]*\)?\s*$", "", q).strip()        # GetInspect() / Print( -> bez nawiasu
    q = re.sub(r"^(class|enum|method)\s+", "", q, flags=re.I)
    return q.strip("`'\" ")


def _exact_match_note(name: str, arguments: dict | None, text: str) -> str:
    """api_search / asset_search zwracają PODOBNE nazwy, gdy dokładnej nie ma. Mówimy to wprost,
    bo model traktuje rozmyte trafienia jako dowód istnienia (np. SCR_Component -> SCR_ComponentHelper).
    Notatka powstaje tylko, gdy format wyniku jest rozpoznany; inaczej nic nie dopisujemy."""
    q = _norm_query((arguments or {}).get("query"))
    if not q:
        return ""
    if name == "api_search" and q in API_GLOBAL_FUNCTIONS:
        # Od 1.8.2: funkcji globalnych nie ma w indeksie api_search; "brak trafienia" nie może znaczyć "nie istnieje".
        return NOTE_GLOBAL_FUNCTION.format(name=q, info=API_GLOBAL_FUNCTIONS[q])
    if name == "api_search":
        classes: list[str] = []
        methods: list[tuple[str, str]] = []      # (klasa, składowa): metody i właściwości
        current = None
        for line in text.splitlines():
            m = re.match(r"^##\s+([A-Za-z_]\w*)\s*$", line)
            if m:
                current = m.group(1)
                classes.append(current)
                continue
            m = re.match(r"^(?:\d+\.\s+|\*\*Method:\*\*\s+)([A-Za-z_]\w*)\.(.+)$", line)
            if m:
                mm = re.search(r"([A-Za-z_]\w*)\s*\(", m.group(2))
                if mm:
                    methods.append((m.group(1), mm.group(1)))
                continue
            if current and line.lstrip().startswith("- "):       # składowe wewnątrz bloku klasy
                mm = re.search(r"([A-Za-z_]\w*)\s*\(", line) or re.search(r"\*\*(\w+)\*\*", line)
                if mm:
                    methods.append((current, mm.group(1)))
        if not classes and not methods:
            return ""
        ql = q.lower()
        hits = []
        if "." in q:
            owner_q, _, member_q = ql.rpartition(".")
            hits = [f"{o}.{n}" for o, n in methods if o.lower() == owner_q and n.lower() == member_q]
        else:
            hits = [c for c in classes if c.lower() == ql]
            hits += [f"{o}.{n}" for o, n in methods if n.lower() == ql]
        if hits:
            uniq = list(dict.fromkeys(hits))[:4]
            return tr(f"[Dokładne trafienie dla '{q}': {', '.join(uniq)}]", f"[Exact match for '{q}': {', '.join(uniq)}]")
        shown = list(dict.fromkeys(classes + [f"{o}.{n}" for o, n in methods]))[:3]
        method_like = (str((arguments or {}).get("type", "any")).lower() == "class"
                       and re.match(r"(Get|Set|Is|Has|Can|On|Try|Add|Remove)[A-Z]|[msg]_", q))
        tip = (tr(" Wygląda to na nazwę metody lub pola, nie klasy: spróbuj api_search z type=method.",
                  " This looks like a method or field name, not a class: try api_search with type=method.")
               if method_like else "")
        return tr(f"[BRAK DOKŁADNEGO TRAFIENIA dla '{q}'. Poniższe wyniki to tylko PODOBNE nazwy "
                  f"({', '.join(shown)}). To NIE jest dowód, że '{q}' istnieje - nie opisuj go jako istniejącego.{tip}]",
                  f"[NO EXACT MATCH for '{q}'. The results below are only SIMILAR names "
                  f"({', '.join(shown)}). This is NOT proof that '{q}' exists - do not describe it as existing.{tip}]")
    if name == "asset_search":
        paths = [m.group(1) for m in re.finditer(r"^\s{2,}(\S+/\S+)\s*$", text, re.M)]
        if not paths:
            return ""
        stem = re.sub(r"\.\w+$", "", q).lower()
        exact = [p for p in paths if re.sub(r"\.\w+$", "", p.rsplit("/", 1)[-1]).lower() == stem]
        if exact:
            return tr(f"[Dokładne trafienie nazwy pliku: {exact[0]}]", f"[Exact match of the file name: {exact[0]}]")
        return tr(f"[Brak pliku o nazwie dokładnie '{q}'. Poniżej pliki, których nazwa tylko ZAWIERA ten ciąg; "
                  "to nie oznacza, że szukana klasa istnieje.]",
                  f"[No file named exactly '{q}'. Below are files whose name only CONTAINS this string; "
                  "this does not mean that the searched class exists.]")
    return ""


def tool_text(result: dict, name: str = "", arguments: dict | None = None) -> str:
    content = _raw_text(result)
    if result.get("isError"):
        content = MCP_TOOL_ERROR + "\n" + content
    if name == "api_search":
        content = _dedupe_api_result(content)
    if not result.get("isError"):
        note = _exact_match_note(name, arguments, content)
        if note.startswith(("[Funkcja globalna", "[Global function")):
            # Od 1.8.5: wyniki to metody klas testowych o tej samej nazwie (SCR_AutotestCaseBase.PrintFormat);
            # model brał je za sposób logowania i tworzył obiekt klasy testowej. Zostaje notatka i lista klas.
            owners = list(dict.fromkeys(re.findall(r"^\s*(?:\d+\.\s*|\*\*Method:\*\*\s*)(\w+)\.", content, re.M)))
            content = note + (NOTE_GLOBAL_OWNERS.format(owners=", ".join(owners[:6])) if owners else "")
        elif note:
            content = note + "\n" + content
    if len(content) > MAX_TOOL_RESULT_CHARS:
        content = _shrink(content, MAX_TOOL_RESULT_CHARS)
    return content


def ollama_chat(messages: list[dict], tools: list[dict], model: str, num_ctx: int, think: str | None = None) -> dict:
    messages = [{k: v for k, v in m.items() if not str(k).startswith("_")} for m in messages]
    payload = {"model": model, "messages": messages, "stream": bool(OLLAMA_STREAM),
               "options": {"temperature": OLLAMA_TEMPERATURE, "num_ctx": num_ctx}}
    if OLLAMA_NUM_PREDICT > 0:
        payload["options"]["num_predict"] = OLLAMA_NUM_PREDICT
    if think or OLLAMA_THINK:
        payload["think"] = think or OLLAMA_THINK
    if tools:
        payload["tools"] = tools
    request = urllib.request.Request(
        OLLAMA_URL, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT) as response:
            parsed = _read_stream(response) if OLLAMA_STREAM else json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", "replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(tr(f"Ollama nie odpowiada ({OLLAMA_URL}): {exc}", f"Ollama is not responding ({OLLAMA_URL}): {exc}")) from exc
    message = parsed.get("message")
    if not isinstance(message, dict):
        raise RuntimeError(tr("Ollama nie zwróciła pola message", "Ollama did not return the message field"))
    message = dict(message)
    if not message.get("tool_calls") and isinstance(message.get("content"), str) and message["content"]:
        message["content"] = _clean_answer_text(message["content"])
    # Metadane diagnostyczne nie sa przekazywane z powrotem do API Ollamy.
    message["_done_reason"] = parsed.get("done_reason", "")
    message["_prompt_eval_count"] = parsed.get("prompt_eval_count")
    message["_eval_count"] = parsed.get("eval_count")
    return message


def _read_stream(response) -> dict:
    """Od 1.8.7: odpowiedź Ollamy w trybie stream (NDJSON). Składa treść, rozumowanie i tool_calls w jedną
    wiadomość jak przy stream=false. Gdy samo rozumowanie przekroczy THINK_ABORT_TOKENS, a tekstu odpowiedzi
    i wywołań narzędzi jeszcze nie ma, przerywa generację (done_reason=length, pusta treść): silnik ma już
    na to ścieżkę (ponowienie z niskim rozumowaniem), a nie czeka minutami do num_predict."""
    content: list[str] = []
    thinking: list[str] = []
    tool_calls: list = []
    role = "assistant"
    think_chunks = 0
    last: dict = {}
    for raw in response:
        raw = raw.strip()
        if not raw:
            continue
        try:
            chunk = json.loads(raw)
        except ValueError:
            continue
        if chunk.get("error"):
            raise RuntimeError(f"Ollama: {chunk['error']}")
        msg = chunk.get("message") or {}
        role = msg.get("role") or role
        if msg.get("content"):
            content.append(msg["content"])
        if msg.get("thinking"):
            thinking.append(msg["thinking"])
            think_chunks += 1
        if msg.get("tool_calls"):
            tool_calls.extend(msg["tool_calls"])
        if chunk.get("done"):
            last = chunk
            break
        if (THINK_ABORT_TOKENS > 0 and think_chunks >= THINK_ABORT_TOKENS
                and not tool_calls and not "".join(content).strip()):
            print(tr(f"  [OLLAMA] rozumowanie przerwane po ~{think_chunks} tokenach bez tekstu odpowiedzi "
                     f"(próg REFORGER_THINK_ABORT={THINK_ABORT_TOKENS})",
                     f"  [OLLAMA] reasoning aborted after ~{think_chunks} tokens without answer text "
                     f"(threshold REFORGER_THINK_ABORT={THINK_ABORT_TOKENS})"), flush=True)
            last = {"done_reason": "length", "eval_count": think_chunks, "_aborted": True}
            break
    message = {"role": role, "content": "".join(content)}
    if thinking:
        message["thinking"] = "".join(thinking)
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"message": message, "done_reason": last.get("done_reason", ""),
            "prompt_eval_count": last.get("prompt_eval_count"), "eval_count": last.get("eval_count")}


def _clean_answer_text(text: str) -> str:
    """Od 1.8.7: rozumowanie, które wyciekło do treści, i zapętlone powtórzenia wierszy."""
    try:
        text, cut = _strip_leaked_reasoning(text)
        if cut:
            print(tr(f"  [ROZUMOWANIE] usunięto z treści odpowiedzi wyciek rozumowania modelu: {cut} zn.",
                     f"  [REASONING] removed leaked model reasoning from the answer text: {cut} chars"), flush=True)
        text, rep = _collapse_repeats(text)
        if rep:
            print(tr(f"  [POWTÓRZENIA] usunięto {rep} powtórzonych linii (zapętlenie modelu)",
                     f"  [REPEATS] removed {rep} repeated lines (model loop)"), flush=True)
        text, renamed = _sync_entry_classes(text)
        for old_name, new_name in renamed:
            print(tr(f"  [AUTOPOPRAWKA] wpis .et: klasa {old_name} -> {new_name} (jak nowa klasa w skrypcie)",
                     f"  [AUTOFIX] .et entry: class {old_name} -> {new_name} (same as the new class in the script)"), flush=True)
    except Exception as exc:  # porządkowanie nigdy nie psuje odpowiedzi
        print(tr(f"  [ROZUMOWANIE] porządkowanie pominięte z powodu błędu: {exc!r}",
                 f"  [REASONING] cleanup skipped because of an error: {exc!r}"), flush=True)
    return text


def prune_history(messages: list[dict]) -> None:
    """Usuwaj tylko pełne zakończone tury, nigdy fragment wywołania narzędzia."""
    while len(messages) > MAX_HISTORY_MESSAGES:
        if len(messages) < 3:
            return
        next_user = next((i for i in range(2, len(messages))
                          if messages[i].get("role") == "user" and not messages[i].get("_draft")), None)
        if next_user is None:
            return
        del messages[1:next_user]


def _is_negative_result(text: str) -> bool:
    """Wynik bez nowej informacji: brak trafienia, pusty widok, odrzucona powtórka."""
    t = text.lstrip()
    # Od 2.0.0 znaczniki w obu językach (historia mogła powstać w drugim języku).
    return (t.startswith(("[BRAK DOKŁADNEGO TRAFIENIA", "[NO EXACT MATCH", "Ten wynik już masz",
                          "You already have this result", "No wiki page found", "BŁĄD", "ERROR"))
            or bool(re.match(r"No (?:\w+ )?(?:assets|classes|methods|enums|properties|results|wiki)", t))
            or "Brak dopasowań dla" in t[:400] or "No matches for" in t[:400])


def _synthesize_after_mcp_limit(question: str, messages: list[dict],
                                model: str, num_ctx: int,
                                cause: str = "") -> str:
    """Nowa prosta rozmowa bez historii tool_calls i bez udostępniania narzędzi.

    Tu model ma odpowiedzieć na podstawie *już pobranych* rezultatów MCP,
    zamiast ponawiać wywołania. Błędy wywołań nie są traktowane jako dowody.
    """
    cause = cause or tr("limit wywołań MCP", "MCP call limit")
    qpos = next((i for i in range(len(messages) - 1, -1, -1)
                 if messages[i].get("role") == "user" and not messages[i].get("_draft")), 0)
    history = [
        {"role": item["role"], "content": item["content"]}
        for item in messages[1:qpos]
        if item.get("role") in ("user", "assistant")
        and isinstance(item.get("content"), str)
        and item.get("content", "").strip()
    ][-4:]
    entries = [
        item for item in messages[qpos + 1:]
        if item.get("role") == "tool"
        and isinstance(item.get("content"), str)
        and not item["content"].lstrip().startswith((
            "BŁĄD:", "BŁĄD NARZĘDZIA", "ERROR:", "MCP TOOL ERROR"))
        and not _is_negative_result(item["content"])
    ]
    # Od 1.8.3: wybór według wartości, nie według pozycji (wcześniej: pierwsze 4 + ostatnie 8, po 3500 znaków;
    # dokładne trafienie ze środka tury wypadało). Najpierw odczyty plików i dokładne trafienia, w kolejności tury.
    valuable = [it for it in entries if _is_source_result(it["content"], it.get("tool_name", ""))
                or it["content"].lstrip().startswith(("[Dokładne trafienie", "[Exact match"))]
    selected = valuable + [it for it in entries if it not in valuable]
    chunks = []
    remaining = SYNTH_BUDGET_CHARS
    for item in selected:
        if remaining <= 300:
            break
        name = str(item.get("tool_name") or "MCP")
        content = item["content"]
        section = f"[{name}]\n" + _shrink(content, min(SYNTH_ITEM_MAX_CHARS, remaining))
        chunks.append(section)
        remaining -= len(section)
    if not chunks:
        return SYNTH_NO_EVIDENCE.format(cause=cause)
    evidence = "\n\n".join(chunks)
    instructions = SYNTH_INSTRUCTIONS.format(question=question, evidence=evidence)
    simple = [
        {"role": "system", "content": messages[0].get("content", SYSTEM_PROMPT)
         + SYNTH_SYSTEM_SUFFIX},
        *history,
        {"role": "user", "content": instructions},
    ]
    for attempt in range(2):
        try:
            answer = ollama_chat(simple, [], model, num_ctx)
            content = str(answer.get("content") or "").strip()
            if content and not answer.get("tool_calls") and not _is_incomplete_answer(content):
                print(tr(f"  [OLLAMA] Synteza po limicie OK (próba {attempt + 1}).",
                         f"  [OLLAMA] Synthesis after the limit OK (attempt {attempt + 1})."), flush=True)
                return content + SYNTH_FOOTER.format(cause=cause)
            print(tr("  [OLLAMA] Synteza nie zwróciła kompletnego tekstu.",
                     "  [OLLAMA] Synthesis did not return complete text."), flush=True)
        except (RuntimeError, OSError) as exc:
            print(tr(f"  [OLLAMA] Synteza nieudana: {exc}", f"  [OLLAMA] Synthesis failed: {exc}"), flush=True)
        simple = simple[:1] + [{"role": "user", "content": SYNTH_SECOND_ATTEMPT + instructions[:14000]}]
    return SYNTH_FAILED.format(cause=cause)


def _final_without_tools(messages: list[dict], model: str, num_ctx: int, hint: str,
                         thinks: tuple = (None, "low"), label: str = "") -> str:
    """Od 1.8.3: końcowa odpowiedź w TEJ SAMEJ rozmowie (pełny kontekst tury, własne rozumowanie modelu),
    tylko bez narzędzi. Wcześniej po limicie budowano nową, okrojoną rozmowę z wybranych wyników."""
    for think in thinks:
        try:
            r = ollama_chat(messages + [{"role": "user", "content": hint}], [], model, num_ctx, think=think)
        except RuntimeError as exc:
            print(tr(f"  [KONIEC] odpowiedź bez narzędzi ({label}) nieudana: {exc}",
                     f"  [END] answer without tools ({label}) failed: {exc}"), flush=True)
            continue
        reason = r.pop("_done_reason", "")
        r.pop("_prompt_eval_count", None)
        tokens = r.pop("_eval_count", None)
        content = str(r.get("content") or "").strip()
        print(tr(f"  [KONIEC] odpowiedź bez narzędzi ({label}, think={think or '-'}): reason={reason or '?'} "
                 f"output_tokens={tokens} tekst={len(content)} zn.",
                 f"  [END] answer without tools ({label}, think={think or '-'}): reason={reason or '?'} "
                 f"output_tokens={tokens} text={len(content)} chars"), flush=True)
        if content and reason not in ("length", "max_tokens") and not _is_incomplete_answer(content):
            return content
    return ""


def _finish_without_tools(question: str, messages: list[dict], model: str, num_ctx: int, cause: str, hint: str,
                          thinks: tuple, stopped: bool, meta: dict, session_files: dict, mcp, phase) -> str:
    """Zakończenie tury bez dalszych narzędzi: najpierw odpowiedź w tej samej rozmowie; synteza awaryjna
    z wybranych wyników tylko wtedy, gdy model dwa razy nie odda kompletnego tekstu."""
    phase(tr("Kończę bez dalszych wyszukiwań - odpowiedź z zebranych wyników",
             "Finishing without further searches - answer from the collected results"))
    content = _final_without_tools(messages, model, num_ctx, hint, thinks, cause)
    if content and VERIFY_MODE == "fix":
        # Od 1.8.5: także ta odpowiedź przechodzi kontrolę cytatów; poprawka (bez narzędzi) tylko, gdy jest lepsza.
        # Od 1.8.7: oprócz cytatów także kontrola API (enumy, typy, SCR_) i składni - jedna poprawka bez narzędzi.
        def problems_of(text: str) -> tuple[list, list, list]:
            try:
                quote = _quote_problems(text, meta, session_files)
            except Exception as exc:  # kontrola nigdy nie psuje odpowiedzi
                print(tr(f"  [VERIFY] kontrola cytatów pominięta z powodu błędu: {exc!r}",
                         f"  [VERIFY] quote check skipped because of an error: {exc!r}"), flush=True)
                quote = []
            api, syntax = [], []
            if API_CHECK_MODE == "fix":
                try:
                    _prepare_api_evidence(text, meta, session_files, mcp)
                    api = _api_problems(text, meta, session_files)
                    syntax = _syntax_problems(text)
                except Exception as exc:  # j.w.
                    print(tr(f"  [API] kontrola (bez narzędzi) pominięta z powodu błędu: {exc!r}",
                             f"  [API] check (without tools) skipped because of an error: {exc!r}"), flush=True)
            return quote, api, syntax

        quote, api, syntax = problems_of(content)
        if quote or api or syntax:
            print(tr("  [VERIFY] do poprawki (bez narzędzi): ", "  [VERIFY] to fix (without tools): ")
                  + "; ".join(quote + api + syntax), flush=True)
            hint = "\n\n".join(([HINT_API_FIX.format(problems="; ".join(api))] if api else [])
                               + ([HINT_SYNTAX_FIX.format(problems="; ".join(syntax))] if syntax else [])
                               + ([HINT_QUOTE_FIX.format(problems="; ".join(quote))] if quote else []))
            draft = [{"role": "assistant", "content": content}, {"role": "user", "content": hint}]
            reason = " + ".join(r for r, on in ((tr("cytaty", "quotes"), quote), ("API", api),
                                                (tr("składnia", "syntax"), syntax)) if on)
            second = _final_without_tools(messages + draft[:1], model, num_ctx, hint, ("low",), reason)
            if second and sum(map(len, problems_of(second))) < len(quote) + len(api) + len(syntax):
                print(tr("  [SZKIC] poprawka bez narzędzi przyjęta", "  [DRAFT] fix without tools accepted"), flush=True)
                content = second
            else:
                print(tr("  [SZKIC] poprawka bez narzędzi nie jest lepsza - zostaje pierwsza wersja",
                         "  [DRAFT] fix without tools is not better - the first version stays"), flush=True)
    if content:
        footer = (FOOTER_STOPPED.format(cause=cause) if stopped else "") + _final_check_footer(
            content, meta, session_files, mcp, tr("bez narzędzi", "without tools"))
        messages.append({"role": "assistant", "content": content})
        compact_finished_history(messages)
        phase(tr("Odpowiedź gotowa", "Answer ready"))
        return content + footer
    print(tr("  [KONIEC] brak kompletnej odpowiedzi bez narzędzi - synteza awaryjna z wybranych wyników",
             "  [END] no complete answer without tools - emergency synthesis from selected results"), flush=True)
    content = _synthesize_after_mcp_limit(question, messages, model, num_ctx, cause=cause)
    footer = _final_check_footer(content, meta, session_files, mcp, tr("synteza", "synthesis"))
    messages.append(_emergency_history_entry(content))
    compact_finished_history(messages)
    phase(tr("Odpowiedź gotowa (synteza awaryjna)", "Answer ready (emergency synthesis)"))
    return content + footer


def _short_question(question: str, cap: int = 600) -> str:
    """Pytanie użytkownika do przypomnienia w podpowiedzi (od 1.9.1: test J - po podpowiedzi z wzorcami model
    odpowiadał na podpowiedź, a nie na pytanie)."""
    q = " ".join(str(question or "").split())
    return q if len(q) <= cap else q[:cap - 3] + "..."


def _push_draft(messages: list[dict], content: str, hint: str, reason: str) -> None:
    """Od 1.8.3: odrzucony szkic zostaje w kontekście tury (model widzi, co ma poprawić), a podpowiedź po nim.
    Oba wpisy mają znacznik _draft: znikają z historii po turze i nie są wysyłane do Ollamy jako pole."""
    messages.append({"role": "assistant", "content": content, "_draft": True})
    messages.append({"role": "user", "content": hint, "_draft": True})
    print(tr(f"  [SZKIC] odrzucony ({reason}): {len(content)} zn.; model poprawia go, widząc swój szkic",
             f"  [DRAFT] rejected ({reason}): {len(content)} chars; the model fixes it while seeing its draft"), flush=True)


def ask(question: str, messages: list[dict], mcp: MCPStdioClient,
        model: str, num_ctx: int, on_phase=None) -> str:
    """Jedna tura narzędzi MCP i odpowiedzi + weryfikator cytatów (tryb: REFORGER_VERIFY)."""
    answer = _ask_impl(question, messages, mcp, model, num_ctx, on_phase)
    if VERIFY_MODE == "off":
        return answer
    try:
        findings, checked, ok = _verify_answer(answer, _session_files(messages))
        if VERIFY_MODE == "fix":
            findings += _line_ref_problems(answer, _session_meta(messages))
            refs, seen_n, bad_n = _line_ref_stats(answer, _session_meta(messages))
            if refs:
                print(tr(f"  [LINIE] końcowa odpowiedź: odwołań do numerów linii {refs}; numerów z widoków w rozmowie "
                         f"{seen_n}; niepotwierdzonych {bad_n}",
                         f"  [LINES] final answer: line number references {refs}; numbers from views in the conversation "
                         f"{seen_n}; unconfirmed {bad_n}"), flush=True)
        _log_verification(findings, checked, ok)
        if VERIFY_MODE == "fix":
            # Od 1.8.7: problemy, które przetrwały poprawki, są oznaczone W TREŚCI (przy bloku / numerze linii),
            # a nie tylko w stopce pod odpowiedzią (stopki zostają bez zmian).
            cut = answer.find("\n\n_[")
            body, tail = (answer[:cut], answer[cut:]) if cut >= 0 else (answer, "")
            meta_now, files_now = _session_meta(messages), _session_files(messages)
            api_now = _api_problems(body, meta_now, files_now) if API_CHECK_MODE == "fix" else []
            body, marked = _annotate_answer(body, files_now, meta_now,
                                            _syntax_problems(body) if API_CHECK_MODE == "fix" else [], api_now)
            if marked:
                print(tr(f"  [OZNACZENIA] oznaczono w treści odpowiedzi: {marked}",
                         f"  [MARKS] marked in the answer text: {marked}"), flush=True)
                answer = body + tail
        if VERIFY_MODE == "footer" and findings:
            answer += _verification_footer(findings)
        elif VERIFY_MODE == "fix":
            shown = [f for f in findings if not any(m in f for m in VERIFY_NO_FIX_MARKERS)]
            if shown:
                answer += _verification_footer(shown)
    except Exception as exc:  # weryfikator nigdy nie może zepsuć odpowiedzi
        print(tr(f"  [VERIFY] weryfikator pominięty z powodu błędu: {exc!r}",
                 f"  [VERIFY] verifier skipped because of an error: {exc!r}"), flush=True)
    return answer


def _ask_impl(question: str, messages: list[dict], mcp: MCPStdioClient,
              model: str, num_ctx: int, on_phase=None) -> str:
    """Jedna tura narzedzi MCP i odpowiedzi, z diagnostyka limitu Ollamy."""
    def phase(text: str) -> None:
        if on_phase:
            on_phase(text)

    user_msg = {"role": "user", "content": question}
    messages.append(user_msg)
    try:
        note = _question_files_note(question, mcp)
        if note:
            user_msg["content"] = question + note
    except Exception as exc:  # wyszukanie pomocnicze nigdy nie psuje tury
        print(tr(f"  [PYTANIE] wyszukanie plików z pytania pominięte: {exc!r}",
                 f"  [QUESTION] lookup of files from the question skipped: {exc!r}"), flush=True)
    # Od 1.8.2: granica tury to TA wiadomość (szukana po tożsamości), nie zapamiętany indeks:
    # prune_history w trakcie tury usuwa starsze wiadomości i indeks wskazywał wtedy za daleko.
    session_files = _session_files(messages)   # pełne teksty odczytanych plików (dla weryfikatora)
    view_counts: dict[str, int] = {}
    misses: list[str] = []
    meta = _session_meta(messages)       # wyniki narzędzi w sesji i nazwy odrzucone przez kompilator
    meta["kb_this_turn"] = False         # czy w tej turze ktoś (model albo silnik) sięgnął do wb_knowledge
    meta["budget_hint"] = False
    meta["compile_turn"] = False         # od 2.0.3: czy pytanie zgłasza błąd kompilacji (wtedy odpowiedź musi mieć kod)
    meta["enum_tried"] = set()           # od 2.0.3: enumy, których deklaracji silnik szukał w tej turze
    meta.pop("enum_notes", None)
    meta["resolve_budget"] = PARENT_RESOLVE_PER_TURN   # ile klas bazowych silnik może ustalić w tej turze
    meta.setdefault("chains", {})
    kb_rounds = 0
    api_fix_rounds = 0
    api_footer = ""
    pending_hint = None                  # jednorazowa podpowiedź do następnego wywołania (nie trafia do historii)
    if API_CHECK_MODE != "off":
        try:
            pending_hint = _compile_error_lookup(question, meta, mcp, messages)
            meta["compile_turn"] = pending_hint is not None      # od 2.0.3: odpowiedź musi zawierać poprawiony kod
        except Exception as exc:  # kontrola nigdy nie psuje tury
            print(tr(f"  [API] sprawdzenie błędu kompilatora pominięte: {exc!r}",
                     f"  [API] compiler error check skipped: {exc!r}"), flush=True)
    empty_retries = 0
    first_draft = None                   # od 1.8.3: (treść, problemy API, składnia, cytaty) pierwszego odrzuconego szkicu
    tools = _with_local_view_params(slim_tool_definitions(mcp.tools))
    full_cache: dict[str, str] = {}      # pełny tekst odczytów game_read (do lokalnych widoków)
    seen_calls: set[str] = set()
    results_cache: dict[str, str] = {}
    dup_counts: dict[str, int] = {}
    result_msgs: dict[str, dict] = {}    # sygnatura -> wiadomość z wynikiem (do wykrycia skrócenia)
    read_paths: list[str] = []
    searches: list[str] = []
    count = 0
    tool_rounds = 0
    failed_rounds = 0

    while True:
        # Gdy bieżąca tura się rozrasta, usuwaj tylko CAŁE zakończone starsze tury.
        # Nigdy nie rozdzielaj par assistant(tool_calls) / tool w bieżącej turze.
        prune_history(messages)
        phase((tr(f"Ollama analizuje wyniki · {count} wywołań MCP", f"Ollama is analysing results · {count} MCP calls")
               if count else tr("Ollama szuka rozwiązania", "Ollama is looking for a solution")))
        # Wywołania są nadal ograniczane przez rzeczywiste schematy MCP.
        send = messages + ([pending_hint] if pending_hint else [])
        pending_hint = None
        assistant = ollama_chat(send, tools, model, num_ctx)
        done_reason = assistant.pop("_done_reason", "")
        prompt_tokens = assistant.pop("_prompt_eval_count", None)
        completion_tokens = assistant.pop("_eval_count", None)
        print(f"  [OLLAMA] reason={done_reason or '?'} context_tokens={prompt_tokens} output_tokens={completion_tokens} "
              f"model={model}", flush=True)
        if prompt_tokens and prompt_tokens >= 0.9 * num_ctx:
            print(tr(f"  [UWAGA] kontekst {prompt_tokens}/{num_ctx} tokenów - Ollama mogła uciąć prompt. "
                     "Zwiększ OLLAMA_NUM_CTX.",
                     f"  [WARNING] context {prompt_tokens}/{num_ctx} tokens - Ollama may have cut the prompt. "
                     "Increase OLLAMA_NUM_CTX."), flush=True)
        if prompt_tokens and prompt_tokens > 0.75 * num_ctx:
            total_chars = sum(len(m.get("content", "")) for m in messages if m.get("role") == "tool")
            _compact_tool_context(messages, limit=max(4000, int(total_chars * 0.6)))
        calls = assistant.get("tool_calls") or []
        if calls:
            tool_rounds += 1
        if not calls:
            content = str(assistant.get("content") or "").strip()
            # Model moze wydac tokeny na rozumowanie i nie wygenerowac tekstu.
            # Nie ponawiaj tego samego przepelnionego watku; uzyj zebranego MCP.
            qpos = next((i for i in range(len(messages) - 1, -1, -1) if messages[i] is user_msg), len(messages))
            turn_has_tools = any(m.get("role") == "tool" for m in messages[qpos + 1:])
            if not content and not turn_has_tools:
                # Pusta odpowiedź bez ani jednego odczytu w tej turze (np. nieudane parsowanie
                # tool_calls przez Ollamę). Ponów z podpowiedzią; NIE syntezuj z niczego.
                if empty_retries < 2:
                    empty_retries += 1
                    print(tr(f"  [OLLAMA] Pusta odpowiedź bez użycia MCP w tej turze - ponowienie {empty_retries}/2",
                             f"  [OLLAMA] Empty answer without MCP use in this turn - retry {empty_retries}/2"), flush=True)
                    phase(tr("Model zwrócił pustą odpowiedź - ponawiam", "The model returned an empty answer - retrying"))
                    pending_hint = {"role": "user", "content": HINT_EMPTY_NO_TOOLS}
                    continue
                content = MSG_EMPTY_TWICE
                messages.append({"role": "assistant", "content": content})
                compact_finished_history(messages)
                phase(tr("Brak odpowiedzi modelu", "No answer from the model"))
                return content
            if not content and turn_has_tools:
                # Najczęściej: rozumowanie zjadło limit generacji (reason=length) albo model zwrócił samo rozumowanie.
                # PEŁNY kontekst tury, niskie rozumowanie i bez narzędzi: odpowiedź ma być z tego, co zebrał.
                if first_draft is not None:
                    print(tr(f"  [SZKIC] poprawka nie powstała (pusta generacja, reason={done_reason or '?'}) "
                             "- zostaje pierwszy szkic",
                             f"  [DRAFT] no fix was produced (empty generation, reason={done_reason or '?'}) "
                             "- the first draft stays"), flush=True)
                    content = first_draft[0]
                else:
                    print(tr(f"  [OLLAMA] Pusty wynik po użyciu MCP (reason={done_reason or '?'}) - ponowienie z niskim "
                             "rozumowaniem, bez narzędzi",
                             f"  [OLLAMA] Empty result after MCP use (reason={done_reason or '?'}) - retry with low "
                             "reasoning, without tools"), flush=True)
                    return _finish_without_tools(question, messages, model, num_ctx,
                                                 tr("pusta odpowiedź modelu", "empty model answer"),
                                                 HINT_RETRY_AFTER_EMPTY, ("low", "low"), False,
                                                 meta, session_files, mcp, phase)
            needs_repair = (done_reason in ("length", "max_tokens") or _is_incomplete_answer(content))
            if needs_repair:
                print(tr("  [OLLAMA] Odpowiedź niepełna / limit generowania — jedna próba ponownej syntezy.",
                         "  [OLLAMA] Incomplete answer / generation limit - one more synthesis attempt."), flush=True)
                phase(tr("Ollama dokańcza niepełną odpowiedź", "Ollama is completing an incomplete answer"))
                # Zamiast przesylac ucięta tabele jako odpowiedz koncowa,
                # prosimy o krotka, pelna synteze dotychczasowych dowodow.
                retry_messages = list(messages) + [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": HINT_INCOMPLETE_RETRY},
                ]
                try:
                    again = ollama_chat(retry_messages, [], model, num_ctx)
                    again_reason = again.get("_done_reason")
                    again_content = str(again.get("content") or "").strip()
                    print(f"  [OLLAMA] Retry reason={again_reason or '?'} output_tokens={again.get('_eval_count')}", flush=True)
                    if (again_content and again_reason not in ("length", "max_tokens")
                            and not _is_incomplete_answer(again_content)):
                        content = again_content
                    else:
                        content = (content or tr("[Brak odpowiedzi]", "[No answer]")) + "\n\n" + NOTE_INCOMPLETE
                except (RuntimeError, MCPError, OSError) as exc:
                    print(tr(f"  [OLLAMA] Ponowna synteza nieudana: {exc}", f"  [OLLAMA] Repeated synthesis failed: {exc}"),
                          flush=True)
                    content = (content or tr("[Brak odpowiedzi]", "[No answer]")) + tr(
                        "\n\n[Uwaga: odpowiedź jest niepełna; ponowna próba się nie udała.]",
                        "\n\n[Note: the answer is incomplete; the retry did not succeed.]")
            api_footer = ""
            kb_hint = None
            problems, syntax = [], []
            if (KB_CHECK_MODE == "on" and content and kb_rounds < 1 and first_draft is None and not meta.get("kb_this_turn")
                    and "wb_knowledge" in getattr(mcp, "tools", {}) and count < MAX_TOOL_CALLS):
                try:
                    own = _own_code_blocks(content, meta, session_files)
                    if own:
                        kb_query = _kb_query_from_code("\n".join(own))
                        raw = _raw_text(mcp.call_tool("wb_knowledge", {"query": kb_query, "max_files": KB_CHECK_MAX_FILES}))
                        _add_evidence(meta, raw)
                        meta["kb_this_turn"] = True
                        kb_rounds += 1
                        excerpt, kb_files = _kb_excerpt(raw, kb_query)
                        print(tr(f"  [KB] własny kod bez konsultacji z bazą - wb_knowledge('{kb_query}'): "
                                 f"{', '.join(kb_files) or 'brak plików'}; {len(excerpt)} zn. wzorców",
                                 f"  [KB] own code without consulting the knowledge base - wb_knowledge('{kb_query}'): "
                                 f"{', '.join(kb_files) or 'no files'}; {len(excerpt)} chars of patterns"), flush=True)
                        if excerpt:
                            kb_hint = HINT_KB_CHECK.format(query=kb_query, files=", ".join(kb_files) or "-", excerpt=excerpt,
                                                         question=_short_question(question))
                except Exception as exc:  # kontrola nigdy nie psuje odpowiedzi
                    print(tr(f"  [KB] kontrola wzorców pominięta z powodu błędu: {exc!r}",
                             f"  [KB] pattern check skipped because of an error: {exc!r}"), flush=True)
            quote: list[str] = []
            if API_CHECK_MODE != "off" and content:
                try:
                    _prepare_api_evidence(content, meta, session_files, mcp)
                    problems = _api_problems(content, meta, session_files)
                except Exception as exc:  # kontrola nigdy nie psuje odpowiedzi
                    print(tr(f"  [API] kontrola pominięta z powodu błędu: {exc!r}",
                             f"  [API] check skipped because of an error: {exc!r}"), flush=True)
                    problems = []
                try:
                    syntax = _syntax_problems(content)
                except Exception as exc:  # j.w.
                    print(tr(f"  [KOD] kontrola składni pominięta z powodu błędu: {exc!r}",
                             f"  [CODE] syntax check skipped because of an error: {exc!r}"), flush=True)
                    syntax = []
                if syntax:
                    print(tr("  [KOD] niedozwolona składnia: ", "  [CODE] disallowed syntax: ") + "; ".join(syntax), flush=True)
                if problems:
                    print(tr("  [API] niepotwierdzone: ", "  [API] not confirmed: ") + "; ".join(problems), flush=True)
            if VERIFY_MODE == "fix" and content:
                try:
                    quote = _quote_problems(content, meta, session_files)
                except Exception as exc:  # j.w.
                    print(tr(f"  [VERIFY] kontrola cytatów pominięta z powodu błędu: {exc!r}",
                             f"  [VERIFY] quote check skipped because of an error: {exc!r}"), flush=True)
                    quote = []
                if quote:
                    print(tr("  [VERIFY] do poprawki: ", "  [VERIFY] to fix: ") + "; ".join(quote), flush=True)
                refs, seen_n, bad_n = _line_ref_stats(content, meta)
                if refs:
                    print(tr(f"  [LINIE] odwołań do numerów linii: {refs}; numerów z widoków w rozmowie: {seen_n}; "
                             f"niepotwierdzonych: {bad_n}",
                             f"  [LINES] line number references: {refs}; numbers from views in the conversation: {seen_n}; "
                             f"unconfirmed: {bad_n}"), flush=True)
            api_fixable = API_CHECK_MODE == "fix" and bool(problems or syntax)
            # Od 2.0.3: po zgłoszonym błędzie kompilacji odpowiedź bez bloku kodu (sam opis poprawki) to też problem.
            need_code = bool(meta.get("compile_turn")) and content and "```" not in content
            if need_code:
                quote = quote + [NEED_CODE_MARK]
                print(tr("  [KOD] po błędzie kompilacji brak poprawionego kodu w odpowiedzi",
                         "  [CODE] no corrected code in the answer after a compile error"), flush=True)
            if (api_fixable or quote) and api_fix_rounds < 1 and count < MAX_TOOL_CALLS:
                api_fix_rounds += 1
                phase(tr("Sprawdzam nazwy API i cytaty w odpowiedzi", "Checking API names and quotes in the answer"))
                quote_only = [q for q in quote if q != NEED_CODE_MARK]
                parts = ([HINT_API_FIX.format(problems="; ".join(problems))] if api_fixable and problems else []) + (
                    meta.pop("enum_notes", [])) + (
                    [HINT_SYNTAX_FIX.format(problems="; ".join(syntax))] if api_fixable and syntax else []) + (
                    [HINT_QUOTE_FIX.format(problems="; ".join(quote_only))] if quote_only else []) + (
                    [HINT_COMPILE_FULL_CODE] if need_code else []) + (
                    [kb_hint] if kb_hint else [])
                first_draft = first_draft or (content, problems, syntax, quote)
                reason = " + ".join(r for r, on in ((tr("kontrola API", "API check"), api_fixable),
                                                    (tr("cytaty", "quotes"), bool(quote_only)),
                                                    (tr("brak kodu", "missing code"), bool(need_code)),
                                                    (tr("wiedza", "knowledge"), bool(kb_hint))) if on)
                _push_draft(messages, content, "\n\n".join(parts), reason)
                continue          # szkic odrzucony: model poprawia go, widząc go w kontekście tury
            if api_fix_rounds and not (problems or syntax or quote):
                print(tr("  [API] po rundzie poprawkowej wszystkie nazwy i cytaty potwierdzone",
                         "  [API] after the fix round all names and quotes are confirmed"), flush=True)
            if kb_hint:
                phase(tr("Porównuję kod z wzorcami z bazy wiedzy", "Comparing the code with knowledge base patterns"))
                first_draft = first_draft or (content, problems, syntax, quote)
                _push_draft(messages, content, kb_hint, tr("wiedza przed kodem", "knowledge before code"))
                continue              # szkic odrzucony: model porówna go ze wzorcami i odpowie od nowa
            if first_draft is not None and (API_CHECK_MODE != "off" or VERIFY_MODE == "fix"):
                now, before = len(problems) + len(syntax) + len(quote), sum(len(x) for x in first_draft[1:])
                if now > before:
                    # Od 1.8.3: poprawka nie może pogorszyć odpowiedzi (A2: dobry szkic zastąpiony gorszym).
                    print(tr(f"  [SZKIC] poprawiona wersja ma więcej problemów ({now} > {before}) - zostaje pierwszy szkic",
                             f"  [DRAFT] the fixed version has more problems ({now} > {before}) - the first draft stays"),
                          flush=True)
                    content, problems, syntax, quote = first_draft
            if API_CHECK_MODE == "fix" and (problems or syntax):
                api_footer = (_api_footer(problems) if problems else "") + (
                    FOOTER_SYNTAX.format(problems="; ".join(syntax)) if syntax else "")
            messages.append({"role": "assistant", "content": content})
            compact_finished_history(messages)
            phase(tr("Odpowiedź gotowa", "Answer ready"))
            return (content or tr("[Model nie zwrócił odpowiedzi tekstowej]", "[The model returned no text answer]")) + api_footer

        # Od 1.8.8: seria rund bez nowych danych kończy wyszukiwanie dopiero, gdy model wykorzystał już część limitu
        # (test G: stop po 4 wywołaniach, zanim model trafił na właściwy plik) albo zastój trwa naprawdę długo.
        stalled = failed_rounds >= STALL_STOP_ROUNDS and (count >= STALL_STOP_MIN_CALLS
                                                          or failed_rounds >= STALL_STOP_ROUNDS_HARD)
        if stalled or tool_rounds > MAX_TOOL_CALLS + 6:
            stop_cause = (tr("seria rund bez nowych danych", "series of rounds without new data") if stalled
                          else tr("limit rund narzędzi", "tool round limit"))
            # GPT-OSS bywa skłonny zwrócić tool_calls nawet gdy API nie przekazało
            # narzędzi. Zamiast kończyć pustym błędem: osobna synteza ze źródeł.
            print(tr(f"  [OLLAMA] Zatrzymano dalsze wywołania ({stop_cause}); odpowiedź bez narzędzi w tej rozmowie.",
                     f"  [OLLAMA] Further calls stopped ({stop_cause}); answer without tools in this conversation."), flush=True)
            return _finish_without_tools(question, messages, model, num_ctx, stop_cause,
                                         HINT_FINAL_NO_TOOLS.format(cause=stop_cause), (None, "low"), True,
                                         meta, session_files, mcp, phase)

        # Ollama wymaga dopisania assistant/tool_calls przed wynikami narzedzi.
        _trim_thinking(assistant)
        messages.append(assistant)
        successful_tool = False
        for call in calls:
            fn = call.get("function") or {}
            orig_name = fn.get("name", "")
            name = orig_name
            arguments = fn.get("arguments", {})
            new_signature = None
            try:
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if not isinstance(arguments, dict):
                    raise ValueError(tr("Argumenty nie są obiektem JSON", "Arguments are not a JSON object"))
                # Lokalny widok pliku (query / zakres linii): wycinamy te parametry PRZED naprawą,
                # bo game_read w BK ich nie ma, a model prosi o nie w każdej rundzie testów.
                view = None
                content_search = None
                if str(name or "").lower() in CONTENT_SEARCH_ALIASES:
                    # Od 1.8.4: modele wymyślają "szukaj w treści plików" (np. game_search).
                    path_arg = str(arguments.get("path") or arguments.get("file") or "")
                    text_arg = next((arguments[k] for k in ("query", "pattern", "text", "search") if arguments.get(k)), "")
                    if re.search(r"\.\w{1,6}$", path_arg) and text_arg:
                        content_search = tr(f"'{name}' nie istnieje -> game_read z query (szukanie w tym pliku)",
                                            f"'{name}' does not exist -> game_read with query (search in this file)")
                        name, arguments = "game_read", {"path": path_arg, "query": text_arg}
                    else:
                        content_search = TOOL_CONTENT_SEARCH.format(name=name)
                if str(name or "").lower() in GAME_READ_ALIASES:
                    arguments, view = _extract_view_spec(arguments)
                # Naprawa PRZED limitem i dedupe: halucynowane nazwy (search/open...),
                # nieznane argumenty, typy i limity wg prawdziwego schematu z tools/list.
                model_title = arguments.get("title") if isinstance(arguments, dict) else None
                fixed_name, fixed_args, notes = repair_tool_call(name, arguments, mcp.tools)
                if content_search and name != "game_read":
                    fixed_name, notes = None, [content_search]
                elif content_search:
                    notes.insert(0, content_search)
                class_hint = None
                if fixed_name == "api_search" and isinstance(fixed_args.get("query"), str):
                    m = API_CLASS_METHOD_QUERY_RE.match(fixed_args["query"])
                    if m:
                        first, second = m.groups()
                        old_query = fixed_args["query"]
                        if first.lower() in API_QUERY_KEYWORDS:
                            fixed_args["query"] = second
                        elif (second[0].isupper() and (first[0].isupper() or first in API_QUERY_BUILTIN_TYPES)
                              and str(fixed_args.get("type", "any")).lower() in ("method", "any", "property")):
                            fixed_args["query"] = second
                            class_hint = first
                        if fixed_args["query"] != old_query:
                            notes.append(API_QUERY_REWRITTEN.format(old=old_query, new=fixed_args["query"]))
                if fixed_name in TOOL_DROP_ARGS:
                    for dropped in TOOL_DROP_ARGS[fixed_name]:
                        fixed_args.pop(dropped, None)
                if fixed_name in TOOL_ACTION_LIMITS and fixed_args.get("action") not in TOOL_ACTION_LIMITS[fixed_name]:
                    notes = [TOOL_ACTION_BLOCKED.format(action=fixed_args.get("action"), tool=fixed_name,
                                                        allowed=", ".join(TOOL_ACTION_LIMITS[fixed_name]))]
                    fixed_name = None         # bez wywołania MCP: tylko odczyt
                if fixed_name == "wb_knowledge":
                    wanted = fixed_args.get("max_files", 2)
                    if not isinstance(wanted, (int, float)) or wanted > WB_KNOWLEDGE_MAX_FILES:
                        notes.append(f"max_files {wanted} -> {WB_KNOWLEDGE_MAX_FILES}")
                        fixed_args["max_files"] = WB_KNOWLEDGE_MAX_FILES
                if fixed_name == "game_browse" and isinstance(fixed_args.get("pattern"), str):
                    pattern = fixed_args["pattern"].strip()
                    if pattern in GAME_BROWSE_ANY_PATTERNS or not pattern:
                        fixed_args.pop("pattern")
                        notes.append(tr(f"pattern {pattern!r} usunięty (bez filtra)", f"pattern {pattern!r} removed (no filter)"))
                    elif not re.fullmatch(GAME_BROWSE_PATTERN_RE, pattern):
                        # Od 1.8.3: w BK pattern to tylko filtr rozszerzenia; inny wzorzec zwraca same katalogi.
                        frag = re.sub(r"[*?()]|\.c$", "", pattern).strip(". ") or pattern
                        notes = [TOOL_BROWSE_PATTERN.format(pattern=pattern, frag=frag)]
                        fixed_name = None
                if fixed_name == "asset_search" and re.search(ASSET_QUERY_CODE_RE, str(fixed_args.get("query", ""))):
                    notes = [TOOL_ASSET_CODE_QUERY.format(query=fixed_args.get("query", ""))]
                    fixed_name = None
                if fixed_name is None:
                    # Błąd modelu, nie wyszukiwanie: nie wołamy MCP i nie liczymy do limitu.
                    response = ERROR_PREFIX + ": " + "; ".join(notes) + "\n" + tool_schema_hint(mcp.tools, name)
                    print(tr(f"  [REPAIR] odrzucono {orig_name}: {'; '.join(notes)}",
                             f"  [REPAIR] rejected {orig_name}: {'; '.join(notes)}"), flush=True)
                else:
                    name, arguments = fixed_name, fixed_args
                    if name == "api_search":
                        q = str(arguments.get("query") or "").strip()
                        if (str(arguments.get("type", "any")).lower() in ("class", "any")
                                and re.fullmatch(API_EXACT_CLASS_RE, q) and _class_result(mcp, q)):
                            # Od 1.8.3: przy kilku wynikach BK pokazuje tylko 10 metod klasy i bez dziedziczonych
                            # (test D: model "dopełnił" brakujące metody wymysłami). Dokładna klasa = pełny widok.
                            if arguments.get("limit") != 1 or arguments.get("type") != "class":
                                notes.append(API_EXACT_CLASS_NOTE.format(name=q))
                            arguments = {"query": q, "type": "class", "limit": 1}
                        else:
                            cap = (SOFT_LIMIT_CLASS_SEARCH if arguments.get("type", "any") in ("class", "any")
                                   else SOFT_LIMIT_OTHER_SEARCH)
                            wanted = arguments.get("limit", 10)
                            if not isinstance(wanted, (int, float)) or wanted > cap:
                                notes.append(tr(f"limit {wanted} -> {cap} (wyniki klas są bardzo długie)",
                                                f"limit {wanted} -> {cap} (class results are very long)"))
                                arguments["limit"] = cap
                            elif "limit" not in arguments:
                                arguments["limit"] = cap
                    if notes:
                        print(f"  [REPAIR] {orig_name}: {'; '.join(notes)}", flush=True)
                    if name != "game_read":
                        view = None
                    base_signature = json.dumps([name, arguments], sort_keys=True, ensure_ascii=False)
                    signature = (json.dumps([name, arguments, view], sort_keys=True, ensure_ascii=False)
                                 if view else base_signature)
                    if signature in seen_calls:
                        dup_counts[signature] = dup_counts.get(signature, 0) + 1
                        cached = results_cache.get(signature)
                        held = result_msgs.get(signature)
                        intact = bool(held is not None and cached is not None
                                      and str(held.get("content", "")).startswith(cached))
                        ledger = _ledger(read_paths, searches, misses)
                        if cached is not None and not intact and dup_counts[signature] <= 2:
                            # Wynik został skrócony w kontekście - oddajemy pełny z pamięci.
                            print(f"  [DUP] {name} {json.dumps(arguments, ensure_ascii=False)} -> "
                                  + tr("pełny wynik z pamięci", "full result from memory"), flush=True)
                            response = tr("[powtórzony odczyt - pełny wynik z pamięci podręcznej]\n",
                                          "[repeated read - full result from the cache]\n") + cached
                        elif intact and dup_counts[signature] <= 1:
                            print(f"  [DUP] {name} {json.dumps(arguments, ensure_ascii=False)} -> "
                                  + tr("wynik już w kontekście", "result already in context"), flush=True)
                            response = TOOL_DUP_IN_CONTEXT.format(ledger=ledger)
                        else:
                            print(f"  [DUP] {name} {json.dumps(arguments, ensure_ascii=False)} -> "
                                  + tr(f"zablokowano (powtórka nr {dup_counts[signature]})",
                                       f"blocked (repeat no. {dup_counts[signature]})"), flush=True)
                            response = TOOL_DUP_BLOCKED.format(ledger=ledger)
                    elif view and base_signature in full_cache:
                        # Plik już pobrany w tej turze: widok liczymy lokalnie, bez wywołania MCP i bez zużycia limitu.
                        seen_calls.add(signature)
                        vkey = _path_key(arguments.get("path"))
                        view_counts[vkey] = view_counts.get(vkey, 0) + 1
                        if view_counts[vkey] > VIEW_LIMIT_PER_FILE:
                            print(f"  [VIEW] {arguments.get('path', '')} -> "
                                  + tr(f"limit {VIEW_LIMIT_PER_FILE} widoków tego pliku", f"limit of {VIEW_LIMIT_PER_FILE} views of this file"),
                                  flush=True)
                            response = TOOL_VIEW_LIMIT.format(limit=VIEW_LIMIT_PER_FILE, ledger=_ledger(read_paths, searches, misses))
                        else:
                            response, view_found = _render_view(full_cache[base_signature], view)
                            _record_view_lines(meta, response, arguments.get("path"))
                            print(tr(f"  [VIEW] {arguments.get('path', '')} {_view_label(view)} -> {len(response)} zn. "
                                     f"({'trafienia' if view_found else 'BEZ trafień'}; z pamięci, bez wywołania MCP)",
                                     f"  [VIEW] {arguments.get('path', '')} {_view_label(view)} -> {len(response)} chars "
                                     f"({'matches' if view_found else 'NO matches'}; from memory, without an MCP call)"), flush=True)
                            if view_found:
                                successful_tool = True
                            else:
                                misses.append(f"{arguments.get('path', '')}: {_view_label(view)}")
                            results_cache[signature] = response
                            new_signature = signature
                            read_paths.append(f"{arguments.get('path', '')} [{_view_label(view)}]")
                        if notes:
                            response += CALL_FIX_NOTE + "; ".join(notes) + "]"
                    elif count >= MAX_TOOL_CALLS:
                        response = TOOL_MCP_LIMIT
                    else:
                        seen_calls.add(signature)
                        count += 1
                        print(f"  [MCP {count}/{MAX_TOOL_CALLS}] {name} {json.dumps(arguments, ensure_ascii=False)}"
                              + (tr(" + widok ", " + view ") + _view_label(view) if view else ""), flush=True)
                        phase(f"MCP · {name} ({count}/{MAX_TOOL_CALLS})")
                        result = mcp.call_tool(name, arguments)
                        is_error = bool(result.get("isError"))
                        raw = _raw_text(result)
                        if (name == "wiki_read" and not is_error and _is_wiki_miss(raw)
                                and isinstance(model_title, str) and model_title.strip()
                                and model_title != arguments.get("title")):
                            # Znormalizowany tytuł nie istnieje: próbujemy raz tytułu dokładnie takiego, jak podał model.
                            second = mcp.call_tool(name, {**arguments, "title": model_title})
                            if not second.get("isError") and not _is_wiki_miss(_raw_text(second)):
                                result, raw = second, _raw_text(second)
                                notes.append(tr(f"użyto tytułu z wywołania modelu: {model_title!r}",
                                                f"used the title from the model's call: {model_title!r}"))
                                print(tr(f"  [REPAIR] wiki_read: znormalizowany tytuł nie istnieje; użyto {model_title!r}",
                                         f"  [REPAIR] wiki_read: the normalized title does not exist; used {model_title!r}"), flush=True)
                        if not is_error:
                            _add_evidence(meta, raw)
                            if name == "wb_knowledge":
                                meta["kb_this_turn"] = True
                        view_found = True
                        if name == "game_read" and not is_error:
                            full_cache[base_signature] = raw
                            session_files[_path_key(arguments.get("path"))] = raw
                            while len(session_files) > _SESSION_FILE_CAP:
                                session_files.pop(next(iter(session_files)))
                            if view:
                                view_counts[_path_key(arguments.get("path"))] = 1
                        if view and not is_error:
                            response, view_found = _render_view(raw, view)
                            _record_view_lines(meta, response, arguments.get("path"))
                        else:
                            response = tool_text(result, name, arguments)
                            if name == "game_read" and not is_error and len(raw) > MAX_TOOL_RESULT_CHARS:
                                response += TOOL_FILE_SHORTENED.format(chars=len(raw))
                        if is_error:
                            # Wyjaśnij walidację z rzeczywistego schematu BK.
                            response += "\n" + tool_schema_hint(mcp.tools, name)
                            if name == "game_read":
                                response += _suggest_paths(mcp, str(arguments.get("path", "")))
                        else:
                            # Trafienie negatywne (api_search tylko podobne nazwy, asset_search "No assets found",
                            # widok bez dopasowań) nie jest nową informacją: nie zeruje licznika zastoju.
                            negative = ((name == "api_search" and response.startswith(("[BRAK DOKŁADNEGO TRAFIENIA", "[NO EXACT MATCH")))
                                        or (name == "asset_search" and raw.lstrip().lower().startswith("no assets found"))
                                        or (name == "wiki_read" and _is_wiki_miss(raw))
                                        or (view is not None and not view_found))
                            if negative and name == "wiki_read":
                                response += WIKI_TITLE_HINT
                            if negative:
                                misses.append(f"{name}({arguments.get('query', arguments.get('path', arguments.get('title', '')))})"
                                              + (f" {_view_label(view)}" if view else ""))
                            else:
                                successful_tool = True
                            results_cache[signature] = response
                            new_signature = signature
                            if name == "game_read":
                                read_paths.append(str(arguments.get("path", ""))
                                                  + (f" [{_view_label(view)}]" if view else ""))
                            else:
                                searches.append(f"{name}({arguments.get('query', arguments.get('path', ''))})")
                        gq = re.sub(r"[\s(\"'`]+", "", str(arguments.get("query") or "")) if name in ("api_search", "wiki_search") else ""
                        if gq in GLOBAL_FUNCTION_FILES and not is_error:
                            try:
                                gpath, gdecl, gtext = _global_decl(mcp, gq)
                            except Exception as exc:  # uzupełnienie nigdy nie psuje tury
                                print(tr(f"  [GLOBALNA] pominięte z powodu błędu: {exc!r}",
                                         f"  [GLOBAL] skipped because of an error: {exc!r}"), flush=True)
                                gpath = ""
                            if gpath:
                                response += NOTE_GLOBAL_DECL.format(name=gq, path=gpath, decl=gdecl)
                                session_files[_path_key(gpath)] = gtext      # cytat z tego pliku przejdzie weryfikację
                                _add_evidence(meta, gtext)
                                successful_tool = True
                        if name == "api_search" and not is_error:
                            try:
                                parents = _parents_note(mcp, meta, arguments.get("query"), raw)
                            except Exception as exc:  # uzupełnienie nigdy nie psuje tury
                                print(tr(f"  [BAZA] uzupełnienie pominięte z powodu błędu: {exc!r}",
                                         f"  [BASE] addition skipped because of an error: {exc!r}"), flush=True)
                                parents = ""
                            if parents:
                                response += parents
                                successful_tool = True
                            elif _is_negative_result(response) or response.lstrip().startswith(("[BRAK DOKŁADNEGO", "[NO EXACT MATCH")):
                                try:
                                    miss = _search_miss_file_note(mcp, arguments.get("query"))
                                except Exception as exc:  # j.w.
                                    print(tr(f"  [PLIK] sprawdzenie pliku pominięte z powodu błędu: {exc!r}",
                                             f"  [FILE] file check skipped because of an error: {exc!r}"), flush=True)
                                    miss = ""
                                if (not miss and re.fullmatch(r"[A-Z][A-Za-z0-9_]{2,}", _norm_query(arguments.get("query")))
                                        and str(arguments.get("type", "any")).lower() != "method"
                                        and not re.match(r"(?:Get|Set|Is|Has|Can|On|Try|Add|Remove)[A-Z]",
                                                         _norm_query(arguments.get("query")))):
                                    try:      # od 2.0.3: enum spoza indeksu BK - deklaracja z pliku klasy, która go używa
                                        epath, edecl = _resolve_enum(mcp, meta, session_files, _norm_query(arguments.get("query")))
                                    except Exception as exc:  # j.w.
                                        print(f"  [ENUM] {exc!r}", flush=True)
                                        epath = edecl = ""
                                    if epath:
                                        miss = NOTE_ENUM_DECL.format(name=_norm_query(arguments.get("query")), path=epath, decl=edecl)
                                if miss:
                                    response += miss
                                    successful_tool = True
                        print(f"  -> {ERROR_PREFIX if is_error else 'ok'} {len(response)} " + tr("zn.", "chars"), flush=True)
                        if class_hint and not is_error:
                            method = arguments.get("query", "")
                            owners = list(dict.fromkeys(re.findall(rf"^\s*\d+\.\s*(\w+)\.[^\n]*\b{re.escape(method)}\s*\(", raw, re.M)))
                            if class_hint in owners:
                                notes.append(API_CLASS_SEEN.format(method=method, cls=class_hint))
                            elif owners:
                                notes.append(API_CLASS_NOT_SEEN.format(method=method, owners=", ".join(owners[:5]), cls=class_hint))
                        if notes:
                            response += CALL_FIX_NOTE + "; ".join(notes) + "]"
            except (MCPError, ValueError, TypeError, json.JSONDecodeError) as exc:
                response = tr("BŁĄD NARZĘDZIA: ", "TOOL ERROR: ") + str(exc)
                # Przy nieistniejącej nazwie / złym schemacie daj modelowi
                # dokładne dane z tools/list, zamiast dopisywać wyjątki do promptu.
                if (name not in mcp.tools or any(m in str(exc) for m in (
                        "Niepoprawne argumenty", "Invalid arguments", "Argumenty nie są obiektem JSON",
                        "Arguments are not a JSON object"))):
                    response += "\n" + tool_schema_hint(mcp.tools, name)
                print("  " + response[:1300], flush=True)
            tool_msg = {"role": "tool", "tool_name": orig_name, "content": response}
            messages.append(tool_msg)
            if new_signature is not None:
                result_msgs[new_signature] = tool_msg
            _compact_tool_context(messages)
        failed_rounds = 0 if successful_tool else failed_rounds + 1
        if count >= BUDGET_HINT_AT and not meta.get("budget_hint") and count < MAX_TOOL_CALLS:
            # Od 2.0.3: jednorazowe przypomnienie o limicie (test "popraw skrypt": 25 wywołań bez odczytu głównego pliku).
            meta["budget_hint"] = True
            print(tr(f"  [LIMIT] {count}/{MAX_TOOL_CALLS} wywołań MCP - przypomnienie o limicie",
                     f"  [LIMIT] {count}/{MAX_TOOL_CALLS} MCP calls - limit reminder"), flush=True)
            if pending_hint is None:
                pending_hint = {"role": "user", "content": HINT_BUDGET.format(
                    used=count, limit=MAX_TOOL_CALLS, ledger=_ledger(read_paths, searches, misses))}
        if failed_rounds == 2 or (failed_rounds >= STALL_STOP_ROUNDS and failed_rounds % 2 == 0):
            # Przełamanie zastoju: rundy bez nowych danych. Jednorazowa podpowiedź (nie trafia do historii).
            print(tr(f"  [STALL] {failed_rounds} rundy bez nowych danych - podpowiedź z rejestrem",
                     f"  [STALL] {failed_rounds} rounds without new data - hint with the ledger"), flush=True)
            pending_hint = {"role": "user", "content": HINT_STALL.format(ledger=_ledger(read_paths, searches, misses))}
        if count >= MAX_TOOL_CALLS:
            # Nie zostawiaj w historii trwałego systemowego zakazu narzędzi!
            # Wcześniej taka wiadomość mogła zatruwać następną turę rozmowy.
            print(tr("  [OLLAMA] Limit MCP - odpowiedź bez narzędzi w tej rozmowie.",
                     "  [OLLAMA] MCP limit - answer without tools in this conversation."), flush=True)
            cause = tr(f"limit {MAX_TOOL_CALLS} wywołań MCP", f"limit of {MAX_TOOL_CALLS} MCP calls")
            return _finish_without_tools(question, messages, model, num_ctx, cause,
                                         HINT_FINAL_NO_TOOLS.format(cause=cause), (None, "low"), True,
                                         meta, session_files, mcp, phase)


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Reforger Assistant {VERSION} — " + tr("bez OpenCode", "without OpenCode"))
    parser.add_argument("--check", action="store_true", help=tr("tylko sprawdź połączenie i listę narzędzi MCP",
                                                                "only check the connection and the MCP tool list"))
    parser.add_argument("--model", default=MODEL, help=tr("nazwa modelu Ollama", "Ollama model name"))
    parser.add_argument("--num-ctx", type=int, default=NUM_CTX, help=tr("rozmiar kontekstu Ollama", "Ollama context size"))
    args = parser.parse_args()

    print(f"REFORGER ASSISTANT {VERSION}")
    print("Ollama:", args.model, tr("| MCP BK: bez OpenCode | tryb: tylko odczyt", "| MCP BK: without OpenCode | mode: read-only"))
    print(tr("Brak skanowania .c, lokalnego indeksu lub ekstrakcji .pak przez Pythona.",
             "No .c scanning, local index or .pak extraction by Python."))
    try:
        with MCPStdioClient() as mcp:
            print(tr("Połączono z Enfusion MCP BK.", "Connected to Enfusion MCP BK."))
            print(tr("Narzędzia:", "Tools:"), ", ".join(mcp.tools))
            if args.check:
                return 0
            print(tr("Komendy: exit / quit — koniec; /reset — nowa rozmowa.", "Commands: exit / quit - end; /reset - new conversation."))
            messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
            while True:
                try:
                    question = input(tr("\nTy: ", "\nYou: ")).strip()
                except (EOFError, KeyboardInterrupt):
                    print(tr("\nDo zobaczenia!", "\nSee you!"))
                    break
                if question.lower() in ("exit", "quit", "koniec"):
                    break
                if question.lower() == "/reset":
                    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                    print(tr("Historia rozmowy wyczyszczona (bez modyfikacji plików).", "Conversation history cleared (no files modified)."))
                    continue
                if not question:
                    continue
                try:
                    answer = ask(question, messages, mcp, args.model, args.num_ctx)
                    print(tr("\nAsystent:\n", "\nAssistant:\n") + answer)
                except (RuntimeError, MCPError) as exc:
                    print(ERROR_PREFIX + ":", exc)
                    # Po błędzie modelu nie zostawiamy w historii urwanej tury.
                    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                    print(tr("Historia tej sesji została zresetowana po błędzie.", "This session's history was reset after the error."))
    except (MCPError, OSError) as exc:
        print(tr("Nie udało się uruchomić MCP:", "Could not start MCP:"), exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
