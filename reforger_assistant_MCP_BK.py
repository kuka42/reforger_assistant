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

try:
    from reforger_helpers import repair_tool_call, slim_tool_definitions, digest_enforce
except ImportError as _exc:  # jasny komunikat zamiast tracebacku
    raise SystemExit("Brak pliku reforger_helpers.py obok tego pliku: " + str(_exc))

# Moduły projektu (od 1.7.0). Nazwy są importowane jawnie do przestrzeni silnika, więc wszystko,
# co było dostępne jako reforger_assistant_MCP_BK.X (serwer WEB, testy), działa bez zmian.
try:
    from reforger_config import (  # noqa: F401
        KB_CHECK_MODE,
        VERSION,
        MCP_SCRIPT,
        GAME_PATH,
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
        THINKING_KEEP_CHARS,
        VIEW_LIMIT_PER_FILE,
        VERIFY_MODE,
        API_CHECK_MODE,
        EMERGENCY_IN_HISTORY,
        config_summary,
    )
    from reforger_prompts import (  # noqa: F401
        HINT_KB_CHECK,
        HINT_COMPILE_LINES,
        COMPILE_LINE_FOUND,
        COMPILE_LINE_FINDINGS,
        COMPILE_LINE_MISSING,
        COMPILE_KB,
        COMPILE_PROJECT,
        HINT_SYNTAX_FIX,
        FOOTER_SYNTAX,
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
    )
    from reforger_mcp import (  # noqa: F401
        MCPError,
        MCPStdioClient,
        ollama_tool_definitions,
        tool_schema_hint,
        _raw_text,
    )
except ImportError as _exc:
    raise SystemExit("Brak pliku modułu asystenta obok reforger_assistant_MCP_BK.py: " + str(_exc))


print(config_summary(), flush=True)


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
            item["content"] = text[:200] + "\n[... wynik wyszukiwania skrócony po zakończeniu tury ...]"
    _compact_tool_context(messages, limit=FINISHED_EVIDENCE_CHARS)
    prune_history(messages)


def _excerpt(value: str, size: int) -> str:
    """Jawnie oznaczony fragment wyniku; nie udaje pelnego pliku."""
    if len(value) <= size:
        return value
    marker = "\n[... ŚRODKOWA CZĘŚĆ WYNIKU POMINIĘTA Z POWODU LIMITU KONTEKSTU ...]\n"
    available = max(100, size - len(marker))
    head = max(50, int(available * 0.75))
    return value[:head] + marker + value[-(available - head):]


def _strip_note(text: str) -> str:
    """Skrócony wynik zaczyna się linią '[SKRÓT...]'; kolejne skracanie i klasyfikacja
    muszą ją pomijać, inaczej wynik przestaje wyglądać jak plik i traci strukturę."""
    if text.startswith("[SKRÓT"):
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
                out.append(f"   [... {len(block) - 2} linii komponentu pominięto ...]")
                out.append("  }")
            i = j + 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _shrink(text: str, size: int) -> str:
    """Skraca wynik do ~size znaków. Kod .c: zostają WSZYSTKIE deklaracje.
    Reszta: jawnie oznaczony wyciąg (_excerpt)."""
    if len(text) <= size:
        return text
    body = _strip_note(text)
    if _looks_like_prefab(text):
        candidate = _digest_prefab(body)
        note = "[SKRÓT PREFABU: komponenty poza ActionsManagerComponent zwinięte do nagłówków]\n"
        if len(candidate) < len(body) or text.startswith("[SKRÓT PREFABU"):
            # Digest zachowuje blok ActionsManagerComponent w całości; tniemy go dopiero
            # przy naprawdę ogromnym bloku (powyżej max(size, 4200) znaków).
            cap = max(size, 4200)
            return note + (candidate if len(candidate) <= cap else _excerpt(candidate, cap))
    if _looks_like_enforce(text):
        note = "[SKRÓT: zachowano wszystkie deklaracje, pominięto ciała metod i część komentarzy]\n"
        for keep_docs in (True, False):
            candidate = digest_enforce(body, keep_docs=keep_docs)
            if len(candidate) <= size:
                return note + candidate
        return note + _excerpt(digest_enforce(body, keep_docs=False), size)
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
        parts.append("Przeczytane pliki: " + "; ".join(read_paths[-12:]) + ".")
    if searches:
        parts.append("Wykonane wyszukiwania: " + "; ".join(searches[-12:]) + ".")
    if misses:
        parts.append("Szukano BEZ trafienia: " + "; ".join(misses[-10:]) + ".")
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
    return f"linie {view.get('start', 1)}-{view.get('end', '...')}"


