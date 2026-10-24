# -*- coding: utf-8 -*-
"""Zestaw testowy asystenta Reforger (Ollama + Enfusion MCP BK).

Trzy polecenia:
  python reforger_eval.py questions
      Wypisuje pytania do wklejenia (jedna NOWA rozmowa na test; test A ma 2 pytania w jednej rozmowie).
      Od 2.0.0 w języku asystenta: REFORGER_LANG=en (albo "lang": "en" w settings.json) daje pytania po angielsku.
      Klucz odpowiedzi rozumie oba języki, a score rozpoznaje pytania polskie i angielskie.

  python reforger_eval.py score [assistant_web_data\\conversations.json] [--md wyniki.md]
      Ocenia odpowiedzi z zapisanych rozmów według klucza (wymagane elementy + znane błędy).
      Rozmowy rozpoznaje po treści pierwszego pytania, więc kilka podejść do tego samego testu
      jest automatycznie liczonych jako kolejne uruchomienia.

  python reforger_eval.py log log.txt
      Podsumowuje log serwera: liczba wywołań MCP, błędy, [REPAIR]/[DUP]/[STALL], puste odpowiedzi,
      szczyt kontekstu i czas każdej tury.

Klucz odpowiedzi pochodzi z prawdziwych plików gry (odczytanych przez MCP BK), a nie z pamięci.
Ocena automatyczna to wyrażenia regularne: łapie nazwy, pola i znane błędy. Nie ocenia sensu
zdań ani tego, czy kod się skompiluje. Traktuj ją jako szybki przegląd, a nie wyrok.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from reforger_i18n import EN, tr as L     # od 2.0.0: pytania i raport w języku asystenta (REFORGER_LANG / settings.json)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # starsze Pythony / przekierowania
    pass

I = re.I
S = re.S


def rx(pattern: str, flags: int = I | S):
    compiled = re.compile(pattern, flags)
    return lambda text: bool(compiled.search(text))


def all_of(*patterns: str):
    compiled = [re.compile(p, I | S) for p in patterns]
    return lambda text: all(c.search(text) for c in compiled)


def count_of(patterns: list[str], need: int):
    compiled = [re.compile(p, I | S) for p in patterns]
    def check(text: str) -> bool:
        return sum(1 for c in compiled if c.search(text)) >= need
    return check


def count_hits(patterns: list[str]):
    compiled = [re.compile(p, I | S) for p in patterns]
    return lambda text: sum(1 for c in compiled if c.search(text))


ALLOWED_ICONS = {"pick-up", "bipod", "not-available", "magazine", "availability-full"}


def invented_icon(text: str) -> bool:
    """m_sIconName spoza ikon znanych z Weapon_Base.et i bez oznaczenia 'WYMYSLONE/szkic' w tej linii."""
    for line in text.splitlines():
        m = re.search(r'm_sIconName\s+"([^"]+)"', line)
        if m and m.group(1) not in ALLOWED_ICONS and not re.search(r"wymy[sś]l|szkic|zast[aą]p|invented|replace|sketch", line, I):
            return True
    return False


NEGATION = re.compile(r"\bnie\b|\bbrak\b|\bbez\b|nieistniej|not found|does not exist|\bnot\b|\bno\b|\bwithout\b|n't\b", re.I)


_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
_GAME_LABEL = re.compile(r"z\s+kodu\s+gry|fragment\w*\s+z\s+gry|kod\s+z\s+gry"
                         r"|from\s+(?:the\s+)?game\s+code|(?:excerpt|fragment|snippet)\w*\s+from\s+(?:the\s+)?game"
                         r"|code\s+from\s+(?:the\s+)?game", re.I)
_PATH_ANY = re.compile(r"(?:scripts|prefabs|configs|ui)/[\w./\-{}]+\.(?:c|et|conf|layout|proto)|\w+\.(?:c|et)\b", re.I)


def game_label_without_file(text: str) -> bool:
    """Blok kodu poprzedzony etykietą 'z kodu gry' bez wskazanego pliku (ścieżka w pierwszych liniach bloku
    albo w tekście tuż przed blokiem); bloki opisane jako szkic/nowy plik pomijamy."""
    prev = 0
    for m in _FENCE_RE.finditer(text):
        gap = text[prev:m.start()]
        prev = m.end()
        if not _GAME_LABEL.search(gap[-220:]):
            continue
        head = "\n".join(m.group(1).split("\n")[:4])
        if _PATH_ANY.search(head) or _PATH_ANY.search(gap[-400:]):
            continue
        if re.search(r"szkic|nowy plik|nowa klasa|sketch|new file|new class", gap[-250:] + head, re.I):
            continue
        return True
    return False


def invented_weaponlog_file(text: str) -> bool:
    """Plik SCR_WeaponLogManager.c podany jak prawdziwe źródło: linia z przeczeniem, pytaniem
    ('sprawdź, czy istnieje') albo sugestią szukania nie jest twierdzeniem."""
    for line in text.splitlines():
        if (re.search(r"SCR_WeaponLogManager\.c", line, I) and not NEGATION.search(line)
                and not re.search(r"\bczy\b|sprawd[źz]|jeśli|jezeli|ewentualn|lub\s+`?SCR_WeaponLogManager\.et"
                                  r"|\bwhether\b|\bcheck|\bif\b|possibl|or\s+`?SCR_WeaponLogManager\.et", line, I)):
            return True
    return False


def has_disclaimer_for_getprefabname(text: str) -> bool:
    return bool(re.search(
        r"(nie istnieje|nie występuje|nie znaleziono|brak\s+(?:\w+\s+){0,3}metod"
        r"|nie\s+(?:ma|jest)\s+[^\n]{0,60}(GetPrefabName|zdefiniowan|dostępn|metod\w*)"
        r"|GetPrefabName[^\n]{0,80}nie\s+(?:jest|istnieje|ma)"
        # od 2.0.0: po angielsku
        r"|does not exist|doesn't exist|not found|no such method|there is no\s+[^\n]{0,60}(?:GetPrefabName|method)"
        r"|(?:is|are)\s+not\s+(?:a\s+)?(?:method|member|defined|available|part)"
        r"|IEntity\s+(?:does not|doesn't)\s+have|GetPrefabName[^\n]{0,80}(?:does not|doesn't|is not|isn't))", text, I))


def entity_getprefabname_call(text: str) -> bool:
    """Wywołanie X.GetPrefabName( na encji (IEntity tego nie ma). Linie z przeczeniem
    ('nie ma metody IEntity.GetPrefabName()') są pomijane, a EntityPrefabData i
    SCR_ResourceNameUtils są poprawnymi odbiorcami."""
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        window = ((lines[idx - 1] + " " if idx else "") + line
                  + (" " + lines[idx + 1] if idx + 1 < len(lines) else ""))   # zaprzeczenie bywa w następnej linii
        if NEGATION.search(window):
            continue
        for m in re.finditer(r"(\w+)\s*\.\s*GetPrefabName\s*\(", line):
            ident = m.group(1).lower()
            if ident.endswith("data") or ident.endswith("class") or ident == "scr_resourcenameutils":
                continue
            if "entity" in ident or ident in ("owner", "ent", "e", "player", "weapon"):
                return True
    return False


def invented_line_numbers(text: str) -> bool:
    """Od 1.8.9: o numerach linii decyduje silnik. Sprawdza je per plik względem widoków, które model naprawdę
    oglądał (game_read z line_start/line_end albo query), i oznacza niepotwierdzone w treści:
    "⚠(numer linii niepotwierdzony)". Wcześniejsza heurystyka (każde "linia N" bez przepisanego widoku) dawała
    fałszywe alarmy dla numerów potwierdzonych przez silnik. Odpowiedzi sprzed 1.8.7 nie mają oznaczeń."""
    return ("numer linii niepotwierdzony" in text      # oznaczenie 1.8.7-1.9.3
            or bool(re.search(r"(?:lini|line)\w*\s*\**\s*\d+(?:\s*[-‑–]\s*\d+)?\s*\**\s*⚠", text, re.I)))   # od 1.9.4: " ⚠"


def default_as_inspection(text: str) -> bool:
    """'default' opisany jako tryb inspekcji. Nie liczymy poprawnego rozumowania: kontekst 'default',
    a widoczność w inspekcji zapewnia CanBeShownScript klasy SCR_InspectionUserAction."""
    for m in re.finditer(r"default[^\n]{0,60}(tryb\w*\s+inspekcj|czyli\s+w\s+trybie|inspection\s+mode|i\.e\.\s+in\s+(?:the\s+)?inspection"
                         r"|(?:active|used)\s+(?:during|in|while)\s+(?:the\s+)?inspect|while\s+inspecting)",
                         text, re.I):
        if not re.search(r"CanBeShown", m.group(0)):
            return True
    return False


def recommends_scr_prefix(text: str) -> bool:
    """Zalecenie prefiksu SCR_ dla moda. Od 1.8.6 nie liczymy zdań, które opisują SCR_ jako prefiks gry albo
    każą użyć własnego tagu ZAMIAST SCR_ (np. "w bazie gry skrypty mają prefiks SCR_ ... użyj MY_ zamiast SCR_")."""
    for m in re.finditer(r"(prefiks\w*|zaczyna\w*\s+od|użyj\w*|prefix\w*|start\w*\s+with|\buse)\s+[^\n]{0,20}SCR_", text, re.I):
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line = text[line_start:line_end if line_end >= 0 else len(text)]
        if not re.search(r"zamiast|w\s+bazie\s+gry|gry\s+maj|prefiks\w*\s+gry|zarezerwowan|nie\s+używ"
                         r"|instead\s+of|the\s+game'?s?\b|of\s+the\s+game|vanilla|reserved|Bohemia|do\s+not\s+use|don't\s+use"
                         r"|never\s+use|not\s+use", line, re.I):
            return True
    return False


def scr_example_without_caveat(text: str) -> bool:
    """Przykładowe nazwy moda z prefiksem SCR_ bez zastrzeżenia, że SCR_ należy do gry.
    Od 2.0.0 nie liczymy cytowanych plików gry (np. "przykład z `SCR_ScoringSystemComponent.c`" - test J 1.9.4),
    tylko nazwy wyglądające na przykład moda (SCR_My..., SCR_Example...) albo sam prefiks `SCR_` w przykładzie."""
    example = re.search(r"(?:np\.|e\.g\.|przykład\w*|example\w*)[^\n]{0,40}`?SCR_(?:`|(?:My|Example|Mod|Custom|Test|Your|Twoj)\w*)"
                        r"|class\s+SCR_(?:My|Example|Mod|Custom|Test|Your|Twoj)\w*|SCR_(?:MyObject|Example\w*)", text, I)
    caveat = re.search(r"SCR_[^\n]{0,120}(Bohemi|\bBI\b|zarezerwowan|należy do gry|prefiks gry|nie\s+używ|wbudowan|w\s+gr[ęy]\b|gry\b"
                       r"|zamiast|instead\s+of|reserved|belongs\s+to\s+the\s+game|the\s+game'?s?\b|vanilla|do\s+not\s+use|don't\s+use"
                       r"|built-in)", text, I)
    return bool(example) and not caveat


# Błędy, które wystąpiły w różnych testach (sprawdzane w KAŻDEJ odpowiedzi).
COMMON_BAD = [
    (L("blok oznaczony 'z kodu gry' bez wskazania pliku (kod własny opisany jako cytat z gry)",
       "block labelled 'from game code' without a file (own code described as a game quote)"), game_label_without_file),
    (L("wymyślony poziom LogLevel (są: SPAM, VERBOSE, DEBUG, NORMAL, WARNING, ERROR, FATAL)",
       "invented LogLevel value (there are: SPAM, VERBOSE, DEBUG, NORMAL, WARNING, ERROR, FATAL)"),
     rx(r"LogLevel\.(?!(?:SPAM|VERBOSE|DEBUG|NORMAL|WARNING|ERROR|FATAL)\b|c\b)\w+", I)),
    (L("nieistniejąca klasa bazowa SCR_Component", "non-existent base class SCR_Component"), rx(r":\s*SCR_Component\b")),
    (L("operator ?. (nie widziałem go w Enforce Script - podejrzane)", "operator ?. (not seen in Enforce Script - suspicious)"),
     rx(r"\)\s*\?\s*\.\s*\w")),
    (L("'w pełni zweryfikowane' (nadmierna pewność)", "'fully verified' (overconfidence)"),
     rx(r"w pełni zweryfikowan|fully verified")),
    (L("numery linii w plikach (game_read ich nie zwraca - wymysł)", "line numbers in files (game_read does not return them - invented)"),
     invented_line_numbers),
    # od 1.8.7
    (L("rozumowanie modelu (po angielsku) w treści odpowiedzi", "model reasoning in the answer text"),
     rx(r"\bWe need to (?:answer|show|provide|find)|Let's craft (?:the )?answer")),
    (L("wpis prefabu .et zapisany jako JSON", ".et prefab entry written as JSON"), rx(r'"(?:ParentContextList|UIInfo|ContextName)"\s*:')),
    (L("nowa klasa moda z prefiksem SCR_ (prefiks gry)", "new mod class with the SCR_ prefix (the game's prefix)"),
     rx(r"\bclass\s+SCR_(?:My|Log|Custom|Print|Example|Mod|Test)\w*")),
    (L("wywołanie z parametrem typu .Cast<T>() (nie istnieje w Enforce Script)",
       "call with a type parameter .Cast<T>() (does not exist in Enforce Script)"), rx(r"\.\s*Cast\s*<\s*\w+\s*>\s*\(")),
    # od 1.8.8
    (L("PrintFormat ze znacznikami %s/%d (Enforce Script używa %1..%9)", "PrintFormat with %s/%d (Enforce Script uses %1..%9)"),
     rx(r'PrintFormat\s*\(\s*"[^"\n]*%[sdifx]')),
]


def entry_class_mismatch(text: str) -> bool:
    """Wpis w .et z inną klasą niż nowa klasa w skrypcie tej samej odpowiedzi (TAG_X w skrypcie, SCR_X we wpisie)."""
    new = set(re.findall(r"^\s*class\s+([A-Za-z_]\w*)\s*:", text, re.M))
    for entry in re.findall(r'^\s*([A-Za-z_]\w*)\s+"\{', text, re.M):
        if entry not in new and any(c != entry and c.split("_", 1)[-1] == entry.split("_", 1)[-1] for c in new):
            return True
    return False


# Pułapka muzzle: typ lufy opisany jako magazynek/amunicja (PL i EN).
MUZZLE_AS_MAGAZINE = (r"(typ\w*|zależności od typu)\s+(magazyn|municj)"
                      r"|(?:type|depending on the type)\s+of\s+(?:the\s+)?(?:magazine|ammunition|ammo)\b")


# ---------------------------------------------------------------------------------------------
# TESTY. Każdy test: lista pytań (tur) i reguły na odpowiedź KAŻDEJ tury.
# turns: pytania po polsku, turns_en: te same pytania po angielsku (od 2.0.0); klucz rozumie oba języki.
# must: (etykieta, funkcja)  -> pożądane; ocena = ile spełnionych.
# bad : (etykieta, funkcja)  -> znane błędy; każde trafienie to naruszenie.
# ---------------------------------------------------------------------------------------------
Q_A1 = """Chcę dodać własną akcję użytkownika do broni, jako override prefabu
Weapon_Base w moim modzie. Znajdź w grze istniejącą akcję użytkownika
na broni (np. safety albo tryb ognia) i na jej podstawie wyjaśnij:

1. Który prefab i jakie pola ActionsManagerComponent definiują akcje
   i konteksty broni?
2. Po jakiej klasie dziedziczy ta akcja i które metody nadpisuje?
3. Jak taka akcja jest podpięta w prefabie i jak wiąże się z kontekstem?

Odpowiedz w trzech sekcjach: "Z kodu" (z nazwą pliku przy każdym
twierdzeniu), "Wnioski (niezweryfikowane)", "Czego nie sprawdzono".
Nie podawaj kodu ani pól, których nie było w odczytanych plikach."""

Q_A2 = """Na podstawie tego, co ustaliłeś, zaproponuj własną akcję użytkownika
dla broni: po wybraniu wypisuje do logu nazwę prefabu broni, na której
została użyta. Ma być widoczna tylko w trybie inspekcji broni.
Podaj (1) klasę Enforce Script, (2) wpis do additionalActions w moim
override Weapon_Base.et. Każdy element oznacz: "z kodu gry (plik)"
albo "szkic". Zaznacz, czego nie da się zweryfikować bez uruchomienia
Workbencha."""

Q_A1_EN = """I want to add my own user action to a weapon, as an override of the
Weapon_Base prefab in my mod. Find an existing user action on a weapon
in the game (e.g. safety or fire mode) and based on it explain:

1. Which prefab and which ActionsManagerComponent fields define the
   weapon's actions and contexts?
2. Which class does this action inherit from and which methods does it override?
3. How is such an action hooked up in the prefab and how is it tied to a context?

Answer in three sections: "From code" (with the file name for every
claim), "Conclusions (unverified)", "Not checked".
Do not give code or fields that were not in the files you read."""

Q_A2_EN = """Based on what you found, propose my own user action for a weapon:
when selected, it writes the name of the weapon prefab it was used on
to the log. It must be visible only in weapon inspection mode.
Give (1) the Enforce Script class, (2) the additionalActions entry in my
Weapon_Base.et override. Label every element: "from game code (file)"
or "sketch". Note what cannot be verified without running
Workbench."""

TESTS = [
    {
        "id": "A",
        "name": L("Akcja na broni (2 tury: badanie, potem własny kod)", "Weapon action (2 turns: research, then own code)"),
        "turns": [Q_A1, Q_A2],
        "turns_en": [Q_A1_EN, Q_A2_EN],
        "rules": [
            {   # tura 1
                "must": [
                    (L("prefab Weapon_Base.et", "prefab Weapon_Base.et"), rx(r"Weapon_Base\.et")),
                    (L("konteksty default/bipod/magazine/firemode", "contexts default/bipod/magazine/firemode"),
                     all_of(r"firemode", r"bipod", r"magazine")),
                    ("additionalActions", rx(r"additionalActions")),
                    ("ParentContextList", rx(r"ParentContextList")),
                    (L("klasa bazowa SCR_InspectionUserAction", "base class SCR_InspectionUserAction"), rx(r"SCR_InspectionUserAction")),
                    (L("łańcuch SCR_InventoryAction -> ScriptedUserAction", "chain SCR_InventoryAction -> ScriptedUserAction"),
                     all_of(r"SCR_InventoryAction", r"ScriptedUserAction")),
                    (L("4 nadpisania Toggle Safety", "4 Toggle Safety overrides"),
                     all_of(r"PerformAction", r"CanBeShownScript", r"GetActionNameScript", r"\bInit\b")),
                ],
                "bad": [
                    (L("muzzle przetłumaczone jako magazyn/municja", "muzzle translated as magazine/ammunition"),
                     rx(MUZZLE_AS_MAGAZINE + r"|aktualny\s+magazyn|(?:odpowiedni|właściw)\w*\s+magazyn|sprawdza[^\n]{0,60}magazyn")),
                    (L("'w pełni zweryfikowane' mimo sekcji Wnioski", "'fully verified' despite the Conclusions section"),
                     rx(r"w pełni zweryfikowan|fully verified")),
                    (L("XML zamiast formatu .et", "XML instead of the .et format"), rx(r"<ActionsManagerComponent|<additionalActions")),
                    (L("wymyślona tablica 'Actions'", "invented 'Actions' array"),
                     rx(r"tablic\w*\s+Actions\b|\bActions\s+array|array\s+(?:called\s+)?`?Actions`?\b")),
                    (L("IsSafetyOn jako prywatna", "IsSafetyOn as private"),
                     rx(r"IsSafetyOn[^\n]{0,40}(?:prywatn|private)|(?:prywatn\w*|private)[^\n]{0,25}IsSafetyOn")),
                ],
            },
            {   # tura 2
                "must": [
                    (L("dziedziczy po SCR_InspectionUserAction", "inherits from SCR_InspectionUserAction"),
                     rx(r"class\s+\w+\s*:\s*SCR_InspectionUserAction")),
                    (L("poprawna sygnatura PerformAction(IEntity, IEntity)", "correct signature PerformAction(IEntity, IEntity)"),
                     rx(r"PerformAction\(\s*IEntity\s+pOwnerEntity\s*,\s*IEntity\s+pUserEntity\s*\)")),
                    (L("nazwa prefabu przez istniejące API", "prefab name through an existing API"),
                     rx(r"SCR_ResourceNameUtils\.GetPrefabName\(\s*pOwnerEntity|GetPrefabData\(\)\s*\.\s*GetPrefabName|EntityPrefabData")),
                    (L("globalne Print( lub PrintFormat(", "global Print( or PrintFormat("), rx(r"(?<![\w.])(?:Print|PrintFormat)\s*\(")),
                    (L("ParentContextList w wpisie", "ParentContextList in the entry"), rx(r"ParentContextList")),
                    ("UIInfo SCR_ActionUIInfo", rx(r"SCR_ActionUIInfo")),
                    (L("uwaga o efekcie lokalnym", "note about the local effect"),
                     rx(r"HasLocalEffectOnly|tylko lokaln|efekt lokaln|lokalny efekt|local effect|only locally|locally only|local only")),
                ],
                "bad": [
                    (L("pOwnerEntity.GetPrefabName() (nie istnieje na IEntity)", "pOwnerEntity.GetPrefabName() (does not exist on IEntity)"),
                     rx(r"pOwnerEntity\s*\.\s*GetPrefabName\s*\(")),
                    ("GetPrefabName(this)", rx(r"GetPrefabName\(\s*this\s*\)")),
                    (L("logowanie przez SCR_AddonManager/_print", "logging through SCR_AddonManager/_print"),
                     rx(r"SCR_AddonManager|\b_print\s*\(")),
                    (L("XML zamiast formatu .et", "XML instead of the .et format"), rx(r"<ActionsManagerComponent|<additionalActions|<action>")),
                    (L("ponowna deklaracja m_WeaponComponent", "m_WeaponComponent declared again"),
                     rx(r"protected\s+BaseWeaponComponent\s+m_WeaponComponent")),
                    (L("wymyślona ikona bez oznaczenia", "invented icon without a label"), invented_icon),
                    (L("'default' jako 'tryb inspekcji'", "'default' as 'inspection mode'"), default_as_inspection),
                    (L("log opisany jako serwerowy (akcja ma efekt lokalny)", "log described as server-side (the action has a local effect)"),
                     rx(r"(Logujemy|wypisze|Print|logs?\b|prints?\b)[^\n]{0,80}(na serwerze|konsol\w+ serwera|on the server|server console)"
                        r"|(na serwerze|konsol\w+ serwera|on the server|server console)[^\n]{0,80}Print")),
                    (L("klasa we wpisie .et inna niż klasa w skrypcie", "class in the .et entry differs from the script class"),
                     entry_class_mismatch),
                ],
            },
        ],
    },
    {
        "id": "B",
        "name": L("Logowanie / funkcje globalne (Print)", "Logging / global functions (Print)"),
        "turns": ["Jak wypisać komunikat do logu w skrypcie Enforce Script? Podaj składnię, sposób użycia "
                  "poziomu logowania i krótki przykład. Zaznacz, skąd masz tę informację."],
        "turns_en": ["How do I write a message to the log in an Enforce Script script? Give the syntax, how to use "
                     "the log level and a short example. Say where you got this information from."],
        "rules": [{
            "must": [
                ("Print(", rx(r"(?<![\w.])Print\s*\(")),
                ("PrintFormat", rx(r"PrintFormat")),
                ("LogLevel", rx(r"LogLevel")),
                (L("placeholdery %1", "placeholders %1"), rx(r"%1")),
                (L("podane źródło (wiki/plik)", "source given (wiki/file)"), rx(r"community\.bistudio|wiki|Scripting|\.c\b")),
            ],
            "bad": [
                ("SCR_AddonManager/_print", rx(r"SCR_AddonManager|\b_print\s*\(")),
                (L("Print jako metoda klasy testowej SCR_Autotest* (to nie globalna funkcja logowania)",
                   "Print as a method of the test class SCR_Autotest* (not the global logging function)"),
                 rx(r"SCR_Autotest\w+\.Print\s*\(|Print[^\n]{0,40}(?:z\s+klasy|from\s+(?:the\s+)?(?:class\s+)?)\s*`?SCR_Autotest")),
                (L("wymyślone API logowania", "invented logging API"),
                 rx(r"\b(Debug\.Print|System\.Print|Log\.(Info|Debug|Warn)|printf\s*\(|console\.log|SCR_Log)")),
                (L("Log(prefix, level) klas UIInfo podane jako ogólne logowanie (to metoda instancji)",
                   "Log(prefix, level) of UIInfo classes given as general logging (it is an instance method)"), rx(r"\bSCR_\w+\.Log\s*\(")),
                (L("zaprzecza istnieniu poziomów logowania (jest enum LogLevel)", "denies that log levels exist (there is the LogLevel enum)"),
                 rx(r"nie ma wbudowan\w*\s+(?:mechanizm\w*\s+)?[„\"]?poziom|poziom\w* logowania nie są wbudowan|brak poziomów logowania"
                    r"|no\s+built-in\s+(?:log(?:ging)?\s+)?levels?|log(?:ging)?\s+levels\s+are\s+not\s+built|there\s+are\s+no\s+(?:log(?:ging)?\s+)?levels")),
            ],
        }],
    },
    {
        "id": "C",
        "name": L("Eventy ScriptedUserAction (lista z kodu)", "ScriptedUserAction events (list from code)"),
        "turns": ["Wymień wszystkie eventy ScriptedUserAction z sygnaturami i krótko napisz, kiedy są "
                  "wywoływane. Opieraj się wyłącznie na komentarzach z kodu gry i podaj plik."],
        "turns_en": ["List all ScriptedUserAction events with their signatures and briefly say when they are "
                     "called. Rely only on the comments from the game code and give the file."],
        "rules": [{
            "must": [
                (L("plik ScriptedUserAction.c", "file ScriptedUserAction.c"), rx(r"generated/UserAction/ScriptedUserAction\.c")),
                (L("15 eventów (min. 13)", "15 events (at least 13)"), count_of([
                    r"\bInit\b", r"\bPerformAction\b", r"PerformContinuousAction", r"\bOnConfirmed\b", r"\bOnRejected\b",
                    r"OnActionCanceled", r"OnActionStart", r"GetActionNameScript", r"GetActionDescriptionScript",
                    r"CanBePerformedScript", r"CanBeShownScript", r"HasLocalEffectOnlyScript",
                    r"CheckOnServerFirstScript", r"CanBroadcastScript", r"GetActionProgressScript"], 13)),
                (L("domyślny postęp fProgress + timeSlice", "default progress fProgress + timeSlice"),
                 rx(r"fProgress\s*\+\s*timeSlice|dodaje\s+`?timeSlice|timeSlice[^\n]{0,50}(dodaj|do bieżącego)"
                    r"|adds\s+`?timeSlice|timeSlice[^\n]{0,50}(add|to the current)")),
            ],
            "bad": [
                (L("metody BaseUserAction przypisane do ScriptedUserAction", "BaseUserAction methods attributed to ScriptedUserAction"),
                 rx(r"ScriptedUserAction[^\n]{0,120}(GetContextIndex|SetActiveContext)")),
                (L("'Init rejestruje akcję'", "'Init registers the action'"),
                 rx(r"Init[^\n]{0,80}rejestruj\w*\s+akcj|Init[^\n]{0,80}registers?\s+the\s+action")),
            ],
        }],
    },
    {
        "id": "D",
        "name": L("UserActionContext (API + prefab)", "UserActionContext (API + prefab)"),
        "turns": ["Czym jest UserActionContext, jakie pola ma w prefabie Weapon_Base i jakie metody ma w API? "
                  "Podaj źródła."],
        "turns_en": ["What is UserActionContext, which fields does it have in the Weapon_Base prefab and which methods "
                     "does it have in the API? Give the sources."],
        "rules": [{
            "must": [
                (L("pola prefabu ContextName/Position/Radius", "prefab fields ContextName/Position/Radius"),
                 all_of(r"ContextName", r"Radius", r"Position")),
                (L("PointInfo albo SCR_ActionContextUIInfo", "PointInfo or SCR_ActionContextUIInfo"), rx(r"PointInfo|SCR_ActionContextUIInfo")),
                ("API GetContextName/GetRadius", all_of(r"GetContextName", r"GetRadius")),
                ("API IsOmnidirectional/GetHeight/IsCapsule", rx(r"IsOmnidirectional|GetHeight|IsCapsule")),
                ("GetActionsList", rx(r"GetActionsList")),
                (L("opis: kolekcja akcji w ActionsManagerComponent", "description: a collection of actions in ActionsManagerComponent"),
                 rx(r"(kolekcj|zbi[oó]r|grup|collection|group|set\s+of)\w*[^\n]{0,80}(?:akcj|action)|ActionsManagerComponent")),
            ],
            "bad": [
                (L("XML zamiast formatu .et", "XML instead of the .et format"), rx(r"<UserActionContext|<ActionContexts")),
            ],
        }],
    },
    {
        "id": "E",
        "name": L("WeaponComponent w prefabie (konfiguracja)", "WeaponComponent in the prefab (configuration)"),
        "turns": ["Jak w prefabie Weapon_Base skonfigurowany jest komponent WeaponComponent? Wymień pola "
                  "i ich wartości, które widać w pliku."],
        "turns_en": ["How is the WeaponComponent component configured in the Weapon_Base prefab? List the fields "
                     "and their values that are visible in the file."],
        "rules": [{
            "must": [
                ("WeaponSlotType primary", all_of(r"WeaponSlotType", r"primary")),
                ("obstructionTestBBScale", rx(r"obstructionTestBBScale")),
                ("sightsCameraRollScaler", rx(r"sightsCameraRollScaler")),
                ("WeaponUIInfo / box.conf", rx(r"WeaponUIInfo|box\.conf|m_MagIndicator")),
                ("SightsComponent / WeaponAnimationComponent", rx(r"SightsComponent|WeaponAnimationComponent")),
                (L("ścieżka Weapon_Base.et", "path Weapon_Base.et"), rx(r"Weapon_Base\.et")),
            ],
            "bad": [
                (L("pola/komponenty spoza tego prefabu", "fields/components from outside this prefab"),
                 rx(r"fire\s*rate|MuzzleComponent|BaseMuzzleComponent|magazine\s*well|m_fFireRate")),
                (L("XML zamiast formatu .et", "XML instead of the .et format"), rx(r"<WeaponComponent")),
            ],
        }],
    },
    {
        "id": "F",
        "name": L("Init w SCR_ToggleSafetyUserAction (pułapka muzzle/magazyn)", "Init in SCR_ToggleSafetyUserAction (muzzle/magazine trap)"),
        "turns": ["Co robi Init w SCR_ToggleSafetyUserAction w zależności od atrybutu m_eMuzzleType? Opisz "
                  "każdą gałąź i wyjaśnij, po co ta akcja ma ten atrybut."],
        "turns_en": ["What does Init in SCR_ToggleSafetyUserAction do depending on the m_eMuzzleType attribute? Describe "
                     "each branch and explain why this action has this attribute."],
        "rules": [{
            "must": [
                ("MT_BaseMuzzle", rx(r"MT_BaseMuzzle")),
                ("MT_UGLMuzzle", rx(r"MT_UGLMuzzle")),
                ("m_WeaponComponent", rx(r"m_WeaponComponent")),
                ("m_AttachmentStorage", rx(r"m_AttachmentStorage")),
                ("WeaponAttachmentsStorageComponent", rx(r"WeaponAttachmentsStorageComponent")),
                (L("mowa o lufie/wyrzutni (muzzle)", "mentions the barrel/launcher (muzzle)"),
                 rx(r"luf\w+|wyrzutni|granatnik|UGL|muzzle|barrel|launcher")),
            ],
            "bad": [
                (L("muzzle przetłumaczone jako magazyn/municja", "muzzle translated as magazine/ammunition"),
                 rx(MUZZLE_AS_MAGAZINE + r"|typ\s+magazyn")),
                (L("Init rzekomo ustawia m_eMuzzleType", "Init supposedly sets m_eMuzzleType"),
                 rx(r"Init[^\n]{0,80}(?:ustawia|sets)[^\n]{0,40}m_eMuzzleType")),
            ],
        }],
    },
    {
        "id": "G",
        "name": L("Sprawdzenie trybu inspekcji (krótki fragment kodu)", "Inspection mode check (short code excerpt)"),
        "turns": ["Jak w skrypcie sprawdzić, czy postać gracza jest w trybie inspekcji broni? Pokaż fragment "
                  "kodu z gry i podaj plik."],
        "turns_en": ["How do I check in a script whether the player character is in weapon inspection mode? Show an "
                     "excerpt of game code and give the file."],
        "rules": [{
            "must": [
                ("CharacterControllerComponent", rx(r"CharacterControllerComponent")),
                ("GetInspect()", rx(r"GetInspect\s*\(\s*\)")),
                ("FindComponent + Cast", all_of(r"FindComponent", r"\.Cast\s*\(")),
                (L("plik SCR_InspectionUserAction/ToggleSafety", "file SCR_InspectionUserAction/ToggleSafety"),
                 rx(r"SCR_InspectionUserAction\.c|SCR_ToggleSafetyUserAction\.c")),
            ],
            "bad": [
                (L("GetComponent<T>() (to nie jest API Enforce Script; jest FindComponent + Cast)",
                   "GetComponent<T>() (not Enforce Script API; it is FindComponent + Cast)"), rx(r"\bGetComponent\s*<")),
                (L("FindComponent(...).Cast<T>() (nieprawidłowa składnia)", "FindComponent(...).Cast<T>() (invalid syntax)"),
                 rx(r"FindComponent\([^)]*\)\s*\.\s*Cast\s*<")),
                (L("zła klasa bazowa SCR_CharacterControllerComponent (jest CharacterControllerComponent)",
                   "wrong base class SCR_CharacterControllerComponent (it is CharacterControllerComponent)"),
                 rx(r"class\s+SCR_CharacterControllerComponent\s*:\s*(?!CharacterControllerComponent\b)\w+")),
                (L("m_bInspectionFocus użyte zamiast GetInspect() (pole protected: fokus podglądu, nie stan trybu)",
                   "m_bInspectionFocus used instead of GetInspect() (protected field: view focus, not the mode state)"),
                 rx(r"\b[a-z]\w*\.m_bInspectionFocus|(?:użyć|użycie|sprawdz|use|using|check)\w*[^\n]{0,70}m_bInspectionFocus")),
                (L("m_bInspectionFocus opisane jako 'tryb inspekcji' (to fokus podglądu, nie stan trybu)",
                   "m_bInspectionFocus described as 'inspection mode' (it is the view focus, not the mode state)"),
                 rx(r"m_bInspectionFocus[^\n]{0,90}(tryb\w*\s+inspekcj|jest w trybie|czy postać|inspection\s+mode|is\s+in\s+(?:the\s+)?inspection"
                    r"|whether\s+the\s+character)")),
                (L("wymyślone API inspekcji", "invented inspection API"),
                 lambda t: bool(re.search(r"\b(GetIsInspecting|IsInspecting|IsInspect)\s*\(|\bInspectionComponent\b", t))),
                (L("GetInspect przypisany do SCR_CharacterControllerComponent.c / .proto (plik .c go nie zawiera)",
                   "GetInspect attributed to SCR_CharacterControllerComponent.c / .proto (the .c file does not contain it)"),
                 rx(r"SCR_CharacterControllerComponent\.c[\s\S]{0,300}proto external"
                    r"|(zadeklarowan\w*|zdefiniowan\w*|definicj\w*|declared|defined|definition)[^\n]{0,80}SCR_CharacterControllerComponent\.c"
                    r"|SCR_CharacterControllerComponent\.c[\s\S]{0,250}\.proto")),
            ],
        }],
    },
    {
        "id": "H",
        "name": L("Fałszywa przesłanka: IEntity.GetPrefabName()", "False premise: IEntity.GetPrefabName()"),
        "turns": ["Jak użyć metody IEntity.GetPrefabName() żeby pobrać nazwę prefabu encji? Podaj przykład."],
        "turns_en": ["How do I use the IEntity.GetPrefabName() method to get the prefab name of an entity? Give an example."],
        "rules": [{
            "must": [
                (L("zaznacza, że takiej metody nie ma na IEntity", "says that IEntity has no such method"), has_disclaimer_for_getprefabname),
                (L("wskazuje działającą alternatywę", "points to a working alternative"),
                 rx(r"SCR_ResourceNameUtils\.GetPrefabName|GetPrefabData\s*\(\s*\)\s*\.\s*GetPrefabName|EntityPrefabData")),
            ],
            "bad": [
                (L("wywołanie GetPrefabName() na encji (nie istnieje na IEntity)", "GetPrefabName() called on an entity (does not exist on IEntity)"),
                 entity_getprefabname_call),
                (L("encja rzutowana na GenericEntityClass (to klasa danych prefabu, nie encja)",
                   "entity cast to GenericEntityClass (that is the prefab data class, not the entity)"),
                 rx(r"GenericEntityClass\s+\w+\s*=\s*(?:(?:Class|GenericEntityClass)\.Cast\(\s*\w*[eE]ntity|\w*[eE]ntity\s*\.\s*Cast\s*<)")),
                (L("GetPrefab() przypisane do ResourceName (GetPrefab zwraca BaseContainer)",
                   "GetPrefab() assigned to ResourceName (GetPrefab returns BaseContainer)"),
                 rx(r"ResourceName\s+\w+\s*=\s*[^;\n]*\.GetPrefab\s*\(\s*\)\s*;")),
            ],
        }],
    },
    {
        "id": "I",
        "name": L("Fałszywa przesłanka: nieistniejąca klasa SCR_WeaponLogManager", "False premise: the non-existent class SCR_WeaponLogManager"),
        "turns": ["Jak działa klasa SCR_WeaponLogManager i jakie ma metody? Podaj plik źródłowy."],
        "turns_en": ["How does the SCR_WeaponLogManager class work and which methods does it have? Give the source file."],
        "rules": [{
            "must": [
                (L("informuje, że klasy nie znaleziono", "says that the class was not found"),
                 rx(r"(nie (znaleziono|istnieje|ma|udało (mi )?się (znaleźć|odnaleźć))|brak (takiej )?klas|nie występuje|nie jest zdefiniowan"
                    r"|not found|does not exist|doesn['’]t exist|could not (?:find|locate)|couldn['’]t (?:find|locate)|no such class"
                    r"|is not defined|there is no\s+[^\n]{0,60}class|(?:is|was) not (?:found|present)|no matching)")),
            ],
            "bad": [
                (L("wymyślony plik SCR_WeaponLogManager.c (bez przeczenia)", "invented file SCR_WeaponLogManager.c (without a negation)"),
                 invented_weaponlog_file),
                (L("opisuje klasę, jakby istniała", "describes the class as if it existed"),
                 rx(r"SCR_WeaponLogManager\W{0,6}(ma|zawiera|definiuje|dziedziczy|udostępnia|oferuje"
                    r"|(?:has|contains|defines|inherits|provides|offers|exposes)\b)")),
                (L("podstawia inną klasę (SCR_AddonManager itp.)", "substitutes another class (SCR_AddonManager etc.)"),
                 rx(r"SCR_AddonManager|SCR_CameraManager|SCR_ChatPanelManager")),
                (L("cytuje 'api_search(...) -> brak wyników' (api_search zwraca rozmyte trafienia, nigdy 'brak')",
                   "quotes 'api_search(...) -> no results' (api_search returns fuzzy matches, never 'nothing')"),
                 rx(r"api_search\([^)]*\)\s*(→|->|=>)\s*(?:brak|no\s+results|nothing|none)")),
            ],
        }],
    },
    {
        "id": "J",
        "name": L("Prefiks modderski i katalogi skryptów (wiki)", "Modder prefix and script folders (wiki)"),
        "turns": ["Jakie prefiksy powinny mieć nazwy plików i klas w moim modzie i w jakich katalogach muszą "
                  "leżeć skrypty, żeby gra je załadowała? Podaj źródło."],
        "turns_en": ["Which prefixes should the file and class names in my mod have, and in which folders must "
                     "the scripts be placed so that the game loads them? Give the source."],
        "rules": [{
            "must": [
                (L("prefiks / modder tag", "prefix / modder tag"), rx(r"prefiks|prefix|tag\b|TAG_|ABC_")),
                (L("podane źródło (wiki)", "source given (wiki)"),
                 rx(r"community\.bistudio|wiki|Scripting[:_ ]+_?Conventions|Scripting[ _]Modding|Scripting[ _]Example|Conventions")),
                (L("SCR_ to prefiks gry, mod ma własny tag", "SCR_ is the game's prefix, a mod has its own tag"),
                 rx(r"SCR_[^\n]{0,120}(Bohemia|\bBI\b|zarezerwowan|gr[ęay]\b|wbudowan|własn\w+\s+tag|nie\s+używ"
                    r"|reserved|the\s+game'?s?\b|of\s+the\s+game|vanilla|built-in|own\s+tag|do\s+not\s+use|don't\s+use)"
                    # od 2.0.2 także zastrzeżenie przed nazwą: "must not be the vanilla prefix SCR_"
                    r"|(?:vanilla|reserved|game's|Bohemia|must\s+\**not\**\s+be|do\s+not\s+use|don't\s+use|instead\s+of)[^\n]{0,40}SCR_")),
            ],
            # Od 1.8.4: tej wiedzy nie ma w danych BK (wiki BK nie opisuje modułów skryptów), więc nie wlicza się
            # do wyniku; pokazujemy ją osobno.
            "bonus": [
                (L("katalogi Game i GameCode", "folders Game and GameCode"), all_of(r"\bGame\b", r"GameCode")),
                (L("skrypty poza modułami są ignorowane", "scripts outside the modules are ignored"),
                 rx(r"ignor|pomijan|nie zostan|nie będ\w+ załadowan|skipped|not\s+(?:be\s+)?loaded|won't\s+be\s+loaded")),
            ],
            "bad": [
                (L("zaleca prefiks SCR_ dla modów", "recommends the SCR_ prefix for mods"), recommends_scr_prefix),
                (L("przykłady z prefiksem SCR_ (prefiks gry) bez zastrzeżenia", "examples with the SCR_ prefix (the game's prefix) without a caveat"),
                 scr_example_without_caveat),
                (L("folder scripts/Game jako jedyny / wymyślona ścieżka Mods/<...>/", "scripts/Game as the only folder / invented path Mods/<...>/"),
                 rx(r"jedynym katalogiem|Mods/<|wszystkie[^\n]{0,50}(?:muszą|powinny)\s+(?:się\s+)?znajdować\s+się[^\n]{0,30}scripts/Game/?[`\s.]"
                    r"|poza\s+tą\s+ścieżką\s+nie\s+zostan"
                    r"|the\s+only\s+(?:folder|directory|place|location)"
                    r"|all[^\n]{0,50}(?:must|should)\s+(?:be\s+(?:placed\s+|located\s+)?in|live\s+(?:in|under))[^\n]{0,30}scripts/Game/?[`\s.]"
                    r"|outside\s+(?:this|that)\s+(?:path|folder)[^\n]{0,30}\bnot\b")),
            ],
        }],
    },
]


def norm(text: str) -> str:
    return " ".join(text.split())


def match_test(first_question: str):
    """(test, pytania w języku rozmowy) albo (None, None). Od 2.0.0 rozpoznaje pytania polskie i angielskie."""
    q = norm(first_question)
    for test in TESTS:
        for key in ("turns", "turns_en"):
            if q.startswith(norm(test[key][0])[:80]):
                return test, test[key]
    return None, None


def cmd_questions() -> None:
    print(L("Każdy test = NOWA rozmowa. Test A ma dwa pytania w tej samej rozmowie (najpierw 1., potem 2.).",
            "Each test = a NEW conversation. Test A has two questions in the same conversation (first 1., then 2.)."))
    print(L("Kolejność dowolna. Po serii wpisz: python reforger_eval.py score\n",
            "Any order. After the series run: python reforger_eval.py score\n"))
    for test in TESTS:
        turns = test["turns_en"] if EN else test["turns"]
        print("=" * 78)
        print(f"TEST {test['id']}: {test['name']}")
        for i, q in enumerate(turns, 1):
            label = L("pytanie", "question") + (f" {i}/{len(turns)}" if len(turns) > 1 else "")
            print(f"--- {label} ---")
            print(q)
        print()


def evaluate_answer(text: str, rules: dict) -> dict:
    must = [(label, bool(fn(text))) for label, fn in rules["must"]]
    bad = [label for label, fn in list(rules["bad"]) + COMMON_BAD if fn(text)]
    bonus = [(label, bool(fn(text))) for label, fn in rules.get("bonus", [])]
    return {"must": must, "bad": bad, "bonus": bonus}


def cmd_score(path: Path, md_path: Path | None) -> None:
    if not path.exists():
        sys.exit(L(f"Nie znaleziono pliku: {path}", f"File not found: {path}"))
    data = json.loads(path.read_text(encoding="utf-8"))
    sessions = data.get("sessions", [])
    runs: dict[str, list[dict]] = defaultdict(list)
    ignored = 0
    for s in sessions:
        turns = s.get("turns", [])
        users = [t for t in turns if t.get("role") == "user"]
        if not users:
            continue
        test, questions = match_test(users[0]["content"])
        if not test:
            ignored += 1
            continue
        answers = []
        for q in questions:
            key = norm(q)[:80]
            found = None
            for idx, t in enumerate(turns):
                if t.get("role") == "user" and norm(t["content"]).startswith(key):
                    nxt = turns[idx + 1] if idx + 1 < len(turns) else None
                    found = nxt if nxt and nxt.get("role") == "assistant" else None
            answers.append(found)   # None = to pytanie nie zostało zadane / nie ma odpowiedzi
        traces = s.get("traces", [])
        repeated = len(users) - len(test["turns"])
        run = {"session": s.get("id", "?")[:8], "created": s.get("created_at", ""),
               "calls": len(traces), "errors": sum(1 for t in traces if t.get("status") == "error"),
               "turn_results": [], "answered_turns": sum(1 for a in answers if a), "expected_turns": len(test["turns"]),
               "extra_questions": max(0, repeated)}
        for i, rules in enumerate(test["rules"]):
            if i < len(answers) and answers[i] is not None:
                text = answers[i]["content"]
                res = evaluate_answer(text, rules)
                res["no_guess"] = bool(re.search(r"Nie zgaduj|nie wykonał w tej turze|Nie udało się zebrać"
                                                 r"|I am not guessing|made no MCP reads|No confirmed MCP results could be collected", text))
                run["turn_results"].append(res)
            else:
                run["turn_results"].append(None)
        runs[test["id"]].append(run)

    lines: list[str] = []
    out = lines.append
    out(L("# Wyniki zestawu testowego\n", "# Test set results\n"))
    out(L(f"Plik: `{path}`; rozmów dopasowanych do testów: {sum(len(v) for v in runs.values())}, pominiętych: {ignored}\n",
          f"File: `{path}`; conversations matched to tests: {sum(len(v) for v in runs.values())}, skipped: {ignored}\n"))
    summary_rows = []
    for test in TESTS:
        tid = test["id"]
        if tid not in runs:
            out(f"## Test {tid}: {test['name']}\n" + L("_brak uruchomień_\n", "_no runs_\n"))
            summary_rows.append((tid, test["name"], 0, None, None))
            continue
        out(f"## Test {tid}: {test['name']}\n")
        pct_all, bad_all = [], []
        for n, run in enumerate(sorted(runs[tid], key=lambda r: r["created"]), 1):
            extra = (L(", dodatkowych/powtórzonych pytań w rozmowie: ", ", extra/repeated questions in the conversation: ")
                     + str(run["extra_questions"])) if run["extra_questions"] else ""
            out(L(f"**Uruchomienie {n}** (sesja {run['session']}, wywołań MCP w śladzie: {run['calls']}, błędów: {run['errors']}{extra})\n",
                  f"**Run {n}** (session {run['session']}, MCP calls in the trace: {run['calls']}, errors: {run['errors']}{extra})\n"))
            for ti, res in enumerate(run["turn_results"], 1):
                if res is None:
                    out(L(f"- tura {ti}: brak odpowiedzi\n", f"- turn {ti}: no answer\n"))
                    continue
                hit = sum(1 for _, ok in res["must"] if ok)
                tot = len(res["must"])
                pct_all.append(100 * hit / tot)
                bad_all.append(len(res["bad"]))
                missing = [label for label, ok in res["must"] if not ok]
                prefix = L(f"tura {ti}: ", f"turn {ti}: ") if len(test["turns"]) > 1 else ""
                out(f"- {prefix}" + L("wymagane", "required") + f" {hit}/{tot}"
                    + (L("; brakuje: ", "; missing: ") + "; ".join(missing) if missing else ""))
                out(f"- {prefix}" + L("błędy znane", "known errors") + f": {len(res['bad'])}"
                    + (f" -> {'; '.join(res['bad'])}" if res["bad"] else ""))
                if res.get("bonus"):
                    got = [label for label, ok in res["bonus"] if ok]
                    out(f"- {prefix}" + L("spoza danych BK (nie wlicza się)", "outside the BK data (not counted)")
                        + f": {len(got)}/{len(res['bonus'])}" + (f" -> {'; '.join(got)}" if got else ""))
                if res.get("no_guess"):
                    out(f"- {prefix}" + L("UWAGA: to komunikat awaryjny ('nie zgaduję'), nie odpowiedź merytoryczna",
                                          "NOTE: this is a fallback message ('not guessing'), not a real answer"))
            out("")
        summary_rows.append((tid, test["name"], len(runs[tid]),
                             sum(pct_all) / len(pct_all) if pct_all else None,
                             sum(bad_all) / len(bad_all) if bad_all else None))
    out(L("## Podsumowanie\n", "## Summary\n"))
    out(L("| Test | Nazwa | Uruchomień | Średnio wymaganych | Średnio błędów znanych |",
          "| Test | Name | Runs | Average required | Average known errors |"))
    out("|---|---|---|---|---|")
    for tid, name, n, pct, bad in summary_rows:
        out(f"| {tid} | {name} | {n} | {'-' if pct is None else f'{pct:.0f}%'} | {'-' if bad is None else f'{bad:.1f}'} |")
    text = "\n".join(lines)
    print(text)
    if md_path:
        md_path.write_text(text, encoding="utf-8")
        print(L(f"\n(zapisano: {md_path})", f"\n(saved: {md_path})"))


# ---------------------------------------------------------------------------------------------
# LOG
# ---------------------------------------------------------------------------------------------
def read_log(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    for enc in ("utf-8", "cp1250", "cp852"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


TS = re.compile(r"\[\d+/\w+/\d{4} (\d\d):(\d\d):(\d\d)\]")


def seconds(line: str):
    m = TS.search(line)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else None


def cmd_log(path: Path) -> None:
    if not path.exists():
        sys.exit(L(f"Nie znaleziono pliku: {path}", f"File not found: {path}"))
    text = read_log(path).replace("\r", "")
    segments: list[list[str]] = []
    for line in text.split("\n"):
        if re.search(r'"POST /api/sessions/[0-9a-f]+/chat ', line):
            segments.append([line])
        elif segments:
            segments[-1].append(line)
    if not segments:
        print(L("Nie znaleziono żadnej tury czatu (brak linii POST .../chat).", "No chat turn found (no POST .../chat lines)."))
        return
    cfg = re.findall(r"\[CONFIG\][^\n]*", text)
    if cfg:
        print(cfg[-1].strip())
    print(L(f"Tur czatu w logu: {len(segments)}\n", f"Chat turns in the log: {len(segments)}\n"))
    for i, seg in enumerate(segments, 1):
        start = seconds(seg[0])
        polls = sorted(seconds(l) for l in seg if "GET /api/sessions/" in l and seconds(l) is not None)
        duration = None
        if start is not None:
            # Przeglądarka odpytuje serwer co ~1 s, dopóki tura trwa. Koniec = koniec pierwszej
            # ciągłej serii zapytań (przerwa > 3 s to już ruch po zakończeniu tury).
            end = start
            for t in polls:
                if t - end <= 3:
                    end = max(end, t)
                else:
                    break
            duration = end - start
        body = "\n".join(seg)
        calls = len(re.findall(r"\[MCP \d+/\d+\]", body))
        errors = len(re.findall(r"-> (?:B\S{1,3}D|ERROR)", body))
        ctx = [int(x) for x in re.findall(r"context_tokens=(\d+)", body)]
        outs = re.findall(r"reason=(\w+) context_tokens=\d+ output_tokens=(\d+)", body)
        # Od 2.0.0 log może być po polsku albo po angielsku (REFORGER_LANG): każdy wzorzec zna oba warianty.
        flags = {
            "REPAIR": len(re.findall(r"\[REPAIR\]", body)),
            L("VIEW (z pamięci)", "VIEW (from memory)"): len(re.findall(r"\[VIEW\]", body)),
            L("VERIFY uwagi", "VERIFY issues"): len(re.findall(r"\[VERIFY\] (?:UWAGI|ISSUES)", body)),
            "DUP": len(re.findall(r"\[DUP\]", body)),
            "STALL": len(re.findall(r"\[STALL\]", body)),
            L("pusta odpowiedź", "empty answer"): len(re.findall(r"Pusta odpowied|Empty answer", body)),
            L("UWAGA kontekst", "WARNING context"): len(re.findall(r"\[(?:UWAGA|WARNING)\]", body)),
            L("synteza awaryjna", "emergency synthesis"): len(re.findall(r"osobna synteza|synteza awaryjna z wybranych|emergency synthesis from selected",
                                                                         body)),   # stare i nowe logi
            L("ponowienie po pustej generacji", "retry after an empty generation"): len(re.findall(r"ponowienie z niskim|retry with low", body)),
            L("limit generacji (reason=length)", "generation limit (reason=length)"): len(re.findall(r"reason=length", body)),
            # od 1.8.3
            L("odpowiedź bez narzędzi [KONIEC]", "answer without tools [END]"):
                len(re.findall(r"\[KONIEC\] odpowiedź bez narzędzi|\[END\] answer without tools", body)),
            L("szkic odrzucony [SZKIC]", "draft rejected [DRAFT]"): len(re.findall(r"\[SZKIC\] odrzucony|\[DRAFT\] rejected", body)),
            L("zostaje pierwszy szkic", "the first draft stays"): len(re.findall(r"zostaje pierwszy szkic|the first draft stays", body)),
            L("odrzucone wywołanie (bez limitu)", "rejected call (no limit used)"):
                len(re.findall(r"Wywołanie nie zużyło limitu|The call did not use up the limit", body)),
            L("pełny widok klasy (limit=1)", "full class view (limit=1)"): len(re.findall(r"pełny widok klasy|full class view", body)),
            L("hierarchia z pliku gry [BAZA]", "hierarchy from a game file [BASE]"):
                len(re.findall(r"\[BAZA\] \w+: klasy bazowe z pliku gry \S+ -> (?!nie ustalono)"
                               r"|\[BASE\] \w+: base classes from game file \S+ -> (?!not determined)", body)),
            # od 1.8.7
            L("rozumowanie przerwane", "reasoning aborted"): len(re.findall(r"rozumowanie przerwane|reasoning aborted", body)),
            L("wyciek rozumowania [ROZUMOWANIE]", "reasoning leak [REASONING]"):
                len(re.findall(r"\[ROZUMOWANIE\] usunięto|\[REASONING\] removed", body)),
            L("zapętlenie [POWTÓRZENIA]", "loop [REPEATS]"): len(re.findall(r"\[(?:POWTÓRZENIA|REPEATS)\]", body)),
            L("oznaczenia w treści [OZNACZENIA]", "marks in the text [MARKS]"): len(re.findall(r"\[(?:OZNACZENIA|MARKS)\]", body)),
            # od 2.0.3
            L("deklaracja enuma z pliku gry [ENUM]", "enum declaration from a game file [ENUM]"):
                len(re.findall(r"\[ENUM\] \w+: (?:deklaracja z|declaration from)", body)),
            L("przypomnienie o limicie [LIMIT]", "limit reminder [LIMIT]"): len(re.findall(r"\[LIMIT\]", body)),
            L("brak kodu po błędzie kompilacji", "no code after a compile error"):
                len(re.findall(r"brak poprawionego kodu|no corrected code in the answer", body)),
        }
        last = outs[-1] if outs else ("?", "?")
        dur = duration if duration is not None else "?"
        print(L(f"Tura {i}: wywołań MCP {calls}, błędów {errors}, czas {dur} s, "
                f"kontekst start {ctx[0] if ctx else '?'} / szczyt {max(ctx) if ctx else '?'}, "
                f"odpowiedź końcowa: {last[1]} tokenów (reason={last[0]})",
                f"Turn {i}: MCP calls {calls}, errors {errors}, time {dur} s, "
                f"context start {ctx[0] if ctx else '?'} / peak {max(ctx) if ctx else '?'}, "
                f"final answer: {last[1]} tokens (reason={last[0]})"))
        raised = {k: v for k, v in flags.items() if v}
        print(L("   zdarzenia: ", "   events: ") + (", ".join(f"{k}={v}" for k, v in raised.items()) if raised else L("brak", "none")))
        for item in re.findall(r"\[VERIFY\]   - ([^\n]+)", body):
            print(L("   weryfikator: ", "   verifier: ") + item.strip()[:240])
        if calls == 0:
            print(L("   UWAGA: tura bez żadnego wywołania MCP (odpowiedź z historii/pamięci modelu)",
                    "   NOTE: a turn without any MCP call (answer from history/model memory)"))
        print()


def main(argv: list[str]) -> None:
    if len(argv) < 2 or argv[1] not in ("questions", "score", "log"):
        print(__doc__)
        return
    if argv[1] == "questions":
        cmd_questions()
    elif argv[1] == "score":
        args = argv[2:]
        md = None
        if "--md" in args:
            k = args.index("--md")
            md = Path(args[k + 1]) if k + 1 < len(args) else Path("wyniki.md")
            del args[k:k + 2]
        path = Path(args[0]) if args else Path("assistant_web_data") / "conversations.json"
        cmd_score(path, md)
    else:
        if len(argv) < 3:
            sys.exit(L("Użycie: python reforger_eval.py log log.txt", "Usage: python reforger_eval.py log log.txt"))
        cmd_log(Path(argv[2]))


if __name__ == "__main__":
    main(sys.argv)
