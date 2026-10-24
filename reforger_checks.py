"""Kontrole odpowiedzi: weryfikator cytatów, kontrola nazw API, pamięć sesji (dowody z narzędzi).
Czyste funkcje: nie wołają modelu ani MCP i nie czytają trybów konfiguracji (decyduje o nich silnik)."""
from __future__ import annotations

import re

from reforger_i18n import tr
from reforger_prompts import FOOTER_VERIFY, FOOTER_VERIFY_MORE, FOOTER_API
from reforger_prompts import API_GAME_INSTANCE, API_CHAIN_NOT_SEEN, API_DECL_NO_CLASS, API_DECL_NO_OVERRIDE, API_DECL_NO_IMPLICIT
from reforger_prompts import QUOTE_LINES_NOT_SEEN
from reforger_prompts import (API_SCR_TAG_CLASS, API_SCR_TAG_TEXT, API_RETURN_TYPE, SYNTAX_PREFAB_JSON,
                              SYNTAX_PRINTFORMAT, SYNTAX_ENTRY_CLASS,
                              MARK_QUOTE_BLOCK, MARK_SYNTAX_BLOCK, MARK_LINE_REF, MARK_UNREAD_BLOCK,
                              MARK_API_BLOCK)
from reforger_rules import (REASONING_LEAK_START_RE, REASONING_LEAK_MARKERS_RE, REPEAT_LINE_MAX, SCR_TAG_TEXT_RE,
                            SCR_EXAMPLE_NAME_RE,
                            VALUE_TYPES, VALUE_TYPE_COMPAT)