def _body_lines(raw: str):
    """Linie pliku BEZ trzylinijkowego nagłówka dopisywanego przez game_read (ścieżka, rozmiar, pusta linia).
    Dzięki temu numery w widoku odpowiadają numerom w pliku."""
    lines = raw.split("\n")
    if (len(lines) >= 3 and lines[0].startswith("//") and "(from .pak)" in lines[0]
            and lines[1].startswith("//") and "bytes" in lines[1] and lines[2].strip() == ""):
        return lines[3:], 3
    return lines, 0


def _render_view(raw: str, view: dict):
    """Widok liczony lokalnie na PEŁNYM tekście pliku z game_read (nie na skróconym).
    Zwraca (tekst, znaleziono). znaleziono=False oznacza brak dopasowań (brak nowej informacji)."""
    lines, _offset = _body_lines(raw)
    total = len(lines)
    head = (f"[Widok lokalny pliku: {total} linii, {len(raw)} znaków. Numeracja = linie pliku "
            "(bez nagłówka dopisywanego przez game_read).]")
    if "query" in view:
        q = view["query"]
        try:
            pattern = re.compile(q, re.I)
        except re.error:
            pattern = None
        hits = [i for i, line in enumerate(lines)
                if q.lower() in line.lower() or (pattern and pattern.search(line))]
        if not hits:
            return (f"{head}\nBrak dopasowań dla '{q}' w CAŁYM pliku (przeszukano wszystkie {total} linii). "
                    "Tego tekstu w tym pliku NIE ma. Nie zgaduj kolejnych nazw: zmień strategię "
                    "(api_search z type=method, wiki_search) albo napisz, że nie znaleziono."), False
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
                out.append("... (kolejne dopasowania pominięte; zawęź query)")
                break
            take = min(hi - lo + 1, VIEW_MAX_LINES - used)
            out.append("\n".join(f"{n + 1}| {lines[n]}" for n in range(lo, lo + take)))
            used += take
            if lo + take <= hi:
                out.append("... (przycięto)")
        return f"{head}\nDopasowań dla '{q}': {len(hits)} linii.\n" + "\n...\n".join(out), True
    start = max(1, view.get("start", 1))
    end = min(total, view.get("end", start + 199))
    if end < start:
        end = start
    if end - start + 1 > VIEW_MAX_LINES + 90:
        end = start + VIEW_MAX_LINES + 89
    end = min(end, total)
    if start > total:
        return f"{head}\nPlik ma tylko {total} linii; zakres zaczyna się za końcem.", False
    body = "\n".join(f"{n}| {lines[n - 1]}" for n in range(start, end + 1))
    more = f"\n... (plik ma jeszcze {total - end} linii)" if end < total else ""
    return f"{head}\nLinie {start}-{end}:\n{body}{more}", True


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
    return {"role": "assistant", "content": EMERGENCY_PLACEHOLDER}


def _compile_error_lookup(question: str, meta: dict, mcp, messages: list | None = None) -> dict | None:
    """Błąd kompilatora w pytaniu: zapamiętaj odrzucone nazwy i sprawdź je od razu w api_search.
    Zwraca jednorazową podpowiedź dla modelu albo None."""
    found = [s for s in dict.fromkeys(_COMPILE_ERR_RE.findall(question or "")) if s not in meta["banned"]]
    line_hint = _compile_line_hint(question, meta, mcp, messages)
    if not found:
        return {"role": "user", "content": line_hint} if line_hint else None
    parts = []
    for sym in found[:3]:
        meta["banned"].add(sym)
        meth = sym.replace("::", ".").split(".")[-1]
        if "api_search" not in getattr(mcp, "tools", {}):
            continue
        args = {"query": meth, "type": "method", "limit": 10}
        try:
            result = mcp.call_tool("api_search", args)
            raw = _raw_text(result)
            _add_evidence(meta, raw)
            parts.append(f"api_search('{meth}'):\n" + tool_text(result, "api_search", args)[:3000])
            print(f"  [API] błąd kompilatora: {sym} - automatyczne api_search('{meth}')", flush=True)
        except (MCPError, OSError, ValueError, TypeError) as exc:
            print(f"  [API] automatyczne sprawdzenie {sym} nieudane: {exc!r}", flush=True)
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
    for path, line, message in errors[:3]:
        hit = _code_line_excerpt(messages or [], path, line)
        print(f"  [KOD] błąd kompilatora: {path}({line}) - "
              + ("linia znaleziona w ostatnim kodzie" if hit else "linii nie ma w ostatnim kodzie"), flush=True)
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
            print(f"  [KOD] automatyczne wb_knowledge('{KB_PITFALLS_QUERY}'): {len(sections)} zn. sekcji o pułapkach", flush=True)
        except (MCPError, OSError, ValueError, TypeError) as exc:
            print(f"  [KOD] wb_knowledge nieudane: {exc!r}", flush=True)
    project = COMPILE_PROJECT if "project" in getattr(mcp, "tools", {}) else ""
    return HINT_COMPILE_LINES.format(errors="\n\n".join(blocks), kb=kb, project=project)


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
    proto_note = ("\n[W tej instalacji nie ma plików .proto: deklaracje API leżą w plikach .c "
                  "(scripts/Game/generated/...).]" if ext.lower() == "proto" else "")
    return (f"\n[Podpowiedź: wyniki asset_search dla '{stem}' - użyj jednej z tych ścieżek:]\n"
            + found[:1500] + proto_note)


