"""Kontrole odpowiedzi: weryfikator cytatów, kontrola nazw API, pamięć sesji (dowody z narzędzi).
Czyste funkcje: nie wołają modelu ani MCP i nie czytają trybów konfiguracji (decyduje o nich silnik)."""
from __future__ import annotations

import re

from reforger_prompts import FOOTER_VERIFY, FOOTER_VERIFY_MORE, FOOTER_API
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


def _session_files(messages: list) -> dict[str, str]:
    key = id(messages)
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


def _verify_answer(answer: str, files: dict[str, str]):
    """Sprawdza bloki kodu przypisane do plików gry: czy ich linie występują w odczytanym pliku.
    Zwraca (uwagi, liczba_sprawdzonych_bloków, liczba_zgodnych). Nic nie zmienia i nie woła modelu."""
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
            findings.append("blok oznaczony jako 'z kodu gry' nie wskazuje pliku - cytat niepotwierdzony")
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
                    msg = (f"GUID {{{guid}}} jest w '{_display_name(owner, files[owner])}' przypisany do wpisu "
                           f"{found.group(1)}, a tutaj użyty dla {cls}: kolizja identyfikatorów "
                           "(nowy wpis powinien mieć własny GUID)")
                    if msg not in findings:
                        findings.append(msg)
        if (not path or _OWN_CODE_RE.search(window) or own_example
                or _EXAMPLE_PATH_RE.search(path) or re.search(r"\bnp\.|e\.g\.", first_lines)):
            continue                     # kod własny modelu / ścieżka przykładowa / bez przypisanego pliku
        key, text = _find_evidence(files, path)
        if text is None:
            # Kod własny (modded class albo nowa klasa z własnym tagiem, np. RA_Foo) to nie cytat z gry,
            # tylko plik docelowy użytkownika - "nieodczytany" byłby fałszywym alarmem.
            if not (re.search(r"\bmodded\s+class\b", block)
                    or re.search(r"\bclass\s+(?!SCR_)[A-Z][A-Z0-9]{1,5}_\w+", block)):
                findings.append(f"plik '{path}' nie został odczytany w tej rozmowie - cytat niepotwierdzony")
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
            missing = [ln.strip() for ln in seg if len(_norm_code(ln)) >= 12 and _norm_code(ln) not in fnorm]
            if not missing:
                # krótkie linie (np. "return null;") sprawdzamy dopiero, gdy cały fragment nie pasuje do pliku
                missing = [ln.strip() for ln in seg if len(_norm_code(ln)) >= 6 and _norm_code(ln) not in fnorm]
            if missing:
                bad_lines.extend(missing)
            else:
                discontinuous = True
        if bad_lines:
            sample = "; ".join(f"`{ln[:80]}`" for ln in bad_lines[:2])
            findings.append(f"w bloku przypisanym do '{path}' nie znaleziono w pliku linii: {sample}")
        elif discontinuous:
            findings.append(f"blok przypisany do '{path}' łączy linie, które w pliku nie sąsiadują ze sobą")
        else:
            ok += 1
        # klasa o tej samej nazwie w odczytanych plikach, ale z inną klasą bazową
    for cm in re.finditer(r"\bclass\s+(\w+)\s*:\s*(\w+)", answer):
        cname, parent = cm.groups()
        for text in files.values():
            found = re.search(rf"\bclass\s+{re.escape(cname)}\s*:\s*(\w+)", text)
            if found and found.group(1) != parent:
                msg = (f"klasa '{cname}' dziedziczy w odczytanym pliku po '{found.group(1)}', "
                       f"a w odpowiedzi po '{parent}'")
                if msg not in findings:
                    findings.append(msg)
                break
    # Teza w prozie: "X dziedziczy po Y" vs deklaracja klasy w odczytanych plikach.
    for pm in re.finditer(r"[`*]*(\w+)[`*]*\s+dziedziczy\s+po\s+[`*]*(\w+)", answer):
        cname, parent = pm.groups()
        for text in files.values():
            found = re.search(rf"\bclass\s+{re.escape(cname)}\s*:\s*(\w+)", text)
            if found:
                if found.group(1) != parent:
                    msg = (f"klasa '{cname}' dziedziczy w odczytanym pliku po '{found.group(1)}', "
                           f"a w odpowiedzi po '{parent}'")
                    if msg not in findings:
                        findings.append(msg)
                break
    return findings, checked, ok


def _log_verification(findings: list[str], checked: int, ok: int) -> None:
    if findings:
        print(f"  [VERIFY] UWAGI ({len(findings)}); bloków sprawdzonych: {checked}, zgodnych: {ok}", flush=True)
        for item in findings:
            print(f"  [VERIFY]   - {item}", flush=True)
    else:
        print(f"  [VERIFY] OK; bloków sprawdzonych: {checked}, zgodnych: {ok}", flush=True)


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
    key = id(messages)
    meta = _SESSION_META.get(key)
    if meta is None:
        if len(_SESSION_META) >= _SESSION_FILES_MAX:
            _SESSION_META.pop(next(iter(_SESSION_META)))
        meta = _SESSION_META[key] = {"evidence": [], "chars": 0, "banned": set()}
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


def _api_problems(answer: str, meta: dict, files: dict[str, str]) -> list[str]:
    """Nazwy API w kodzie odpowiedzi, których nie potwierdzają wyniki narzędzi tej rozmowy."""
    texts = _evidence_texts(meta, files)
    banned = meta.get("banned", set())
    problems: list[str] = []
    for cls, meth, kind in _api_calls(answer):
        shown = (f"GetGame().{meth}" if kind == "game" else f"{cls}.{meth}" if cls else f"{meth}")
        if (cls and f"{cls}.{meth}" in banned) or meth in banned:
            problems.append(f"{shown}: kompilator zgłosił, że {cls + '.' if cls else ''}{meth} nie istnieje")
            continue
        if kind == "game":
            if not any(_find_class_method(texts, c, meth)[0] for c in _API_GAME_CLASSES):
                problems.append(f"{shown}: brak w wynikach narzędzi dla ArmaReforgerScripted i jej klas bazowych")
            continue
        if kind == "static":
            found, is_static = _find_class_method(texts, cls, meth)
            if not found:
                problems.append(f"{shown}: brak w wynikach narzędzi dla klasy {cls}")
            elif is_static is False:
                problems.append(f"{shown}: metoda instancji wywołana statycznie (wywołaj ją na obiekcie)")
            continue
        if not any(re.search(rf"\b{re.escape(meth)}\s*\(", t) for t in texts):
            problems.append(f"{shown}(): brak w wynikach narzędzi")
    return list(dict.fromkeys(problems))[:8]


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
    return list(dict.fromkeys(problems))[:6]


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