from reforger_rules import LINE_REF_RE, LINE_COLUMN_RE, VERIFY_NO_FIX_MARKERS, REASONING_LEAK_MIN_MARKERS
from reforger_rules import _COMPILE_LINE_RES, KB_SECTION_RE, SYNTAX_RULES
from reforger_rules import KB_CHECK_CAP, KB_CHECK_DROP_WORDS, KB_CHECK_PRIORITY_RE
from reforger_rules import (
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


# ---------------------------------------------------------------- weryfikator cytatów
# Pliki odczytane w danej rozmowie (klucz: id listy messages): ścieżka(lowercase) -> pełny tekst z game_read.
_SESSION_FILES: dict[int, dict[str, str]] = {}


_SESSION_FILES_MAX = 20


_SESSION_FILE_CAP = 60


def _path_key(path) -> str:
    return str(path or "").replace("\\", "/").strip().lstrip("/").lower()


def _session_key(messages: list):
    """Od 1.8.5: trwały klucz rozmowy zapisany w wiadomości systemowej (pole '_sid', nie trafia do Ollamy).
    Wcześniej kluczem był id(listy): po usunięciu rozmowy Python oddawał ten sam adres nowej liście
    i nowa rozmowa dziedziczyła odczytane pliki, dowody i widziane numery linii poprzedniej."""
    if messages and isinstance(messages[0], dict):
        sid = messages[0].get("_sid")
        if not sid:
            import secrets
            sid = messages[0]["_sid"] = secrets.token_hex(8)
        return sid
    return id(messages)


def _session_files(messages: list) -> dict[str, str]:
    key = _session_key(messages)
    store = _SESSION_FILES.get(key)
    if store is None:
        if len(_SESSION_FILES) >= _SESSION_FILES_MAX:
            _SESSION_FILES.pop(next(iter(_SESSION_FILES)))
        store = _SESSION_FILES[key] = {}
    return store


def _norm_code(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return re.sub(r"\s+", "", text)


def _display_name(key: str, text: str) -> str:
    """Nazwa pliku z oryginalną wielkością liter (z nagłówka odczytu '// ścieżka (from .pak)'), inaczej z klucza."""
    m = re.match(r"//\s*(\S+)\s*\(from", text or "")
    return (m.group(1) if m else key).rsplit("/", 1)[-1]


def _find_evidence(files: dict[str, str], path: str):
    pk = _path_key(path)
    if pk in files:
        return pk, files[pk]
    for key, text in files.items():
        if key.endswith("/" + pk) or pk.endswith("/" + key):
            return key, text
    return None, None


def _verify_answer(answer: str, files: dict[str, str], marks: list | None = None):
    """Sprawdza bloki kodu przypisane do plików gry: czy ich linie występują w odczytanym pliku.
    Zwraca (uwagi, liczba_sprawdzonych_bloków, liczba_zgodnych). Nic nie zmienia i nie woła modelu.
    Od 1.8.7: gdy podano listę marks, dopisuje do niej (początek bloku, ścieżka) bloków niezgodnych z plikiem."""
    findings: list[str] = []
    checked = ok = 0
    norm_cache: dict[str, str] = {}
    prev_end = 0
    pending_path = None
    for match in _CODE_BLOCK_RE.finditer(answer):
        block = match.group(2)
        gap = answer[prev_end:match.start()]
        prev_end = match.end()
        stripped = block.strip()
        # Blok zawierający wyłącznie ścieżkę to etykieta następnego bloku.
        only_path = _PATH_RE.fullmatch(stripped.strip("`' ")) if stripped and "\n" not in stripped else None
        if only_path:
            pending_path = only_path.group(1)
            continue
        lines = [re.sub(r"^\s*\d+\|\s?", "", ln) for ln in block.split("\n")]      # numeracja widoku
        # Od 1.8.4: skrót treści w linii ("Komponent "{GUID}" { … }") to pominięcie, nie wymyślona linia.
        lines = [re.sub(r"\{\s*(?:…|\.\.\.)\s*\}\s*$", "{", ln) for ln in lines]
        path = None
        head_paths = _PATH_RE.findall("\n".join(lines[:4]))
        if head_paths:
            path = head_paths[0]
        else:
            near = _PATH_RE.findall(gap[-400:])
            if near:
                path = near[-1]
            elif pending_path and len(gap) < 250:
                path = pending_path
        pending_path = None
        window = gap[-250:] + "\n" + "\n".join(lines[:3])
        # Od 1.8.7: podpis "szkic" tuż POD blokiem (pierwsze niepuste linie po nim) też oznacza kod własny.
        after = answer[match.end():match.end() + 400].split("```", 1)[0]
        after_lines = [ln for ln in after.split("\n") if ln.strip()][:2]
        if any(_OWN_CODE_RE.search(ln) for ln in after_lines):
            window += "\n" + "\n".join(after_lines)
        # Decyduje ostatnia niepusta linia TUŻ przed blokiem: nagłówek "Przykład użycia" bez podpisu
        # "fragment z gry" / "Plik: ..." oznacza kod własny, nawet gdy wcześniej w akapicie padła ścieżka.
        gap_lines = [ln for ln in gap.split("\n") if ln.strip()]
        last_line = gap_lines[-1] if gap_lines else ""
        own_example = bool(_EXAMPLE_RE.search(last_line)
                           and not (_GAME_QUOTE_RE.search(last_line) or _PATH_RE.search(last_line))
                           and not head_paths)
        if path:
            low = path.lower()
            if ((low.endswith((".et", ".conf", ".layout")) and _SCRIPT_LIKE_RE.search(block))
                    or (low.endswith(".c") and _PREFAB_LIKE_RE.search(block))):
                path = None                 # przypisanie nie pasuje do treści bloku: nie weryfikujemy go z tym plikiem
        first_lines = "\n".join(lines[:3])
        attributed = bool(path) and not (_OWN_CODE_RE.search(window) or own_example)
        if (not path and not _OWN_CODE_RE.search(window) and not own_example and _GAME_LABEL_RE.search(gap[-220:])):
            findings.append(tr("blok oznaczony jako 'z kodu gry' nie wskazuje pliku - cytat niepotwierdzony",
                               "block labelled 'from game code' does not name a file - unconfirmed quote"))
        if not attributed or _EXAMPLE_PATH_RE.search(path or ""):
            # Nowy kod nie powinien używać identyfikatorów istniejących wpisów (kolizja/nadpisanie wpisu).
            for cls, guid in dict.fromkeys(_ENTRY_GUID_RE.findall(block)):
                owner = next((k for k, txt in files.items() if "{" + guid.upper() + "}" in txt.upper()), None)
                if not owner:
                    continue
                found = re.search(r'([A-Za-z_]\w*)\s+"\{' + guid + r'\}"', files[owner], re.I)
                if found and found.group(1) != cls:
                    # Ten sam GUID dla INNEJ klasy = kolizja identyfikatorów. Ta sama klasa to cytat albo
                    # prawidłowe nadpisanie wpisu w override prefabu (np. ActionsManagerComponent).
                    msg = tr(f"GUID {{{guid}}} jest w '{_display_name(owner, files[owner])}' przypisany do wpisu "
                             f"{found.group(1)}, a tutaj użyty dla {cls}: kolizja identyfikatorów "
                             "(nowy wpis powinien mieć własny GUID)",
                             f"GUID {{{guid}}} in '{_display_name(owner, files[owner])}' belongs to the entry "
                             f"{found.group(1)}, but here it is used for {cls}: identifier collision "
                             "(a new entry should have its own GUID)")
                    if msg not in findings:
                        findings.append(msg)
        if (not path or _OWN_CODE_RE.search(window) or own_example
                or _EXAMPLE_PATH_RE.search(path) or re.search(r"\bnp\.|e\.g\.", first_lines)):
            continue                     # kod własny modelu / ścieżka przykładowa / bez przypisanego pliku
        key, text = _find_evidence(files, path)
        if text is None:
            # Kod własny (modded class albo nowa klasa z własnym tagiem, np. RA_Foo) to nie cytat z gry,
            # tylko plik docelowy użytkownika - "nieodczytany" byłby fałszywym alarmem.
            new_classes = [c for c in re.findall(r"^\s*(?:sealed\s+)?class\s+([A-Za-z_]\w*)", block, re.M)
                           if not c.endswith("Class")]
            # Od 1.8.8: klasa z prefiksem gry (SCR_) przypisana do pliku gry to rzekomy cytat, nie plik moda.
            own_new = (bool(new_classes) and not any(c.startswith("SCR_") for c in new_classes)
                       and not any(re.search(rf"\bclass\s+{re.escape(c)}\b", t)
                                   for c in new_classes for t in files.values()))
            if not (re.search(r"\bmodded\s+class\b", block) or own_new       # od 1.8.6: nowa klasa = plik modu
                    or re.search(r"\bclass\s+(?!SCR_)[A-Z][A-Z0-9]{1,5}_\w+", block)):
                findings.append(tr(f"plik '{path}' nie został odczytany w tej rozmowie - cytat niepotwierdzony",
                                   f"file '{path}' was not read in this conversation - unconfirmed quote"))
                if marks is not None:
                    marks.append((match.start(), path, "unread"))
            continue
        checked += 1
        fnorm = norm_cache.setdefault(key, _norm_code(text))
        segments, current = [], []
        for ln in lines:
            if _SEPARATOR_RE.match(ln):
                segments.append(current)
                current = []
            else:
                current.append(ln)
        segments.append(current)
        bad_lines: list[str] = []
        discontinuous = False
        for seg in segments:
            seg_norm = _norm_code("\n".join(seg))
            if len(seg_norm) < 20 or seg_norm in fnorm:
                continue
            # Od 1.8.6: linia ze skrótem ("components { … }", "X …") nie może być dosłowna - to pominięcie, nie wymysł.
            cand = [ln for ln in seg if not re.search(r"…|\.\.\.", ln)]
            missing = [ln.strip() for ln in cand if len(_norm_code(ln)) >= 12 and _norm_code(ln) not in fnorm]
            if not missing:
                # krótkie linie (np. "return null;") sprawdzamy dopiero, gdy cały fragment nie pasuje do pliku
                missing = [ln.strip() for ln in cand if len(_norm_code(ln)) >= 6 and _norm_code(ln) not in fnorm]
            if missing:
                bad_lines.extend(missing)
            else:
                discontinuous = True
        if bad_lines:
            sample = "; ".join(f"`{ln[:80]}`" for ln in bad_lines[:2])
            findings.append(tr(f"w bloku przypisanym do '{path}' nie znaleziono w pliku linii: {sample}",
                               f"in the block attributed to '{path}' these lines were not found in the file: {sample}"))
            if marks is not None:
                marks.append((match.start(), path, "mismatch"))
        elif discontinuous:
            findings.append(tr(f"blok przypisany do '{path}' łączy linie, które w pliku nie sąsiadują ze sobą",
                               f"the block attributed to '{path}' joins lines that are not adjacent in the file"))
        else:
            ok += 1
        # klasa o tej samej nazwie w odczytanych plikach, ale z inną klasą bazową
    for cm in re.finditer(r"\bclass\s+(\w+)\s*:\s*(\w+)", answer):
        cname, parent = cm.groups()
        for text in files.values():
            found = re.search(rf"\bclass\s+{re.escape(cname)}\s*:\s*(\w+)", text)
            if found and found.group(1) != parent:
                msg = _inherit_msg(cname, found.group(1), parent)
                if msg not in findings:
                    findings.append(msg)
                break
    # Teza w prozie: "X dziedziczy po Y" vs deklaracja klasy w odczytanych plikach (od 2.0.0 także "X inherits from Y").
    for pm in re.finditer(r"[`*]*(\w+)[`*]*\s+(?:dziedziczy\s+po|inherits\s+from|extends|derives\s+from)\s+[`*]*(\w+)",
                          answer):
        cname, parent = pm.groups()
        for text in files.values():
            found = re.search(rf"\bclass\s+{re.escape(cname)}\s*:\s*(\w+)", text)
            if found:
                if found.group(1) != parent:
                    msg = _inherit_msg(cname, found.group(1), parent)
                    if msg not in findings:
                        findings.append(msg)
                break
    return findings, checked, ok


def _inherit_msg(cname: str, real: str, parent: str) -> str:
    return tr(f"klasa '{cname}' dziedziczy w odczytanym pliku po '{real}', a w odpowiedzi po '{parent}'",
              f"class '{cname}' inherits from '{real}' in the file that was read, but from '{parent}' in the answer")


def _log_verification(findings: list[str], checked: int, ok: int) -> None:
    if findings:
        print(tr(f"  [VERIFY] UWAGI ({len(findings)}); bloków sprawdzonych: {checked}, zgodnych: {ok}",
                 f"  [VERIFY] ISSUES ({len(findings)}); blocks checked: {checked}, matching: {ok}"), flush=True)
        for item in findings:
            print(f"  [VERIFY]   - {item}", flush=True)
    else:
        print(tr(f"  [VERIFY] OK; bloków sprawdzonych: {checked}, zgodnych: {ok}",
                 f"  [VERIFY] OK; blocks checked: {checked}, matching: {ok}"), flush=True)


def _verification_footer(findings: list[str]) -> str:
    shown = "; ".join(findings[:4])
    more = FOOTER_VERIFY_MORE.format(n=len(findings) - 4) if len(findings) > 4 else ""
    return FOOTER_VERIFY.format(shown=shown, more=more)


def _is_wiki_miss(text: str) -> bool:
    return str(text or "").lstrip().startswith("No wiki page found")


# ---------------------------------------------------------------- kontrola nazw API w kodzie odpowiedzi
# Pamięć sesji (klucz: id listy messages): surowe wyniki narzędzi i nazwy odrzucone przez kompilator.
_SESSION_META: dict[int, dict] = {}


_EVIDENCE_CAP_CHARS = 600_000


def _session_meta(messages: list) -> dict:
    key = _session_key(messages)
    meta = _SESSION_META.get(key)
    if meta is None:
        if len(_SESSION_META) >= _SESSION_FILES_MAX:
            _SESSION_META.pop(next(iter(_SESSION_META)))
        meta = _SESSION_META[key] = {"evidence": [], "chars": 0, "banned": set(), "chains": {}}
    return meta


def _add_evidence(meta: dict, text: str) -> None:
    if not text:
        return
    meta["evidence"].append(text)
    meta["chars"] += len(text)
    while meta["chars"] > _EVIDENCE_CAP_CHARS and len(meta["evidence"]) > 1:
        meta["chars"] -= len(meta["evidence"].pop(0))


def _strip_code_noise(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    code = re.sub(r"//[^\n]*", "", code)
    return re.sub(r'"(?:\\.|[^"\\\n])*"', '""', code)


def _api_calls(answer: str) -> list[tuple]:
    """Wywołania API w blokach kodu odpowiedzi: (klasa | None, metoda, rodzaj).
    rodzaj: 'static' (Klasa.Metoda), 'game' (GetGame().Metoda), 'instance' (zmienna.Metoda), 'global' (Metoda)."""
    calls: list[tuple] = []
    for lang, block in _API_CODE_BLOCK_RE.findall(answer):
        if lang.lower() in _NON_CODE_LANGS or _PREFAB_LIKE_RE.search(block):
            continue
        code = _strip_code_noise(block)
        own = {name for typ, name in re.findall(
            r"^\s*(?:(?:override|static|protected|private|sealed|event|proto|external)\s+)*(?:ref\s+)?"
            r"([A-Za-z_][\w<>,]*)\s+([A-Za-z_]\w*)\s*\(", code, re.M)
            if typ not in ("return", "new", "else", "case", "delete")}
        for m in re.finditer(r"GetGame\(\)\s*\.\s*([A-Za-z_]\w*)\s*\(", code):
            calls.append(("ArmaReforgerScripted", m.group(1), "game"))
        for m in re.finditer(r"(?<![\w.])([A-Z][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_]\w*)\s*\(", code):
            cls, meth = m.groups()
            if cls in _API_CLASS_OK or meth in _API_METHOD_OK:
                continue
            calls.append((cls, meth, "static"))
        for m in re.finditer(r"(?:(?<![\w.])[a-z_]\w*|[)\]])\s*\.\s*([A-Za-z_]\w*)\s*\(", code):
            meth = m.group(1)
            if code[:m.start() + 1].endswith("GetGame()"):
                continue
            if meth in _API_METHOD_OK or meth in own:
                continue
            calls.append((None, meth, "instance"))
        for m in re.finditer(r"(?<![\w.])([A-Z]\w*)\s*\(", code):
            name = m.group(1)
            before = code[max(0, m.start() - 6):m.start()]
            if (name in own or name in _API_GLOBAL_OK or name in _API_KEYWORDS or name in _API_METHOD_OK
                    or re.search(r"new\s+$", before) or re.search(r"\[\s*$", before)):
                continue              # deklaracje, konstruktory, atrybuty [Attribute(...)]
            calls.append((None, name, "global"))
    return list(dict.fromkeys(calls))


def _evidence_texts(meta: dict, files: dict[str, str]) -> list[str]:
    return list(meta.get("evidence", [])) + list(files.values())


def _find_class_method(texts: list[str], cls: str, meth: str):
    """(znaleziono, statyczna | None) dla Klasa.Metoda w wynikach narzędzi: wiersz wyszukiwania metod
    ('Klasa.static proto bool Metoda ()'), sekcja klasy ('## Klasa' ... '- static ... Metoda (') albo odczytany plik."""
    m_re = re.escape(meth)
    c_re = re.escape(cls)
    for text in texts:
        hit = re.search(rf"^\s*(?:\d+\.\s*)?{c_re}\.(.*?)\b{m_re}\s*\(", text, re.M)
        if hit:
            return True, "static" in hit.group(1)
        sec = re.search(rf"^##\s+{c_re}\b(.*?)(?=^##\s|\Z)", text, re.M | re.S)
        if sec:
            line = re.search(rf"^\s*-\s*(.*?)\b{m_re}\s*\(", sec.group(1), re.M)
            if line:
                return True, "static" in line.group(1)
        if re.search(rf"\bclass\s+{c_re}\b", text) and re.search(rf"\b{m_re}\s*\(", text):
            decl = re.search(rf"^[^\n(]*\b{m_re}\s*\(", text, re.M)
            return True, (None if not decl else ("static" in decl.group(0)))
    return False, None


_CLASS_DECL_LINE_RE = re.compile(
    r"^[ \t]*(modded[ \t]+)?(?:sealed[ \t]+)?class[ \t]+([A-Za-z_]\w*)[ \t]*(?:(?::|extends)[ \t]*([A-Za-z_]\w*))?", re.M)
_OVERRIDE_RE = re.compile(
    r"\boverride\s+(?:(?:protected|private|static|event|ref|proto|external)\s+)*[\w<>,]+\s+([A-Za-z_]\w*)\s*\(")


def _decl_items(answer: str) -> list[tuple]:
    """Deklaracje klas w kodzie odpowiedzi (od 1.8.3): (klasa, klasa bazowa | None, modded, [metody z override])."""
    items: list[tuple] = []
    for lang, block in _API_CODE_BLOCK_RE.findall(answer):
        if lang.lower() in _NON_CODE_LANGS or _PREFAB_LIKE_RE.search(block):
            continue
        code = _strip_code_noise(block)
        decls = list(_CLASS_DECL_LINE_RE.finditer(code))
        for i, m in enumerate(decls):
            body = code[m.end():decls[i + 1].start() if i + 1 < len(decls) else len(code)]
            overrides = list(dict.fromkeys(_OVERRIDE_RE.findall(body)))
            items.append((m.group(2), m.group(3), bool(m.group(1)), overrides, _implicit_calls(body)))
    return items


def _implicit_calls(body: str) -> list[str]:
    """Od 1.8.6: wywołania bez obiektu w ciele klasy (np. GetEntity()) - metody tej klasy albo jej klas bazowych.
    Pomijamy metody zadeklarowane w tym ciele, konstruktory (new X), atrybuty, słowa kluczowe i funkcje globalne."""
    own = set(re.findall(r"^\s*(?:(?:override|static|protected|private|sealed|event|proto|external)\s+)*(?:ref\s+)?"
                         r"[A-Za-z_][\w<>,]*\s+([A-Za-z_]\w*)\s*\(", body, re.M))
    calls = []
    for m in re.finditer(r"(?<![\w.])([A-Z]\w*)\s*\(", body):
        name = m.group(1)
        before = body[max(0, m.start() - 6):m.start()]
        if (name in own or name in _API_GLOBAL_OK or name in _API_KEYWORDS or name in _API_METHOD_OK
                or re.search(r"new\s+$", before) or re.search(r"\[\s*$", before)):
            continue
        calls.append(name)
    return list(dict.fromkeys(calls))


def _decl_target(cls: str, base, modded: bool, own: set):
    """Klasa, którą deklaracja zakłada w grze: modded -> sama klasa; 'class X : Y' -> Y (chyba że Y jest w odpowiedzi)."""
    if modded:
        return cls
    if base and base not in own:
        return base
    return None


def _class_known(texts: list[str], cls: str) -> bool:
    c_re = re.escape(cls)
    return any(re.search(rf"^##\s+{c_re}\s*$", t, re.M) or re.search(rf"\bclass\s+{c_re}\b", t) for t in texts)


def _decl_problems(answer: str, meta: dict, files: dict[str, str]) -> list[str]:
    """Klasa bazowa / klasa modyfikowana musi istnieć, a metody z override muszą być w niej lub w jej przodkach."""
    texts = _evidence_texts(meta, files)
    chains = meta.get("chains", {})
    items = _decl_items(answer)
    own = {it[0] for it in items if not it[2]}
    problems: list[str] = []
    for cls, base, modded, overrides, implicit in items:
        target = _decl_target(cls, base, modded, own)
        if not target:
            continue
        decl = f"modded class {cls}" if modded else f"class {cls} : {base}"
        if not _class_known(texts, target):
            problems.append(API_DECL_NO_CLASS.format(decl=decl, target=target))
            continue
        classes = [target] + chains.get(target, [])
        for meth in overrides:
            if not any(_find_class_method(texts, c, meth)[0] for c in classes):
                problems.append(API_DECL_NO_OVERRIDE.format(meth=meth, cls=cls, target=target))
        for meth in implicit:
            if meth in overrides or _class_known(texts, meth):
                continue                  # nazwa klasy (np. rzutowanie) albo metoda już sprawdzona jako override
            if not any(_find_class_method(texts, c, meth)[0] for c in classes):
                problems.append(API_DECL_NO_IMPLICIT.format(meth=meth, cls=cls, target=target))
    return problems


def _enum_values(texts: list[str], enum: str) -> set[str] | None:
    """Wartości enuma z dowodów: deklaracja 'enum X { ... }' z odczytanego pliku albo lista 'Values:' z api_search.
    None = enuma nie ma w dowodach (wtedy nic nie zgłaszamy)."""
    e_re = re.escape(enum)
    for t in texts:
        m = re.search(rf"\benum\s+{e_re}\s*(?::\s*\w+\s*)?\{{(.*?)\}}", t, re.S)
        if m:
            body = re.sub(r"//[^\n]*|/\*.*?\*/", "", m.group(1), flags=re.S)
            return set(re.findall(r"\b([A-Za-z_]\w*)\s*(?:=[^,\n]*)?\s*(?:,|$)", body, re.M))
        m = re.search(rf"\.{e_re}\b[^\n]*\n(?:[^\n]*\n){{0,4}}?\s*Values:\s*\n((?:\s*-\s*\w+[^\n]*\n?)+)", t)
        if m:
            return set(re.findall(r"^\s*-\s*(\w+)", m.group(1), re.M))
    return None


def _enum_problems(answer: str, texts: list[str]) -> list[str]:
    """Enum.WARTOŚĆ w kodzie odpowiedzi, gdy enum jest w dowodach, a takiej wartości w nim nie ma (np. LogLevel.INFO)."""
    problems = []
    codes = [_strip_code_noise(block) for lang, block in _API_CODE_BLOCK_RE.findall(answer)
             if not (lang.lower() in _NON_CODE_LANGS or _PREFAB_LIKE_RE.search(block))]
    # Od 1.8.7: także kod w linii tekstu i w tabelach (`Print("x", LogLevel.INFO);`), nie tylko bloki.
    prose = _API_CODE_BLOCK_RE.sub("", answer)
    codes += [span for span in re.findall(r"`([^`\n]+)`", prose)]
    for code in codes:
        for enum, value in dict.fromkeys(re.findall(r"(?<![\w.])([A-Z]\w*)\.([A-Z][A-Z0-9_]+)\b(?!\s*\()", code)):
            values = _enum_values(texts, enum)
            if values and value not in values:
                shown = ", ".join(sorted(values)[:10])
                problems.append(tr(f"{enum}.{value}: wartości {value} nie ma w enumie {enum} (są: {shown})",
                                   f"{enum}.{value}: the value {value} is not in the enum {enum} (values: {shown})"))
    return problems


def _game_classes(meta: dict) -> list[str]:
    """Klasy obiektu gry: stała lista + łańcuch przodków ArmaReforgerScripted ustalony z plików gry (od 1.8.2)."""
    chain = meta.get("chains", {}).get("ArmaReforgerScripted", [])
    return list(dict.fromkeys(list(_API_GAME_CLASSES) + list(chain)))


def _api_problems(answer: str, meta: dict, files: dict[str, str]) -> list[str]:
    """Nazwy API w kodzie odpowiedzi, których nie potwierdzają wyniki narzędzi tej rozmowy.
    Od 1.8.2 metoda klasy jest szukana także w klasach bazowych ustalonych przez silnik (meta['chains'])."""
    texts = _evidence_texts(meta, files)
    banned = meta.get("banned", set())
    chains = meta.get("chains", {})
    game_classes = _game_classes(meta)
    problems: list[str] = []
    for cls, meth, kind in _api_calls(answer):
        shown = (f"GetGame().{meth}" if kind == "game" else f"{cls}.{meth}" if cls else f"{meth}")
        if (cls and f"{cls}.{meth}" in banned) or meth in banned:
            problems.append(tr(f"{shown}: kompilator zgłosił, że {cls + '.' if cls else ''}{meth} nie istnieje",
                               f"{shown}: the compiler reported that {cls + '.' if cls else ''}{meth} does not exist"))
            continue
        if kind == "game":
            if not any(_find_class_method(texts, c, meth)[0] for c in game_classes):
                problems.append(API_CHAIN_NOT_SEEN.format(shown=shown, cls="ArmaReforgerScripted",
                                                          chain=" : ".join(game_classes[1:]) or "-"))
            continue
        if kind == "static":
            found, is_static = _find_class_method(texts, cls, meth)
            if not found:
                for ancestor in chains.get(cls, []):
                    found, is_static = _find_class_method(texts, ancestor, meth)
                    if found:
                        break
            if not found:
                chain = chains.get(cls)
                problems.append(API_CHAIN_NOT_SEEN.format(shown=shown, cls=cls, chain=" : ".join(chain))
                                if chain else tr(f"{shown}: brak w wynikach narzędzi dla klasy {cls}",
                                                 f"{shown}: not in the tool results for class {cls}"))
            elif is_static is False:
                problems.append(API_GAME_INSTANCE.format(cls=cls, meth=meth) if cls in game_classes
                                else tr(f"{shown}: metoda instancji wywołana statycznie (wywołaj ją na obiekcie)",
                                        f"{shown}: instance method called statically (call it on an object)"))
            continue
        if not any(re.search(rf"\b{re.escape(meth)}\s*\(", t) for t in texts):
            problems.append(tr(f"{shown}(): brak w wynikach narzędzi", f"{shown}(): not in the tool results"))
    problems = _decl_problems(answer, meta, files) + problems      # od 1.8.3: klasy bazowe i override najpierw
    problems += _enum_problems(answer, texts)                     # od 1.8.5: wymyślone wartości enumów
    problems += _return_type_problems(answer, texts)              # od 1.8.7: typ zwracany vs typ zmiennej
    problems += _scr_tag_problems(answer, texts, files)           # od 1.8.7: SCR_ jako prefiks klas moda
    return list(dict.fromkeys(problems))[:8]


# ---------------------------------------------------------------- od 1.8.7
_RET_SKIP = {"return", "new", "else", "case", "delete", "proto", "external", "static", "override", "event",
             "private", "protected", "sealed", "native", "volatile", "const", "out", "inout", "notnull", "ref",
             "autoptr", "owned", "local", "if", "while", "for", "foreach", "switch", "typedef", "class", "modded",
             "and", "or", "not", "a", "the", "is", "be"}


def _return_types(texts: list[str], meth: str) -> set[str]:
    """Typy zwracane metody meth w wynikach narzędzi ("proto external BaseContainer GetPrefab ()")."""
    found: set[str] = set()
    m_re = re.escape(meth)
    for t in texts:
        for m in re.finditer(rf"(?<![\w.])([A-Za-z_]\w*(?:<[^<>\n]*>)?)\s+{m_re}\s*\(", t):
            typ = m.group(1)
            if typ.split("<", 1)[0] not in _RET_SKIP:
                found.add(typ)
    return found


def _types_compatible(declared: str, returned: str) -> bool:
    if declared == returned or declared in ("auto", "Managed", "Class") or returned == "auto":
        return True
    if (declared, returned) in VALUE_TYPE_COMPAT:
        return True
    d_val, r_val = declared in VALUE_TYPES, returned in VALUE_TYPES
    if d_val or r_val:
        return False            # wartość <-> obiekt albo dwie różne wartości (np. ResourceName <- BaseContainer)
    return True                 # dwie klasy: dziedziczenia tu nie znamy, nie zgłaszamy


def _return_type_problems(answer: str, texts: list[str]) -> list[str]:
    """`Typ x = ....Metoda(...);` gdy wyniki narzędzi zgodnie podają inny typ zwracany tej metody
    (H: ResourceName rn = owner.GetPrefabData().GetPrefab(); a GetPrefab() zwraca BaseContainer)."""
    problems = []
    for lang, block in _API_CODE_BLOCK_RE.findall(answer):
        if lang.lower() in _NON_CODE_LANGS or _PREFAB_LIKE_RE.search(block):
            continue
        code = _strip_code_noise(block)
        for m in re.finditer(r"^\s*(?:ref\s+)?([A-Za-z_]\w*)\s+([a-zA-Z_]\w*)\s*=\s*([^;\n]+?)\s*;", code, re.M):
            typ, var, expr = m.groups()
            if typ in _RET_SKIP:
                continue
            call = re.search(r"\.\s*([A-Za-z_]\w*)\s*\([^()]*\)\s*$", expr)
            if not call or re.search(r"\bCast\s*\(", expr):
                continue
            meth = call.group(1)
            rets = {r for r in _return_types(texts, meth) if r != "void"}
            if len(rets) != 1:
                continue        # metody nie ma w dowodach albo kilka klas ma ją z różnymi typami: nie zgadujemy
            ret = next(iter(rets))
            if not _types_compatible(typ, ret):
                problems.append(API_RETURN_TYPE.format(decl=f"{typ} {var} = ...{meth}()", meth=meth, ret=ret, typ=typ))
    return problems


# Od 2.0.2: silnik podstawia tu DOCS.knows (hierarchia klas z dokumentacji Workbencha), żeby rozpoznać klasy gry.
GAME_CLASS_LOOKUP = None


def _scr_tag_problems(answer: str, texts: list[str], files: dict[str, str]) -> list[str]:
    """Nowa klasa moda z prefiksem SCR_ (prefiks gry) albo zalecenie SCR_ jako tagu moda w tekście."""
    problems = []
    for cls, _base, modded, _ov, _imp in _decl_items(answer):
        if modded or not cls.startswith("SCR_") or cls.endswith("Class"):
            continue
        if _class_known(texts, cls) or any(re.search(rf"\bclass\s+{re.escape(cls)}\b", t) for t in files.values()):
            continue            # klasa gry (cytat albo modded): to nie jest nowa klasa moda
        # Od 2.0.2: klasa gry znana z dokumentacji API albo z wyników narzędzi jako właściciel metod ("SCR_X.Metoda(")
        # - test G (EN): SCR_CharacterControllerComponent opisany przez silnik jako "nowa klasa moda".
        if (GAME_CLASS_LOOKUP and GAME_CLASS_LOOKUP(cls)) or any(
                re.search(rf"\b{re.escape(cls)}\.\w+\s*\(", t) for t in texts):
            continue
        problems.append(API_SCR_TAG_CLASS.format(cls=cls, rest=cls[4:]))
    prose = _API_CODE_BLOCK_RE.sub("", answer)
    if (re.search(SCR_TAG_TEXT_RE, prose, re.I)
            # od 1.9.3: tabela "Tag (prefiks) | ... | `SCR_`" i przykładowe nazwy moda w tekście (`SCR_MyComponent.c`)
            or re.search(r"^\|[^\n]*(?:tag|prefiks|prefix)[^\n]*\|\s*[*`]*SCR_[*`]*\s*\|", prose, re.I | re.M)
            or re.search(SCR_EXAMPLE_NAME_RE, prose)):
        problems.append(API_SCR_TAG_TEXT)
    return problems


def _api_footer(problems: list[str]) -> str:
    return FOOTER_API.format(problems="; ".join(problems))



# ---------------------------------------------------------------- od 1.7.1: błędy kompilatora z linią i kontrola składni
def _compile_line_errors(text: str) -> list[tuple[str, int, str]]:
    """(plik, linia, komunikat) z komunikatów kompilatora wklejonych przez użytkownika."""
    found: dict[tuple, tuple] = {}
    for pattern in _COMPILE_LINE_RES:
        for m in pattern.finditer(text or ""):
            path, line, msg = m.group(1).strip(), int(m.group(2)), m.group(3).strip()
            key = (path.replace("\\", "/").rsplit("/", 1)[-1].lower(), line)
            found.setdefault(key, (path, line, msg))
    return list(found.values())


def _enforce_blocks(answer: str) -> list[str]:
    return [block for lang, block in _API_CODE_BLOCK_RE.findall(answer or "")
            if lang.lower() not in _NON_CODE_LANGS and not _PREFAB_LIKE_RE.search(block)]


def _syntax_findings(code: str) -> list[str]:
    lines = _strip_code_noise(code).split("\n")
    out = []
    for pattern, message in SYNTAX_RULES:
        hit = next((ln.strip() for ln in lines if pattern.search(ln)), None)
        if hit is not None:
            out.append(f"{message}: `{hit[:90]}`")
    return out


def _syntax_problems(answer: str) -> list[str]:
    """Składnia, której Enforce Script nie przyjmuje, w blokach kodu odpowiedzi."""
    problems: list[str] = []
    for block in _enforce_blocks(answer):
        problems.extend(_syntax_findings(block))
    problems.extend(_prefab_json_problems(answer))           # od 1.8.7
    problems.extend(_format_string_problems(answer))         # od 1.8.8
    problems.extend(_entry_class_problems(answer))           # od 1.8.8
    return list(dict.fromkeys(problems))[:6]


def _format_string_problems(answer: str) -> list[str]:
    """PrintFormat ze znacznikami z C (%s, %d): Enforce Script używa %1..%9 (test H)."""
    for block in _enforce_blocks(answer):
        hit = re.search(r'PrintFormat\s*\(\s*"[^"\n]*%[sdifx][^"\n]*"[^\n]*', block)
        if hit:
            return [SYNTAX_PRINTFORMAT.format(line=hit.group(0).strip()[:90])]
    return []


def _entry_class_problems(answer: str) -> list[str]:
    """Wpis prefabu (.et) z inną klasą niż nowa klasa w skrypcie tej samej odpowiedzi
    (A2: class TAG_LogWeaponPrefabUserAction w skrypcie, a w additionalActions SCR_LogWeaponPrefabUserAction)."""
    new = {cls for cls, _b, modded, _o, _i in _decl_items(answer) if not modded}
    if not new:
        return []
    problems = []
    for lang, block in _API_CODE_BLOCK_RE.findall(answer):
        if not (lang.lower() == "et" or _PREFAB_LIKE_RE.search(block)):
            continue
        for entry in dict.fromkeys(re.findall(r'^\s*([A-Za-z_]\w*)\s+"\{', block, re.M)):
            if entry in new:
                continue
            tail = entry.split("_", 1)[-1]
            twin = next((c for c in new if c.split("_", 1)[-1] == tail), None)
            if twin:
                problems.append(SYNTAX_ENTRY_CLASS.format(entry=entry, cls=twin))
    return problems


def _prefab_json_problems(answer: str) -> list[str]:
    """Wpis prefabu (.et) podany jako JSON (A2: {"Name": ..., "ParentContextList": ...})."""
    if not re.search(r"\.et\b|additionalActions|ActionsManagerComponent|prefab", answer, re.I):
        return []
    for lang, block in _API_CODE_BLOCK_RE.findall(answer):
        b = block.strip()
        if (lang.lower() == "json" or b.startswith(("{", "["))) and re.search(r'^\s*"\w+"\s*:', b, re.M) \
                and re.search(r'"(?:ParentContextList|UIInfo|components|additionalActions|ActionContexts|ContextName|'
                              r'Name|m_\w+)"\s*:', b):
            return [SYNTAX_PREFAB_JSON]
    return []


def _code_line_excerpt(messages: list, file_name: str, line_no: int, radius: int = 2):
    """Linia wskazana przez kompilator w ostatnim bloku kodu asystenta: (fragment z numeracją, linia) albo None.
    Preferuje blok, w którego nagłówku pada nazwa pliku z komunikatu."""
    base = file_name.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for message in reversed(messages or []):
        if message.get("role") != "assistant":
            continue
        blocks = _enforce_blocks(str(message.get("content", "")))
        if not blocks:
            continue
        chosen = next((b for b in blocks if base and base in b[:300].lower()), blocks[-1])
        lines = chosen.split("\n")
        if lines and not lines[-1].strip():
            lines = lines[:-1]
        if not 1 <= line_no <= len(lines):
            return None
        lo, hi = max(1, line_no - radius), min(len(lines), line_no + radius)
        excerpt = "\n".join(f"{'>>' if i == line_no else '  '} {i:3d}| {lines[i - 1]}" for i in range(lo, hi + 1))
        return excerpt, lines[line_no - 1]
    return None


def _kb_sections(text: str, cap: int = 4500) -> str:
    """Z pliku bazy wiedzy tylko sekcje o pułapkach składni (nagłówki '## ...' pasujące do KB_SECTION_RE)."""
    parts = re.split(r"(?m)^(?=##\s)", text or "")
    keep = [part.strip() for part in parts if part.startswith("##") and KB_SECTION_RE.search(part.split("\n", 1)[0])]
    return "\n\n".join(keep)[:cap]


# ---------------------------------------------------------------- wiedza przed kodem (od 1.8.0)
def _own_code_blocks(answer: str, meta: dict, files: dict[str, str]) -> list[str]:
    """Bloki z WŁASNYM kodem modelu: modded class albo deklaracja klasy, której nie ma w wynikach narzędzi.
    Cytaty z gry (klasy znane z odczytów) i krótkie fragmenty bez klasy nie liczą się."""
    texts = _evidence_texts(meta, files)
    own = []
    for block in _enforce_blocks(answer):
        code = _strip_code_noise(block)
        if re.search(r"\bmodded\s+class\b", code):
            own.append(block)
            continue
        names = re.findall(r"\bclass\s+(\w+)", code)
        if names and not all(any(re.search(rf"\bclass\s+{re.escape(n)}\b", t) for t in texts) for n in names):
            own.append(block)
    return own


def _kb_query_from_code(code: str, limit: int = 16) -> str:
    """Zapytanie do wb_knowledge zbudowane z samego kodu: modded/override i słowa z nazw klas i metod
    (CamelCase rozbite, prefiksy tagów usunięte, sąsiednie słowa także sklejone, np. game+mode -> gamemode)."""
    code = _strip_code_noise(code)
    words: list[str] = []
    if re.search(r"\bmodded\s+class\b", code):
        words += ["modded", "override"]
    idents = [n for pair in re.findall(r"\b(?:modded\s+)?class\s+(\w+)(?:\s*:\s*(\w+))?", code) for n in pair if n]
    idents += re.findall(r"\b([A-Z]\w+)\s*\.\s*[A-Z]\w*\s*\(", code) + re.findall(r"\boverride\s+\w+\s+(\w+)\s*\(", code)
    for ident in idents:
        ident = re.sub(r"^(SCR_|[A-Z]{2,5}_)", "", ident)
        for part in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", ident):
            p = part.lower()
            if len(p) > 2 and p not in KB_CHECK_DROP_WORDS:
                words.append(p)
    joined = [a + b for a, b in zip(words, words[1:]) if a != b]
    return " ".join(list(dict.fromkeys(words + joined))[:limit])


def _kb_excerpt(text: str, query: str, cap: int = KB_CHECK_CAP) -> tuple[str, list[str]]:
    """Z wyniku wb_knowledge: najpierw sekcje z regułami/pułapkami/strukturą, potem sekcje z nagłówkiem
    zawierającym słowo z zapytania. Zwraca (fragment, tytuły plików)."""
    sections = re.split(r"(?m)^(?=##\s)", text or "")
    titles, picked = [], []
    tokens = [t for t in query.split() if len(t) > 3]
    for i, sec in enumerate(sections):
        if not sec.startswith("##"):
            continue
        heading, _, body = sec.partition("\n")
        if body.lstrip().startswith("# "):        # nagłówek pliku dopisany przez wb_knowledge
            titles.append(heading[2:].strip())
            continue
        if KB_CHECK_PRIORITY_RE.search(heading):
            picked.append((0, i, sec.strip()))
        elif any(t in heading.lower() for t in tokens):
            picked.append((1, i, sec.strip()))
    out, used = [], 0
    for _, _, sec in sorted(picked):
        if used + len(sec) > cap:
            continue
        out.append(sec)
        used += len(sec) + 2
    return "\n\n".join(out), titles


# ---------------------------------------------------------------- od 1.8.1
def _fenced_code_blocks(text: str, cap: int) -> str:
    """Wszystkie bloki kodu z odpowiedzi w oryginalnej postaci (z językiem), łącznie do cap znaków."""
    out, used = [], 0
    for m in re.finditer(r"```[^\n]*\n.*?```", text or "", re.S):
        block = m.group(0)
        if used + len(block) > cap:
            break
        out.append(block)
        used += len(block) + 2
    return "\n\n".join(out)


# ---------------------------------------------------------------- od 1.8.4: numery linii i uwagi do rundy poprawkowej
def _record_view_lines(meta: dict, view_text: str, path: str | None = None) -> None:
    """Zapamiętuje numery linii pokazane modelowi w lokalnym widoku pliku ('12| kod'): łącznie i (od 1.8.6) dla pliku."""
    nums = {int(n) for n in re.findall(r"^(\d+)\| ", view_text or "", re.M)}
    meta.setdefault("seen_lines", set()).update(nums)
    if path:
        meta.setdefault("seen_by_file", {}).setdefault(_path_key(path), set()).update(nums)


_FILE_NAME_RE = re.compile(r"[\w./\\-]*?([A-Za-z_]\w*)\.(?:c|et|conf|layout)\b")


def _seen_for(context: str, meta: dict) -> set[int] | None:
    """Numery linii widziane w pliku, o którym mowa w kontekście odwołania (wiersz tabeli / linia tekstu).
    Plik rozpoznajemy po nazwie pliku albo nazwie klasy równej nazwie pliku. None = nie wiadomo, o który plik chodzi."""
    by_file = meta.get("seen_by_file", {})
    names = {m.group(1).lower() for m in _FILE_NAME_RE.finditer(context)}
    names |= {w.lower() for w in re.findall(r"\b([A-Z]\w{3,})\b", context)}
    hits = [key for key in by_file if key.rsplit("/", 1)[-1].rsplit(".", 1)[0] in names]
    if hits:
        return set().union(*(by_file[k] for k in hits))
    if any(m.group(1).lower() for m in _FILE_NAME_RE.finditer(context)):
        return set()                  # plik nazwany, ale nigdy nie oglądany w widoku: żaden numer nie jest potwierdzony
    return None


TABLE_LABEL = tr("tabela: ", "table: ")
_RANGE_RE = re.compile(r"(\d{1,5})(?:\s*[-‑–]\s*(\d{1,5}))?")


def _line_refs(answer: str) -> list[tuple[str, int, int | None]]:
    """Odwołania do numerów linii: w prozie ("linie 8-12") i w kolumnie tabeli o nagłówku "Linia/Linie..." (od 1.8.5)."""
    text = re.sub(r"^\s*\d+\|.*$", "", answer, flags=re.M)        # przepisany widok z numerami to nie odwołanie
    refs = []
    for m in re.finditer(LINE_REF_RE, text, re.I):
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        context = text[line_start:line_end if line_end >= 0 else len(text)]
        refs.append((m.group(0).strip(), int(m.group(1)), int(m.group(2)) if m.group(2) else None, context))
    col = None
    for line in text.split("\n"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") else None
        if cells is None:
            col = None
            continue
        if col is None:
            col = next((i for i, c in enumerate(cells) if re.match(LINE_COLUMN_RE, c)), None)
            continue
        if col < len(cells) and not re.fullmatch(r"[-:\s]*", cells[col]):
            for m in _RANGE_RE.finditer(cells[col]):
                refs.append((TABLE_LABEL + cells[col], int(m.group(1)), int(m.group(2)) if m.group(2) else None, line))
    return refs


def _ref_unconfirmed(ref: tuple, meta: dict) -> bool:
    _label, start, end, context = ref
    seen = _seen_for(context, meta)
    if seen is None:
        seen = meta.get("seen_lines", set())
    return start not in seen or (end is not None and end not in seen)


def _line_ref_stats(answer: str, meta: dict) -> tuple[int, int, int]:
    """Do logu: (odwołań do linii, ile numerów widział model w widokach, ile odwołań niepotwierdzonych)."""
    refs = _line_refs(answer)
    bad = [r for r in refs if _ref_unconfirmed(r, meta)]
    return len(refs), len(meta.get("seen_lines", set())), len(bad)


def _line_ref_problems(answer: str, meta: dict) -> list[str]:
    """Numery linii w odpowiedzi, których model nie widział w żadnym widoku pliku (game_read nie numeruje linii)."""
    bad = [ref[0] for ref in _line_refs(answer) if _ref_unconfirmed(ref, meta)]
    if not bad:
        return []
    refs = ", ".join(f"'{b}'" for b in list(dict.fromkeys(bad))[:4]) + (" ..." if len(bad) > 4 else "")
    return [QUOTE_LINES_NOT_SEEN.format(refs=refs)]


def _quote_problems(answer: str, meta: dict, files: dict[str, str]) -> list[str]:
    """Uwagi weryfikatora cytatów + numery linii spoza widoków: to, co uzasadnia rundę poprawkową."""
    findings, _checked, _ok = _verify_answer(answer, files)
    findings = [f for f in findings if not any(m in f for m in VERIFY_NO_FIX_MARKERS)]
    return list(dict.fromkeys(findings + _line_ref_problems(answer, meta)))[:6]



# ---------------------------------------------------------------- od 1.8.7: porządkowanie i oznaczenia w treści
def _strip_leaked_reasoning(text: str) -> tuple[str, int]:
    """Rozumowanie gpt-oss, które trafiło do treści ("We need to answer: ... Let's craft answer in Polish.**Jak...").
    Usuwa wstęp do pierwszego nagłówka/pogrubienia po zdaniu, gdy wstęp wygląda na rozumowanie po angielsku.
    Zwraca (tekst, ile znaków usunięto)."""
    if not text or not re.match(REASONING_LEAK_START_RE, text):
        return text, 0
    for m in re.finditer(r"(?:^|(?<=[.!?:]))[ \t]*(\*\*[^*\n]|#{1,4} |\|)", text, re.M):
        head = text[:m.start()]
        if len(head) < 80:
            continue
        if len(re.findall(REASONING_LEAK_MARKERS_RE, head)) < REASONING_LEAK_MIN_MARKERS:
            continue
        rest = text[m.start():].lstrip()
        if len(rest) < 80:
            return text, 0
        return rest, len(text) - len(rest)
    return text, 0


def _collapse_repeats(text: str) -> tuple[str, int]:
    """Zapętlenie modelu: ten sam wiersz tabeli / ta sama linia tekstu powtórzona wiele razy (A1: ~90 identycznych
    wierszy). Poza blokami kodu zostawia pierwsze REPEAT_LINE_MAX wystąpień. Zwraca (tekst, ile linii usunięto)."""
    out, counts, removed, in_code = [], {}, 0, False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        key = re.sub(r"\s+", " ", line.strip())
        if in_code or len(key) < 12 or re.fullmatch(r"[|:\-\s]+", key):
            out.append(line)
            continue
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > REPEAT_LINE_MAX:
            removed += 1
            continue
        out.append(line)
    return "\n".join(out), removed


def _annotate_answer(answer: str, files: dict[str, str], meta: dict, syntax: list[str] | None = None,
                     api: list[str] | None = None) -> tuple[str, int]:
    """Oznaczenia w TREŚCI odpowiedzi dla problemów, które przetrwały rundę poprawek: blok podpisany plikiem gry,
    którego linii nie ma w pliku; blok z niedozwoloną składnią; numery linii spoza widoków. Zwraca (tekst, ile oznaczeń)."""
    inserts: list[tuple[int, str]] = []
    marks: list = []
    _verify_answer(answer, files, marks)
    for pos, path, kind in marks:
        inserts.append((pos, (MARK_UNREAD_BLOCK if kind == "unread" else MARK_QUOTE_BLOCK).format(path=path)))
    for problem in syntax or []:
        hit = re.search(r"`([^`]+)`\s*$", problem)
        needle = _norm_code(hit.group(1)) if hit else ""
        for m in _API_CODE_BLOCK_RE.finditer(answer):
            if needle and needle in _norm_code(m.group(2)):
                text = problem[:hit.start()].rstrip(": ") if hit else problem
                inserts.append((m.start(), MARK_SYNTAX_BLOCK.format(problem=text)))
                break
    # Od 1.9.1: deklaracje klas, których nie potwierdza API (np. modded class nieistniejącej klasy, klasa bazowa
    # spoza API, SCR_ w nowej klasie moda) - oznaczenie przy bloku z tą deklaracją.
    for problem in api or []:
        m = re.match(r"(?:modded\s+)?class\s+([A-Za-z_]\w*)", problem)
        if not m:
            continue
        decl_re = re.compile(rf"^\s*(?:modded\s+)?(?:sealed\s+)?class\s+{re.escape(m.group(1))}\b", re.M)
        for b in _API_CODE_BLOCK_RE.finditer(answer):
            if decl_re.search(b.group(2)):
                if not any(p == b.start() and problem in t for p, t in inserts):
                    inserts.append((b.start(), MARK_API_BLOCK.format(problem=problem)))
                break
    count = len(inserts)
    for pos, mark in sorted(inserts, key=lambda x: -x[0]):
        line_start = answer.rfind("\n", 0, pos) + 1
        answer = answer[:line_start] + mark + answer[line_start:]
    # numery linii: po wstawieniach (nie przesuwają się, bo szukamy tekstu, nie pozycji)
    bad = [ref for ref in _line_refs(answer) if _ref_unconfirmed(ref, meta)]
    labels = list(dict.fromkeys(ref[0].replace(TABLE_LABEL, "", 1) for ref in bad))
    for label in labels:
        if not label:
            continue
        answer, n = re.subn(re.escape(label) + r"(?!" + re.escape(MARK_LINE_REF) + ")", label + MARK_LINE_REF, answer)
        count += n
    return answer, count


def _sync_entry_classes(answer: str) -> tuple[str, list[tuple[str, str]]]:
    """Od 1.8.8: wpis .et z klasą, która różni się od nowej klasy w skrypcie tej samej odpowiedzi tylko tagiem
    (SCR_LogWeaponPrefabUserAction we wpisie, TAG_LogWeaponPrefabUserAction w skrypcie), silnik ujednolica sam:
    nazwa we wpisie musi być nazwą klasy ze skryptu. Zmienia tylko pierwszy token wpisu w bloku prefabu."""
    pairs = []
    for problem_entry, cls in _entry_class_pairs(answer):
        pairs.append((problem_entry, cls))
    if not pairs:
        return answer, []

    def fix_block(m: re.Match) -> str:
        block = m.group(0)
        if not (m.group(1).lower() == "et" or _PREFAB_LIKE_RE.search(m.group(2))):
            return block
        for old, new in pairs:
            block = re.sub(rf'^(\s*){re.escape(old)}(\s+"\{{)', rf"\g<1>{new}\g<2>", block, flags=re.M)
        return block

    return _API_CODE_BLOCK_RE.sub(fix_block, answer), pairs


def _entry_class_pairs(answer: str) -> list[tuple[str, str]]:
    new = {cls for cls, _b, modded, _o, _i in _decl_items(answer) if not modded}
    out = []
    if not new:
        return out
    for lang, block in _API_CODE_BLOCK_RE.findall(answer):
        if not (lang.lower() == "et" or _PREFAB_LIKE_RE.search(block)):
            continue
        for entry in dict.fromkeys(re.findall(r'^\s*([A-Za-z_]\w*)\s+"\{', block, re.M)):
            if entry in new:
                continue
            tail = entry.split("_", 1)[-1]
            twins = [c for c in new if c.split("_", 1)[-1] == tail]
            if len(twins) == 1 and (entry, twins[0]) not in out:
                out.append((entry, twins[0]))
    return out