def _is_source_result(text: str, tool_name: str = "") -> bool:
    """Odczyt pliku/wiki (wysoka wartość) vs. wynik wyszukiwania (niska wartość)."""
    first = _strip_note(text).split("\n", 1)[0]
    # Lokalny widok pliku (query / zakres linii) to też odczyt pliku, a nie wynik wyszukiwania.
    return ((first.startswith("//") and "(from .pak)" in first) or first.startswith("[Widok lokalny")
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
            return f"[Dokładne trafienie dla '{q}': {', '.join(uniq)}]"
        shown = list(dict.fromkeys(classes + [f"{o}.{n}" for o, n in methods]))[:3]
        method_like = (str((arguments or {}).get("type", "any")).lower() == "class"
                       and re.match(r"(Get|Set|Is|Has|Can|On|Try|Add|Remove)[A-Z]|[msg]_", q))
        tip = (" Wygląda to na nazwę metody lub pola, nie klasy: spróbuj api_search z type=method."
               if method_like else "")
        return (f"[BRAK DOKŁADNEGO TRAFIENIA dla '{q}'. Poniższe wyniki to tylko PODOBNE nazwy "
                f"({', '.join(shown)}). To NIE jest dowód, że '{q}' istnieje - nie opisuj go jako istniejącego.{tip}]")
    if name == "asset_search":
        paths = [m.group(1) for m in re.finditer(r"^\s{2,}(\S+/\S+)\s*$", text, re.M)]
        if not paths:
            return ""
        stem = re.sub(r"\.\w+$", "", q).lower()
        exact = [p for p in paths if re.sub(r"\.\w+$", "", p.rsplit("/", 1)[-1]).lower() == stem]
        if exact:
            return f"[Dokładne trafienie nazwy pliku: {exact[0]}]"
        return (f"[Brak pliku o nazwie dokładnie '{q}'. Poniżej pliki, których nazwa tylko ZAWIERA ten ciąg; "
                "to nie oznacza, że szukana klasa istnieje.]")
    return ""


def tool_text(result: dict, name: str = "", arguments: dict | None = None) -> str:
    content = _raw_text(result)
    if result.get("isError"):
        content = "BŁĄD NARZĘDZIA MCP:\n" + content
    if name == "api_search":
        content = _dedupe_api_result(content)
    if not result.get("isError"):
        note = _exact_match_note(name, arguments, content)
        if note:
            content = note + "\n" + content
    if len(content) > MAX_TOOL_RESULT_CHARS:
        content = _shrink(content, MAX_TOOL_RESULT_CHARS)
    return content


def ollama_chat(messages: list[dict], tools: list[dict], model: str, num_ctx: int, think: str | None = None) -> dict:
    payload = {"model": model, "messages": messages, "stream": False,
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
            parsed = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", "replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Ollama nie odpowiada ({OLLAMA_URL}): {exc}") from exc
    message = parsed.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Ollama nie zwróciła pola message")
    message = dict(message)
    # Metadane diagnostyczne nie sa przekazywane z powrotem do API Ollamy.
    message["_done_reason"] = parsed.get("done_reason", "")
    message["_prompt_eval_count"] = parsed.get("prompt_eval_count")
    message["_eval_count"] = parsed.get("eval_count")
    return message


def prune_history(messages: list[dict]) -> None:
    """Usuwaj tylko pełne zakończone tury, nigdy fragment wywołania narzędzia."""
    while len(messages) > MAX_HISTORY_MESSAGES:
        if len(messages) < 3:
            return
        next_user = next((i for i in range(2, len(messages))
                          if messages[i].get("role") == "user"), None)
        if next_user is None:
            return
        del messages[1:next_user]


def _synthesize_after_mcp_limit(question: str, messages: list[dict],
                                model: str, num_ctx: int,
                                cause: str = "limit wywolan MCP") -> str:
    """Nowa prosta rozmowa bez historii tool_calls i bez udostępniania narzędzi.

    Tu model ma odpowiedzieć na podstawie *już pobranych* rezultatów MCP,
    zamiast ponawiać wywołania. Błędy wywołań nie są traktowane jako dowody.
    """
    qpos = next((i for i in range(len(messages) - 1, -1, -1)
                 if messages[i].get("role") == "user"), 0)
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
            "BŁĄD:", "BŁĄD NARZĘDZIA", "BŁĄD NARZĘDZIA MCP:"))
    ]
    # Zachowujemy pierwsze i ostatnie źródła, bez forsowania nazwy konkretnej
    # mechaniki (paliwo, broń itd.). Wyrzucamy środkowe, gdy wyników jest dużo.
    selected = entries if len(entries) <= 12 else entries[:4] + entries[-8:]
    chunks = []
    remaining = 23000
    for item in selected:
        if remaining <= 0:
            break
        name = str(item.get("tool_name") or "MCP")
        content = item["content"]
        section = f"[{name}]\n" + _shrink(content, min(3500, remaining))
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
                print(f"  [OLLAMA] Synteza po limicie OK (próba {attempt + 1}).", flush=True)
                return content + SYNTH_FOOTER.format(cause=cause)
            print("  [OLLAMA] Synteza nie zwróciła kompletnego tekstu.", flush=True)
        except (RuntimeError, OSError) as exc:
            print(f"  [OLLAMA] Synteza nieudana: {exc}", flush=True)
        simple = simple[:1] + [{"role": "user", "content": SYNTH_SECOND_ATTEMPT + instructions[:14000]}]
    return SYNTH_FAILED.format(cause=cause)


def ask(question: str, messages: list[dict], mcp: MCPStdioClient,
        model: str, num_ctx: int, on_phase=None) -> str:
    """Jedna tura narzędzi MCP i odpowiedzi + weryfikator cytatów (tryb: REFORGER_VERIFY)."""
    answer = _ask_impl(question, messages, mcp, model, num_ctx, on_phase)
    if VERIFY_MODE == "off":
        return answer
    try:
        findings, checked, ok = _verify_answer(answer, _session_files(messages))
        _log_verification(findings, checked, ok)
        if VERIFY_MODE == "footer" and findings:
            answer += _verification_footer(findings)
    except Exception as exc:  # weryfikator nigdy nie może zepsuć odpowiedzi
        print(f"  [VERIFY] weryfikator pominięty z powodu błędu: {exc!r}", flush=True)
    return answer


def _ask_impl(question: str, messages: list[dict], mcp: MCPStdioClient,
              model: str, num_ctx: int, on_phase=None) -> str:
    """Jedna tura narzedzi MCP i odpowiedzi, z diagnostyka limitu Ollamy."""
    def phase(text: str) -> None:
        if on_phase:
            on_phase(text)

    messages.append({"role": "user", "content": question})
    turn_start = len(messages)           # tylko wyniki narzędzi PO tym punkcie należą do tej tury
    session_files = _session_files(messages)   # pełne teksty odczytanych plików (dla weryfikatora)
    view_counts: dict[str, int] = {}
    misses: list[str] = []
    meta = _session_meta(messages)       # wyniki narzędzi w sesji i nazwy odrzucone przez kompilator
    meta["kb_this_turn"] = False         # czy w tej turze ktoś (model albo silnik) sięgnął do wb_knowledge
    kb_rounds = 0
    api_fix_rounds = 0
    api_footer = ""
    pending_hint = None                  # jednorazowa podpowiedź do następnego wywołania (nie trafia do historii)
    if API_CHECK_MODE != "off":
        try:
            pending_hint = _compile_error_lookup(question, meta, mcp, messages)
        except Exception as exc:  # kontrola nigdy nie psuje tury
            print(f"  [API] sprawdzenie błędu kompilatora pominięte: {exc!r}", flush=True)
    empty_retries = 0
    empty_final_retries = 0              # ponowienia po pustej generacji PO użyciu narzędzi
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
        phase(f"Ollama analizuje wyniki · {count} wywołań MCP" if count else "Ollama szuka rozwiązania")
        # Wywołania są nadal ograniczane przez rzeczywiste schematy MCP.
        send = messages + ([pending_hint] if pending_hint else [])
        pending_hint = None
        assistant = ollama_chat(send, tools, model, num_ctx)
        done_reason = assistant.pop("_done_reason", "")
        prompt_tokens = assistant.pop("_prompt_eval_count", None)
        completion_tokens = assistant.pop("_eval_count", None)
        print(f"  [OLLAMA] reason={done_reason or '?'} context_tokens={prompt_tokens} output_tokens={completion_tokens}", flush=True)
        if prompt_tokens and prompt_tokens >= 0.9 * num_ctx:
            print(f"  [UWAGA] kontekst {prompt_tokens}/{num_ctx} tokenów - Ollama mogła uciąć prompt. "
                  "Zwiększ OLLAMA_NUM_CTX.", flush=True)
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
            turn_has_tools = any(m.get("role") == "tool" for m in messages[turn_start:])
            if not content and not turn_has_tools:
                # Pusta odpowiedź bez ani jednego odczytu w tej turze (np. nieudane parsowanie
                # tool_calls przez Ollamę). Ponów z podpowiedzią; NIE syntezuj z niczego.
                if empty_retries < 2:
                    empty_retries += 1
                    print(f"  [OLLAMA] Pusta odpowiedź bez użycia MCP w tej turze - ponowienie {empty_retries}/2", flush=True)
                    phase("Model zwrócił pustą odpowiedź - ponawiam")
                    pending_hint = {"role": "user", "content": HINT_EMPTY_NO_TOOLS}
                    continue
                content = MSG_EMPTY_TWICE
                messages.append({"role": "assistant", "content": content})
                compact_finished_history(messages)
                phase("Brak odpowiedzi modelu")
                return content
            if not content and turn_has_tools and empty_final_retries < 1:
                # Najczęściej: rozumowanie zjadło cały limit generacji (reason=length) albo model zwrócił
                # samo rozumowanie. Zamiast od razu syntezować z okrojonych dowodów, dajemy modelowi
                # PEŁNY kontekst tury, niskie rozumowanie i zakaz narzędzi: odpowiedź ma być z tego, co zebrał.
                empty_final_retries += 1
                print(f"  [OLLAMA] Pusty wynik po użyciu MCP (reason={done_reason or '?'}) - ponowienie z niskim "
                      "rozumowaniem, bez narzędzi", flush=True)
                phase("Model nie zwrócił tekstu - ponawiam z krótszym rozumowaniem")
                retry_hint = {"role": "user", "content": HINT_RETRY_AFTER_EMPTY}
                retry = None
                try:
                    retry = ollama_chat(messages + [retry_hint], [], model, num_ctx, think="low")
                except RuntimeError as exc:
                    print(f"  [OLLAMA] ponowienie nieudane ({exc}); przechodzę do syntezy", flush=True)
                if retry is not None:
                    r_reason = retry.pop("_done_reason", "")
                    retry.pop("_prompt_eval_count", None)
                    r_tokens = retry.pop("_eval_count", None)
                    print(f"  [OLLAMA] ponowienie: reason={r_reason or '?'} output_tokens={r_tokens}", flush=True)
                    r_content = str(retry.get("content") or "").strip()
                    if r_content and r_reason not in ("length", "max_tokens") and not _is_incomplete_answer(r_content):
                        messages.append({"role": "assistant", "content": r_content})
                        compact_finished_history(messages)
                        phase("Odpowiedź gotowa (ponowienie po pustej generacji)")
                        return r_content
                    print("  [OLLAMA] ponowienie bez pełnej odpowiedzi - synteza awaryjna", flush=True)
            if not content and turn_has_tools:
                print("  [OLLAMA] Pusty wynik po uzyciu MCP - osobna synteza z dowodow", flush=True)
                phase("Model nie zwrocil tekstu - przygotowanie podsumowania")
                content = _synthesize_after_mcp_limit(question, messages, model, num_ctx,
                                                       cause="pusta odpowiedz modelu")
                messages.append(_emergency_history_entry(content))
                compact_finished_history(messages)
                phase("Odpowiedz gotowa (podsumowanie zrodel)")
                return content
            needs_repair = (done_reason in ("length", "max_tokens") or _is_incomplete_answer(content))
            if needs_repair:
                print("  [OLLAMA] Odpowiedź niepełna / limit generowania — jedna próba ponownej syntezy.", flush=True)
                phase("Ollama dokańcza niepełną odpowiedź")
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
                        content = (content or "[Brak odpowiedzi]") + "\n\n" + NOTE_INCOMPLETE
                except (RuntimeError, MCPError, OSError) as exc:
                    print(f"  [OLLAMA] Ponowna synteza nieudana: {exc}", flush=True)
                    content = (content or "[Brak odpowiedzi]") + (
                        "\n\n[Uwaga: odpowiedź jest niepełna; ponowna próba się nie udała.]"
                    )
            api_footer = ""
            kb_hint = None
            if (KB_CHECK_MODE == "on" and content and kb_rounds < 1 and not meta.get("kb_this_turn")
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
                        print(f"  [KB] własny kod bez konsultacji z bazą - wb_knowledge('{kb_query}'): "
                              f"{', '.join(kb_files) or 'brak plików'}; {len(excerpt)} zn. wzorców", flush=True)
                        if excerpt:
                            kb_hint = HINT_KB_CHECK.format(query=kb_query, files=", ".join(kb_files) or "-", excerpt=excerpt)
                except Exception as exc:  # kontrola nigdy nie psuje odpowiedzi
                    print(f"  [KB] kontrola wzorców pominięta z powodu błędu: {exc!r}", flush=True)
            if API_CHECK_MODE != "off" and content:
                try:
                    problems = _api_problems(content, meta, session_files)
                except Exception as exc:  # kontrola nigdy nie psuje odpowiedzi
                    print(f"  [API] kontrola pominięta z powodu błędu: {exc!r}", flush=True)
                    problems = []
                try:
                    syntax = _syntax_problems(content)
                except Exception as exc:  # j.w.
                    print(f"  [KOD] kontrola składni pominięta z powodu błędu: {exc!r}", flush=True)
                    syntax = []
                if syntax:
                    print("  [KOD] niedozwolona składnia: " + "; ".join(syntax), flush=True)
                if problems or syntax:
                    if problems:
                        print("  [API] niepotwierdzone: " + "; ".join(problems), flush=True)
                    if API_CHECK_MODE == "fix" and api_fix_rounds < 1 and count < MAX_TOOL_CALLS:
                        api_fix_rounds += 1
                        phase("Sprawdzam nazwy API użyte w kodzie")
                        parts = ([HINT_API_FIX.format(problems="; ".join(problems))] if problems else []) + (
                            [HINT_SYNTAX_FIX.format(problems="; ".join(syntax))] if syntax else []) + (
                            [kb_hint] if kb_hint else [])
                        pending_hint = {"role": "user", "content": "\n\n".join(parts)}
                        continue          # szkic odrzucony: nie trafia do historii
                    if API_CHECK_MODE == "fix":
                        api_footer = (_api_footer(problems) if problems else "") + (
                            FOOTER_SYNTAX.format(problems="; ".join(syntax)) if syntax else "")
                elif api_fix_rounds:
                    print("  [API] po rundzie poprawkowej wszystkie nazwy potwierdzone", flush=True)
            if kb_hint:
                phase("Porównuję kod z wzorcami z bazy wiedzy")
                pending_hint = {"role": "user", "content": kb_hint}
                continue              # szkic odrzucony: model porówna go ze wzorcami i odpowie od nowa
            messages.append({"role": "assistant", "content": content})
            compact_finished_history(messages)
            phase("Odpowiedź gotowa")
            return (content or "[Model nie zwrócił odpowiedzi tekstowej]") + api_footer

        if failed_rounds >= 4 or tool_rounds > MAX_TOOL_CALLS + 6:
            stop_cause = ("seria rund bez nowych danych" if failed_rounds >= 4
                          else "limit rund narzędzi")
            # GPT-OSS bywa skłonny zwrócić tool_calls nawet gdy API nie przekazało
            # narzędzi. Zamiast kończyć pustym błędem: osobna synteza ze źródeł.
            print("  [OLLAMA] Zatrzymano dalsze wywołania (limit lub pętla błędów); osobna synteza.", flush=True)
            phase("Zatrzymano poszukiwania — podsumowanie źródeł")
            content = _synthesize_after_mcp_limit(question, messages, model, num_ctx, cause=stop_cause)
            messages.append(_emergency_history_entry(content))
            compact_finished_history(messages)
            phase("Odpowiedź gotowa (zatrzymano wyszukiwanie)")
            return content

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
                    raise ValueError("Argumenty nie są obiektem JSON")
                # Lokalny widok pliku (query / zakres linii): wycinamy te parametry PRZED naprawą,
                # bo game_read w BK ich nie ma, a model prosi o nie w każdej rundzie testów.
                view = None
                if str(name or "").lower() in GAME_READ_ALIASES:
                    arguments, view = _extract_view_spec(arguments)
                # Naprawa PRZED limitem i dedupe: halucynowane nazwy (search/open...),
                # nieznane argumenty, typy i limity wg prawdziwego schematu z tools/list.
                model_title = arguments.get("title") if isinstance(arguments, dict) else None
                fixed_name, fixed_args, notes = repair_tool_call(name, arguments, mcp.tools)
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
                if fixed_name is None:
                    # Błąd modelu, nie wyszukiwanie: nie wołamy MCP i nie liczymy do limitu.
                    response = "BŁĄD: " + "; ".join(notes) + "\n" + tool_schema_hint(mcp.tools, name)
                    print(f"  [REPAIR] odrzucono {orig_name}: {'; '.join(notes)}", flush=True)
                else:
                    name, arguments = fixed_name, fixed_args
                    if name == "api_search":
                        cap = (SOFT_LIMIT_CLASS_SEARCH if arguments.get("type", "any") in ("class", "any")
                               else SOFT_LIMIT_OTHER_SEARCH)
                        wanted = arguments.get("limit", 10)
                        if not isinstance(wanted, (int, float)) or wanted > cap:
                            notes.append(f"limit {wanted} -> {cap} (wyniki klas są bardzo długie)")
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
                            print(f"  [DUP] {name} {json.dumps(arguments, ensure_ascii=False)} -> pełny wynik z pamięci", flush=True)
                            response = "[powtórzony odczyt - pełny wynik z pamięci podręcznej]\n" + cached
                        elif intact and dup_counts[signature] <= 1:
                            print(f"  [DUP] {name} {json.dumps(arguments, ensure_ascii=False)} -> wynik już w kontekście", flush=True)
                            response = TOOL_DUP_IN_CONTEXT.format(ledger=ledger)
                        else:
                            print(f"  [DUP] {name} {json.dumps(arguments, ensure_ascii=False)} -> zablokowano (powtórka nr {dup_counts[signature]})", flush=True)
                            response = TOOL_DUP_BLOCKED.format(ledger=ledger)
                    elif view and base_signature in full_cache:
                        # Plik już pobrany w tej turze: widok liczymy lokalnie, bez wywołania MCP i bez zużycia limitu.
                        seen_calls.add(signature)
                        vkey = _path_key(arguments.get("path"))
                        view_counts[vkey] = view_counts.get(vkey, 0) + 1
                        if view_counts[vkey] > VIEW_LIMIT_PER_FILE:
                            print(f"  [VIEW] {arguments.get('path', '')} -> limit {VIEW_LIMIT_PER_FILE} widoków tego pliku", flush=True)
                            response = TOOL_VIEW_LIMIT.format(limit=VIEW_LIMIT_PER_FILE, ledger=_ledger(read_paths, searches, misses))
                        else:
                            response, view_found = _render_view(full_cache[base_signature], view)
                            print(f"  [VIEW] {arguments.get('path', '')} {_view_label(view)} -> {len(response)} zn. "
                                  f"({'trafienia' if view_found else 'BEZ trafień'}; z pamięci, bez wywołania MCP)", flush=True)
                            if view_found:
                                successful_tool = True
                            else:
                                misses.append(f"{arguments.get('path', '')}: {_view_label(view)}")
                            results_cache[signature] = response
                            new_signature = signature
                            read_paths.append(f"{arguments.get('path', '')} [{_view_label(view)}]")
                        if notes:
                            response += "\n[korekta wywołania: " + "; ".join(notes) + "]"
                    elif count >= MAX_TOOL_CALLS:
                        response = TOOL_MCP_LIMIT
                    else:
                        seen_calls.add(signature)
                        count += 1
                        print(f"  [MCP {count}/{MAX_TOOL_CALLS}] {name} {json.dumps(arguments, ensure_ascii=False)}", flush=True)
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
                                notes.append(f"użyto tytułu z wywołania modelu: {model_title!r}")
                                print(f"  [REPAIR] wiki_read: znormalizowany tytuł nie istnieje; użyto {model_title!r}", flush=True)
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
                            negative = ((name == "api_search" and response.startswith("[BRAK DOKŁADNEGO TRAFIENIA"))
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
                        print(f"  -> {'BŁĄD' if is_error else 'ok'} {len(response)} zn.", flush=True)
                        if notes:
                            response += "\n[korekta wywołania: " + "; ".join(notes) + "]"
            except (MCPError, ValueError, TypeError, json.JSONDecodeError) as exc:
                response = f"BŁĄD NARZĘDZIA: {exc}"
                # Przy nieistniejącej nazwie / złym schemacie daj modelowi
                # dokładne dane z tools/list, zamiast dopisywać wyjątki do promptu.
                if (name not in mcp.tools or "Niepoprawne argumenty" in str(exc)
                        or "Argumenty nie są obiektem JSON" in str(exc)):
                    response += "\n" + tool_schema_hint(mcp.tools, name)
                print("  " + response[:1300], flush=True)
            tool_msg = {"role": "tool", "tool_name": orig_name, "content": response}
            messages.append(tool_msg)
            if new_signature is not None:
                result_msgs[new_signature] = tool_msg
            _compact_tool_context(messages)
        failed_rounds = 0 if successful_tool else failed_rounds + 1
        if failed_rounds == 2:
            # Przełamanie zastoju: rundy bez nowych danych. Jednorazowa podpowiedź (nie trafia do historii).
            print("  [STALL] 2 rundy bez nowych danych - podpowiedź z rejestrem", flush=True)
            pending_hint = {"role": "user", "content": HINT_STALL.format(ledger=_ledger(read_paths, searches, misses))}
        if count >= MAX_TOOL_CALLS:
            # Nie zostawiaj w historii trwałego systemowego zakazu narzędzi!
            # Wcześniej taka wiadomość mogła zatruwać następną turę rozmowy.
            print("  [OLLAMA] Limit MCP — osobna synteza już odczytanych źródeł.", flush=True)
            phase("Limit MCP — podsumowanie zebranych źródeł")
            content = _synthesize_after_mcp_limit(question, messages, model, num_ctx)
            messages.append(_emergency_history_entry(content))
            compact_finished_history(messages)
            phase("Odpowiedź gotowa (podsumowanie po limicie)")
            return content


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Reforger Assistant {VERSION} — bez OpenCode")
    parser.add_argument("--check", action="store_true", help="tylko sprawdź połączenie i listę narzędzi MCP")
    parser.add_argument("--model", default=MODEL, help="nazwa modelu Ollama")
    parser.add_argument("--num-ctx", type=int, default=NUM_CTX, help="rozmiar kontekstu Ollama")
    args = parser.parse_args()

    print(f"REFORGER ASSISTANT {VERSION}")
    print("Ollama:", args.model, "| MCP BK: bez OpenCode | tryb: tylko odczyt")
    print("Brak skanowania .c, lokalnego indeksu lub ekstrakcji .pak przez Pythona.")
    try:
        with MCPStdioClient() as mcp:
            print("Połączono z Enfusion MCP BK.")
            print("Narzędzia:", ", ".join(mcp.tools))
            if args.check:
                return 0
            print("Komendy: exit / quit — koniec; /reset — nowa rozmowa.")
            messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
            while True:
                try:
                    question = input("\nTy: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nDo zobaczenia!")
                    break
                if question.lower() in ("exit", "quit", "koniec"):
                    break
                if question.lower() == "/reset":
                    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                    print("Historia rozmowy wyczyszczona (bez modyfikacji plików).")
                    continue
                if not question:
                    continue
                try:
                    answer = ask(question, messages, mcp, args.model, args.num_ctx)
                    print("\nAsystent:\n" + answer)
                except (RuntimeError, MCPError) as exc:
                    print("BŁĄD:", exc)
                    # Po błędzie modelu nie zostawiamy w historii urwanej tury.
                    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                    print("Historia tej sesji została zresetowana po błędzie.")
    except (MCPError, OSError) as exc:
        print("Nie udało się uruchomić MCP:", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
